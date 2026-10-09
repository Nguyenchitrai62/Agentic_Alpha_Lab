"""oc_cboostmanual: can the MANUAL product use the cascade boost?

Pre-registered rows (PLAN.md, frozen before any run):
  M5_human  deployed MANUAL reference (must reproduce oc_manualcap exactly)
  KM_B7     every dip bracket rung x1.5 iff its bar opens inside the 7-day
            window after a cascade bar (frozen oc_cascadedelay definition)
  KM_B3     the same with 3 days

Cascade definition (frozen, verbatim oc_cascadedelay / oc_cascadeboost):
closes-only |r| > 4*SIG(540,min120), tc = T+4h, union over 5 majors per
shift, window (tc, tc+Nd] market-wide (human acts from the NEXT bar after
the cascade close). Engine joins the FROZEN
oc_cascadeboost/boost_mult_4shift.parquet on (shift, T); exact match,
fallback to latest grid time <= T (causal ffill), missing -> 1.0.
Book orders unchanged; dip scaling via sleeve_filter (bar-open only).
Human schedule win_start=15 / sleeve_start=16, night bar skipped, agents
ON, gate costs. 4 phases, reset_metric.year_reset per anchor + v388.mix
full-path DD. CONTAMINATED like oc_cascadeboost: the idea was formed after
a replica covering all five years, so the post-release year is a LABELLED
DIAGNOSTIC, scored once, never used to choose. Select on dev4 ONLY.

  python research/tournament/oc_cboostmanual/compute_cboostmanual.py --validate
  python research/tournament/oc_cboostmanual/compute_cboostmanual.py --heavy
"""

from __future__ import annotations

import argparse
import bisect
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
CACHE = TMP / "oc_cboostmanual_runs.pkl"
BOOST_PATH = (ROOT / "research/tournament/oc_cascadeboost"
              / "boost_mult_4shift.parquet")

# ---- pre-registered constants (mirrored in tests) ----
WIN_START = 15
SLEEVE_START = 16
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
BOOST = 1.5
B7_DAYS = 7
B3_DAYS = 3
MAKER, TAKER, FUND_LONG = 0.0002, 0.00055, 0.0001  # gate costs
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
ROWS = ["M5_human", "KM_B7", "KM_B3"]
ENGINE_MODE = {"M5_human": "ref", "KM_B7": "b7", "KM_B3": "b3"}
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
# Frozen boost grid loading (no fits, no outcomes)
# --------------------------------------------------------------------------
def load_boost() -> dict:
    """Load (shift, T) -> (mult_B7, mult_B3) from the frozen parquet.

    Asserts the 4 shift grids and cross-checks boosted counts are sane.
    Read-only; never recomputed here (cboost_rule.py holds the verbatim
    arithmetic for unit tests).
    """
    df = pd.read_parquet(BOOST_PATH,
                         columns=["shift", "T", "boosted_B7", "boosted_B3",
                                  "mult_B7", "mult_B3"])
    df["T"] = pd.to_datetime(df["T"], utc=True)
    shifts = sorted(df["shift"].unique().tolist())
    assert shifts == [0, 1, 2, 3], shifts
    assert len(df) == 53877, len(df)
    grid: dict = {}
    per_shift: dict = {}
    for shift, t, b7, b3, m7, m3 in zip(df["shift"], df["T"],
                                       df["boosted_B7"], df["boosted_B3"],
                                       df["mult_B7"], df["mult_B3"]):
        s = int(shift)
        tt = pd.Timestamp(t)
        assert (m7 == BOOST) == bool(b7), (s, tt)
        assert (m3 == BOOST) == bool(b3), (s, tt)
        grid[(s, tt)] = (float(m7), float(m3))
    for s in (0, 1, 2, 3):
        sub = df[df["shift"] == s]
        per_shift[s] = dict(n=int(len(sub)), b7=int(sub["boosted_B7"].sum()),
                            b3=int(sub["boosted_B3"].sum()))
    return {"grid": grid, "per_shift": per_shift}


def parquet_year_means() -> dict:
    """Pre-registered decision means: mean mult over parquet time-bars.

    Pooled per year y over all shift grids with T in [A+sh, min(A+365d,
    live1)); rows before the first anchor or at/after live1 are never
    simulated and are excluded. No outcome data of any kind.
    """
    df = pd.read_parquet(BOOST_PATH, columns=["shift", "T", "mult_B7",
                                              "mult_B3"])
    df["T"] = pd.to_datetime(df["T"], utc=True)
    out = {}
    for y, a in enumerate(ANCH5):
        ms7, ms3, n = [], [], 0
        for s in (0, 1, 2, 3):
            sh = pd.Timedelta(hours=s)
            a0 = pd.Timestamp(a, tz="UTC") + sh
            live1 = Y1 + sh
            a1 = min(a0 + pd.Timedelta(days=365), live1)
            sub = df[(df["shift"] == s) & (df["T"] >= a0) & (df["T"] < a1)]
            ms7.extend(sub["mult_B7"].tolist())
            ms3.extend(sub["mult_B3"].tolist())
            n += len(sub)
        out[a] = dict(b7=float(np.mean(ms7)), b3=float(np.mean(ms3)),
                      n_timebars=int(n))
    return out


def build_cboost_filter(hours, night, idx, cols, shift, variant, boost):
    """sleeve_filter: 0 on the night bar else 1.5 iff boosted (bar-open).

    Boosted(T, shift) joins the frozen parquet on (shift, T = idx[i]+4h):
    exact match, else latest grid time <= T (causal ffill), else 1.0
    (counted as miss). Same mult for every coin and every rung of the bar
    (market-wide). Records per-year sized mults for the diagnostic.
    """
    grid = boost["grid"]
    by_shift: dict = {}
    for (s, t), (m7, m3) in grid.items():
        by_shift.setdefault(s, []).append(t)
    for s in by_shift:
        by_shift[s] = sorted(by_shift[s])
    sorted_ns: dict = {s: np.array([t.value for t in ts], dtype=np.int64)
                       for s, ts in by_shift.items()}
    cache: dict = {}
    misses = [0]
    sized_sum = [0.0] * 5
    sized_cnt = [0] * 5

    def lookup(t):
        key = (shift, pd.Timestamp(t))
        hit = grid.get(key)
        if hit is not None:
            return hit[0] if variant == "b7" else hit[1], True
        arr = sorted_ns.get(shift, np.array([], dtype=np.int64))
        if len(arr) == 0:
            misses[0] += 1
            return 1.0, False
        pos = bisect.bisect_right(arr.tolist(), pd.Timestamp(t).value) - 1
        if pos < 0:
            misses[0] += 1
            return 1.0, False
        tt = pd.Timestamp(arr[pos])
        hit2 = grid.get((shift, tt))
        if hit2 is None:  # pragma: no cover
            misses[0] += 1
            return 1.0, False
        return (hit2[0] if variant == "b7" else hit2[1]), True

    def filt(i, a, r):
        if hours[i] == night:
            return 0.0
        key = (i, a)
        m = cache.get(key)
        if m is None:
            t = idx[i] + pd.Timedelta(hours=4)
            m, _ = lookup(t)
            cache[key] = m
            sized_sum[anchor_of(t, shift)] += m
            sized_cnt[anchor_of(t, shift)] += 1
        return m

    filt.cache = cache
    filt.sized_sum = sized_sum
    filt.sized_cnt = sized_cnt
    filt.misses = misses
    filt.lookup = lookup
    return filt


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
            print("cboostmanual: RAM check failed (%s), retry in 300 s" % exc,
                  flush=True)
            time.sleep(300)
            continue
        if free_kb > need_kb:
            return
        print("cboostmanual: %.2f GB free, waiting for > %.0f GB"
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
    boost = load_boost()
    for s in (0, 1, 2, 3):
        d = boost["per_shift"][s]
        print("boost grid shift%d: n=%d b7=%d b3=%d"
              % (s, d["n"], d["b7"], d["b3"]), flush=True)
    ym = parquet_year_means()
    for a in ANCH5:
        print("parquet year %s: meanB7=%.6f meanB3=%.6f n_tb=%d"
              % (a, ym[a]["b7"], ym[a]["b3"], ym[a]["n_timebars"]),
              flush=True)
    return {"m5_ref": {"R5": 3.728, "W": 0.847, "maxDD": 17.94,
                       "fullDD": 17.79}}


# --------------------------------------------------------------------------
# Stage 1: 4-phase MANUAL runs (heavy)
# --------------------------------------------------------------------------
def run_phase(shift: int, boost: dict):
    wait_for_ram(2.0)
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load("pod_cbm_%d" % shift,
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load("hist_cbm_%d" % shift, ROOT / "backend/history_tm.py")
    v221 = pof._load("v221_cbm_%d" % shift,
                     pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load("fw_cbm_%d" % shift, ROOT / "scripts/forward_v205.py")
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
            filt = build_cboost_filter(
                hours, night, idx, cols, shift, mode, boost)
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
        out[row] = dict(run=run, wins=years, cross=ch, sized=sized,
                        misses=int(filt.misses[0]) if filt is not None else 0)
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


def score_all(allres, ymeans) -> dict:
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    v388 = pof._load("v388_cbm_score", RD / "v388/v388_bot_stop_distance.py")
    rm = pof._load("reset_cbm_score",
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
            parquet_mean=[round(float(ymeans[a]["b7" if row == "KM_B7" else "b3"]), 6)
                          if row != "M5_human" else 1.0 for a in ANCH5],
            sized_mean=sized_y if row != "M5_human"
            else [1.0, 1.0, 1.0, 1.0, 1.0],
        )
    return table


def robust_pick(table: dict) -> str:
    """AGENTS.md robust criterion on dev4 ONLY among eligible rows."""
    cands = [r for r in ("KM_B7", "KM_B3")
             if table[r]["DDdev4"] <= 20 and table[r]["losing_dev4"] == 0]
    if not cands:
        return "none-eligible"
    over = [r for r in cands if table[r]["Rdev4"] >= 5.0]
    pool = over if over else cands
    best = max(pool, key=lambda r: (table[r]["Wdev4"], table[r]["Rdev4"]))
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--heavy", action="store_true")
    args = ap.parse_args()
    base = validate_baselines()
    boost = load_boost()
    ymeans = parquet_year_means()
    if not args.heavy:
        print("validate-only done (no engine run). Use --heavy for the "
              "4-phase runs.", flush=True)
        return
    hb = threading.Thread(target=heartbeat, args=("oc_cboostmanual",),
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
        s, out = run_phase(shift, boost)
        allres[s] = out
        CACHE.write_bytes(pickle.dumps(allres))
        print("phase %d cached" % s, flush=True)
    _stop_hb.set()
    check_harness_identity(allres)
    table = score_all(allres, ymeans)
    pick = robust_pick(table)
    elig = {r: bool(table[r]["DDdev4"] <= 20 and table[r]["losing_dev4"] == 0)
            for r in ROWS}
    out = {
        "meta": {
            "idea": ("oc_cboostmanual: MANUAL dip brackets x1.5 for N days "
                     "after a cascade bar (> 4 sigma 4h move, frozen "
                     "oc_cascadedelay definition)"),
            "harness": ("MANUAL 4-phase (M5 pipe v367, human schedule "
                        "win_start=15 / sleeve_start=16, night bar skipped, "
                        "agents ON, gate costs maker 0.0002 / taker 0.00055 / "
                        "longs pay 0.0001 per 8h); harness copied exactly "
                        "from oc_k2manual/oc_c2manual, only the multiplier "
                        "table swapped (frozen oc_cascadeboost "
                        "boost_mult_4shift.parquet, market-wide per shift)"),
            "metric": ("reset_metric.year_reset per anchor + v388.mix "
                       "full-path DD (v421/v422 convention); KM_B7 vs KM_B3 "
                       "chosen on dev years 2021-2024 only; last year "
                       "CONTAMINATED diagnostic, scored once"),
            "rows": {
                "M5_human": "deployed reference (reproduces oc_manualcap)",
                "KM_B7": "dip rungs x1.5 inside the 7-day post-cascade window",
                "KM_B3": "dip rungs x1.5 inside the 3-day post-cascade window",
            },
            "baseline": base,
            "boost_grid": BOOST_PATH.name,
            "parquet_year_means": ymeans,
            "robust_pick_dev4": pick,
            "eligibility_dev4": elig,
            "costs": {"maker": MAKER, "taker": TAKER, "fund_long_8h": FUND_LONG},
            "caveat": ("CONTAMINATED like oc_cascadeboost: idea formed AFTER "
                       "a replica covering all five years incl. the "
                       "post-release year; select on dev4 ONLY; the "
                       "post-release year 2025-09-24 .. 2026-09-23 is a "
                       "LABELLED DIAGNOSTIC (new product variant), not clean "
                       "evidence; only prospective paper could confirm"),
        },
        "rows": table,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for row, v in table.items():
        print(row, "R5", v["R5"], "W", v["W"], "maxDD", v["maxDD"],
              "fullDD", v["fullDD"], "Rdev4", v["Rdev4"], "Wdev4", v["Wdev4"],
              "DDdev4", v["DDdev4"], "Rlast", v["Rlast"],
              "book_win", v["book_win"], "rung_win", v["rung_win"],
              "eligible", elig[row], flush=True)
    print("ROBUST PICK (dev4 only):", pick, flush=True)
    print("ELIGIBILITY (dev4 only):", elig, flush=True)


if __name__ == "__main__":
    main()
