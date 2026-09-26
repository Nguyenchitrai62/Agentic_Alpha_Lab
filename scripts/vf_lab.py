"""Run virtual-forward families and keep a leaderboard.

  python scripts/vf_lab.py trend_long donchian_long ... [--cap 1.0]
"""
import argparse, json, time
from pathlib import Path
import pandas as pd
from agentic_alpha_lab.research_vf import ANCHORS, accept, load_context, load_context_extended, run, strip
from agentic_alpha_lab.vf_families import FAMILIES

OUT = Path("artifacts/research/vf")


def report(name, res, cap):
    print(f"\n=== {name} (cap {cap}) ===")
    for p in res["per_anchor"]:
        if p.get("selected") is None:
            print(p["anchor"], "no selection"); continue
        n, s = p["forward"]["normal"], p["forward"]["stress"]
        print(f"{p['anchor']} sel={p['selected']} k={p['scale']} | fwd net {n['net_pct']:.1f}% stress {s['net_pct']:.1f}% ddI {n['dd_intrabar_pct']:.1f}% sharpe {n['sharpe']:.2f} changes {n['changes']} | B&H {p['buy_hold_net']:.1f}%")
    a = res["aggregate"]
    for c in ("normal", "stress"):
        if c in a: print(c, a[c])
    print("B&H yearly", a["buy_hold_yearly"], "total", a["buy_hold_total_pct"], "| ACCEPT" if accept(a) else "| reject")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("families", nargs="+"); ap.add_argument("--cap", type=float, default=1.0); ap.add_argument("--tf", default="4h"); ap.add_argument("--multi", action="store_true", help="secondary 5-year robustness view"); ap.add_argument("--extended", action="store_true", help="prefix 2017-2019 spot history")
    a = ap.parse_args()
    ctx = load_context_extended(a.tf) if a.extended else load_context(a.tf)
    board = OUT / "leaderboard.csv"
    for fam in a.families:
        t0 = time.time()
        fn, grid = FAMILIES[fam]
        res = run(ctx, fn, grid, cap=a.cap, anchors=ANCHORS, select_years=None) if a.multi else run(ctx, fn, grid, cap=a.cap)
        report(fam, res, a.cap)
        tag = f"{fam}_cap{a.cap}_{a.tf}" + ("_multi" if a.multi else "_hidden1y") + ("_ext" if a.extended else "")
        (OUT / f"{tag}.json").write_text(json.dumps(strip(res), indent=1, default=str))
        ag = res["aggregate"]
        row = dict(family=tag, run_at=pd.Timestamp.utcnow().isoformat(), accept=accept(ag),
                   **{f"{c}_{k}": ag[c][k] for c in ("normal", "stress") if c in ag for k in ("cagr_pct", "monthly_geo_pct", "max_dd_close_pct", "worst_year_intrabar_dd", "years_positive")},
                   stress_yearly=ag.get("stress", {}).get("yearly_net"), bh_yearly=ag["buy_hold_yearly"])
        df = pd.read_csv(board) if board.exists() else pd.DataFrame()
        df = pd.concat([df[df.family != tag] if len(df) else df, pd.DataFrame([row])])
        df.to_csv(board, index=False)
        print(f"({time.time()-t0:.0f}s)")
