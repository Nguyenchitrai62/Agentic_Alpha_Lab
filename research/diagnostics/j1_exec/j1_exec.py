"""Leader diagnostic (post-selection executability of v296 J1; not a selection input): the J1 agents (size + take-profit) deciding once
at the bar open (state at the close of minute 0 of the holding bar, as the deployed CS pipeline does), compared with J1 at the fill and
with the deployed CS form (S1 size only at the bar open: 5y 5.987, last 5.266, DD 17.20).
  python research/diagnostics/j1_exec/j1_exec.py
"""
import importlib.util, json
from pathlib import Path
import numpy as np
import pandas as pd

RD = Path("research/parallel/rounds/parallel-20260906-r2")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v297 = _load("v297_x", RD / "v297/v297_risk_realloc.py")
v296, v294, v293 = v297.v296, v297.v294, v297.v293


def build_j1_hooks(eu, idx, cols, pm=None):
    """The v296 J1 agents (size S1 rule + X4 take-profit), fitted exactly as v296."""
    U = v294.universe()
    assets = {s: v293.Asset(s) for s in v293.MAJORS}
    btc = assets["BTCUSDT"]
    parts = []
    for s in v293.MAJORS + U:
        A = assets[s] if s in assets else v293.Asset(s)
        d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc).assign(sym=s)
        if len(d):
            parts.append(d)
        del A
    allf = pd.concat(parts, ignore_index=True)
    X = allf[[f"x{q}" for q in range(7)]].to_numpy(float)
    Y = np.clip(allf[[f"y{mu}" for mu in v293.ACTIONS]].to_numpy(float), -0.10, 0.08)
    y1 = Y[:, v293.ACTIONS.index(1.0)]
    half = (allf["j"] % 2).to_numpy()
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    size_m, tp_m, mus = {}, {}, {}
    for jj, a0 in enumerate(anchors):
        keep = np.asarray(allf.t_exit < a0 - v293.EMBARGO)
        mus[jj] = float(y1[keep].mean())
        size_m[jj] = [v296.hgb(10 * jj + h).fit(X[keep & (half == h)], y1[keep & (half == h)]) for h in (0, 1)]
        tp_m[jj] = [[v296.hgb(10 * jj + h + 3 * c).fit(X[keep & (half == h)], Y[keep & (half == h), c]) for c in range(len(v293.ACTIONS))]
                    for h in (0, 1)]
    pos = pd.Series(np.arange(len(btc.t0)), index=btc.t0)
    base = v293.ACTIONS.index(1.0)

    def state(i, a, r, f):
        T = idx[i] + pd.Timedelta(hours=4)
        jj = max([q for q, a0 in enumerate(anchors) if T >= a0], default=None)
        if jj is None or T not in pos.index:
            return None, None
        A, j = assets[cols[a]], int(pos[T])
        kk = j * 240 + (f - 1 if pm is None else pm)
        sg = A.sig[j]
        return jj, np.array([[A.sp30(kk), v293.RUNGS[r], A.volreg[j], A.trend[j], btc.sp30(kk),
                              np.log(A.C[kk] / A.hmax24[kk]) / sg if A.hmax24[kk] > 0 else np.nan, (A.t0[j].hour + (f if pm is None else pm) // 60) % 24]])

    def size(i, a, r, f):
        jj, x = state(i, a, r, f)
        if jj is None:
            return 1.0
        pa, pb = (mm.predict(x)[0] for mm in size_m[jj])
        mu = mus[jj]
        return 1.5 if (pa > 2 * mu and pb > 2 * mu) else (0.5 if (pa < 0 and pb < 0) else 1.0)

    def tp(i, a, r, f):
        jj, x = state(i, a, r, f)
        if jj is None:
            return 1.0
        pa = np.array([mm.predict(x)[0] for mm in tp_m[jj][0]])
        pb = np.array([mm.predict(x)[0] for mm in tp_m[jj][1]])
        ba, bb = int(np.argmax(pa)), int(np.argmax(pb))
        if ba == bb and ba != base and pa[ba] - pa[base] > 0.0010 and pb[bb] - pb[base] > 0.0010:
            return v293.ACTIONS[ba]
        return 1.0
    return size, tp



def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_x", RD / "v286/v286_coinbase_member_upgrade.py")
    eu, v216, v204 = v221.eu, v221.v216, v221.v204
    books154, opens = eu.er.v154_books()
    cols, idx, C = list(books154.columns), books154.index, eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    cb = 0.8 * (0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2) + 0.2 * (m["D"] + m["Dq"]) / 2
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    out = {}
    for key, pm, use_tp in (("J1_fill", None, True), ("J1_bar_open", 0, True), ("S1_bar_open_check", 0, False)):
        size, tp = build_j1_hooks(eu, idx, cols, pm)
        hk = dict(sleeve_fill_size=size, **({"sleeve_tp": tp} if use_tp else {}))
        r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, **hk, **dict(v221.KW, **v293.C4R))
        out[key] = dict(dev4=r["monthly_dev4"], worst=round(v204.worst_month(r), 3), dev_dd=v286.dev_dd(r), y5=r["monthly_5y"],
                        last=r["monthly_last_year"], gate_dd=r["gate_dd"])
        print(key, out[key], flush=True)
    Path("research/diagnostics/j1_exec/j1_exec.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
