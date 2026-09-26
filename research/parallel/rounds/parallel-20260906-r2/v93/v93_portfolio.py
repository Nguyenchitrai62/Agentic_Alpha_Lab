"""v93: v92 model book (70% capital) + majors funding carry sleeve (30%, 3x notional) with a causal
portfolio volatility target of 15% annual (cap 2x). All fixed before evaluation (registry v93).

Model book: v92 continuous OOS predictions -> v92 weights (unscaled). Carry: OOS 4h returns from
scripts/carry_lab.py (selection before each anchor, fee 0.0004 per leg, capital 1.2 per notional).
Portfolio scale s_t = min(2, 0.15 / vol_t), vol_t = std of the last 60 days of realised unscaled
portfolio returns (shifted one bar). Model-book costs are charged on scaled turnover; carry rescaling
pays 2 legs x 0.0004 on its notional change.

  python research/parallel/rounds/parallel-20260906-r2/v93/v93_portfolio.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
V92 = HERE.parent / "v92" / "v92_pooled_hgb_vt.py"
spec = importlib.util.spec_from_file_location("v92", V92)
v92 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v92)

W_MODEL, W_CARRY, CARRY_LEV, TARGET, CAP = 0.7, 0.3, 3.0, 0.15, 2.0
PD = v92.PD


def main():
    panel = v92.build()
    v92.FEATS = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar")]
    oos = pd.concat([v92.train_predict(panel, a)[0] for a in v92.ANCHORS], ignore_index=True)
    W = v92.weights_from(oos, "model")
    carry = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"].reindex(W.index).fillna(0.0)
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(W.index)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    # unscaled portfolio return realised by bar t (weights decided at t-2 earn open t-1 -> open t)
    realized = W_MODEL * (W.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + W_CARRY * CARRY_LEV * carry.shift(1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)
    s = (TARGET / vol).clip(upper=CAP).fillna(1.0)
    out = {"version": "v93", "fixed": dict(W_MODEL=W_MODEL, W_CARRY=W_CARRY, CARRY_LEV=CARRY_LEV, TARGET=TARGET, CAP=CAP), "anchors": []}
    for sc, (fee, slip) in v92.SCEN.items():
        Wm = W.mul(W_MODEL * s, axis=0)
        turn = Wm.diff().abs().sum(axis=1).fillna(Wm.abs().sum(axis=1))
        long_funding = Wm.clip(lower=0).sum(axis=1) * 0.00005
        model_net = (Wm * r_next).sum(axis=1) - turn * (fee + slip) - long_funding
        carry_exposure = W_CARRY * CARRY_LEV * s
        carry_net = carry_exposure * carry - carry_exposure.diff().abs().fillna(0.0) * 2 * 0.0004 / 1.2
        net = model_net + carry_net
        yearly = []
        for a in v92.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            m = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
            yearly.append(dict(anchor=a, **v92.stats(net[m], turn[m])))
        nets = [y["net_pct"] for y in yearly]
        geo = np.prod([1 + x / 100 for x in nets]) ** (1 / len(nets)) - 1
        out[sc] = dict(yearly=yearly, geometric_annual_pct=round(100 * geo, 2), monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
                       worst_year_dd=max(y["max_drawdown_percent"] for y in yearly), mean_scale=round(float(s.mean()), 3))
        print(sc, {k: v for k, v in out[sc].items() if k != "yearly"}, [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in yearly], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v93_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
