"""oc_wfselect: walk-forward meta-selection over cached 4-phase variant rows.

LIGHT job: single process, loads one runs.pkl at a time, no 1m data.
Per-year stats via research/diagnostics/r2_decompose5/reset_metric.py year_reset.
See PLAN.md (pre-registered before computing outcomes).
Usage: .venv/Scripts/python.exe research/tournament/oc_wfselect/run_wfselect.py
"""
from __future__ import annotations

import gc
import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research" / "parallel" / "rounds" / "parallel-20260906-r2"
PLATEAU = ROOT / "research" / "diagnostics" / "oc_plateau" / "oc_plateau_runs.pkl"

SOURCES: dict[str, list[str]] = {
    "v406/v406_runs.pkl": ["R2B1D16", "R2B1D18B08", "R2B1_130"],
    "v411/v411_runs.pkl": ["R2B1D17BF"],
    "v415/v415_runs.pkl": ["R2B1D17BFS5", "R2B1D17BFS6"],
    "v417/v417_runs.pkl": ["R2B1D17BFC", "R2B1D17BFCX", "R2B1D17BFX"],
    "v418/v418_runs.pkl": ["R2B1D17BFDS"],
    "v419/v419_runs.pkl": ["R2B1D17BFBRK05", "R2B1D17BFBRK08", "R2B1D17BFBUD13"],
    "v420/v420_runs.pkl": ["R2B1F15K20", "R2B1F15K23", "R2B1F20K17", "R2B1F20K20"],
    "v421/v421_runs.pkl": ["R2B1D17BFG2", "R2B1D17BFG3"],
    "v422/v422_runs.pkl": ["G15K20", "G2F20K20", "G2K20"],
    "v423/v423_runs.pkl": ["R2B1D17BFX45", "R2B1D17BFX45G2", "R2B1D17BFX5"],
    "__plateau__": ["R2B1D17BF_F20", "R2B1D17BF_F30", "R2B1D17BF_MA900",
                    "R2B1D17BF_MA1500", "R2B1D17BF_BM035", "R2B1D17BF_BM065"],
}
ANCH = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
BASE = "R2B1D17BF"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def geo(rs) -> float:
    rs = list(rs)
    return float(100 * (np.prod([1 + r / 100 for r in rs]) ** (1 / len(rs)) - 1))


def pick_robust(stats: dict[str, list[list[float]]], sel: list[int]):
    """AGENTS robust criterion over selection years sel. Returns (row, fallback)."""
    elig = []
    for row, yrs in stats.items():
        Rs = [yrs[y][0] for y in sel]
        DDs = [yrs[y][1] for y in sel]
        if all(d <= 20 for d in DDs) and all(r >= 0 for r in Rs):
            elig.append(row)
    pool = [r for r in elig if geo(stats[r][y][0] for y in sel) >= 5] or elig

    def key(r):
        Rs = [stats[r][y][0] for y in sel]
        return (min(Rs), geo(Rs))
    if pool:
        best_w = max(min(stats[r][y][0] for y in sel) for r in pool)
        cand = [r for r in pool if min(stats[r][y][0] for y in sel) == best_w]
        best_m = max(geo(stats[r][y][0] for y in sel) for r in cand)
        cand = sorted(r for r in cand if geo(stats[r][y][0] for y in sel) == best_m)
        return cand[0], False
    allm = {r: geo(stats[r][y][0] for y in sel) for r in stats}
    best = max(allm.values())
    cand = sorted(r for r, m in allm.items() if m == best)
    return cand[0], True


def pick_dd18(stats: dict[str, list[list[float]]], sel: list[int]):
    elig = [r for r, yrs in stats.items()
            if all(yrs[y][1] <= 18 for y in sel)]
    pool = elig or list(stats)
    fb = not elig
    m = {r: geo(stats[r][y][0] for y in sel) for r in pool}
    best = max(m.values())
    return sorted(r for r, v in m.items() if v == best)[0], fb


def main():
    rm = _load("rm_wfselect", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    stats: dict[str, list[list[float]]] = {}
    for src, rows in SOURCES.items():
        p = PLATEAU if src == "__plateau__" else RD / src
        runs = pickle.loads(Path(p).read_bytes())
        for row in rows:
            assert row in runs[0], f"{row} missing in {src}"
            stats[row] = [[rm.year_reset(runs, row, y)["R"],
                           rm.year_reset(runs, row, y)["DD"]] for y in range(5)]
        print(f"{src}: " + ", ".join(
            f"{r} R={[x[0] for x in stats[r]]}" for r in rows), flush=True)
        del runs
        gc.collect()
    assert len(stats) == 31, len(stats)

    wfA, wfB, looA = {}, {}, {}
    for k in (1, 2, 3, 4):
        sel = list(range(k))
        pa, fba = pick_robust(stats, sel)
        pb, fbb = pick_dd18(stats, sel)
        wfA[str(k)] = {"pick": pa, "fallback": fba,
                       "R": stats[pa][k][0], "DD": stats[pa][k][1]}
        wfB[str(k)] = {"pick": pb, "fallback": fbb,
                       "R": stats[pb][k][0], "DD": stats[pb][k][1]}
        if k >= 2:
            loo = {}
            for drop in sel:
                sub = [y for y in sel if y != drop]
                p, _ = pick_robust(stats, sub)
                loo[f"drop_{ANCH[drop][:4]}"] = p
            looA[str(k)] = {"main": pa, "loo": loo,
                            "stable": all(v == pa for v in loo.values())}

    def chain(wf):
        Rs = [wf[str(k)]["R"] for k in (1, 2, 3, 4)]
        DDs = [wf[str(k)]["DD"] for k in (1, 2, 3, 4)]
        return {"R_geo": round(geo(Rs), 3), "maxDD": max(DDs),
                "losing": sum(r < 0 for r in Rs),
                "years": [[wf[str(k)]["R"], wf[str(k)]["DD"]] for k in (1, 2, 3, 4)]}

    chainA, chainB = chain(wfA), chain(wfB)
    base_years = [[stats[BASE][k][0], stats[BASE][k][1]] for k in (1, 2, 3, 4)]
    chainBase = {"R_geo": round(geo(r for r, _ in base_years), 3),
                 "maxDD": max(d for _, d in base_years),
                 "losing": sum(r < 0 for r, _ in base_years), "years": base_years}
    scored = {r: geo(yrs[k][0] for k in (1, 2, 3, 4)) for r, yrs in stats.items()}
    bh = max(scored.values())
    bh_rows = sorted(r for r, m in scored.items() if m == bh)
    bh_row = bh_rows[0]
    bh_years = [[stats[bh_row][k][0], stats[bh_row][k][1]] for k in (1, 2, 3, 4)]
    chainBH = {"row": bh_row, "R_geo": round(bh, 3),
               "maxDD": max(d for _, d in bh_years),
               "losing": sum(r < 0 for r, _ in bh_years), "years": bh_years}

    excess = [round(wfA[str(k)]["R"] - stats[BASE][k][0], 3) for k in (1, 2, 3, 4)]
    npos = sum(e > 0 for e in excess)
    nstable = sum(1 for k in ("2", "3", "4") if looA[k]["stable"])
    verdict = "PROMISING" if (npos >= 3 and nstable >= 3) else "NOT PROMISING"

    out = {"version": "oc_wfselect", "anchors": ANCH, "n_candidates": 31,
           "per_row_years": stats, "ruleA_wf": wfA, "ruleA_chain": chainA,
           "ruleB_wf": wfB, "ruleB_chain": chainB,
           "always_R2B1D17BF": chainBase, "best_hindsight": chainBH,
           "looA": looA, "excess_A_minus_base": excess,
           "npos_ge3": npos >= 3, "nstable": nstable,
           "verdict": verdict,
           "note": "Candidates designed after seeing all five years; "
                   "even this walk-forward chain is optimistic."}
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("chainA", chainA, flush=True)
    print("chainB", chainB, flush=True)
    print("base", chainBase, flush=True)
    print("BH", chainBH, flush=True)
    print("excess", excess, "npos", npos, "nstable", nstable, verdict, flush=True)


if __name__ == "__main__":
    main()
