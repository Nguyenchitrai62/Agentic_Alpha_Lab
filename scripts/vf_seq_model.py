"""Small cross-asset sequence model (TCN + GRU) predicting BTC 2-day vol-normalized return.

For each anchor A (expanding window), train only on labels realized before A - embargo,
then predict every 4h bar in [A, next anchor). Predictions are saved aligned to the
BTC 4h index for use by the vf family "seq". Light model; local GPU inference/training.
"""

from __future__ import annotations

import torch  # noqa: I001  (import torch before pandas on this Windows host)

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns.common import load_bars, load_funding
from agentic_alpha_lab.research_vf import ANCHORS, EMBARGO_DAYS

ALTS = ["ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT", "TRXUSDT"]
XA = Path("data/raw/xasset_20260924")
OUT = Path("artifacts/research/vf/seq")
H, WIN = 12, 120
import os
H = int(os.environ.get("SEQ_H", H))


def asset_feats(b: pd.DataFrame) -> pd.DataFrame:
    lc = np.log(b["close"])
    f = pd.DataFrame(index=b.index)
    f["r1"] = lc.diff()
    f["r6"] = lc.diff(6)
    f["hl"] = np.log(b["high"] / b["low"])
    f["co"] = np.log(b["close"] / b["open"])
    lv = np.log(b["quote_volume"].clip(lower=1))
    f["vz"] = (lv - lv.rolling(42).mean()) / lv.rolling(42).std()
    f["tk"] = b["taker_buy_volume"] / b["volume"].replace(0, np.nan) - 0.5
    f["d20"] = np.log(b["close"] / b["close"].ewm(span=20, adjust=False).mean())
    f["d200"] = np.log(b["close"] / b["close"].ewm(span=200, adjust=False).mean())
    return f


def build():
    btc = load_bars("4h", include_opened_year=True)
    feats = [asset_feats(btc).add_prefix("BTC_")]
    key = btc[["close_time"]].copy()
    for s in ALTS:
        a = pd.read_parquet(XA / f"{s}_4h.parquet")
        fa = asset_feats(a).add_prefix(f"{s}_")
        fa["close_time"] = a["close_time"].to_numpy()
        m = pd.merge_asof(key, fa.sort_values("close_time"), on="close_time", direction="backward", tolerance=pd.Timedelta("1h"))
        m.index = btc.index
        feats.append(m.drop(columns=["close_time"]))
    f = load_funding(include_opened_year=True)
    right = pd.DataFrame({"close_time": f["fundingTime"].to_numpy(), "fund": f["fundingRate"].rolling(21, min_periods=1).mean().to_numpy()})
    fund = pd.merge_asof(key, right, on="close_time", direction="backward")["fund"].to_numpy() * 1e4
    x = pd.concat(feats, axis=1)
    x["BTC_fund"] = fund
    o, c = btc["open"].to_numpy(), btc["close"].to_numpy()
    n = len(btc)
    fwd = np.full(n, np.nan)
    fwd[: n - 1 - H] = np.log(o[1 + H:] / o[1: n - H])
    vol = pd.Series(np.log(c)).diff().rolling(180).std().to_numpy() * np.sqrt(H)
    y = np.clip(fwd / vol, -4, 4)
    return btc, x, y


class Net(torch.nn.Module):
    def __init__(self, d_in: int, hid: int = 48):
        super().__init__()
        self.conv = torch.nn.Sequential(
            torch.nn.Conv1d(d_in, hid, 3, padding=2, dilation=1), torch.nn.GELU(),
            torch.nn.Conv1d(hid, hid, 3, padding=4, dilation=2), torch.nn.GELU(),
            torch.nn.Conv1d(hid, hid, 3, padding=8, dilation=4), torch.nn.GELU())
        self.gru = torch.nn.GRU(hid, hid, batch_first=True)
        self.drop = torch.nn.Dropout(0.2)
        self.head = torch.nn.Linear(hid, 2)  # regression, sign logit

    def forward(self, x):  # x: (B, T, F)
        h = self.conv(x.transpose(1, 2))[:, :, : x.shape[1]]  # causal crop (left context only)
        out, _ = self.gru(h.transpose(1, 2))
        return self.head(self.drop(out[:, -1]))


def windows(xv: np.ndarray, idx: np.ndarray) -> np.ndarray:
    return np.stack([xv[i - WIN + 1: i + 1] for i in idx])


def train_predict(xv, y, train_idx, pred_idx, seed, dev):
    torch.manual_seed(seed)
    np.random.seed(seed)
    n_val = max(int(len(train_idx) * 0.15), 200)
    tr, va = train_idx[:-n_val - H], train_idx[-n_val:]  # purge H bars between train and validation
    net = Net(xv.shape[1]).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-3)
    Xva = torch.tensor(windows(xv, va), device=dev)
    yva = torch.tensor(y[va], device=dev, dtype=torch.float32)
    best, best_state, bad = np.inf, None, 0
    for ep in range(30):
        net.train()
        perm = np.random.permutation(tr)
        for k in range(0, len(perm), 256):
            bi = perm[k:k + 256]
            xb = torch.tensor(windows(xv, bi), device=dev)
            yb = torch.tensor(y[bi], device=dev, dtype=torch.float32)
            out = net(xb)
            loss = torch.nn.functional.huber_loss(out[:, 0], yb) + 0.5 * torch.nn.functional.binary_cross_entropy_with_logits(out[:, 1], (yb > 0).float())
            opt.zero_grad()
            loss.backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            ov = net(Xva)
            vl = float(torch.nn.functional.huber_loss(ov[:, 0], yva))
        if vl < best - 1e-4:
            best, bad = vl, 0
            best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
        else:
            bad += 1
            if bad >= 5:
                break
    net.load_state_dict(best_state)
    net.eval()
    preds = []
    with torch.no_grad():
        for k in range(0, len(pred_idx), 1024):
            preds.append(net(torch.tensor(windows(xv, pred_idx[k:k + 1024]), device=dev))[:, 0].cpu().numpy())
    return np.concatenate(preds), best, ep + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    a = ap.parse_args()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    btc, x, y = build()
    ot = btc["open_time"]
    n = len(btc)
    pred = np.full(n, np.nan)
    log = []
    anchors = list(ANCHORS)
    for i, anchor in enumerate(anchors):
        t0 = time.time()
        A = pd.Timestamp(anchor, tz="UTC")
        a_idx = int(np.flatnonzero(ot >= A)[0])
        end_idx = int(np.flatnonzero(ot >= pd.Timestamp(anchors[i + 1], tz="UTC"))[0]) if i + 1 < len(anchors) else n
        cut = int(np.flatnonzero(ot < A - pd.Timedelta(days=EMBARGO_DAYS))[-1])
        realized = np.arange(n) + 1 + H
        first = WIN + 200
        train_idx = np.array([t for t in range(first, cut) if realized[t] < cut and np.isfinite(y[t])])
        # scaler on training rows only
        mu = np.nanmean(x.iloc[train_idx].to_numpy(), axis=0)
        sd = np.nanstd(x.iloc[train_idx].to_numpy(), axis=0) + 1e-8
        xv = np.nan_to_num(np.clip((x.to_numpy() - mu) / sd, -6, 6), nan=0.0).astype(np.float32)
        pred_idx = np.arange(a_idx, min(end_idx, n))
        ps, info = [], []
        for s in range(a.seeds):
            p, vl, ep = train_predict(xv, y, train_idx, pred_idx, s, dev)
            ps.append(p)
            info.append(dict(seed=s, val_huber=round(vl, 4), epochs=ep))
        pred[pred_idx] = np.mean(ps, axis=0)
        yy = y[pred_idx]
        m = np.isfinite(yy)
        ic = float(pd.Series(pred[pred_idx][m]).corr(pd.Series(yy[m]), method="spearman"))
        hit = float(np.mean(np.sign(pred[pred_idx][m]) == np.sign(yy[m])))
        log.append(dict(anchor=anchor, train_rows=len(train_idx), pred_rows=len(pred_idx), spearman_ic=round(ic, 4), sign_hit=round(hit, 4), seeds=info, sec=round(time.time() - t0)))
        print(log[-1], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    np.save(OUT / f"pred_h{H}.npy", pred)
    (OUT / f"log_h{H}.json").write_text(json.dumps(dict(features=list(x.columns), horizon=H, window=WIN, anchors=log), indent=1))


if __name__ == "__main__":
    main()
