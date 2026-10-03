"""Aggregate runs/*.json of phase_offset_full.py: per pipeline x phase table, 4-phase mean, equal-capital 4-phase mix (daily returns
averaged, i.e. daily rebalanced), daily-return correlations. Equity of each phase sampled at 00:00 UTC (last closed bar <= midnight).
Writes phase_offset_full.json and prints a markdown table. Dev years only (2021-09-24 .. 2025-09-23) plus the dip-only pre period.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
EXPECT = {"v367": 6.015, "v362": 6.392, "v340": 5.23, "v321": 7.079}
ANCH = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")


def daily(eq_end: dict, d0, d1):
    s = pd.Series(eq_end)
    s.index = pd.to_datetime(s.index, utc=True)
    s = s.sort_index()
    days = pd.date_range(d0, d1, freq="1D", tz="UTC")
    v = s.reindex(s.index.union(days)).ffill().reindex(days)
    return v.fillna(1.0) / (v.fillna(1.0).iloc[0])


def mix_stats(cols, D, anchors, d0, d1):
    r = D[cols].pct_change().dropna()
    mix = pd.concat([pd.Series([1.0], index=[D.index[0]]), (1 + r.mean(axis=1)).cumprod()])
    out = dict(total_pct=round(100 * (mix.iloc[-1] - 1), 2), dd_daily=round(100 * float((1 - mix / mix.cummax()).max()), 2))
    months = (d1 - d0).days / (365 / 12)
    out["monthly_geo"] = round(100 * (mix.iloc[-1] ** (1 / months) - 1), 3)
    if anchors:
        yrs = []
        for a in anchors:
            a0 = pd.Timestamp(a, tz="UTC")
            a1 = min(a0 + pd.Timedelta(days=365), d1)
            yrs.append(round(100 * (float(mix.asof(a1)) / float(mix.asof(a0)) - 1), 2))
        out["yearly"] = yrs
        out["monthly_dev4"] = round(100 * (np.prod([1 + y / 100 for y in yrs]) ** (1 / 48) - 1), 3)
    return out


def main():
    runs = []
    for f in sorted((HERE / "runs").glob("*.json")):
        runs += json.loads(f.read_text())["runs"]
    res, lines = {}, []
    # pre: nothing trades before SOLUSDT has 1m data (2020-09-14; the engine skips a bar unless every coin has an open), so the
    # pre monthly figures run over the traded span 2020-09-14 .. 2021-09-24 (12.3 months)
    for period, d0, d1, anchors in (("dev", "2021-09-24", "2025-09-24", ANCH), ("pre", "2020-09-14", "2021-09-24", ())):
        d0, d1 = pd.Timestamp(d0, tz="UTC"), pd.Timestamp(d1, tz="UTC")
        for tag in ("full_noagents", "diponly_noagents", "full_agents", "full_noagents_stale4h"):
            for pipe in EXPECT:
                rs = sorted([r for r in runs if r["pipe"] == pipe and r["tag"] == tag and r["period"] == period], key=lambda r: r["shift"])
                if not rs:
                    continue
                key = f"{period}/{tag}/{pipe}"
                D = pd.concat({f"s{r['shift']}": daily(r["eq_end"], d0, d1) for r in rs}, axis=1)
                ent = dict(rows=[{k: r.get(k) for k in ("shift", "monthly_dev4", "monthly_geo", "total_pct", "dd_1m", "dd_4h", "book_trades", "book_win",
                                                          "rungs", "rung_win", "win_all", "first_traded_bar", "h1_2020_pct", "h2_2021_pct")}
                                 | {"yearly": [y["net_pct"] for y in r["yearly"]]} for r in rs])
                for r, row in zip(rs, ent["rows"]):
                    if period == "pre":
                        row["monthly_geo"] = round(100 * ((1 + r["total_pct"] / 100) ** (1 / ((d1 - d0).days / (365 / 12))) - 1), 3)
                        r["monthly_geo"] = row["monthly_geo"]
                    e = D[f"s{r['shift']}"]
                    row["dd_daily"] = round(100 * float((1 - e / e.cummax()).max()), 2)
                if len(rs) == 4:
                    mk = "monthly_dev4" if period == "dev" else "monthly_geo"
                    ent["mean_4_phases"] = dict(monthly=round(float(np.mean([r[mk] for r in rs])), 3), dd_1m=round(float(np.mean([r["dd_1m"] for r in rs])), 2),
                                                min_monthly=min(r[mk] for r in rs), max_monthly=max(r[mk] for r in rs))
                    if anchors:
                        ent["mean_4_phases"]["yearly"] = [round(float(np.mean([r["yearly"][k]["net_pct"] for r in rs])), 2) for k in range(4)]
                    ent["mix_4_phases"] = mix_stats(list(D.columns), D, anchors, d0, d1)
                    ent["corr_daily"] = D.pct_change().dropna().corr().round(3).to_dict()
                    cc = D.pct_change().dropna().corr().to_numpy()
                    ent["corr_mean_offdiag"] = round(float(cc[~np.eye(4, dtype=bool)].mean()), 3)
                if tag == "full_agents":
                    ent["expected_history_tm_dev4"] = EXPECT[pipe]
                    ent["diff"] = round(rs[0]["monthly_dev4"] - EXPECT[pipe], 4)
                res[key] = ent
    (HERE / "phase_offset_full.json").write_text(json.dumps(res, indent=1, default=str))
    # markdown
    for key, ent in res.items():
        period = key.split("/")[0]
        print(f"\n### {key}")
        if period == "dev":
            print("| phase | dev4 %/mo | 21-22 | 22-23 | 23-24 | 24-25 | DD 1m | DD daily | book win (n) | all win |")
            print("|---|---|---|---|---|---|---|---|---|---|")
            for r in ent["rows"]:
                bw = f"{r['book_win']} ({r['book_trades']})" if r["book_trades"] else "-"
                print(f"| s={r['shift']} | {r['monthly_dev4']} | " + " | ".join(str(y) for y in r["yearly"]) + f" | {r['dd_1m']} | {r['dd_daily']} | {bw} | {r['win_all']} |")
        else:
            print("| phase | %/mo | total | H2-2020 | 2021 to 09-23 | DD 1m | DD daily | first traded bar |")
            print("|---|---|---|---|---|---|---|---|")
            for r in ent["rows"]:
                print(f"| s={r['shift']} | {r['monthly_geo']} | {r['total_pct']} | {r['h1_2020_pct']} | {r['h2_2021_pct']} | {r['dd_1m']} | {r['dd_daily']} | {r['first_traded_bar']} |")
        if "mean_4_phases" in ent:
            m, x = ent["mean_4_phases"], ent["mix_4_phases"]
            print(f"| mean 4 phases | {m['monthly']} | {m.get('yearly', '')} | DD1m {m['dd_1m']} |")
            print(f"| 4-phase mix (daily rebal.) | {x.get('monthly_dev4', x['monthly_geo'])} | {x.get('yearly', '')} | DD daily {x['dd_daily']} | corr {ent['corr_mean_offdiag']} |")
        if "diff" in ent:
            print(f"sanity: dev4 {ent['rows'][0]['monthly_dev4']} vs history_tm {ent['expected_history_tm_dev4']} (diff {ent['diff']})")


if __name__ == "__main__":
    main()
