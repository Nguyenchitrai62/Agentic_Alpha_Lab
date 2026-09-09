"""Opencode R48-M DIAG v132 (train-only plumbing diagnostic, KHONG phai ket qua nghien cuu).

Boi canh: smoke 3-epoch dau tien KL TANG (0.164->0.208) trong khi rank GIAM va
entropy TREN floor (2.71>2.20). Day la mat can bang huong gradient (ListNet-on-hard
keo di xa teacher diffuse-tau8) chu khong phai mass-collapse (entropy van cao).
Diag nay chay train-only tren fold_1/seed1729 de phan biet:
  A: spec hien tai (KL+ent+rank0.1+cov) x 6 epochs — KL co U-turn khong?
  B: KL-only (rank_w=0, giu ent+cov) x 3 epochs — encoder co distill duoc khong?
Ket luan du kien: B giam + A tiep tuc tang => xung dot loss mang tinh cau truc
=> STOP theo mission (khong package). A giam => xem xet plumbing (khong fit gate).
KHONG dung test/PnL, KHONG export, KHONG anh huong config.
"""
import torch  # noqa: F401  (torch truoc pandas)
import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from opencode_r48m_attndistill_features import N_FLAT, build_flat  # noqa: E402
from opencode_r48m_attndistill_model import AttnDistillTemporal  # noqa: E402
from opencode_r48m_attndistill_train import (  # noqa: E402
    fold_indices,
    load_soft_bundle,
    loss_params,
    make_model,
)
from agentic_alpha_lab.models.temporal_validation import nested_split  # noqa: E402
from train_tcn_kaggle import stable_evaluation_backend  # noqa: E402
import pandas as pd  # noqa: E402


def run_variant(train_fn_note, rank_w_override, epochs, sequence, flat, labels,
                train, tr_soft_mask, soft_pos_train, soft_mat, plan, candidates, seed,
                lr_override=None):
    import torch
    from opencode_r48m_attndistill_model import (
        attndistill_loss_from_parts, student_kl,
    )
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = make_model(plan, candidates)
    model.feature_mean.copy_(torch.tensor(flat[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(flat[train].std(0), 1e-6), dtype=torch.float32))
    model.train()
    xs = torch.tensor(sequence[train], dtype=torch.float32)
    xf = torch.tensor(flat[train], dtype=torch.float32)
    ys = torch.tensor(labels[train], dtype=torch.float32)
    kw, entw, entf, rw, lam, flr, rtemp = loss_params(plan)
    rw = float(rank_w_override)
    lr = float(lr_override) if lr_override is not None else float(plan["training"]["learning_rate"])
    opt = torch.optim.AdamW(model.parameters(), lr=lr,
                            weight_decay=plan["training"]["weight_decay"])
    batch = 32
    kls, ranks = [], []
    for epoch in range(epochs):
        order = torch.randperm(len(train))
        ktot, rtot = 0.0, 0.0
        for s in range(0, len(order), batch):
            idx = order[s:s + batch]
            opt.zero_grad(set_to_none=True)
            logits = model(xs[idx], xf[idx])
            gmask_np = tr_soft_mask[idx.numpy()]
            if gmask_np.any():
                sm = torch.as_tensor(soft_mat[soft_pos_train[idx.numpy()][gmask_np]], dtype=torch.float32)
                kl = student_kl(logits[torch.as_tensor(gmask_np)], sm)
            else:
                kl = logits.new_zeros(())
            total_b, parts = attndistill_loss_from_parts(
                float(kl.detach()), logits, ys[idx],
                kl_w=kw, ent_w=entw, rank_w=rw, lambda_cov=lam,
                floor_pos=flr, rank_temp=rtemp, floor_nats=entf)
            total_b.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), plan["training"]["gradient_clip"])
            opt.step()
            ktot += float(parts["kl"]) * len(idx)
            rtot += float(parts["rank"]) * len(idx)
        kls.append(ktot / len(train))
        ranks.append(rtot / len(train))
        print(json.dumps({"variant": train_fn_note, "epoch": epoch + 1,
                          "kl": kls[-1], "rank": ranks[-1]}), flush=True)
    return kls, ranks


def main(a):
    torch.set_num_threads(2)
    torch.backends.mha.set_fastpath_enabled(False)
    stable_evaluation_backend()
    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    assert plan.get("model_family") == "distill_attn_v132"
    parent = json.loads((ROOT / plan["folds"]["parent"]).read_text(encoding="utf-8"))
    ds, cache = ROOT / plan["dataset"], ROOT / plan["cache"]
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    flat = build_flat(decisions, candles, ds / "examples.npz",
                      ROOT / "artifacts/features/btc_derivatives_lag48_v1/features.npz",
                      ROOT / plan["funding_source"]["file"], ROOT / plan["macro_source"]["dir"])
    with np.load(ds / "examples.npz", allow_pickle=False) as z:
        labels = z["labels"]
    sequence = np.load(cache / "sequences.npy", allow_pickle=False)
    cfg = json.loads((ds / "config.json").read_text(encoding="utf-8"))
    candidates = np.asarray([[s, e, *b, d] for s in (1, -1) for e in cfg["entry_atr_5m"]
                             for b in cfg["brackets_atr_4h"] for d in cfg["holding_days"]], np.float32)
    soft_mat, soft_indices, soft_fold, soft_pos, soft_path = load_soft_bundle(ROOT, plan)
    seed, fold = 1729, 1
    train, test = fold_indices(decisions, parent, plan, fold)
    n = len(decisions)
    soft_idx_of = np.full(n, -1, dtype=np.int64)
    for ix, p in soft_pos.items():
        soft_idx_of[int(ix)] = int(p)
    tr_soft_mask = soft_idx_of[train] >= 0
    soft_pos_train = soft_idx_of[train]
    print(json.dumps({"diag_setup": {"fold": fold, "n_train": len(train),
          "n_train_soft": int(tr_soft_mask.sum())}}), flush=True)
    # Rerun nhe (A/B da co ket qua o diag/diag_summary.json): chi C2 + D.
    kls_c2, ranks_c2 = run_variant("C2-klonly-lr1e4", 0.0, 3, sequence, flat, labels,
                                   train, tr_soft_mask, soft_pos_train, soft_mat,
                                   plan, candidates, seed, lr_override=1e-4)
    kls_d, ranks_d = run_variant("D-spec-lr1e4-4ep", 0.1, 4, sequence, flat, labels,
                                 train, tr_soft_mask, soft_pos_train, soft_mat,
                                 plan, candidates, seed, lr_override=1e-4)
    summary = {
        "C2_klonly_lr1e4": {"kls": kls_c2, "ranks": ranks_c2,
                            "kl_last_lt_first": bool(kls_c2[-1] < kls_c2[0] - 1e-9)},
        "D_spec_lr1e4_4ep": {"kls": kls_d, "ranks": ranks_d,
                             "kl_last_lt_first": bool(kls_d[-1] < kls_d[0] - 1e-9)},
        "prior": "A_spec_6ep KL tang net (0.164->0.212, dao dong), B_klonly_3ep KL tang (0.131->0.137): xem artifacts/research/opencode_v132_attndistill/diag/diag_summary.json",
        "interpretation": "C2 giam + D giam => LR plumbing (fix config LR truoc packaging, trung thuc bao cao). C2 giam + D tang => xung dot loss cau truc => STOP. C2 tang => STOP.",
        "live_approved": False,
    }
    out = a.output
    out.mkdir(parents=True, exist_ok=True)
    (out / "diag_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, default=ROOT / "configs/opencode_v132_attndistill.json")
    p.add_argument("--output", type=Path,
                   default=ROOT / "artifacts/research/opencode_v132_attndistill/diag")
    main(p.parse_args())
