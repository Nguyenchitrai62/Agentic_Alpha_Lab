"""Compare historical dataset clocks; do not reprice or regenerate old labels."""
import torch
import json
from pathlib import Path
import numpy as np
import pandas as pd
from agentic_alpha_lab.data.decision_clock import decision_indices
from agentic_alpha_lab.data.training import sha256


def run():
    output = Path("artifacts/research/decision_clock_audit_v1.json")
    if output.exists():
        raise FileExistsError("Audit already exists")
    source = Path("data/processed/btc_2022_2026_source_v1/candles.parquet")
    times = pd.read_parquet(source, columns=["close_time"]).close_time
    anchored = decision_indices(times, 72, 2028, "1970-01-01T00:04:59.999Z")
    runs = {}
    for name in ("kronos_swing_20260905_v2", "kronos_swing_v5_20260905"):
        path = Path("data/processed") / name / "validation_decisions.parquet"
        decisions = pd.read_parquet(path)
        stamp = pd.Timestamp(decisions.signal_time.iloc[0])
        runs[name] = {"first_validation_decision": str(stamp), "rows": len(decisions), "sha256": sha256(path)}
    shift = 50
    shifted = times.iloc[shift:].reset_index(drop=True)
    matched = decision_indices(shifted, 72, 2028, "1970-01-01T00:04:59.999Z") + shift
    np.testing.assert_array_equal(anchored[anchored >= shift], matched)
    report = {"source_sha256": sha256(source), "datasets": runs, "history_offset_invariance": True,
              "historical_datasets_modified": False, "warning": "v2 vs v5 decisions differ; not a controlled architecture-only comparison. Future configs must declare decision_anchor_utc. Existing manifests/source snapshots retained."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    run()
