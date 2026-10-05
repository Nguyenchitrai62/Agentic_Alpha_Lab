"""tp worker (tournament, dev-only): take-profit choice {0.5, 1.0, 1.5} sigma as a full-information contextual bandit. See PLAN.md.

    .venv/Scripts/python.exe research/tournament/tp/tp_bandit.py <variant|refs>
variants: v1_cls, v2_diff, v3_mlp, v4_bot_only. Writes score_<variant>.json and tp_<variant>.parquet (test-row decisions + fold info).
Leakage: per fold only rows with t_exit < anchor - 7 d are used for fitting, imputation, scaling, margins and early stopping (inner
chronological split inside them); features are bar-open (<= T + 1 min) except v4_bot_only (fill-time x0..x6, labelled bot_only).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import torch  # noqa: F401  (import before pandas on this host)
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import harness as H  # noqa: E402

BO = ["bo_sp30", "bo_volreg", "bo_trend", "bo_btc_sp30", "bo_dd24", "hour", "r1h", "r4h", "r24h", "r72h", "rng24", "dd7", "du7", "rv24",
      "btc_r4h", "btc_r24h", "btc_dd24"]
FEAT = BO + ["k"]
BOT = FEAT + ["x0", "x2", "x3", "x4", "x5", "x6"]
ACT = np.array([0.5, 1.0, 1.5])
MARGINS = [0.0, 0.0005, 0.001, 0.002, 0.003, np.inf]
HGB = dict(max_depth=3, learning_rate=0.05, max_iter=300, min_samples_leaf=200, l2_regularization=1.0, random_state=0)


def data():
    d = H.load()
    bo = pd.read_parquet(HERE.parent / "data/bar_open.parquet")
    f = pd.read_parquet(H.FILLS)
    bo = bo[(f.t_fill < H.DEV_END).to_numpy()].reset_index(drop=True)
    assert len(bo) == len(d) and (bo.j.to_numpy() == d.j.to_numpy()).all() and (bo.sym.to_numpy() == d.sym.to_numpy()).all() \
        and (bo.r.to_numpy() == d.r.to_numpy()).all(), "bar_open join mismatch"
    for c in BO:
        d[c] = bo[c].to_numpy()
    Y = np.clip(d[["y0.5", "y1.0", "y1.5"]].to_numpy(float), -0.10, 0.08)
    return d, Y


def inner_split(d, tr):
    """Inner chronological split inside the training rows: val = last 25 % by T, inner-train = t_exit < first val T - 7 d."""
    idx = np.flatnonzero(tr)
    T = d["T"].to_numpy()[idx]
    cut = np.sort(T)[int(0.75 * len(T))]
    va = np.zeros(len(d), bool); va[idx[T >= cut]] = True
    it = tr & (d.t_exit < pd.Timestamp(cut) - H.EMBARGO).to_numpy()
    return it, va


# ---------------------------------------------------------------- V1
def v1(d, Y, tr, te, cols):
    X = d[cols].to_numpy(float)
    lab = np.argmax(Y + np.array([0, 1e-9, 0]), 1)
    w = Y.max(1) - Y.min(1)
    fit = tr & (w > 0)
    M = np.array([Y[fit & (lab == c)].mean(0) for c in range(3)])
    clf = HistGradientBoostingClassifier(**HGB).fit(X[fit], lab[fit], sample_weight=w[fit])
    P = np.zeros((te.sum(), 3)); P[:, clf.classes_] = clf.predict_proba(X[te])
    ev = P @ M
    return ACT[np.argmax(ev, 1)], dict(M=M.round(5).tolist())


# ---------------------------------------------------------------- V2 / V4
def diff_models(X, Y, m):
    return [HistGradientBoostingRegressor(**HGB).fit(X[m], Y[m, c] - Y[m, 1]) for c in (0, 2)]


def diff_decide(models, X, margin):
    p = np.column_stack([models[0].predict(X), models[1].predict(X)])
    b = np.argmax(p, 1)
    best = p[np.arange(len(p)), b]
    return np.where(best > margin, np.where(b == 0, 0.5, 1.5), 1.0)


def v2(d, Y, tr, te, cols):
    X = d[cols].to_numpy(float)
    it, va = inner_split(d, tr)
    mods = diff_models(X, Y, it)
    gains = {}
    for m in MARGINS:
        a = diff_decide(mods, X[va], m)
        ya = np.select([a == 0.5, a == 1.5], [Y[va, 0], Y[va, 2]], Y[va, 1])
        gains[m] = float((ya - Y[va, 1]).sum())
    best = max(gains.values())
    margin = max(m for m, g in gains.items() if g >= best - 1e-12)
    mods = diff_models(X, Y, tr)
    return diff_decide(mods, X[te], margin), dict(margin=margin, inner_gain={str(k): round(v, 4) for k, v in gains.items()},
                                                  n_inner_train=int(it.sum()), n_inner_val=int(va.sum()))


# ---------------------------------------------------------------- V3
def v3(d, Y, tr, te, cols, seeds=5):
    import torch.nn as nn
    torch.set_num_threads(4)
    X = d[cols].to_numpy(float)
    it, va = inner_split(d, tr)
    med = np.nanmedian(X[it], 0)
    Xf = np.where(np.isfinite(X), X, med)
    mu, sd = Xf[it].mean(0), Xf[it].std(0) + 1e-9
    Z = ((Xf - mu) / sd).astype(np.float32)
    R = ((Y - Y[:, [1]]) / 0.01).astype(np.float32)
    Zt, Rt = torch.from_numpy(Z[it]), torch.from_numpy(R[it])
    Zv, Rv = torch.from_numpy(Z[va]), torch.from_numpy(R[va])
    Zte = torch.from_numpy(Z[te])
    probs, info = [], []
    for s in range(seeds):
        torch.manual_seed(s); g = np.random.default_rng(s)
        net = nn.Sequential(nn.Linear(Z.shape[1], 64), nn.ReLU(), nn.Dropout(0.1), nn.Linear(64, 64), nn.ReLU(), nn.Dropout(0.1),
                            nn.Linear(64, 3))
        opt = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-4)
        best, best_state, bad, ep_best = -np.inf, None, 0, 0
        for ep in range(60):
            net.train()
            perm = g.permutation(len(Zt))
            for b0 in range(0, len(perm), 512):
                bi = torch.from_numpy(perm[b0:b0 + 512])
                loss = -(torch.softmax(net(Zt[bi]), 1) * Rt[bi]).sum(1).mean()
                opt.zero_grad(); loss.backward(); opt.step()
            net.eval()
            with torch.no_grad():
                v = float((torch.softmax(net(Zv), 1) * Rv).sum(1).mean())
            if v > best + 1e-6:
                best, best_state, bad, ep_best = v, {k: t.clone() for k, t in net.state_dict().items()}, 0, ep
            else:
                bad += 1
                if bad >= 8:
                    break
        net.load_state_dict(best_state); net.eval()
        with torch.no_grad():
            probs.append(torch.softmax(net(Zte), 1).numpy())
        info.append(dict(seed=s, best_epoch=ep_best, inner_val_reward=round(best, 5)))
    P = np.mean(probs, 0)
    return ACT[np.argmax(P, 1)], dict(seeds=info, n_inner_train=int(it.sum()), n_inner_val=int(va.sum()))


def run(variant):
    d, Y = data()
    tp = np.full(len(d), np.nan)
    fold_info = []
    for y, a0, tr, te in H.folds(d):
        assert d.t_exit[tr].max() < a0 - H.EMBARGO and d["T"][te].min() >= a0
        if variant == "v1_cls":
            a, inf = v1(d, Y, tr, te, FEAT)
        elif variant == "v2_diff":
            a, inf = v2(d, Y, tr, te, FEAT)
        elif variant == "v3_mlp":
            a, inf = v3(d, Y, tr, te, FEAT)
        elif variant == "v4_bot_only":
            a, inf = v2(d, Y, tr, te, BOT)
        else:
            raise SystemExit(variant)
        tp[te] = a
        fold_info.append(dict(year=str(a0.date()), n_train=int(tr.sum()), n_test=int(te.sum()),
                              tp_counts={str(k): int(v) for k, v in pd.Series(a).value_counts().items()}, **inf))
        print(variant, a0.date(), fold_info[-1], flush=True)
    name = variant + ("  [bot_only: fill-time features]" if variant == "v4_bot_only" else "")
    res = H.score_tp(d, tp, name)
    res["folds"] = fold_info
    (HERE / f"score_{variant}.json").write_text(json.dumps(res, indent=1))
    te_all = np.isfinite(tp)
    pd.DataFrame({"row": np.flatnonzero(te_all), "T": d["T"][te_all].to_numpy(), "sym": d.sym[te_all].to_numpy(), "k": d.k[te_all].to_numpy(),
                  "tp_dep": d.tp_dep[te_all].to_numpy(), "tp_new": tp[te_all]}).to_parquet(HERE / f"tp_{variant}.parquet")
    print(json.dumps(res, indent=1))


def refs():
    d, _ = data()
    out = {}
    for nm, v in (("const_1.0", np.full(len(d), 1.0)), ("const_1.5", np.full(len(d), 1.5))):
        out[nm] = H.score_tp(d, v, nm)
    Yr = d[["y0.5", "y1.0", "y1.5"]].to_numpy()
    out["oracle"] = H.score_tp(d, ACT[np.argmax(Yr + np.array([0, 1e-9, 0]), 1)], "oracle (upper bound, uses outcomes)")
    (HERE / "score_references.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    refs() if sys.argv[1] == "refs" else run(sys.argv[1])
