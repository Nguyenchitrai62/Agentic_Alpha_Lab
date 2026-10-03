"""Aggregate runs/dev_s*.json (agents ON, rebuilt shifted tables) next to the agents-OFF rows of
research/diagnostics/phase_offset_full/phase_offset_full.json. Writes phase_agents.json and table.md. Dev years only.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
OFF = json.loads((HERE.parents[0] / "phase_offset_full/phase_offset_full.json").read_text())
PIPES = ("v367", "v321")


def main():
    runs = []
    for f in sorted((HERE / "runs").glob("dev_s*.json")):
        runs += json.loads(f.read_text())["runs"]
    out, md = {}, []
    for pipe in PIPES:
        on = {r["shift"]: r for r in runs if r["pipe"] == pipe and r["tag"] == "full_agents_rebuilt"}
        off = {r["shift"]: r for r in OFF[f"dev/full_noagents/{pipe}"]["rows"]}
        dep = [r for r in runs if r["pipe"] == pipe and r["tag"] == "full_agents_deployed"]
        rows = []
        md += [f"\n### {pipe}", "| phase | agents | dev4 %/mo | 21-22 | 22-23 | 23-24 | 24-25 | DD 1m | book win (n) | all win | agent gain %/mo |",
               "|---|---|---|---|---|---|---|---|---|---|---|"]
        for s in range(4):
            a, b = on[s], off[s]
            ya = [y["net_pct"] for y in a["yearly"]]
            row = dict(shift=s, on=dict(monthly_dev4=a["monthly_dev4"], yearly=ya, dd_1m=a["dd_1m"], book_win=a["book_win"], book_trades=a["book_trades"],
                                        win_all=a["win_all"], rungs=a["rungs"], rung_win=a["rung_win"]),
                       off=dict(monthly_dev4=b["monthly_dev4"], yearly=b["yearly"], dd_1m=b["dd_1m"], book_win=b["book_win"], book_trades=b["book_trades"],
                                win_all=b["win_all"], rungs=b["rungs"], rung_win=b["rung_win"]),
                       gain=round(a["monthly_dev4"] - b["monthly_dev4"], 3))
            rows.append(row)
            for lab, x in (("off", row["off"]), ("ON", row["on"])):
                md.append(f"| s={s} | {lab} | {x['monthly_dev4']} | " + " | ".join(str(y) for y in x["yearly"]) +
                          f" | {x['dd_1m']} | {x['book_win']} ({x['book_trades']}) | {x['win_all']} | {row['gain'] if lab == 'ON' else ''} |")
        mean = lambda k, w: round(float(np.mean([r[w][k] for r in rows])), 3)
        summ = dict(mean_on=mean("monthly_dev4", "on"), mean_off=mean("monthly_dev4", "off"),
                    mean_gain=round(float(np.mean([r["gain"] for r in rows])), 3), gain_s0=rows[0]["gain"],
                    mean_gain_offphase=round(float(np.mean([r["gain"] for r in rows[1:]])), 3),
                    mean_dd_on=mean("dd_1m", "on"), mean_dd_off=mean("dd_1m", "off"),
                    mean_yearly_on=[round(float(np.mean([r["on"]["yearly"][k] for r in rows])), 2) for k in range(4)],
                    mean_yearly_off=[round(float(np.mean([r["off"]["yearly"][k] for r in rows])), 2) for k in range(4)],
                    mean_win_all_on=mean("win_all", "on"), mean_win_all_off=mean("win_all", "off"),
                    mean_book_win_on=mean("book_win", "on"), mean_book_win_off=mean("book_win", "off"),
                    s0_reproduction={r["tag"]: r["monthly_dev4"] for r in dep} | {"rebuilt": on[0]["monthly_dev4"]})
        md += [f"| mean 4 | off | {summ['mean_off']} | " + " | ".join(str(y) for y in summ["mean_yearly_off"]) + f" | {summ['mean_dd_off']} | {summ['mean_book_win_off']} | {summ['mean_win_all_off']} | |",
               f"| mean 4 | ON | {summ['mean_on']} | " + " | ".join(str(y) for y in summ["mean_yearly_on"]) + f" | {summ['mean_dd_on']} | {summ['mean_book_win_on']} | {summ['mean_win_all_on']} | {summ['mean_gain']} |",
               f"gain s=0 {summ['gain_s0']} | mean gain s=1..3 {summ['mean_gain_offphase']} | s=0 reproduction {summ['s0_reproduction']}"]
        out[pipe] = dict(rows=rows, summary=summ)
    (HERE / "phase_agents.json").write_text(json.dumps(out, indent=1))
    (HERE / "table.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
