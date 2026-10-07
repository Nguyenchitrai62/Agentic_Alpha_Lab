"""Build the G2-family return-vs-drawdown map.

Copies numbers ONLY from cited reports (see SOURCES below) into
frontier_table.csv and frontier.png. No engine run, no recomputation:
dev4 aggregates are included only where the source report prints them,
otherwise left blank.
"""
import csv
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "frontier_table.csv")
PNG = os.path.join(HERE, "frontier.png")

# id, label, kind(dial/signal/overlay), adopted, R5y, dev4_R, dev4_W,
# recent_R, max_yearly_DD, full_DD, audit, source
# Sources (report lines quoted by worker extraction):
#  G2: v421_audit/COMPARISON.md:72,75; ROBUST.md:21-27,87; oc_kpi_g2/REPORT.md:56-60
#  D17BF: v411_audit/COMPARISON.md:70,73; ROBUST.md:36-44,102
#  D13BF: v424_audit/COMPARISON.md:76,79; comparison.json:71-100; oc_kpi_d13/REPORT.md:58-62,70-77
#  G2K20: v422_audit/COMPARISON.md:77,80; oc_g2k20robust/ROBUST.md:19-28,30
#  G2+carry: oc_carrycompound/REPORT.md:19-27; results.json:94-102
#  G2K20+carry: oc_g2k20compound/REPORT.md:40-53; results.json:117-124
#  GV1-3: oc_governor/REPORT.md:51-61,66-70,75
#  Ablation: oc_ablation/REPORT.md:16-27,49-55,65
#  A1: oc_lit_xs/REPORT.md:33,46-48; S5: oc_amihudrobust/REPORT.md:36-49
#  M1: oc_lit_position/REPORT.md:59-68,73-79; oc_mvrvrobust/REPORT.md:9-10,38-45,69-87,108
#  A1M1: oc_mvrvrobust/REPORT.md:89-95
#  K2: oc_kronoshidden/REPORT.md:106-111,121-137 (dev4+Y4 only, NO 5y -> R5y blank)
#  VRP FULL: oc_vrpstrike/REPORT.md:130-138,152-156,174-182
#  Frontier rows: oc_frontier/REPORT.md:18-99 (table), :103-114 (frontiers), :116-121
ROWS = [
    ("G2", "G2 v421 R2B1D17BFG2", "signal", "yes", 5.410, "", "", 4.648, 16.91, 16.82,
     "v421 PASS; robust PASS", "v421_audit"),
    ("D17BF", "D17BF v411 R2B1D17BF", "signal", "no", 5.425, "", "", 5.060, 18.33, 16.90,
     "v411 PASS; robust PASS", "v411_audit"),
    ("D13BF", "D13BF v424 R2B1D13BF", "signal", "no", 4.971, "", "", 4.723, 14.98, 14.86,
     "v424 comparison PASS (no ROBUST.md)", "v424_audit+oc_kpi_d13"),
    ("G2K20", "G2K20 v422", "signal", "no", 5.874, "", "", 4.716, 17.79, 17.69,
     "v422 PASS; blind PASS; Y4 fold FAILED vs ref", "v422_audit+oc_g2k20robust"),
    ("G2carry", "G2+carry f0.25", "overlay", "no", 5.634, "", "", 4.698, 16.75, 16.66,
     "repro to digit; post-hoc, needs prospective", "oc_carrycompound"),
    ("G2K20carry", "G2K20+carry f0.25 base", "overlay", "no", 6.097, "", "", 4.766, 17.64, 17.54,
     "cross-checks exact; post-hoc", "oc_g2k20compound"),
    ("GV1", "Governor GV1", "dial", "no", 5.827, 6.110, 2.826, 4.704, 19.14, 18.91,
     "REJECT (recent<5)", "oc_governor"),
    ("GV2", "Governor GV2", "dial", "no", 5.872, 6.158, 2.828, 4.736, 19.32, 19.05,
     "REJECT (recent<5)", "oc_governor"),
    ("GV3", "Governor GV3 pooled", "dial", "no", 5.849, 6.107, 2.830, 4.824, 17.89, 17.50,
     "REJECT (recent<5); robust-pick nominal", "oc_governor"),
    ("NO_GOV", "Ablation NO_GOV", "dial", "no", 5.907, 6.180, 2.83, 4.824, 20.04, 19.60,
     "diagnostic; breaches 20%", "oc_ablation"),
    ("NO_VT", "Ablation NO_VT", "dial", "no", 6.119, 6.459, 2.393, 4.772, 17.93, 18.39,
     "diagnostic only", "oc_ablation"),
    ("NO_BEAR", "Ablation NO_BEAR", "dial", "no", 5.415, 5.597, 2.119, 4.689, 16.91, 16.81,
     "diagnostic only", "oc_ablation"),
    ("NO_CAP", "Ablation NO_CAP", "dial", "no", 5.425, 5.517, 2.831, 5.060, 18.33, 16.90,
     "diagnostic only", "oc_ablation"),
    ("NO_B1", "Ablation NO_B1", "dial", "no", 5.142, 5.434, 1.571, 3.986, 23.65, 20.20,
     "diagnostic; breaches gate", "oc_ablation"),
    ("TOUCH", "Ablation TOUCH", "dial", "no", 5.079, 5.220, 2.356, 4.519, 18.62, 18.56,
     "diagnostic only", "oc_ablation"),
    ("A1", "Amihud A1", "signal", "no", 5.624, 5.844, 2.798, 4.750, 16.81, 16.66,
     "dev4-only selection; Y4 scored once", "oc_lit_xs"),
    ("A1_S5", "Amihud A1 S5 Bybit", "signal", "no", 4.884, 4.989, "", "", 18.58, 21.32,
     "strict FAIL (gap~0, DD>20)", "oc_amihudrobust"),
    ("M1", "MVRV M1", "signal", "no", 5.881, 6.192, 2.588, 4.648, 16.26, 16.22,
     "robust but tie->not strict", "oc_lit_position+oc_mvrvrobust"),
    ("A1M1", "A1+M1 post-hoc", "overlay", "no", 5.939, 6.238, 2.798, 4.750, 16.08, 15.92,
     "post-hoc compatibility only", "oc_mvrvrobust"),
    ("K2", "Kronos K2 (dev+Y4)", "signal", "no", "", 5.772, 2.469, 4.801, 16.20, 16.09,
     "REJECT (Y4<5, upper bound)", "oc_kronoshidden"),
    ("VRP", "VRP straddle FULL f0.25", "overlay", "no", 5.332, 5.408, 2.909, 5.025, 18.19, 18.11,
     "REJECT (mean-DD bar)", "oc_vrpstrike"),
    ("v399_R2B1", "v399 R2B1", "dial", "no", 4.550, "", "", 4.405, 13.88, "",
     "audited yes; no full-path logged", "oc_frontier"),
    ("v409_D13", "v409 R2B1D13", "dial", "no", 4.957, "", "", 4.704, 15.00, 16.36,
     "audited yes; yearly frontier", "oc_frontier"),
    ("v409_D15B08", "v409 R2B1D15B08", "dial", "no", 4.626, "", "", 4.054, 15.99, 14.94,
     "audited yes; lowest full-path DD", "oc_frontier"),
    ("v423_X45", "v423 R2B1D17BFX45", "dial", "no", 5.118, "", "", 4.643, 15.92, 15.81,
     "audited yes; both frontiers", "oc_frontier"),
    ("v422_F20K20", "v422 G2F20K20", "dial", "no", 5.346, "", "", 4.613, 16.20, 16.02,
     "audited yes; both frontiers", "oc_frontier"),
    ("v415_S6", "v415 R2B1D17BFS6", "dial", "no", 5.565, "", "", 5.167, 18.37, 16.71,
     "audited yes; dominates deploy full-path", "oc_frontier"),
    ("v422_G15K20", "v422 G15K20", "dial", "no", 5.731, "", "", 4.340, 16.96, 16.76,
     "audited yes; yearly frontier", "oc_frontier"),
    ("v407_D20B11", "v407 R2B1D20B11", "dial", "no", 5.894, "", "", 5.528, 21.21, 19.10,
     "audited yes; highest R", "oc_frontier"),
]

HEADER = ["id", "label", "kind", "adopted", "R5y_pctpm", "dev4_R", "dev4_W",
          "recent_R", "max_yearly_DD", "full_DD", "audit", "source"]


def main():
    with open(CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for r in ROWS:
            w.writerow(r)

    colors = {"dial": "#1f77b4", "signal": "#2ca02c", "overlay": "#ff7f0e"}
    fig, ax = plt.subplots(figsize=(9, 6))
    for _id, label, kind, adopted, r5y, _d4r, _d4w, _rec, _mdd, full, _au, _src in ROWS:
        if r5y == "" or full == "":
            continue
        marker = "*" if adopted == "yes" else "o"
        size = 160 if adopted == "yes" else 55
        ax.scatter(full, r5y, c=colors[kind], marker=marker, s=size,
                   edgecolors="black", linewidths=0.6, zorder=3)
    # annotations for key points only (avoid clutter)
    annotate = {"G2": (-32, 8), "G2K20": (4, 4), "A1M1": (4, 4), "M1": (-30, 8),
                "A1": (6, -14), "G2carry": (6, 4), "D13BF": (-38, 2), "v407_D20B11": (4, 2),
                "v409_D15B08": (-52, 6), "VRP": (4, 2), "GV2": (4, 2)}
    pts = {r[0]: (r[9], r[4]) for r in ROWS if r[4] != "" and r[9] != ""}
    for _id, (dx, dy) in annotate.items():
        x, y = pts[_id]
        ax.annotate(_id, (x, y), xytext=(dx, dy), textcoords="offset points", fontsize=8)
    # legend proxies
    import matplotlib.lines as mlines
    handles = [mlines.Line2D([], [], color=c, marker="o", linestyle="None",
                             markersize=7, label=k) for k, c in colors.items()]
    handles.append(mlines.Line2D([], [], color="black", marker="*", linestyle="None",
                                 markersize=12, label="adopted (G2)"))
    ax.legend(handles=handles, fontsize=8, loc="upper left")
    ax.set_xlabel("full-path DD (%)")
    ax.set_ylabel("5-year mean (%/month, reset metric)")
    ax.set_title("G2 family: return vs drawdown (gate costs; numbers copied from cited reports)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(PNG, dpi=150)
    print(f"wrote {CSV} ({len(ROWS)} rows) and {PNG}")


if __name__ == "__main__":
    main()
