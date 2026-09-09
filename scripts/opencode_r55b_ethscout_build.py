"""R55b ETH scout (2/3): minimal ETH decision clock + labels MIRRORING BTC v4.

- Doc data/processed/swing_regime_research_v4 pattern (6h grid, horizons 3d/7d,
  embargo 8d) nhung o quy mo NHO, chi tu ETH 6h closes + funding ETH local.
- KHONG innovate labels: fwd log-return 3d/7d + 3-class co dinh +/-2%
  (pre-spec trong configs/opencode_v142_ethscout.json).
- Causal past-only: features chi dung bars <= t; labels chi dung bars > t.
  signal_time = close_time bar t; label_end = close_time bar t+28 < cutoff.
- Ghi thu muc MOI data/processed/opencode_eth_scout_*/ (khong ghi de):
  decisions.parquet + features.npz + manifest.json.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import torch  # noqa: F401 - torch truoc pandas (DLL load-order Windows host)
import numpy as np
import pandas as pd

CFG_PATH = "configs/opencode_v142_ethscout.json"
WARMUP = 120
H3, H7 = 12, 28  # 3d / 7d tren luoi 6h
THR = 0.02
CUTOFF = pd.Timestamp("2026-03-23T00:00:00Z", tz="UTC")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def rsi_wilder(close: np.ndarray, period: int = 14) -> np.ndarray:
    out = np.full(len(close), np.nan)
    if len(close) <= period:
        return out
    d = np.diff(close)
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    ag = gain[:period].mean()
    al = loss[:period].mean()
    out[period] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    for i in range(period + 1, len(close)):
        ag = (ag * (period - 1) + gain[i - 1]) / period
        al = (al * (period - 1) + loss[i - 1]) / period
        out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    return out


def build(root: Path, outdir: Path):
    cfg = json.loads((root / CFG_PATH).read_text())
    eth = pd.read_parquet(root / "data/raw/opencode_eth_6h_20260907/eth_ETHUSDT_6h.parquet")
    eth = eth.sort_values("open_time").reset_index(drop=True)
    # Verify clock 6h 00/06/12/18 UTC (mirror crawl asserts).
    assert bool(eth["open_time"].dt.hour.isin([0, 6, 12, 18]).all())
    fund = pd.read_parquet(root / "data/raw/opencode_funding_20260907/funding_ETHUSDT.parquet")
    fund = fund.sort_values("funding_time").reset_index(drop=True)
    frate = fund["fundingRate"].astype(float).to_numpy()
    ftime = pd.to_datetime(fund["funding_time"], utc=True).to_numpy()

    close = eth["close"].to_numpy(float)
    high = eth["high"].to_numpy(float)
    low = eth["low"].to_numpy(float)
    vol = eth["volume"].to_numpy(float)
    n = len(eth)
    logc = np.log(close)
    ret1 = np.diff(logc, prepend=np.nan)
    rsi = rsi_wilder(close, 14)

    # Causal funding join: last funding_time <= signal_time (close_time bar t).
    sig_times = eth["close_time"]
    fidx = np.searchsorted(ftime, sig_times.to_numpy(), side="right") - 1
    fund_last = np.where(fidx >= 0, frate[np.clip(fidx, 0, len(frate) - 1)], 0.0)
    fund_prev = np.where(fidx >= 1, frate[np.clip(fidx - 1, 0, len(frate) - 1)], 0.0)
    fund_mask = (fidx >= 0).astype(float)

    names = ["lr1", "lr2", "lr4", "lr8", "lr16", "lr28",
             "hl1", "hl_mean4", "vol1", "vol_ratio4", "vol_ratio28", "volz28",
             "rsi14", "dist_sma28", "rv12", "rv28", "range28",
             "funding_last", "funding_chg8h", "funding_mask", "hour"]
    feats, recs = [], []
    for t in range(WARMUP, n - H7):
        label_end = eth["close_time"].iloc[t + H7]
        if not (label_end < CUTOFF):
            continue
        c = close[t]
        lr = lambda k: logc[t] - logc[t - k]
        hls = np.log(high[t - 3:t + 1] / low[t - 3:t + 1])
        vwin28 = vol[t - 27:t + 1]
        sma28 = close[t - 27:t + 1].mean()
        r12 = ret1[t - 11:t + 1]
        r28 = ret1[t - 27:t + 1]
        fwd3 = logc[t + H3] - logc[t]
        fwd7 = logc[t + H7] - logc[t]
        row = [
            lr(1), lr(2), lr(4), lr(8), lr(16), lr(28),
            float(np.log(high[t] / low[t])), float(hls.mean()),
            float(np.log(vol[t] + 1.0)),
            float(vol[t] / (vol[t - 3:t + 1].mean() + 1e-12)),
            float(vol[t] / (vwin28.mean() + 1e-12)),
            float((vol[t] - vwin28.mean()) / (vwin28.std() + 1e-12)),
            float(rsi[t]), float(c / sma28 - 1.0),
            float(np.nanstd(r12)), float(np.nanstd(r28)),
            float((high[t - 27:t + 1].max() - low[t - 27:t + 1].min()) / c),
            float(fund_last[t]), float(fund_last[t] - fund_prev[t]), float(fund_mask[t]),
            int(eth["open_time"].iloc[t].hour),
        ]
        feats.append(row)
        cls = lambda f: 2 if f > THR else (0 if f < -THR else 1)
        recs.append({"bar_index": int(t),
                     "signal_time": eth["close_time"].iloc[t],
                     "label_end": label_end,
                     "close": float(c),
                     "fwd3": float(fwd3), "fwd7": float(fwd7),
                     "class3": cls(fwd3), "class7": cls(fwd7)})
    X = np.asarray(feats, dtype=np.float64)
    dec = pd.DataFrame(recs)
    assert np.isfinite(X).all(), "features phai finite (warmup 120 bars)"
    assert dec["signal_time"].is_monotonic_increasing and not dec["signal_time"].duplicated().any()
    assert bool((dec["label_end"] < CUTOFF).all())

    if outdir.exists():
        raise FileExistsError(f"{outdir} da ton tai: chon thu muc moi, khong ghi de.")
    outdir.mkdir(parents=True)
    dec.to_parquet(outdir / "decisions.parquet", index=False)
    np.savez_compressed(outdir / "features.npz", features=X, feature_names=np.array(names))
    (outdir / "config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    bal7 = dec["class7"].value_counts(normalize=True).to_dict()
    bal3 = dec["class3"].value_counts(normalize=True).to_dict()
    manifest = {
        "source_6h": "data/raw/opencode_eth_6h_20260907/eth_ETHUSDT_6h.parquet",
        "source_funding": "data/raw/opencode_funding_20260907/funding_ETHUSDT.parquet",
        "grid": "6h 00/06/12/18 UTC (mirror BTC v4 stride-72)",
        "warmup_bars": WARMUP, "horizons": {"h3d_bars": H3, "h7d_bars": H7},
        "threshold": THR, "cutoff": str(CUTOFF), "embargo_days": 8,
        "rows": int(len(dec)),
        "first": str(dec["signal_time"].iloc[0]), "last": str(dec["signal_time"].iloc[-1]),
        "class7_balance": {str(k): round(float(v), 4) for k, v in bal7.items()},
        "class3_balance": {str(k): round(float(v), 4) for k, v in bal3.items()},
        "feature_names": names,
        "files": {p.name: sha256_file(p) for p in sorted(outdir.iterdir())},
        "note": "Mirror-only labels (fwd log-return + fixed +/-2%), exploratory, causal past-only.",
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps({k: manifest[k] for k in ("rows", "first", "last", "class7_balance", "class3_balance")},
                     indent=2, ensure_ascii=False), flush=True)
    print(f"DA GHI {outdir}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", type=str, default=None)
    ab = ap.parse_args()
    rt = Path(__file__).resolve().parents[1]
    if ab.outdir is None:
        hom_nay = datetime.now(timezone.utc).strftime("%Y%m%d")
        od = rt / "data" / "processed" / f"opencode_eth_scout_{hom_nay}"
    else:
        od = Path(ab.outdir)
        od = od if od.is_absolute() else rt / od
    build(rt, od)
