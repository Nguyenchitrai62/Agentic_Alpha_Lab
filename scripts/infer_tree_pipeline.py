"""Offline trading-support candidate from frozen model and causal candle history.

Does not place orders or assume the user has no existing position. Alert state is
optional and read-only; otherwise the output is explicitly only a candidate.
"""
import torch
import argparse
import json
from pathlib import Path
import pandas as pd
from agentic_alpha_lab.models.tree_pipeline import PortableForest
from agentic_alpha_lab.models.regime_gate import apply_gate
from agentic_alpha_lab.data.swing import SwingStore, choose
from agentic_alpha_lab.data.training import validate_source, sha256


def on_decision_clock(timestamp, stride):
    """Frozen datasets start at a UTC midnight 5-minute bar, sampled every stride."""
    timestamp = pd.Timestamp(timestamp).tz_convert("UTC")
    origin = pd.Timestamp("1970-01-01T00:04:59.999Z")
    return (timestamp.value - origin.value) % pd.Timedelta(minutes=5 * stride).value == 0


def infer(a):
    meta = json.loads((a.checkpoint / "metadata.json").read_text())
    if sha256(a.checkpoint / "forests.npz") != meta["checkpoint_sha256"]:
        raise ValueError("Model hash mismatch")
    root = Path(__file__).resolve().parents[1]
    for name, digest in meta["source_hashes"].items():
        if sha256(root / name) != digest:
            raise ValueError(f"Inference source differs from frozen model: {name}")
    candles = validate_source(pd.read_parquet(a.candles))
    cfg = meta["config"]
    as_of = pd.Timestamp(candles.close_time.iloc[-1])
    if a.as_of:
        cutoff = pd.Timestamp(a.as_of)
        if cutoff.tzinfo is None:
            raise ValueError("Use timezone-aware as_of")
        candles = candles.loc[candles.close_time <= cutoff].reset_index(drop=True)
        if candles.empty:
            raise ValueError("No candles at or before as_of")
        as_of = pd.Timestamp(candles.close_time.iloc[-1])
    _, _, _, features, atr5, atr4 = SwingStore(candles, cfg).sample(as_of)
    model = PortableForest(a.checkpoint)
    raw, disagreement = model.swing_prediction(features[None])
    raw = apply_gate(raw, features[None], cfg, meta.get("regime_gate", "none"))
    result = choose(raw[0], float(candles.close.iloc[-1]), atr5, atr4, cfg)
    result.pop("conditional_net_quantiles_percent", None)
    result.pop("conditional_win_score", None)
    if result["action"] != "WAIT":
        result["ensemble_disagreement_net_percent"] = float(disagreement[0, result["candidate_id"]])
        result["earliest_entry_at"] = str(as_of + pd.Timedelta(milliseconds=1))
        result["entry_expires_at"] = str(as_of + pd.Timedelta(milliseconds=1, minutes=5*cfg["entry_expiry_bars"]))
    state_checked = a.state is not None
    if state_checked:
        state = json.loads(a.state.read_text())
        alerts = [pd.Timestamp(t) for t in state.get("alert_times", [])]
        if any(t.tzinfo is None or t > as_of for t in alerts):
            raise ValueError("State must contain timezone-aware past alerts only")
        blocked = None
        if state.get("position_open", False):
            blocked = "Existing position; no overlapping signal"
        elif alerts and as_of - max(alerts) < pd.Timedelta(days=cfg["policy"]["cooldown_days"]):
            blocked = "Cooldown after prior alert"
        elif sum(t.tz_convert("UTC").strftime("%Y-%m") == as_of.strftime("%Y-%m") for t in alerts) >= cfg["policy"]["maximum_signals_per_month"]:
            blocked = "Monthly alert cap"
        if blocked:
            result = {"action": "WAIT", "reason": blocked}
    clock_eligible = on_decision_clock(as_of, cfg["stride"])
    if not clock_eligible:
        result = {"action": "WAIT", "reason": "Outside the frozen 6-hour decision clock"}
    return {"symbol": "BTCUSDT", "as_of": str(as_of), "source_candles_sha256": sha256(a.candles),
            "model": meta["model"], "checkpoint_sha256": meta["checkpoint_sha256"],
            "regime_gate": meta.get("regime_gate", "none"), "timeframes": cfg["timeframes"],
            "research_only": True, "state_checked": state_checked, "candidate_only": not state_checked,
            "decision_clock_eligible": clock_eligible,
            "probabilities_calibrated": False, "live_risk_limit_guaranteed": False,
            "note": "No orders sent. Historical candles are not live advice. Alert state is read-only; caller must persist new alerts.", **result}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--candles", type=Path, required=True)
    p.add_argument("--as-of")
    p.add_argument("--state", type=Path)
    print(json.dumps(infer(p.parse_args()), indent=2))
