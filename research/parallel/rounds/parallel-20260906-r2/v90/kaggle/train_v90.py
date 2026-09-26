"""v90 pooled-majors sequence model — STANDALONE Kaggle training script.

Runs on private Kaggle (GPU T4) with ONLY:
    majors_4h_bundle.npz  (built locally by ../build_bundle.py)
    data_manifest.json    (SHA-256 of the bundle)
plus this file. No project source is imported; only torch / numpy / pandas /
pyarrow from the Kaggle image are used. No credentials, no network, no upload.

Model: TCN (causal dilated conv) + Transformer-encoder hybrid, ~2.9M params
(inside the assigned 2-10M band; exact count is printed and asserted).

Input : 180 x 4h bars x 5 assets x 8 causal features = 40 channels/window,
  plus 1 availability channel per asset (1 = all 8 features finite at that
  row, else 0) -> 45 channels. Missing feature values are zero-filled AFTER
  train-only normalisation. A window is valid when BTC is feature-complete
  for all 180 rows (other assets may be masked via their availability
  channel).
  Per asset, value at row t uses only information available at/before the
  4h bar close_time[t]:
    lr1   = ln(close[t]/close[t-1])
    lr6   = ln(close[t]/close[t-6])
    lr42  = ln(close[t]/close[t-42])          (42 x 4h = 7d)
    range = (high[t]-low[t])/close[t]
    volz  = z-score of ln(volume[t]) vs trailing 42 bars ending at t
    fund7 = mean of last 21 funding payments with fundingTime <= close[t]
    dSMA50 / dSMA200 = (close[t]-SMA)/SMA of daily closes with
            daily close_time <= close[t]  ("daily ribbon as of last closed
            daily bar")
Output: per asset, 7-day vol-normalized forward return (Huber, main) and
  1-day vol-normalized forward return (Huber, aux x0.3), computed from OPENS
  (execution fills at the next open):
    y7 = log(open[t+43]/open[t+1]) / vol42_t
    y1 = log(open[t+7]/open[t+1]) / vol42_t
  vol scale = trailing-42-bar std of 1-bar log returns ending at t
  (causal; labels therefore need no future information beyond the close
  series itself, plus future opens for the forward move).

Protocol (fixed before any run; see package_manifest.json):
  5 expanding anchors 2021-09-24 .. 2025-09-24 (yearly).
  Per anchor: train on samples whose 7d label is REALIZED before
  anchor-17d (17d embargo past realization ~= 24d past feature time,
  label END = open[t+43] bar close grid[t+43]);
  early-stop on the last 15% of training time, purged by 7d from the fit
  set; 3 seeds (0,1,2); predict every BTC-complete bar in the next
  year. Normalization (mean/std, nan-aware) is fit on the fit-train portion
  ONLY, per anchor; missing features are then zero-filled and availability
  channels appended. A training row needs a finite BTC y7 (other assets may
  be NaN and are masked in the Huber loss). Deterministic seeds; cudnn
  deterministic.

Hidden-year guard (structural): labels are NEVER formed when the 7d label
window touches >= 2025-09-24 (HIDDEN_CUTOFF, on the label END time
grid[t+43]). The 2025-09-24 anchor therefore
exports predictions for 2025-09-24..2026-09-23 with NaN labels; the worker
never computes or inspects forward returns for dates >= 2025-09-24.

Smoke: `python train_v90.py --bundle ... --manifest ... --out ... --smoke`
  runs anchor[0] x seed 0 x 1 epoch on a strided subset on CPU.
"""
import torch  # noqa: F401  (must precede pandas on some Windows hosts)

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- constants
ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
N_FEAT = 8
N_AVAIL = 5
N_CHAN = N_FEAT * len(ASSETS) + N_AVAIL  # 45
WIN = 180            # 180 x 4h bars = 30d lookback
H7 = 42              # 7d horizon in 4h bars (label uses opens t+1 -> t+43)
H1 = 6               # 1d aux horizon in 4h bars (label uses opens t+1 -> t+7)
EMBARGO_D = 17       # label realized before anchor - 17d
VAL_FRac = 0.15      # last 15% of training time is validation
PURGE_D = 7          # purge gap between fit-train and validation
SEEDS = (0, 1, 2)
ANCHORS = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
HIDDEN_CUTOFF = "2025-09-24"   # never form labels touching this date or later
D_MODEL = 192
N_TCN_BLOCKS = 5
N_TRANS_LAYERS = 4
N_HEADS = 6
LR = 3e-4
WD = 1e-2
BATCH = 256
MAX_EPOCHS = 50
PATIENCE = 8
AUX_W = 0.3
NS_PER_DAY = 86_400_000_000_000


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- features
def build_features(bundle: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Return (X [T, 40] float32 raw with NaN for unavailable,
    avail [T, 5] float32 0/1, btc_ok [T] bool, info). Causal by construction.

    avail[t, m] = 1 iff all 8 features of asset m are finite at row t.
    btc_ok = avail[:, 0] == 1. feat_ok_all (all assets complete) is in info
    for diagnostics only; windows are validated on BTC only (see
    anchor_split / v90 revision 2026-09-25).
    """
    grid = bundle["close_time_4h_ns"].astype("int64")
    T = len(grid)
    per_asset = []
    avail = np.zeros((T, len(ASSETS)), dtype=np.float32)
    for mi, a in enumerate(ASSETS):
        o = bundle[f"{a}.open"].astype("float64")
        hi = bundle[f"{a}.high"].astype("float64")
        lo = bundle[f"{a}.low"].astype("float64")
        c = bundle[f"{a}.close"].astype("float64")
        v = bundle[f"{a}.volume"].astype("float64")
        F = np.full((T, N_FEAT), np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            F[1:, 0] = np.log(c[1:] / c[:-1])
            F[6:, 1] = np.log(c[6:] / c[:-6])
            F[42:, 2] = np.log(c[42:] / c[:-42])
            F[:, 3] = (hi - lo) / c
            lv = np.where(v > 0, np.log(v), np.nan)
            mu = pd.Series(lv).rolling(42, min_periods=42).mean().to_numpy()
            sd = pd.Series(lv).rolling(42, min_periods=42).std(ddof=0).to_numpy()
            F[:, 4] = (lv - mu) / sd
            # funding 7d mean as-of bar close (backward availability)
            ft = bundle[f"{a}.funding_time_ns"].astype("int64")
            fr = bundle[f"{a}.funding_rate"].astype("float64")
            cs = np.cumsum(fr)
            j = np.searchsorted(ft, grid, side="right") - 1
            ok_f = j >= 21
            jj = np.clip(j, 21, len(fr) - 1)
            F[ok_f, 5] = (cs[jj[ok_f]] - cs[jj[ok_f] - 21]) / 21.0
            # distance to daily SMA50 / SMA200 as of last closed daily bar
            dct = bundle[f"{a}.daily_close_time_ns"].astype("int64")
            dc = bundle[f"{a}.daily_close"].astype("float64")
            dcs = np.cumsum(dc)
            k = np.searchsorted(dct, grid, side="right") - 1
            for n, col in ((50, 6), (200, 7)):
                valid = k >= n
                if valid.any():
                    kv = k[valid]
                    sma = (dcs[kv] - dcs[kv - n]) / n
                    with np.errstate(divide="ignore", invalid="ignore"):
                        F[valid, col] = (c[valid] - sma) / sma
        per_asset.append(F)
        avail[:, mi] = np.isfinite(F).all(axis=1).astype(np.float32)
    X = np.concatenate(per_asset, axis=1).astype(np.float32)
    btc_ok = avail[:, 0] == 1.0
    feat_ok_all = avail.all(axis=1) == 1.0
    return X, avail, btc_ok, {"rows": T, "feat_ok_all": feat_ok_all}


def build_labels(bundle: dict, cutoff_ns: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Open-based vol-normalized forward log-returns (execution fills at the
    next open): y7 = log(open[t+43]/open[t+1]) / vol42_t,
    y1 = log(open[t+7]/open[t+1]) / vol42_t, where vol42_t is the
    trailing-42-bar std of 1-bar close log-returns ending at t (causal).
    Labels whose 7d END (grid[t+43]) touches >= cutoff are left NaN and
    never formed (hidden-year guard on the label END time). Other assets
    may stay NaN (masked in the loss); a training row needs finite BTC y7.
    """
    grid = bundle["close_time_4h_ns"].astype("int64")
    T = len(grid)
    Y7 = np.full((T, len(ASSETS)), np.nan, dtype=np.float64)
    Y1 = np.full((T, len(ASSETS)), np.nan, dtype=np.float64)
    end_ns = np.full(T, np.iinfo(np.int64).max)
    for m, a in enumerate(ASSETS):
        c = bundle[f"{a}.close"].astype("float64")
        o = bundle[f"{a}.open"].astype("float64")
        with np.errstate(divide="ignore", invalid="ignore"):
            lr1 = np.log(c[1:] / c[:-1])
        lr1 = np.concatenate([[np.nan], lr1])
        vol = pd.Series(lr1).rolling(42, min_periods=42).std(ddof=0).to_numpy()
        vol = np.where(vol > 1e-12, vol, np.nan)
        last = T - (H7 + 1)  # need o[t+43]; H7=42
        ts = np.arange(0, last)
        allowed = grid[ts + H7 + 1] < cutoff_ns
        ts = ts[allowed]
        with np.errstate(divide="ignore", invalid="ignore"):
            r7 = np.log(o[ts + H7 + 1] / o[ts + 1]) / vol[ts]
            r1 = np.log(o[ts + H1 + 1] / o[ts + 1]) / vol[ts]
        Y7[ts, m] = r7
        Y1[ts, m] = r1
        end_ns[ts] = grid[ts + H7 + 1]
    return Y7.astype(np.float32), Y1.astype(np.float32), end_ns


# ---------------------------------------------------------------- model
class CausalConv(torch.nn.Module):
    def __init__(self, d: int, k: int, dilation: int):
        super().__init__()
        self.pad = (k - 1) * dilation
        self.conv = torch.nn.Conv1d(d, d, k, dilation=dilation)
        self.dilation = dilation

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # [B, D, L]
        return self.conv(torch.nn.functional.pad(x, (self.pad, 0)))[:, :, : x.shape[2]]


class TCNBlock(torch.nn.Module):
    def __init__(self, d: int, dilation: int):
        super().__init__()
        self.ln1 = torch.nn.LayerNorm(d)
        self.c1 = CausalConv(d, 3, dilation)
        self.ln2 = torch.nn.LayerNorm(d)
        self.c2 = CausalConv(d, 3, dilation)

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # [B, L, D]
        h = self.ln1(x).transpose(1, 2)
        h = torch.relu(self.c1(h)).transpose(1, 2)
        h = self.ln2(h).transpose(1, 2)
        h = self.c2(h).transpose(1, 2)
        return torch.relu(x + h)


class PooledSequenceModel(torch.nn.Module):
    """TCN (local causal structure) + Transformer encoder (cross-time and
    cross-asset mixing inside the all-past window) -> per-asset heads."""

    def __init__(self, n_chan: int = N_CHAN, n_assets: int = 5, d: int = D_MODEL):
        super().__init__()
        self.in_proj = torch.nn.Linear(n_chan, d)
        self.tcn = torch.nn.Sequential(*[TCNBlock(d, 2**i) for i in range(N_TCN_BLOCKS)])
        layer = torch.nn.TransformerEncoderLayer(
            d_model=d, nhead=N_HEADS, dim_feedforward=4 * d,
            batch_first=True, dropout=0.0,
        )
        self.tr = torch.nn.TransformerEncoder(layer, num_layers=N_TRANS_LAYERS)
        self.head = torch.nn.Sequential(
            torch.nn.LayerNorm(d), torch.nn.Linear(d, d // 2),
            torch.nn.ReLU(), torch.nn.Linear(d // 2, n_assets * 2),
        )
        self.n_assets = n_assets

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.in_proj(x)
        h = self.tcn(h)
        h = self.tr(h)
        last = h[:, -1, :]
        out = self.head(last).view(x.shape[0], self.n_assets, 2)
        return out[:, :, 0], out[:, :, 1]  # y7, y1


def count_params(model: torch.nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


# ---------------------------------------------------------------- data
class IdxDataset(torch.utils.data.Dataset):
    def __init__(self, X: np.ndarray, Y7: np.ndarray, Y1: np.ndarray, idx: np.ndarray):
        self.X, self.Y7, self.Y1, self.idx = X, Y7, Y1, idx

    def __len__(self) -> int:
        return len(self.idx)

    def __getitem__(self, i: int):
        t = int(self.idx[i])
        return (
            torch.from_numpy(self.X[t - WIN + 1: t + 1]),
            torch.from_numpy(self.Y7[t]),
            torch.from_numpy(self.Y1[t]),
        )


def anchor_split(grid: np.ndarray, btc_ok: np.ndarray, end_ns: np.ndarray,
                 label_ok_btc: np.ndarray, anchor: str) -> dict:
    a_ns = pd.Timestamp(anchor, tz="UTC").value
    # A sample at t consumes the window [t-WIN+1, t]: every row must be
    # BTC feature-complete. Other assets may be masked (their missing
    # features are zero-filled post-normalisation + availability channel).
    # v90 revision 2026-09-25: BTC-only gating (was: all 5 assets complete).
    win_ok = pd.Series(btc_ok.astype(np.float32)).rolling(WIN, min_periods=WIN).min().to_numpy() == 1.0
    train = win_ok & label_ok_btc & (end_ns < a_ns - EMBARGO_D * NS_PER_DAY)
    t_idx = np.flatnonzero(train)
    if len(t_idx) < 500:
        raise ValueError(f"anchor {anchor}: only {len(t_idx)} train rows")
    t0, t1 = grid[t_idx[0]], grid[t_idx[-1]]
    cut = t1 - int(VAL_FRac * (t1 - t0))
    val = train & (grid >= cut)
    fit = train & (grid < cut - PURGE_D * NS_PER_DAY)
    if fit.sum() < 300 or val.sum() < 50:
        raise ValueError(f"anchor {anchor}: fit={fit.sum()} val={val.sum()}")
    nxt = pd.Timestamp(anchor, tz="UTC") + pd.DateOffset(years=1)
    pred = win_ok & (grid >= a_ns) & (grid < nxt.value)
    return {"fit": np.flatnonzero(fit), "val": np.flatnonzero(val), "pred": np.flatnonzero(pred)}


def huber(p: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    m = torch.isfinite(y)
    if not m.any():
        return torch.zeros((), device=p.device)
    return torch.nn.functional.huber_loss(p[m], y[m], delta=1.0)


# ---------------------------------------------------------------- run
def run_anchor(Xn: np.ndarray, Y7: np.ndarray, Y1: np.ndarray, split: dict,
               device: str, out_dir: Path, anchor: str, seed: int,
               epochs: int, stride: int = 1, batch: int = BATCH) -> dict:
    g = torch.Generator().manual_seed(seed)
    torch.manual_seed(seed)
    np.random.seed(seed)
    fit_idx = split["fit"][::stride]
    val_idx = split["val"][::stride]
    dl_fit = torch.utils.data.DataLoader(
        IdxDataset(Xn, Y7, Y1, fit_idx), batch_size=batch, shuffle=True,
        generator=g, num_workers=0, drop_last=True)
    dl_val = torch.utils.data.DataLoader(
        IdxDataset(Xn, Y7, Y1, val_idx), batch_size=1024,
        shuffle=False, num_workers=0)
    model = PooledSequenceModel().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WD)
    use_amp = str(device).startswith("cuda")
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    best, bad, best_state, hist = float("inf"), 0, None, []
    t_start = time.monotonic()
    n_win = 0
    for ep in range(epochs):
        model.train()
        for xb, y7, y1 in dl_fit:
            xb, y7, y1 = xb.to(device), y7.to(device), y1.to(device)
            opt.zero_grad(set_to_none=True)
            with torch.autocast("cuda", enabled=use_amp):
                p7, p1 = model(xb)
                loss = huber(p7, y7) + AUX_W * huber(p1, y1)
            if not torch.isfinite(loss):
                raise ValueError("nonfinite training loss")
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            n_win += 1
        model.eval()
        with torch.no_grad():
            tot, n = 0.0, 0
            for xb, y7, _ in dl_val:
                xb, y7 = xb.to(device), y7.to(device)
                p7, _ = model(xb.float() if use_amp else xb)
                tot += huber(p7, y7).item() * len(xb)
                n += len(xb)
        v = tot / max(n, 1)
        hist.append(v)
        if v < best - 1e-6:
            best, bad = v, 0
            best_state = {k: v_.detach().cpu().clone() for k, v_ in model.state_dict().items()}
        else:
            bad += 1
            if bad >= PATIENCE:
                break
    speed = n_win / max(time.monotonic() - t_start, 1e-6)
    model.load_state_dict(best_state)
    ck = out_dir / f"ckpt_{anchor}_seed{seed}.pt"
    torch.save({"state_dict": best_state, "anchor": anchor, "seed": seed,
                "val_huber7": best, "history": hist}, ck)
    return {"seed": seed, "val_huber7": best, "epochs_run": len(hist),
            "windows_per_sec": speed, "checkpoint": ck.name}


def predict(Xn: np.ndarray, ckpt: Path, idx: np.ndarray, device: str) -> np.ndarray:
    model = PooledSequenceModel()
    model.load_state_dict(torch.load(ckpt, map_location="cpu")["state_dict"])
    model.to(device).eval()
    outs = []
    with torch.no_grad():
        for s in range(0, len(idx), 1024):
            xb = torch.stack([torch.from_numpy(Xn[t - WIN + 1: t + 1]) for t in idx[s:s + 1024]]).to(device)
            p7, p1 = model(xb.float())
            outs.append(torch.stack([p7, p1], dim=-1).cpu().numpy())
    return np.concatenate(outs, axis=0) if outs else np.zeros((0, len(ASSETS), 2), np.float32)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    man = json.loads(Path(args.manifest).read_text())
    if sha256(Path(args.bundle)) != man["sha256"]:
        raise ValueError("bundle hash mismatch")
    out = Path(args.out)
    (out / "checkpoints").mkdir(parents=True, exist_ok=True)
    (out / "predictions").mkdir(parents=True, exist_ok=True)

    bundle = dict(np.load(args.bundle, allow_pickle=False))
    if list(bundle["assets"].astype(str)) != ASSETS:
        raise ValueError("bundle assets mismatch")
    grid = bundle["close_time_4h_ns"].astype("int64")
    cutoff_ns = pd.Timestamp(HIDDEN_CUTOFF, tz="UTC").value

    X_raw, avail, btc_ok, _ = build_features(bundle)
    Y7, Y1, end_ns = build_labels(bundle, cutoff_ns)
    # v90 revision: a training row needs a finite BTC y7 only; other assets
    # may be NaN and are masked in the Huber loss (huber() is NaN-masked).
    label_ok_btc = np.isfinite(Y7[:, 0])

    model0 = PooledSequenceModel()
    n_params = count_params(model0)
    print(f"params: {n_params}")
    if not 2_000_000 <= n_params <= 10_000_000:
        raise ValueError(f"param count {n_params} outside 2-10M band")
    cap_note = (
        f"{n_params} params (low end of the 2-10M band): TCN captures local "
        "causal structure with ~1.1M params; 4x192-d transformer layers mix "
        "cross-time/cross-asset context with ~1.8M; heads are linear. "
        "Pooling 5 majors gives ~5x weekly-horizon supervision vs BTC-only "
        "(prior BTC-only deep models: IC~0); capacity is capped low with "
        "Huber + aux head + early stopping + weight decay until pooled "
        "evidence justifies more."
    )

    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True, warn_only=True)

    anchors = ANCHORS[:1] if args.smoke else ANCHORS
    seeds = SEEDS[:1] if args.smoke else SEEDS
    epochs = 1 if args.smoke else MAX_EPOCHS
    stride = 20 if args.smoke else 1

    t_all = time.monotonic()
    summary = {"params": n_params, "capacity_note": cap_note, "device": device,
               "anchors": {}, "smoke": args.smoke}
    for anchor in anchors:
        split = anchor_split(grid, btc_ok, end_ns, label_ok_btc, anchor)
        # train-only normalization (fit portion only, NaN-aware): missing
        # features are zero-filled AFTER normalisation; availability
        # channels (0/1) are appended unnormalised -> 45 channels.
        mu = np.nanmean(X_raw[split["fit"]], axis=0).astype(np.float32)
        sd = np.nanstd(X_raw[split["fit"]], axis=0).astype(np.float32)
        mu = np.where(np.isfinite(mu), mu, 0.0).astype(np.float32)
        sd = np.where(np.isfinite(sd) & (sd > 1e-8), sd, 1.0).astype(np.float32)
        with np.errstate(invalid="ignore"):
            Xn_feat = ((X_raw - mu) / sd).astype(np.float32)
        Xn_feat[~np.isfinite(Xn_feat)] = 0.0
        Xn = np.concatenate([Xn_feat, avail.astype(np.float32)], axis=1).astype(np.float32)
        assert Xn.shape[1] == N_CHAN == 45
        win_btc = pd.Series(btc_ok.astype(np.float32)).rolling(WIN, min_periods=WIN).min().to_numpy() == 1.0
        if not np.isfinite(Xn[win_btc]).all():
            raise ValueError(f"anchor {anchor}: nonfinite normalized windows")
        np.savez_compressed(out / "checkpoints" / f"norm_{anchor}.npz",
                            mean=mu.astype(np.float32), scale=sd)
        anchor_rec = {"n_fit": int(split["fit"].size), "n_val": int(split["val"].size),
                      "n_pred": int(split["pred"].size), "seeds": []}
        ckpts = []
        for seed in seeds:
            rec = run_anchor(Xn, Y7, Y1, split, device, out / "checkpoints",
                             anchor, seed, epochs, stride,
                             batch=8 if args.smoke else BATCH)
            anchor_rec["seeds"].append(rec)
            ckpts.append(out / "checkpoints" / rec["checkpoint"])
        # predict every BTC-complete bar in the next year (labels never inspected here)
        if split["pred"].size:
            t_pred = time.monotonic()
            preds = [predict(Xn, c, split["pred"], device) for c in ckpts]
            anchor_rec["pred_windows_per_sec"] = (
                split["pred"].size * len(ckpts) / max(time.monotonic() - t_pred, 1e-6))
            P = np.stack(preds, axis=0)  # [S, N, 5, 2]
            df = pd.DataFrame({"close_time": pd.to_datetime(grid[split["pred"]], utc=True)})
            for m, a in enumerate(ASSETS):
                for s, seed in enumerate(seeds):
                    df[f"{a}_y7_seed{seed}"] = P[s, :, m, 0]
                    df[f"{a}_y1_seed{seed}"] = P[s, :, m, 1]
                df[f"{a}_y7_mean"] = P[:, :, m, 0].mean(axis=0)
                df[f"{a}_y1_mean"] = P[:, :, m, 1].mean(axis=0)
            if not np.isfinite(df.filter(like="_y7_").to_numpy()).all():
                raise ValueError(f"anchor {anchor}: nonfinite predictions")
            df.to_parquet(out / "predictions" / f"pred_{anchor}.parquet", index=False)
            anchor_rec["pred_file"] = f"pred_{anchor}.parquet"
        summary["anchors"][anchor] = anchor_rec

    summary["wall_seconds"] = time.monotonic() - t_all
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2, default=float))
    print(json.dumps({k: (v if k != "anchors" else {a: {kk: vv for kk, vv in r.items() if kk != "seeds"} for a, r in v.items()}) for k, v in summary.items() if k != "capacity_note"}, indent=2, default=float))


if __name__ == "__main__":
    main()
