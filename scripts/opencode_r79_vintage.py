"""Opencode R79 Track-B: bounded vintage audit harness (AUDIT-ONLY, local, no fitting).

Scope: inventory 11 folds x 3 seeds, trace per-fold vs frozen fold-10 routing,
rerun the ALREADY-OPENED W2 anchor (decision rows [2450,2485)) with the correct
historical per-fold weights as a separately labeled reproduction mode
(label: vintage-repro, NOT holdout, NOT untouched), enforce availability checks
with boundary negative tests, and emit the eligible/excluded interval table.

Reads existing assets only. Creates files ONLY under artifacts/research/opencode_r79/.
Exits nonzero on availability violation (self-test failure -> 1; --claim causal
with a future-vintage bundle -> 2).

torch is imported before pandas (Windows DLL load-order rule).
"""
import torch  # noqa: F401  (torch truoc pandas)

import argparse
import datetime as _dt
import hashlib
import json
import subprocess
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

LABEL = "vintage-repro"  # NOT holdout, NOT untouched
SEEDS = (1729, 1730, 1731)
FOLDS_CONFIG = json.loads(
    (ROOT / "configs/swing_v15_continuous_folds.json").read_text(encoding="utf-8"))
FOLD_WINDOWS = [(pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC"))
                for a, b in FOLDS_CONFIG["folds"]]
ANCHOR_ROWS = (2450, 2485)
CANDLE_SLICE_END = 218500  # W2 anchor: positional bars [0,218500)
OUT = ROOT / "artifacts/research/opencode_r79"


def sha_file(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def stat_times(path: Path) -> dict:
    st = path.stat()
    return {
        "size_bytes": st.st_size,
        "mtime_utc": _dt.datetime.fromtimestamp(
            st.st_mtime, _dt.timezone.utc).isoformat(),
        "ctime_utc": _dt.datetime.fromtimestamp(
            st.st_ctime, _dt.timezone.utc).isoformat(),
        "note": ("local filesystem time = Kaggle-download date, NOT training "
                 "completion; training ran on Kaggle Tesla T4, completion time UNKNOWN"),
    }


# ---------------------------------------------------------------- inventory
def inventory() -> dict:
    folds = []
    n_full = n_partial = n_unknown = 0
    prespec = json.loads(
        (ROOT / "configs/opencode_r76_infer.json").read_text(encoding="utf-8"))
    for k in range(11):
        for seed in SEEDS:
            base = (ROOT / "artifacts/kaggle/v29_download/tcn-training"
                    / f"seed{seed}/checkpoints/fold_{k}")
            meta_p = base / "metadata.json"
            ckpt_p = base / "model.safetensors"
            rec = {"fold": k, "seed": seed,
                   "metadata_path": str(meta_p.relative_to(ROOT)),
                   "checkpoint_path": str(ckpt_p.relative_to(ROOT))}
            meta = None
            if meta_p.exists():
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
                rec["train_decisions_src"] = (
                    f"{rec['metadata_path']}:train_decisions")
                rec["train_decisions"] = meta.get("train_decisions")
                rec["test_decisions"] = meta.get("test_decisions")
                rec["last_training_label_end_src"] = (
                    f"{rec['metadata_path']}:last_training_label_end")
                rec["last_training_label_end"] = meta.get(
                    "last_training_label_end")
                rec["embargo_days_src"] = (
                    f"{rec['metadata_path']}:training.embargo_days")
                rec["embargo_days"] = (meta.get("training") or {}).get(
                    "embargo_days")
                rec["window_days"] = (meta.get("training") or {}).get(
                    "window_days")
                rec["weights_sha256_in_metadata"] = meta.get("weights_sha256")
                rec["torch"] = meta.get("torch")
                rec["gpu"] = meta.get("gpu")
                # No validation split recorded in v29 metadata -> UNKNOWN.
                rec["val_end"] = "UNKNOWN"
                rec["val_end_src"] = (
                    f"{rec['metadata_path']}: no validation field present")
                # Simulated fit cutoff = last label end + embargo.
                try:
                    le = pd.Timestamp(rec["last_training_label_end"])
                    rec["simulated_fit_cutoff"] = (
                        le + pd.Timedelta(days=rec["embargo_days"])).isoformat()
                    rec["simulated_fit_cutoff_src"] = (
                        "derived: last_training_label_end + embargo_days "
                        "(policy: 730day past-only train; label_end before "
                        "refit minus 8days; source configs/"
                        "swing_v15_continuous_folds.json:policy)")
                except Exception:
                    rec["simulated_fit_cutoff"] = "UNKNOWN"
                    rec["simulated_fit_cutoff_src"] = "derivation failed"
            else:
                for f_ in ("train_decisions", "test_decisions",
                           "last_training_label_end", "embargo_days",
                           "window_days", "simulated_fit_cutoff", "val_end"):
                    rec[f_] = "UNKNOWN"
            if ckpt_p.exists():
                rec["disk_sha256"] = sha_file(ckpt_p)
                rec["disk_sha256_src"] = (
                    f"sha256 of file bytes {rec['checkpoint_path']}")
                rec["file_times"] = stat_times(ckpt_p)
                rec["deployment_availability"] = "UNKNOWN"
                rec["deployment_availability_src"] = (
                    "no deploy log exists; local presence since "
                    "Kaggle download only; training completion time UNKNOWN")
                want_meta = (meta or {}).get("weights_sha256")
                rec["sha_match_metadata"] = (
                    rec["disk_sha256"] == want_meta) if want_meta else "UNKNOWN"
            else:
                rec["disk_sha256"] = "UNKNOWN"
                rec["file_times"] = "UNKNOWN"
                rec["deployment_availability"] = "UNKNOWN"
                rec["sha_match_metadata"] = "UNKNOWN"
            if k == 10 and ckpt_p.exists():
                want = prespec["checkpoints"]["sha256"][SEEDS.index(seed)]
                rec["sha_match_r76_prespec"] = (rec["disk_sha256"] == want)
                rec["sha_match_r76_prespec_src"] = (
                    "configs/opencode_r76_infer.json:checkpoints.sha256")
            # train window derived from fold start (730d past-only).
            fstart = FOLD_WINDOWS[k][0]
            rec["train_window_derived"] = [
                (fstart - pd.Timedelta(days=730)).isoformat(),
                (fstart - pd.Timedelta(days=8)).isoformat()]
            rec["train_window_derived_src"] = (
                "derived: fold-k start minus 730d/8d per "
                "configs/swing_v15_continuous_folds.json:policy; "
                "exact per-row train membership UNKNOWN (indices.npz not mapped)")
            if (meta is not None and ckpt_p.exists()
                    and rec.get("sha_match_metadata") is True
                    and rec["last_training_label_end"] != "UNKNOWN"):
                rec["status"] = "full"
                n_full += 1
            elif meta is not None or ckpt_p.exists():
                rec["status"] = "partial"
                n_partial += 1
            else:
                rec["status"] = "unknown"
                n_unknown += 1
            folds.append(rec)
    # Calibrators (shared across seeds, per-fold records in file).
    calibs = {}
    for short, rec in (("isotonic_2", "iso2"), ("isotonic_4", "iso4"),
                       ("isotonic_all", "isoall")):
        m = prespec["calibrators"]["maps"][rec]
        p = ROOT / m["path"]
        doc = json.loads(p.read_text(encoding="utf-8"))
        rows = []
        for r in doc:
            rows.append({"fold": r.get("fold"), "asof": r.get("asof"),
                         "eligible_rows": r.get("eligible_rows"),
                         "latest_label_end": r.get("latest_label_end")})
        calibs[short] = {
            "path": m["path"], "disk_sha256": sha_file(p),
            "prespec_sha256": m["sha256"],
            "sha_match_prespec": sha_file(p) == m["sha256"],
            "file_times": stat_times(p),
            "fit_provenance_src": ("configs/opencode_r76_infer.json:"
                                   "calibrators.fit_provenance"),
            "records": rows}
    return {"label": LABEL, "folds": folds,
            "summary": {"n_full": n_full, "n_partial": n_partial,
                        "n_unknown": n_unknown, "n_total": 33},
            "calibrators": calibs,
            "scaler": {
                "fitted_scaler": "NONE (stateless per-window norm)",
                "src": ("configs/opencode_r76_infer.json:"
                        "scaler_normalization")},
            "research_config": {
                "path": prespec["research_config"]["path"],
                "sha256": prespec["research_config"]["sha256"]}}
# ---------------------------------------------------------------- routing
def fold_for_signal_time(ts: pd.Timestamp) -> int | None:
    for k, (a, b) in enumerate(FOLD_WINDOWS):
        if a <= ts < b:
            return k
    return None


def routing() -> dict:
    dec = pd.read_parquet(
        ROOT / "data/processed/swing_regime_research_v4/decisions.parquet")
    anchor = dec.iloc[ANCHOR_ROWS[0]:ANCHOR_ROWS[1]]
    rows = []
    for i, r in anchor.iterrows():
        ts = pd.Timestamp(r["signal_time"])
        rows.append({"decision_row": int(i), "bar_index": int(r["bar_index"]),
                     "signal_time": str(ts),
                     "reference_fold": fold_for_signal_time(ts),
                     "frozen_serving_fold": 10})
    folds_hit = sorted({x["reference_fold"] for x in rows})
    return {
        "label": LABEL,
        "reference_rule_src": ("configs/swing_v15_continuous_folds.json:policy "
                               "+ artifacts/research/opencode_r78_rolling/w2/"
                               "summary.json:known_signal_reproduction."
                               "first_divergence.cause (fold_k scores decisions "
                               "in fold-k window)"),
        "frozen_rule_src": ("scripts/opencode_r76_infer.py:45 FOLD_USED=10 + "
                            "configs/opencode_r76_infer.json:ensemble.fold_used"),
        "anchor_rows": list(ANCHOR_ROWS),
        "anchor_reference_folds": folds_hit,
        "rows": rows}
# ------------------------------------------------------- availability rule
_UNKNOWN_TOKENS = frozenset({
    "", "UNKNOWN", "NONE", "NULL", "NAT", "NAN", "NA", "N/A",
    "UNDEFINED", "MISSING", "NAN.",
})


def _coerce_utc_strict(value, role: str):
    """Strictly coerce one timestamp to tz-aware UTC.

    Returns (Timestamp|None, reason). Any missing/null/empty/NaT/NaN/UNKNOWN/
    invalid/ambiguous input yields (None, reason) -- NEVER a silent NaT and
    NEVER an exception. Explicit timezones are normalized to UTC; naive
    values are REJECTED as ambiguous (no implicit localization).
    """
    if value is None:
        return None, f"{role} timestamp missing (None)"
    if isinstance(value, str):
        text = value.strip()
        if not text or text.upper() in _UNKNOWN_TOKENS:
            return None, f"{role} timestamp missing/UNKNOWN ({value!r})"
    else:
        try:
            if pd.isna(value):
                return None, f"{role} timestamp is NaT/NaN"
        except Exception:
            return None, (f"{role} timestamp not a scalar timestamp "
                           f"({type(value).__name__})")
    try:
        ts = pd.Timestamp(value)
    except Exception:
        return None, f"{role} timestamp unparseable ({value!r})"
    try:
        if pd.isna(ts):
            return None, f"{role} timestamp is NaT"
    except Exception:
        return None, f"{role} timestamp is NaT"
    if ts.tzinfo is None:
        return None, (f"{role} timestamp naive without timezone (ambiguous "
                       f"wall time, rejected; got {value!r})")
    return ts.tz_convert("UTC"), ""


def check_availability(decision_time, model_fit_available,
                       calibrator_asof) -> tuple[str, str]:
    """Strict vintage guard (R80: fail-closed).

    Rule: future-vintage model OR calibrator at an old decision => REJECTED
    for causal evaluation (may be labeled integration-only). UNKNOWN fails
    closed. Model needs decision_time > fit-available (strict: equality
    REJECTED; fit-available = last training label end + embargo). Calibrator
    needs decision_time >= asof.
    NO exception and NO NaT comparison may yield ELIGIBLE: every rejection
    path above returns REJECTED explicitly.
    """
    try:
        dt_, err = _coerce_utc_strict(decision_time, "decision")
        if err:
            return "REJECTED", f"UNKNOWN metadata fails closed: {err}"
        mf, err = _coerce_utc_strict(model_fit_available,
                                     "model-fit-available")
        if err:
            return "REJECTED", f"UNKNOWN metadata fails closed: {err}"
        ca, err = _coerce_utc_strict(calibrator_asof, "calibrator-asof")
        if err:
            return "REJECTED", f"UNKNOWN metadata fails closed: {err}"
    except Exception as exc:  # defensive: never let a guard bug fail open
        return "REJECTED", f"availability guard internal error fails closed: {exc!r}"
    try:
        if dt_ <= mf:
            return ("REJECTED",
                    f"model vintage violation: decision {dt_} <= fit-available {mf} "
                    "(fit-available = last training label end + embargo; "
                    "strict: equality REJECTED)")
        if dt_ < ca:
            return ("REJECTED",
                    f"calibrator vintage violation: decision {dt_} < asof {ca}")
    except Exception as exc:
        return "REJECTED", f"availability comparison fails closed: {exc!r}"
    return ("ELIGIBLE",
            "model fit-available < decision and calibrator asof <= decision "
            "(UTC-normalized)")


def boundary_tests(inv: dict) -> dict:
    meta2 = next(r for r in inv["folds"]
                 if r["fold"] == 2 and r["seed"] == 1729)
    fit2 = pd.Timestamp(meta2["simulated_fit_cutoff"])
    cal2_asof = "2023-12-01T00:00:00Z"  # iso4 fold-2 record
    cal10_asof = "2025-12-01T00:00:00Z"  # frozen fold-10 record
    fit10 = pd.Timestamp(next(
        r for r in inv["folds"] if r["fold"] == 10 and r["seed"] == 1729
    )["simulated_fit_cutoff"])
    anchor0 = pd.Timestamp("2024-01-11 12:04:59.999000+00:00")
    cases = [
        {"name": "T1 decision exactly at model fit-available",
         "decision": fit2.isoformat(), "model_fit": fit2.isoformat(),
         "cal": cal2_asof, "expect": "REJECTED"},
        {"name": "T2 calibrator one bar (5m) too new",
         "decision": anchor0.isoformat(),
         "model_fit": fit2.isoformat(),
         "cal": (anchor0 + pd.Timedelta(minutes=5)).isoformat(),
         "expect": "REJECTED"},
        {"name": "T3 per-fold-correct model + future shared calibrator",
         "decision": anchor0.isoformat(), "model_fit": fit2.isoformat(),
         "cal": cal10_asof, "expect": "REJECTED",
         "note": "selecting per-fold model does NOT cure future calibrator"},
        {"name": "T4 positive control: fold2 model + fold2-era calibrator",
         "decision": anchor0.isoformat(), "model_fit": fit2.isoformat(),
         "cal": cal2_asof, "expect": "ELIGIBLE"},
        {"name": "T5 frozen fold10 bundle at anchor (model+calibrator future)",
         "decision": anchor0.isoformat(), "model_fit": fit10.isoformat(),
         "cal": cal10_asof, "expect": "REJECTED"},
        # R80 fail-closed cases: missing/null/NaT/UNKNOWN/invalid/naive.
        {"name": "F1 counterexample: model+calibrator None",
         "decision": anchor0.isoformat(), "model_fit": None,
         "cal": None, "expect": "REJECTED"},
        {"name": "F2 counterexample: model+calibrator 'NaT' strings",
         "decision": anchor0.isoformat(), "model_fit": "NaT",
         "cal": "NaT", "expect": "REJECTED"},
        {"name": "F3 decision None",
         "decision": None, "model_fit": fit2.isoformat(),
         "cal": cal2_asof, "expect": "REJECTED"},
        {"name": "F4 decision empty/UNKNOWN",
         "decision": "UNKNOWN", "model_fit": fit2.isoformat(),
         "cal": cal2_asof, "expect": "REJECTED"},
        {"name": "F5 fold0 calibrator asof None (casually ineligible)",
         "decision": "2023-07-01T00:00:00Z",
         "model_fit": "2023-05-31T19:04:59.999000+00:00",
         "cal": None, "expect": "REJECTED"},
        {"name": "F6 naive decision (ambiguous, no timezone)",
         "decision": "2024-01-11 12:04:59",
         "model_fit": fit2.isoformat(),
         "cal": cal2_asof, "expect": "REJECTED"},
        {"name": "F7 invalid model-fit string",
         "decision": anchor0.isoformat(), "model_fit": "not-a-date",
         "cal": cal2_asof, "expect": "REJECTED"},
    ]
    out = []
    ok = True
    for c in cases:
        verdict, reason = check_availability(
            c["decision"], c["model_fit"], c["cal"])
        passed = verdict == c["expect"]
        ok = ok and passed
        out.append({**c, "verdict": verdict, "reason": reason,
                    "passed": passed})
    return {"cases": out, "all_passed": ok}
# ------------------------------------------------------------- vintage rerun
def load_anchor_features():
    cfg = json.loads((ROOT / "data/processed/swing_regime_research_v4"
                       "/config.json").read_text(encoding="utf-8"))
    candles = pd.read_parquet(
        ROOT / "data/processed/swing_regime_research_v4/candles.parquet"
    ).iloc[:CANDLE_SLICE_END]
    candles = validate_source(candles)
    closes = pd.DatetimeIndex(pd.to_datetime(candles["close_time"], utc=True))
    dec = pd.read_parquet(
        ROOT / "data/processed/swing_regime_research_v4/decisions.parquet")
    anchor = dec.iloc[ANCHOR_ROWS[0]:ANCHOR_ROWS[1]]
    store = SwingStore(candles, cfg)
    candidates = np.asarray(grid(cfg), dtype=np.float32)
    seqs, feats, rows = [], [], []
    for i, r in anchor.iterrows():
        bar = int(r["bar_index"])
        decision_time = closes[bar]
        windows, _, _ = store.at(decision_time)
        seqs.append(encode_windows(windows))
        w, stamps, ages, feat40, atr5, atr4 = store.sample(decision_time)
        feats.append(np.asarray(feat40, dtype=np.float32))
        rows.append({"decision_row": int(i), "bar_index": bar,
                     "decision_time": str(decision_time),
                     "close": float(candles["close"].iloc[bar]),
                     "atr5": float(atr5), "atr4": float(atr4)})
    return cfg, candidates, (np.stack(seqs).astype(np.float32),
                             np.stack(feats).astype(np.float32), rows)


def forward_fold(fold: int, seqs, feats, candidates, device) -> dict:
    outs = []
    for seed in SEEDS:
        ckpt = (ROOT / "artifacts/kaggle/v29_download/tcn-training"
                / f"seed{seed}/checkpoints/fold_{fold}/model.safetensors")
        if not ckpt.exists():
            raise FileNotFoundError(f"frozen asset missing: {ckpt}")
        model = ResidualTemporalValue(candidates, width=48, dropout=0.15)
        model.load_state_dict(load_file(str(ckpt)))
        model.eval()
        model.to(device)
        outs.append(residual_predict(model, seqs, feats, batch_size=32))
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    return {"stacked": np.stack(outs).astype(np.float64)}


def apply_calibrator(base, details, calib_rec) -> np.ndarray:
    score = np.asarray(details["selection_score_percent"], dtype=np.float64)
    fill = np.asarray(details["mean_fill_score"], dtype=np.float64)
    xv = np.asarray(calib_rec["x"], dtype=np.float64)
    yv = np.asarray(calib_rec["y"], dtype=np.float64)
    mapped = np.interp(score.ravel(), xv, yv).reshape(score.shape)
    arr = np.asarray(base, dtype=np.float64).copy()
    arr[..., 0] = mapped / np.clip(fill, 1e-6, 1 - 1e-6)
    return arr


def anchor_forward_bundle() -> dict:
    """Shared bounded forward bundle: anchor features + fold-2 / fold-10
    (twice, determinism) checkpoint stacks. Inference only, no fitting."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    cfg, candidates, (seqs, feats, rows) = load_anchor_features()
    f2 = forward_fold(2, seqs, feats, candidates, device)
    f10 = forward_fold(10, seqs, feats, candidates, device)
    f10b = forward_fold(10, seqs, feats, candidates, device)  # determinism
    return {"device": device, "cfg": cfg, "candidates": candidates,
            "seqs": seqs, "feats": feats, "rows": rows,
            "f2": f2, "f10": f10, "f10b": f10b}


def vintage_repro() -> dict:
    bundle = anchor_forward_bundle()
    device = bundle["device"]
    cfg, rows = bundle["cfg"], bundle["rows"]
    f2, f10, f10b = bundle["f2"], bundle["f10"], bundle["f10b"]
    prespec = json.loads(
        (ROOT / "configs/opencode_r76_infer.json").read_text(encoding="utf-8"))
    # Reference per-fold routing for the anchor: fold 2 (Jan 2024 in
    # [2023-12-01, 2024-03-01)); frozen serving: fold 10 everywhere.
    det_bitexact = bool(np.array_equal(f10["stacked"], f10b["stacked"]))
    per_seed_dmax, first_div = [], None
    for s in range(3):
        d = np.abs(f2["stacked"][s] - f10["stacked"][s]).max()
        per_seed_dmax.append(float(d))
        idx = np.argmax(
            np.abs(f2["stacked"][s] - f10["stacked"][s]).reshape(len(rows), -1
                                                                ).max(axis=1))
        if first_div is None or rows[int(idx)]["decision_row"] < first_div[
                "decision_row"]:
            first_div = {"seed": SEEDS[s], "decision_row": rows[int(idx)][
                "decision_row"], "bar_index": rows[int(idx)]["bar_index"]}
    base2, det2 = combine(f2["stacked"], 0.0)
    base10, det10 = combine(f10["stacked"], 0.0)
    dmax_combined = float(np.abs(np.asarray(base2) - np.asarray(base10)).max())
    # Calibrators: frozen fold-10 iso4 vs vintage fold-2-era iso4 (asof
    # 2023-12-01, available at the anchor).
    doc4 = json.loads((ROOT / prespec["calibrators"]["maps"]["iso4"][
        "path"]).read_text(encoding="utf-8"))
    cal10 = next(r for r in doc4 if r["fold"] == 10)
    cal2 = next(r for r in doc4 if r["fold"] == 2)
    p10_frozen = apply_calibrator(base10, det10, cal10)   # fold10-everywhere
    p2_stageA = apply_calibrator(base2, det2, cal10)      # vintage weights only
    p2_stageB = apply_calibrator(base2, det2, cal2)       # fully vintage
    acts = {}
    for name, preds in (("fold10_everywhere", p10_frozen),
                        ("stageA_fold2weights_frozencalib", p2_stageA),
                        ("stageB_fold2weights_fold2calib", p2_stageB)):
        alist = []
        for j in range(preds.shape[0]):
            o = choose(preds[j], rows[j]["close"], rows[j]["atr5"],
                       rows[j]["atr4"], cfg)
            alist.append(o.get("action"))
        acts[name] = alist
    first_action_flip = None
    for j, r in enumerate(rows):
        if acts["fold10_everywhere"][j] != acts["stageA_fold2weights_"
                                                "frozencalib"][j]:
            first_action_flip = {
                "stage": "stageA(checkpoint vintage only)",
                "decision_row": r["decision_row"], "bar_index": r["bar_index"],
                "fold10_action": acts["fold10_everywhere"][j],
                "vintage_action": acts["stageA_fold2weights_frozencalib"][j]}
            break
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(f2["stacked"]).tobytes())
    h2 = hashlib.sha256()
    h2.update(np.ascontiguousarray(f10["stacked"]).tobytes())
    return {
        "label": LABEL, "device": str(device),
        "anchor_rows": list(ANCHOR_ROWS),
        "reference_fold": 2, "frozen_fold": 10,
        "stage_raw_forward_per_seed_dmax": dict(zip(SEEDS, per_seed_dmax)),
        "first_raw_divergence": first_div,
        "stage_combined_dmax": dmax_combined,
        "determinism_fold10_rerun_bitexact": det_bitexact,
        "stacked_sha256": {"fold2": h.hexdigest(), "fold10": h2.hexdigest()},
        "actions": acts,
        "first_action_flip_stageA": first_action_flip,
        "n_action_flips_stageA": sum(
            a != b for a, b in zip(acts["fold10_everywhere"],
                                   acts["stageA_fold2weights_frozencalib"])),
        "n_action_flips_stageB_vs_frozen": sum(
            a != b for a, b in zip(acts["fold10_everywhere"],
                                   acts["stageB_fold2weights_fold2calib"])),
        "calibrator_note": ("stageA isolates checkpoint vintage; stageB is "
                            "fully vintage-correct; NEITHER is a holdout")}


def eligible_intervals(inv: dict) -> dict:
    cal4 = {r["fold"]: r for r in inv["calibrators"]["isotonic_4"]["records"]}
    table = []
    for k in range(11):
        a, b = FOLD_WINDOWS[k]
        m = next(r for r in inv["folds"]
                 if r["fold"] == k and r["seed"] == 1729)
        fit = m.get("simulated_fit_cutoff")
        c = cal4.get(k, {})
        asof = c.get("asof")
        # R80 fix: folds with UNKNOWN fit-available or UNKNOWN/None calibrator
        # asof (fold 0: warmup-WAIT record, 0 eligible rows, no asof key) are
        # WITHHELD for causal eval. UNKNOWNs preserved, never invented.
        unknown_fields = []
        if fit in (None, "UNKNOWN"):
            unknown_fields.append("model fit-available")
        if asof in (None, "UNKNOWN"):
            unknown_fields.append("calibrator asof")
        if unknown_fields:
            table.append({
                "fold": k,
                "window": [a.isoformat(), b.isoformat()],
                "eligible_bundle_for_causal_eval": (
                    "WITHHELD: UNKNOWN " + ", ".join(unknown_fields)
                    + " (preserved, not invented; no causal claim)"),
                "causal_eligibility": "WITHHELD",
                "unknown_fields": unknown_fields,
                "model_fit_available": fit if fit is not None else "UNKNOWN",
                "calibrator_asof": asof if asof is not None else "UNKNOWN",
                "calibrator_eligible_rows": c.get("eligible_rows", "UNKNOWN"),
                "calibrator_latest_label_end": (
                    c.get("latest_label_end") or "UNKNOWN"),
                "excluded_for_causal_eval": (
                    "frozen fold-10 bundle (model fit-available "
                    + str(next(r for r in inv["folds"]
                               if r["fold"] == 10 and r["seed"] == 1729
                               ).get("simulated_fit_cutoff"))
                    + "; calibrator asof 2025-12-01T00:00:00Z)")})
            continue
        table.append({
            "fold": k,
            "window": [a.isoformat(), b.isoformat()],
            "eligible_bundle_for_causal_eval": {
                "model": f"fold_{k} 3-seed (fit-available {fit})",
                "calibrator": (f"iso2/iso4/isoall fold-{k} record "
                               f"(asof {asof})"),
                "condition": "decision_time > fit-available AND >= asof"},
            "causal_eligibility": ("per-decision guard: decision_time > "
                                   "fit-available AND >= asof; UNKNOWN fails "
                                   "closed"),
            "model_fit_available": fit,
            "calibrator_asof": asof,
            "calibrator_eligible_rows": c.get("eligible_rows", "UNKNOWN"),
            "calibrator_latest_label_end": (
                c.get("latest_label_end") or "UNKNOWN"),
            "excluded_for_causal_eval": (
                "frozen fold-10 bundle (model fit-available "
                + str(next(r for r in inv["folds"]
                           if r["fold"] == 10 and r["seed"] == 1729
                           ).get("simulated_fit_cutoff"))
                + "; calibrator asof 2025-12-01T00:00:00Z)")})
    f10fit = next(r for r in inv["folds"]
                  if r["fold"] == 10 and r["seed"] == 1729
                  ).get("simulated_fit_cutoff")
    return {
        "label": LABEL,
        "rule": ("future-vintage model or calibrator at an old decision => "
                 "REJECTED for causal evaluation (integration-only only)"),
        "per_fold_table": table,
        "prospective_bundle": {
            "checkpoints": {
                "seed1729": inv["folds"][30]["disk_sha256"],
                "seed1730": inv["folds"][31]["disk_sha256"],
                "seed1731": inv["folds"][32]["disk_sha256"]},
            "calibrators_sha256": {
                m: inv["calibrators"][m]["disk_sha256"]
                for m in ("isotonic_2", "isotonic_4", "isotonic_all")},
            "eligible_for_prospective_observation_only_after": (
                "2025-12-01T00:00:00Z (max of fold-10 fit-available "
                f"{f10fit} and calibrator asof); no profitability claim"),
            "note": ("reserve holdout [2026-04-01,2026-08-01] NOT opened; "
                     "declaration only, no evaluation")},
        "no_profitability_promotion": True}


OUT_R80 = ROOT / "artifacts/research/opencode_r80"

# Pinned stored historical reference for the W2 anchor (walk-forward v30
# per-fold weights, NOT the frozen fold-10 rerun): fold-2 test decisions are
# decision rows [2284, 2284+364), so stored_test_position = decision_row-2284.
STORED_FOLD2_PRED = {
    seed: (f"artifacts/research/swing_v15_continuous_20260905/training/seed{seed}"
           f"/temporal_neural/fold_2/predictions.npy")
    for seed in SEEDS}
STORED_FOLD2_SIGNALS = {
    seed: (f"artifacts/research/swing_v15_continuous_20260905/training/seed{seed}"
           f"/temporal_neural/fold_2/signals.parquet")
    for seed in SEEDS}
PUBLISHED_SIGNALS = ("artifacts/research/opencode_v15_mapensemble/"
                     "confirmed_dd_guard/signals.parquet")
FOLD2_TEST_START_ROW = 2284  # first fold-2 test decision row in decisions.parquet


def current_attestation(inv: dict) -> dict:
    """R80 CURRENT availability attestation for the existing verified bundle.

    observed_at is the UTC instant of THIS run (never backdated). Records all
    asset/source/config sha256 plus fit/calibration ranges WITH unknowns
    marked. Authorizes neither past claims nor trading.
    """
    observed_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    prespec = json.loads(
        (ROOT / "configs/opencode_r76_infer.json").read_text(encoding="utf-8"))
    folds_cfg_p = ROOT / "configs/swing_v15_continuous_folds.json"
    r76_cfg_p = ROOT / "configs/opencode_r76_infer.json"
    research_cfg_p = ROOT / prespec["research_config"]["path"]
    data_manifest_p = (ROOT / "data/processed/swing_regime_research_v4"
                       / "manifest.json")
    data_config_p = (ROOT / "data/processed/swing_regime_research_v4"
                     / "config.json")
    data_plan_p = (ROOT / "data/processed/swing_regime_research_v4"
                   / "plan.json")
    dec_p = (ROOT / "data/processed/swing_regime_research_v4"
             / "decisions.parquet")
    candles = pd.read_parquet(
        ROOT / "data/processed/swing_regime_research_v4/candles.parquet",
        columns=["open_time"])
    f10recs = [r for r in inv["folds"] if r["fold"] == 10]
    fit_ranges = []
    for k in range(11):
        m = next(r for r in inv["folds"]
                 if r["fold"] == k and r["seed"] == 1729)
        a, b = FOLD_WINDOWS[k]
        cal_maps = {}
        for short in ("isotonic_2", "isotonic_4", "isotonic_all"):
            rec = next((r for r in inv["calibrators"][short]["records"]
                        if r["fold"] == k), {})
            cal_maps[short] = {
                "asof": rec.get("asof") or "UNKNOWN",
                "latest_label_end": rec.get("latest_label_end") or "UNKNOWN",
                "eligible_rows": rec.get("eligible_rows", "UNKNOWN")}
        fit = m.get("simulated_fit_cutoff", "UNKNOWN")
        unknowns = []
        if fit in (None, "UNKNOWN"):
            unknowns.append("model fit-available")
        if cal_maps["isotonic_4"]["asof"] in (None, "UNKNOWN"):
            unknowns.append("calibrator asof")
        fit_ranges.append({
            "fold": k,
            "window": [a.isoformat(), b.isoformat()],
            "model_fit_available": fit if fit is not None else "UNKNOWN",
            "model_fit_src": m.get("simulated_fit_cutoff_src", "UNKNOWN"),
            "val_end": m.get("val_end", "UNKNOWN"),
            "val_end_src": m.get("val_end_src", "UNKNOWN"),
            "deployment_availability": m.get("deployment_availability",
                                             "UNKNOWN"),
            "deployment_availability_src": m.get(
                "deployment_availability_src", "UNKNOWN"),
            "calibrators": cal_maps,
            "causal_eligibility": ("WITHHELD" if unknowns
                                   else "per-decision guard"),
            "unknown_fields": unknowns})
    return {
        "label": "r80-current-attestation",
        "observed_at": observed_at,
        "observed_at_note": ("UTC instant of THIS attestation run; authorizes "
                             "neither past claims nor trading; NEVER backdated "
                             "to 2025-12-01; prospective observations after "
                             "this instant may be tracked honestly"),
        "bundle": "frozen fold-10 3-seed serving (configs/opencode_r76_infer.json)",
        "asset_sha256": {
            "checkpoints": {
                f"seed{r['seed']}": r["disk_sha256"] for r in f10recs},
            "calibrators": {
                m: inv["calibrators"][m]["disk_sha256"]
                for m in ("isotonic_2", "isotonic_4", "isotonic_all")},
            "configs": {
                "opencode_r76_infer.json": sha_file(r76_cfg_p),
                "swing_v15_continuous_folds.json": sha_file(folds_cfg_p),
                str(prespec["research_config"]["path"]): sha_file(
                    research_cfg_p)},
            "sources": {
                "decisions.parquet": sha_file(dec_p),
                "decisions_rows": int(pd.read_parquet(dec_p,
                                                      columns=["bar_index"]
                                                      ).shape[0]),
                "candles_rows": int(candles.shape[0]),
                "manifest.json": sha_file(data_manifest_p),
                "config.json": sha_file(data_config_p),
                "plan.json": sha_file(data_plan_p)},
            "serving_code": {
                "scripts/opencode_r79_vintage.py": sha_file(
                    ROOT / "scripts/opencode_r79_vintage.py"),
                "scripts/opencode_r76_infer.py": sha_file(
                    ROOT / "scripts/opencode_r76_infer.py")}},
        "fit_calibration_ranges": fit_ranges,
        "authorizes_trading": False,
        "authorizes_past_claims": False,
        "no_profitability_promotion": True}


def repro_vs_stored(bundle: dict, inv: dict) -> dict:
    """R80 bounded repro: correct per-fold (fold-2) rerun vs the ACTUAL stored
    historical reference on W2 anchor rows [2450,2485) (stored test positions
    [166,201)). Reproduction, not holdout performance."""
    rows, f2 = bundle["rows"], bundle["f2"]
    cfg = bundle["cfg"]
    dec = pd.read_parquet(
        ROOT / "data/processed/swing_regime_research_v4/decisions.parquet")
    # Pinned mapping proof: first fold-2 test row is decision row 2284.
    assert int(dec.iloc[FOLD2_TEST_START_ROW]["bar_index"]) == 201312
    stored_sig0 = pd.read_parquet(ROOT / STORED_FOLD2_SIGNALS[1729])
    assert int(stored_sig0.iloc[0]["bar_index"]) == 201312
    per_seed, dmax_all = {}, []
    for s, seed in enumerate(SEEDS):
        sp = ROOT / STORED_FOLD2_PRED[seed]
        stored = np.load(str(sp)).astype(np.float64)  # (364,16,6) float32
        sl = stored[166:201]  # anchor rows 2450..2484
        assert sl.shape[0] == len(rows) == 35
        rerun = np.asarray(f2["stacked"][s], dtype=np.float64)
        diff = np.abs(rerun - sl)
        h = hashlib.sha256()
        h.update(np.ascontiguousarray(sl).tobytes())
        per_seed[str(seed)] = {
            "stored_path": STORED_FOLD2_PRED[seed],
            "stored_sha256": sha_file(sp),
            "stored_slice_sha256": h.hexdigest(),
            "stored_shape": list(stored.shape),
            "n_compared": int(sl.shape[0]),
            "dmax": float(diff.max()),
            "mean_abs": float(diff.mean())}
        dmax_all.append(float(diff.max()))
    # Fully vintage-correct stageB actions (fold-2 weights + fold-2 calibrator).
    prespec = json.loads(
        (ROOT / "configs/opencode_r76_infer.json").read_text(encoding="utf-8"))
    doc4 = json.loads((ROOT / prespec["calibrators"]["maps"]["iso4"][
        "path"]).read_text(encoding="utf-8"))
    cal2 = next(r for r in doc4 if r["fold"] == 2)
    base2, det2 = combine(f2["stacked"], 0.0)
    p2_stageB = apply_calibrator(base2, det2, cal2)
    stageB = []
    for j in range(p2_stageB.shape[0]):
        o = choose(p2_stageB[j], rows[j]["close"], rows[j]["atr5"],
                   rows[j]["atr4"], cfg)
        stageB.append(o.get("action"))
    pub = pd.read_parquet(ROOT / PUBLISHED_SIGNALS)
    anchor_check = []
    for row_id in (2457, 2477):
        j = row_id - ANCHOR_ROWS[0]
        bar = int(dec.iloc[row_id]["bar_index"])
        hit = pub[pub["bar_index"] == bar]
        pub_action = ("LONG" if len(hit) and int(hit.iloc[0]["direction"]) == 1
                      else ("SHORT" if len(hit) else "ABSENT"))
        anchor_check.append({
            "decision_row": row_id, "bar_index": bar,
            "published_action": pub_action,
            "stageB_action": stageB[j],
            "match": bool(len(hit) and pub_action == stageB[j])})
    worst = max(dmax_all)
    residual_class = ("EXPLAINED" if worst <= 1e-4 else
                      ("MIXED" if worst <= 1e-2 else "UNEXPLAINED"))
    # Weight-provenance verdict (file evidence only, no fitting): the stored
    # v15 predictions predate the pinned v29 retrain checkpoints. The v29
    # fold-2 metadata pins a prediction_sha256 for ITS OWN (Kaggle) test-set
    # predictions, which are not stored on disk (only the sha survives).
    weight_prov = {}
    for s, seed in enumerate(SEEDS):
        sp = ROOT / STORED_FOLD2_PRED[seed]
        meta = json.loads(
            (ROOT / "artifacts/kaggle/v29_download/tcn-training"
             / f"seed{seed}/checkpoints/fold_2/metadata.json").read_text(
                 encoding="utf-8"))
        stored_h = hashlib.sha256(sp.read_bytes()).hexdigest()
        weight_prov[str(seed)] = {
            "stored_predictions_sha256": stored_h,
            "v29_metadata_prediction_sha256": meta.get("prediction_sha256"),
            "v29_weights_sha256": meta.get("weights_sha256"),
            "match": stored_h == meta.get("prediction_sha256"),
            "note": ("mismatch => stored v15 vectors came from different "
                     "fitted weights than the pinned v29 checkpoints; exact "
                     "reproduction of the stored vectors is impossible from "
                     "pinned weights")}
    # Stored per-seed fold-2 signals whose bars fall inside the anchor window:
    # action-level overlap check vs fully-vintage stageB (same combine/choose
    # path; stored signals are uncalibrated single-seed, stageB is calibrated
    # 3-seed, so agreement is evidence, not identity).
    anchor_bars = {r["bar_index"] for r in rows}
    overlap = []
    for seed in SEEDS:
        sdoc = pd.read_parquet(ROOT / STORED_FOLD2_SIGNALS[seed])
        for _, sr in sdoc.iterrows():
            bar = int(sr["bar_index"])
            if bar not in anchor_bars:
                continue
            j = next(i for i, r in enumerate(rows)
                     if r["bar_index"] == bar)
            overlap.append({
                "seed": seed, "bar_index": bar,
                "decision_row": rows[j]["decision_row"],
                "stored_action": str(sr["action"]),
                "stageB_action": stageB[j],
                "match": bool(str(sr["action"]) == stageB[j])})
    # Cross-run determinism vs the R79 stored rerun hashes (if present).
    r79_path = OUT / "b_vintage_repro.json"
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(f2["stacked"]).tobytes())
    h10 = hashlib.sha256()
    h10.update(np.ascontiguousarray(bundle["f10"]["stacked"]).tobytes())
    cross = {"r79_reference_present": r79_path.exists()}
    if cross["r79_reference_present"]:
        ref = json.loads(r79_path.read_text(encoding="utf-8"))
        cross["fold2_sha_match_r79"] = (
            ref["stacked_sha256"]["fold2"] == h.hexdigest())
        cross["fold10_sha_match_r79"] = (
            ref["stacked_sha256"]["fold10"] == h10.hexdigest())
    return {
        "label": LABEL,
        "anchor_rows": list(ANCHOR_ROWS),
        "reference_fold": 2,
        "frozen_fold": 10,
        "mapping": "stored_test_position = decision_row - 2284",
        "mapping_proof": {"first_test_bar": 201312,
                          "first_test_decision_row": FOLD2_TEST_START_ROW,
                          "stored_signals_first_bar": int(
                              stored_sig0.iloc[0]["bar_index"])},
        "per_seed_vs_stored": per_seed,
        "worst_dmax_vs_stored": worst,
        "residual_class": residual_class,
        "residual_note": ("EXPLAINED = rerun-vs-stored dmax <= 1e-4 "
                          "(cross-GPU float nondeterminism only); else the "
                          "residual values above are UNEXPLAINED and must not "
                          "be promoted as reproduction"),
        "stored_reference_note": ("stored fold_2/predictions.npy (per-seed "
                                  "walk-forward weights, Kaggle Tesla T4) + "
                                  "stored fold_2/signals.parquet "
                                  "(calibrated=False: uncalibrated scores, so "
                                  "stageB calibrated actions differ by "
                                  "construction) + published "
                                  "confirmed_dd_guard anchors"),
        "weight_provenance": weight_prov,
        "stored_signal_overlap": overlap,
        "determinism_fold10_rerun_bitexact": bool(
            np.array_equal(bundle["f10"]["stacked"],
                           bundle["f10b"]["stacked"])),
        "stacked_sha256": {"fold2": h.hexdigest(), "fold10": h10.hexdigest()},
        "cross_run_vs_r79": cross,
        "stageB_actions": stageB,
        "published_anchor_check": anchor_check,
        "calibrator_note": ("stageB is fully vintage-correct for the anchor; "
                            "stored signals are uncalibrated; NEITHER is a "
                            "holdout")}


def _scope_check(run_start: float):
    """Forbidden-path mtime check with Track-B in-scope allowances.

    In-scope for Track B (excluded from violation): the guard call-site edit
    in scripts/opencode_r76_infer.py and NEW tests/test_r80_b_*.py. Everything
    else (r78 roll, core, r77/matrix scripts, other configs/tests/src) stays
    forbidden. Recorded transparently in the manifest.
    """
    forbidden_roots = [
        ROOT / "scripts/opencode_r78_roll.py",
        ROOT / "scripts/opencode_r77_advisor_core.py",
        ROOT / "configs", ROOT / "tests", ROOT / "src"]
    allowed_prefixes = [
        "scripts/opencode_r76_infer.py",
        "tests/test_r80_b_guard.py",
        "tests/test_r80_b_serving.py",
        "tests/test_r80_b_repro.py"]
    touched, allowed = [], []
    for fr in forbidden_roots:
        if fr.is_file():
            cands = [fr]
        elif fr.is_dir():
            cands = [p for p in fr.rglob("*") if p.is_file()]
        else:
            cands = []
        for p in cands:
            if p.stat().st_mtime > run_start:
                rel = str(p.relative_to(ROOT)).replace("\\", "/")
                (allowed if any(rel == a or rel.startswith(a)
                                for a in allowed_prefixes)
                 else touched).append(rel)
    return touched, allowed


def run_r80() -> int:
    OUT_R80.mkdir(parents=True, exist_ok=True)
    run_start = _dt.datetime.now(_dt.timezone.utc).timestamp()
    inv = inventory()
    bt = boundary_tests(inv)
    (OUT_R80 / "b_availability_tests.json").write_text(
        json.dumps({"label": LABEL, **bt}, indent=1, default=str),
        encoding="utf-8")
    ei = eligible_intervals(inv)
    (OUT_R80 / "b_eligible_intervals.json").write_text(
        json.dumps(ei, indent=1, default=str), encoding="utf-8")
    att = current_attestation(inv)
    (OUT_R80 / "b_current_attestation.json").write_text(
        json.dumps(att, indent=1, default=str), encoding="utf-8")
    bundle = anchor_forward_bundle()
    rs = repro_vs_stored(bundle, inv)
    (OUT_R80 / "b_repro_vs_stored.json").write_text(
        json.dumps(rs, indent=1, default=str), encoding="utf-8")
    gs = subprocess.run(["git", "status", "--short"], capture_output=True,
                        text=True, cwd=str(ROOT))
    gd = subprocess.run(["git", "diff", "--name-only"], capture_output=True,
                        text=True, cwd=str(ROOT))
    touched_forbidden, allowed_touched = _scope_check(run_start)
    manifest = {
        "label": LABEL, "device": str(bundle["device"]),
        "stacked_sha256": rs["stacked_sha256"],
        "determinism_bitexact": rs["determinism_fold10_rerun_bitexact"],
        "cross_run_vs_r79": rs["cross_run_vs_r79"],
        "worst_dmax_vs_stored": rs["worst_dmax_vs_stored"],
        "residual_class": rs["residual_class"],
        "attestation_observed_at": att["observed_at"],
        "git_status": gs.stdout,
        "git_tracked_diff_name_only": gd.stdout,
        "note_tracked_dirt": ("tracked modifications/untracked files outside "
                              "opencode_r80/ pre-date this run (other workers); "
                              "this harness writes only OUT_R80/b_*.json; "
                              "artifacts/research/opencode_r79/* untouched"),
        "forbidden_paths_touched_by_this_run": touched_forbidden,
        "allowed_in_scope_touched": allowed_touched,
        "existing_files_modified": bool(touched_forbidden),
        "r79_reference": ("artifacts/research/opencode_r79/b_inventory.json, "
                          "b_routing.json, b_eligible_intervals.json "
                          "(pre-fix), b_availability_tests.json (pre-fix)"),
        "artifacts": sorted(str(p.relative_to(ROOT)).replace("\\", "/")
                            for p in OUT_R80.glob("b_*.json"))}
    (OUT_R80 / "b_manifest.json").write_text(
        json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    print(json.dumps({
        "boundary_all_passed": bt["all_passed"],
        "boundary_n_cases": len(bt["cases"]),
        "fold0_withheld": ei["per_fold_table"][0]["causal_eligibility"],
        "attestation_observed_at": att["observed_at"],
        "worst_dmax_vs_stored": rs["worst_dmax_vs_stored"],
        "residual_class": rs["residual_class"],
        "determinism_bitexact": rs["determinism_fold10_rerun_bitexact"],
        "existing_files_modified": manifest["existing_files_modified"]},
        indent=1))
    if not bt["all_passed"]:
        print("AVAILABILITY SELF-TEST FAILURE", file=sys.stderr)
        return 1
    if manifest["existing_files_modified"]:
        print("SCOPE VIOLATION: existing file modified", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claim", default="vintage-repro",
                    choices=["vintage-repro", "causal"])
    ap.add_argument("--decision", default=None)
    ap.add_argument("--model-fit-available", default=None)
    ap.add_argument("--calibrator-asof", default=None)
    ap.add_argument("--emit-r80", action="store_true",
                    help=("Track-B R80 run: fixed tables + current attestation "
                          "+ bounded stored-reference repro under "
                          "artifacts/research/opencode_r80/"))
    args = ap.parse_args()
    if args.claim == "causal":
        verdict, reason = check_availability(
            args.decision, args.model_fit_available, args.calibrator_asof)
        print(json.dumps({"claim": "causal", "verdict": verdict,
                          "reason": reason}, indent=1))
        return 0 if verdict == "ELIGIBLE" else 2
    if args.emit_r80:
        return run_r80()
    OUT.mkdir(parents=True, exist_ok=True)
    run_start = _dt.datetime.now(_dt.timezone.utc).timestamp()
    inv = inventory()
    (OUT / "b_inventory.json").write_text(
        json.dumps(inv, indent=1, default=str), encoding="utf-8")
    rt = routing()
    (OUT / "b_routing.json").write_text(
        json.dumps(rt, indent=1, default=str), encoding="utf-8")
    vr = vintage_repro()
    (OUT / "b_vintage_repro.json").write_text(
        json.dumps(vr, indent=1, default=str), encoding="utf-8")
    bt = boundary_tests(inv)
    (OUT / "b_availability_tests.json").write_text(
        json.dumps({"label": LABEL, **bt}, indent=1, default=str),
        encoding="utf-8")
    ei = eligible_intervals(inv)
    (OUT / "b_eligible_intervals.json").write_text(
        json.dumps(ei, indent=1, default=str), encoding="utf-8")
    gs = subprocess.run(["git", "status", "--short"], capture_output=True,
                        text=True, cwd=str(ROOT))
    gd = subprocess.run(["git", "diff", "--name-only"], capture_output=True,
                        text=True, cwd=str(ROOT))
    # Scope proof: harness never writes outside OUT/; any forbidden-path
    # mtime newer than this run's start would be a scope violation.
    forbidden_roots = [
        ROOT / "scripts/opencode_r78_roll.py",
        ROOT / "scripts/opencode_r76_infer.py",
        ROOT / "scripts/opencode_r77_advisor_core.py",
        ROOT / "configs", ROOT / "tests", ROOT / "src"]
    touched_forbidden = []
    for fr in forbidden_roots:
        if fr.is_file():
            if fr.stat().st_mtime > run_start:
                touched_forbidden.append(str(fr.relative_to(ROOT)))
        elif fr.is_dir():
            for p in fr.rglob("*"):
                if p.is_file() and p.stat().st_mtime > run_start:
                    touched_forbidden.append(str(p.relative_to(ROOT)))
    manifest = {
        "label": LABEL, "device": vr["device"],
        "stacked_sha256": vr["stacked_sha256"],
        "determinism_bitexact": vr["determinism_fold10_rerun_bitexact"],
        "git_status": gs.stdout,
        "git_tracked_diff_name_only": gd.stdout,
        "note_tracked_dirt": ("tracked modifications/untracked files outside "
                              "opencode_r79/ pre-date this run (other workers); "
                              "this harness writes only OUT/b_*.json"),
        "forbidden_paths_touched_by_this_run": touched_forbidden,
        "existing_files_modified": bool(touched_forbidden),
        "artifacts": sorted(str(p.relative_to(ROOT))
                            for p in OUT.glob("b_*.json"))}
    (OUT / "b_manifest.json").write_text(
        json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"inventory_summary": inv["summary"],
                      "anchor_reference_folds": rt["anchor_reference_folds"],
                      "first_raw_divergence": vr["first_raw_divergence"],
                      "per_seed_dmax": vr["stage_raw_forward_per_seed_dmax"],
                      "first_action_flip": vr["first_action_flip_stageA"],
                      "boundary_all_passed": bt["all_passed"],
                      "existing_files_modified":
                          manifest["existing_files_modified"]}, indent=1))
    if not bt["all_passed"]:
        print("AVAILABILITY SELF-TEST FAILURE", file=sys.stderr)
        return 1
    if manifest["existing_files_modified"]:
        print("SCOPE VIOLATION: existing file modified", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
