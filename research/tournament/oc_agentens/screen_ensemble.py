"""oc_agentens screening (rung level, phase 0): ensemble vs deployed + singles.

Frozen in PLAN.md: majors x traded rungs 2.5..5.0 fills with bar open in each
anchor year; outcome = table size * y_at_table_TP; daily sums by exit date;
per year sum / win rates / worst day / maxDD of daily-sum path for V in
{S0, S101, S202, S303, S404, ENS}; dispersion of the 5 singles.
PROMISING only if sum(ENS)>=sum(S0) in >=3/5 years AND min year sum(ENS) >
min year sum(S0).
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
SEEDS = (0, 101, 202, 303, 404)
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
    v294 = L("v294_agentens_sc", RD / "v294/v294_wide_pool_exit_agent.py")
    v293 = v294.v293
    START = v293.START

    fills = pd.read_parquet(EXT / "fills_U_ext.parquet")
    fills["t_exit"] = pd.to_datetime(fills["t_exit"], utc=True)
    fills["t_fill"] = pd.to_datetime(fills["t_fill"], utc=True)
    fills["T"] = [START + pd.Timedelta(hours=4 * int(j)) for j in fills["j"].to_numpy()]

    tabs = {}
    for S in SEEDS:
        t = pd.read_parquet(HERE / f"seed_table_s{S}_s0.parquet")
        t["T"] = pd.to_datetime(t["T"], utc=True)
        tabs[f"S{S}"] = t.set_index(["T", "sym", "rung"])[["size", "tp"]]
    te = pd.read_parquet(HERE / "ens_table_s0.parquet")
    te["T"] = pd.to_datetime(te["T"], utc=True)
    tabs["ENS"] = te.set_index(["T", "sym", "rung"])[["size", "tp"]]
    tags = [f"S{S}" for S in SEEDS] + ["ENS"]

    uni = fills[fills.sym.isin(MAJORS) & fills["x1"].isin(R2)].copy()
    uni["rung"] = uni["x1"].map(R2_IDX).astype(int)
    years = {}
    for k, a0 in enumerate(ANCHORS):
        a1 = a0 + pd.Timedelta(days=365)
        years[k] = uni[(uni["T"] >= a0) & (uni["T"] < a1)].copy()

    per_year, dropped = {}, {}
    for k, a0 in enumerate(ANCHORS):
        d = years[k]
        s = d.copy()
        miss = {}
        for tag in tags:
            j = d.join(tabs[tag], on=["T", "sym", "rung"])
            s[f"size_{tag}"] = j["size"].to_numpy()
            s[f"tp_{tag}"] = j["tp"].to_numpy()
            miss[tag] = int(j[["size", "tp"]].isna().any(axis=1).sum())
        s = s.dropna(subset=[f"size_{t}" for t in tags] + [f"tp_{t}" for t in tags]).copy()
        dropped[k] = dict(n=int(len(d)), kept=int(len(s)), **{f"miss_{t}": m for t, m in miss.items()})
        for tag in tags:
            ycol = s[f"tp_{tag}"].map(YCOL)
            out = np.array([s.iloc[i][ycol.iloc[i]] * s.iloc[i][f"size_{tag}"] for i in range(len(s))],
                           dtype=float)
            s[f"out_{tag}"] = out
        s["day"] = s["t_exit"].dt.floor("D")
        stats = {}
        for tag in tags:
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
        singles = [f"S{S}" for S in SEEDS]
        sums = np.array([stats[t]["sum"] for t in singles])
        stats["ens_ge_s0"] = bool(stats["ENS"]["sum"] >= stats["S0"]["sum"])
        stats["singles"] = dict(
            min=round(float(sums.min()), 6), max=round(float(sums.max()), 6),
            range=round(float(sums.max() - sums.min()), 6),
            std=round(float(sums.std(ddof=1)) if len(sums) > 1 else 0.0, 6),
            mean=round(float(sums.mean()), 6),
            best_seed=singles[int(np.argmax(sums))],
            s0_rank=int(1 + (sums > stats["S0"]["sum"]).sum()),
            s0_minus_mean=round(float(stats["S0"]["sum"] - sums.mean()), 6),
        )
        per_year[str(k)] = dict(anchor=str(a0.date()), n=int(len(s)), **stats)
        print(k, a0.date(), "n", len(s),
              "s0", stats["S0"]["sum"], "ens", stats["ENS"]["sum"],
              "singles", [stats[t]["sum"] for t in singles], flush=True)

    n_ens_ge = sum(per_year[str(k)]["ens_ge_s0"] for k in range(5))
    s0_sums = np.array([per_year[str(k)]["S0"]["sum"] for k in range(5)])
    ens_sums = np.array([per_year[str(k)]["ENS"]["sum"] for k in range(5)])
    worst_s0, worst_ens = float(s0_sums.min()), float(ens_sums.min())
    worst_better = bool(worst_ens > worst_s0)
    verdict = "PROMISING" if (n_ens_ge >= 3 and worst_better) else "NOT PROMISING"
    build_info = json.loads((HERE / "build_info.json").read_text())
    results = dict(
        s0_match=build_info["s0_vs_v0"],
        agreement_vs_s0=build_info["agreement_vs_s0"],
        per_year=per_year, dropped=dropped,
        years_ens_ge_s0=int(n_ens_ge),
        worst_year_sum=dict(s0=round(worst_s0, 6), ens=round(worst_ens, 6),
                            better=worst_better),
        decision_rule="PROMISING only if sum(ENS)>=sum(S0) in >=3/5 years AND min yearly sum(ENS) > min yearly sum(S0)",
        verdict=verdict)
    (HERE / "results.json").write_text(json.dumps(results, indent=1))
    print("ens>=s0 years:", n_ens_ge, "worst s0/ens:", worst_s0, worst_ens,
          "verdict:", verdict, flush=True)


if __name__ == "__main__":
    main()
