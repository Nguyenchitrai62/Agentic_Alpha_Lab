"""Prospective scorecard: each paper pipeline's live result vs what its own walk-forward research expects for the same horizon.

For every paper pipeline with a trade plan (artifacts/research/advisor_shadow/trade_plan_<v>.json, equity_curve since its freeze) and a research
replay in the backend DB (equity source tm_<v>), the research expectation for a horizon of d days is a stationary block bootstrap of the replay's
DAILY returns over the four dev years only (2021-09-24 .. 2025-09-24; 10-day blocks, 4000 draws, seed 0) -> quantiles of the cumulative return
over d days. The live paper return is placed in that distribution (percentile). Nothing here feeds any research choice; it only tells whether
the live behaviour is consistent with the research claim.
  python scripts/prospective_scorecard.py            -> prints a table, writes artifacts/research/advisor_shadow/prospective_scorecard.json
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "artifacts/research/advisor_shadow"
DB = ROOT / "artifacts/web/app.db"
DEV0, DEV1 = pd.Timestamp("2021-09-24", tz="UTC"), pd.Timestamp("2025-09-24", tz="UTC")
NAMES = {"bot_paper": "R2-4P bot on Bybit (paper)", "bot_paper_d17bf": "R2B1D17BF bot on Bybit (paper, v411)",
         "bot_paper_d17bfg2": "R2B1D17BFG2 bot on Bybit (paper, G2+cap2.0)",
         "bot_paper_g2k20": "G2K20 bot on Bybit (paper, v422)",
         "v367": "M5 (MANUAL)", "v362": "M4 (MANUAL)", "v342": "M3 (MANUAL)", "v340": "M2 (MANUAL)", "v315": "M1 (MANUAL)", "v321": "R2 (BOT)", "v301": "G2 (BOT)", "v295": "CS (BOT)", "v285": "D2", "v269": "M1-old",
         "v266": "C5"}
# Static research expectations for the two deployment-candidate paper bots
# (docs/DEPLOYMENT_PLAN_VI.md; research/parallel/rounds/parallel-20260906-r2/
# v421/v422 result JSONs: v421 R2B1D17BFG2 R=5.41 DD=16.91; v422 G2K20 R=5.874 DD=17.79).
RESEARCH_EXPECT = {
    "bot_paper_d17bfg2": {"variant": "R2B1D17BFG2 (v421)", "monthly_pct": 5.41, "max_yearly_dd": 16.91,
                          "config": "R2B1D17BF + --dip-gross-cap 2.0 (deployment)", "started": "2026-10-05 17:51 UTC"},
    "bot_paper_g2k20": {"variant": "G2K20 (v422)", "monthly_pct": 5.87, "max_yearly_dd": 17.79,
                        "config": "--dip-mult 2.0 --dip-gross-cap 2.0", "started": "2026-10-05 17:38 UTC"},
}
# Go-live / stop thresholds used for d17bf (docs/DEPLOYMENT_PLAN_VI.md s2.3 go-live, s4 stop); same bar for the two new bots.
GO_LIVE = ("min 8w: live pct>=20 of bootstrap for same days, DD<=15%, "
           "paper-vs-plan divergence<=1.5pp/month, no cycle_error>1h, every position has stop")
STOP_RULE = ("DD>20% stop new entries (keep SL/TP); monthly loss>10% halve size next month; "
             "live pct<5 after >=8w stop")
BOT_DIRS = (("bot_paper", ROOT / "artifacts/bot/paper/exchange.json"),
            ("bot_paper_d17bf", ROOT / "artifacts/bot/paper_d17bf/exchange.json"),
            ("bot_paper_d17bfg2", ROOT / "artifacts/bot/paper_d17bfg2/exchange.json"),
            ("bot_paper_g2k20", ROOT / "artifacts/bot/paper_g2k20/exchange.json"))


def research_daily(con, v):
    rows = con.execute("SELECT t, equity FROM equity WHERE source = ? ORDER BY t", (f"tm_{v}",)).fetchall()
    if not rows:
        return None
    s = pd.Series([e for _, e in rows], index=pd.to_datetime([t for t, _ in rows], unit="ms", utc=True))
    s = s[(s.index >= DEV0) & (s.index < DEV1)]
    return s.resample("1D").last().dropna().pct_change().dropna().to_numpy()


def bootstrap(daily, days, draws=4000, block=10, seed=0):
    rng = np.random.default_rng(seed)
    n = max(1, int(round(days)))
    out = np.empty(draws)
    for q in range(draws):
        path = []
        while len(path) < n:
            st = rng.integers(0, len(daily) - block)
            path.extend(daily[st:st + block])
        out[q] = np.prod(1 + np.array(path[:n])) - 1
    return out


def main():
    con = sqlite3.connect(DB)
    table = []
    sources = [(p.stem.replace("trade_plan_", ""), json.loads(p.read_text()).get("equity_curve") or []) for p in sorted(PLANS.glob("trade_plan_v*.json"))]
    for key, path in BOT_DIRS:  # paper bots filled from live Bybit 1m klines (bot/paper.py); order kept for stable output
        if path.exists():
            sources.append((key, json.loads(path.read_text()).get("equity_curve") or []))
    for v, curve in sources:
        if len(curve) < 2:
            continue
        t0, t1 = pd.Timestamp(curve[0][0]), pd.Timestamp(curve[-1][0])
        days = (t1 - t0).total_seconds() / 86400
        live = float(curve[-1][1]) / float(curve[0][1]) - 1
        daily = research_daily(con, "v376" if v.startswith("bot_paper") else v)  # proxy expectation: the R2-4P replay  # the bot mirrors the R2-4P plan
        row = dict(pipeline=v, name=NAMES.get(v, v), start=str(t0), last=str(t1), days=round(days, 2), live_pct=round(100 * live, 3))
        if v in RESEARCH_EXPECT:
            exp = RESEARCH_EXPECT[v]
            row.update(research_variant=exp["variant"], research_monthly_pct=exp["monthly_pct"],
                       research_max_yearly_dd=exp["max_yearly_dd"], config=exp["config"], started=exp["started"],
                       go_live=GO_LIVE, stop=STOP_RULE)
        if daily is not None and len(daily) > 100 and days >= 0.5:
            b = bootstrap(daily, days)
            row.update(expected_p05=round(100 * float(np.quantile(b, 0.05)), 2), expected_p50=round(100 * float(np.quantile(b, 0.5)), 2),
                       expected_p95=round(100 * float(np.quantile(b, 0.95)), 2), percentile=round(100 * float((b <= live).mean()), 1))
        table.append(row)
    out = PLANS / "prospective_scorecard.json"
    out.write_text(json.dumps({"generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "rows": table}, indent=1))
    print(pd.DataFrame(table).to_string(index=False))


if __name__ == "__main__":
    main()
