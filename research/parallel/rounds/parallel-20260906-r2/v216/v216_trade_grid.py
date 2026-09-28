"""v216: trade mode that follows the pipeline's size on a coarse grid - limit adjustments at most once a day (registry v216).

Why: continuous v205 earns dev4 5.82 by following the signal strength, but it re-sizes every 4h. The executable trade modes
(v210-v213) freeze the size and lose ~1-1.6pp/month; learned trade management (v214/v215) was worse than the rules. A trader
who follows a model re-sizes a few times, with clear limit orders and time to react.

Fixed before running (engine_user trade mode through trade["policy"]; everything else = v212 S3: entry limit open -/+
max(0.10%, 0.25 sigma_4h) valid 8h, minute-5 rule, SL 4 sigma_d market from the average entry, TP 8 sigma_d limit, break-even
at +2 sigma_d, v205 books / governor / aligned dip sleeve / Bybit fees / adverse funding). Policy per coin and decision:
  flat with a signal (|target| >= 5%) -> open (limit) at weight |target|.
  in a position: signal reversed -> tighten + close (limit); signal gone (|target| < 5%) -> close (limit);
                 else, at most one adjustment per 6 bars (1 day) since the last order: if |target| - w > band -> ADD
                 |target| - w (limit); if w - |target| > band -> REDUCE the fraction (w - |target|) / w (limit); else hold.
  band = max(B_abs, B_rel * |target|):
  G1_fine     B_abs 2% equity, B_rel 25%.
  G2_medium   B_abs 3%, B_rel 40%.
  G3_coarse   B_abs 5%, B_rel 60%.
References: ref_v205, rule_E1 (= v213 E1), rule_S3 (= v212 S3). SELECTION = robust criterion among G1..G3; the most recent year
is scored once for the selected row. Orders per coin per day are reported.

  python research/parallel/rounds/parallel-20260906-r2/v216/v216_trade_grid.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v215 = _load("v215", HERE.parent / "v215/v215_policy_improvement.py")
v213, eu, v204 = v215.v213, v215.eu, v215.v204
KW, S3 = v215.KW, v215.S3
rule_s3, rule_e1 = v215.rule_s3, v215.rule_e1
COOL = 6
GRID = dict(S3, max_adds=99)
VARIANTS = {"G1_fine": (0.02, 0.25), "G2_medium": (0.03, 0.40), "G3_coarse": (0.05, 0.60)}


def grid_policy(b_abs, b_rel):
    def pol(i, a, st):
        if st["pos"] == 0:
            return "open"
        side, tg, w, valid = st["pos"], st["tg"], st["w"], st["valid"]
        if st["sgn"] == -side:
            return {"tighten": 1, "close": 1} if "close" in valid else "tighten"
        if st["sgn"] == 0:
            return "close" if "close" in valid else "hold"
        if st["since_adj"] < COOL:
            return "hold"
        band = max(b_abs, b_rel * abs(tg))
        diff = abs(tg) - w
        if diff > band and "add" in valid:
            return {"add": diff}
        if -diff > band and "reduce" in valid and w > 0:
            return {"reduce": min(1.0, -diff / w)}
        return "hold"
    return pol


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    books = 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    out = {"version": "v216", "cooldown_bars": COOL, "variants": VARIANTS, "rows": {}, "trades": {}}
    runs = [("ref_v205", {}), ("rule_S3", dict(trade=dict(S3, policy=rule_s3), win_start=5)),
            ("rule_E1", dict(trade=dict(S3, policy=rule_e1), win_start=5))]
    runs += [(k, dict(trade=dict(GRID, policy=grid_policy(*v)), win_start=5)) for k, v in VARIANTS.items()]
    days = 4 * 365
    for key, extra in runs:
        ev = []
        r = eu.simulate(books, opens, prep, events=ev, **KW, **extra)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key] = r
        ts = v213.trade_stats(ev) if "trade" in extra else None
        if ts:
            out["trades"][key] = ts
        st = r["stats"]
        orders = sum(1 for e in ev if e["kind"] == "order_issue" and e["t"] < pd.Timestamp("2025-09-24", tz="UTC"))
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              {k: st[k] for k in ("fills", "stops", "tps", "adds", "reduces", "limit_exits", "tightened") if k in st},
              "orders/coin/day", round(orders / 5 / days, 2) if ts else None, "dev trades", ts["dev"] if ts else None, flush=True)
        if key == "rule_S3":
            assert abs(r["monthly_dev4"] - 4.826) < 0.002
        if key == "rule_E1":
            assert abs(r["monthly_dev4"] - 4.216) < 0.002
    sel = v204.robust_select({k: out["rows"][k] for k in VARIANTS})
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v216_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
