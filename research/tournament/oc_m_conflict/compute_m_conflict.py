"""oc_m_conflict: IDEAS9 #3 book-vs-dip conflict skip on the MANUAL product.

Pre-registered rows (PLAN.md, frozen before any run):
  M5_human  deployed MANUAL reference (must reproduce oc_manualcap exactly)
  V1        skip new long dip bracket on (i,a) iff close-known book w[i,a] < 0
  V2        same skip iff w[i,a] < 0 AND |w[i,a]| > THR[coin,anchor(T)]

THR[c,A] = median |w| of coin c over fw.research_books_d2 history rows with
index < A - 7d (finite values only; < 100 values -> +inf, never skip).
Book orders untouched on every row; night skip applies FIRST on every row.
Everything else is exactly M5_human (oc_k2manual harness: pipe v367,
agents ON, win_start=15, sleeve_start=16, gate costs, trade-through fills,
no fill minutes 0..15, stop-first). 4 phases, reset_metric.year_reset per
anchor + v388.mix full-path DD. Selection on dev years 2021-2024 ONLY; the
most recent year is scored ONCE for the pick + M5_human, labelled
POST-RELEASE.

  python research/tournament/oc_m_conflict/compute_m_conflict.py --validate
  python research/tournament/oc_m_conflict/compute_m_conflict.py --heavy
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
CACHE = TMP / "oc_m_conflict_runs.pkl"

# ---- pre-registered constants (mirrored in tests) ----
WIN_START = 15
SLEEVE_START = 16
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
EMBARGO_DAYS = 7
THR_MIN_N = 100
MAKER, TAKER, FUND_LONG = 0.0002, 0.00055, 0.0001  # gate costs
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
ROWS = ["M5_human", "V1", "V2"]
ENGINE_MODE = {"M5_human": "ref", "V1": "v1", "V2": "v2"}
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
def skip_v1(w: float) -> bool:
    """V1 conflict skip: book target strictly short vs long dip."""
    return bool(np.isfinite(w) and float(w) < 0.0)


def skip_v2(w: float, thr: float) -> bool:
    """V2 strong-short skip: short AND |w| above the frozen median."""
    if not np.isfinite(float(w)) or not np.isfinite(float(thr)):
        return False
    return bool(float(w) < 0.0 and abs(float(w)) > float(thr))


def conflict_filter_value(is_night: bool, skip: bool) -> float:
    """Dip-bracket multiplier decided at the bar open (no minute/fill data)."""
    if is_night:
        return 0.0
    return 0.0 if skip else 1.0


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


def median_thr(abs_vals) -> float:
    """Frozen per-coin median |w|; too little history -> +inf (never skip)."""
    v = np.asarray(abs_vals, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) < THR_MIN_N:
        return float("inf")
    return float(np.median(v))


def compute_thr(std_books: pd.DataFrame, cols) -> dict:
    """Per-(coin, anchor) THR medians from book history only (no outcomes).

    std_books: research books before the ffill to idx (indexed by 4h bars).
    Uses rows with index < A - 7d for anchor A (EMBARGO_DAYS).
    """
    out: dict = {}
    for a in ANCH5:
        cutoff = pd.Timestamp(a, tz="UTC") - pd.Timedelta(days=EMBARGO_DAYS)
        hist = std_books[std_books.index < cutoff]
        for c in cols:
            out[(c, a)] = median_thr(np.abs(hist[c].to_numpy(dtype=float))) \
                if len(hist) else float("inf")
    return out


def build_skip_masks(books_arr: np.ndarray, idx, cols, shift: int,
                     thr: dict):
    """V1/V2 boolean skip masks (n x na), bar-open book targets only.

    books_arr[i,a] is the ffill'd close-known target used by the engine
    (oc_netting precedent); night is applied separately in the filter.
    No 1m/minute/fill data enters.
    """
    n, na = books_arr.shape
    v1 = np.zeros((n, na), dtype=bool)
    v2 = np.zeros((n, na), dtype=bool)
    for i in range(n):
        t = idx[i] + pd.Timedelta(hours=4)
        akey = ANCH5[anchor_of(t, shift)]
        for j in range(na):
            w = float(books_arr[i, j])
            s1 = skip_v1(w)
            v1[i, j] = s1
            v2[i, j] = bool(s1 and skip_v2(w, thr[(cols[j], akey)]))
    return v1, v2


def build_conflict_filter(hours, night, skip_arr):
    """sleeve_filter: 0 on night bar or conflict skip, else 1 (bar-open)."""
    def filt(i, a, r):
        if hours[i] == night:
            return 0.0
        if bool(skip_arr[i, a]):
            return 0.0
        return 1.0
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
            print("m_conflict: RAM check failed (%s), retry in 300 s" % exc,
                  flush=True)
            time.sleep(300)
            continue
        if free_kb > need_kb:
            return
        print("m_conflict: %.2f GB free, waiting for > %.0f GB"
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
    assert EMBARGO_DAYS == 7 and THR_MIN_N == 100
    print("conflict rule frozen: V1 w<0; V2 w<0 and |w|>per-coin "
          "pre-anchor median (7d embargo)", flush=True)
    return {"m5_ref": {"R5": 3.728, "W": 0.847, "maxDD": 17.94,
                       "fullDD": 17.79}}


# --------------------------------------------------------------------------
# Stage 1: 4-phase MANUAL runs (heavy)
# --------------------------------------------------------------------------
def run_phase(shift: int):
    wait_for_ram(2.0)
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load("pod_mcf_%d" % shift,
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load("hist_mcf_%d" % shift, ROOT / "backend/history_tm.py")
    v221 = pof._load("v221_mcf_%d" % shift,
                     pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load("fw_mcf_%d" % shift, ROOT / "scripts/forward_v205.py")
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
    thr = compute_thr(std_books, cols)
    books_arr = books.to_numpy(dtype=float)
    v1mask, v2mask = build_skip_masks(books_arr, idx, cols, shift, thr)
    masks = {"v1": v1mask, "v2": v2mask}
    n = len(idx)
    print("shift %d: THR medians BTC %s" %
          (shift, [round(float(thr[('BTCUSDT', a)]), 6) for a in ANCH5]),
          flush=True)
    print("shift %d: skip coin-bar rate V1 %.4f V2 %.4f (n=%d)" %
          (shift, float(v1mask.mean()), float(v2mask.mean()), n), flush=True)
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
        if mode == "ref":
            kw["sleeve_filter"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0
        else:
            kw["sleeve_filter"] = build_conflict_filter(
                hours, night, masks[mode])
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
        if mode == "ref":
            sr = [0.0] * 5
        else:
            sm = masks[mode]
            sr = []
            for y, a in enumerate(ANCH5):
                a0 = pd.Timestamp(a, tz="UTC") + sh
                a1 = min(a0 + pd.Timedelta(days=365), live1)
                msk = (idx >= a0 - pd.Timedelta(hours=4)) & \
                      (idx < a1 - pd.Timedelta(hours=4))
                msk = np.asarray(msk)
                sr.append(round(float(sm[msk].mean()) if msk.sum() else 0.0, 6))
        out[row] = dict(run=run, wins=years, cross=ch, skip_rate=sr)
        print(shift, row, [round(100 * v["net"], 1) for v in ch],
              [v["dd"] for v in ch], "skip=%s" % (sr,), flush=True)
        del events
        gc.collect()
    thr_json = {c: {a: (None if not np.isfinite(thr[(c, a)])
                        else round(float(thr[(c, a)]), 6))
                    for a in ANCH5} for c in cols}
    out["_thr"] = thr_json
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
    v388 = pof._load("v388_mcf_score", RD / "v388/v388_bot_stop_distance.py")
    rm = pof._load("reset_mcf_score",
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
        sr_y = []
        for y in range(5):
            vals = [allres[s][row]["skip_rate"][y] for s in range(4)]
            sr_y.append(round(float(np.mean(vals)), 6))
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
            skip_rate=sr_y,
        )
    return table


def robust_pick(table: dict) -> str:
    """AGENTS.md robust criterion on dev4 ONLY: eligible = DD<=20, no losing
    year; prefer dev4 mean >= 5; then highest dev4 WORST; ties -> higher mean."""
    cand = [r for r in ("V1", "V2")
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
    hb = threading.Thread(target=heartbeat, args=("oc_m_conflict",),
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
    thr_all = {str(s): allres[s].get("_thr") for s in range(4)}
    out = {
        "meta": {
            "idea": "oc_m_conflict: IDEAS9 #3 book-vs-dip conflict skip (MANUAL)",
            "harness": ("MANUAL 4-phase (M5 pipe v367, human schedule "
                        "win_start=15 / sleeve_start=16, night bar skipped, "
                        "agents ON, gate costs maker 0.0002 / taker 0.00055 / "
                        "longs pay 0.0001 per 8h); harness copied exactly "
                        "from oc_k2manual, only the dip gate changed"),
            "metric": ("reset_metric.year_reset per anchor + v388.mix "
                       "full-path DD (v421/v422 convention); V1 vs V2 judged "
                       "on dev years 2021-2024 only; last year POST-RELEASE, "
                       "scored once for the pick + M5_human"),
            "rows": {
                "M5_human": "deployed reference (reproduces oc_manualcap)",
                "V1": "skip new long dip iff close-known book w < 0",
                "V2": "skip iff w < 0 and |w| > per-coin pre-anchor "
                      "median |w| (7d embargo)",
            },
            "baseline": base,
            "thr": thr_all,
            "eligibility_dev4": elig,
            "pick_dev4": pick,
            "costs": {"maker": MAKER, "taker": TAKER, "fund_long_8h": FUND_LONG},
            "caveat": ("THR medians from book weights only (no outcomes), "
                       "rows ending before anchor minus 7d; anchor A THR "
                       "applies to year [A, A+365d); most recent year is "
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
              "skip", v["skip_rate"], "eligible", elig[row], flush=True)
    print("ELIGIBILITY (dev4 only):", elig, "PICK:", pick, flush=True)


if __name__ == "__main__":
    main()
