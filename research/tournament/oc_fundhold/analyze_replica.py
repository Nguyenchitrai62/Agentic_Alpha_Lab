"""oc_fundhold replica gate scoring (CPU-only, no 1m).

Loads fills.parquet -> per-year per-arm stats, PASS_sum/DD legs (strict base
comparison), dSum per year + dSum5y vs +0.273 placebo gate, LOO, fee/funding
split, extension rates -> results.json. No engine run here (engine only for
gate-passing variants per PLAN.md).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd

import fundhold as X
from fund_rule import ANCH5

TMP = HERE / "tmp"
DSUM_GATE = 0.273


def daily_path(recs):
    if not recs:
        return 0.0, 0.0, 0.0, 0
    daily = {}
    for d, v in recs:
        daily[d] = daily.get(d, 0.0) + v
    days = sorted(daily)
    cum, peak, dd = 0.0, 0.0, 0.0
    for d in days:
        cum += daily[d]
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return float(sum(daily.values())), float(min(daily.values())), float(-dd), len(days)


def arm_stats(df, rcol, xcol, hcol):
    per_year = []
    for yi in range(5):
        sub = df[df["y"] == yi]
        n = len(sub)
        if n:
            yv = sub[rcol].to_numpy(float)
            w = sub["w"].to_numpy(float)
            wy = w * yv
            recs = list(zip(sub[xcol].tolist(), wy.tolist()))
            S, Wd, DD, nd = daily_path(recs)
            win = float((yv > 0).mean())
            mean = float(yv.mean())
            to = float((sub[hcol].to_numpy() == "time").mean())
            eff = float(S / DD) if DD > 0 else float("nan")
            fee = float((w * sub[hcol].map(X.fee_for).to_numpy(float)).sum())
        else:
            S, Wd, DD, nd, win, mean, to, eff, fee = 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, float("nan"), 0.0
        per_year.append({"year": ANCH5[yi], "n": int(n), "mean": mean,
                         "win_rate": win, "sum": S, "timeout_share": to,
                         "worst_day": Wd, "max_dd": DD, "efficiency": eff,
                         "ndays": nd, "fee_wsum": fee})
    return per_year


def fund_wsum(df, vcol: str) -> list[float]:
    """Aggregate w*fund per year for arm vcol in {base, v1, v2} (frozen flags)."""
    out = []
    for yi in range(5):
        sub = df[df["y"] == yi]
        tot = 0.0
        if len(sub):
            for _, r in sub.iterrows():
                if vcol == "base":
                    x, how = int(r["base_x"]), r["base_how"]
                    fund = X.FUND if (bool(r["settle_mid"]) and x == 240) else 0.0
                elif vcol == "v1":
                    x, how = int(r["v1_x"]), r["v1_how"]
                    if bool(r["v1_ext"]):
                        fund = (X.FUND if r["mid1"] else 0.0) \
                            + (X.FUND if (r["mid2"] and x >= 480) else 0.0) \
                            + (X.FUND if (r["final"] and x == 720) else 0.0)
                    else:
                        fund = X.FUND if (bool(r["settle_mid"]) and x == 240) else 0.0
                else:
                    x, how = int(r["v2_x"]), r["v2_how"]
                    if bool(r["v2_ext"]):
                        fund = (X.FUND if r["mid1"] else 0.0) \
                            + (X.FUND if (r["mid2"] and x >= 480) else 0.0) \
                            + (X.FUND if (r["final"] and x == 720) else 0.0)
                    else:
                        fund = X.FUND if (bool(r["settle_mid"]) and x == 240) else 0.0
                tot += float(r["w"]) * fund
        out.append(tot)
    return out


def main():
    df = pd.read_parquet(HERE / "fills.parquet")
    assert len(df) > 0, "empty fills ledger"
    thresholds = json.loads((TMP / "thresholds.json").read_text())
    per_year = {
        "BASE": arm_stats(df, "base_ret", "xd_base", "base_how"),
        "V1": arm_stats(df, "v1_ret", "xd_v1", "v1_how"),
        "V2": arm_stats(df, "v2_ret", "xd_v2", "v2_how"),
    }
    funds = {v: fund_wsum(df, v.lower()) for v in ("BASE", "V1", "V2")}
    for v in ("BASE", "V1", "V2"):
        for yi in range(5):
            per_year[v][yi]["fund_wsum"] = funds[v][yi]
    # extension rates: share of base timeouts extended
    ext_rate = {}
    for v, ecol in (("V1", "v1_ext"), ("V2", "v2_ext")):
        rates = []
        for yi in range(5):
            sub = df[(df["y"] == yi) & (df["base_how"] == "time")]
            rates.append({"year": ANCH5[yi],
                          "n_timeouts": int(len(sub)),
                          "ext_share": float(sub[ecol].mean()) if len(sub) else 0.0})
        ext_rate[v] = rates
    # gate
    gate = {}
    for v, rcol in (("V1", "v1_ret"), ("V2", "v2_ret")):
        scol = [f"{v.lower()}_ret", "base_ret"]
        dsum_y = [round(per_year[v][yi]["sum"] - per_year["BASE"][yi]["sum"], 6)
                  for yi in range(5)]
        dsum5y = round(float(sum(dsum_y)), 6)
        sum_pass = sum(1 for yi in range(5)
                       if per_year[v][yi]["sum"] > per_year["BASE"][yi]["sum"])
        dd_pass = sum(1 for yi in range(5)
                      if per_year[v][yi]["max_dd"] <= per_year["BASE"][yi]["max_dd"])
        loo = []
        for left in range(5):
            d = sum(per_year[v][yi]["sum"] - per_year["BASE"][yi]["sum"]
                    for yi in range(5) if yi != left)
            loo.append({"left_out": ANCH5[left], "diff_loo": d,
                        "higher": bool(d > 0)})
        promising = bool(sum_pass >= 4 and dd_pass >= 4 and dsum5y >= DSUM_GATE)
        gate[v] = {"dsum_yearly": dsum_y, "dsum5y": dsum5y,
                   "dsum5y_gate": DSUM_GATE,
                   "years_sum_higher": int(sum_pass),
                   "years_dd_not_worse": int(dd_pass),
                   "loo_higher": int(sum(r["higher"] for r in loo)),
                   "loo": loo, "promising": promising}
    engine_run = [v for v in ("V1", "V2") if gate[v]["promising"]]
    out = {"config": {"arms": ["BASE", "V1_p70", "V2_p50"],
                       "grid": "single 4h phase from 2020-08-01",
                       "bars": "open in [2021-09-24, 2026-09-24)",
                       "rungs": list(X.RUNGS), "live": [X.LIVE_A, X.LIVE_B],
                       "maker": X.MAKER, "taker": X.TAKER, "fund_long": X.FUND,
                       "gate": "PASS_sum>=4/5 AND PASS_dd>=4/5 AND dSum5y>=+0.273",
                       "note": "all 5 years are research data; PROMISING needs prospective validation"},
             "thresholds": thresholds,
             "n_fills": int(len(df)),
             "fills_per_coin": {s: int((df["sym"] == s).sum()) for s in sorted(df["sym"].unique().tolist())},
             "n_base_timeouts": int((df["base_how"] == "time").sum()),
             "per_year": per_year,
             "ext_rate": ext_rate,
             "gate": gate,
             "engine_run_variants": engine_run,
             "engine_not_run": len(engine_run) == 0}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({v: gate[v] for v in ("V1", "V2")}, indent=1))
    print("engine_run_variants:", engine_run if engine_run else "NONE (no engine per PLAN)")


if __name__ == "__main__":
    main()
