"""v351: NEW INFORMATION - Binance delivery-futures (quarterly) basis in the book member A, scored on the deployed MANUAL structure M3 (registry v351).

Not tried before: the spot-vs-perp basis (v130), perp premium / predicted funding (v231 diagnostics, data leaderboard) and Coinbase premium were
tested; the TERM STRUCTURE of the quarterly delivery contracts was not. Data (OpenCode worker, scripts/fetch_quarterly_basis.py ->
data/raw/qbasis_20261003, artifacts/research/engine_real/qbasis_features_4h.parquet; public data.binance.vision archive): per coin and hour, the
annualised basis of the front delivery contract (roll 7 days before expiry) vs the perp, the next-minus-front slope and the 24h change, taken at
each 4h close (only bars closed by then).
FEATURES (fixed before running; market-wide so every coin has the same availability, no staggered-NaN time proxy): btc_qb_front, btc_qb_slope,
btc_qb_chg24, eth_qb_front (BTC / ETH rows of the table, joined on the 4h bar).
MEMBER: A_qb = the v240 O1 A member (v144 builder, TV + Binance order-level flow; annual v144 + quarterly v202 retrains, same windows / embargo)
with the four features added (excluded from the vol models, as v244). Books CB_qb = (2 A_qb + 2 B + D)/5.
ROWS (M3 structure fixed: book x0.75, pullback 0.75 sigma / 3 bars, bracket dip limits 3.0 / 4.0 sigma, size_mult 4.375, touch stop 8 sigma,
budget 0.26, R2 agents; kpack inputs for the engine):  M3 = CB books (reference dev4 6.233)  |  QB1 = CB_qb books.
CHOICE as v347-v350 (MANUAL fitness, all-trade win): dev folds k = 2, 3 on years [:k]; TRANSFER if QB1 is chosen and beats M3 on the unseen dev
year in both folds; final on dev4; most recent year once. Secondary row (reported, never chosen on): the BOT R2 with CB_qb books.

  python research/parallel/rounds/parallel-20260906-r2/v351/v351_quarterly_basis_member.py      (builds the members, then scores with KPACK)
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
C = Path("artifacts/research/engine_real")
QB = C / "qbasis_features_4h.parquet"
FEATS = ("btc_qb_front", "btc_qb_slope", "btc_qb_chg24", "eth_qb_front")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def market_features() -> pd.DataFrame:
    q = pd.read_parquet(QB)
    q["t"] = pd.to_datetime(q["open_time"], utc=True)
    b = q[q.sym == "BTCUSDT"].set_index("t")[["qb_front", "qb_slope", "qb_chg24"]].add_prefix("btc_")
    e = q[q.sym == "ETHUSDT"].set_index("t")[["qb_front"]].add_prefix("eth_")
    return b.join(e, how="outer").sort_index()


def build_member(quarterly: bool):
    tag = "q" if quarterly else "a"
    v240 = _load(f"v240_qb{tag}", RD / "v240/v240_order_level_flow.py")
    flo, tvm, SYMS = v240.flo, v240.tvm, v240.SYMS
    v202 = _load(f"v202_qb{tag}", RD / "v202/v202_quarterly_retrain.py")
    v144 = _load(f"v144_qb{tag}", RD / "v144/v144_deploy_v3.py")
    if quarterly:
        v202.quarterly(v144)
    ext, v103 = v144.v115.v114.v113, v144.v103
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    base92 = b92()
    mk = market_features()
    rows = []
    for s in SYMS:
        b, _, _ = ext.v92.load_asset(s)
        t = pd.DatetimeIndex(b["open_time"])
        parts = [pd.DataFrame({"t": t, "sym": s}), tvm.tv_features(b).reset_index(drop=True), flo.flow_features(s, t).reset_index(drop=True),
                 mk.reindex(t).reset_index(drop=True)[list(FEATS)]]
        rows.append(pd.concat(parts, axis=1))
    xf = pd.concat(rows, ignore_index=True)
    drop = {c for c in xf.columns if c not in ("t", "sym")}
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in drop], anchors, emb)
    ext.v92.build = lambda: base92.merge(xf, on=["t", "sym"], how="left")
    v103.build = lambda: b103().merge(xf, on=["t", "sym"], how="left")
    return v144.books_v142()[1]


def score():
    v347 = _load("v347_qb", RD / "v347/v347_member_weight_evolution.py")
    v347.init_worker()
    W0 = v347.W["v310"].W
    idx, cols = W0["idx"], W0["cols"]
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols].to_numpy(float)
    A_qb = (rd("member_A_qb.parquet") + rd("member_Aq_qb.parquet")) / 2
    X = v347.W["X"]
    res = {"M3": v347.run_genome(v347.encode(v347.SEEDS["CB"]))}
    keepA = X["wA"]
    X["wA"] = A_qb
    res["QB1"] = v347.run_genome(v347.encode(v347.SEEDS["CB"]))
    X["wA"] = keepA
    assert abs(v347.W_metrics(res["M3"], [0, 1, 2, 3])["R"] - 6.233) < 0.003
    out = {"version": "v351", "rows": {k: dict(dev4=v347.W_metrics(r, [0, 1, 2, 3]), F=round(v347.fitness(r, [0, 1, 2, 3]), 4),
                                               years=[v347.W_metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        print(k, "dev4", v["dev4"], "F", v["F"], flush=True)
    gains = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v347.fitness(res[x], ys))
        f_ch, f0 = v347.f_single(res[ch], [k]), v347.f_single(res["M3"], [k])
        out["folds"][k] = dict(choice=ch, test=dict(v347.W_metrics(res[ch], [k]), F=round(f_ch, 4)), m3_F=round(f0, 4))
        gains.append(ch != "M3" and f_ch > f0)
        print("FOLD", k, ch, out["folds"][k]["test"], "vs M3", round(f0, 4), flush=True)
    out["transfer"] = bool(all(gains))
    print("TRANSFER", out["transfer"], flush=True)
    ch = max(res, key=lambda x: v347.fitness(res[x], [0, 1, 2, 3]))
    if ch == "QB1":
        X["wA"] = A_qb
    full = v347.run_genome(v347.encode(v347.SEEDS["CB"]), True)
    X["wA"] = keepA
    out["final"] = dict(choice=ch, dev4=v347.W_metrics(res[ch], [0, 1, 2, 3]), last_year=v347.W_metrics(full, [4]),
                        five_years=v347.W_metrics(full, [0, 1, 2, 3, 4]), full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("FINAL", json.dumps(out["final"], default=str), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v351_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "score":
        return score()
    for name, q in (("A", False), ("Aq", True)):
        p = C / f"member_{name}_qb.parquet"
        if not p.exists():
            build_member(q).to_parquet(p)
        print("member", name, "ready", flush=True)
    env = dict(os.environ, KPACK="artifacts/kaggle/kpack/pack347")
    subprocess.run([sys.executable, __file__, "score"], env=env, check=True)


if __name__ == "__main__":
    main()
