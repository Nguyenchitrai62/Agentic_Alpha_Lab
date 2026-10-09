"""oc_clockweights: Adaptive 4-clock capital share (IDEAS6 #6).

Implements PLAN.md exactly. LIGHT: hourly grid only (~44k rows x4), no 1m,
no GPU, one process.

  python research/tournament/oc_clockweights/compute_clockweights.py
"""

from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
RUNS_PKL = RD / "v421/v421_runs.pkl"
RES_JSON = RD / "v421/v421_result.json"
STRAT = "R2B1D17BFG2"
EMBARGO = pd.Timedelta(days=7)
TRAIL = pd.Timedelta(days=365)
YEAR = pd.Timedelta(days=365)
MIN_TRAIL_H = 2400


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_ocw", RD / "v388/v388_bot_stop_distance.py")
rm = _load("reset_ocw", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")

ANCH = [pd.Timestamp(a, tz="UTC") for a in v388.ANCH]
G0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
G1 = v388.Y1 + pd.Timedelta(hours=12)
GRID0_LBL = "2021-09-24 04:00"


def trailing_weights(E: np.ndarray, idx: pd.DatetimeIndex, y: int):
    """Return (w_invDD, w_sharpe, info) for anchor y. Causal: window ends A-7d."""
    a0 = ANCH[y]
    if y == 0:
        w = np.full(4, 0.25)
        return w, w.copy(), {"n_rows": 0, "fallback": "y0_no_history"}
    wend = a0 - EMBARGO
    wstart = wend - TRAIL
    m = (idx > wstart) & (idx <= wend)
    n_rows = int(np.sum(m))
    if n_rows < MIN_TRAIL_H:
        w = np.full(4, 0.25)
        return w, w.copy(), {"n_rows": n_rows, "fallback": "short_history"}
    Ew, Mw = E[m], M_of_E[m]  # set by main via global; see below
    # V1: trailing marked max-DD per phase, rebased at window start
    # base = last grid <= wstart (per-phase equity then)
    lei0 = np.where(idx <= wstart)[0]
    base = E[lei0[-1]] if len(lei0) else E[m][0]
    base = np.where(base <= 0, 1.0, base)
    es = Ew / base
    ms = Mw / base
    dds = []
    for s in range(4):
        pk = np.maximum.accumulate(es[:, s])
        dd = float(np.max(1 - ms[:, s] / pk)) * 100.0
        dds.append(dd)
    dds = np.array(dds)
    ddc = np.clip(dds, 1.0, 100.0)
    inv = 1.0 / ddc
    w1 = inv / inv.sum()
    # V2: trailing hourly Sharpe per phase (annualised, floor 0)
    r = Ew[1:] / Ew[:-1] - 1.0
    shr = []
    for s in range(4):
        rs = r[:, s]
        rs = rs[np.isfinite(rs)]
        if len(rs) < 2:
            shr.append(0.0)
            continue
        sd = float(np.std(rs, ddof=1))
        if not np.isfinite(sd) or sd <= 0:
            shr.append(0.0)
        else:
            shr.append(float(np.mean(rs)) / sd * np.sqrt(8760.0))
    shr = np.array(shr)
    pos = np.clip(shr, 0.0, None)
    if pos.sum() <= 0:
        w2 = np.full(4, 0.25)
    else:
        w2 = pos / pos.sum()
    assert abs(w1.sum() - 1) < 1e-12 and (w1 >= 0).all()
    assert abs(w2.sum() - 1) < 1e-12 and (w2 >= 0).all()
    return w1, w2, {"n_rows": n_rows,
                    "trail_dd": [round(float(x), 2) for x in dds],
                    "trail_sharpe": [round(float(x), 3) for x in shr]}


def weighted_year(Ec, Mc, idx, y, w):
    a0 = ANCH[y]
    seg = (idx > a0) & (idx <= a0 + YEAR)
    lei = np.where(idx <= a0)[0]
    b = Ec[lei[-1]] if len(lei) else np.ones(4)
    b = np.where(b <= 0, 1.0, b)
    E4 = Ec[seg] / b
    M4 = Mc[seg] / b
    es = (E4 * w).sum(axis=1)
    ms = (M4 * w).sum(axis=1)
    pk = np.maximum.accumulate(es)
    R = round(100 * float(es[-1] ** (1 / 12) - 1), 3)
    DD = round(100 * float(np.max(1 - ms / pk)), 2)
    return R, DD, float(es[-1]), es, ms


def stitched_full(Ec, Mc, idx, weights_by_year):
    """Yearly-weighted compounding stitch covering EVERY grid point.

    Per-year R/DD (weighted_year) stay on the fixed reset convention
    seg=(A_y, A_y+365d] for comparability with REF year_reset. But that
    convention drops one day across the 2024 leap (2023-09-24+365d =
    2024-09-23, while A_3 = 2024-09-24). The continuous path therefore
    covers year y as (A_y, A_{y+1}] for y<4 and (A_4, A_4+365d] for y=4
    (same approach as oc_phaserebal: per-year slices on 365d, full path
    on the full grid), so no grid point is left unassigned.
    """
    A = np.full(len(idx), np.nan)
    M = np.full(len(idx), np.nan)
    A_anchor = 1.0
    # value of Ec at GRID0 index 0 anchors the first year base
    for y in range(5):
        a0 = ANCH[y]
        w = weights_by_year[y]
        hi = ANCH[y + 1] if y < 4 else a0 + YEAR
        seg = (idx > a0) & (idx <= hi)
        lei = np.where(idx <= a0)[0]
        b = Ec[lei[-1]] if len(lei) else np.ones(4)
        b = np.where(b <= 0, 1.0, b)
        ii = np.where(seg)[0]
        assert len(ii) > 0, y
        E4 = Ec[ii] / b
        M4 = Mc[ii] / b
        es = (E4 * w).sum(axis=1)
        ms = (M4 * w).sum(axis=1)
        A[ii] = A_anchor * es
        M[ii] = A_anchor * ms
        A_anchor = float(A[ii[-1]])
    covered = idx >= G0
    assert bool(np.isfinite(A[covered]).all()), "stitched path must cover every grid point"
    assert bool(np.isfinite(M[covered]).all())
    return A, M


def full_dd(A, M, idx):
    seg = idx > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = A[seg], M[seg]
    pk = np.maximum.accumulate(es)
    dd_m = round(100 * float(np.max(1 - ms / pk)), 2)
    dd_c = round(100 * float(np.max(1 - es / pk)), 2)
    return dd_m, dd_c, max(dd_m, dd_c)


def geomean(rs):
    return round(100 * (float(np.prod([1 + r / 100 for r in rs])) ** (1 / len(rs)) - 1), 3)


M_of_E = None  # set in main for trailing_weights use


def main():
    global M_of_E
    runs = pickle.loads(RUNS_PKL.read_bytes())
    assert set(runs.keys()) == {0, 1, 2, 3}
    for s in range(4):
        assert set(runs[s][STRAT].keys()) == {"t", "eq", "eq_min"}

    # ---- REF: reproduce G2 to the digit via imported year_reset ----
    ref_years = [rm.year_reset(runs, STRAT, y) for y in range(5)]
    exp = json.loads(RES_JSON.read_text())["rows"][STRAT]
    assert [yy["R"] for yy in ref_years] == [r for r, _ in exp["years"]], ref_years
    assert [yy["DD"] for yy in ref_years] == [d for _, d in exp["years"]], ref_years
    assert round(float(np.prod([1 + yy["R"] / 100 for yy in ref_years]) ** (1 / 5) - 1) * 100, 3) == exp["R"]
    assert min(yy["R"] for yy in ref_years) == exp["W"]
    assert max(yy["DD"] for yy in ref_years) == exp["DD"]
    e_mix, mn_mix = v388.mix(runs, STRAT, G1)
    seg = e_mix.index > pd.Timestamp("2021-09-24", tz="UTC")
    esf, msf = e_mix[seg].to_numpy(), mn_mix[seg].to_numpy()
    full_ref = round(100 * float(np.max(1 - msf / np.maximum.accumulate(esf))), 2)
    assert full_ref == exp["full_path_dd"], (full_ref, exp["full_path_dd"])
    print("G2 validation OK: reproduces v421_result R2B1D17BFG2 to the digit", flush=True)

    # ---- per-phase hourly series ----
    Es, Ms = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s][STRAT], G0, G1)
        Es.append(e1)
        Ms.append(m1)
    idx = Es[0].index
    assert all(e.index.equals(idx) for e in Es + Ms)
    Ec = np.column_stack([e.to_numpy(float) for e in Es])
    Mc = np.column_stack([m.to_numpy(float) for m in Ms])
    M_of_E = Mc

    # ---- trailing weights per anchor (causal, embargo 7d) ----
    W1, W2, infos = {}, {}, {}
    for y in range(5):
        w1, w2, info = trailing_weights(Ec, idx, y)
        W1[y], W2[y], infos[y] = w1, w2, info
        print(f"anchor {ANCH[y].date()} n={info['n_rows']} "
              f"V1={np.round(w1,4).tolist()} V2={np.round(w2,4).tolist()} {info}", flush=True)

    # ---- dev4 weighted years (y 0..3) for both variants ----
    devR1, devD1, devR2, devD2 = [], [], [], []
    for y in range(4):
        r, d, _, _, _ = weighted_year(Ec, Mc, idx, y, W1[y])
        devR1.append(r)
        devD1.append(d)
        r2, d2, _, _, _ = weighted_year(Ec, Mc, idx, y, W2[y])
        devR2.append(r2)
        devD2.append(d2)

    def dev_stats(Rs, DDs):
        return {"R": Rs, "DD": DDs, "mean4": geomean(Rs),
                "worst4": min(Rs), "DDmax4": max(DDs),
                "losing4": sum(r < 0 for r in Rs)}

    s1, s2 = dev_stats(devR1, devD1), dev_stats(devR2, devD2)
    print("V1 dev4", s1, flush=True)
    print("V2 dev4", s2, flush=True)

    # ---- robust pick on dev4 ONLY ----
    def eligible(s):
        return s["DDmax4"] <= 20 and s["losing4"] == 0

    cands = {"V1_invDD": s1, "V2_sharpe": s2}
    elig = {k: v for k, v in cands.items() if eligible(v)}
    if elig and any(v["mean4"] >= 5 for v in elig.values()):
        pool = {k: v for k, v in elig.items() if v["mean4"] >= 5}
        pick = max(pool, key=lambda k: (pool[k]["worst4"], pool[k]["mean4"]))
        rule = "eligible + mean>=5 -> highest WORST, ties mean"
    elif elig:
        pick = max(elig, key=lambda k: (elig[k]["worst4"], elig[k]["mean4"]))
        rule = "eligible (none >=5) -> highest WORST, ties mean"
    else:
        pick = max(cands, key=lambda k: (cands[k]["worst4"], cands[k]["mean4"]))
        rule = "FALLBACK no eligible -> highest WORST (disclosed)"
    print("dev4 pick:", pick, rule, flush=True)

    # ---- score y=4 ONCE for pick + REF only ----
    Wpick = W1 if pick == "V1_invDD" else W2
    rp, dp, endp, _, _ = weighted_year(Ec, Mc, idx, 4, Wpick[4])
    ref4 = ref_years[4]
    print(f"y4 pick {pick}: R={rp} DD={dp}; REF: R={ref4['R']} DD={ref4['DD']}", flush=True)

    # ---- full-path DD: REF continuous (v421) + pick stitched (disclosed) ----
    A_pick, M_pick = stitched_full(Ec, Mc, idx,
                                   {y: (Wpick[y] if y <= 4 else Wpick[4]) for y in range(5)})
    # stitched arrays cover grid from G0; restrict DD to >2021-09-24 inside full_dd
    fmp, fcp, fgp = full_dd(A_pick, M_pick, idx)

    # 5y means: REF 5y from v421_result; pick 5y = geo(dev4 + scored y4)
    R5pick = geomean(devR1 + [rp] if pick == "V1_invDD" else devR2 + [rp])
    out = {
        "meta": {
            "idea": "IDEAS6 #6 Adaptive 4-clock capital share (yearly weights)",
            "strat": STRAT,
            "src": "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl",
            "grid": [str(idx[0]), str(idx[-1])],
            "anchors": [str(a) for a in ANCH],
            "metric": "weighted reset per anchor year (weights frozen all year); R=100*(end^(1/12)-1), DD=marked peak-to-trough in 365d segment; full-path DD = max(close,marked) from 2021-09-24",
            "embargo": "trailing window ends anchor-7d; y0 fallback equal 1/4; V1 DD clip [1,100]; V2 Sharpe=max(mean/std*sqrt(8760),0) else equal",
            "costs": "stored G2 equity already embeds gate costs (maker 0.0002, taker 0.00055, longs 0.0001/8h, trade-through, minute-0-4 ban, stop-first); overlay changes capital shares only, no new orders",
            "engine_confirm": "NOT executed; overlay exact at 1x under linear sizing; win rates and fee/funding splits N/A from equity-only pkl",
            "selection": "dev4-only robust (DD<=20, no losing; prefer mean>=5; highest WORST; ties mean); y4 scored ONCE for pick+REF",
            "plan": "research/tournament/oc_clockweights/PLAN.md (frozen pre-outcome)",
        },
        "ref_G2": {
            "years": [{"anchor": str(ANCH[y].date()), "R": ref_years[y]["R"],
                       "DD": ref_years[y]["DD"]} for y in range(5)],
            "R5": exp["R"], "W5": exp["W"], "DDmax": exp["DD"],
            "full_path_dd": exp["full_path_dd"], "losing5": 0,
            "dev4": {"R": [ref_years[y]["R"] for y in range(4)],
                     "DD": [ref_years[y]["DD"] for y in range(4)]},
        },
        "variants": {
            "V1_invDD": {
                "weights": {str(ANCH[y].date()): [round(float(x), 6) for x in W1[y]]
                            for y in range(5)},
                "dev4": s1,
                "y4": "NOT_SCORED (only dev4 pick + REF scored in y4)",
            },
            "V2_sharpe": {
                "weights": {str(ANCH[y].date()): [round(float(x), 6) for x in W2[y]]
                            for y in range(5)},
                "dev4": s2,
                "y4": "NOT_SCORED (only dev4 pick + REF scored in y4)",
            },
        },
        "trailing_info": {str(ANCH[y].date()): infos[y] for y in range(5)},
        "pick": {"name": pick, "rule": rule},
        "y4_once": {
            pick: {"anchor": str(ANCH[4].date()), "R": rp, "DD": dp,
                   "end": round(endp, 6)},
            "REF_G2": {"anchor": str(ANCH[4].date()), "R": ref4["R"],
                       "DD": ref4["DD"]},
        },
        "full_path_dd": {
            "REF_G2_continuous": exp["full_path_dd"],
            pick + "_stitched_yearly_compounded": {
                "marked": fmp, "close": fcp, "full": fgp},
        },
        "win_rates": "N/A (v421_runs.pkl holds t/eq/eq_min only; no trade ledger)",
        "fee_funding_split": "N/A (same reason; stored equity is net of gate costs)",
    }
    # fill pick 5y + dev rows for the winner
    devR = devR1 if pick == "V1_invDD" else devR2
    devD = devD1 if pick == "V1_invDD" else devD2
    out["variants"][pick]["dev4_years"] = [
        {"anchor": str(ANCH[y].date()), "R": devR[y], "DD": devD[y]} for y in range(4)]
    out["variants"][pick]["R5_with_scored_y4"] = R5pick
    out["variants"][pick]["y4_scored"] = {"R": rp, "DD": dp}
    out["variants"][pick]["y4"] = "SCORED ONCE (dev4 pick + REF only; see y4_scored / y4_once)"
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"pick {pick} R5(dev4+y4scored)={R5pick} full_stitched={fgp}", flush=True)


if __name__ == "__main__":
    main()
