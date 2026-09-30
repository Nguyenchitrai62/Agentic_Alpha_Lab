"""v287: path-dependent (triple-barrier) labels for the flow member A - model diversity through the TARGET (registry v287).

Why: every member so far regresses the same target family - the vol-normalised open-to-open return over h bars (v92 h=42, v94
h=18/42/84, v103 h=6/18), clipped at +-4 sd. Trades, however, are executed with a stop-loss and a take-profit, so what matters is which
side of the price path is hit FIRST. v285 showed that a member carrying DIFFERENT information (Coinbase premium) lifts the weak dev
years at 20% weight, and v286 showed that making a member more similar to the others does not. Hypothesis: the same audited O1
features trained on a first-touch (path) target give a member that is diverse in its errors (it ignores the size of fat-tail moves and
the path after the first touch) and is good alone.
Label (replaces every return target inside the v144 builder - v92 'y', v94 'y18/y42/y84', v103 'y6/y18'; the horizon h, the anchors,
the embargo and the training filter 't + 4h (h + 1) < cutoff' are unchanged): entry = open of bar t+1; barrier B = vol42_t x sqrt(h)
(one sd over the horizon, the same unit as the old label); scan bars t+1 .. t+h: +1 if the high reaches entry x exp(+B) first, -1 if
the low reaches entry x exp(-B) first (both in one bar -> -1, stop-first), otherwise clip(log(open_{t+1+h} / entry) / B, -1, 1).
The window is exactly the old label's window (open t+1 .. open t+1+h, bar t+h's high/low end at that open) -> no new look-ahead.
OHLC from the builder's own loader (ext.load_asset_ext), merged on (sym, t); rows whose path is incomplete get NaN (not trained on).
Member = v240 O1 A member (4h TradingView + order-level flow; v144 builder; v202 quarterly wrapper) with the path label: PA / PAq.
Fixed before running (everything else = CB / C4 rules: G2 grid trader, close5 dip stops 4 sigma + 8-sigma backstop, budget 0.18,
v221.KW, minute-5 rule, limit entries, SL market / TP limit, Bybit fees, adverse funding):
  P1_add       books = 0.8 x CB + 0.2 x (PA + PAq)/2                      (the path member as an extra, diverse member)
  P2_replace   books = 0.8 x [0.5 (PA + B)/2 + 0.5 (PAq + Bq)/2] + 0.2 x (D + Dq)/2   (path label replaces the return label in A)
Reference: CB_ref = v285 D2 (must reproduce dev4 5.864). Builder check: with the label switch OFF the builder must reproduce
member_A_O1_orders exactly. SELECTION = v286 dev_select (v204 robust criterion, DD filter on 2021-2024 only) among P1, P2; the selected
row replaces CB only if dev_select prefers it over CB_ref. The most recent year is scored once, for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v287/v287_path_label_member.py
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


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v240 = _load("v240_p", RD / "v240/v240_order_level_flow.py")
v286 = _load("v286_p", RD / "v286/v286_coinbase_member_upgrade.py")


def path_label(o, hi, lo, vol, h):
    """First-touch label for entry at o[t+1] over bars t+1..t+h (arrays of one symbol's consecutive 4h bars)."""
    n = len(o)
    y = np.full(n, np.nan)
    m = n - 1 - h
    if m <= 0:
        return y
    e = o[1:m + 1]
    B = vol[:m] * np.sqrt(h)
    up, dn = e * np.exp(B), e * np.exp(-B)
    done = np.zeros(m, bool)
    lab = np.full(m, np.nan)
    bad = ~np.isfinite(B) | (B <= 0)
    for k in range(1, h + 1):
        H, L = hi[k:k + m], lo[k:k + m]
        bad |= ~np.isfinite(H) | ~np.isfinite(L)
        hd, hu = (L <= dn) & ~done, (H >= up) & ~done
        lab[hd] = -1.0  # stop-first when both barriers are inside one bar
        lab[hu & ~hd] = 1.0
        done |= hd | hu
    fin = np.clip(np.log(o[1 + h:1 + h + m] / e) / B, -1.0, 1.0)
    lab = np.where(done, lab, fin)
    lab[bad] = np.nan
    y[:m] = lab
    return y


def relabel(panel, specs, ohlc):
    """Replace return targets by path labels; specs = [(column, h)]; ohlc = {sym: DataFrame(open_time, high, low)}."""
    out = []
    for s, g in panel.groupby("sym", sort=False):
        g = g.sort_values("t").copy()
        x = ohlc[s].set_index("open_time").reindex(pd.DatetimeIndex(g["t"]))
        o, hi, lo, vol = g["open"].to_numpy(float), x["high"].to_numpy(float), x["low"].to_numpy(float), g["vol42"].to_numpy(float)
        gap = np.diff(g["t"].to_numpy()).astype("timedelta64[h]").astype(float)
        hi[1:][gap != 4], lo[1:][gap != 4] = np.nan, np.nan  # a missing bar breaks the path -> NaN label
        for col, h in specs:
            g[col] = path_label(o, hi, lo, vol, h)
        out.append(g)
    return pd.concat(out, ignore_index=True)


def build_member(quarterly: bool, path: bool):
    tag = f"{'q' if quarterly else 'a'}{int(path)}"
    v202 = _load(f"v202_p{tag}", RD / "v202/v202_quarterly_retrain.py")
    v144 = _load(f"v144_p{tag}", RD / "v144/v144_deploy_v3.py")
    if quarterly:
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
    if not path:
        ext.v92.build = lambda: base92.merge(xf, on=["t", "sym"], how="left")
        v103.build = lambda: b103().merge(xf, on=["t", "sym"], how="left")
        return v144.books_v142()[1]
    ohlc = {s: ext.load_asset_ext(s)[0][["open_time", "high", "low"]].drop_duplicates("open_time") for s in v240.SYMS}
    add94 = ext.v94.add_targets
    ext.v92.build = lambda: relabel(base92.merge(xf, on=["t", "sym"], how="left"), [("y", ext.v92.H)], ohlc)
    ext.v94.add_targets = lambda p: relabel(add94(p), [(f"y{h}", h) for h in ext.v94.HORIZONS], ohlc)
    v103.build = lambda: relabel(b103().merge(xf, on=["t", "sym"], how="left"), [(f"y{h}", h) for h in v103.HS], ohlc)
    return v144.books_v142()[1]


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    a_o1 = pd.read_parquet(C / "member_A_O1_orders.parquet")
    chk = build_member(False, False).reindex(a_o1.index)[list(a_o1.columns)]
    diff = float((chk - a_o1).abs().max().max())
    assert diff < 1e-12, f"builder does not reproduce member_A_O1_orders (max diff {diff})"
    print("builder check: member_A_O1_orders reproduced exactly", flush=True)
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    for name, q in (("PA", False), ("PAq", True)):
        cache = C / f"member_{name}_path.parquet"
        if not cache.exists():
            build_member(q, True).to_parquet(cache)
        m[name] = pd.read_parquet(cache).reindex(idx).fillna(0.0)[cols]
        print("member", name, "cached", flush=True)
    for k in ("A", "Aq"):
        pk = "P" + k
        c = pd.concat([m[k].stack(), m[pk].stack()], axis=1).corr().iloc[0, 1]
        print(f"book-weight corr {k} vs {pk}: {c:.3f}", flush=True)
    dm = 0.2 * (m["D"] + m["Dq"]) / 2
    c4 = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    cb = 0.8 * c4 + dm
    mixes = {"CB_ref": cb,
             "P1_add": 0.8 * cb + 0.2 * (m["PA"] + m["PAq"]) / 2,
             "P2_replace": 0.8 * (0.5 * (m["PA"] + m["B"]) / 2 + 0.5 * (m["PAq"] + m["Bq"]) / 2) + dm}
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    out = {"version": "v287", "rows": {}, "trades": {}}
    for key, bk in mixes.items():
        ev = []
        r = eu.simulate(bk, opens, prep, trade=trade, win_start=5, events=ev, **dict(v221.KW, **C4R))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "CB_ref":
            assert abs(r["monthly_dev4"] - 5.864) < 0.002
    sel = v286.dev_select({k: out["rows"][k] for k in ("P1_add", "P2_replace")}, v204.worst_month)
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
    (HERE / "v287_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
