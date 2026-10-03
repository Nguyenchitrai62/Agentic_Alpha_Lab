"""v372 Kaggle GPU job: walk-forward CNN dip SIZE agent on bar-open sequences (writes predictions only; no selection inside).

Data: v372_seq_data.py (train.npz: pooled fills X state[7], S coin sequence[240], B BTC sequence[240], y = y1.0, j, t_exit; table.npz: majors x
bars from the first anchor, same inputs). For every anchor a (5) and cross-fit half h in (0, 1) (j % 2, as the HGB agents): train on fills with
t_exit < a - 7 days and j % 2 == h (the last 10 % of them by exit time = early-stopping validation, still before the cutoff), predict every table row
of the year starting at a at each of the seven depths (state x1 = depth) -> pa (h = 0), pb (h = 1); mu = mean y of the training fills (both halves).
Model: Conv1d(2, 16, 7) - ReLU - Conv1d(16, 32, 5, stride 2) - ReLU - Conv1d(32, 32, 5, stride 2) - ReLU - global average pool (32) concat the
standardised state (7, NaN -> 0) -> Linear(39, 32) - ReLU - Linear(32, 1); target y x 100; MSE; Adam 1e-3, weight decay 1e-4, batch 512, at most 30
epochs, early stopping (patience 4) on the validation MSE; seed 372 + anchor * 10 + h. Output: v372_cnn_preds.parquet (T, sym, k, pa, pb, mu).
  python v372_cnn_train.py <data_dir> <out_dir>
"""
import sys
from pathlib import Path

import torch  # noqa: F401  (import before pandas on Windows)
import numpy as np
import pandas as pd
import torch.nn as nn

U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
EMB = 7 * 86400 * 10**9


class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(nn.Conv1d(2, 16, 7, padding=3), nn.ReLU(), nn.Conv1d(16, 32, 5, stride=2, padding=2), nn.ReLU(),
                                  nn.Conv1d(32, 32, 5, stride=2, padding=2), nn.ReLU())
        self.head = nn.Sequential(nn.Linear(39, 32), nn.ReLU(), nn.Linear(32, 1))

    def forward(self, seq, st):
        z = self.conv(seq).mean(-1)
        return self.head(torch.cat([z, st], 1)).squeeze(1)


def fit_predict(Xs, Ss, ys, Xv, Sv, yv, Xp, Sp, seed, dev):
    torch.manual_seed(seed)
    np.random.seed(seed)
    m_, s_ = np.nanmean(Xs, 0), np.nanstd(Xs, 0) + 1e-6
    norm = lambda X: np.nan_to_num((X - m_) / s_).astype(np.float32)
    T = lambda a: torch.tensor(a, device=dev)
    xs, ss, yy = T(norm(Xs)), T(Ss), T(ys * 100)
    xv, sv, yv_ = T(norm(Xv)), T(Sv), T(yv * 100)
    net = Net().to(dev)
    opt = torch.optim.Adam(net.parameters(), 1e-3, weight_decay=1e-4)
    best, best_state, bad = np.inf, None, 0
    n = len(ys)
    for ep in range(30):
        net.train()
        perm = torch.randperm(n, device=dev)
        for i in range(0, n, 512):
            b = perm[i:i + 512]
            opt.zero_grad()
            loss = ((net(ss[b], xs[b]) - yy[b]) ** 2).mean()
            loss.backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            v = float(((net(sv, xv) - yv_) ** 2).mean())
        if v < best - 1e-6:
            best, best_state, bad = v, {k: t.clone() for k, t in net.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= 4:
                break
    net.load_state_dict(best_state)
    net.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(Xp), 4096):
            out.append(net(T(Sp[i:i + 4096]), T(norm(Xp[i:i + 4096]))).cpu().numpy() / 100)
    return np.concatenate(out), best


def main(data, out):
    data, out = Path(data), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tr, tb = np.load(data / "train.npz"), np.load(data / "table.npz")
    X, S, y, j, tx = tr["X"], np.stack([tr["S"], tr["B"]], 1), tr["y"], tr["j"], tr["t_exit"]
    TXs, TS = tb["X"], np.stack([tb["S"], tb["B"]], 1)
    anchors = tb["anchors"]
    rows = []
    for a_i, a in enumerate(anchors):
        sel = tb["anchor"] == a_i
        if not sel.any():
            continue
        keep = tx < a - EMB
        mu = float(y[keep].mean())
        Xp = np.repeat(TXs[sel], len(U), 0)
        Xp[:, 1] = np.tile(U, sel.sum())
        Sp = np.repeat(TS[sel], len(U), 0)
        preds = {}
        for h in (0, 1):
            idx = np.where(keep & (j % 2 == h))[0]
            idx = idx[np.argsort(tx[idx])]
            cut = int(len(idx) * 0.9)
            p, v = fit_predict(X[idx[:cut]], S[idx[:cut]], y[idx[:cut]], X[idx[cut:]], S[idx[cut:]], y[idx[cut:]], Xp, Sp, 372 + 10 * a_i + h, dev)
            preds[h] = p
            print("anchor", a_i, "half", h, "train", cut, "val mse", round(v, 4), flush=True)
        rows.append(pd.DataFrame({"T": np.repeat(tb["T"][sel], len(U)), "sym": np.repeat(tb["sym"][sel], len(U)), "k": np.tile(U, sel.sum()),
                                  "pa": preds[0], "pb": preds[1], "mu": mu}))
    df = pd.concat(rows, ignore_index=True)
    df["T"] = pd.to_datetime(df["T"], utc=True)
    df.to_parquet(out / "v372_cnn_preds.parquet")
    print("saved", len(df), flush=True)


def _kaggle_default_argv():
    ins = sorted(Path("/kaggle/input").rglob("train.npz"))
    return [str(ins[0].parent), "/kaggle/working"] if ins else []


if __name__ == "__main__":
    args = sys.argv[1:] or _kaggle_default_argv()
    main(*args)
