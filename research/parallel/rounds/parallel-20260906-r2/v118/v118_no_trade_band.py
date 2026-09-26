"""v118: no-trade band on the final v115 portfolio weights (registry parallel-20260906-r2 / v118, track C).

v115 primary (books from the v115 code path, 15% portfolio vol target, ungoverned, v110 cost/carry conventions) with a
per-asset no-trade band: the held weight h_i changes to the target w_i only when |w_i - h_i| > band (then h_i = w_i);
band = 0.02 (primary) or 0.05 (secondary) of equity; band = 0 reproduces v115. Carry exposure unchanged. Sequential
simulation over the v110 live span. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v118/v118_no_trade_band.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v115 = _load("v115", "v115/v115_candidate.py")
v110, v99 = v115.v110, v115.v99
PD = 6


def run_band(panel, books, band, fee, slip, target=0.15):
    idx = books.index
    carry = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"].reindex(idx).fillna(0.0)
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(idx)
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + v99.W_CARRY * v99.CARRY_LEV * carry.shift(1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)
    s = (target / vol).clip(upper=v99.CAP).fillna(1.0)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0).to_numpy()
    B = books.mul(v99.W_BOOKS * s, axis=0).to_numpy()
    cexp = (v99.W_CARRY * v99.CARRY_LEV * s).to_numpy()
    cr = carry.to_numpy()
    live = (idx >= v110.START) & (idx < v110.END)
    n = len(idx)
    net, turn = np.zeros(n), np.zeros(n)
    held = np.zeros(B.shape[1])
    prev_c = 0.0
    for i in range(n):
        tgt = B[i] if live[i] else np.zeros(B.shape[1])
        new = np.where(np.abs(tgt - held) > band, tgt, held) if live[i] else tgt
        c = cexp[i] if live[i] else 0.0
        turn[i] = np.abs(new - held).sum()
        net[i] = (new * r_next[i]).sum() - turn[i] * (fee + slip) - np.clip(new, 0, None).sum() * 0.00005 + c * cr[i] - abs(c - prev_c) * 2 * 0.0004 / 1.2
        held, prev_c = new, c
    return pd.Series(net, index=idx), pd.Series(turn, index=idx), pd.Series(1.0, index=idx)


def main():
    panel, books = v115.books_v115()
    out = {"version": "v118"}
    for key, band in (("primary_band002", 0.02), ("secondary_band005", 0.05), ("reference_band0_v115", 0.0)):
        res = {}
        for sc, (fee, slip) in v115.v104.v92.SCEN.items():
            res[sc] = v110.summarize(*run_band(panel, books, band, fee, slip))
            print(key, sc, res[sc]["monthly_pct"], "fullDD", res[sc]["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"], y["fills"]) for y in res[sc]["yearly"]], flush=True)
        out[key] = res
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v118_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
