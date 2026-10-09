"""oc_m_top2: IDEAS9 #4 max-2 bracket priority (attention cap) on MANUAL.

Pre-registered rows (PLAN.md, frozen before any run):
  M5_human  deployed MANUAL reference (must reproduce oc_manualcap exactly)
  V1_TOP2   new book+dip brackets ONLY on the top-2 coins by |w| each bar
  V2_TOP3   new book+dip brackets ONLY on the top-3 coins by |w| each bar

Rank key w[i,a] = close-known ffill'd research book at idx[i] (same w as
oc_m_conflict); ties -> canonical MAJORS order (BTC>ETH>SOL>BNB>XRP);
K = 2 / 3 frozen integers; no intraday re-rank (kept set cached per bar).
Skipped coin: book wait-if-flat / hold-if-in-position (night-skip semantic,
resting SL/TP stay) + sleeve_filter 0.0. Kept coins: unchanged M5_human
(all depths/SL/TP, size x1.0, no rescale). Night skip applies FIRST.
Everything else is exactly M5_human (oc_m_btceth harness: pipe v367,
agents ON, win_start=15, sleeve_start=16, gate costs, trade-through fills,
no fill minutes 0..15, stop-first). 4 phases, reset_metric.year_reset per
anchor + v388.mix full-path DD. V1 vs V2 judged on dev years 2021-2024
ONLY; the most recent year is scored ONCE for the pick + M5_human,
labelled POST-RELEASE.

  python research/tournament/oc_m_top2/compute_m_top2.py --validate
  python research/tournament/oc_m_top2/compute_m_top2.py --heavy
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
CACHE = TMP / "oc_m_top2_runs.pkl"

# ---- pre-registered constants (mirrored in tests) ----
WIN_START = 15
SLEEVE_START = 16
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ROW_K = {"V1_TOP2": 2, "V2_TOP3": 3}
MAKER, TAKER, FUND_LONG = 0.0002, 0.00055, 0.0001  # gate costs
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
ROWS = ["M5_human", "V1_TOP2", "V2_TOP3"]
ENGINE_MODE = {"M5_human": "ref", "V1_TOP2": "v1", "V2_TOP3": "v2"}
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
def _abs_w(x: float) -> float:
    v = float(x)
    if not np.isfinite(v):
        return 0.0
    return abs(v)


def topk_kept(wrow, cols, k: int) -> frozenset:
    """Kept coin indices: top-k by |w|, ties -> canonical MAJORS order.

    wrow: close-known book weights for one bar (index-aligned with cols).
    Pure function of the decision-bar row; no minute/fill/outcome data.
    """
    order = sorted(range(len(cols)),
                   key=lambda a: (-_abs_w(wrow[a]),
                                  MAJORS.index(str(cols[a]))))
    return frozenset(order[: int(k)])


def coin_filter_value(coin_idx: int, kept: frozenset, is_night: bool) -> float:
    """Dip-bracket multiplier decided at the bar open (no minute/fill data)."""
    if is_night:
        return 0.0
    return 1.0 if coin_idx in kept else 0.0


def book_action_for_skipped(pos: int, is_night: bool, is_kept: bool):
    """Book action override for night / skipped coins; None = base policy.

    Night applies first (identical both legs): flat -> wait, in position ->
    hold. Skipped coin: same wait/hold so no new order is placed (resting
    SL/TP stay; runs start flat so a skipped coin stays flat).
    """
    if is_night or not is_kept:
        return "wait" if pos == 0 else "hold"
    return None


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
            print("m_top2: RAM check failed (%s), retry in 300 s" % exc,
                  flush=True)
            time.sleep(300)
            continue
        if free_kb > need_kb:
            return
        print("m_top2: %.2f GB free, waiting for > %.0f GB"
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
    assert ROW_K == {"V1_TOP2": 2, "V2_TOP3": 3}, ROW_K
    assert all(0 < k < len(MAJORS) for k in ROW_K.values()), ROW_K
    print("K frozen: V1_TOP2 K=2, V2_TOP3 K=3 (no rescale, kept x1.0)",
          flush=True)
    return {"m5_ref": {"R5": 3.728, "W": 0.847, "maxDD": 17.94,
                       "fullDD": 17.79}}


# --------------------------------------------------------------------------
# Stage 1: 4-phase MANUAL runs (heavy)
# --------------------------------------------------------------------------
def run_phase(shift: int):
    wait_for_ram(2.0)
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load("pod_mt2_%d" % shift,
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load("hist_mt2_%d" % shift, ROOT / "backend/history_tm.py")
    v221 = pof._load("v221_mt2_%d" % shift,
                     pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load("fw_mt2_%d" % shift, ROOT / "scripts/forward_v205.py")
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
    wmat = books.to_numpy(dtype=float)
    bar_year = np.asarray(
        [anchor_of(t, shift) for t in (idx + pd.Timedelta(hours=4))],
        dtype=int)
    out = {}
    for row in ROWS:
        mode = ENGINE_MODE[row]
        kw, trade = pof.pipe_setup("v367", hist, v221, v216, idx, cols, True)
        kept_cache: dict = {}

        def _kept(i, _k=ROW_K.get(row, 5)):
            kset = kept_cache.get(i)
            if kset is None:
                kset = topk_kept(wmat[i], cols, _k)
                kept_cache[i] = kset
            return kset

        if mode == "ref":
            pol = trade["policy"]
            trade["policy"] = lambda i, a, st, pol=pol: (
                ("wait" if st["pos"] == 0 else "hold")
                if hours[i] == night else pol(i, a, st))
            kw["sleeve_start"] = SLEEVE_START
            kw["sleeve_filter"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0
        else:
            base_pol = trade["policy"]

            def _pol(i, a, st, base_pol=base_pol, _kept=_kept):
                ov = book_action_for_skipped(
                    int(st["pos"]), bool(hours[i] == night),
                    bool(a in _kept(i)))
                if ov is not None:
                    return ov
                return base_pol(i, a, st)

            trade["policy"] = _pol
            kw["sleeve_start"] = SLEEVE_START

            def _filt(i, a, r, _kept=_kept):
                return coin_filter_value(a, _kept(i), hours[i] == night)

            kw["sleeve_filter"] = _filt
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
        gate = None
        if mode != "ref":
            gate = _phase_gate_stats(
                wmat, cols, hours, night, bar_year, ROW_K[row])
        out[row] = dict(run=run, wins=years, cross=ch, gate=gate)
        print(shift, row, [round(100 * v["net"], 1) for v in ch],
              [v["dd"] for v in ch],
              ("gate=%s" % (gate["skip_frac"],) if gate else ""), flush=True)
        del events
        gc.collect()
    del opens, prep, books
    gc.collect()
    return shift, out


def _phase_gate_stats(wmat: np.ndarray, cols, hours: np.ndarray,
                      night: int, bar_year: np.ndarray, k: int) -> dict:
    """Per-year top-K gate stats on non-night bars (book data only).

    skip_frac[y]: share of (bar, coin) slots skipped by the cap in year y.
    kept_abs_w / skip_abs_w: mean |w| of kept vs skipped coins (conviction
    separation). No outcome data of any kind.
    """
    skip_frac, kept_w, skip_w, nbars = [], [], [], []
    for y in range(5):
        sel = (bar_year == y) & (hours != night)
        ii = np.nonzero(sel)[0]
        nbars.append(int(len(ii)))
        if len(ii) == 0:
            skip_frac.append(0.0)
            kept_w.append(0.0)
            skip_w.append(0.0)
            continue
        ks, ss, kn, sn = 0.0, 0.0, 0, 0
        sk_slots = 0
        for i in ii:
            kept = topk_kept(wmat[i], cols, k)
            for a in range(len(cols)):
                v = _abs_w(wmat[i, a])
                if a in kept:
                    ks += v
                    kn += 1
                else:
                    ss += v
                    sn += 1
                    sk_slots += 1
        tot = kn + sn
        skip_frac.append(round(sk_slots / tot, 4) if tot else 0.0)
        kept_w.append(round(ks / kn, 6) if kn else 0.0)
        skip_w.append(round(ss / sn, 6) if sn else 0.0)
    return {"K": int(k), "n_bars": nbars, "skip_frac": skip_frac,
            "kept_abs_w": kept_w, "skip_abs_w": skip_w}


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
    v388 = pof._load("v388_mt2_score", RD / "v388/v388_bot_stop_distance.py")
    rm = pof._load("reset_mt2_score",
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
        gate_y = None
        if allres[0][row].get("gate") is not None:
            gate_y = []
            for y in range(5):
                sf = [allres[s][row]["gate"]["skip_frac"][y] for s in range(4)]
                kw_ = [allres[s][row]["gate"]["kept_abs_w"][y] for s in range(4)]
                sw_ = [allres[s][row]["gate"]["skip_abs_w"][y] for s in range(4)]
                gate_y.append(dict(skip_frac=round(float(np.mean(sf)), 4),
                                   kept_abs_w=round(float(np.mean(kw_)), 6),
                                   skip_abs_w=round(float(np.mean(sw_)), 6)))
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
            K=(ROW_K.get(row, 5)),
            gate_years=gate_y,
        )
    return table


def robust_pick(table: dict) -> str:
    """AGENTS.md robust criterion on dev4 ONLY: eligible = DD<=20, no losing
    year; prefer dev4 mean >= 5; then highest dev4 WORST; ties -> higher mean."""
    cand = [r for r in ("V1_TOP2", "V2_TOP3")
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
    hb = threading.Thread(target=heartbeat, args=("oc_m_top2",),
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
    out = {
        "meta": {
            "idea": "oc_m_top2: IDEAS9 #4 max-2 bracket priority (MANUAL)",
            "harness": ("MANUAL 4-phase (M5 pipe v367, human schedule "
                        "win_start=15 / sleeve_start=16, night bar skipped, "
                        "agents ON, gate costs maker 0.0002 / taker 0.00055 / "
                        "longs pay 0.0001 per 8h); harness copied exactly "
                        "from oc_m_btceth, only the per-bar coin gate changed "
                        "(frozen allow-list -> top-K by close-known |w|)"),
            "metric": ("reset_metric.year_reset per anchor + v388.mix "
                       "full-path DD (v421/v422 convention); V1 vs V2 judged "
                       "on dev years 2021-2024 only; last year POST-RELEASE, "
                       "scored once for the pick + M5_human"),
            "rows": {
                "M5_human": "deployed reference (reproduces oc_manualcap)",
                "V1_TOP2": "book+dip brackets ONLY on top-2 by |w|, others "
                           "wait/hold + no dip (kept x1.0, no rescale)",
                "V2_TOP3": "book+dip brackets ONLY on top-3 by |w|, others "
                           "wait/hold + no dip (kept x1.0, no rescale)",
            },
            "baseline": base,
            "K": dict(ROW_K),
            "eligibility_dev4": elig,
            "pick_dev4": pick,
            "costs": {"maker": MAKER, "taker": TAKER, "fund_long_8h": FUND_LONG},
            "caveat": ("Rank key is close-known book |w| only (no fit, no "
                       "per-year pick); dev years are research data; most "
                       "recent year is POST-RELEASE context, scored once, "
                       "never used to choose"),
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
    print("ELIGIBILITY (dev4 only):", elig, "PICK:", pick, flush=True)


if __name__ == "__main__":
    main()
