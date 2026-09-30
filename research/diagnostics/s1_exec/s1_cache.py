"""Walk-forward size-multiplier table of the deployed v295 S1 form (placement at the bar open) for the backend history (not a
selection input). For every holding bar T (2021-09-24 ..), major and rung: the multiplier from the models of the anchor year of T
(fits on pooled fills that exited before anchor - 7 days, exactly v295), state at the close of minute 0 of T.
Check (asserted): the engine with a lookup hook reproduces the s1_exec_m1 row S1_placement_m0 (dev4 6.168).
Output: artifacts/research/engine_real/v295_size_mult_m0.parquet (T, sym, rung, mult).
  python research/diagnostics/s1_exec/s1_cache.py
"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

RD = Path("research/parallel/rounds/parallel-20260906-r2")


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


v294 = L("v294_c", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
v221 = L("v221", RD / "v221/v221_grid_hysteresis.py"); eu, v216 = v221.eu, v221.v216
books154, opens = eu.er.v154_books(); cols, idx, C = list(books154.columns), books154.index, eu.er.CACHE
assets = {s: v293.Asset(s) for s in v293.MAJORS}; btc = assets["BTCUSDT"]
parts = []
for s in v293.MAJORS + v294.universe():
    A = assets[s] if s in assets else v293.Asset(s)
    d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc)
    if len(d):
        parts.append(d.assign(sym=s))
    del A
allf = pd.concat(parts, ignore_index=True)
X = allf[[f"x{q}" for q in range(7)]].to_numpy(float); y = np.clip(allf["y1.0"].to_numpy(float), -0.10, 0.08); half = (allf["j"] % 2).to_numpy()
anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
models, mus = {}, {}
for jj, a0 in enumerate(anchors):
    keep = np.asarray(allf.t_exit < a0 - v293.EMBARGO)
    mus[jj] = float(y[keep].mean())
    models[jj] = [HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0,
                                                random_state=10 * jj + h).fit(X[keep & (half == h)], y[keep & (half == h)]) for h in (0, 1)]
rows = []
for s, A in assets.items():
    for j, T in enumerate(A.t0):
        if T < anchors[0] or not np.isfinite(A.sig[j]):
            continue
        jj = max(q for q, a0 in enumerate(anchors) if T >= a0)
        kk = j * 240
        base = [A.sp30(kk), 0.0, A.volreg[j], A.trend[j], btc.sp30(kk),
                np.log(A.C[kk] / A.hmax24[kk]) / A.sig[j] if A.hmax24[kk] > 0 else np.nan, T.hour]
        for r, k in enumerate(v293.RUNGS):
            x = np.array([base[:1] + [k] + base[2:]], float)
            pa, pb = (mm.predict(x)[0] for mm in models[jj])
            mult = 1.5 if (pa > 2 * mus[jj] and pb > 2 * mus[jj]) else (0.5 if (pa < 0 and pb < 0) else 1.0)
            rows.append((T, s, r, mult))
tab = pd.DataFrame(rows, columns=["T", "sym", "rung", "mult"])
look = {(T, s, r): m_ for T, s, r, m_ in rows}
m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
cb = 0.8 * (0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2) + 0.2 * (m["D"] + m["Dq"]) / 2
hook = lambda i, a, r, f: look.get((idx[i] + pd.Timedelta(hours=4), cols[a], r), 1.0)
res = eu.simulate(cb, opens, eu.prepare(books154, opens), trade=dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL)), win_start=5,
                  sleeve_fill_size=hook, **dict(v221.KW, **v293.C4R))
print("lookup engine dev4", res["monthly_dev4"], "5y", res["monthly_5y"], "last", res["monthly_last_year"], "DD", res["gate_dd"], flush=True)
assert abs(res["monthly_dev4"] - 6.168) < 0.002, "lookup table does not reproduce S1_placement_m0"
out = C / "v295_size_mult_m0.parquet"
tab.to_parquet(out)
print("saved", out, len(tab), tab.mult.value_counts().to_dict())
