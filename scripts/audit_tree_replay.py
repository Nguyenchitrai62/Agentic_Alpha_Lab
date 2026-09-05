"""Replay already-opened alerts and append an audit, without reranking or retesting."""
import torch
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
from infer_tree_pipeline import infer
from check_swing_acceptance import assess
from agentic_alpha_lab.data.training import sha256


def audit(a):
    target = a.evaluation / "replay_audit.json"
    if target.exists():
        raise FileExistsError("Do not overwrite an existing audit")
    report_path = a.evaluation / "report.json"
    report = json.loads(report_path.read_text())
    manifest = json.loads((a.evaluation / "evaluation_manifest.json").read_text())
    if sha256(a.checkpoint / "metadata.json") != manifest["checkpoint_metadata_sha256"]:
        raise ValueError("Checkpoint metadata changed since evaluation")
    if sha256(a.candles) != manifest["source_sha256"]:
        raise ValueError("Source differs from evaluated source")
    signals = pd.read_parquet(a.evaluation / "signals.parquet")
    replays = []
    fields = ["candidate_id", "entry_limit", "stop_loss", "take_profit_1", "take_profit_2", "holding_bars"]
    for row in signals.to_dict("records"):
        value = infer(SimpleNamespace(checkpoint=a.checkpoint, candles=a.candles,
                                     as_of=str(row["signal_time"]), state=None))
        assert value["decision_clock_eligible"]
        for field in fields:
            np.testing.assert_allclose(value[field], row[field], rtol=1e-7, atol=1e-7)
        replays.append(value)
    gates = json.loads(Path("configs/swing_acceptance.json").read_text())
    result = {"report_sha256": sha256(report_path), "historical_report_modified": False,
              "replayed_alert_count": len(replays), "replays": replays, "acceptance": assess(report, gates),
              "bootstrap_interpretation": "Original one-trade resampling quantiles are degenerate and must NOT be interpreted as confidence bounds. Original report preserved; future evaluator suppresses quantiles for fewer than 6 trades.",
              "frequency_note": "Only 3 alerts, all June; April, May, July zero. Does not meet desired 1-4 alerts each month.",
              "approved_for_live": False}
    target.write_text(json.dumps(result, indent=2))
    print(json.dumps({"replayed_alert_count": len(replays), "acceptance": result["acceptance"], "audit": str(target)}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--candles", type=Path, required=True)
    p.add_argument("--evaluation", type=Path, required=True)
    audit(p.parse_args())
