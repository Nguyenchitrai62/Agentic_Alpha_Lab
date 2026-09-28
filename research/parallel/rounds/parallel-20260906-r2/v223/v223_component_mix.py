"""v223: re-weight the three components of the foundation signal for the executable trade mode (registry v223).

Why: every trade-management layer (v212-v222) plateaus at dev4 ~5.1-5.3 / last year ~3.8-4.0: the foundation signal is the limit.
Each member book (v144 structure) is 0.25 v92 long-only 7d + 0.25 v94 long/short 18/42/84-bar + 0.5 v103 flow long/short 1d/3d.
The weights were chosen for the continuous 4h-rebalanced book (v115/v133 era); the trade mode holds positions ~2 days and exits
when |target| falls below 5% (80% of the exits), so the fast flow half may make the signal cross its threshold too often.
Data: build_components.py re-runs the audited member pipelines (annual + v202 quarterly, members A = v144, B = v150 options) and
keeps the three weighted components apart; their sum reproduces the audited member caches (checked).
Fixed before running: member book = w_lo * lo/0.25 + w_ls * ls/0.25 + w_fl * fl/0.5 (lo, ls, fl = the stored weighted components);
ensemble = 0.5 (A + B)/2 annual + 0.5 (Aq + Bq)/2 quarterly as in v205; everything else = v218 D2 (v216 G2 grid trader, sleeve
budget 0.15, rung x1.75, minute-5 rule, limits, SL market / TP limit, governor, aligned sleeve, Bybit fees, adverse funding).
  ref_mix     (0.25, 0.25, 0.50)  must reproduce v218 D2 (dev4 5.261).
  W1_slower   (0.35, 0.35, 0.30)
  W2_slow     (0.40, 0.40, 0.20)
  W3_noflow   (0.50, 0.50, 0.00)
SELECTION = robust criterion among W1..W3; the most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v223/v223_component_mix.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
CACHE = Path("artifacts/research/engine_real")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v221 = _load("v221", HERE.parent / "v221/v221_grid_hysteresis.py")
v216, eu, v204, v213 = v221.v216, v221.eu, v221.v204, v221.v216.v213
KW = v221.KW
MIXES = {"ref_mix": (0.25, 0.25, 0.50), "W1_slower": (0.35, 0.35, 0.30), "W2_slow": (0.40, 0.40, 0.20), "W3_noflow": (0.50, 0.50, 0.00)}


def member(name, mix, index, cols):
    c = pd.read_parquet(CACHE / f"components_{name}.parquet")
    lo, ls, fl = (c.xs(k, axis=1, level=0).reindex(index).fillna(0.0)[cols] for k in ("lo", "ls", "fl"))
    return mix[0] * lo / 0.25 + mix[1] * ls / 0.25 + mix[2] * fl / 0.5


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    prep = eu.prepare(books154, opens)
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v223", "mixes": MIXES, "rows": {}, "trades": {}}
    for key, mix in MIXES.items():
        A, B, Aq, Bq = (member(n, mix, idx, cols) for n in ("A_annual", "B_annual", "A_quarterly", "B_quarterly"))
        books = 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2
        ev = []
        r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol), win_start=5, events=ev, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "ref_mix":
            assert abs(r["monthly_dev4"] - 5.261) < 0.002, "the component sum must reproduce v218 D2"
    cands = ("W1_slower", "W2_slow", "W3_noflow")
    sel = v204.robust_select({k: out["rows"][k] for k in cands})
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
    (HERE / "v223_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
