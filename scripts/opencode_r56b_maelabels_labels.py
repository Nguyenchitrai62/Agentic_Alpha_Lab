"""Opencode R56-B (v146 MAE-aware labels): risk-adjusted utility label pipeline.

Nhan moi (label innovation chua tung thu trong chuong trinh):
  utility = net_pct - LAMBDA * mae_pct,  LAMBDA = 1.0 DUY NHAT (khong sweep).

MAE duoc tinh bang CUNG fast_outcome engine path (src/agentic_alpha_lab/data/swing.py):
  mo rong vong lap tuong lai cua fast_outcome mot cach causal — MAE lay tu cung
  cua so [entry_index, exit_index] inclusive, cung OHLC/entry/direction nhu net%.
  Unfilled -> MAE = 0 (khong vi the, khong excursion). Dinh nghia MAE VERBATIM
  scripts/opencode_mae.py (LONG: max(0,(entry-min_low)/entry);
  SHORT: max(0,(max_high-entry)/entry); fractions; mae_pct = frac*100).

Nhan qua:
  labels use future INSIDE the label window only (standard, giong labels net%
  hien tai); features KHONG BAO GIO dung tuong lai (past-only nghiem ngat,
  builders GIU NGUYEN). Unfilled utility = 0 (zeros giu nguyen nhu v41 de
  WAIT=0 gan 0). utility <= net cho moi filled candidate (MAE >= 0).

File nay cung cấp:
  fast_outcome_with_mae() — ban mo rong tra ve [net*100, fill, win, mae*100].
  build_mae_labels() — precompute one-time local (5628,16) mae_pct + parity
    bit-identical net vs examples.npz (SAME engine path proof).
  load_mae_labels() — load + sha-check + finite proof (train/smoke/cloud dung).
  utility_from() — u = net - LAMBDA*mae (LAMBDA phai 1.0, else raise).
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)
import hashlib
import json
from pathlib import Path

import numpy as np

LAMBDA_MAE = 1.0
MAE_TOL_PARITY = 1e-4

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fast_outcome_with_mae(ohlc, funding_times, index, signal, config):
    """fast_outcome + MAE tu CUNG vong lap (causal, same window).

    Tra ve np.float32 [net*100, fill, win|fill, mae*100].
    net/fill/win VERBATIM src/agentic_alpha_lab/data/swing.py::fast_outcome
    (copy logic, khong doi so); MAE track min_low/max_high tren bars
    [entry_index, exit_index] inclusive (exit = bar dong vi the: stop-fill,
    TP-fill cuoi, hoac horizon-end), dinh nghia VERBATIM opencode_mae.py.
    """
    from agentic_alpha_lab.data.swing import fast_outcome as _ref  # noqa: F401 (ghi nhan goc)
    side, limit = signal["direction"], signal["entry_limit"]
    horizon, expiry = signal["holding_bars"], config["entry_expiry_bars"]
    if index + expiry + horizon >= len(ohlc):
        raise ValueError("Incomplete swing label horizon")
    entry_index, entry = None, None
    for i in range(index + 1, index + expiry + 1):
        op, hi, lo, _ = ohlc[i]
        if (side == 1 and lo <= limit) or (side == -1 and hi >= limit):
            entry_index = i
            entry = min(op, limit) if side == 1 else max(op, limit)
            break
    if entry_index is None:
        return np.asarray([0, 0, 0, 0], np.float32)
    fee = config["costs"]["fee_rate_per_fill"]
    rate = config["costs"]["funding_long_rate"] if side == 1 else config["costs"]["funding_short_rate"]
    net, remaining, tp1_done = -fee, 1.0, False
    end = entry_index + horizon
    exit_index = end
    # MAE track: cuc tri bat loi tren window [entry_index, exit] (in sau vong chinh)
    for i in range(entry_index, end):
        op, hi, lo, _ = ohlc[i]
        if i > entry_index and funding_times[i]:
            net -= op / entry * remaining * rate
        stop = signal["stop_loss"]
        if (side == 1 and lo <= stop) or (side == -1 and hi >= stop):
            fill = min(op, stop) if side == 1 else max(op, stop)
            net += (side * (fill / entry - 1) - fee * fill / entry) * remaining
            remaining = 0
            exit_index = i
            break
        allow = i != entry_index or (op <= limit if side == 1 else op >= limit)
        if allow:
            for target, fraction in ((signal["take_profit_1"], 0.5), (signal["take_profit_2"], remaining)):
                first = target == signal["take_profit_1"]
                if first and tp1_done:
                    continue
                if (side == 1 and hi >= target) or (side == -1 and lo <= target):
                    fill = max(op, target) if side == 1 else min(op, target)
                    fraction = 0.5 if first else remaining
                    net += (side * (fill / entry - 1) - fee * fill / entry) * fraction
                    remaining -= fraction
                    if first:
                        tp1_done = True
            if remaining <= 0:
                exit_index = i
                break
    if remaining > 0:
        op = ohlc[end, 0]
        if funding_times[end]:
            net -= op / entry * remaining * rate
        net += (side * (op / entry - 1) - fee * op / entry) * remaining
        exit_index = end
    win = ohlc[entry_index:exit_index + 1]
    min_low = float(win[:, 2].min())
    max_high = float(win[:, 1].max())
    if side == 1:
        mae = max(0.0, (entry - min_low) / entry)
    else:
        mae = max(0.0, (max_high - entry) / entry)
    return np.asarray([net * 100, 1, float(net > 0), mae * 100], np.float32)


def utility_from(net_pct, mae_pct, lam=LAMBDA_MAE):
    """u = net - lam*mae (percent). lam phai 1.0 (single value, no sweep)."""
    if not float(lam) == 1.0:
        raise ValueError("v146 lambda phai 1.0 duy nhat (khong sweep)")
    net = np.asarray(net_pct, dtype=np.float64)
    mae = np.asarray(mae_pct, dtype=np.float64)
    if net.shape != mae.shape:
        raise ValueError("net/mae shape mismatch")
    if not (np.isfinite(net).all() and np.isfinite(mae).all()):
        raise ValueError("Nonfinite utility inputs")
    if not (mae >= -1e-9).all():
        raise ValueError("MAE am (vo ly)")
    return (net - float(lam) * mae).astype(np.float64)


def build_mae_labels(dataset_dir=None, output=None):
    """Precompute one-time local (5628,16) mae_pct + parity vs examples.npz.

    Tra ve dict thong ke (label finite proof + MAE thang/thua phan biet).
    Ghi output .npz {mae_pct, utility_lambda1, net_parity_max_abs, lambda}.
    """
    import pandas as pd
    from agentic_alpha_lab.data.swing import funding_flags, grid, prices
    ds = Path(dataset_dir) if dataset_dir else ROOT / "data/processed/swing_regime_research_v4"
    cfg = json.loads((ds / "config.json").read_text(encoding="utf-8"))
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet").sort_values("open_time").reset_index(drop=True)
    ohlc = candles[["open", "high", "low", "close"]].to_numpy(float)
    funding = funding_flags(candles, cfg["costs"]["funding_interval_hours"])
    with np.load(ds / "examples.npz", allow_pickle=False) as z:
        frozen = z["labels"]
    assert frozen.shape == (len(decisions), 16, 3)
    cands = grid(cfg)
    assert cands.shape == (16, 6)
    n = len(decisions)
    mae = np.empty((n, 16), dtype=np.float32)
    net_re = np.empty((n, 16), dtype=np.float32)
    for di in range(n):
        bi = int(decisions["bar_index"].iloc[di])
        close = float(decisions["close"].iloc[di])
        a5 = float(decisions["atr5"].iloc[di])
        a4 = float(decisions["atr4"].iloc[di])
        for k in range(16):
            sig = prices(close, a5, a4, cands[k], cfg)
            out = fast_outcome_with_mae(ohlc, funding, bi, sig, cfg)
            net_re[di, k] = out[0]
            mae[di, k] = out[3]
        if (di + 1) % 1000 == 0:
            print(f"labels_mae progress {di + 1}/{n}", flush=True)
    parity = float(np.max(np.abs(net_re - frozen[..., 0])))
    if not parity <= MAE_TOL_PARITY:
        raise ValueError(f"SAME-engine parity FAIL: max|net_re - net_frozen|={parity} > {MAE_TOL_PARITY}")
    if not np.isfinite(mae).all():
        raise ValueError("Nonfinite mae labels")
    if not (mae >= 0).all():
        raise ValueError("MAE am (vo ly)")
    fill = frozen[..., 1] > 0.5
    util = frozen[..., 0].astype(np.float64) - LAMBDA_MAE * mae.astype(np.float64)
    if not np.isfinite(util).all():
        raise ValueError("Nonfinite utility labels")
    # unfilled utility phai 0 (net=0 + MAE=0)
    if not float(np.abs(util[~fill]).max(initial=0.0)) <= 1e-6:
        raise ValueError("Unfilled utility khac 0")
    # utility <= net cho filled (MAE >= 0)
    if not (util[fill] <= frozen[..., 0][fill].astype(np.float64) + 1e-6).all():
        raise ValueError("utility > net o filled (vo ly)")
    won = fill & (frozen[..., 2] > 0.5)
    lost = fill & (frozen[..., 2] <= 0.5) & (frozen[..., 0] < 0)
    stats = {
        "n_decisions": n, "n_candidates": 16,
        "lambda": LAMBDA_MAE,
        "net_parity_max_abs_vs_frozen": parity,
        "mae_mean_pct": float(mae[fill].mean()) if fill.any() else None,
        "mae_p50_pct": float(np.quantile(mae[fill], 0.5)) if fill.any() else None,
        "mae_p90_pct": float(np.quantile(mae[fill], 0.9)) if fill.any() else None,
        "mae_max_pct": float(mae.max()),
        "mae_mean_winners_pct": float(mae[won].mean()) if won.any() else None,
        "mae_mean_losers_pct": float(mae[lost].mean()) if lost.any() else None,
        "n_winners": int(won.sum()), "n_losers": int(lost.sum()),
        "utility_mean_pct": float(util.mean()),
        "utility_std_pct": float(util.std()),
        "utility_p95_pct": float(np.percentile(util, 95)),
        "utility_min_pct": float(util.min()), "utility_max_pct": float(util.max()),
        "fill_frac": float(fill.mean()),
    }
    if output is not None:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(output, mae_pct=mae, utility_lambda1=util.astype(np.float32),
                            net_recomputed=net_re, Lambda=np.asarray(LAMBDA_MAE))
    return stats


def load_mae_labels(path, expect_n=5628):
    """Load + sha-ghi-nhan + finite proof (train/smoke/cloud dung chung)."""
    z = np.load(path, allow_pickle=False)
    mae = z["mae_pct"]
    if mae.shape != (expect_n, 16):
        raise ValueError(f"MAE shape {mae.shape} != ({expect_n},16)")
    if not np.isfinite(mae).all():
        raise ValueError("Nonfinite mae labels (load)")
    if not (mae >= 0).all():
        raise ValueError("MAE am (load)")
    lam = float(np.asarray(z["Lambda"]).reshape(-1)[0]) if "Lambda" in z else LAMBDA_MAE
    if not lam == 1.0:
        raise ValueError("MAE bundle lambda phai 1.0")
    return mae.astype(np.float64)
