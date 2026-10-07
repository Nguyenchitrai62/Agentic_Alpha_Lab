"""oc_cooldown POST-HOC sensitivity (not pre-registered; see REPORT.md notes).

Same 24h rule, but self-consistent triggers: a stop fires as a trigger only
if its own rung was KEPT (a cooled rung is never placed, so its stop can never
happen). Implemented by processing each coin's rungs in bar-open order and
growing the stop set from kept rungs only. Compares against results.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
from run_cooldown import ANCHORS, COOLDOWN, R2_DEPTHS, daily_stats, year_of  # noqa: E402

RUNG_S0 = HERE.parent / "oc_ddanat17" / "rungs_s0.parquet"


def iterative_mask(df: pd.DataFrame) -> pd.Series:
    removed = pd.Series(False, index=df.index)
    for _, g in df.groupby("symbol"):
        g = g.sort_values("bar_start")
        stops: list = []
        for ix, row in g.iterrows():
            b = row["bar_start"]
            cool = any(s < b <= s + COOLDOWN for s in stops)
            removed.loc[ix] = cool
            if not cool and row["exit"] == "rung_sl":
                stops.append(row["exit_t"])
    return removed


def main():
    r = pd.read_parquet(RUNG_S0)
    r["bar_start"] = pd.to_datetime(r["bar_start"], utc=True)
    r["exit_t"] = pd.to_datetime(r["exit_t"], utc=True)
    u = r[r["depth"].isin(R2_DEPTHS)].copy()
    u["y"] = u["bar_start"].map(year_of)
    u = u[u["y"].notna()].copy()
    u["removed_it"] = iterative_mask(u)
    prim = json.load(open(HERE / "results.json"))
    print("year | n_removed_prim -> iter | sum_cool_prim -> iter | dd_cool_prim -> iter")
    for yi in range(5):
        sub = u[u["y"] == yi]
        # primary mask recomputed identically to run_cooldown
        from run_cooldown import apply_cooldown
        pm = apply_cooldown(sub, COOLDOWN)
        k_p, k_i = sub[~pm], sub[~sub["removed_it"]]
        sb = float(sub["loss"].sum())
        sc_p, sc_i = float(k_p["loss"].sum()), float(k_i["loss"].sum())
        dd_p = daily_stats(k_p["loss"], k_p["exit_t"])["max_dd"]
        dd_i = daily_stats(k_i["loss"], k_i["exit_t"])["max_dd"]
        dd_b = daily_stats(sub["loss"], sub["exit_t"])["max_dd"]
        pp = prim["per_year"][yi]
        assert abs(sc_p - pp["sum_cool"]) < 1e-9 and abs(dd_p - pp["maxdd_cool"]) < 1e-12
        impr_i = dd_i > dd_b
        ret_i = (sc_i >= 0.90 * sb) if sb > 0 else (sc_i >= sb)
        print(f"{ANCHORS[yi].date()} | {int(pm.sum())} -> {int(sub['removed_it'].sum())} | "
              f"{sc_p:.4f} -> {sc_i:.4f} | {dd_p:.4f} -> {dd_i:.4f} "
              f"({'impr' if impr_i else 'no'},{'ret' if ret_i else 'LOST>10%'})")
    print("phantom-trigger-only rungs un-cooled:",
          int(((u['removed_it'] == False) & (apply_cooldown(u, COOLDOWN))).sum()))


if __name__ == "__main__":
    main()
