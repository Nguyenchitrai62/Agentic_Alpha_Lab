"""v124: hidden-year strict 1m execution of the v118 band-0.05 portfolio (registry parallel-20260906-r2 / v124).

v115 books, 15% portfolio vol target, ungoverned, per-asset no-trade band 0.05 (held weights from the v118 band rule,
applied continuously over the whole index instead of only inside the v110 live span; path differences before the
hidden year are possible). Orders = changes of the held weights. Hidden year 2025-09-24..2026-09-23 with the v104 strict fill rule (maker
0.0002 only on trade-through in minutes 2..14 after the execution-bar open, else taker 0.0005 at minute 15 + 0.0002
adverse; missing 1m bar = taker). Carry leg and long funding as v115. Reported next to the v115 (band 0) hidden-year
strict figure (+36.0%, DD 10.31%). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v124/v124_band_execution.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v118", HERE.parent / "v118" / "v118_no_trade_band.py")
v118 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v118)
v115, v99, v104 = v118.v115, v118.v99, v118.v115.v104
PD, BAND, TARGET = 6, 0.05, 0.15


def main():
    panel, books = v115.books_v115()
    idx = books.index
    carry = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"].reindex(idx).fillna(0.0)
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(idx)
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + v99.W_CARRY * v99.CARRY_LEV * carry.shift(1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)
    s = (TARGET / vol).clip(upper=v99.CAP).fillna(1.0)
    B = books.mul(v99.W_BOOKS * s, axis=0)
    held = np.zeros(B.shape[1])
    H = np.zeros(B.shape)
    for i, row in enumerate(B.to_numpy()):
        held = np.where(np.abs(row - held) > BAND, row, held)
        H[i] = held
    Wt = pd.DataFrame(H, index=idx, columns=B.columns)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    carry_exp = v99.W_CARRY * v99.CARRY_LEV * s
    rel, maker = v104.fill_strict(Wt)
    dW = Wt.diff().fillna(Wt)
    rate = np.where(maker.reindex_like(dW).to_numpy(), 0.0002, 0.0005)
    cost = pd.Series((dW.abs().to_numpy() * rate).sum(axis=1), index=idx) + (dW * rel.reindex_like(dW).fillna(0.0)).sum(axis=1)
    net = (Wt * r_next).sum(axis=1) - cost - Wt.clip(lower=0).sum(axis=1) * 0.00005 + carry_exp * carry - carry_exp.diff().abs().fillna(0.0) * 2 * 0.0004 / 1.2
    turn = dW.abs().sum(axis=1)
    mk = (idx >= v104.HIDDEN) & (idx < v104.HIDDEN + pd.Timedelta(days=365))
    orders = (dW.abs() > 1e-9) & (idx >= v104.HIDDEN)[:, None]
    out = {"version": "v124", "band": BAND, "target": TARGET,
           "primary_hidden_year_strict_band005": dict(**v104.v92.stats(net[mk], turn[mk]), maker_fill_rate=round(float(maker[orders].stack().mean()), 3), orders=int(orders.to_numpy().sum())),
           "reference_v115_band0": {"net_pct": 36.0, "max_drawdown_percent": 10.31, "maker_fill_rate": 0.853}}
    print(out["primary_hidden_year_strict_band005"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v124_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
