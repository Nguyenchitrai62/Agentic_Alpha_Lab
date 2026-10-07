"""oc_c2ic: does the C2 calibration fix add cross-sectional info the deployed book lacks?

Inputs (read-only):
  fixed members  artifacts/research/v427_eval/c2fix_members/member_C2_{A,Aq,B,Bq}_{2021..2024}.parquet
  buggy members  artifacts/kaggle/v427/output_v2/out_C2/member_C2_{A,Aq,B,Bq}_{2021..2024}.parquet
  deployed       artifacts/research/engine_real/member_{A_O1_orders,Aq_O1_orders,B_tv,Bq_tv}.parquet
                 + members_v154.parquet (D) + members_quarterly_D.parquet (Dq)
                 + opens_v154.parquet (4h opens)
  book builder   research/tournament/oc_bookmodel_evalprep/eval_candidate.py
                 candidate book = 0.8 x new O1 + 0.2 x D, D byte-identical deployed
                 (O1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2); math replicated verbatim below.

Labels: y42(t,sym) = open[t+43]/open[t+1] - 1 (simple 42-bar forward return from
  opens t+1..t+43 on the 4h grid; positional shift on the sorted opens index).
  For rank-IC purposes this is monotone-equivalent to the common_impl log
  numerator; vol normalisation is intentionally NOT applied (raw cross-section).

Scope: dev years 2021-2024 ONLY. Scored rows t satisfy t < 2025-09-24 UTC.
  Opens beyond the cutoff are used ONLY to realise y42 for the last dev bars
  (t+43); no row t >= 2025-09-24 is ever scored. No training, no engine.

Metrics per (year, member) and per (year, book):
  pooled_spearman : Spearman over all stacked (t,sym) cells (weight vs y42).
  xs_mean         : mean of per-timestamp cross-sectional Spearman across the 5
                    majors (timestamps with zero variance on either side skipped).
  hit_rate        : P(sign(w)==sign(y42)) over cells with w != 0.
  long_share/net  : long_share = P(w>0); net_long = P(w>0)-P(w<0).
  pearson_depl    : pooled Pearson(weight_new, weight_deployed_same_slot).
Books use the same metrics plus candidate-vs-deployed book Pearson.

Verdict: YES iff candidate-book xs_mean IC > deployed-book xs_mean IC in >=3/4
  dev years AND pooled candidate-vs-deployed book Pearson < 0.7.

Usage:
  .venv/Scripts/python.exe research/tournament/oc_c2ic/compute_c2ic.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "artifacts/research/engine_real"
FIX_DIR = ROOT / "artifacts/research/v427_eval/c2fix_members"
BUG_DIR = ROOT / "artifacts/kaggle/v427/output_v2/out_C2"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
MEMBERS = ("A", "Aq", "B", "Bq")
YEARS = (2021, 2022, 2023, 2024)
CUTOFF = pd.Timestamp("2025-09-24", tz="UTC")
DEPLOYED_FILES = {
    "A": "member_A_O1_orders.parquet",
    "Aq": "member_Aq_O1_orders.parquet",
    "B": "member_B_tv.parquet",
    "Bq": "member_Bq_tv.parquet",
}


def year_interval(year: int):
    a0 = pd.Timestamp(f"{year}-09-24", tz="UTC")
    return a0, a0 + pd.Timedelta(days=365)


def pooled_spearman(w: pd.DataFrame, y: pd.DataFrame) -> tuple[float, int]:
    xs = w.stack().astype(float)
    ys = y.reindex_like(w).stack().astype(float)
    both = pd.DataFrame({"x": xs, "y": ys}).dropna()
    n = len(both)
    if n < 3 or both["x"].std() == 0 or both["y"].std() == 0:
        return float("nan"), int(n)
    return float(both["x"].corr(both["y"], method="spearman")), int(n)


def xs_ic_stats(w: pd.DataFrame, y: pd.DataFrame) -> dict:
    """Vectorised per-timestamp cross-sectional Spearman (rank then Pearson, n=5)."""
    Y = y.reindex_like(w)
    rw = w.astype(float).rank(axis=1)
    ry = Y.astype(float).rank(axis=1)
    rw = rw - rw.mean(axis=1).values[:, None]
    ry = ry - ry.mean(axis=1).values[:, None]
    denom = np.sqrt((rw ** 2).sum(axis=1).values * (ry ** 2).sum(axis=1).values)
    valid = Y.notna().all(axis=1).values & (denom > 0) & np.isfinite(denom)
    vals = ((rw.values * ry.values).sum(axis=1) / np.where(denom > 0, denom, np.nan))[valid]
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0:
        return {"xs_mean": float("nan"), "xs_median": float("nan"),
                "xs_frac_pos": float("nan"), "xs_n": 0}
    return {"xs_mean": float(vals.mean()), "xs_median": float(np.median(vals)),
            "xs_frac_pos": float((vals > 0).mean()), "xs_n": int(len(vals))}


def hit_and_positioning(w: pd.DataFrame, y: pd.DataFrame) -> dict:
    ws = w.stack().astype(float)
    ys = y.reindex_like(w).stack().astype(float)
    both = pd.DataFrame({"x": ws, "y": ys}).dropna()
    nz = both[both["x"] != 0]
    hit = float((np.sign(nz["x"]) == np.sign(nz["y"])).mean()) if len(nz) else float("nan")
    long_share = float((both["x"] > 0).mean()) if len(both) else float("nan")
    short_share = float((both["x"] < 0).mean()) if len(both) else float("nan")
    return {"hit_rate": hit, "n_hit": int(len(nz)),
            "long_share": long_share, "short_share": short_share,
            "net_long": float(long_share - short_share) if np.isfinite(long_share) else float("nan")}


def pooled_pearson(a: pd.DataFrame, b: pd.DataFrame) -> tuple[float, int]:
    xs = a.stack().astype(float)
    ys = b.reindex_like(a).stack().astype(float)
    both = pd.DataFrame({"x": xs, "y": ys}).dropna()
    n = len(both)
    if n < 3 or both["x"].std() == 0 or both["y"].std() == 0:
        return float("nan"), int(n)
    return float(both["x"].corr(both["y"], method="pearson")), int(n)


def build_book_o1(A: pd.DataFrame, B: pd.DataFrame, Aq: pd.DataFrame, Bq: pd.DataFrame,
                  D: pd.DataFrame, Dq: pd.DataFrame) -> pd.DataFrame:
    """Verbatim research/tournament/oc_bookmodel_evalprep/eval_candidate.py math.

    candidate_books_d2: O1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2 on idx=A.union(Aq);
    book = 0.8*O1 + 0.2*(D+Dq)/2 on idx2=o1.union(D).union(Dq). D/Dq are the
    deployed caches (byte-identical by construction; never from a candidate dir).
    """
    idx = A.index.union(Aq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)  # noqa: E731
    o1 = 0.5 * (f(A) + f(B)) / 2 + 0.5 * (f(Aq) + f(Bq)) / 2
    idx2 = o1.index.union(D.index).union(Dq.index)
    g = lambda X: X.reindex(idx2).fillna(0.0)  # noqa: E731
    return 0.8 * g(o1) + 0.2 * (g(D) + g(Dq)) / 2


def main() -> None:
    # ---- loads (LIGHT: only 4h parquets, all < 2 MB each) ----
    fix = {(m, y): pd.read_parquet(FIX_DIR / f"member_C2_{m}_{y}.parquet")[SYMS]
           for m in MEMBERS for y in YEARS}
    bug = {(m, y): pd.read_parquet(BUG_DIR / f"member_C2_{m}_{y}.parquet")[SYMS]
           for m in MEMBERS for y in YEARS}
    for (m, y), w in list(fix.items()) + list(bug.items()):
        w.index = pd.to_datetime(w.index, utc=True)
        w.index.name = "t"
        assert (w.index < CUTOFF).all(), f"{m} {y}: scored row >= cutoff"
    dep_full = {m: pd.read_parquet(CACHE / f)[SYMS] for m, f in DEPLOYED_FILES.items()}
    for m, w in dep_full.items():
        w.index = pd.to_datetime(w.index, utc=True)
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    D.index = pd.to_datetime(D.index, utc=True)
    Dq = pd.read_parquet(CACHE / "members_quarterly_D.parquet")[SYMS]
    Dq.index = pd.to_datetime(Dq.index, utc=True)
    opens = pd.read_parquet(CACHE / "opens_v154.parquet")[SYMS].sort_index()
    opens.index = pd.to_datetime(opens.index, utc=True)
    assert opens.index.is_monotonic_increasing
    print("loads done", flush=True)

    # y42(t) = open[t+43]/open[t+1]-1 on grid positions (realises past cutoff for tail bars)
    y42_full = opens.shift(-43) / opens.shift(-1) - 1.0

    per_member, per_book = [], []
    cand_o1_parts, dep_o1_parts = [], []
    for y in YEARS:
        a0, a1 = year_interval(y)
        print(f"members year {y} ...", flush=True)
        y42y = y42_full[(y42_full.index >= a0) & (y42_full.index < a1)]
        for m in MEMBERS:
            Wf = fix[(m, y)]
            Wb = bug[(m, y)]
            Wd = dep_full[m][(dep_full[m].index >= a0) & (dep_full[m].index < a1)][SYMS]
            assert (Wf.index < CUTOFF).all() and (Wd.index < CUTOFF).all()
            common = Wf.index.intersection(y42y.index)
            Wf, Wd = Wf.reindex(common), Wd.reindex(common)
            Wb = Wb.reindex(common)
            Y = y42y.reindex(common)
            scored = Y.dropna(how="all").index
            Wf, Wb, Wd, Y = Wf.reindex(scored), Wb.reindex(scored), Wd.reindex(scored), Y.reindex(scored)
            ps_f, n_f = pooled_spearman(Wf, Y)
            xs_f = xs_ic_stats(Wf, Y)
            hp_f = hit_and_positioning(Wf, Y)
            ps_d, _ = pooled_spearman(Wd, Y)
            xs_d = xs_ic_stats(Wd, Y)
            hp_d = hit_and_positioning(Wd, Y)
            ps_b, _ = pooled_spearman(Wb, Y)
            hp_b = hit_and_positioning(Wb, Y)
            corr_f, n_c = pooled_pearson(Wf, Wd)
            corr_b, _ = pooled_pearson(Wb, Wd)
            per_member.append({
                "year": y, "member": m, "n_bars": int(len(common)),
                "n_scored": int(len(scored)),
                "fix_pooled_spearman": ps_f, "fix_xs_mean": xs_f["xs_mean"],
                "fix_xs_median": xs_f["xs_median"], "fix_xs_frac_pos": xs_f["xs_frac_pos"],
                "fix_xs_n": xs_f["xs_n"], "fix_hit_rate": hp_f["hit_rate"],
                "fix_long_share": hp_f["long_share"], "fix_net_long": hp_f["net_long"],
                "deployed_pooled_spearman": ps_d, "deployed_xs_mean": xs_d["xs_mean"],
                "deployed_hit_rate": hp_d["hit_rate"], "deployed_net_long": hp_d["net_long"],
                "buggy_pooled_spearman": ps_b, "buggy_net_long": hp_b["net_long"],
                "buggy_long_share": hp_b["long_share"],
                "fix_vs_deployed_pearson": corr_f, "n_corr": int(n_c),
                "buggy_vs_deployed_pearson": corr_b,
                "fix_ic_minus_deployed_xs": float(xs_f["xs_mean"] - xs_d["xs_mean"])
                if np.isfinite(xs_f["xs_mean"]) and np.isfinite(xs_d["xs_mean"]) else float("nan"),
            })
        # books: stash this year's O1 parts; blended once below (eval_candidate math)
        cand_o1_parts.append((y, fix[("A", y)], fix[("B", y)], fix[("Aq", y)], fix[("Bq", y)]))
        dep_o1_parts.append((y, dep_full["A"][(dep_full["A"].index >= a0) & (dep_full["A"].index < a1)],
                            dep_full["B"][(dep_full["B"].index >= a0) & (dep_full["B"].index < a1)],
                            dep_full["Aq"][(dep_full["Aq"].index >= a0) & (dep_full["Aq"].index < a1)],
                            dep_full["Bq"][(dep_full["Bq"].index >= a0) & (dep_full["Bq"].index < a1)]))

    # Concatenate dev O1s (each year disjoint) then blend once, exactly like eval_candidate
    candA = pd.concat([p[1] for p in cand_o1_parts]).sort_index()
    candB = pd.concat([p[2] for p in cand_o1_parts]).sort_index()
    candAq = pd.concat([p[3] for p in cand_o1_parts]).sort_index()
    candBq = pd.concat([p[4] for p in cand_o1_parts]).sort_index()
    depA = pd.concat([p[1] for p in dep_o1_parts]).sort_index()
    depB = pd.concat([p[2] for p in dep_o1_parts]).sort_index()
    depAq = pd.concat([p[3] for p in dep_o1_parts]).sort_index()
    depBq = pd.concat([p[4] for p in dep_o1_parts]).sort_index()
    cand_book_full = build_book_o1(candA, candB, candAq, candBq, D, Dq)
    dep_book_full = build_book_o1(depA, depB, depAq, depBq, D, Dq)
    assert (cand_book_full.index < CUTOFF).any()
    scored_t = candA.index.intersection(dep_book_full.index)
    assert (scored_t < CUTOFF).all()

    for y in YEARS:
        a0, a1 = year_interval(y)
        Wc = cand_book_full[(cand_book_full.index >= a0) & (cand_book_full.index < a1)][SYMS]
        Wd = dep_book_full[(dep_book_full.index >= a0) & (dep_book_full.index < a1)][SYMS]
        Y = y42_full.reindex(Wc.index)
        scored = Y.dropna(how="all").index.intersection(Wd.index)
        Wc, Wd, Y = Wc.reindex(scored), Wd.reindex(scored), Y.reindex(scored)
        ps_c, _ = pooled_spearman(Wc, Y)
        xs_c = xs_ic_stats(Wc, Y)
        hp_c = hit_and_positioning(Wc, Y)
        ps_d, _ = pooled_spearman(Wd, Y)
        xs_d = xs_ic_stats(Wd, Y)
        hp_d = hit_and_positioning(Wd, Y)
        corr, n_c = pooled_pearson(Wc, Wd)
        per_book.append({
            "year": y, "n_bars": int(len(scored)),
            "cand_pooled_spearman": ps_c, "cand_xs_mean": xs_c["xs_mean"],
            "cand_xs_median": xs_c["xs_median"], "cand_hit_rate": hp_c["hit_rate"],
            "cand_net_long": hp_c["net_long"],
            "deployed_pooled_spearman": ps_d, "deployed_xs_mean": xs_d["xs_mean"],
            "deployed_hit_rate": hp_d["hit_rate"], "deployed_net_long": hp_d["net_long"],
            "cand_vs_deployed_pearson": corr, "n_corr": int(n_c),
            "cand_minus_deployed_xs": float(xs_c["xs_mean"] - xs_d["xs_mean"])
            if np.isfinite(xs_c["xs_mean"]) and np.isfinite(xs_d["xs_mean"]) else float("nan"),
        })

    wins = sum(1 for b in per_book if np.isfinite(b["cand_minus_deployed_xs"]) and b["cand_minus_deployed_xs"] > 0)
    pooled_corr, _ = pooled_pearson(
        cand_book_full.reindex(scored_t)[SYMS], dep_book_full.reindex(scored_t)[SYMS])
    verdict = "YES" if (wins >= 3 and np.isfinite(pooled_corr) and pooled_corr < 0.7) else "NO"

    out = {
        "task": "oc_c2ic",
        "sources": {
            "fixed": "artifacts/research/v427_eval/c2fix_members/member_C2_{A,Aq,B,Bq}_{2021..2024}.parquet",
            "buggy": "artifacts/kaggle/v427/output_v2/out_C2/member_C2_{A,Aq,B,Bq}_{2021..2024}.parquet",
            "deployed": ["member_A_O1_orders", "member_Aq_O1_orders", "member_B_tv", "member_Bq_tv"],
            "D": "members_v154.parquet key D + members_quarterly_D.parquet (byte-identical both books)",
            "opens": "artifacts/research/engine_real/opens_v154.parquet",
            "book_builder": "research/tournament/oc_bookmodel_evalprep/eval_candidate.py candidate_books_d2 (verbatim math)",
            "process_note": "v427_c2_rank_calibrated.py: buggy C2 all-short (Platt base-rate); fix centres on calibration-fold base rate",
        },
        "label": "y42(t,sym)=open[t+43]/open[t+1]-1 (42-bar simple forward return, 4h grid positions)",
        "scope": ("dev years 2021-2024 only; scored t < 2025-09-24 UTC; "
                  "y42 for late-2024 bars realises from opens up to t+43 (~2025-09-30) "
                  "but no t >= 2025-09-24 is scored; no tail dropped (all dev bars realised)"),
        "metric_defs": ("pooled_spearman=stacked Spearman(w,y42); xs_mean=mean per-t XS Spearman(5 syms); "
                        "hit_rate=P(sign w==sign y42|w!=0); net_long=P(w>0)-P(w<0); "
                        "pearson=pooled Pearson(new,deployed)"),
        "per_member": per_member,
        "per_book": per_book,
        "book_corr_pooled_2021_2024": pooled_corr,
        "book_ic_wins_cand_over_deployed": int(wins),
        "verdict_rule": "YES iff cand book xs_mean > deployed book xs_mean in >=3/4 years AND pooled book Pearson < 0.7",
        "verdict": verdict,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps({"verdict": verdict, "wins": int(wins),
                      "pooled_corr": round(float(pooled_corr), 4) if np.isfinite(pooled_corr) else None,
                      "per_book": [{k: b[k] for k in ("year", "cand_xs_mean", "deployed_xs_mean",
                                                      "cand_minus_deployed_xs", "cand_vs_deployed_pearson")}
                                    for b in per_book]}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
