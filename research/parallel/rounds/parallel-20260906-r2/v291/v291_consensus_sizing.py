"""v291: size the CB book by the CONSENSUS of its six model sets (confidence = agreement) (registry v291).

Why (user idea 2026-09-30: take more exposure when the model is confident): CB's book is a weighted MEAN of six walk-forward model sets
(A, Aq = O1 flow; B, Bq = options + TradingView; D, Dq = Coinbase premium; weights 0.2 / 0.2 / 0.2 / 0.2 / 0.1 / 0.1). When the sets
disagree, the mean is only diluted - disagreement itself (epistemic uncertainty) is never used. Here the per-coin weight is scaled by
the agreement a = |sum w_m m| / sum w_m |m| in [0, 1] (1 = all sets on the same side). The engine's portfolio vol target (0.25 on the
trailing 60 days of realised book returns, cap 2) re-normalises the overall size, so the scaling moves exposure towards bars / coins
where the sets agree rather than adding risk. Every input is a walk-forward member already used by CB (no new fit, no new data).
Fixed before running (everything else = CB / C4 rules: G2 grid trader, close5 dip stops 4 sigma + 8-sigma backstop, budget 0.18,
v221.KW, minute-5 rule, limit entries, SL market / TP limit, Bybit fees, adverse funding):
  C1_a1   books = CB x a        C2_a2   books = CB x a^2
Reference: CB_ref (must reproduce dev4 5.864). SELECTION = v286.dev_select among C1, C2; the selected row replaces CB only if
dev_select prefers it over CB_ref. The most recent year is scored once, for the selected row. Also reported (dev): mean agreement,
the mean book gross relative to CB.

  python research/parallel/rounds/parallel-20260906-r2/v291/v291_consensus_sizing.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
C4R = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0, sleeve_risk_budget=0.18)
W = {"A": 0.2, "B": 0.2, "Aq": 0.2, "Bq": 0.2, "D": 0.1, "Dq": 0.1}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_c", RD / "v286/v286_coinbase_member_upgrade.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols, idx, C = list(books154.columns), books154.index, eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    cb = sum(W[k] * m[k] for k in W)
    absum = sum(W[k] * m[k].abs() for k in W)
    a = (cb.abs() / absum.where(absum > 0)).fillna(0.0).clip(0.0, 1.0)
    dev = (idx >= pd.Timestamp("2021-09-24", tz="UTC")) & (idx < pd.Timestamp("2025-09-24", tz="UTC"))
    out = {"version": "v291", "rows": {}, "trades": {}, "diag": {}}
    nz = cb.abs().to_numpy()[dev] > 0
    out["diag"]["mean_agreement_dev_nonzero"] = round(float(a.to_numpy()[dev][nz].mean()), 3)
    mixes = {"CB_ref": cb, "C1_a1": cb * a, "C2_a2": cb * a ** 2}
    for k, bk in mixes.items():
        out["diag"][f"gross_rel_{k}"] = round(float(bk.abs().sum(axis=1)[dev].mean() / cb.abs().sum(axis=1)[dev].mean()), 3)
    print("diag", out["diag"], flush=True)
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    for key, bk in mixes.items():
        ev = []
        r = eu.simulate(bk, opens, prep, trade=trade, win_start=5, events=ev, **dict(v221.KW, **C4R))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"]["trades"], "win", out["trades"][key]["dev"]["win_rate"], flush=True)
        if key == "CB_ref":
            assert abs(r["monthly_dev4"] - 5.864) < 0.002
    sel = v286.dev_select({k: out["rows"][k] for k in ("C1_a1", "C2_a2")}, v204.worst_month)
    out["selected"] = sel
    out["replaces_cb"] = v286.dev_select({k: out["rows"][k] for k in ("CB_ref", sel)}, v204.worst_month) == sel
    s_ = out["rows"][sel]
    out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                   "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y", "gate_dd", "gate_pass", "dd_4h", "dd_1m", "losing_years"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, "replaces CB:", out["replaces_cb"], out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v291_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
