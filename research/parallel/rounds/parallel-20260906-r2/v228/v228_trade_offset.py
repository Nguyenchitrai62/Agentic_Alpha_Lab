"""v228: deeper limit offsets for the executable grid trader D2 (registry v228).

Why: entries / adjustments / exits of D2 rest 0.25 sigma_4h from the open. Patient traders place deeper limits (better price, fewer
fills). LABEL: the D2 robustness diagnostic (research/diagnostics/d2_robustness) already showed offset 0.40 with ALL years (dev4 5.36,
last year 4.00, DD 18.8); this version therefore uses other offsets and needs the prospective log as clean evidence.
Fixed before running (everything else = v218 D2): trade["k_off"] (entry, add, reduce and exit limits):
  O1_035   0.35 sigma_4h      O2_045   0.45 sigma_4h      O3_055   0.55 sigma_4h
Reference: v218_D2 (0.25). SELECTION = robust criterion among O1..O3; the most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v228/v228_trade_offset.py
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


v221 = _load("v221", HERE.parent / "v221/v221_grid_hysteresis.py")
eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
VARIANTS = {"O1_035": 0.35, "O2_045": 0.45, "O3_055": 0.55}


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    books = 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v228", "variants": VARIANTS, "rows": {}, "trades": {}}
    for key, k_off in [("v218_D2", 0.25)] + list(VARIANTS.items()):
        ev = []
        r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol, k_off=k_off), win_start=5, events=ev, **v221.KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "v218_D2":
            assert abs(r["monthly_dev4"] - 5.261) < 0.002
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
    (HERE / "v228_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
