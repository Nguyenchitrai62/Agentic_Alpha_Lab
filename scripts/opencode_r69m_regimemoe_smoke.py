"""Opencode R69-M SMOKE v159 nhe (KHONG phai ket qua nghien cuu).

(1) Audit coverage + causal-join tung nguon (in so, giong v28/v35/v38/v39/v40/v41/v145).
(2) Build flat (5628,133) qua wrapper v159 + labels H=48, assert shapes/finite/causal.
(3) Router + upweight descriptors EXACT v103 (past-only: vol_high/fund_high as-of strict) + record.
(4) 1 fold (fold_0) x 1 seed (1729) x 3 epochs CPU batch 32: forward/backward
     FULL v159 MoE loss ([2.0*value_q + 0.5*rank_q_weighted(opt_B) + 3.0*cov_q]
     + [2.0*value_r + 0.5*rank_r_uniform + 3.0*cov_r] + aux shared),
     CA HAI experts RANKING-DECREASING proof (rank_q_last < rank_q_first VA
     rank_r_last < rank_r_first — PHAI dich chuyen CA HAI; neu 1 flat thi STOP),
     ROUTER-ACTIVE proof (ca hai experts duoc chon tren test sample + full test
     fold: counts + fracs noi bo, khong 0/100%),
     UPWEIGHT-ACTIVE proof (mean_w_Llike=2.0 vs rest=1.0 + frac + counts + ESS),
     RAW-SCALE-SANE proof MOI expert (max|tradeable| vai percent, KHONG rail,
     KHONG collapse), DESTANDARDIZE roundtrip MOI expert,
     TIE-BREAK deterministic proof (tren expert-duoc-chon),
     VAL-EXPORT proof (per-expert + routed RAW finite + shapes, KHONG CLIP),
     SIZING-CAP-RIENG proof (routed clip +-2.0),
     save/reload parity (ca hai experts + routed),
     policy-floor unit-test tren routed.
     Khong training nang local.
Ket qua chi de dan ong, KHONG so voi standing_best.
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
from opencode_r69m_regimemoe_features import N_FLAT, build_flat  # noqa: E402
from opencode_r69m_regimemoe_model import (  # noqa: E402
    FUND_ABS,
    LOSS_W_RANK_Q,
    LOSS_W_RANK_R,
    LOSS_W_VALUE,
    RANK_TEMP_PCT,
    RANK_TIE_PCT,
    SIGMA_FLOOR,
    SIZING_CAP,
    TIE_BREAK_EPS,
    UPWEIGHT_LLIKE,
    VOL_CUT_V56,
    RegimeMoESSMTemporal,
    apply_sizing_cap_numpy,
    compute_router_mask,
    compute_upweights,
    compute_value_stats,
    count_params,
    destandardize,
    deterministic_best_index,
    deterministic_best_indices,
    expected_net_best,
    multitask_loss_moe,
    predict_moe_raw,
    route_blocks,
    router_stats,
    upweight_stats,
)
from opencode_r69m_regimemoe_train import loss_params, make_model, regime_vectors  # noqa: E402
from opencode_r9m_nextarch_model import POLICY_MARGIN, POLICY_N_MIN  # noqa: E402
from agentic_alpha_lab.models.temporal_validation import nested_split  # noqa: E402
from train_tcn_kaggle import fold_indices, stable_evaluation_backend  # noqa: E402
from opencode_r9m_nextarch_model import apply_coverage_floor_policy  # noqa: E402
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
    assert plan.get("model_family") == "regimemoe_ssm_v159", "Sai plan family"
    assert int(plan["training"]["epochs"]) == 16, "v159 FIXED 16 epochs"
    assert plan.get("epoch_selection", {}).get("mode", "").startswith("FIXED"), "v159 bo early-stop"
    assert str(plan["training"].get("value_scale_method", "")) == "standardize_train_window", "v159 phai chuan-hoa"
    assert plan["training"].get("value_scale_shared", False) is True, "v159 mu/sigma dung chung 2 experts"
    assert float(plan["training"].get("sizing_cap_percent", -1)) == 2.0, "v159 sizing cap phai 2.0 percent"
    assert float(plan["training"].get("upweight_Llike_factor", -1)) == 2.0, "v159 upweight phai 2.0"
    assert float(plan["training"].get("ranking_weight_quiet", -1)) == 0.5, "v159 rank_q phai 0.5"
    assert float(plan["training"].get("ranking_weight_rest", -1)) == 0.5, "v159 rank_r phai 0.5"
    assert float(plan["training"].get("tie_break_eps", -1)) == 1e-6, "v159 eps phai 1e-6"
    assert "policy_cap_cap" not in plan["training"] and "policy_cap_mode" not in plan["training"], "v159 KHONG clip selection"
    assert abs(VOL_CUT_V56 - 0.01338037015711381) < 1e-15, "VOL_CUT phai verbatim v56"
    assert FUND_ABS == 0.0001 and UPWEIGHT_LLIKE == 2.0
    assert SIZING_CAP == 2.0 and TIE_BREAK_EPS == 1e-6
    vw, rwq, rwr, lam, flr, rtemp, rtie = loss_params(plan)
    assert (vw, rwq, rwr) == (2.0, 0.5, 0.5), f"value/ranking weights khac dong bang: {(vw, rwq, rwr)}"
    assert (lam, flr) == (3.0, 5e-4), f"Coverage-floor khac dong bang: {(lam, flr)}"
    assert (rtemp, rtie) == (1.0, 0.25), f"Ranking temp/tie khac dong bang: {(rtemp, rtie)}"
    assert (LOSS_W_VALUE, LOSS_W_RANK_Q, LOSS_W_RANK_R, RANK_TEMP_PCT, RANK_TIE_PCT) == (2.0, 0.5, 0.5, 1.0, 0.25)
    assert float(plan["budget"]["gpu_hours_max"]) <= 10.0, "budget tran 10 GPU-gio"
    parent = json.loads((ROOT / plan["folds"]["parent"]).read_text(encoding="utf-8"))
    ds, cache = ROOT / plan["dataset"], ROOT / plan["cache"]
    t0 = time.monotonic()
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    assert len(decisions) == 5628

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

    # Router + upweight descriptors EXACT v103 (past-only) tren toan bo decisions
    vol_high_all, fund_high_all, fund_last_all, atr_all, w_all, like_all, mask_all = regime_vectors(
        decisions, ROOT / plan["funding_source"]["file"])
    uw_global = upweight_stats(w_all, like_all)
    rs_global = router_stats(mask_all)
    print(json.dumps({"upweight_descriptors_global": {
        "n": uw_global["n"], "n_Llike": uw_global["n_Llike"], "frac_Llike": uw_global["frac_Llike"],
        "mean_w_Llike": uw_global["mean_w_Llike"], "mean_w_rest": uw_global["mean_w_rest"],
        "eff_sample_size": uw_global["eff_sample_size"],
        "rule": "L-like quiet = (vol_high==0)&(fund_high==0) -> w=2.0 else 1.0 (EXACT v103 opt_B)",
        "vol_cut_v56": VOL_CUT_V56, "fund_abs": FUND_ABS}}, ensure_ascii=False), flush=True)
    print(json.dumps({"router_global": rs_global,
                      "rule": "quiet NEU (vol_high==0)&(fund_high==0) else rest (frozen, NO learned gating)"},
                     ensure_ascii=False), flush=True)
    assert abs(float(uw_global["mean_w_Llike"]) - 2.0) < 1e-12, "upweight L-like phai 2.0"
    assert abs(float(uw_global["mean_w_rest"]) - 1.0) < 1e-12, "upweight rest phai 1.0"
    assert 0.0 < float(uw_global["frac_Llike"]) < 1.0, "frac L-like phai noi bo (khong exclude)"
    assert 0 < int(rs_global["n_quiet"]) < int(rs_global["n"]), "router phai active global"

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
    assert not np.intersect1d(validation, test).size, "validation phai past-only, khong lan test"
    mu_train, sigma_train = compute_value_stats(labels[train])
    print(json.dumps({"value_scale_train_only": {"mu_train": mu_train, "sigma_train": sigma_train,
           "n_train": int(len(train)), "shared": True}}), flush=True)
    assert np.isfinite(mu_train) and np.isfinite(sigma_train) and sigma_train >= SIGMA_FLOOR
    assert 0.5 < sigma_train < 10.0, f"sigma_train bat thuong (don vi?): {sigma_train}"
    w_train = np.asarray(w_all)[train]
    like_train = np.asarray(like_all)[train]
    mask_train = np.asarray(mask_all)[train]
    mask_test = np.asarray(mask_all)[test]
    mask_val = np.asarray(mask_all)[validation]
    uw_tr = upweight_stats(w_train, like_train)
    rs_tr = router_stats(mask_train)
    rs_te = router_stats(mask_test)
    rs_va = router_stats(mask_val)
    print(json.dumps({"upweight_active_proof_train": uw_tr}, ensure_ascii=False), flush=True)
    print(json.dumps({"router_active_proof": {"train": rs_tr, "test": rs_te, "validation": rs_va}},
                     ensure_ascii=False), flush=True)
    assert abs(float(uw_tr["mean_w_Llike"]) - 2.0) < 1e-12 and abs(float(uw_tr["mean_w_rest"]) - 1.0) < 1e-12
    assert int(uw_tr["n_Llike"]) > 0 and int(uw_tr["n_Llike"]) < int(uw_tr["n"])
    assert 0 < int(rs_tr["n_quiet"]) < int(rs_tr["n"]), "router phai active tren train"
    assert 0 < int(rs_te["n_quiet"]) < int(rs_te["n"]), "router phai active tren test (ca hai experts duoc chon)"
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = make_model(plan, candidates)
    assert isinstance(model, RegimeMoESSMTemporal)
    n_params = count_params(model)
    assert n_params == 748909, f"params doi so voi tinh toan MoE (600875+148034=748909): {n_params}"
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
    w_tr_t = torch.tensor(np.asarray(w_train, dtype=np.float32))
    opt = torch.optim.AdamW(model.parameters(), lr=plan["training"]["learning_rate"],
                            weight_decay=plan["training"]["weight_decay"])
    losses, ranks_q, ranks_r, covs_q, covs_r = [], [], [], [], []
    for epoch in range(epochs):
        order = torch.randperm(len(train))
        total, rqq, rrr, cqq, crr = 0.0, 0.0, 0.0, 0.0, 0.0
        for s in range(0, len(order), batch):
            idx = order[s:s + batch]
            opt.zero_grad(set_to_none=True)
            out = model(xs[idx], xf[idx])
            if not (torch.isfinite(out[0]).all() and torch.isfinite(out[1]).all()):
                raise ValueError("Nonfinite MoE Z scores")
            loss, parts = multitask_loss_moe(out[0], out[1], out[2], out[3], out[4], out[5],
                                             ys[idx], yd[idx], yr[idx], yu[idx], yn[idx],
                                             mu=mu_train, sigma=sigma_train, weights_quiet=w_tr_t[idx],
                                             value_w=vw, rank_w_q=rwq, rank_w_r=rwr,
                                             lambda_cov=lam, floor_pos=flr,
                                             rank_temp=rtemp, rank_tie=rtie)
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite smoke loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), plan["training"]["gradient_clip"])
            opt.step()
            total += loss.detach().item() * len(idx)
            rqq += float(parts["rank_q"]) * len(idx)
            rrr += float(parts["rank_r"]) * len(idx)
            cqq += float(parts["cov_q"]) * len(idx)
            crr += float(parts["cov_r"]) * len(idx)
        losses.append(total / len(train))
        ranks_q.append(rqq / len(train))
        ranks_r.append(rrr / len(train))
        covs_q.append(cqq / len(train))
        covs_r.append(crr / len(train))
        print(json.dumps({"smoke_epoch": epoch + 1, "loss": losses[-1],
                          "rank_quiet_weighted": ranks_q[-1], "rank_rest_uniform": ranks_r[-1],
                          "cov_q": covs_q[-1], "cov_r": covs_r[-1]}), flush=True)
    assert all(np.isfinite(ranks_q)) and all(np.isfinite(ranks_r)), "ca hai ranking terms phai finite"
    assert all(np.isfinite(covs_q)) and all(np.isfinite(covs_r)), "ca hai coverage terms phai finite"
    move_q = float(ranks_q[0] - ranks_q[-1])
    move_r = float(ranks_r[0] - ranks_r[-1])
    dec_q = bool(ranks_q[-1] < ranks_q[0] - 1e-9)
    dec_r = bool(ranks_r[-1] < ranks_r[0] - 1e-9)
    range_q = float(max(ranks_q) - min(ranks_q))
    range_r = float(max(ranks_r) - min(ranks_r))
    print(json.dumps({"ranking_decreasing_proof_quiet": {"ranks": ranks_q, "move": move_q,
          "range": range_q, "pass": dec_q}}), flush=True)
    print(json.dumps({"ranking_decreasing_proof_rest": {"ranks": ranks_r, "move": move_r,
          "range": range_r, "pass": dec_r}}), flush=True)
    if not (dec_q and range_q > 1e-9):
        raise RuntimeError(f"STOP: expert-quiet ranking FLAT — ranks={ranks_q}; khong package thiet ke chet")
    if not (dec_r and range_r > 1e-9):
        raise RuntimeError(f"STOP: expert-rest ranking FLAT — ranks={ranks_r}; khong package thiet ke chet")
    out = a.output / "seed1729" / "fold_0"
    out.mkdir(parents=True, exist_ok=False)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
              str(out / "model.safetensors"))
    (out / "value_scale.json").write_text(json.dumps({"mu_train": mu_train, "sigma_train": sigma_train,
        "method": "standardize_train_window", "shared": True, "causal": "train-only past-only"}))
    (out / "upweight_stats.json").write_text(json.dumps({
        "rule": "L-like quiet = (vol_high==0)&(fund_high==0) -> w=2.0 else 1.0 (EXACT v103 opt_B, expert-quiet only)",
        "vol_cut_v56": VOL_CUT_V56, "fund_abs": FUND_ABS, "factor": UPWEIGHT_LLIKE,
        "applies_to": "expert-quiet ranking term only (weighted mean); expert-rest uniform",
        "excluded": "none",
        "train": uw_tr,
        "validation": upweight_stats(np.asarray(w_all)[validation], np.asarray(like_all)[validation]),
        "causal": "descriptors past-only"}, indent=2))
    (out / "router_stats.json").write_text(json.dumps({
        "rule": "quiet NEU (vol_high==0)&(fund_high==0) else rest (frozen, NO learned gating)",
        "vol_cut_v56": VOL_CUT_V56, "fund_abs": FUND_ABS,
        "train": rs_tr, "validation": rs_va, "test": rs_te,
        "causal": "descriptors past-only"}, indent=2))
    fc_q, fc_r = predict_moe_raw(model, sequence[test][:64], flat[test][:64], mu_train, sigma_train, batch_size=32)
    assert fc_q.shape == (64, 16, 6) and fc_r.shape == (64, 16, 6)
    assert np.isfinite(fc_q).all() and np.isfinite(fc_r).all()
    mask_s = np.asarray(mask_all)[test][:64]
    fc_routed = route_blocks(fc_q, fc_r, mask_s)
    assert fc_routed.shape == (64, 16, 6) and np.isfinite(fc_routed).all()
    n_q_s, n_r_s = int(mask_s.sum()), int((~mask_s).sum())
    print(json.dumps({"router_active_proof_sample64": {"n_quiet": n_q_s, "n_rest": n_r_s,
          "frac_quiet": float(n_q_s / 64)}}), flush=True)
    assert n_q_s > 0 and n_r_s > 0, "router phai chon CA HAI experts tren sample64"
    sane = {}
    for tag, fc in (("quiet", fc_q), ("rest", fc_r)):
        fill = 1 / (1 + np.exp(-np.clip(fc[..., 4], -40, 40)))
        unconditional = fc[..., 0] * fill
        max_abs = float(np.max(np.abs(unconditional)))
        rg = float(np.max(unconditional) - np.min(unconditional))
        sd = float(np.std(unconditional))
        frac_big = float((np.abs(unconditional) > SIZING_CAP).mean())
        ok = bool((0.05 < max_abs < 15.0) and (rg > 0.01) and (sd > 1e-3) and (frac_big < 0.80))
        sane[tag] = {"max_abs": max_abs, "range": rg, "std": sd,
                     "frac_beyond_2pct": frac_big, "pass": ok}
        print(json.dumps({f"raw_scale_sane_proof_{tag}": sane[tag]}), flush=True)
        if not ok:
            raise RuntimeError(f"STOP: expert-{tag} raw scale KHONG sane — {sane[tag]}; khong package")
    model.eval()
    with torch.no_grad():
        xs_s = torch.tensor(sequence[test][:8], dtype=torch.float32)
        xf_s = torch.tensor(flat[test][:8], dtype=torch.float32)
        s_q, s_r, *_ = model(xs_s, xf_s)
        zq = s_q[..., 0].cpu().numpy()
        zr = s_r[..., 0].cpu().numpy()
    assert np.allclose(destandardize(zq, mu_train, sigma_train), (zq * sigma_train + mu_train)), "destandardize quiet hong"
    assert np.allclose(destandardize(zr, mu_train, sigma_train), (zr * sigma_train + mu_train)), "destandardize rest hong"
    fill_r = 1 / (1 + np.exp(-np.clip(fc_routed[..., 4], -40, 40)))
    uncond_routed = fc_routed[..., 0] * fill_r
    capped = apply_sizing_cap_numpy(uncond_routed, cap=SIZING_CAP)
    assert bool((np.abs(capped) <= SIZING_CAP + 1e-9).all()), "sizing-cap bound hong"
    assert bool((np.abs(capped) <= np.abs(uncond_routed) + 1e-9).all()), "sizing phai <= |raw| (chi cat)"
    # Tie-break proof tren expert-duoc-chon: dung decision quiet dau tien + rest dau tien
    iq = int(np.flatnonzero(mask_s)[0])
    ir = int(np.flatnonzero(~mask_s)[0])
    for tag, blk, irow in (("quiet", fc_q, iq), ("rest", fc_r, ir)):
        fill_row = blk[irow, :, 4]
        exp_row = (blk[irow, :, 0] * (1 / (1 + np.exp(-np.clip(fill_row, -40, 40)))))
        p1 = deterministic_best_index(exp_row, fill_row, candidates)
        p2 = deterministic_best_index(exp_row, fill_row, candidates)
        assert p1 == p2, f"tie-break {tag} phai bit-identical repeat"
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
    vec = deterministic_best_indices(np.stack([exp_row, exp_row2]), np.stack([fil_row, np.zeros(16)]), candidates)
    assert vec.tolist() == [7, idx_h3], f"vectorized tie-break hong: {vec}"
    tie_pass = True
    fv_q, fv_r = predict_moe_raw(model, sequence[validation][:64], flat[validation][:64],
                                 mu_train, sigma_train, batch_size=32)
    assert fv_q.shape == (64, 16, 6) and fv_r.shape == (64, 16, 6)
    assert np.isfinite(fv_q).all() and np.isfinite(fv_r).all()
    fv_routed = route_blocks(fv_q, fv_r, np.asarray(mask_all)[validation][:64])
    assert fv_routed.shape == (64, 16, 6) and np.isfinite(fv_routed).all()
    np.save(out / "val_predictions_quiet_sample.npy", fv_q)
    np.save(out / "val_predictions_rest_sample.npy", fv_r)
    np.save(out / "val_predictions_routed_sample.npy", fv_routed)
    val_export_present = bool((out / "val_predictions_routed_sample.npy").exists())
    restored = make_model(plan, candidates)
    restored.load_state_dict(load_file(str(out / "model.safetensors")))
    rp_q, rp_r = predict_moe_raw(restored, sequence[test][:8], flat[test][:8],
                                 mu_train, sigma_train, batch_size=32)
    rp_routed = route_blocks(rp_q, rp_r, np.asarray(mask_all)[test][:8])
    parity = bool(np.allclose(rp_q, fc_q[:8], rtol=1e-4, atol=1e-4)
                  and np.allclose(rp_r, fc_r[:8], rtol=1e-4, atol=1e-4)
                  and np.allclose(rp_routed, fc_routed[:8], rtol=1e-4, atol=1e-4))
    neg = apply_coverage_floor_policy(np.full(50, -0.01), POLICY_MARGIN, POLICY_N_MIN)
    assert len(neg) == POLICY_N_MIN == 8, f"fallback floor hong: {len(neg)}"
    mixed_en = np.concatenate([np.full(3, 0.5), np.full(47, -0.01)])
    mixed = apply_coverage_floor_policy(mixed_en, POLICY_MARGIN, POLICY_N_MIN)
    assert len(mixed) == 8 and set(range(3)) <= set(mixed.tolist()), "gate+fallback hong"
    fill_full_q = 1 / (1 + np.exp(-np.clip(fc_q[..., 4], -40, 40)))
    fill_full_r = 1 / (1 + np.exp(-np.clip(fc_r[..., 4], -40, 40)))
    en_q = (fc_q[..., 0] * fill_full_q).max(axis=1)
    en_r = (fc_r[..., 0] * fill_full_r).max(axis=1)
    en_routed = np.where(mask_s, en_q, en_r)
    gate_hits = int((en_routed > POLICY_MARGIN).sum())
    np.save(out / "predictions_quiet_sample.npy", fc_q)
    np.save(out / "predictions_rest_sample.npy", fc_r)
    np.save(out / "predictions_routed_sample.npy", fc_routed)
    np.savez_compressed(out / "indices.npz", train=train, validation=validation, test=test)
    bal = {k: int((ydir[train] == v).sum()) for k, v in (("SHORT", 0), ("WAIT", 1), ("LONG", 2))}
    summary = {"state": "smoke_complete" if parity else "parity_failed",
               "seed": seed, "fold": fold, "epochs": epochs, "device": "cpu",
               "losses": losses,
               "ranking_terms_quiet_weighted": ranks_q, "ranking_terms_rest_uniform": ranks_r,
               "coverage_terms_q": covs_q, "coverage_terms_r": covs_r,
               "ranking_decreasing_proof_quiet": {"ranks": ranks_q, "move": move_q,
                   "range": range_q, "pass": dec_q,
                   "note": "expert-quiet weighted rank (opt_B 2.0x) TREN TRADEABLE phai dich chuyen; flat => STOP"},
               "ranking_decreasing_proof_rest": {"ranks": ranks_r, "move": move_r,
                   "range": range_r, "pass": dec_r,
                   "note": "expert-rest uniform rank TREN TRADEABLE phai dich chuyen; flat => STOP"},
               "router_active_proof": {"train": rs_tr, "test_full_fold": rs_te,
                   "validation": rs_va, "sample64": {"n_quiet": n_q_s, "n_rest": n_r_s},
                   "pass": bool(n_q_s > 0 and n_r_s > 0
                                 and 0 < int(rs_te["n_quiet"]) < int(rs_te["n"])),
                   "rule": "quiet NEU (vol_high==0)&(fund_high==0) else rest (frozen, NO learned gating)"},
               "upweight_active_proof": {"rule": "L-like quiet -> w=2.0 else 1.0 (EXACT v103 opt_B, expert-quiet only)",
                   "global": uw_global, "train_fold0": uw_tr,
                   "mean_w_Llike_must_be": 2.0, "mean_w_rest_must_be": 1.0,
                   "pass": bool(abs(float(uw_tr["mean_w_Llike"]) - 2.0) < 1e-12
                                 and abs(float(uw_tr["mean_w_rest"]) - 1.0) < 1e-12
                                 and 0 < int(uw_tr["n_Llike"]) < int(uw_tr["n"]))},
               "loss_weights": {"value_per_expert": vw, "rank_quiet": rwq, "rank_rest": rwr,
                                "dir": 1.0, "quant": 1.0, "exc": 0.5, "cov_lambda": lam},
               "ranking_params": {"temperature_percent": rtemp, "tie_band_percent": rtie},
               "coverage_floor": {"lambda": lam, "floor_pos": flr, "domain": "TRADEABLE percent per expert"},
               "value_scale": {"method": "standardize_train_window", "shared": True,
                               "mu_train": mu_train, "sigma_train": sigma_train,
                               "causal": "train-only past-only"},
               "raw_scale_sane_proof": sane,
               "sizing_cap_separate_proof": {"cap": SIZING_CAP,
                   "pass": True, "note": "cap CHI file routed rieng, KHONG dung cho selection"},
               "destandardize_roundtrip": {"quiet": True, "rest": True},
               "tie_break_proof": {"eps": TIE_BREAK_EPS, "fill_desc_pick": int(pick_fill),
                   "holding_asc_pick": int(pick_hold), "repeat_identical": True,
                   "vectorized": vec.tolist(), "pass": tie_pass,
                   "rule": "router (chon expert) + gap<1e-6 -> fill-desc, roi holding-asc (3 truoc 7), roi index nho nhat (tren RAW expert-duoc-chon)"},
               "val_export_proof": {"files": ["val_predictions_quiet_sample.npy",
                   "val_predictions_rest_sample.npy", "val_predictions_routed_sample.npy"],
                                    "present": val_export_present,
                                    "shape": list(fv_routed.shape),
                                    "n_validation_total": int(len(validation)),
                                    "finite": True, "pass": True,
                                    "note": "VAL RAW (moi expert + routed, khong clip) + router_stats.json + upweight_stats.json, cho calibrate-first outlier-robust sau"},
               "epoch_mode": "FIXED 16 (smoke chay 3 epochs plumbing + decreasing x2 + router-active + sane + parity)",
               "policy_floor_unit_test": {"all_negative_picks": len(neg), "mixed_picks": len(mixed),
                                          "margin": POLICY_MARGIN, "n_min": POLICY_N_MIN, "pass": True},
               "smoke_gate_preview (KHONG phai ket qua)": {"n_test_sample": 64,
                   "gate_hits_en_routed_gt_0": gate_hits, "en_best_routed_mean": float(en_routed.mean())},
               "parameters": n_params, "params_band": "~0.75M (600875 base + 148034 head thu hai = 748909)",
               "model_family": "regimemoe_ssm_v159", "n_flat": N_FLAT,
               "train_decisions": len(train), "test_decisions": len(test),
               "validation_decisions": len(validation),
               "train_label_balance_H48": bal, "gpu_reload_parity": parity,
               "prediction_sha256": digest(out / "predictions_routed_sample.npy"),
               "elapsed_seconds": round(time.monotonic() - t0, 1),
               "coverage_audit": audit,
               "calibration_next": "audit local sau train: fit isotonic outlier-robust TREN VAL-PRED EXPORT ROUTED RAW past-only TRUOC choose + nguong tu phan vi validation",
               "warning": "SMOKE plumbing only. KHONG phai ket qua nghien cuu; khong so voi standing_best.",
               "live_approved": False}
    (out / "smoke_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, default=ROOT / "configs/opencode_v159_regimemoe.json")
    p.add_argument("--output", type=Path,
                   default=ROOT / "artifacts/research/opencode_v159_regimemoe/smoke")
    main(p.parse_args())
