"""v238: market-wide large-order flow (BTC + cross-asset mean) for every major, on top of v236 W2 (registry v238).

Why: v236 W2 (T3 + per-asset whale-vs-retail taker flow in the A members) is the best foundation (dev4 5.774, worst dev year 2.491,
DD 19.51, 5y 5.442, most recent year 4.123; robust to cost / latency / parameter shifts, no losing year in any perturbation). Each
coin sees only its own flow; traders read altcoins against the market leader's (BTC) and the whole market's large-order pressure.
Features (market-wide, identical for every asset at a bar; built from the same v236 flow features, known at the bar close):
  mk_btc_big_imb6, mk_btc_big_imb42   BTC's fl_big_imb6 / fl_big_imb42
  mk_mean_big_imb6                    mean over the five majors of fl_big_imb6 (the assets available at the bar)
  mk_mean_div6                        mean over the five majors of fl_div6 (large orders vs retail)
Members as in v236 (v144 builder, v202 quarterly wrapper); B members = T3 (unchanged). New features excluded from the vol models.
Fixed before running (everything else = v218 D2 settings: v216 G2 grid trader, sleeve budget 0.15, rung x1.75, minute-5 rule, limit
orders, SL market / TP limit, governor, aligned sleeve, Bybit fees, adverse funding):
  M1_add_market      A members = TV + per-asset flow (W2) + market-wide flow
  M2_market_only     A members = TV + market-wide flow (no per-asset flow)
Reference: v236_W2 (must reproduce dev4 5.774). SELECTION = robust criterion among M1, M2; the most recent year is scored once for the
selected row.

  python research/parallel/rounds/parallel-20260906-r2/v238/v238_market_flow.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v236 = _load("v236_m", RD / "v236/v236_whale_flow.py")
MK = ("mk_btc_big_imb6", "mk_btc_big_imb42", "mk_mean_big_imb6", "mk_mean_div6")


def frames(load_asset, per_asset: bool) -> pd.DataFrame:
    xf = v236.feature_frame(load_asset)  # TV + per-asset flow, per (t, sym)
    fl = list(v236.flm.FL)
    btc = xf[xf.sym == "BTCUSDT"].set_index("t")[["fl_big_imb6", "fl_big_imb42"]]
    mk = pd.DataFrame({"mk_btc_big_imb6": btc["fl_big_imb6"], "mk_btc_big_imb42": btc["fl_big_imb42"]})
    mk["mk_mean_big_imb6"] = xf.groupby("t")["fl_big_imb6"].mean()
    mk["mk_mean_div6"] = xf.groupby("t")["fl_div6"].mean()
    out = xf.merge(mk.reset_index(), on="t", how="left")
    return out if per_asset else out.drop(columns=fl)


def build_member(quarterly: bool, per_asset: bool):
    tag = f"{'q' if quarterly else 'a'}_m{int(per_asset)}"
    v202 = _load(f"v202_{tag}", RD / "v202/v202_quarterly_retrain.py")
    v144 = _load(f"v144_{tag}", RD / "v144/v144_deploy_v3.py")
    if quarterly:
        v202.quarterly(v144)
    ext, v103 = v144.v115.v114.v113, v144.v103
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    base92 = b92()
    xf = frames(ext.v92.load_asset, per_asset)
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
    base = {k: pd.read_parquet(C / f) for k, f in (("A", "member_A_whale.parquet"), ("Aq", "member_Aq_whale.parquet"),
                                                    ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    mixes = {"v236_W2": base}
    for key, per_asset in (("M1_add_market", True), ("M2_market_only", False)):
        mm = {"B": base["B"], "Bq": base["Bq"]}
        for name, q in (("A", False), ("Aq", True)):
            cache = C / f"member_{name}_{key}.parquet"
            if not cache.exists():
                build_member(q, per_asset).to_parquet(cache)
            mm[name] = pd.read_parquet(cache)
            print("member", name, key, "cached", flush=True)
        mixes[key] = mm
    prep = eu.prepare(books154, opens)
    pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    out = {"version": "v238", "rows": {}, "trades": {}}
    for key, mm in mixes.items():
        m = {k: v.reindex(idx).fillna(0.0)[cols] for k, v in mm.items()}
        books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
        ev = []
        r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol), win_start=5, events=ev, **v221.KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "v236_W2":
            assert abs(r["monthly_dev4"] - 5.774) < 0.002
    sel = v204.robust_select({k: out["rows"][k] for k in ("M1_add_market", "M2_market_only")})
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]],
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
    (HERE / "v238_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
