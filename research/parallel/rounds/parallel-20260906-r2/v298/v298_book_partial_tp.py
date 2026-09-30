"""v298: take partial profits on book trades like a trader - towards the new win-rate goal (~60%) (registry v298).

Why (user goal 2026-09-30: DD ~15%, 6-7 %/month, win rate ~60%): the book (G2 grid trader) wins ~51% of its trades - trend trades win
rarely but big; dip rungs already win ~70%. A trader scales out: book half of the position at a first target, move the stop to
break-even, let the rest run. The engine's trade mode supports it (partial_k: limit take-profit of partial_frac of the position at
entry +- partial_k sigma_d, then the stop moves to break-even), but it was only tested in the pre-grid trade mode (v210 T3); never on the
G2 grid trader with the current foundation and the learned dip agents. Everything else = v296 J1 (same books, C4 rules, J1 agents).
Fixed before running:
  P1_k2_h     partial_k 2.0, partial_frac 0.5
  P2_k3_h     partial_k 3.0, partial_frac 0.5
  P3_k2_t     partial_k 2.0, partial_frac 0.33
Reference: J1_ref (must reproduce dev4 6.268).
SELECTION (win-rate goal, dev years only): pool = rows whose worst dev year >= 0.95 x J1's, dev DD <= J1's + 0.5 and no losing dev year;
within the pool the highest dev book-trade win rate (ties -> worst dev year). The selected row replaces J1 only if its dev win rate beats
J1's by >= 0.03. The most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v298/v298_book_partial_tp.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
ROWS = {"J1_ref": {}, "P1_k2_h": dict(partial_k=2.0, partial_frac=0.5), "P2_k3_h": dict(partial_k=3.0, partial_frac=0.5),
        "P3_k2_t": dict(partial_k=2.0, partial_frac=0.33)}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v297 = _load("v297_p", RD / "v297/v297_risk_realloc.py")
v296, v293 = v297.v296, v297.v293


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_p", RD / "v286/v286_coinbase_member_upgrade.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols, idx, C = list(books154.columns), books154.index, eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    cb = 0.8 * (0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2) + 0.2 * (m["D"] + m["Dq"]) / 2
    prep = eu.prepare(books154, opens)
    size, tp = v297.build_j1_hooks(eu, idx, cols)
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    out = {"version": "v298", "rows": {}, "trades": {}}
    for key, extra in ROWS.items():
        ev = []
        trade = dict(v216.GRID, **extra, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
        r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, sleeve_fill_size=size, sleeve_tp=tp,
                        **dict(v221.KW, **v293.C4R))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        r["dev_rungs"] = v296.rung_stats([e for e in ev if e["t"] < anchors[4]])
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], "partials", r["stats"].get("partials"), "dev rungs", r["dev_rungs"], flush=True)
        if key == "J1_ref":
            assert abs(r["monthly_dev4"] - 6.268) < 0.002
    ref, wr = out["rows"]["J1_ref"], out["trades"]["J1_ref"]["dev"]["win_rate"]
    pool = {k: v for k, v in out["rows"].items() if k != "J1_ref" and v["worst_dev_month_pct"] >= 0.95 * ref["worst_dev_month_pct"]
            and v["dev_dd"] <= ref["dev_dd"] + 0.5 and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    sel = max(pool, key=lambda k: (out["trades"][k]["dev"]["win_rate"], pool[k]["worst_dev_month_pct"])) if pool else None
    if sel and out["trades"][sel]["dev"]["win_rate"] < wr + 0.03:
        sel = None
    out["selected"] = sel
    if sel:
        s_ = out["rows"][sel]
        out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                       "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                       "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                       "hidden_year_trades": out["trades"][sel]["_hidden"]}
    else:
        out["final_score_selected"] = "no row meets the win-rate rule - J1 stays; nothing scored on the most recent year"
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y", "gate_dd", "gate_pass", "dd_4h", "dd_1m", "losing_years"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v298_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
