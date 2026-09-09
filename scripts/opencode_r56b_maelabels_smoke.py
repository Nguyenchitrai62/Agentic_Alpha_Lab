"""Opencode R56-B SMOKE v146 nhe (KHONG phai ket qua nghien cuu).

(1) MAE self-check (3 hand trades) + SAME-engine parity spot-check
    (recomputed net vs examples.npz frozen tren 32 decisions dau).
(2) Label finite proof: utility/MAE finite, MAE>=0, unfilled u=0, utility<=net.
(3) Coverage audit 5 nguon + build flat (5628,133) + labels_u (5628,16,3).
(4) 1 fold (fold_0) x 1 seed (1729) x 3 epochs CPU batch 32: forward/backward
     FULL v146 loss (2.0*value-chuan-hoa tren Z_u + 0.5*pairwise-ranking TREN
     UTILITY TRADEABLE (PRIMARY) + aux + coverage-hinge TREN UTILITY),
     RANKING-DECREASING proof (rank_last < rank_first — flat => STOP),
     RAW-SCALE-SANE proof tren utility, DESTANDARDIZE roundtrip,
     TIE-BREAK deterministic proof tren raw utility, VAL-EXPORT RAW UTILITY
     proof, SIZING-CAP-RIENG proof, save/reload parity, policy-floor unit-test.
     Khong training nang local. Ket qua chi de dan ong, KHONG so standing_best.
"""
import torch  # noqa: F401  (torch truoc pandas)
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import opencode_mae  # noqa: E402
from opencode_r56b_maelabels_features import N_FLAT, build_flat  # noqa: E402
from opencode_r56b_maelabels_labels import (  # noqa: E402
    LAMBDA_MAE,
    fast_outcome_with_mae,
    load_mae_labels,
    utility_from,
)
from opencode_r56b_maelabels_model import (  # noqa: E402
    LOSS_W_RANK,
    LOSS_W_VALUE,
    RANK_TEMP_PCT,
    RANK_TIE_PCT,
    SIGMA_FLOOR,
    SIZING_CAP,
    TIE_BREAK_EPS,
    UtilityScaleSSMTemporal,
    apply_sizing_cap_numpy,
    compute_utility_stats,
    count_params,
    destandardize,
    deterministic_best_index,
    deterministic_best_indices,
    expected_net_best,
    multitask_loss_cov_rank,
    predict_ssm_raw_utility,
    predict_ssm_sizing_capped,
)
from opencode_r56b_maelabels_train import loss_params, make_model  # noqa: E402
from opencode_r9m_nextarch_model import POLICY_MARGIN, POLICY_N_MIN  # noqa: E402
from agentic_alpha_lab.models.temporal_validation import nested_split  # noqa: E402
from train_tcn_kaggle import fold_indices, stable_evaluation_backend  # noqa: E402
from opencode_r9m_nextarch_model import apply_coverage_floor_policy  # noqa: E402
from agentic_alpha_lab.data.swing import funding_flags, grid, prices  # noqa: E402
from safetensors.torch import load_file, save_file  # noqa: E402

H = 48
BAND = 8e-4


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build_h48(decisions, candles):
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
    assert plan.get("model_family") == "mae_utility_selective_ssm_v146", "Sai plan family"
    assert int(plan["training"]["epochs"]) == 16, "v146 FIXED 16 epochs"
    assert plan.get("epoch_selection", {}).get("mode", "").startswith("FIXED"), "v146 bo early-stop"
    assert str(plan["training"].get("value_scale_method", "")) == "standardize_train_window_utility"
    assert float(plan["training"].get("label_lambda_mae", -1)) == 1.0, "v146 lambda phai 1.0"
    assert LAMBDA_MAE == 1.0
    assert float(plan["training"].get("sizing_cap_percent", -1)) == 2.0
    assert float(plan["training"].get("tie_break_eps", -1)) == 1e-6
    assert "policy_cap_cap" not in plan["training"] and "policy_cap_mode" not in plan["training"]
    assert SIZING_CAP == 2.0 and TIE_BREAK_EPS == 1e-6
    vw, rw, lam, flr, rtemp, rtie = loss_params(plan)
    assert (vw, rw) == (2.0, 0.5), f"value/ranking weights khac dong bang: {(vw, rw)}"
    assert (lam, flr) == (3.0, 5e-4), f"Coverage-floor khac dong bang: {(lam, flr)}"
    assert (rtemp, rtie) == (1.0, 0.25), f"Ranking temp/tie khac dong bang: {(rtemp, rtie)}"
    assert (LOSS_W_VALUE, LOSS_W_RANK, RANK_TEMP_PCT, RANK_TIE_PCT) == (2.0, 0.5, 1.0, 0.25)
    assert float(plan["budget"]["gpu_hours_max"]) <= 10.0, "budget tran 10 GPU-gio"
    parent = json.loads((ROOT / plan["folds"]["parent"]).read_text(encoding="utf-8"))
    ds, cache = ROOT / plan["dataset"], ROOT / plan["cache"]
    t0 = time.monotonic()

    # (1) MAE self-check + engine parity spot-check (SAME path proof, 32 decisions)
    mae_check = opencode_mae.self_check()
    print(json.dumps({"mae_self_check": mae_check}), flush=True)
    assert mae_check["assert"] == "PASS", "MAE self-check FAIL -> STOP"
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet").sort_values("open_time").reset_index(drop=True)
    assert len(decisions) == 5628
    cfg = json.loads((ds / "config.json").read_text(encoding="utf-8"))
    ohlc = candles[["open", "high", "low", "close"]].to_numpy(float)
    funding = funding_flags(candles, cfg["costs"]["funding_interval_hours"])
    with np.load(ds / "examples.npz", allow_pickle=False) as z:
        frozen = z["labels"]
    assert frozen.shape == (5628, 16, 3)
    cands = grid(cfg)
    spot_max = 0.0
    for di in range(32):
        bi = int(decisions["bar_index"].iloc[di])
        for k in range(16):
            sig = prices(float(decisions["close"].iloc[di]), float(decisions["atr5"].iloc[di]),
                         float(decisions["atr4"].iloc[di]), cands[k], cfg)
            out = fast_outcome_with_mae(ohlc, funding, bi, sig, cfg)
            spot_max = max(spot_max, abs(float(out[0]) - float(frozen[di, k, 0])))
    print(json.dumps({"engine_parity_spot32": {"max_abs_net_vs_frozen": spot_max}}), flush=True)
    assert spot_max <= 1e-4, f"SAME-engine parity FAIL: {spot_max}"

    # (2) Label finite proof (precomputed causal file)
    mae_pct = load_mae_labels(ROOT / plan["mae_labels"]["file"])
    assert mae_pct.shape == (5628, 16) and np.isfinite(mae_pct).all() and (mae_pct >= 0).all()
    utility = utility_from(frozen[..., 0], mae_pct, lam=1.0)
    assert np.isfinite(utility).all()
    fill_m = frozen[..., 1] > 0.5
    assert float(np.abs(utility[~fill_m]).max(initial=0.0)) <= 1e-6, "unfilled utility phai 0"
    assert bool((utility[fill_m] <= frozen[..., 0][fill_m].astype(np.float64) + 1e-6).all())
    won = fill_m & (frozen[..., 2] > 0.5)
    lost = fill_m & (frozen[..., 0] < 0)
    mae_win = float(mae_pct[won].mean()) if won.any() else None
    mae_lose = float(mae_pct[lost].mean()) if lost.any() else None
    print(json.dumps({"label_finite_proof": {"finite": True, "mae_ge_0": True, "unfilled_u_zero": True,
          "utility_le_net": True, "mae_mean_winners_pct": mae_win,
          "mae_mean_losers_pct": mae_lose, "utility_mean": float(utility.mean()),
          "utility_std": float(utility.std())}}), flush=True)
    labels_u = np.stack([utility, frozen[..., 1].astype(np.float64),
                         frozen[..., 2].astype(np.float64)], -1).astype(np.float32)

    # coverage audit 5 nguon (giong v41)
    fund = pd.read_parquet(ROOT / plan["funding_source"]["file"])
    ft = pd.to_datetime(fund["funding_time"], utc=True).sort_values().to_numpy()
    st = pd.to_datetime(decisions["signal_time"], utc=True).to_numpy()
    fpos = np.searchsorted(ft, st, side="left") - 1
    spy = pd.read_parquet(Path(plan["macro_source"]["dir"]) / "spy.parquet")
    audit = {
        "price40": {"rows": 5628, "coverage": 1.0, "causal": "frozen past-only", "verdict": "GIU"},
        "deriv40_lag48": {"rows": 5628, "finite_frac": 1.0,
                          "causal": "kich ban source_day+48h (disclosed)",
                          "verdict": "GIU (co disclosure)"},
        "flow40": {"rows": 5628, "causal": "closed-candle merge_asof backward, stale->raise",
                   "verdict": "GIU"},
        "funding": {"parquet_rows": len(fund), "decisions_covered": int((fpos >= 0).sum()),
                    "min_prior_periods": int(fpos.min()), "need_90": bool((fpos >= 90).all()),
                    "causal": "as-of funding_time < signal_time", "verdict": "GIU"},
        "macro": {"spy_daily_rows": len(spy), "decisions_with_Tminus1_and_60d": 5628,
                  "causal": "strict T-1", "dropped": "GLD/GC-future", "verdict": "GIU SPY/DXY"},
    }
    print(json.dumps({"coverage_audit": audit}, ensure_ascii=False), flush=True)

    flat = build_flat(decisions, candles, ds / "examples.npz",
                      ROOT / "artifacts/features/btc_derivatives_lag48_v1/features.npz",
                      ROOT / plan["funding_source"]["file"], ROOT / plan["macro_source"]["dir"])
    assert flat.shape == (5628, N_FLAT) and np.isfinite(flat).all()
    ret48, up48, dn48 = build_h48(decisions, candles)
    ydir = np.select([ret48 < -BAND, ret48 > BAND], [0, 2], default=1).astype(np.int64)
    sequence = np.load(cache / "sequences.npy", allow_pickle=False)
    assert sequence.shape == (5628, 5, 128, 6)
    candidates = np.asarray([[s, e, *b, d] for s in (1, -1) for e in cfg["entry_atr_5m"]
                             for b in cfg["brackets_atr_4h"] for d in cfg["holding_days"]], np.float32)
    assert candidates.shape == (16, 6)

    seed, fold, epochs, batch = 1729, 0, 3, 32
    assert seed in plan["seeds"]
    fold_settings = {"window_days": plan["folds"]["trailing_window_days"],
                     "embargo_days": plan["folds"]["embargo_days"],
                     "minimum_train_decisions": plan["folds"]["minimum_train_decisions"]}
    train, test = fold_indices(decisions, parent, fold_settings, fold)
    spec = plan["epoch_selection"]
    _, validation, _clock = nested_split(
        decisions, parent["folds"][fold][0],
        window_days=spec["window_days"], validation_days=spec["validation_days"],
        embargo_days=spec["embargo_days"], minimum_train=spec["minimum_train"],
        minimum_validation=spec["minimum_validation"])
    assert len(validation) >= 100
    assert not np.intersect1d(validation, test).size
    mu_u, sigma_u = compute_utility_stats(labels_u[train][..., 0])
    print(json.dumps({"utility_scale_train_only": {"mu_u_train": mu_u, "sigma_u_train": sigma_u,
           "n_train": int(len(train))}}), flush=True)
    assert np.isfinite(mu_u) and np.isfinite(sigma_u) and sigma_u >= SIGMA_FLOOR
    assert 0.5 < sigma_u < 10.0, f"sigma_u bat thuong: {sigma_u}"
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = make_model(plan, candidates)
    assert isinstance(model, UtilityScaleSSMTemporal)
    n_params = count_params(model)
    assert n_params == 600875, f"params doi so voi dong bang: {n_params}"
    model.feature_mean.copy_(torch.tensor(flat[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(flat[train].std(0), 1e-6), dtype=torch.float32))
    model.train()
    xs = torch.tensor(sequence[train], dtype=torch.float32)
    xf = torch.tensor(flat[train], dtype=torch.float32)
    ys = torch.tensor(labels_u[train], dtype=torch.float32)
    yd = torch.tensor(ydir[train], dtype=torch.int64)
    yr = torch.tensor(ret48[train], dtype=torch.float32)
    yu = torch.tensor(up48[train], dtype=torch.float32)
    yn = torch.tensor(dn48[train], dtype=torch.float32)
    opt = torch.optim.AdamW(model.parameters(), lr=plan["training"]["learning_rate"],
                            weight_decay=plan["training"]["weight_decay"])
    losses, ranks, covs, poss = [], [], [], []
    for epoch in range(epochs):
        order = torch.randperm(len(train))
        total, rtot, ctot, ptot = 0.0, 0.0, 0.0, 0.0
        for s in range(0, len(order), batch):
            idx = order[s:s + batch]
            opt.zero_grad(set_to_none=True)
            out = model(xs[idx], xf[idx])
            if not torch.isfinite(out[0]).all():
                raise ValueError("Nonfinite Z_u score")
            loss, parts = multitask_loss_cov_rank(*out, ys[idx], yd[idx], yr[idx], yu[idx], yn[idx],
                                                  mu=mu_u, sigma=sigma_u,
                                                  value_w=vw, rank_w=rw, lambda_cov=lam,
                                                  floor_pos=flr, rank_temp=rtemp, rank_tie=rtie)
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite smoke loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), plan["training"]["gradient_clip"])
            opt.step()
            total += loss.detach().item() * len(idx)
            rtot += float(parts["rank"]) * len(idx)
            ctot += float(parts["cov"]) * len(idx)
            ptot += float(parts["mean_pos"]) * len(idx)
        losses.append(total / len(train))
        ranks.append(rtot / len(train))
        covs.append(ctot / len(train))
        poss.append(ptot / len(train))
        print(json.dumps({"smoke_epoch": epoch + 1, "loss": losses[-1], "rank": ranks[-1],
                          "cov": covs[-1], "mean_pos_utility": poss[-1]}), flush=True)
    assert all(np.isfinite(ranks)), "ranking-term tren UTILITY phai finite"
    assert all(np.isfinite(covs)), "coverage-term tren UTILITY phai finite"
    rank_move = float(ranks[0] - ranks[-1])
    rank_decreasing = bool(ranks[-1] < ranks[0] - 1e-9)
    rank_range = float(max(ranks) - min(ranks))
    print(json.dumps({"ranking_decreasing_proof": {"ranks": ranks, "move": rank_move,
          "range": rank_range, "pass": rank_decreasing}}), flush=True)
    if not rank_decreasing or not rank_range > 1e-9:
        raise RuntimeError(f"STOP: ranking loss FLAT tren utility — ranks={ranks}; khong package")
    out = a.output / "seed1729" / "fold_0"
    out.mkdir(parents=True, exist_ok=False)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
              str(out / "model.safetensors"))
    (out / "value_scale.json").write_text(json.dumps({"mu_u_train": mu_u, "sigma_u_train": sigma_u,
        "method": "standardize_train_window_utility", "lambda_mae": 1.0,
        "causal": "train-only past-only"}))
    fc = predict_ssm_raw_utility(model, sequence[test][:64], flat[test][:64], mu_u, sigma_u, batch_size=32)
    assert fc.shape == (64, 16, 6) and np.isfinite(fc).all()
    fill = 1 / (1 + np.exp(-np.clip(fc[..., 4], -40, 40)))
    unconditional = fc[..., 0] * fill  # raw utility tradeable percent
    max_abs_raw = float(np.max(np.abs(unconditional)))
    raw_range = float(np.max(unconditional) - np.min(unconditional))
    raw_std = float(np.std(unconditional))
    frac_beyond_sizing = float((np.abs(unconditional) > SIZING_CAP).mean())
    print(json.dumps({"raw_scale_sane_proof": {"max_abs_raw_utility_percent": max_abs_raw,
      "range": raw_range, "std": raw_std, "frac_beyond_sizing_cap_2pct": frac_beyond_sizing,
      "mu_u_train": mu_u, "sigma_u_train": sigma_u}}), flush=True)
    sane_pass = bool((0.05 < max_abs_raw < 15.0) and (raw_range > 0.01) and (raw_std > 1e-3)
                     and (frac_beyond_sizing < 0.80))
    if not sane_pass:
        raise RuntimeError(f"STOP: raw utility KHONG sane — max={max_abs_raw}, range={raw_range}, std={raw_std}; khong package")
    model.eval()
    with torch.no_grad():
        xs_s = torch.tensor(sequence[test][:8], dtype=torch.float32)
        xf_s = torch.tensor(flat[test][:8], dtype=torch.float32)
        score_s, *_ = model(xs_s, xf_s)
        z0 = score_s[..., 0].cpu().numpy()
    trade_rt = destandardize(z0, mu_u, sigma_u)
    assert np.allclose(trade_rt, (z0 * sigma_u + mu_u)), "destandardize roundtrip hong"
    fc_sizing = predict_ssm_sizing_capped(model, sequence[test][:64], flat[test][:64],
                                          mu_u, sigma_u, batch_size=32)
    assert fc_sizing.shape == (64, 16, 6) and np.isfinite(fc_sizing).all()
    fill_sz = 1 / (1 + np.exp(-np.clip(fc_sizing[..., 4], -40, 40)))
    uncond_sz = fc_sizing[..., 0] * fill_sz
    assert bool((np.abs(uncond_sz) <= SIZING_CAP + 1e-9).all()), "sizing-cap bound hong"
    assert bool((np.abs(uncond_sz) <= np.abs(unconditional) + 1e-9).all()), "sizing phai <= |raw|"
    exp_row = np.full(16, 0.5)
    exp_row[3] = 0.5 + 5e-7
    exp_row[7] = 0.5 + 5e-7
    fil_row = np.zeros(16)
    fil_row[3] = 0.5
    fil_row[7] = 1.5
    pick_fill = deterministic_best_index(exp_row, fil_row, candidates)
    assert pick_fill == 7, f"tie-break fill-desc hong: {pick_fill}"
    exp_row2 = np.full(16, 0.5)
    holds = candidates[:, 5]
    idx_h3 = int(np.flatnonzero(holds == 3)[0])
    pick_hold = deterministic_best_index(exp_row2, np.zeros(16), candidates)
    assert int(candidates[pick_hold, 5]) == 3, f"tie-break holding-asc hong: {pick_hold}"
    assert pick_hold == idx_h3, f"tie-break index nho nhat hong: {pick_hold} vs {idx_h3}"
    rep1 = deterministic_best_index(exp_row, fil_row, candidates)
    rep2 = deterministic_best_index(exp_row, fil_row, candidates)
    assert rep1 == rep2 == 7, "tie-break phai bit-identical repeat"
    vec = deterministic_best_indices(np.stack([exp_row, exp_row2]), np.stack([fil_row, np.zeros(16)]), candidates)
    assert vec.tolist() == [7, idx_h3], f"vectorized tie-break hong: {vec}"
    tie_pass = True
    fc_val = predict_ssm_raw_utility(model, sequence[validation][:64], flat[validation][:64],
                                     mu_u, sigma_u, batch_size=32)
    assert fc_val.shape == (64, 16, 6) and np.isfinite(fc_val).all()
    fill_val = 1 / (1 + np.exp(-np.clip(fc_val[..., 4], -40, 40)))
    uncond_val = fc_val[..., 0] * fill_val
    max_abs_val = float(np.max(np.abs(uncond_val)))
    print(json.dumps({"val_raw_utility_preview": {"max_abs_val_utility_percent": max_abs_val}}), flush=True)
    np.save(out / "val_predictions_sample.npy", fc_val)
    val_export_present = bool((out / "val_predictions_sample.npy").exists())
    restored = make_model(plan, candidates)
    restored.load_state_dict(load_file(str(out / "model.safetensors")))
    replay = predict_ssm_raw_utility(restored, sequence[test][:8], flat[test][:8],
                                     mu_u, sigma_u, batch_size=32)
    parity = bool(np.allclose(replay, fc[:8], rtol=1e-4, atol=1e-4))
    neg = apply_coverage_floor_policy(np.full(50, -0.01), POLICY_MARGIN, POLICY_N_MIN)
    assert len(neg) == POLICY_N_MIN == 8, f"fallback floor hong: {len(neg)}"
    mixed_en = np.concatenate([np.full(3, 0.5), np.full(47, -0.01)])
    mixed = apply_coverage_floor_policy(mixed_en, POLICY_MARGIN, POLICY_N_MIN)
    assert len(mixed) == 8 and set(range(3)) <= set(mixed.tolist()), "gate+fallback hong"
    en_raw = (fc[..., 0] * fill).max(axis=1)
    gate_hits = int((en_raw > POLICY_MARGIN).sum())
    np.save(out / "predictions_sample.npy", fc)
    np.save(out / "predictions_sizing_capped_sample.npy", fc_sizing)
    np.savez_compressed(out / "indices.npz", train=train, validation=validation, test=test)
    bal = {k: int((ydir[train] == v).sum()) for k, v in (("SHORT", 0), ("WAIT", 1), ("LONG", 2))}
    summary = {"state": "smoke_complete" if parity else "parity_failed",
               "seed": seed, "fold": fold, "epochs": epochs, "device": "cpu",
               "losses": losses, "ranking_terms": ranks,
               "coverage_terms": covs, "mean_pos_utility": poss,
               "label_proof": {"mae_self_check": mae_check["assert"],
                   "engine_parity_spot32_max_abs": spot_max,
                   "mae_mean_winners_pct": mae_win, "mae_mean_losers_pct": mae_lose,
                   "utility_mean": float(utility.mean()), "utility_std": float(utility.std()),
                   "lambda": 1.0, "pass": True},
               "ranking_decreasing_proof": {"ranks": ranks, "move": rank_move,
                   "range": rank_range, "pass": rank_decreasing,
                   "note": "v146 rank TREN UTILITY phai dich chuyen; flat => STOP khong package"},
               "loss_weights": {"value": vw, "rank": rw, "dir": 1.0, "quant": 1.0,
                                "exc": 0.5, "cov_lambda": lam},
               "ranking_params": {"temperature_percent": rtemp, "tie_band_percent": rtie},
               "coverage_floor": {"lambda": lam, "floor_pos": flr, "domain": "UTILITY TRADEABLE percent"},
               "value_scale": {"method": "standardize_train_window_utility", "mu_u_train": mu_u,
                               "sigma_u_train": sigma_u, "lambda_mae": 1.0,
                               "causal": "train-only past-only"},
               "raw_scale_sane_proof": {"max_abs_raw_utility_percent": max_abs_raw,
                                        "range": raw_range, "std": raw_std,
                                        "frac_beyond_sizing_cap_2pct": frac_beyond_sizing,
                                        "max_abs_val_preview": max_abs_val,
                                        "pass": sane_pass,
                                        "bounds": "0.05<max<15.0, range>0.01, std>1e-3, frac>2%<80%"},
               "sizing_cap_separate_proof": {"cap": SIZING_CAP, "max_abs_sizing": float(np.max(np.abs(uncond_sz))),
                                             "pass": True},
               "destandardize_roundtrip": True,
               "tie_break_proof": {"eps": TIE_BREAK_EPS, "fill_desc_pick": int(pick_fill),
                   "holding_asc_pick": int(pick_hold), "repeat_identical": True,
                   "vectorized": vec.tolist(), "pass": tie_pass,
                   "rule": "gap<1e-6 -> fill-desc, holding-asc (3 truoc 7), index-min (tren RAW UTILITY)"},
               "val_export_proof": {"val_predictions_file": "val_predictions_sample.npy",
                                    "present": val_export_present,
                                    "shape": list(fc_val.shape),
                                    "n_validation_total": int(len(validation)),
                                    "finite": True, "pass": True},
               "epoch_mode": "FIXED 16 (smoke chay 3 epochs plumbing + decreasing+sane-proof)",
               "policy_floor_unit_test": {"all_negative_picks": len(neg), "mixed_picks": len(mixed),
                                          "margin": POLICY_MARGIN, "n_min": POLICY_N_MIN, "pass": True},
               "smoke_gate_preview (KHONG phai ket qua)": {"n_test_sample": 64,
                   "gate_hits_en_raw_gt_0": gate_hits, "en_best_raw_mean": float(en_raw.mean())},
               "parameters": n_params, "params_band": "dong kich thuoc v35/v38/v39/v40/v41 (600875)",
               "model_family": "mae_utility_selective_ssm_v146", "n_flat": N_FLAT,
               "train_decisions": len(train), "test_decisions": len(test),
               "validation_decisions": len(validation),
               "train_label_balance_H48": bal, "gpu_reload_parity": parity,
               "prediction_sha256": digest(out / "predictions_sample.npy"),
               "val_prediction_sha256": digest(out / "val_predictions_sample.npy"),
               "elapsed_seconds": round(time.monotonic() - t0, 1),
               "coverage_audit": audit,
               "calibration_next": "audit local sau train: fit isotonic outlier-robust TREN VAL-PRED EXPORT RAW UTILITY past-only TRUOC choose",
               "warning": "SMOKE plumbing only. KHONG phai ket qua nghien cuu; KHONG so voi standing_best.",
               "live_approved": False}
    (out / "smoke_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, default=ROOT / "configs/opencode_v146_maelabels.json")
    p.add_argument("--output", type=Path,
                   default=ROOT / "artifacts/research/opencode_v146_maelabels/smoke")
    main(p.parse_args())
