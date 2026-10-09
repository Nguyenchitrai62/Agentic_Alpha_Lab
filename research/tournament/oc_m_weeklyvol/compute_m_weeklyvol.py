"""oc_m_weeklyvol: IDEAS9 #5 weekly-frozen vol distance table (MANUAL).

Pre-registered rows (PLAN.md, frozen before any run):
  M5_human    deployed MANUAL reference (must reproduce oc_manualcap exactly)
  V1_WEEKLY   M5_human with every sigma-scaled bracket distance computed from
              the weekly-frozen sigma360 (Sunday 00 UTC print, no recompute)
  V2_WEEKLY5T V1 + every sigma-derived price rounded to the 5-tick grid

sigma360 = the engine's own sigma_4h estimator (std of 4h open-to-open pct
returns, trailing 360 bars, min_periods 120 = prep_idx sig4). For a holding
bar opening at T, the frozen sigma is sig4[jw] with jw = last j with
T_j = idx[j]+4h <= SUN(T) (most recent Sunday 00:00 UTC <= T); fallback to
the per-bar sig4 when no jw exists or sig4[jw] is NaN. V1/V2 swap the whole
prep sig4 array (dip lv/TP/SL + budget, book entry/SL/TP/tighten/scales);
everything else is exactly M5_human (oc_m_conflict harness: pipe v367,
agents ON, win_start=15, sleeve_start=16, night skip, gate costs).
V2 rounds dip lv/tp/sl, book entry px/SL/TP, tighten moves and scale-order
limits via a patched simulate (audited inspect.getsource pattern cf.
oc_m_breakeven); M5/V1 use the unpatched eu.simulate.

  python research/tournament/oc_m_weeklyvol/compute_m_weeklyvol.py --validate
  python research/tournament/oc_m_weeklyvol/compute_m_weeklyvol.py --heavy
"""

from __future__ import annotations

import argparse
import gc
import inspect
import json
import pickle
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"
TMP = HERE / "tmp"
CACHE = TMP / "oc_m_weeklyvol_runs.pkl"
ENGINE_USER = (RD / "engine_user" / "engine_user.py")

# ---- pre-registered constants (mirrored in tests) ----
WIN_START = 15
SLEEVE_START = 16
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
TICKS = {"BTCUSDT": 0.10, "ETHUSDT": 0.01, "SOLUSDT": 0.01,
         "BNBUSDT": 0.10, "XRPUSDT": 0.0001}  # frozen exchange ticks
TICK_STEP = {c: 5.0 * t for c, t in TICKS.items()}  # V2 5-tick grid step
MAKER, TAKER, FUND_LONG = 0.0002, 0.00055, 0.0001  # gate costs
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
ROWS = ["M5_human", "V1_WEEKLY", "V2_WEEKLY5T"]
ENGINE_MODE = {"M5_human": "ref", "V1_WEEKLY": "v1", "V2_WEEKLY5T": "v2"}
HEARTBEAT_S = 600

# ---- V2 engine patch anchors (counts asserted at build time) ----
DIP_LV = "lv = o1[i][a] * (1 - k * sig_sl[i][a])"
DIP_TP = ("tp = lv * (1 + (m_sleeve_tp if sleeve_tp is None "
          "else float(sleeve_tp(i, a, r, f))) * sg)")
DIP_SL = "sl = lv * (1 - _msl(a) * sg)"
BOOK_PX = ('T["side"][a], T["px"][a], T["w"][a] = '
           "sgn, Oa[0] * (1 - sgn * off), size")
BOOK_SLTP = ('T["sl"][a], T["tp"][a], T["sd"][a] = '
             "px * (1 - ps * m_sl * sdv), px * (1 + ps * mt * sdv), sdv")
TIGHTEN_POL = "new = Oa[0] * (1 - side * P.get(\"tighten\", 1.5) * sd_a)"
TIGHTEN_NP = "new = Oa[0] * (1 - side * k_t * sd_a)"
SCALE_ADD = "Oa[0] * (1 - side * off)"  # x2: policy add + non-policy add
SCALE_RED = "Oa[0] * (1 + side * off)"  # x3: policy reduce + 2 non-policy

_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print("[hb %sZ] %s alive"
              % (datetime.now(timezone.utc).strftime("%H:%M:%S"), tag),
              flush=True)


# --------------------------------------------------------------------------
# Pure helpers (unit-tested; no data access)
# --------------------------------------------------------------------------
def anchor_of(t: pd.Timestamp, shift: int) -> int:
    """Dev/most-recent year index 0..4 of holding-bar open T on phase shift.

    Year y covers [a0, min(a0+365d, live1)) with a0 = ANCH5[y]+sh.
    Bars at/after live1 use the last anchor's stats (beyond scoring).
    """
    sh = pd.Timedelta(hours=shift)
    live1 = Y1 + sh
    tt = pd.Timestamp(t)
    if tt.tzinfo is None:
        tt = tt.tz_localize("UTC")
    if tt < pd.Timestamp(ANCH5[0], tz="UTC") + sh:
        return 0
    for y, a in enumerate(ANCH5):
        a0 = pd.Timestamp(a, tz="UTC") + sh
        a1 = min(a0 + pd.Timedelta(days=365), live1)
        if a0 <= tt < a1:
            return y
    return 4


def geo_mean_monthly(Rs) -> float:
    g = 1.0
    for r in Rs:
        g *= 1.0 + float(r) / 100.0
    return 100.0 * (g ** (1.0 / len(Rs)) - 1.0)


def week_start_of(t: pd.Timestamp) -> pd.Timestamp:
    """Most recent Sunday 00:00 UTC <= t (the print time of the weekly table)."""
    tt = pd.Timestamp(t)
    if tt.tzinfo is None:
        tt = tt.tz_localize("UTC")
    wd = (tt.weekday() + 1) % 7  # days since Sunday (Mon=0..Sun=6)
    return (tt - pd.Timedelta(days=wd)).floor("D")


def build_weekly_sig4(idx: pd.DatetimeIndex,
                      sig4: np.ndarray) -> tuple[np.ndarray, dict]:
    """Freeze sig4 at the Sunday print (same shape; causal by construction).

    For holding-bar open T = idx[i]+4h with SUN(T) the most recent Sunday
    00:00 UTC <= T, weekly[i,a] = sig4[jw,a] where jw = last j with
    idx[j]+4h <= SUN(T). Fallback (frozen): jw < 0 or sig4[jw,a] NaN ->
    per-bar sig4[i,a] (NaN per-bar stays NaN, identical to M5_human there).
    Uses only the decision index and the sig4 array (no 1m/minute/fill
    data, no future opens: jw < i except the measure-zero T == Sunday bar).
    """
    idx = pd.DatetimeIndex(idx)
    n = len(idx)
    na = np.asarray(sig4).shape[1]
    T = idx + pd.Timedelta(hours=4)
    ws = pd.DatetimeIndex([week_start_of(t) for t in T])
    jw = np.searchsorted(T.asi8, ws.asi8, side="right") - 1
    base = np.asarray(sig4, dtype=float)
    out = base.copy()
    fb = np.zeros((n, na), dtype=bool)
    for a in range(na):
        col = base[:, a]
        take = np.zeros(n, dtype=bool)
        vals = np.full(n, np.nan)
        ok = jw >= 0
        vals[ok] = col[np.clip(jw[ok], 0, n - 1)]
        take = ok & np.isfinite(vals)
        out[:, a] = np.where(take, vals, col)
        fb[:, a] = ~take
    n_weeks = int(pd.DatetimeIndex(ws).nunique())
    fin = np.isfinite(base) & np.isfinite(out)
    frozen = fin & (out != base)
    with np.errstate(divide="ignore", invalid="ignore"):
        dev = np.abs(out / base - 1.0)
    diag = dict(
        n_weeks=int(n_weeks),
        frozen_frac=round(float(frozen.mean()) if fin.size else 0.0, 6),
        fallback_frac=round(float(fb.mean()), 6),
        mean_abs_dev=round(float(dev[fin & (out != base)].mean())
                           if (fin & (out != base)).any() else 0.0, 6),
    )
    return out, diag


def round5(price: float, step: float) -> float:
    """Nearest multiple of step (ties to even); non-finite passes through."""
    p, s = float(price), float(step)
    if not np.isfinite(p) or not np.isfinite(s) or s <= 0:
        return p
    return float(np.round(p / s) * s)


def _slot_r5(tick_step: dict):
    """5-tick rounding closure: nearest grid point from price + frozen tick."""
    steps = dict(tick_step)

    def _r5(px, sym):
        return round5(px, steps.get(sym, 0.0))

    return _r5


def make_weekly5t_simulate(eu, tick_step: dict = TICK_STEP):
    """eu.simulate with every sigma-derived price rounded to the 5-tick grid.

    Rounded (nearest grid point, frozen ticks, cols[a] symbol lookup):
    dip lv/tp/sl, book entry px + SL/TP, tighten SL moves, scale-order
    limits (policy and non-policy spellings). Nothing else changes; the
    rounding helper uses only the computed price + the frozen tick.
    """
    src = inspect.getsource(eu.simulate)
    assert src.count(DIP_LV) == 1, "dip lv anchor not unique"
    assert src.count(DIP_TP) == 1, "dip tp anchor not unique"
    assert src.count(DIP_SL) == 1, "dip sl anchor not unique"
    assert src.count(BOOK_PX) == 1, "book px anchor not unique"
    assert src.count(BOOK_SLTP) == 1, "book sltp anchor not unique"
    assert src.count(TIGHTEN_POL) == 1, "policy tighten anchor not unique"
    assert src.count(TIGHTEN_NP) == 1, "non-policy tighten anchor not unique"
    assert src.count(SCALE_ADD) == 2, "scale-add anchors != 2"
    assert src.count(SCALE_RED) == 3, "scale-reduce anchors != 3"
    patched = src
    patched = patched.replace(
        DIP_LV, "lv = _r5(o1[i][a] * (1 - k * sig_sl[i][a]), cols[a])")
    patched = patched.replace(
        DIP_TP, ("tp = _r5(lv * (1 + (m_sleeve_tp if sleeve_tp is None else "
                 "float(sleeve_tp(i, a, r, f))) * sg), cols[a])"))
    patched = patched.replace(
        DIP_SL, "sl = _r5(lv * (1 - _msl(a) * sg), cols[a])")
    patched = patched.replace(
        BOOK_PX, ('T["side"][a], T["px"][a], T["w"][a] = '
                  "sgn, _r5(Oa[0] * (1 - sgn * off), cols[a]), size"))
    patched = patched.replace(
        BOOK_SLTP, ('T["sl"][a], T["tp"][a], T["sd"][a] = '
                    "_r5(px * (1 - ps * m_sl * sdv), cols[a]), "
                    "_r5(px * (1 + ps * mt * sdv), cols[a]), sdv"))
    patched = patched.replace(
        TIGHTEN_POL,
        "new = _r5(Oa[0] * (1 - side * P.get(\"tighten\", 1.5) * sd_a), "
        "cols[a])")
    patched = patched.replace(
        TIGHTEN_NP,
        "new = _r5(Oa[0] * (1 - side * k_t * sd_a), cols[a])")
    patched = patched.replace(
        SCALE_ADD, "_r5(Oa[0] * (1 - side * off), cols[a])")
    patched = patched.replace(
        SCALE_RED, "_r5(Oa[0] * (1 + side * off), cols[a])")
    g = dict(eu.simulate.__globals__)
    g["_r5"] = _slot_r5(tick_step)
    g["_TICK5"] = dict(tick_step)
    ns: dict = {}
    exec(patched, g, ns)  # noqa: S102 - audited pattern (cf. oc_m_breakeven)
    fn = ns.get(eu.simulate.__name__)
    if fn is None:  # pragma: no cover
        raise RuntimeError("patched simulate missing")
    fn._patched_src = patched  # test hook
    fn._tick_step = dict(tick_step)
    return fn


def wait_for_ram(min_gb: float = 2.0) -> None:
    need_kb = min_gb * 1048576
    while True:
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"],
                text=True, timeout=120)
            free_kb = float(out.strip().split()[0])
        except Exception as exc:
            print("m_weeklyvol: RAM check failed (%s), retry in 300 s" % exc,
                  flush=True)
            time.sleep(300)
            continue
        if free_kb > need_kb:
            return
        print("m_weeklyvol: %.2f GB free, waiting for > %.0f GB"
              % (free_kb / 1048576, min_gb), flush=True)
        time.sleep(300)


# --------------------------------------------------------------------------
# Stage 0: reproduce the M5_human baseline (read-only) or STOP
# --------------------------------------------------------------------------
def validate_baselines() -> dict:
    man = json.loads(
        (ROOT / "research/diagnostics/oc_manualcap/results.json").read_text())
    m5 = man["rows"]["M5_human"]
    assert (m5["R5"], m5["W"], m5["maxDD"], m5["fullDD"], m5["book_win"]) == \
        (3.728, 0.847, 17.94, 17.79, 0.6482), m5
    print("M5_human reference OK: R5 3.728 / W 0.847 / maxDD 17.94 / "
          "fullDD 17.79 / win .6482", flush=True)
    assert set(TICKS) == set(MAJORS), sorted(TICKS)
    assert all(v == 5.0 * TICKS[c] for c, v in TICK_STEP.items()), TICK_STEP
    print("ticks frozen: %s" % (TICK_STEP,), flush=True)
    src = ENGINE_USER.read_text()
    for name, expect in (("DIP_LV", 1), ("DIP_TP", 1), ("DIP_SL", 1),
                         ("BOOK_PX", 1), ("BOOK_SLTP", 1),
                         ("TIGHTEN_POL", 1), ("TIGHTEN_NP", 1),
                         ("SCALE_ADD", 2), ("SCALE_RED", 3)):
        anchor = globals()[name]
        got = src.count(anchor)
        assert got == expect, (name, got, expect)
    print("engine anchors OK (1/1/1/1/1/1/1/2/3)", flush=True)
    assert week_start_of(pd.Timestamp("2022-01-05 12:00", tz="UTC")) == \
        pd.Timestamp("2022-01-02", tz="UTC")
    print("weekly rule frozen: sigma360 print Sunday 00 UTC, V1 plain, "
          "V2 + 5-tick grid", flush=True)
    return {"m5_ref": {"R5": 3.728, "W": 0.847, "maxDD": 17.94,
                       "fullDD": 17.79}}

# --------------------------------------------------------------------------
# Stage 1: 4-phase MANUAL runs (heavy)
# --------------------------------------------------------------------------
def run_phase(shift: int):
    wait_for_ram(2.0)
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load("pod_mwv_%d" % shift,
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load("hist_mwv_%d" % shift, ROOT / "backend/history_tm.py")
    v221 = pof._load("v221_mwv_%d" % shift,
                     pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load("fw_mwv_%d" % shift, ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    sims = {"ref": eu.simulate, "v2": make_weekly5t_simulate(eu)}
    cap = {}
    stats_hold = {}

    def _summ(idx, net, eq, eq_min, g, stats, eq_max=None):
        cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
                   eq_max=(eq if eq_max is None else eq_max).copy())
        stats_hold.update(stats)
        return {}

    eu.summarize = _summ
    sh = pd.Timedelta(hours=shift)
    live0, live1 = DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    cols = list(books154.columns)
    assert set(cols) == set(MAJORS), cols
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, cols)
    del M
    gc.collect()
    idx = prep["idx"]
    weekly, wdiag = build_weekly_sig4(idx, prep["sig4"])
    prep_w = dict(prep, sig4=weekly)
    print("shift %d: weeks=%d frozen=%.4f fallback=%.4f meandev=%.4f" %
          (shift, wdiag["n_weeks"], wdiag["frozen_frac"],
           wdiag["fallback_frac"], wdiag["mean_abs_dev"]), flush=True)
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    books = std_books.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / ("r2_table_s%d.parquet" % shift)
    hours = np.asarray((idx + pd.Timedelta(hours=4)).hour)
    night = (20 + shift) % 24
    out = {}
    for row in ROWS:
        mode = ENGINE_MODE[row]
        kw, trade = pof.pipe_setup("v367", hist, v221, v216, idx, cols, True)
        pol = trade["policy"]
        trade["policy"] = lambda i, a, st, pol=pol: (
            ("wait" if st["pos"] == 0 else "hold")
            if hours[i] == night else pol(i, a, st))
        kw["sleeve_start"] = SLEEVE_START
        kw["sleeve_filter"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0
        events: list = []
        stats_hold.clear()
        use_prep = prep if mode == "ref" else prep_w
        sim = sims["v2"] if mode == "v2" else eu.simulate
        sim(books, opens, use_prep, trade=trade, win_start=WIN_START,
            events=events, **kw)
        m = pof.metrics(cap["idx"], cap["eq"], cap["eq_min"], cap["eq_max"],
                        ANCH5, live0, live1, sh)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        run = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                   eq=(cap["eq"][lv] / base).tolist(),
                   eq_min=(cap["eq_min"][lv] / base).tolist())
        years = []
        ch = []
        for y, a in enumerate(ANCH5):
            a0 = pd.Timestamp(a, tz="UTC") + sh
            a1 = min(a0 + pd.Timedelta(days=365), live1)
            ev = [e for e in events
                  if a0 <= pd.Timestamp(e["t"]) < a1 + pd.Timedelta(hours=8)]
            ts = v216.v213.trade_stats(ev)
            nb = sum((ts.get(k) or {}).get("trades", 0) for k in ("dev", "_hidden"))
            wb = sum(round((ts.get(k) or {}).get("win_rate", 0)
                           * (ts.get(k) or {}).get("trades", 0))
                     for k in ("dev", "_hidden"))
            rr = [float(e["ret"]) for e in ev if e["kind"] in RUNG_KINDS
                  and "ret" in e]
            years.append(dict(nb=int(nb), wb=int(wb), nr=len(rr),
                              wr=int(sum(r > 0 for r in rr))))
            yy = m["yearly"][y]
            ch.append(dict(net=yy["net_pct"] / 100, dd=yy["dd_1m_pct"]))
        out[row] = dict(run=run, wins=years, cross=ch)
        print(shift, row, [round(100 * v["net"], 1) for v in ch],
              [v["dd"] for v in ch], flush=True)
        del events
        gc.collect()
    out["_weekly"] = wdiag
    del opens, prep, books
    gc.collect()
    return shift, out


def check_harness_identity(allres) -> None:
    """My M5_human rerun must equal the stored oc_manualcap run bit-exact."""
    stored = pickle.loads(
        (ROOT / "research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl").read_bytes())
    maxd = 0.0
    for s in range(4):
        for k in ("eq", "eq_min"):
            a = np.asarray(allres[s]["M5_human"]["run"][k], dtype=float)
            b = np.asarray(stored[s]["M5_human"]["run"][k], dtype=float)
            assert a.shape == b.shape, (s, k, a.shape, b.shape)
            maxd = max(maxd, float(np.max(np.abs(a - b))))
    print("M5_human harness identity: max abs d(eq) = %.3e" % maxd, flush=True)
    assert maxd <= 1e-12, "harness drift %.3e -- STOP" % maxd


def runs_for_reset(allres, row):
    return {s: {row: allres[s][row]["run"]} for s in allres}


def score_all(allres) -> dict:
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    v388 = pof._load("v388_mwv_score", RD / "v388/v388_bot_stop_distance.py")
    rm = pof._load("reset_mwv_score",
                   ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    fr = {row: float(np.mean([float(allres[s]["_weekly"]["frozen_frac"])
                              for s in range(4)]))
          if row != "M5_human" else 0.0 for row in ROWS}
    table = {}
    for row in ROWS:
        runs = runs_for_reset(allres, row)
        yr = [rm.year_reset(runs, row, y) for y in range(5)]
        Rs = [y["R"] for y in yr]
        DDs = [y["DD"] for y in yr]
        e, mn = v388.mix(runs, row, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        fullDD = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        nb = sum(allres[s][row]["wins"][y]["nb"] for s in range(4) for y in range(5))
        wb = sum(allres[s][row]["wins"][y]["wb"] for s in range(4) for y in range(5))
        nr = sum(allres[s][row]["wins"][y]["nr"] for s in range(4) for y in range(5))
        wr = sum(allres[s][row]["wins"][y]["wr"] for s in range(4) for y in range(5))
        r_ph = []
        for s in range(4):
            yy = allres[s][row]["cross"]
            r_ph.append(100 * (np.prod([1 + v["net"] for v in yy]) ** (1 / 60) - 1))
        table[row] = dict(
            years_R=[y["R"] for y in yr], years_DD=[y["DD"] for y in yr],
            years_book_win=[
                round(sum(allres[s][row]["wins"][y]["wb"] for s in range(4))
                      / max(sum(allres[s][row]["wins"][y]["nb"] for s in range(4)), 1), 4)
                for y in range(5)],
            years_rung_win=[
                round(sum(allres[s][row]["wins"][y]["wr"] for s in range(4))
                      / max(sum(allres[s][row]["wins"][y]["nr"] for s in range(4)), 1), 4)
                for y in range(5)],
            R5=round(geo_mean_monthly(Rs), 3), W=round(min(Rs), 3),
            maxDD=round(max(DDs), 2), fullDD=fullDD,
            Rdev4=round(geo_mean_monthly(Rs[:4]), 3),
            Wdev4=round(min(Rs[:4]), 3),
            DDdev4=round(max(DDs[:4]), 2),
            losing_dev4=sum(r < 0 for r in Rs[:4]),
            Rlast=round(Rs[4], 3),
            book_trades=int(nb), book_win=round(wb / nb, 4) if nb else None,
            rung_trades=int(nr), rung_win=round(wr / nr, 4) if nr else None,
            win_all=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None,
            cross_Rmean=round(float(np.mean(r_ph)), 3),
            frozen_frac=round(fr[row], 6),
        )
    return table


def robust_pick(table: dict) -> str:
    """AGENTS.md robust criterion on dev4 ONLY: eligible = DD<=20, no losing
    year; prefer dev4 mean >= 5; then highest dev4 WORST; ties -> higher mean."""
    cand = [r for r in ("V1_WEEKLY", "V2_WEEKLY5T")
            if table[r]["DDdev4"] <= 20 and table[r]["losing_dev4"] == 0]
    if not cand:
        return "none-eligible"
    hi = [r for r in cand if table[r]["Rdev4"] >= 5.0]
    pool = hi if hi else cand
    best = max(pool, key=lambda r: (table[r]["Wdev4"], table[r]["Rdev4"]))
    return best


def eligibility(table: dict) -> dict:
    out = {}
    for row in ROWS:
        t = table[row]
        out[row] = bool(t["DDdev4"] <= 20 and t["losing_dev4"] == 0)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--heavy", action="store_true")
    args = ap.parse_args()
    base = validate_baselines()
    if not args.heavy:
        print("validate-only done (no engine run). Use --heavy for the "
              "4-phase runs.", flush=True)
        return
    hb = threading.Thread(target=heartbeat, args=("oc_m_weeklyvol",),
                           daemon=True)
    hb.start()
    TMP.mkdir(parents=True, exist_ok=True)
    if CACHE.exists():
        allres = pickle.loads(CACHE.read_bytes())
        missing = [s for s in range(4) if s not in allres]
        print("loaded cached phase runs (%d/4)" % len(allres), flush=True)
    else:
        allres, missing = {}, list(range(4))
    for shift in missing:
        s, out = run_phase(shift)
        allres[s] = out
        CACHE.write_bytes(pickle.dumps(allres))
        print("phase %d cached" % s, flush=True)
    _stop_hb.set()
    check_harness_identity(allres)
    table = score_all(allres)
    elig = eligibility(table)
    pick = robust_pick(table)
    weekly_all = {str(s): allres[s].get("_weekly") for s in range(4)}
    out = {
        "meta": {
            "idea": "oc_m_weeklyvol: IDEAS9 #5 weekly-frozen vol table (MANUAL)",
            "harness": ("MANUAL 4-phase (M5 pipe v367, human schedule "
                        "win_start=15 / sleeve_start=16, night bar skipped, "
                        "agents ON, gate costs maker 0.0002 / taker 0.00055 / "
                        "longs pay 0.0001 per 8h); harness copied exactly "
                        "from oc_m_conflict, only the sigma input changed"),
            "metric": ("reset_metric.year_reset per anchor + v388.mix "
                       "full-path DD (v421/v422 convention); V1 vs V2 judged "
                       "on dev years 2021-2024 only; last year POST-RELEASE, "
                       "scored once for the pick + M5_human"),
            "rows": {
                "M5_human": "deployed reference (reproduces oc_manualcap)",
                "V1_WEEKLY": "weekly-frozen sigma360 (Sunday 00 UTC print)",
                "V2_WEEKLY5T": "V1 + 5-tick grid rounding of sigma prices",
            },
            "baseline": base,
            "ticks": dict(TICKS),
            "weekly": weekly_all,
            "eligibility_dev4": elig,
            "pick_dev4": pick,
            "costs": {"maker": MAKER, "taker": TAKER, "fund_long_8h": FUND_LONG},
            "caveat": ("k frozen ex-ante (3.0/4.0, 8.0, 5.0/10.0, 0.75), "
                       "ticks frozen ex-ante, Sundays are the public "
                       "calendar; no fits; most recent year is "
                       "POST-RELEASE context, scored once, never used "
                       "to choose"),
        },
        "rows": table,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for row, v in table.items():
        print(row, "R5", v["R5"], "W", v["W"], "maxDD", v["maxDD"],
              "fullDD", v["fullDD"], "Rdev4", v["Rdev4"], "Wdev4", v["Wdev4"],
              "DDdev4", v["DDdev4"], "Rlast", v["Rlast"],
              "book_win", v["book_win"], "rung_win", v["rung_win"],
              "frozen", v["frozen_frac"], "eligible", elig[row], flush=True)
    print("ELIGIBILITY (dev4 only):", elig, "PICK:", pick, flush=True)


if __name__ == "__main__":
    main()