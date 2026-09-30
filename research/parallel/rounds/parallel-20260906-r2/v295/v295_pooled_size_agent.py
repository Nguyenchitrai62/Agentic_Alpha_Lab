"""v295: RL trader decision "how much" - a size agent for every filled dip rung, trained on 35 coins' experience (registry v295).

Why: v279 found that sizing each dip rung at the fill by the pre-fill drop speed gave the best dev rows ever (on M1: dev4 6.25, worst
dev year 3.44, DD 18.7) but did not transfer to the most recent year (3.90 vs 4.65) - fitted on the five majors' own history, it
learned a regime. v293 / v294 showed that pooling dip experience across coins makes a learned dip decision steadier (worst dev year of
the take-profit agent 2.50 -> 2.85 -> 2.93 with 5 -> 11 -> 35 coins). Here the decision is the size: the same pooled, survivorship-free
experience (majors + U2020 alts, v294 data) and the same seven state features known at minute f-1 predict the net return of the rung
under the default exit (TP 1 sigma, close5 4-sigma stop, 8-sigma backstop, timeout), and the agent scales the rung (engine hook
sleeve_fill_size, applied before the sleeve risk-budget check; exits unchanged).
Model: HistGradientBoostingRegressor (depth 3, lr 0.05, 200 iter, min leaf 200, l2 1.0) on the clipped net return y1.0, cross-fitted on
even / odd bars; for the year starting at anchor Y only fills that EXITED before Y - 7 days; mu_Y = mean y1.0 of that training set.
Fixed before running:
  S1_up_down   x1.5 if both halves predict > 2 mu_Y; x0.5 if both predict < 0; else x1.0
  S2_down_only x0.5 if both halves predict < 0; else x1.0 (never adds risk)
Reference: CB_ref (must reproduce dev4 5.864). SELECTION = v286.dev_select among S1, S2; replaces CB only if dev_select prefers it over
CB_ref; the most recent year is scored once for the selected row. Data, replica and fidelity check exactly as v294.

  python research/parallel/rounds/parallel-20260906-r2/v295/v295_pooled_size_agent.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
RD = HERE.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v294 = _load("v294_s", RD / "v294/v294_wide_pool_exit_agent.py")
v293 = v294.v293


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_s", RD / "v286/v286_coinbase_member_upgrade.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols, idx, C = list(books154.columns), books154.index, eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    cb = 0.8 * (0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2) + 0.2 * (m["D"] + m["Dq"]) / 2
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    kw = dict(v221.KW, **v293.C4R)
    U = v294.universe()
    assets = {s: v293.Asset(s) for s in v293.MAJORS}
    btc = assets["BTCUSDT"]
    data = {}
    for s in v293.MAJORS + U:
        A = assets[s] if s in assets else v293.Asset(s)
        d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc).assign(sym=s)
        if len(d):
            data[s] = d
        del A
    print("fills", sum(len(d) for d in data.values()), "assets", len(data), flush=True)

    ev = []
    ref = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, **kw)
    assert abs(ref["monthly_dev4"] - 5.864) < 0.002
    pend, eng = {}, []
    for e in ev:
        if e["kind"] == "rung_fill":
            pend[e["symbol"]] = e
        elif e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and e["symbol"] in pend:
            f0 = pend.pop(e["symbol"])
            eng.append((e["symbol"], f0["t"], f0["rung"], float(e["ret"])))
    eng = [e for e in eng if e[1] >= idx[0] + pd.Timedelta(days=60)]
    look = {(s, t, v293.RUNGS[int(r)]): y for s, d in data.items() if s in v293.MAJORS for t, r, y in zip(d.t_fill, d.r, d["y1.0"])}
    diffs = np.array([abs(look[(s, t, rg)] - ret) if (s, t, rg) in look else np.inf for s, t, rg, ret in eng])
    share, mad = float((diffs < 1e-4).mean()), float(diffs[np.isfinite(diffs)].mean())
    print(f"fidelity: engine rungs {len(eng)}, within 1e-4 {share:.4f}, mean |diff| {mad:.2e}", flush=True)
    assert share >= 0.97 and mad < 2e-4

    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    allf = pd.concat(data.values(), ignore_index=True)
    X = allf[[f"x{q}" for q in range(7)]].to_numpy(float)
    y = np.clip(allf["y1.0"].to_numpy(float), -0.10, 0.08)
    half = (allf["j"] % 2).to_numpy()
    models, mus = {}, {}
    out = {"version": "v295", "fidelity_share_1e-4": round(share, 4), "fills": int(len(allf)), "train": {}, "mu": {}, "rows": {}, "trades": {}}
    for jj, a0 in enumerate(anchors):
        keep = np.asarray(allf.t_exit < a0 - v293.EMBARGO)
        mus[jj] = float(y[keep].mean())
        models[jj] = [HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0,
                                                    random_state=10 * jj + h).fit(X[keep & (half == h)], y[keep & (half == h)]) for h in (0, 1)]
        out["train"][str(a0.date())], out["mu"][str(a0.date())] = int(keep.sum()), round(mus[jj], 5)
    print("train rows", out["train"], "mu", out["mu"], flush=True)
    pos = pd.Series(np.arange(len(btc.t0)), index=btc.t0)

    def agent(up):
        stats = {"asked": 0, "up": 0, "down": 0}

        def pol(i, a, r, f):
            T = idx[i] + pd.Timedelta(hours=4)
            jj = max([q for q, a0 in enumerate(anchors) if T >= a0], default=None)
            if jj is None or T not in pos.index:
                return 1.0
            A, j = assets[cols[a]], int(pos[T])
            kk = j * 240 + f - 1
            sg = A.sig[j]
            x = np.array([[A.sp30(kk), v293.RUNGS[r], A.volreg[j], A.trend[j], btc.sp30(kk),
                           np.log(A.C[kk] / A.hmax24[kk]) / sg if A.hmax24[kk] > 0 else np.nan, (A.t0[j].hour + f // 60) % 24]])
            pa, pb = (mm.predict(x)[0] for mm in models[jj])
            stats["asked"] += 1
            if up and pa > 2 * mus[jj] and pb > 2 * mus[jj]:
                stats["up"] += 1
                return 1.5
            if pa < 0 and pb < 0:
                stats["down"] += 1
                return 0.5
            return 1.0
        pol.stats = stats
        return pol

    ref["worst_dev_month_pct"] = round(v204.worst_month(ref), 3)
    ref["dev_dd"] = v286.dev_dd(ref)
    out["rows"]["CB_ref"], out["trades"]["CB_ref"] = ref, v213.trade_stats(ev)
    for key, up in (("S1_up_down", True), ("S2_down_only", False)):
        hook = agent(up)
        ev = []
        r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, sleeve_fill_size=hook, **kw)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        r["agent"] = dict(hook.stats)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y_["anchor"][:4], y_["net_pct"], y_["dd_1m_pct"]) for y_ in r["yearly"][:4]],
              "agent", r["agent"], flush=True)
    sel = v286.dev_select({k: out["rows"][k] for k in ("S1_up_down", "S2_down_only")}, v204.worst_month)
    out["selected"] = sel
    out["replaces_cb"] = v286.dev_select({k: out["rows"][k] for k in ("CB_ref", sel)}, v204.worst_month) == sel
    s_ = out["rows"][sel]
    out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                   "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                   "yearly": [(y_["anchor"][:4], y_["net_pct"], y_["dd_1m_pct"]) for y_ in s_["yearly"]],
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
    (HERE / "v295_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
