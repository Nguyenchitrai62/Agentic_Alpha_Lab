"""Opencode R76 W1: causal real-inference adapter (v29 chain, NO replayed signals).

Pre-spec: configs/opencode_r76_infer.json (written BEFORE this script ran).

Chain (traced from scripts/opencode_r66L_fwdmaj.py + configs/opencode_v154_fwdmaj.json):
  closed 5m candles -> SwingStore.sample (5 TF x 128 closed bars, forming bucket
  discarded) -> encode_windows + feat40/ATR -> ResidualTemporalValue fold-10
  checkpoints (seeds 1729/1730/1731, width=48, dropout=0.15) -> combine penalty
  0.0 -> frozen iso2/iso4/isoall maps (fold 10, asof 2025-12-01) -> choose() per
  map -> majority/confirmed vote -> frequency cap 4/month + cooldown 5d.

Public API: infer_decisions(closed_candles_df, ...) -> list of decision dicts.
  Status is WARMUP when history < 36864 closed bars (distinct from WAIT).
  Missing checkpoint/calibrator/config asset -> ReadinessError naming the file
  (fail CLOSED; never replay/fallback).

torch is imported before pandas (Windows DLL load-order rule).
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentic_alpha_lab.data.sequence_context import encode_windows  # noqa: E402
from agentic_alpha_lab.data.swing import SwingStore, choose, grid  # noqa: E402
from agentic_alpha_lab.data.training import validate_source  # noqa: E402
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402
from agentic_alpha_lab.models.residual_temporal_value import (  # noqa: E402
    ResidualTemporalValue, residual_predict)
from safetensors.torch import load_file  # noqa: E402

SPEC_PATH = ROOT / "configs/opencode_r76_infer.json"

WARMUP_BARS = 36864
STRIDE = 72
SEEDS = (1729, 1730, 1731)
FOLD_USED = 10
BATCH = 32
MAPS = ("isotonic_2", "isotonic_4", "isotonic_all")


class ReadinessError(FileNotFoundError):
    """Fail-closed readiness error: names the exact missing frozen asset."""


def _sha(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_prespec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _require_file(rel: str) -> Path:
    path = ROOT / rel
    if not path.exists():
        raise ReadinessError(
            f"STOP (fail-closed): frozen asset missing: {rel}. "
            "Khong thay the bang replay/toy/alternate policy.")
    return path


def load_frozen_assets(spec: dict):
    """Load + SHA-verify research config, checkpoints, calibrators. No fitting."""
    cfg_path = _require_file(spec["research_config"]["path"])
    if _sha(cfg_path) != spec["research_config"]["sha256"]:
        raise ValueError("Research config SHA drift vs prespec")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    ck_paths, ck_want = spec["checkpoints"]["paths"], spec["checkpoints"]["sha256"]
    for rel, want in zip(ck_paths, ck_want):
        path = _require_file(rel)
        if _sha(path) != want:
            raise ValueError(f"Checkpoint SHA drift vs prespec: {rel}")

    calibs = {}
    for short, rec in (("isotonic_2", "iso2"), ("isotonic_4", "iso4"),
                       ("isotonic_all", "isoall")):
        m = spec["calibrators"]["maps"][rec]
        doc = json.loads(_require_file(m["path"]).read_text(encoding="utf-8"))
        recs = [r for r in doc if r["fold"] == FOLD_USED]
        if len(recs) != 1:
            raise ValueError(f"{short} fold-10 calibrator record missing/ambiguous")
        rec0 = recs[0]
        xv = np.asarray(rec0["x"], dtype=np.float64)
        yv = np.asarray(rec0["y"], dtype=np.float64)
        if not bool(np.all(np.diff(xv) >= 0)):
            raise ValueError(f"{short} iso map not monotone")
        calibs[short] = {"x": xv, "y": yv}
    return cfg, calibs


def frozen_bundle_vintage(spec: dict | None = None) -> dict:
    """Resolve frozen fold-10 bundle availability from pinned provenance.

    Model fit-available = max over the 3 serving seeds of
    (last_training_label_end + embargo_days) from each checkpoint's sibling
    metadata.json. Calibrator asof = the fold-10 record asof (must agree
    across iso2/iso4/isoall). Anything missing/UNKNOWN fails closed downstream.
    No fitting, no inference; reads small pinned JSON artifacts only.
    """
    spec = spec or load_prespec()
    fits, fit_srcs = [], []
    for rel in spec["checkpoints"]["paths"]:
        meta_p = (ROOT / rel).parent / "metadata.json"
        src = str(meta_p.relative_to(ROOT)).replace("\\", "/")
        if not meta_p.exists():
            return {"model_fit_available": "UNKNOWN",
                    "calibrator_asof": "UNKNOWN",
                    "sources": {"model_fit_available": fit_srcs,
                                "calibrator_asof": [],
                                "note": f"missing checkpoint metadata: {src}"}}
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        label_end = meta.get("last_training_label_end")
        embargo = (meta.get("training") or {}).get("embargo_days")
        try:
            ts = pd.Timestamp(label_end)
            if pd.isna(ts) or ts.tzinfo is None or embargo is None:
                raise ValueError("unknown/naive label end or missing embargo")
            fits.append(ts + pd.Timedelta(days=int(embargo)))
            fit_srcs.append(f"{src}:last_training_label_end+embargo_days")
        except Exception:
            return {"model_fit_available": "UNKNOWN",
                    "calibrator_asof": "UNKNOWN",
                    "sources": {"model_fit_available": fit_srcs,
                                "calibrator_asof": [],
                                "note": f"unresolvable fit provenance: {src}"}}
    asofs, cal_srcs = [], []
    for short, rec in (("isotonic_2", "iso2"), ("isotonic_4", "iso4"),
                       ("isotonic_all", "isoall")):
        m = spec["calibrators"]["maps"][rec]
        doc = json.loads((ROOT / m["path"]).read_text(encoding="utf-8"))
        recs = [r for r in doc if r.get("fold") == FOLD_USED]
        asofs.append(recs[0].get("asof") if len(recs) == 1 else None)
        cal_srcs.append(f"{m['path']}:{rec}.fold=={FOLD_USED}.asof")
    asof = asofs[0] if asofs[0] is not None and len(set(asofs)) == 1 else None
    return {
        "model_fit_available": max(fits).isoformat(),
        "calibrator_asof": asof if asof is not None else "UNKNOWN",
        "sources": {"model_fit_available": fit_srcs,
                    "calibrator_asof": cal_srcs}}


def serving_vintage_verdict(decision_time, spec: dict | None = None,
                            _bundle: dict | None = None) -> dict:
    """Single-contract vintage verdict for one serving decision time.

    Runs the strict shared guard (scripts/opencode_r79_vintage.py). Frozen
    serving with a future-vintage bundle is REJECTED for causal evaluation
    (evaluation_label "integration-only"); ELIGIBLE only at/after the bundle
    (label "prospective-observation-only", no profit claim). Guard import or
    provenance failures fail closed, never silent.
    """
    bundle = _bundle if _bundle is not None else frozen_bundle_vintage(spec)
    try:
        from opencode_r79_vintage import check_availability
    except Exception as exc:
        return {"causal_eligibility": "REJECTED",
                "evaluation_label": "integration-only",
                "causal_eligibility_reason": (
                    f"vintage guard unavailable, fails closed: {exc!r}"),
                "vintage_sources": bundle.get("sources", {})}
    verdict, reason = check_availability(
        decision_time, bundle.get("model_fit_available"),
        bundle.get("calibrator_asof"))
    return {"causal_eligibility": verdict,
            "evaluation_label": ("prospective-observation-only"
                                 if verdict == "ELIGIBLE"
                                 else "integration-only"),
            "causal_eligibility_reason": reason,
            "vintage_sources": bundle.get("sources", {})}


def _annotate_serving_rows(rows: list[dict], bundle: dict) -> list[dict]:
    """Attach per-row causal-eligibility labels (annotation only; the frozen
    chain outputs -- scores, votes, gating -- are untouched)."""
    out = []
    for r in rows:
        if "decision_time" not in r:
            out.append({**r, "causal_eligibility": "NOT-A-DECISION",
                        "evaluation_label": "not-a-decision",
                        "causal_eligibility_reason": (
                            "no decision_time on this row (e.g. WARMUP); "
                            "not a causal evaluation candidate"),
                        "vintage_sources": bundle.get("sources", {})})
        else:
            out.append({**r, **serving_vintage_verdict(
                r["decision_time"], _bundle=bundle)})
    return out


def _frames_ready(store, closes, idx, context) -> bool:
    """True when every timeframe has >= context closed bars at this decision.

    Integration fix r76-int1 (leader): WARMUP_BARS counts 5m bars, but a history
    window starting mid-day loses its first partial daily bucket, leaving the
    1d frame one bar short at the first grid decision. Advancing past such
    leading bars (recording actual warmup) is the causal-correct behavior;
    silently skipping would hide it, crashing would block fresh operation.
    """
    ts = pd.Timestamp(closes[int(idx)]).value
    for frame in store.frames:
        ends = pd.DatetimeIndex(frame["close_time"]).asi8
        if int(np.searchsorted(ends, ts, side="right")) < context:
            return False
    return True


def decision_bars(n_bars: int, open_times: pd.DatetimeIndex) -> np.ndarray:
    """6h-UTC-grid closed bars with >= WARMUP_BARS bars of history (stride 72)."""
    grid_ok = ((open_times - pd.Timestamp("1970-01-01", tz="UTC")).asi8
               % pd.Timedelta(hours=6).value) == 0
    idx = np.where(grid_ok)[0]
    return idx[idx >= WARMUP_BARS].astype(np.int64)


def _load_model(seed: int, candidates: np.ndarray, spec: dict,
                device: torch.device):
    model = ResidualTemporalValue(candidates, width=48, dropout=0.15)
    ckpt = ROOT / spec["checkpoints"]["paths"][SEEDS.index(seed)]
    model.load_state_dict(load_file(str(ckpt)))
    model.eval()
    return model.to(device)


def infer_decisions(closed_candles_df: pd.DataFrame, spec: dict | None = None,
                    device: torch.device | None = None,
                    max_decisions: int | None = None) -> list[dict]:
    """Causal adapter: closed candles -> frozen v29 chain -> decisions.

    Returns a list with one leading status row when history is insufficient:
      [{"status": "WARMUP", ...}]  (never a strategy WAIT).
    Else one row per 6h decision bar with final action + HTF completeness proof.

    R80 serving-boundary enforcement: every returned row carries the strict
    vintage verdict (causal_eligibility / evaluation_label /
    causal_eligibility_reason / vintage_sources). Frozen fold-10 serving at a
    decision older than the bundle is REJECTED for causal evaluation
    (integration-only). Annotation only: scores, votes and gating untouched.
    """
    spec = spec or load_prespec()
    candles = validate_source(closed_candles_df)
    bundle = frozen_bundle_vintage(spec)
    if len(candles) < WARMUP_BARS:
        return _annotate_serving_rows([{"status": "WARMUP",
                  "reason": f"insufficient closed history: {len(candles)} < "
                            f"{WARMUP_BARS} (distinct from strategy WAIT)",
                  "n_bars": int(len(candles)),
                  "warmup_bars_required": WARMUP_BARS}], bundle)
    cfg, calibs = load_frozen_assets(spec)
    device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    candidates = np.asarray(grid(cfg), dtype=np.float32)

    store = SwingStore(candles, cfg)
    opens = pd.DatetimeIndex(pd.to_datetime(candles["open_time"], utc=True))
    closes = pd.DatetimeIndex(pd.to_datetime(candles["close_time"], utc=True))
    bars = decision_bars(len(candles), opens)
    if max_decisions is not None:
        bars = bars[:max_decisions]
    ready = [int(b) for b in bars
             if _frames_ready(store, closes, int(b), cfg["context"])]
    bars = np.asarray(ready, dtype=np.int64)
    if len(bars) == 0:
        return _annotate_serving_rows([{"status": "WARMUP",
                 "reason": "no 6h-aligned decision bar with full warmup yet",
                 "n_bars": int(len(candles)),
                 "warmup_bars_required": WARMUP_BARS}], bundle)

    # Build windows past-only; record HTF completeness proof per decision.
    seqs, feats, rows = [], [], []
    for bar in bars:
        decision_time = closes[int(bar)]
        windows, _, _ = store.at(decision_time)
        seqs.append(encode_windows(windows))
        w, stamps, ages, feat40, atr5, atr4 = store.sample(decision_time)
        feats.append(np.asarray(feat40, dtype=np.float32))
        proof = {}
        for tf, frame in zip(cfg["timeframes"], store.frames):
            last_close = pd.DatetimeIndex(
                pd.to_datetime(frame["close_time"], utc=True))
            used = last_close[last_close <= decision_time]
            if len(used) == 0:
                raise ValueError(f"HTF {tf}: no closed bar <= decision time")
            proof[tf] = str(used.max())
            assert used.max() <= decision_time, f"HTF leak on {tf}"
        rows.append({"bar_index": int(bar), "decision_time": decision_time,
                     "close": float(candles["close"].iloc[int(bar)]),
                     "atr5": float(atr5), "atr4": float(atr4),
                     "htf_last_close_lte_decision": proof})
    seqs = np.stack(seqs).astype(np.float32)
    feats = np.stack(feats).astype(np.float32)

    # Real checkpoint forward passes (GPU inference only).
    outs = []
    for seed in SEEDS:
        model = _load_model(seed, candidates, spec, device)
        outs.append(residual_predict(model, seqs, feats, batch_size=BATCH))
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    stacked = np.stack(outs).astype(np.float64)
    base, details = combine(stacked, 0.0)

    score = np.asarray(details["selection_score_percent"], dtype=np.float64)
    fill = np.asarray(details["mean_fill_score"], dtype=np.float64)
    preds = {}
    for m in MAPS:
        mapped = np.interp(score.ravel(), calibs[m]["x"],
                           calibs[m]["y"]).reshape(score.shape)
        arr = np.asarray(base, dtype=np.float64).copy()
        arr[..., 0] = mapped / np.clip(fill, 1e-6, 1 - 1e-6)
        preds[m] = arr

    per_map, dirs = {}, {}
    for m in MAPS:
        olist, dlist = [], []
        for j in range(preds[m].shape[0]):
            o = choose(preds[m][j], rows[j]["close"], rows[j]["atr5"],
                       rows[j]["atr4"], cfg)
            olist.append(o)
            dlist.append(1 if o.get("action") == "LONG"
                         else (-1 if o.get("action") == "SHORT" else 0))
        per_map[m] = olist
        dirs[m] = np.asarray(dlist, dtype=int)
    d2, d4, dall = dirs["isotonic_2"], dirs["isotonic_4"], dirs["isotonic_all"]

    # Votes (verbatim r66/r73 mask defs) + frequency loop (cap4/cd5, iso4 geometry).
    policy = cfg["policy"]
    majority = np.array([
        (d4[j] != 0) and ([d2[j], d4[j], dall[j]].count(int(d4[j])) >= 2)
        for j in range(len(bars))], dtype=bool)
    confirmed = (d4 != 0) & (dall == d4)
    order = np.argsort([r["decision_time"].value for r in rows], kind="stable")
    next_allowed = pd.Timestamp.min.tz_localize("UTC")
    monthly: dict[str, int] = {}
    gated = np.zeros(len(bars), dtype=bool)
    for pos in order:
        j = int(pos)
        if not bool(confirmed[j]):
            continue
        out = per_map["isotonic_4"][j]
        if out.get("action") == "WAIT":
            continue
        ts = rows[j]["decision_time"]
        month = ts.strftime("%Y-%m")
        if ts < next_allowed or monthly.get(month, 0) >= policy[
                "maximum_signals_per_month"]:
            continue
        gated[j] = True
        monthly[month] = monthly.get(month, 0) + 1
        next_allowed = ts + pd.Timedelta(days=policy["cooldown_days"])

    decisions = []
    for j in range(len(bars)):
        iso4 = per_map["isotonic_4"][j]
        if gated[j]:
            sig = dict(iso4)
            sig.pop("action", None)
            final = {"status": "READY_DECISION", "action": iso4["action"],
                     **sig}
        else:
            final = {"status": "READY_DECISION", "action": "WAIT",
                     "reason": "no confirmed vote or frequency-gated"}
        decisions.append({**rows[j], **final,
                          "vote_majority": bool(majority[j]),
                          "vote_confirmed": bool(confirmed[j]),
                          "per_map_action": {m: per_map[m][j].get("action")
                                             for m in MAPS},
                          "device": str(device)})
    # R80: serving-boundary vintage verdict on every decision row.
    return _annotate_serving_rows(decisions, bundle)
