"""v99 deployment candidate: 80% v96 books (v92 long-only + v94 long/short, 50/50, own vol targets) + 20% funding
carry x3, causal portfolio vol target 15% (cap 2x). OOS 2021-2026 (vectorised) plus hidden-year 1m execution.

Execution model for the trend books (hidden year): each 4h weight change of an asset is sent as a limit at that
bar's open; filled at the open (maker 0.0002) if any 1m bar in the first 15 minutes trades THROUGH it in the
order's favour, else at the minute-15 open with taker 0.0005 + 0.0002 slippage. Carry legs keep the carry_lab cost
model (0.0004 per leg per unit notional). Registry parallel-20260906-r2 / v99 (track C).

  python research/parallel/rounds/parallel-20260906-r2/v99/v99_candidate.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
W_BOOKS, W_CARRY, CARRY_LEV, TARGET, CAP = 0.8, 0.2, 3.0, 0.15, 2.0
HIDDEN = pd.Timestamp("2025-09-24", tz="UTC")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v92 = _load("v92", "v92/v92_pooled_hgb_vt.py")
v94 = _load("v94", "v94/v94_long_short_ensemble.py")
PD = v92.PD


def load_1m(sym):
    d = Path("data/raw/btc_intraday_20260924") if sym == "BTCUSDT" else Path("data/raw/majors_intraday_20260924")
    pat = "klines_1m_202[56].parquet" if sym == "BTCUSDT" else f"{sym}_1m_202[56].parquet"
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low"]) for f in sorted(d.glob(pat))])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    return m.drop_duplicates("open_time").set_index("open_time").sort_index()


def fill_prices(W: pd.DataFrame, o: pd.DataFrame) -> pd.DataFrame:
    """Per asset/bar execution price relative to the next bar open for the weight change decided at bar t."""
    rel = pd.DataFrame(0.0, index=W.index, columns=W.columns)
    maker = pd.DataFrame(True, index=W.index, columns=W.columns)
    dW = W.diff().fillna(W)
    for s in W.columns:
        m = load_1m(s)
        for t in dW.index[(dW[s].abs() > 1e-9) & (dW.index >= HIDDEN)]:
            fill_bar = t + pd.Timedelta(hours=4)  # decision at bar t close -> order at open of bar t+1
            w = m.loc[fill_bar: fill_bar + pd.Timedelta(minutes=14)]
            if len(w) < 15:
                continue
            p0 = w["open"].iloc[0]
            buy = dW.at[t, s] > 0
            through = (w["low"].iloc[1:] < p0).any() if buy else (w["high"].iloc[1:] > p0).any()
            if not through:
                px = m.loc[fill_bar + pd.Timedelta(minutes=15), "open"] if (fill_bar + pd.Timedelta(minutes=15)) in m.index else w["open"].iloc[-1]
                rel.at[t, s] = px / p0 - 1 + (0.0002 if buy else -0.0002)
                maker.at[t, s] = False
    return rel, maker


def main():
    panel = v92.build()
    v92.FEATS = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar")]
    lo = pd.concat([v92.train_predict(panel, a)[0] for a in v92.ANCHORS], ignore_index=True)
    W_lo = v92.weights_from(lo, "model")
    panel94 = v94.add_targets(v92.build())
    f94 = [c for c in panel94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls = pd.concat([v94.train_predict(panel94, a, f94)[0] for a in v92.ANCHORS], ignore_index=True)
    W_ls = v94.weights_ls(ls, True)
    idx = W_lo.index.union(W_ls.index)
    books = 0.5 * W_lo.reindex(idx).fillna(0.0).mul(v92.vol_target_scale(panel, W_lo).reindex(idx).fillna(1.0), axis=0) \
        + 0.5 * W_ls.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(panel94, W_ls).reindex(idx).fillna(1.0), axis=0)
    carry = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"].reindex(idx).fillna(0.0)
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(idx)
    realized = W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + W_CARRY * CARRY_LEV * carry.shift(1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)
    s = (TARGET / vol).clip(upper=CAP).fillna(1.0)
    Wt = books.mul(W_BOOKS * s, axis=0)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    carry_exp = W_CARRY * CARRY_LEV * s
    out = {"version": "v99", "fixed": dict(W_BOOKS=W_BOOKS, W_CARRY=W_CARRY, CARRY_LEV=CARRY_LEV, TARGET=TARGET, CAP=CAP)}

    def path(fee, slip, exec_rel=None):
        turn = Wt.diff().abs().sum(axis=1).fillna(Wt.abs().sum(axis=1))
        dW = Wt.diff().fillna(Wt)
        if exec_rel is None:
            cost = turn * (fee + slip)
        else:
            rel, maker = exec_rel
            fee_rate = np.where(maker.reindex_like(dW).to_numpy(), 0.0002, 0.0005)
            cost = pd.Series((dW.abs().to_numpy() * fee_rate).sum(axis=1), index=dW.index) + (dW * rel.reindex_like(dW).fillna(0.0)).sum(axis=1)
        net = (Wt * r_next).sum(axis=1) - cost - Wt.clip(lower=0).sum(axis=1) * 0.00005 \
            + carry_exp * carry - carry_exp.diff().abs().fillna(0.0) * 2 * 0.0004 / 1.2
        return net, turn

    for sc, (fee, slip) in v92.SCEN.items():
        net, turn = path(fee, slip)
        yearly = []
        for a in v92.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            m = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
            yearly.append(dict(anchor=a, **v92.stats(net[m], turn[m])))
        geo = np.prod([1 + y["net_pct"] / 100 for y in yearly]) ** (1 / 5) - 1
        out[sc] = dict(yearly=yearly, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3), worst_year_dd=max(y["max_drawdown_percent"] for y in yearly))
        print(sc, out[sc]["monthly_pct"], out[sc]["worst_year_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in yearly], flush=True)
    rel = fill_prices(Wt, o)
    net, turn = path(0.0, 0.0, rel)
    m = (net.index >= HIDDEN) & (net.index < HIDDEN + pd.Timedelta(days=365))
    maker_rate = float(rel[1][(Wt.diff().abs() > 1e-9) & (Wt.index >= HIDDEN)[:, None]].stack().mean())
    out["hidden_year_1m_execution"] = dict(**v92.stats(net[m], turn[m]), maker_fill_rate=round(maker_rate, 3))
    print("hidden-year 1m execution", out["hidden_year_1m_execution"])
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v99_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
