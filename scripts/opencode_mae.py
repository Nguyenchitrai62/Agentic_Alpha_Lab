"""Opencode v72 L1 MAE metric (FIRST-EVER in this program).

Per filled trade, adverse/favourable excursion from entry during holding,
from data/processed/swing_regime_research_v4/candles.parquet:

  window = candles.iloc[entry_index:exit_index+1]  (engine-sorted reset-index, inclusive)
  LONG : MAE = max(0, (entry - min_low)/entry) ; MFE = max(0, (max_high - entry)/entry)
  SHORT: MAE = max(0, (max_high - entry)/entry); MFE = max(0, (entry - min_low)/entry)

Fractions (0.01 = 1%). Filled trades only. No live orders; local only.
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

TOL = 1e-12


def _rows(trades):
    """Normalize list[Trade] | DataFrame | list[dict] -> DataFrame with required cols."""
    if isinstance(trades, pd.DataFrame):
        df = trades.copy()
    else:
        recs = []
        for t in trades:
            recs.append(t if isinstance(t, dict) else t.__dict__ if hasattr(t, "__dict__") else dict(t))
        df = pd.DataFrame(recs)
    need = {"direction", "entry_index", "exit_index", "entry_price"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"thieu cot trade: {sorted(missing)}")
    return df


def mae_mfe_for_trades(trades, candles):
    """Trade list + candles -> DataFrame[signal_index?, direction, entry/exit, mae_frac, mfe_frac].

    candles: DataFrame with high/low, positional index == engine run_backtest index
    (candles.sort_values('open_time').reset_index(drop=True)).
    """
    df = _rows(trades)
    if not {"high", "low"} <= set(candles.columns):
        raise ValueError("candles thieu high/low")
    out = []
    n = len(candles)
    for i, r in df.iterrows():
        direction = int(r["direction"])
        if direction not in (-1, 1):
            raise ValueError(f"direction invalid row {i}: {direction}")
        ei, xi = int(r["entry_index"]), int(r["exit_index"])
        entry = float(r["entry_price"])
        if not np.isfinite(entry) or entry <= 0:
            raise ValueError(f"entry_price invalid row {i}: {entry}")
        if not (0 <= ei < n and 0 <= xi < n):
            raise ValueError(f"index ngoai candles row {i}: {ei}->{xi} (n={n})")
        if xi < ei:
            raise ValueError(f"exit<entry row {i}: {ei}->{xi}")
        win = candles.iloc[ei:xi + 1]
        min_low = float(win["low"].min())
        max_high = float(win["high"].max())
        if direction == 1:
            mae = max(0.0, (entry - min_low) / entry)
            mfe = max(0.0, (max_high - entry) / entry)
        else:
            mae = max(0.0, (max_high - entry) / entry)
            mfe = max(0.0, (entry - min_low) / entry)
        rec = {"direction": direction, "entry_index": ei, "exit_index": xi,
               "entry_price": entry, "mae_frac": float(mae), "mfe_frac": float(mfe)}
        for c in ("signal_index", "entry_time", "exit_time", "exit_reason",
                  "net_pnl", "equity_before", "gross_pnl", "fees", "funding"):
            if c in df.columns:
                rec[c] = r[c]
        out.append(rec)
    cols = ["signal_index", "direction", "entry_index", "exit_index", "entry_price",
            "mae_frac", "mfe_frac", "entry_time", "exit_time", "exit_reason",
            "net_pnl", "equity_before", "gross_pnl", "fees", "funding"]
    frame = pd.DataFrame(out)
    return frame[[c for c in cols if c in frame.columns]]


def mae_distribution(frame):
    """mean/p50/p90/max + MAE-vs-realized scatter stats (exploratory)."""
    x = np.asarray(frame["mae_frac"], dtype=float)
    stats = {"n": int(len(x))}
    if not len(x):
        return {**stats, "note": "0 filled trades"}
    stats.update({"mae_mean": float(x.mean()), "mae_p50": float(np.quantile(x, 0.5)),
                  "mae_p90": float(np.quantile(x, 0.9)), "mae_max": float(x.max()),
                  "mae_min": float(x.min()), "mae_std": float(x.std())})
    if "mfe_frac" in frame.columns:
        m = np.asarray(frame["mfe_frac"], dtype=float)
        stats.update({"mfe_mean": float(m.mean()), "mfe_p50": float(np.quantile(m, 0.5)),
                      "mfe_p90": float(np.quantile(m, 0.9)), "mfe_max": float(m.max())})
    if {"net_pnl", "equity_before"} <= set(frame.columns) and len(x) >= 3:
        with np.errstate(divide="ignore", invalid="ignore"):
            realized = np.asarray(frame["net_pnl"], dtype=float) / np.asarray(frame["equity_before"], dtype=float)
        fin = np.isfinite(realized)
        if fin.sum() >= 3 and np.std(x[fin]) > 0 and np.std(realized[fin]) > 0:
            stats["mae_vs_realized_pearson"] = float(np.corrcoef(x[fin], realized[fin])[0, 1])
        else:
            stats["mae_vs_realized_pearson"] = None
        stats["realized_net_frac_mean"] = float(np.mean(realized[fin])) if fin.any() else None
        won, lost = realized[fin] > 0, realized[fin] < 0
        stats["mae_mean_winners"] = float(x[fin][won].mean()) if won.any() else None
        stats["mae_mean_losers"] = float(x[fin][lost].mean()) if lost.any() else None
        stats["n_winners"], stats["n_losers"] = int(won.sum()), int(lost.sum())
    return stats


def self_check():
    """3 hand-computed trades (assert block, tol 1e-12)."""
    candles = pd.DataFrame({
        "high": [100.0, 105.0, 103.0],
        "low": [90.0, 95.0, 92.0],
    })
    # T1 LONG entry 100 idx0->1: min_low 90 -> MAE .10; max_high 105 -> MFE .05
    # T2 SHORT entry 100 idx0->2: max_high 105 -> MAE .05; min_low 90 -> MFE .10
    # T3 LONG entry 95 idx1->1: MAE 0.0; MFE (105-95)/95
    trades = pd.DataFrame([
        {"direction": 1, "entry_index": 0, "exit_index": 1, "entry_price": 100.0},
        {"direction": -1, "entry_index": 0, "exit_index": 2, "entry_price": 100.0},
        {"direction": 1, "entry_index": 1, "exit_index": 1, "entry_price": 95.0},
    ])
    got = mae_mfe_for_trades(trades, candles)
    exp = [(0.10, 0.05), (0.05, 0.10), (0.0, (105.0 - 95.0) / 95.0)]
    for i, (e_mae, e_mfe) in enumerate(exp):
        assert abs(got.iloc[i]["mae_frac"] - e_mae) < TOL, f"T{i+1} MAE {got.iloc[i]['mae_frac']} != {e_mae}"
        assert abs(got.iloc[i]["mfe_frac"] - e_mfe) < TOL, f"T{i+1} MFE {got.iloc[i]['mfe_frac']} != {e_mfe}"
    # error paths: exit<entry, bad direction, nonpositive entry
    for bad in ({"direction": 1, "entry_index": 2, "exit_index": 1, "entry_price": 100.0},
                {"direction": 0, "entry_index": 0, "exit_index": 1, "entry_price": 100.0},
                {"direction": 1, "entry_index": 0, "exit_index": 1, "entry_price": 0.0}):
        try:
            mae_mfe_for_trades(pd.DataFrame([bad]), candles)
        except ValueError:
            pass
        else:
            raise AssertionError(f"khong bat loi {bad}")
    return {"hand_trades": 3, "assert": "PASS", "tol": TOL,
            "expected": [{"mae": a, "mfe": b} for a, b in exp]}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--self-check", action="store_true")
    a = p.parse_args()
    print(json.dumps({"mae_self_check": self_check()}, indent=2))
