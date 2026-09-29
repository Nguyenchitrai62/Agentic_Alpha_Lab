"""v280: a MONTHLY-retrained flow member (O1 member A) on the C4 rules - the foundation adapts to new regimes faster.

Why: every stop / size / RL variant scores lower on the unseen year than on the dev years, and the only changes that ever lifted the
unseen year were foundation information. The foundation members retrain yearly (A, B) and quarterly (Aq, Bq); order-level whale flow is
the most regime-dependent input. A monthly schedule was rejected in v207 (older books, DD > 20) - C4 (v269 M1) now has ~1.7 pp of DD margin.
Fixed before running.
Member Am = the O1 member A builder (v240: v144 builder with TradingView + order-level flow, flow excluded from the vol models) wrapped
with MONTHLY anchors 2021-09-24 + k months (k = 0..59), each model predicting only its own month (v202 wrapper with v207's monthly
anchors; per-target cutoffs and embargoes unchanged, relative to each anchor). Cached in the engine_real cache.
Environment = C4 = v269 M1 rules (dip stops on 5m closes at 4 sigma + 8-sigma native backstop, sleeve budget 0.18, v218 D2 settings).
  V1_monthly_for_quarterly   books = 0.5 (A + B)/2 + 0.5 (Am + Bq)/2          (the flow member's quarterly models replaced by monthly)
  V2_three_schedules         books = [(A + B)/2 + (Aq + Bq)/2 + (Am + Bq)/2] / 3
Reference: C4 / v269 M1 books 0.5 (A + B)/2 + 0.5 (Aq + Bq)/2 (must reproduce dev4 6.026). SELECTION = robust criterion among V1, V2; the
most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v280/v280_monthly_flow_member.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
M = [str(d.date()) for d in pd.date_range("2021-09-24", periods=60, freq=pd.DateOffset(months=1))]
C4 = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0, sleeve_risk_budget=0.18)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_monthly_A():
    v240 = _load("v240_m", RD / "v240/v240_order_level_flow.py")
    v202 = _load("v202_mA", RD / "v202/v202_quarterly_retrain.py")
    v202.Q[:] = M
    v202.END.clear()
    v202.END.update({a: (M[i + 1] if i + 1 < len(M) else "2026-09-24") for i, a in enumerate(M)})
    v144 = _load("v144_mA", RD / "v144/v144_deploy_v3.py")
    v202.quarterly(v144)
    ext, v103 = v144.v115.v114.v113, v144.v103
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    base92 = b92()
    xf = v240.feature_frame(ext.v92.load_asset, False)
    drop = {c for c in xf.columns if c not in ("t", "sym")}
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in drop], anchors, emb)
    ext.v92.build = lambda: base92.merge(xf, on=["t", "sym"], how="left")
    v103.build = lambda: b103().merge(xf, on=["t", "sym"], how="left")
    return v144.books_v142()[1]


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    cache = C / "member_Am_O1_monthly.parquet"
    if not cache.exists():
        build_monthly_A().to_parquet(cache)
    print("member Am cached", flush=True)
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"),
        ("Am", "member_Am_O1_monthly.parquet"))}
    annual, quarterly, monthly = (m["A"] + m["B"]) / 2, (m["Aq"] + m["Bq"]) / 2, (m["Am"] + m["Bq"]) / 2
    mixes = {"v269_M1": 0.5 * annual + 0.5 * quarterly, "V1_monthly_for_quarterly": 0.5 * annual + 0.5 * monthly,
             "V2_three_schedules": (annual + quarterly + monthly) / 3}
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    out = {"version": "v280", "rows": {}, "trades": {}}
    for key, bk in mixes.items():
        ev = []
        r = eu.simulate(bk, opens, prep, trade=trade, win_start=5, events=ev, **dict(v221.KW, **C4))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]], flush=True)
        if key == "v269_M1":
            assert abs(r["monthly_dev4"] - 6.026) < 0.002, "must reproduce v269 M1"
    cands = ("V1_monthly_for_quarterly", "V2_three_schedules")
    sel = v204.robust_select({k: out["rows"][k] for k in cands})
    s_ = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                   "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v280_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
