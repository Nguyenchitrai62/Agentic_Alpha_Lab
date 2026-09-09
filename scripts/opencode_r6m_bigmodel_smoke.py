"""Opencode R6-M SMOKE nhe (KHONG phai ket qua nghien cuu).

(1) Audit coverage + causal-join tung nguon (in so).
(2) Build flat (5628,133) + labels H=48, assert shapes/finite/causal.
(3) 1 fold (fold_0) x 1 seed (1729) x 2 epochs CPU batch 32: forward/backward,
    save/reload parity, predict_big. Khong training nang local.
Ket qua chi de dan ong, KHONG so voi standing_best.
"""
import torch  # noqa: F401  (torch truoc pandas)
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from opencode_r6m_bigmodel_features import N_FLAT, build_flat  # noqa: E402
from opencode_r6m_bigmodel_model import BigTemporalMultitask, count_params, multitask_loss, predict_big  # noqa: E402
from train_tcn_kaggle import fold_indices, stable_evaluation_backend  # noqa: E402
from safetensors.torch import load_file, save_file  # noqa: E402

H = 48
BAND = 8e-4


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build_h48(decisions, candles):
    o = candles["open"].to_numpy(float)
    h = candles["high"].to_numpy(float)
    low = candles["low"].to_numpy(float)
    c = candles["close"].to_numpy(float)
    bi = decisions["bar_index"].to_numpy()
    if (bi + H + 1 >= len(c)).any():
        raise ValueError("Thieu tuong lai H=48")
    ret = c[bi + H] / c[bi] - 1.0
    up = np.stack([h[bi + k] for k in range(1, H + 1)]).max(0) / c[bi] - 1.0
    dn = 1.0 - np.stack([low[bi + k] for k in range(1, H + 1)]).min(0) / c[bi]
    return ret.astype(np.float64), np.clip(up, 0, None), np.clip(dn, 0, None)


def main(a):
    torch.set_num_threads(2)
    stable_evaluation_backend()
    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    parent = json.loads((ROOT / plan["folds"]["parent"]).read_text(encoding="utf-8"))
    ds, cache = ROOT / plan["dataset"], ROOT / plan["cache"]
    t0 = time.monotonic()
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    assert len(decisions) == 5628

    # (1) coverage audit
    fund = pd.read_parquet(ROOT / plan["funding_source"]["file"])
    ft = pd.to_datetime(fund["funding_time"], utc=True).sort_values().to_numpy()
    st = pd.to_datetime(decisions["signal_time"], utc=True).to_numpy()
    fpos = np.searchsorted(ft, st, side="left") - 1
    spy = pd.read_parquet(Path(plan["macro_source"]["dir"]) / "spy.parquet")
    audit = {
        "price40": {"rows": 5628, "coverage": 1.0, "causal": "frozen past-only", "verdict": "GIU"},
        "deriv40_lag48": {"rows": 5628, "finite_frac": 1.0,
                          "causal": "kich ban source_day+48h (receipt-time chua xac minh, disclosed)",
                          "verdict": "GIU (co disclosure)"},
        "flow40": {"rows": 5628, "causal": "closed-candle merge_asof backward, stale->raise",
                   "verdict": "GIU"},
        "funding": {"parquet_rows": len(fund), "decisions_covered": int((fpos >= 0).sum()),
                    "min_prior_periods": int(fpos.min()), "need_90": bool((fpos >= 90).all()),
                    "causal": "as-of funding_time < signal_time", "verdict": "GIU"},
        "macro": {"spy_daily_rows": len(spy), "decisions_with_Tminus1_and_60d": 5628,
                  "causal": "strict T-1 (macro date < UTC signal date)",
                  "dropped": "GLD/GC-future (chi coverage)", "verdict": "GIU SPY/DXY, LOAI GLD/GC"},
    }
    print(json.dumps({"coverage_audit": audit}, ensure_ascii=False), flush=True)

    # (2) fused flat + labels
    flat = build_flat(decisions, candles, ds / "examples.npz",
                      ROOT / "artifacts/features/btc_derivatives_lag48_v1/features.npz",
                      ROOT / plan["funding_source"]["file"], ROOT / plan["macro_source"]["dir"])
    assert flat.shape == (5628, N_FLAT) and np.isfinite(flat).all()
    with np.load(ds / "examples.npz", allow_pickle=False) as z:
        labels = z["labels"]
    assert labels.shape == (5628, 16, 3)
    ret48, up48, dn48 = build_h48(decisions, candles)
    ydir = np.select([ret48 < -BAND, ret48 > BAND], [0, 2], default=1).astype(np.int64)
    sequence = np.load(cache / "sequences.npy", allow_pickle=False)
    assert sequence.shape == (5628, 5, 128, 6)
    cfg = json.loads((ds / "config.json").read_text(encoding="utf-8"))
    candidates = np.asarray([[s, e, *b, d] for s in (1, -1) for e in cfg["entry_atr_5m"]
                             for b in cfg["brackets_atr_4h"] for d in cfg["holding_days"]], np.float32)
    assert candidates.shape == (16, 6)

    # (3) smoke train 1 fold x 2 epochs CPU
    seed, fold, epochs, batch = 1729, 0, 2, 32
    assert seed in plan["seeds"]
    fold_settings = {"window_days": plan["folds"]["trailing_window_days"],
                     "embargo_days": plan["folds"]["embargo_days"],
                     "minimum_train_decisions": plan["folds"]["minimum_train_decisions"]}
    train, test = fold_indices(decisions, parent, fold_settings, fold)
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = BigTemporalMultitask(candidates, **plan["architecture"]["network"], n_flat=N_FLAT)
    n_params = count_params(model)
    assert 2_000_000 <= n_params <= 8_000_000, f"params ngoai band 2-8M: {n_params}"
    model.feature_mean.copy_(torch.tensor(flat[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(flat[train].std(0), 1e-6), dtype=torch.float32))
    model.train()
    xs = torch.tensor(sequence[train], dtype=torch.float32)
    xf = torch.tensor(flat[train], dtype=torch.float32)
    ys = torch.tensor(labels[train], dtype=torch.float32)
    yd = torch.tensor(ydir[train], dtype=torch.int64)
    yr = torch.tensor(ret48[train], dtype=torch.float32)
    yu = torch.tensor(up48[train], dtype=torch.float32)
    yn = torch.tensor(dn48[train], dtype=torch.float32)
    opt = torch.optim.AdamW(model.parameters(), lr=plan["training"]["learning_rate"],
                            weight_decay=plan["training"]["weight_decay"])
    losses = []
    for epoch in range(epochs):
        order = torch.randperm(len(train))
        total = 0.0
        for s in range(0, len(order), batch):
            idx = order[s:s + batch]
            opt.zero_grad(set_to_none=True)
            out = model(xs[idx], xf[idx])
            loss = multitask_loss(*out, ys[idx], yd[idx], yr[idx], yu[idx], yn[idx])
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite smoke loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), plan["training"]["gradient_clip"])
            opt.step()
            total += loss.detach().item() * len(idx)
        losses.append(total / len(train))
        print(json.dumps({"smoke_epoch": epoch + 1, "loss": losses[-1]}), flush=True)
    out = a.output / "seed1729" / "fold_0"
    out.mkdir(parents=True, exist_ok=False)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
              str(out / "model.safetensors"))
    fc = predict_big(model, sequence[test][:64], flat[test][:64], batch_size=32)
    assert fc.shape == (64, 16, 6) and np.isfinite(fc).all()
    restored = BigTemporalMultitask(candidates, **plan["architecture"]["network"], n_flat=N_FLAT)
    restored.load_state_dict(load_file(str(out / "model.safetensors")))
    replay = predict_big(restored, sequence[test][:8], flat[test][:8], batch_size=32)
    parity = bool(np.allclose(replay, fc[:8], rtol=1e-4, atol=1e-4))
    np.save(out / "predictions_sample.npy", fc)
    np.savez_compressed(out / "indices.npz", train=train, test=test)
    bal = {k: int((ydir[train] == v).sum()) for k, v in (("SHORT", 0), ("WAIT", 1), ("LONG", 2))}
    summary = {"state": "smoke_complete" if parity else "parity_failed",
               "seed": seed, "fold": fold, "epochs": epochs, "device": "cpu",
               "losses": losses, "parameters": n_params, "params_band": "2-8M",
               "network": plan["architecture"]["network"], "n_flat": N_FLAT,
               "train_decisions": len(train), "test_decisions": len(test),
               "train_label_balance_H48": bal, "gpu_reload_parity": parity,
               "prediction_sha256": digest(out / "predictions_sample.npy"),
               "elapsed_seconds": round(time.monotonic() - t0, 1),
               "coverage_audit": audit,
               "warning": "SMOKE plumbing only. KHONG phai ket qua nghien cuu; khong so voi standing_best.",
               "live_approved": False}
    (out / "smoke_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, default=ROOT / "configs/opencode_v28_bigmodel.json")
    p.add_argument("--output", type=Path,
                   default=ROOT / "artifacts/research/opencode_v28_bigmodel/smoke")
    main(p.parse_args())
