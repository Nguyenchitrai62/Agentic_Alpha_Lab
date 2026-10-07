"""oc_frontier: collect v399..v423 reset-metric rows + Pareto frontiers.

Reads only small JSON/log files (no 1m data, one process, RAM << 1 GB).
Outputs results.json + frontier.png in this folder.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
R2 = ROOT / "research" / "parallel" / "rounds" / "parallel-20260906-r2"
VERSIONS = [f"v{n}" for n in range(399, 424)]
FULLPATH_RE = re.compile(r"^(\S+)\s+full-path DD\s+([0-9.]+)", re.M)
DEPLOY = ("v411", "R2B1D17BF")


def pareto(keys: list[str], r: dict[str, float], dd: dict[str, float]) -> list[str]:
    """Non-dominated set: maximise R, minimise DD (ties on identical point kept)."""
    out = []
    for a in keys:
        dominated = False
        for b in keys:
            if b == a:
                continue
            if r[b] >= r[a] and dd[b] <= dd[a] and (r[b] > r[a] or dd[b] < dd[a]):
                dominated = True
                break
        if not dominated:
            out.append(a)
    return sorted(out, key=lambda k: (-r[k], dd[k]))


def main() -> None:
    rows: list[dict] = []
    mismatches: list[str] = []
    for v in VERSIONS:
        res = json.loads((R2 / v / f"{v}_result.json").read_text())
        man = json.loads((R2 / v / "result_manifest.json").read_text())
        audited = bool(man.get("audit", {}).get("passed", False))
        log = (R2 / v / "run.log").read_text(errors="replace")
        logged = {m.group(1): float(m.group(2)) for m in FULLPATH_RE.finditer(log)}
        for row, d in res.get("rows", {}).items():
            years = [[float(a), float(b)] for a, b in d["years"]]
            dd_yearly = float(d["DD"])
            r5 = float(d["R"])
            w = float(d["W"])
            recent_r = float(years[4][0])
            jf = d.get("full_path_dd")
            jf = None if jf is None else float(jf)
            lf = logged.get(row)
            if lf is not None and jf is not None and abs(lf - jf) > 1e-9:
                mismatches.append(f"{v}/{row}: log {lf} != json {jf}")
            full = lf if lf is not None else jf
            rows.append({
                "version": v, "row": row, "R": r5, "W": w,
                "dd_yearly": dd_yearly, "full_path_dd": full,
                "recent_r": recent_r, "years": years,
                "audited": audited,
            })
    rows.sort(key=lambda d: (d["version"], d["row"]))

    key = lambda d: d["version"] + "/" + d["row"]  # noqa: E731
    rmap = {key(d): d["R"] for d in rows}
    ymap = {key(d): d["dd_yearly"] for d in rows if d["dd_yearly"] is not None}
    fmap = {key(d): d["full_path_dd"] for d in rows if d["full_path_dd"] is not None}
    frontier_yearly = pareto(list(ymap), rmap, ymap)
    frontier_full = pareto(list(fmap), rmap, fmap)
    dd15_yearly = sorted([k for k in ymap if ymap[k] < 15.0])
    dd15_full = sorted([k for k in fmap if fmap[k] < 15.0])

    out = {
        "meta": {
            "versions": VERSIONS,
            "n_rows": len(rows),
            "deployment_pick": f"{DEPLOY[0]}/{DEPLOY[1]}",
            "definitions": {
                "R": "5y geometric %/month (result.json rows[row].R)",
                "W": "worst single-year %/month (rows[row].W)",
                "dd_yearly": "max yearly DD (rows[row].DD = max years[i][1])",
                "full_path_dd": "run.log '<row> full-path DD x', null if absent in log+JSON",
                "recent_r": "most-recent-year R = years[4][0] (anchor 2025-09-24)",
                "audited": "result_manifest.json audit.passed",
            },
            "log_json_mismatches": mismatches,
        },
        "rows": rows,
        "frontier_yearly": frontier_yearly,
        "frontier_fullpath": frontier_full,
        "dd15_yearly": dd15_yearly,
        "dd15_fullpath": dd15_full,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))

    # Scatter: R vs max yearly DD; frontier highlighted; deploy pick marked.
    fig, ax = plt.subplots(figsize=(8, 5.5))
    xs = [d["R"] for d in rows]
    ys = [d["dd_yearly"] for d in rows]
    ax.scatter(xs, ys, s=18, c="grey", alpha=0.7, label="all rows")
    fset = set(frontier_yearly)
    fx = [rmap[k] for k in frontier_yearly]
    fy = [ymap[k] for k in frontier_yearly]
    ax.scatter(fx, fy, s=55, facecolors="none", edgecolors="blue", linewidths=1.4,
               label="Pareto (R up, yearly DD down)")
    dk = f"{DEPLOY[0]}/{DEPLOY[1]}"
    ax.scatter([rmap[dk]], [ymap[dk]], s=120, marker="*",
               c="red", edgecolors="black", linewidths=0.8, label="deploy R2B1D17BF (v411)", zorder=5)
    ax.annotate(dk, (rmap[dk], ymap[dk]), textcoords="offset points",
                xytext=(8, 6), fontsize=8, color="red")
    ax.set_xlabel("R: 5y geometric %/month")
    ax.set_ylabel("max yearly DD (%)")
    ax.set_title("oc_frontier v399..v423: R vs max yearly DD")
    ax.legend(fontsize=8, loc="best")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(HERE / "frontier.png", dpi=130)
    plt.close(fig)
    print(f"rows={len(rows)} frontier_yearly={len(frontier_yearly)} "
          f"frontier_full={len(frontier_full)} mismatches={len(mismatches)} "
          f"dd15_yearly={len(dd15_yearly)} dd15_full={len(dd15_full)}")


if __name__ == "__main__":
    main()
