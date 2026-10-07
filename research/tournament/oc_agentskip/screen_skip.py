"""oc_agentskip screening (rung level, phase 0): skip vs base per anchor year.

Frozen in PLAN.md: majors x traded rungs 2.5..5.0 fills with bar open in each
anchor year; outcome = table size * y_at_table_TP; daily sums by exit date;
per year sum / win rates / worst day / maxDD of daily-sum path; skipped-rung
share + skipped rungs' realised mean. PROMISING only if sum(skip)>=sum(base)
in >=4/5 years AND maxDD(skip)<=maxDD(base) in >=4/5 years.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
EXT = ROOT / "research/tournament/ext"

U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
R2_IDX = {k: r for r, k in enumerate(R2)}
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YCOL = {0.5: "y0.5", 1.0: "y1.0", 1.5: "y1.5"}


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def max_dd(cum):
    """Max peak-to-trough decline of a cumulative-sum path starting at 0."""
    c = np.asarray(cum, float)
    peak = np.maximum.accumulate(np.concatenate([[0.0], c]))[1:]
    return float(np.max(peak - c)) if len(c) else 0.0


def main():
    v294 = L("v294_agentskip_sc", RD / "v294/v294_wide_pool_exit_agent.py")
    v293 = v294.v293
    START = v293.START

    fills = pd.read_parquet(EXT / "fills_U_ext.parquet")
    fills["t_exit"] = pd.to_datetime(fills["t_exit"], utc=True)
    fills["t_fill"] = pd.to_datetime(fills["t_fill"], utc=True)
    # holding-bar open from standard-grid index j (causal year assignment)
    fills["T"] = [START + pd.Timedelta(hours=4 * int(j)) for j in fills["j"].to_numpy()]

    base = pd.read_parquet(HERE / "base_table_s0.parquet")
    skip = pd.read_parquet(HERE / "skip_table_s0.parquet")
    for t in (base, skip):
        t["T"] = pd.to_datetime(t["T"], utc=True)
    basek = base.set_index(["T", "sym", "rung"])[["size", "tp"]]
    skipk = skip.set_index(["T", "sym", "rung"])[["size", "tp"]]

    # screening universe: majors x traded rungs only
    uni = fills[fills.sym.isin(MAJORS) & fills["x1"].isin(R2)].copy()
    uni["rung"] = uni["x1"].map(R2_IDX).astype(int)
    years = {}
    for k, a0 in enumerate(ANCHORS):
        a1 = a0 + pd.Timedelta(days=365)
        years[k] = uni[(uni["T"] >= a0) & (uni["T"] < a1)].copy()
    dropped = {}
    per_year = {}
    for k, a0 in enumerate(ANCHORS):
        d = years[k]
        s0 = d.join(basek, on=["T", "sym", "rung"], rsuffix="_base")
        s0 = s0.rename(columns={"size": "size0", "tp": "tp0"})
        s0["size2"] = d.join(skipk, on=["T", "sym", "rung"])["size"].to_numpy()
        s0["tp2"] = d.join(skipk, on=["T", "sym", "rung"])["tp"].to_numpy()
        miss0 = int(s0[["size0", "tp0"]].isna().any(axis=1).sum())
        miss2 = int(s0[["size2", "tp2"]].isna().any(axis=1).sum())
        s = s0.dropna(subset=["size0", "tp0", "size2", "tp2"]).copy()
        dropped[k] = dict(n=int(len(d)), kept=int(len(s)), miss_base=miss0, miss_skip=miss2)
        for tag, (sc, tc) in (("base", ("size0", "tp0")), ("skip", ("size2", "tp2"))):
            ycol = s[tc].map(YCOL)
            out = np.array([s.iloc[i][ycol.iloc[i]] * s.iloc[i][sc] for i in range(len(s))],
                           dtype=float)
            s[f"out_{tag}"] = out
        # skip diagnostics: skipped fills' realised mean under BASE table
        skipped = s["size2"] == 0.0
        skip_share = float(skipped.mean()) if len(s) else float("nan")
        skipped_mean = float(s.loc[skipped, "out_base"].mean()) if int(skipped.sum()) else float("nan")
        skipped_n = int(skipped.sum())
        # daily sums by exit date
        s["day"] = s["t_exit"].dt.floor("D")
        stats = {}
        for tag in ("base", "skip"):
            out = s[f"out_{tag}"].to_numpy()
            daily = s.groupby("day")[f"out_{tag}"].sum().sort_index()
            dd = daily.to_numpy()
            cum = np.cumsum(dd)
            stats[tag] = dict(
                n=int(len(out)),
                sum=round(float(out.sum()), 6),
                fill_win=round(float(np.mean(out > 0)) if len(out) else float("nan"), 4),
                days=int(len(daily)),
                day_win=round(float(np.mean(dd > 0)) if len(dd) else float("nan"), 4),
                worst_day=round(float(dd.min()) if len(dd) else float("nan"), 6),
                maxDD=round(max_dd(cum), 6),
                mean_fill=round(float(out.mean()) if len(out) else float("nan"), 6),
            )
        stats["sum_diff_skip_base"] = round(stats["skip"]["sum"] - stats["base"]["sum"], 6)
        stats["dd_diff_skip_base"] = round(stats["skip"]["maxDD"] - stats["base"]["maxDD"], 6)
        stats["skip_not_lower_sum"] = bool(stats["skip"]["sum"] >= stats["base"]["sum"])
        stats["skip_not_worse_dd"] = bool(stats["skip"]["maxDD"] <= stats["base"]["maxDD"])
        per_year[str(k)] = dict(
            anchor=str(a0.date()), n=int(len(s)), **stats,
            skip_share=round(skip_share, 4), skipped_n=skipped_n,
            skipped_realised_mean=round(skipped_mean, 6) if skipped_mean == skipped_mean else None)
        print(k, a0.date(), "n", len(s), "sum_base", stats["base"]["sum"],
              "sum_skip", stats["skip"]["sum"], "dd_base", stats["base"]["maxDD"],
              "dd_skip", stats["skip"]["maxDD"], "skip_share", round(skip_share, 4),
              "skipped_mean", round(skipped_mean, 6) if skipped_mean == skipped_mean else None,
              flush=True)

    n_sum = sum(per_year[str(k)]["skip_not_lower_sum"] for k in range(5))
    n_dd = sum(per_year[str(k)]["skip_not_worse_dd"] for k in range(5))
    verdict = "PROMISING" if (n_sum >= 4 and n_dd >= 4) else "NOT PROMISING"
    build_info = json.loads((HERE / "build_info.json").read_text())
    results = dict(
        base_match=dict(size_match=build_info["size_match"], tp_match=build_info["tp_match"],
                        overlap_rows=build_info["overlap_rows"]),
        skip_thresh=build_info.get("skip_thresh", -0.002),
        skip_frac_tables=float((skip["size"] == 0.0).mean()),
        per_year=per_year, dropped=dropped,
        years_skip_not_lower_sum=int(n_sum), years_skip_not_worse_dd=int(n_dd),
        decision_rule="PROMISING only if sum(skip)>=sum(base) in >=4/5 years AND "
                      "maxDD(skip)<=maxDD(base) in >=4/5",
        verdict=verdict)
    (HERE / "results.json").write_text(json.dumps(results, indent=1))
    print("sum not-lower:", n_sum, "dd not-worse:", n_dd, "verdict:", verdict, flush=True)


if __name__ == "__main__":
    main()
