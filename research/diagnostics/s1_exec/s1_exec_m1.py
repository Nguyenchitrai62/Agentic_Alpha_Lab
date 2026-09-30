"""Leader diagnostic (post-selection executability of v295 S1; not a selection input): the S1 size agent with its state taken
LAG minutes earlier (a bot amending resting-order sizes late) or once at ladder placement (state at minute 15 of the bar).
Same data, models and engine arguments as v295 (code generated from v295/v295_pooled_size_agent.py; only the state minute changes).
  python research/diagnostics/s1_exec/s1_exec.py
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
RD = Path("research/parallel/rounds/parallel-20260906-r2")


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

    def agent(up, lag=0, placement=False, pm=15):
        stats = {"asked": 0, "up": 0, "down": 0}

        def pol(i, a, r, f):
            T = idx[i] + pd.Timedelta(hours=4)
            jj = max([q for q, a0 in enumerate(anchors) if T >= a0], default=None)
            if jj is None or T not in pos.index:
                return 1.0
            A, j = assets[cols[a]], int(pos[T])
            kk = j * 240 + (pm if placement else f - 1 - lag)
            sg = A.sig[j]
            x = np.array([[A.sp30(kk), v293.RUNGS[r], A.volreg[j], A.trend[j], btc.sp30(kk),
                           np.log(A.C[kk] / A.hmax24[kk]) / sg if A.hmax24[kk] > 0 else np.nan, (A.t0[j].hour + (pm if placement else f) // 60) % 24]])
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
    for key, up, lag, plc, pm in (("S1_placement_m0", True, 0, True, 0),):
        hook = agent(up, lag, plc, pm)
        ev = []
        r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, sleeve_fill_size=hook, **kw)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        r["agent"] = dict(hook.stats)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y_["anchor"][:4], y_["net_pct"], y_["dd_1m_pct"]) for y_ in r["yearly"][:4]],
              "agent", r["agent"], flush=True)
    rows = {k: {f: v.get(f) for f in ("monthly_dev4", "worst_dev_month_pct", "dev_dd", "monthly_5y", "monthly_last_year", "gate_dd", "agent")}
            for k, v in out["rows"].items()}
    print("SUMMARY", json.dumps(rows, default=str), flush=True)
    Path("research/diagnostics/s1_exec/s1_exec_m1.json").write_text(json.dumps(rows, indent=1, default=str))


if __name__ == "__main__":
    main()
