"""oc_idea5_manualrest: MANUAL 4h-rest brackets (IDEAS_20261007 section 5).

Pre-registered rows (REPORT.md section 0, frozen before any run):
  M5_human      deployed MANUAL reference (must reproduce oc_manualcap exactly)
  B0_60min      M5_human with book ENTRY orders expiring 60 min after placement
                (fill minutes 15..74 of the issuing bar; comparator, not a pick)
  H1_rest4h     M5_human with book ENTRY orders resting to the next 4h close
                (fill minutes 15..239 of the issuing bar only; base size)
  H2_rest4h_x2dip  H1 with dip size_mult x2.0 (4.375 -> 8.75; budget stays 0.26)

Harness = oc_manualcap copy (M5 pipe v367, human schedule win_start=15 /
sleeve_start=16, night bar skipped, agents ON, gate costs), 4 phases,
reset_metric.year_reset per anchor + v388.mix full-path DD (v421/v422).

  python research/tournament/oc_idea5_manualrest/compute_manualrest.py --validate
  python research/tournament/oc_idea5_manualrest/compute_manualrest.py --heavy
"""

from __future__ import annotations

import argparse
import gc
import inspect
import json
import pickle
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"
TMP = HERE / "tmp"
CACHE = TMP / "oc_idea5_manualrest_runs.pkl"

# ---- pre-registered constants (mirrored in tests) ----
WIN_START = 15          # human book reaction (minute-5 user rule kept, stricter)
SLEEVE_START = 16       # human dip reaction
B0_END = 75             # B0: entry fill window is minutes 15..74 (60-min expiry)
H1_END = 240            # H1/H2: entry rests to the next 4h close (minutes 15..239)
H2_SIZE_MULT = 8.75     # H2: dip size_mult x2.0 vs M5 base 4.375
BASE_SIZE_MULT = 4.375
RISK_BUDGET = 0.26      # unchanged on every row (incl. H2)
MAKER, TAKER, FUND_LONG = 0.0002, 0.00055, 0.0001  # gate costs
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
VOL_CAP = 2.0
ROWS = ["M5_human", "B0_60min", "H1_rest4h", "H2_rest4h_x2dip"]
ENGINE_MODE = {"M5_human": "ref", "B0_60min": "b0",
               "H1_rest4h": "h1", "H2_rest4h_x2dip": "h1"}
SIZE_MULT = {"M5_human": None, "B0_60min": None,
             "H1_rest4h": None, "H2_rest4h_x2dip": H2_SIZE_MULT}

# ---- engine source patches (entry orders only; SL/TP/scale orders untouched) ----
OLD_EXP = 'T["exp"][a], T["psd"][a], T["issued"][a] = i + P.get("n_valid", 2), sd_a, i'
NEW_EXP_H1 = 'T["exp"][a], T["psd"][a], T["issued"][a] = i + 1, sd_a, i'
OLD_HIT = ('            px = T["px"][a]\n'
           '            hit = La[start:240] < px * (1 - ft) if ps > 0 else Ha[start:240] > px * (1 + ft)\n'
           '            if not hit.any():\n'
           '                return carr, qarr, 0.0, np.nan\n')
NEW_HIT_B0 = ('            px = T["px"][a]\n'
              '            _cut = 75 if T["issued"][a] == i else 240\n'
              '            hit = La[start:_cut] < px * (1 - ft) if ps > 0 else Ha[start:_cut] > px * (1 + ft)\n'
              '            if not hit.any():\n'
              '                if T["issued"][a] == i and _cut < 240:\n'
              '                    stats["expired"] += 1\n'
              '                    _ev(i, a, _cut, "order_expire", "buy" if T["side"][a] > 0 else "sell", T["px"][a], 0.0)\n'
              '                    T["side"][a] = 0\n'
              '                    T["risk"][a] = 0.0\n'
              '                return carr, qarr, 0.0, np.nan\n')


def entry_fill_end(mode: str, issued_this_bar: bool) -> int:
    """Last+1 fill minute for a flat-branch book entry order (pure helper)."""
    if mode == "b0" and issued_this_bar:
        return B0_END
    return H1_END


def entry_exp_bar(mode: str, issue_i: int, n_valid: int = 3) -> int:
    """First bar index at which a book entry order expires (pure helper)."""
    if mode in ("b0", "h1"):
        return issue_i + 1  # single-bar validity (B0 expires intra-bar first)
    return issue_i + n_valid


def make_simulate(eu, mode: str):
    """eu.simulate with the entry-order patch for mode (ref = unpatched)."""
    if mode == "ref":
        return eu.simulate
    src = inspect.getsource(eu.simulate)
    if mode == "h1":
        assert src.count(OLD_EXP) == 1, "entry-exp anchor not unique"
        patched = src.replace(OLD_EXP, NEW_EXP_H1)
    elif mode == "b0":
        assert src.count(OLD_HIT) == 1, "entry-hit anchor not found"
        patched = src.replace(OLD_HIT, NEW_HIT_B0)
    else:  # pragma: no cover
        raise ValueError(mode)
    g = eu.simulate.__globals__
    ns: dict = {}
    exec(patched, g, ns)  # noqa: S102 - audited pattern (cf. oc_manualnight)
    fn = ns.get("simulate")
    if fn is None:  # pragma: no cover
        raise RuntimeError("patched simulate missing")
    fn._patched_src = patched  # test hook: lets tests inspect the patch
    return fn


def _load(name: str, path: Path):
    spec = __import__("importlib.util", fromlist=["util"]).spec_from_file_location(name, path)
    mod = __import__("importlib.util", fromlist=["module_from_spec"]).module_from_spec(spec)
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
            print(f"manualrest: RAM check failed ({exc}), retry in 300 s", flush=True)
            time.sleep(300)
            continue
        if free_kb > need_kb:
            return
        print(f"manualrest: {free_kb / 1048576:.2f} GB free, waiting for > {min_gb:.0f} GB",
              flush=True)
        time.sleep(300)


def geo_mean_monthly(Rs) -> float:
    g = 1.0
    for r in Rs:
        g *= 1.0 + float(r) / 100.0
    return 100.0 * (g ** (1.0 / len(Rs)) - 1.0)


# --------------------------------------------------------------------------
# Stage 0: reproduce the G2 / G2+carry baselines (read-only) or STOP
# --------------------------------------------------------------------------
def validate_baselines() -> dict:
    v421_runs = pickle.loads((RD / "v421/v421_runs.pkl").read_bytes())
    assert set(v421_runs) == {0, 1, 2, 3}
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    v388 = pof._load("v388_mrest_val", RD / "v388/v388_bot_stop_distance.py")
    rm = pof._load("reset_mrest_val", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    strat = "R2B1D17BFG2"
    got_r, got_dd = [], []
    for y in range(5):
        m = rm.year_reset(v421_runs, strat, y)
        got_r.append(m["R"])
        got_dd.append(m["DD"])
    assert got_r == [r for r, _ in exp["years"]], (got_r, exp["years"])
    assert got_dd == [d for _, d in exp["years"]], (got_dd, exp["years"])
    R5 = round(float(np.prod([1 + r / 100 for r in got_r]) ** (1 / 5) - 1) * 100, 3)
    assert R5 == exp["R"] and min(got_r) == exp["W"] and max(got_dd) == exp["DD"], (R5, exp)
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(v421_runs, strat, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    assert full == exp["full_path_dd"], (full, exp["full_path_dd"])
    print(f"G2 validation OK: R {R5} / W {min(got_r)} / DD {max(got_dd)} / full {full}", flush=True)

    cc = json.loads((ROOT / "research/tournament/oc_carrycompound/results.json").read_text())
    g = cc["rows"]["G2_f0.25"]
    assert (g["R"], g["W"], g["DD"], g["full_path_dd"]["full"]) == (5.634, 2.778, 16.75, 16.66), g
    assert cc["carry_add_pp_per_month"] == 0.224, cc
    print("G2+carry validation OK: 5.634 / 2.778 / 16.75 / full 16.66 (+0.224)", flush=True)

    man = json.loads((ROOT / "research/diagnostics/oc_manualcap/results.json").read_text())
    m5 = man["rows"]["M5_human"]
    assert (m5["R5"], m5["W"], m5["maxDD"], m5["fullDD"], m5["book_win"]) == \
        (3.728, 0.847, 17.94, 17.79, 0.6482), m5
    print("M5_human reference OK: R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 / win .6482",
          flush=True)
    return {"g2": {"R": R5, "W": min(got_r), "DD": max(got_dd), "full": full},
            "g2_carry": {"R": 5.634, "W": 2.778, "DD": 16.75, "full": 16.66},
            "m5_ref": {"R5": 3.728, "W": 0.847, "maxDD": 17.94, "fullDD": 17.79}}


# --------------------------------------------------------------------------
# Stage 1: 4-phase MANUAL runs (heavy)
# --------------------------------------------------------------------------
def run_phase(shift: int):
    wait_for_ram(2.0)
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod_mrest_{shift}",
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_mrest_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_mrest_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_mrest_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    sims = {"ref": eu.simulate, "b0": make_simulate(eu, "b0"), "h1": make_simulate(eu, "h1")}
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
        eq_max=(eq if eq_max is None else eq_max).copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    cols = list(books154.columns)
    na = len(cols)
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, cols)
    del M
    gc.collect()
    idx = prep["idx"]
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    books = std_books.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    tab = pd.read_parquet(hist.R2_TABLE)
    lsz = dict(zip([(t, s, int(r)) for t, s, r in
                    zip(tab["T"], tab["sym"], tab["rung"])],
                   tab["size"].astype(float)))
    del tab
    gc.collect()
    rmap = dict(hist.M3_R2_RUNG)
    hours = np.asarray((idx + pd.Timedelta(hours=4)).hour)
    night = (20 + shift) % 24
    out = {}
    for row in ROWS:
        mode = ENGINE_MODE[row]
        kw, trade = pof.pipe_setup("v367", hist, v221, v216, idx, cols, True)
        if SIZE_MULT[row] is not None:
            kw["size_mult"] = float(SIZE_MULT[row])
        pol = trade["policy"]
        trade["policy"] = lambda i, a, st, pol=pol: (
            ("wait" if st["pos"] == 0 else "hold")
            if hours[i] == night else pol(i, a, st))
        kw["sleeve_start"] = SLEEVE_START
        # night bar skipped for dips on EVERY row (0 on night else 1.0), exactly
        # as oc_manualcap's reference filter (G=None) and manual_human.py
        kw["sleeve_filter"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0
        events: list = []
        sims[mode](books, opens, prep, trade=trade, win_start=WIN_START,
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
        fills = []
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
            rr = [float(e["ret"]) for e in ev if e["kind"] in RUNG_KINDS and "ret" in e]
            nfill = sum(1 for e in ev if e["kind"] == "book_fill")
            nexp = sum(1 for e in ev if e["kind"] == "order_expire")
            nlate = 0
            for e in ev:
                if e["kind"] != "book_fill":
                    continue
                t = pd.Timestamp(e["t"])
                mm = int((t - (t.floor("4h"))) .total_seconds() // 60)
                if mm >= B0_END:
                    nlate += 1
            years.append(dict(nb=int(nb), wb=int(wb), nr=len(rr),
                              wr=int(sum(r > 0 for r in rr)),
                              nfill=int(nfill), nexp=int(nexp), nlate=int(nlate)))
            yy = m["yearly"][y]
            ch.append(dict(net=yy["net_pct"] / 100, dd=yy["dd_1m_pct"]))
            fills.append(dict(nfill=int(nfill), nexp=int(nexp), nlate=int(nlate)))
        out[row] = dict(run=run, wins=years, cross=ch)
        print(shift, row, [round(100 * v["net"], 1) for v in ch],
              [v["dd"] for v in ch],
              [f["nfill"] for f in fills], flush=True)
        del events
        gc.collect()
    del opens, prep, books
    gc.collect()
    return shift, out


def check_harness_identity(allres) -> None:
    """My M5_human rerun must equal the stored oc_manualcap run bit-exact."""
    stored = pickle.loads((ROOT / "research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl").read_bytes())
    maxd = 0.0
    for s in range(4):
        for k in ("eq", "eq_min"):
            a = np.asarray(allres[s]["M5_human"]["run"][k], dtype=float)
            b = np.asarray(stored[s]["M5_human"]["run"][k], dtype=float)
            assert a.shape == b.shape, (s, k, a.shape, b.shape)
            maxd = max(maxd, float(np.max(np.abs(a - b))))
    print(f"M5_human harness identity: max abs d(eq) = {maxd:.3e}", flush=True)
    assert maxd <= 1e-12, f"harness drift {maxd:.3e} -- STOP (baseline not reproduced)"


def runs_for_reset(allres, row):
    return {s: {row: allres[s][row]["run"]} for s in allres}


def score_all(allres) -> dict:
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    v388 = pof._load("v388_mrest_score", RD / "v388/v388_bot_stop_distance.py")
    rm = pof._load("reset_mrest_score",
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
        nf = sum(allres[s][row]["wins"][y]["nfill"] for s in range(4) for y in range(5))
        nx = sum(allres[s][row]["wins"][y]["nexp"] for s in range(4) for y in range(5))
        nl = sum(allres[s][row]["wins"][y]["nlate"] for s in range(4) for y in range(5))
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
            years_fills=[
                sum(allres[s][row]["wins"][y]["nfill"] for s in range(4)) for y in range(5)],
            years_expires=[
                sum(allres[s][row]["wins"][y]["nexp"] for s in range(4)) for y in range(5)],
            years_late_fills=[
                sum(allres[s][row]["wins"][y]["nlate"] for s in range(4)) for y in range(5)],
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
            fills=int(nf), expires=int(nx), late_fills=int(nl),
            cross_Rmean=round(float(np.mean(r_ph)), 3),
        )
    return table


def robust_pick(table: dict) -> str:
    """H1 vs H2 on dev4 only: DD<=20, no losing dev year; prefer mean>=5;
    then highest dev4 WORST year; ties -> higher mean."""
    cands = {}
    for row in ("H1_rest4h", "H2_rest4h_x2dip"):
        t = table[row]
        if t["DDdev4"] <= 20 and t["losing_dev4"] == 0:
            cands[row] = t
    if not cands:
        return "none-eligible"
    hot = {k: v for k, v in cands.items() if v["Rdev4"] >= 5}
    pool = hot or cands
    best = max(pool, key=lambda k: (pool[k]["Wdev4"], pool[k]["Rdev4"]))
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--heavy", action="store_true")
    args = ap.parse_args()
    base = validate_baselines()
    if not args.heavy:
        print("validate-only done (no engine run). Use --heavy for the 4-phase runs.",
              flush=True)
        return
    TMP.mkdir(parents=True, exist_ok=True)
    if CACHE.exists():
        allres = pickle.loads(CACHE.read_bytes())
        print("loaded cached phase runs", flush=True)
    else:
        allres = {}
        for shift in range(4):
            s, out = run_phase(shift)
            allres[s] = out
            CACHE.write_bytes(pickle.dumps(allres))
            print(f"phase {s} cached", flush=True)
    check_harness_identity(allres)
    table = score_all(allres)
    pick = robust_pick(table)
    out = {
        "meta": {
            "idea": "IDEAS_20261007 section 5: MANUAL 4h-rest brackets",
            "harness": ("MANUAL 4-phase (M5 pipe v367, human schedule win_start=15 / "
                        "sleeve_start=16, night bar skipped, agents ON, gate costs "
                        "maker 0.0002 / taker 0.00055 / longs pay 0.0001 per 8h)"),
            "metric": ("reset_metric.year_reset per anchor + v388.mix full-path DD "
                       "(v421/v422 convention); selection on dev years 2021-2024 only; "
                       "last year POST-HOC (seen years, never used to choose)"),
            "rows": {
                "M5_human": "deployed reference (reproduces oc_manualcap bit-exact)",
                "B0_60min": "idea comparator: book entries expire 60 min after placement (min 15..74)",
                "H1_rest4h": "candidate 1: book entries rest to next 4h close (min 15..239, base size)",
                "H2_rest4h_x2dip": "candidate 2: H1 + dip size_mult x2.0 (8.75, budget 0.26)",
            },
            "baseline": base,
            "pick": pick,
            "costs": {"maker": MAKER, "taker": TAKER, "fund_long_8h": FUND_LONG},
        },
        "rows": table,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for row, v in table.items():
        print(row, "R5", v["R5"], "W", v["W"], "maxDD", v["maxDD"], "fullDD", v["fullDD"],
              "Rdev4", v["Rdev4"], "Wdev4", v["Wdev4"], "DDdev4", v["DDdev4"],
              "Rlast", v["Rlast"], "book_win", v["book_win"],
              "fills", v["fills"], "expires", v["expires"], "late", v["late_fills"],
              flush=True)
    print("PICK (dev4 only):", pick, flush=True)


if __name__ == "__main__":
    main()
