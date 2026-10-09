"""oc_c2manual: can the MANUAL product use the Chronos C2 multiplier?

Pre-registered rows (PLAN.md, frozen before any run):
  M5_human  deployed MANUAL reference (must reproduce oc_manualcap exactly)
  KM_C2     every dip bracket rung x C2 multiplier (1.25 / 0.75 / 1.0 from
            Chronos ch_q10 with per-anchor oc_chronos fits.json)
  CTRL      every dip bracket rung x C_y, constant per year = KM_C2's
            feature-table decision mean in year y (exposure control)
  KM_K2     COPIED from oc_k2manual/results.json (same harness, context only)

C2 mult for (coin c, bar open T, clock shift s): risk = -ch_q10 at
(sym = c, shift = s, T) from oc_chronos/chronos_features_4shift.parquet;
fits of anchor A = oc_chronos fits.json (direction d_A, edges q20_A/q80_A);
d_A > 0: risk >= q80 -> 1.25, risk <= q20 -> 0.75, else 1.0; missing/non-finite
ch_q10 -> 1.0. Fits of anchor A apply to year [A, A+365d) on all shifts.
Book orders unchanged; dip scaling via sleeve_filter (bar-open only).
Human schedule win_start=15 / sleeve_start=16, night bar skipped, agents
ON, gate costs. 4 phases, reset_metric.year_reset per anchor + v388.mix
full-path DD. Dev years are possibly inside Chronos pretraining (UPPER
BOUND); the most recent year is POST-HOC context, scored once, never used
to choose.

  python research/tournament/oc_c2manual/compute_c2manual.py --validate
  python research/tournament/oc_c2manual/compute_c2manual.py --heavy
"""

from __future__ import annotations

import argparse
import gc
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
CACHE = TMP / "oc_c2manual_runs.pkl"
CHRONOS_PATH = (ROOT / "research/tournament/oc_chronos"
                / "chronos_features_4shift.parquet")
FITS_PATH = ROOT / "research/tournament/oc_chronos/fits.json"
K2MANUAL_RESULTS = ROOT / "research/tournament/oc_k2manual/results.json"

# ---- pre-registered constants (mirrored in tests) ----
WIN_START = 15
SLEEVE_START = 16
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
C2_HI = 1.25
C2_LO = 0.75
MAKER, TAKER, FUND_LONG = 0.0002, 0.00055, 0.0001  # gate costs
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
ROWS = ["M5_human", "KM_C2", "CTRL"]
ENGINE_MODE = {"M5_human": "ref", "KM_C2": "c2", "CTRL": "ctrl"}
HEARTBEAT_S = 600

_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print("[hb %sZ] %s alive"
              % (datetime.now(timezone.utc).strftime("%H:%M:%S"), tag),
              flush=True)


# --------------------------------------------------------------------------
# Pure helpers (unit-tested; no data access)
# --------------------------------------------------------------------------
def assign_mult(risk: float, direction: int, q20: float, q80: float,
                hi: float = C2_HI, lo: float = C2_LO) -> float:
    """C2 multiplier for one (coin, holding bar); NaN risk -> 1.0."""
    r = float(risk)
    if not np.isfinite(r):
        return 1.0
    if direction > 0:  # high risk favourable
        if r >= float(q80):
            return float(hi)
        if r <= float(q20):
            return float(lo)
        return 1.0
    if r >= float(q80):  # high risk unfavourable (not hit with these fits)
        return float(lo)
    if r <= float(q20):
        return float(hi)
    return 1.0


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


# --------------------------------------------------------------------------
# Chronos C2 loading + per-year CTRL decision means (fits only, no outcomes)
# --------------------------------------------------------------------------
def load_chronos() -> dict:
    """Load (sym, shift, T) -> ch_q10. Asserts all 20 (shift, sym) groups."""
    df = pd.read_parquet(CHRONOS_PATH, columns=["sym", "shift", "T", "ch_q10"])
    groups = df.groupby(["shift", "sym"]).size()
    assert len(groups) == 20, "chronos groups %d != 20" % len(groups)
    assert set(df["sym"].unique()) == set(MAJORS), df["sym"].unique()
    out: dict = {}
    for sym, shift, t, q in zip(df["sym"], df["shift"],
                                df["T"], df["ch_q10"]):
        out[(str(sym), int(shift), pd.Timestamp(t))] = float(q)
    return out


def load_fits() -> dict:
    """Frozen per-anchor fits of oc_chronos (direction + q20/q80)."""
    fits = json.loads(FITS_PATH.read_text())
    assert set(fits) == set(ANCH5), sorted(fits)
    for a, f in fits.items():
        assert f["direction"] == 1, (a, f)
        assert np.isfinite(f["q20"]) and np.isfinite(f["q80"]), (a, f)
        assert f["q20"] < f["q80"], (a, f)
    return fits


def c2_mult_for(coin: str, t: pd.Timestamp, shift: int,
                chronos: dict, fits: dict) -> float:
    """Final C2 bar-open multiplier for one (coin, bar, shift)."""
    a = ANCH5[anchor_of(t, shift)]
    f = fits[a]
    q = chronos.get((coin, shift, pd.Timestamp(t)))
    risk = -float(q) if q is not None and np.isfinite(float(q)) \
        else float("nan")
    return assign_mult(risk, f["direction"], f["q20"], f["q80"],
                       C2_HI, C2_LO)


def year_of_feature(t: pd.Timestamp, shift: int) -> int | None:
    """Year window 0..4 of a feature row T on clock shift, or None outside.

    Year y covers [a0, min(a0+365d, live1)) with a0 = ANCH5[y]+sh. Rows
    before the first anchor or at/after live1 are never simulated, so they
    are excluded from the CTRL decision means (oc_kronoshidden precedent:
    exactly one year of rows per y). The engine's anchor_of fallback (0 /
    4) never triggers for simulated bars.
    """
    sh = pd.Timedelta(hours=shift)
    live1 = Y1 + sh
    tt = pd.Timestamp(t)
    if tt.tzinfo is None:
        tt = tt.tz_localize("UTC")
    for y, a in enumerate(ANCH5):
        a0 = pd.Timestamp(a, tz="UTC") + sh
        a1 = min(a0 + pd.Timedelta(days=365), live1)
        if a0 <= tt < a1:
            return y
    return None


def decision_means(chronos: dict, fits: dict) -> dict:
    """Per-year CTRL constants C_y: decision mean of the C2 rule.

    Pooled over all (coin, shift, T) feature rows with year_of_feature(T,
    shift) == y; fits of anchor A applied to year A; missing -> 1.0
    exactly as the engine does. Rows outside every year window (never
    simulated) are excluded. No outcome data of any kind.
    """
    sums = [0.0] * 5
    cnts = [0] * 5
    coins = {k[0] for k in chronos}
    assert coins == set(MAJORS), sorted(coins)
    for (sym, shift, t), q in chronos.items():
        y = year_of_feature(t, shift)
        if y is None:
            continue
        f = fits[ANCH5[y]]
        risk = -float(q) if np.isfinite(float(q)) else float("nan")
        m = assign_mult(risk, f["direction"], f["q20"], f["q80"],
                        C2_HI, C2_LO)
        sums[y] += m
        cnts[y] += 1
    out = {}
    for y, a in enumerate(ANCH5):
        assert cnts[y] > 0, (y, a)
        out[a] = dict(c=float(sums[y] / cnts[y]), n_train=int(cnts[y]))
    return out


def build_c2_filter(hours, night, idx, cols, shift, variant, chronos,
                    fits, ctrl):
    """sleeve_filter: 0 on the night bar else the C2/CTRL mult (bar-open).

    Mult depends only on (coin, holding-bar T, shift) via the frozen
    feature table and pre-anchor fits (CTRL: frozen per-year constants);
    never on minute or fill data. Records per-year decision mults for the
    sized-mean diagnostic.
    """
    cache: dict = {}
    sized_sum = [0.0] * 5
    sized_cnt = [0] * 5

    def filt(i, a, r):
        if hours[i] == night:
            return 0.0
        key = (i, a)
        m = cache.get(key)
        if m is None:
            t = idx[i] + pd.Timedelta(hours=4)
            if variant == "c2":
                m = c2_mult_for(cols[a], t, shift, chronos, fits)
            elif variant == "ctrl":
                m = float(ctrl[ANCH5[anchor_of(t, shift)]]["c"])
            else:
                raise ValueError(variant)  # pragma: no cover
            cache[key] = m
            sized_sum[anchor_of(t, shift)] += m
            sized_cnt[anchor_of(t, shift)] += 1
        return m

    filt.cache = cache
    filt.sized_sum = sized_sum
    filt.sized_cnt = sized_cnt
    return filt


def _load(name: str, path: Path):
    spec = __import__("importlib.util", fromlist=["util"]).spec_from_file_location(
        name, path)
    mod = __import__("importlib.util", fromlist=["module_from_spec"]).module_from_spec(
        spec)
    spec.loader.exec_module(mod)
    return mod


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
            print("c2manual: RAM check failed (%s), retry in 300 s" % exc,
                  flush=True)
            time.sleep(300)
            continue
        if free_kb > need_kb:
            return
        print("c2manual: %.2f GB free, waiting for > %.0f GB"
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
    df = pd.read_parquet(CHRONOS_PATH, columns=["sym", "shift"])
    groups = df.groupby(["shift", "sym"]).size()
    assert len(groups) == 20, "chronos groups %d != 20" % len(groups)
    assert set(df["sym"].unique()) == set(MAJORS), df["sym"].unique()
    print("chronos 4shift OK: 20 (shift, sym) groups, syms %s"
          % sorted(df["sym"].unique()), flush=True)
    fits = load_fits()
    for a in ANCH5:
        f = fits[a]
        print("fit %s: dir=%d q20=%.4f q80=%.4f"
              % (a, f["direction"], f["q20"], f["q80"]), flush=True)
    return {"m5_ref": {"R5": 3.728, "W": 0.847, "maxDD": 17.94,
                       "fullDD": 17.79}}


# --------------------------------------------------------------------------
# Stage 1: 4-phase MANUAL runs (heavy)
# --------------------------------------------------------------------------
def run_phase(shift: int, chronos: dict, fits: dict, ctrl: dict):
    wait_for_ram(2.0)
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load("pod_c2m_%d" % shift,
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load("hist_c2m_%d" % shift, ROOT / "backend/history_tm.py")
    v221 = pof._load("v221_c2m_%d" % shift,
                     pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load("fw_c2m_%d" % shift, ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
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
        filt = None
        if mode == "ref":
            kw["sleeve_filter"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0
        else:
            filt = build_c2_filter(
                hours, night, idx, cols, shift, mode, chronos, fits, ctrl)
            kw["sleeve_filter"] = filt
        events: list = []
        stats_hold.clear()
        eu.simulate(books, opens, prep, trade=trade, win_start=WIN_START,
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
        sized = None
        if filt is not None:
            sized = [round(float(filt.sized_sum[y]) / filt.sized_cnt[y], 6)
                     if filt.sized_cnt[y] else None for y in range(5)]
        out[row] = dict(run=run, wins=years, cross=ch, sized=sized)
        print(shift, row, [round(100 * v["net"], 1) for v in ch],
              [v["dd"] for v in ch], "sized=%s" % (sized,), flush=True)
        del events
        gc.collect()
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


def score_all(allres, ctrl) -> dict:
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    v388 = pof._load("v388_c2m_score", RD / "v388/v388_bot_stop_distance.py")
    rm = pof._load("reset_c2m_score",
                   ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
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
        sized_y = []
        for y in range(5):
            vals = [allres[s][row]["sized"][y] for s in range(4)
                    if allres[s][row]["sized"] is not None
                    and allres[s][row]["sized"][y] is not None]
            sized_y.append(round(float(np.mean(vals)), 6) if vals else None)
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
            decision_mean=[round(float(ctrl[a]["c"]), 6) if row != "M5_human"
                           else 1.0 for a in ANCH5],
            sized_mean=sized_y if row != "M5_human"
            else [1.0, 1.0, 1.0, 1.0, 1.0],
        )
    return table


def eligibility(table: dict) -> dict:
    """Eligibility of the single candidate KM_C2 on dev4 only (no choice)."""
    out = {}
    for row in ("KM_C2", "CTRL", "M5_human"):
        t = table[row]
        out[row] = bool(t["DDdev4"] <= 20 and t["losing_dev4"] == 0)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--heavy", action="store_true")
    args = ap.parse_args()
    base = validate_baselines()
    chronos = load_chronos()
    fits = load_fits()
    ctrl = decision_means(chronos, fits)
    for a in ANCH5:
        print("CTRL %s: C=%.6f n=%d"
              % (a, ctrl[a]["c"], ctrl[a]["n_train"]), flush=True)
    if not args.heavy:
        print("validate-only done (no engine run). Use --heavy for the "
              "4-phase runs.", flush=True)
        return
    hb = threading.Thread(target=heartbeat, args=("oc_c2manual",),
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
        s, out = run_phase(shift, chronos, fits, ctrl)
        allres[s] = out
        CACHE.write_bytes(pickle.dumps(allres))
        print("phase %d cached" % s, flush=True)
    _stop_hb.set()
    check_harness_identity(allres)
    table = score_all(allres, ctrl)
    # KM_K2 copied from oc_k2manual (same harness, context for C2-vs-K2)
    k2src = json.loads(K2MANUAL_RESULTS.read_text())["rows"]["KM_K2"]
    table["KM_K2_copied"] = dict(k2src, copied_from="oc_k2manual")
    elig = eligibility(table)
    elig["KM_K2_copied"] = bool(
        table["KM_K2_copied"]["DDdev4"] <= 20
        and table["KM_K2_copied"]["losing_dev4"] == 0)
    out = {
        "meta": {
            "idea": "oc_c2manual: MANUAL dip brackets x Chronos C2 multiplier",
            "harness": ("MANUAL 4-phase (M5 pipe v367, human schedule "
                        "win_start=15 / sleeve_start=16, night bar skipped, "
                        "agents ON, gate costs maker 0.0002 / taker 0.00055 / "
                        "longs pay 0.0001 per 8h); harness copied exactly "
                        "from oc_k2manual, only the multiplier table swapped "
                        "(Kronos low1 -> Chronos ch_q10)"),
            "metric": ("reset_metric.year_reset per anchor + v388.mix "
                       "full-path DD (v421/v422 convention); single "
                       "candidate KM_C2 judged on dev years 2021-2024 only; "
                       "last year POST-HOC, scored once; KM_K2 copied from "
                       "oc_k2manual for context"),
            "rows": {
                "M5_human": "deployed reference (reproduces oc_manualcap)",
                "KM_C2": "dip rungs x C2 (1.25 / 0.75 / 1.0 from -ch_q10, "
                         "per-anchor oc_chronos fits.json)",
                "CTRL": "dip rungs x C_y constant (KM_C2 decision mean)",
                "KM_K2_copied": "copied from oc_k2manual/results.json "
                                "(same harness, Kronos K2 tilt)",
            },
            "baseline": base,
            "fits": {a: dict(direction=fits[a]["direction"],
                              q20=fits[a]["q20"], q80=fits[a]["q80"])
                     for a in ANCH5},
            "ctrl": ctrl,
            "eligibility_dev4": elig,
            "costs": {"maker": MAKER, "taker": TAKER, "fund_long_8h": FUND_LONG},
            "caveat": ("Chronos-Bolt released 2024-11 (mostly public "
                       "non-crypto + synthetic): dev years "
                       "possibly-contaminated -> dev = UPPER BOUND; most "
                       "recent year (after both Chronos and Kronos releases) "
                       "is the clean test (new product variant)"),
        },
        "rows": table,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for row, v in table.items():
        print(row, "R5", v["R5"], "W", v["W"], "maxDD", v["maxDD"],
              "fullDD", v["fullDD"], "Rdev4", v["Rdev4"], "Wdev4", v["Wdev4"],
              "DDdev4", v["DDdev4"], "Rlast", v["Rlast"],
              "book_win", v["book_win"], "rung_win", v["rung_win"],
              "eligible", elig.get(row), flush=True)
    print("ELIGIBILITY (dev4 only):", elig, flush=True)


if __name__ == "__main__":
    main()
