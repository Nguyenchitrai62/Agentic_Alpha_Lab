"""R78 W2 diagnosis: FIRST numerical divergence at published anchor bars.

READ-ONLY diagnosis. No training/fitting/tuning, no orders, no cloud.
Pre-spec: configs/opencode_r78_nonwait.json (interval + frozen SHAs).

Method (harness-only; the tested raw path already ran):
  v30 stored iso4 vector (predictions.npz, walk-forward per-fold) vs the
  r76-traced chain vector (fold-10 checkpoints for every decision) at the
  same published anchor decision rows. Features/clock already proven
  bit-identical (close/atr5/atr4 match decisions.parquet); checkpoints,
  calibrators and research config SHA-verified identical. Any remaining
  vector difference isolates the model-forward stage (fold-specific
  walk-forward weights vs single fold-10 weights).

torch is imported before pandas (Windows DLL load-order rule).
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import opencode_r76_infer as r76  # noqa: E402
from agentic_alpha_lab.data.sequence_context import encode_windows  # noqa: E402
from agentic_alpha_lab.data.swing import choose  # noqa: E402
from agentic_alpha_lab.data.training import validate_source  # noqa: E402
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402
from agentic_alpha_lab.models.residual_temporal_value import (  # noqa: E402
    residual_predict)

OUT_DIR = ROOT / "artifacts" / "research" / "opencode_r78_rolling" / "w2"
ANCHORS = [177696, 190368, 199296, 201600, 207360, 211680, 213768, 215208]


def our_iso4_vector(df: pd.DataFrame, rspec: dict, bar: int) -> dict:
    cfg, calibs = r76.load_frozen_assets(rspec)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    from agentic_alpha_lab.data.swing import SwingStore, grid
    candles = validate_source(df)
    store = SwingStore(candles, cfg)
    closes = pd.DatetimeIndex(pd.to_datetime(candles["close_time"], utc=True))
    pos = int(np.searchsorted(closes.asi8, closes[bar].value, side="left"))
    dt = closes[pos]
    windows, _, _ = store.at(dt)
    seq = encode_windows(windows).astype(np.float32)[None]
    _, _, _, feat40, atr5, atr4 = store.sample(dt)
    feat = np.asarray(feat40, dtype=np.float32)[None]
    candidates = np.asarray(grid(cfg), dtype=np.float32)
    outs = []
    for seed in r76.SEEDS:
        model = r76._load_model(seed, candidates, rspec, device)
        outs.append(residual_predict(model, seq, feat,
                                     batch_size=r76.BATCH))
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    stacked = np.stack(outs).astype(np.float64)  # (3,1,16,6)
    base, details = combine(stacked, 0.0)
    score = np.asarray(details["selection_score_percent"],
                       dtype=np.float64).ravel()
    fill = np.asarray(details["mean_fill_score"], dtype=np.float64).ravel()
    mapped = np.interp(score, calibs["isotonic_4"]["x"],
                       calibs["isotonic_4"]["y"])
    arr = np.asarray(base, dtype=np.float64).copy()
    arr[..., 0] = mapped / np.clip(fill, 1e-6, 1 - 1e-6)
    vec = np.asarray(arr).reshape(16, 6)
    out = choose(vec, float(candles["close"].iloc[pos]), float(atr5),
                 float(atr4), cfg)
    return {"bar": bar, "score_raw": [float(s) for s in score],
            "fill_raw": [float(f) for f in fill],
            "vec": vec, "choose_action": out.get("action"),
            "close": float(candles["close"].iloc[pos])}


def main() -> None:
    t0 = time.time()
    rspec = r76.load_prespec()
    df = pd.read_parquet(
        ROOT / "data/processed/swing_regime_research_v4/candles.parquet")
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    z = np.load(ROOT / "artifacts/research/opencode_v02_reproduce_v30/"
                "isotonic_4/predictions.npz")
    v30_pred, v30_idx = z["prediction"], z["decision_indices"]
    dec = pd.read_parquet(
        ROOT / "data/processed/swing_regime_research_v4/decisions.parquet")
    row_of_bar = {int(b): i for i, b in enumerate(dec["bar_index"].to_numpy())}
    parent = json.loads(
        (ROOT / "configs/swing_v15_continuous_folds.json").read_text())
    rows = []
    for bar in ANCHORS:
        drow = row_of_bar[bar]
        hits = np.where(v30_idx == drow)[0]
        v30_vec = v30_pred[int(hits[0])] if len(hits) else None
        ours = our_iso4_vector(df, rspec, bar)
        if v30_vec is not None:
            dmax = float(np.max(np.abs(v30_vec - ours["vec"])))
        else:
            dmax = None
        v30_act = choose(v30_vec, ours["close"],
                         float(dec["atr5"].iloc[drow]),
                         float(dec["atr4"].iloc[drow]),
                         json.loads((ROOT / "data/processed/"
                                     "swing_regime_research_v4/config.json"
                                     ).read_text())).get("action") \
            if v30_vec is not None else None
        rows.append({
            "bar_index": bar, "decision_row": drow,
            "v30_in_universe": bool(len(hits)),
            "v30_choose_action": v30_act,
            "ours_choose_action": ours["choose_action"],
            "max_abs_diff_vec16x6": dmax,
            "ours_score_first4": ours["score_raw"][:4],
            "ours_fill_first4": ours["fill_raw"][:4],
            "v30_vec_row0": [float(x) for x in v30_vec[0, :6]]
            if v30_vec is not None else None,
            "ours_vec_row0": [float(x) for x in ours["vec"][0, :6]],
            "close": ours["close"],
        })
        print(f"[diag] bar={bar} row={drow} v30={v30_act} "
              f"ours={ours['choose_action']} dmax={dmax}", flush=True)
    (OUT_DIR / "divergence_diag.json").write_text(json.dumps({
        "anchors": rows,
        "fold_windows": parent.get("folds"),
        "v30_pred_shape": list(v30_pred.shape),
        "note": "v30 vectors are walk-forward per-fold predictions.npy; "
                "ours are fold-10 checkpoints applied at every decision",
        "elapsed_s": round(time.time() - t0, 1)}, indent=1, default=str))
    print(f"[diag] -> {OUT_DIR / 'divergence_diag.json'}", flush=True)


if __name__ == "__main__":
    main()
