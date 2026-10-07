"""oc_cooldown run: per-coin 24h dip cooldown after a stop-out.

Universe: majors x R2 depths {2.5,3.0,3.5,4.0} from
research/tournament/oc_ddanat17/rungs_s0.parquet (exact engine rung stream,
weights/sizing included). A rung of coin c with holding-bar open B is COOLED
(removed) iff a rung_sl stop exit of coin c exists with B in (s, s+24h].
See PLAN.md. Parquet-only, one process, no 1m read.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RUNG_S0 = HERE.parent / "oc_ddanat17" / "rungs_s0.parquet"
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
R2_DEPTHS = (2.5, 3.0, 3.5, 4.0)
COOLDOWN = pd.Timedelta(hours=24)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
DAY365 = pd.Timedelta(days=365)


def year_of(bt):
    for i in range(5):
        if ANCHORS[i] <= bt < ANCHORS[i] + DAY365:
            return i
    return None


def apply_cooldown(df: pd.DataFrame, cooldown: pd.Timedelta) -> pd.Series:
    """Boolean Series: True = rung is COOLED (removed). Causal: bar open B uses
    only stop exits s with s < B <= s + cooldown (same coin)."""
    removed = pd.Series(False, index=df.index)
    cd_ns = cooldown.value
    for sym, g in df.groupby("symbol"):
        stops = np.sort(pd.DatetimeIndex(g.loc[g["exit"] == "rung_sl", "exit_t"]).asi8)
        if len(stops) == 0:
            continue
        b = pd.DatetimeIndex(g["bar_start"]).asi8
        j = np.searchsorted(stops, b, side="left")  # stops[j-1] = latest stop < B
        has = j > 0
        cool = np.zeros(len(b), bool)
        cool[has] = stops[j[has] - 1] >= b[has] - cd_ns
        removed.loc[g.index] = cool
    return removed


def daily_stats(losses: pd.Series, dates: pd.Series) -> dict:
    """worst_day / maxDD of the exit-date daily-sum curve starting at 0."""
    if len(losses) == 0:
        return {"worst_day": 0.0, "max_dd": 0.0, "ndays": 0}
    daily = pd.Series(np.asarray(losses, float)).groupby(
        pd.Series(pd.to_datetime(dates).dt.date)).sum().sort_index()
    cum = daily.cumsum().to_numpy()
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    dd = float(np.min(cum - peak)) if len(cum) else 0.0
    return {"worst_day": float(daily.min()), "max_dd": dd, "ndays": int(len(daily))}


def main():
    r = pd.read_parquet(RUNG_S0)
    r["bar_start"] = pd.to_datetime(r["bar_start"], utc=True)
    r["exit_t"] = pd.to_datetime(r["exit_t"], utc=True)
    assert set(r["symbol"].unique()) <= set(MAJORS), r["symbol"].unique()
    assert (r["exit"].isin(("rung_sl", "rung_tp", "rung_timeout"))).all()
    chk = float((r["loss"] - r["weight"] * r["ret"]).abs().max())
    assert chk < 1e-9, chk

    n_d5 = int((~r["depth"].isin(R2_DEPTHS)).sum())
    u = r[r["depth"].isin(R2_DEPTHS)].copy()
    u["y"] = u["bar_start"].map(year_of)
    n_out = int(u["y"].isna().sum())
    u = u[u["y"].notna()].copy()
    u["y"] = u["y"].astype(int)
    n_stops = int((u["exit"] == "rung_sl").sum())

    u["removed"] = apply_cooldown(u, COOLDOWN)
    kept = u[~u["removed"]].copy()
    rem = u[u["removed"]].copy()

    per_year = []
    for yi in range(5):
        sub = u[u["y"] == yi]
        k = sub[~sub["removed"]]
        d = sub[sub["removed"]]
        s_base = float(sub["loss"].sum())
        s_cool = float(k["loss"].sum())
        st_base = daily_stats(sub["loss"], sub["exit_t"])
        st_cool = daily_stats(k["loss"], k["exit_t"])
        if s_base > 0:
            retain_ok = s_cool >= 0.90 * s_base
        else:
            retain_ok = s_cool >= s_base
        per_year.append({
            "year": ANCHORS[yi].date().isoformat(),
            "n_total": int(len(sub)), "n_removed": int(len(d)), "n_kept": int(len(k)),
            "sum_base": s_base, "sum_cool": s_cool,
            "sum_removed": float(d["loss"].sum()) if len(d) else 0.0,
            "win_kept": float((k["ret"] > 0).mean()) if len(k) else 0.0,
            "win_removed": float((d["ret"] > 0).mean()) if len(d) else 0.0,
            "worst_day_base": st_base["worst_day"], "maxdd_base": st_base["max_dd"],
            "worst_day_cool": st_cool["worst_day"],
            "maxdd_cool": st_cool["max_dd"],
            "maxdd_improves": bool(st_cool["max_dd"] > st_base["max_dd"]),
            "sum_retained": bool(retain_ok),
        })

    st_fb = daily_stats(u["loss"], u["exit_t"])
    st_fc = daily_stats(kept["loss"], kept["exit_t"])
    full = {"n_total": int(len(u)), "n_removed": int(len(rem)),
            "sum_base": float(u["loss"].sum()), "sum_cool": float(kept["loss"].sum()),
            "win_kept": float((kept["ret"] > 0).mean()),
            "win_removed": float((rem["ret"] > 0).mean()) if len(rem) else 0.0,
            "worst_day_base": st_fb["worst_day"], "maxdd_base": st_fb["max_dd"],
            "worst_day_cool": st_fc["worst_day"], "maxdd_cool": st_fc["max_dd"]}
    n_dd = sum(1 for p in per_year if p["maxdd_improves"])
    n_rt = sum(1 for p in per_year if p["sum_retained"])
    decision = {"years_maxdd_improves": int(n_dd), "years_sum_retained": int(n_rt),
                "promising": bool(n_dd >= 4 and n_rt >= 4)}
    out = {"config": {"ledger": "research/tournament/oc_ddanat17/rungs_s0.parquet",
                       "universe": "majors x R2 depths [2.5,3.0,3.5,4.0]",
                       "cooldown": "24h", "rule": "bar open B cooled iff stop s of same coin with B in (s, s+24h]",
                       "years": "bar_start in [anchor, anchor+365d), anchors 2021-09-24..2025-09-24",
                       "pnl": "loss = weight*ret (engine-sized, fees/funding in engine)",
                       "win": "ret > 0 strictly", "daily": "exit-date sums, curve from 0 per year"},
             "excluded_depth5_n": n_d5, "rows_outside_years": n_out,
             "n_universe": int(len(u)), "n_stop_triggers": n_stops,
             "per_year": per_year, "full": full, "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"excluded_d5": n_d5, "outside": n_out, "universe": len(u),
                      "stops": n_stops, "removed": int(len(rem)), **decision}, indent=1))
    for p in per_year:
        print(p["year"], "n=%d rem=%d" % (p["n_total"], p["n_removed"]),
              "base=%.4f cool=%.4f" % (p["sum_base"], p["sum_cool"]),
              "dd %.4f->%.4f" % (p["maxdd_base"], p["maxdd_cool"]),
              "impr" if p["maxdd_improves"] else "no",
              "ret" if p["sum_retained"] else "LOST>10%")


if __name__ == "__main__":
    main()
