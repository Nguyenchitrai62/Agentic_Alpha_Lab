"""R76 W1 verification: pytest-collectable tests for the causal adapter.

Lives under scripts/opencode_r76_infer*.py per the W1 write-scope boundary
(tests/ is outside scope, so tests ship here and run via pytest on this file).

Covers: WARMUP-vs-WAIT distinct status, missing-asset fail-closed naming the
file, closed-candle-only proof (HTF last-close <= decision_time; forming bar
rejected), and batch parity vs an independently-driven frozen batch chain
(real checkpoint forward passes, no stored predictions/signals loaded).
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from safetensors.torch import load_file

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from opencode_r76_infer import (  # noqa: E402
    ReadinessError, WARMUP_BARS, infer_decisions, load_prespec)
from agentic_alpha_lab.data.sequence_context import encode_windows  # noqa: E402
from agentic_alpha_lab.data.swing import SwingStore, choose, grid  # noqa: E402
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402
from agentic_alpha_lab.models.residual_temporal_value import (  # noqa: E402
    ResidualTemporalValue, residual_predict)

SPEC = load_prespec()
SEEDS = (1729, 1730, 1731)
MAPS = ("isotonic_2", "isotonic_4", "isotonic_all")


def _research_slice(n_bars: int = 37200) -> pd.DataFrame:
    df = pd.read_parquet(ROOT / "data/processed/swing_regime_research_v4"
                         / "candles.parquet").iloc[:n_bars].reset_index(drop=True)
    return df


def test_warmup_is_not_wait():
    df = _research_slice(37200).iloc[:1000].reset_index(drop=True)
    out = infer_decisions(df, SPEC)
    assert len(out) == 1 and out[0]["status"] == "WARMUP"
    assert out[0].get("action", "WARMUP") != "WAIT"
    assert out[0]["warmup_bars_required"] == WARMUP_BARS


def test_missing_asset_fails_closed_naming_file():
    bad = json.loads(json.dumps(SPEC))
    bad["checkpoints"]["paths"] = list(bad["checkpoints"]["paths"])
    bad["checkpoints"]["paths"][0] = (
        "artifacts/kaggle/v29_download/tcn-training/seed1729/checkpoints/"
        "fold_10/MISSING.safetensors")
    df = _research_slice()
    with pytest.raises(ReadinessError, match="MISSING.safetensors"):
        infer_decisions(df, bad)


def test_missing_calibrator_fails_closed():
    bad = json.loads(json.dumps(SPEC))
    bad["calibrators"]["maps"]["iso4"]["path"] = (
        "artifacts/research/opencode_v02_reproduce_v30/isotonic_4/NOPE.json")
    with pytest.raises(ReadinessError, match="NOPE.json"):
        infer_decisions(_research_slice(), bad)


def test_forming_bar_rejected():
    df = _research_slice().copy()
    df.loc[df.index[-1], "close_time"] = (
        pd.Timestamp.now(tz="UTC") + pd.Timedelta(minutes=5))
    with pytest.raises(ValueError):
        infer_decisions(df, SPEC)


def test_closed_candle_only_proof():
    out = [r for r in infer_decisions(_research_slice(), SPEC)
           if r["status"] == "READY_DECISION"]
    assert len(out) == 5  # bars 36864..37152 step 72
    for row in out:
        dt = row["decision_time"]
        for tf, last in row["htf_last_close_lte_decision"].items():
            assert pd.Timestamp(last, tz="UTC") <= dt, f"HTF leak {tf}"


def run_batch_parity(n_bars: int = 37200) -> dict:
    """Independently-driven frozen batch chain (real inference) vs adapter."""
    df = _research_slice(n_bars)
    adapter = [r for r in infer_decisions(df, SPEC)
               if r["status"] == "READY_DECISION"]

    cfg = json.loads((ROOT / SPEC["research_config"]["path"]).read_text(
        encoding="utf-8"))
    from agentic_alpha_lab.data.training import validate_source
    candles = validate_source(df)
    store = SwingStore(candles, cfg)
    closes = pd.DatetimeIndex(pd.to_datetime(candles["close_time"], utc=True))
    opens = pd.DatetimeIndex(pd.to_datetime(candles["open_time"], utc=True))
    grid_ok = ((opens - pd.Timestamp("1970-01-01", tz="UTC")).asi8
               % pd.Timedelta(hours=6).value) == 0
    bars = np.where(grid_ok)[0]
    bars = bars[bars >= WARMUP_BARS].astype(np.int64)
    assert [int(b) for b in bars] == [r["bar_index"] for r in adapter]

    candidates = np.asarray(grid(cfg), dtype=np.float32)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    seqs, feats, meta = [], [], []
    for bar in bars:
        dt = closes[int(bar)]
        w, _, _, feat40, atr5, atr4 = store.sample(dt)
        seqs.append(encode_windows(w))
        feats.append(np.asarray(feat40, dtype=np.float32))
        meta.append((dt, float(candles["close"].iloc[int(bar)]),
                     float(atr5), float(atr4)))
    seqs = np.stack(seqs).astype(np.float32)
    feats = np.stack(feats).astype(np.float32)

    outs = []
    for seed in SEEDS:
        model = ResidualTemporalValue(candidates, width=48, dropout=0.15)
        ckpt = ROOT / SPEC["checkpoints"]["paths"][SEEDS.index(seed)]
        model.load_state_dict(load_file(str(ckpt)))
        model.eval().to(device)
        outs.append(residual_predict(model, seqs, feats, batch_size=32))
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    base, details = combine(np.stack(outs).astype(np.float64), 0.0)
    score = np.asarray(details["selection_score_percent"], float)
    fill = np.asarray(details["mean_fill_score"], float)
    cal = {}
    for m, short in (("isotonic_2", "iso2"), ("isotonic_4", "iso4"),
                     ("isotonic_all", "isoall")):
        doc = json.loads((ROOT / SPEC["calibrators"]["maps"][short]["path"])
                         .read_text(encoding="utf-8"))
        rec = [r for r in doc if r["fold"] == 10][0]
        mapped = np.interp(score.ravel(), np.asarray(rec["x"], float),
                           np.asarray(rec["y"], float)).reshape(score.shape)
        arr = np.asarray(base, float).copy()
        arr[..., 0] = mapped / np.clip(fill, 1e-6, 1 - 1e-6)
        cal[m] = arr
    per_map, dirs = {}, {}
    for m in MAPS:
        ol, dl = [], []
        for j in range(cal[m].shape[0]):
            o = choose(cal[m][j], meta[j][1], meta[j][2], meta[j][3], cfg)
            ol.append(o)
            dl.append(1 if o.get("action") == "LONG"
                      else (-1 if o.get("action") == "SHORT" else 0))
        per_map[m], dirs[m] = ol, np.asarray(dl, int)
    d2, d4, dall = dirs["isotonic_2"], dirs["isotonic_4"], dirs["isotonic_all"]
    confirmed = (d4 != 0) & (dall == d4)
    policy = cfg["policy"]
    order = np.argsort([m[0].value for m in meta], kind="stable")
    nxt = pd.Timestamp.min.tz_localize("UTC")
    monthly: dict[str, int] = {}
    gated = np.zeros(len(bars), dtype=bool)
    for pos in order:
        j = int(pos)
        if not bool(confirmed[j]) or per_map["isotonic_4"][j].get(
                "action") == "WAIT":
            continue
        ts = meta[j][0]
        month = ts.strftime("%Y-%m")
        if ts < nxt or monthly.get(month, 0) >= policy[
                "maximum_signals_per_month"]:
            continue
        gated[j] = True
        monthly[month] = monthly.get(month, 0) + 1
        nxt = ts + pd.Timedelta(days=policy["cooldown_days"])

    compared, matched, mismatches = 0, 0, []
    for j in range(len(bars)):
        want = per_map["isotonic_4"][j].get("action") if gated[j] else "WAIT"
        got = adapter[j]["action"]
        compared += 1
        keys = ("entry_limit", "stop_loss", "take_profit_1", "take_profit_2",
                "direction")
        numbers_ok = True
        if want != "WAIT":
            for k in keys:
                a, b = float(adapter[j][k]), float(
                    {**per_map["isotonic_4"][j], "direction": int(
                        1 if per_map["isotonic_4"][j].get("action") == "LONG"
                        else -1)}[k])
                if not np.isclose(a, b, rtol=1e-9, atol=1e-9):
                    numbers_ok = False
        if want == got and numbers_ok:
            matched += 1
        else:
            mismatches.append({"bar_index": int(bars[j]), "want": want,
                               "got": got, "numbers_ok": numbers_ok})
    return {"n_decisions": compared, "matched": matched,
            "match_rate": matched / compared if compared else 0.0,
            "mismatches": mismatches,
            "adapter_actions": [r["action"] for r in adapter]}


def test_batch_parity():
    res = run_batch_parity()
    assert res["mismatches"] == [], f"mismatches: {res['mismatches']}"
    assert res["match_rate"] == 1.0
