"""Frozen dip agents for the MANUAL dip pipelines (v342 L2 = paper pipeline M3): two bracket limits per coin at 3.0 / 4.0 sigma_4h - paper only.

The agents are the frozen v321 R2 models (fitted on the pooled dip experience of every rung depth 2.0 .. 5.0, cutoff 2026-09-11,
models/frozen/v321_r2_dip_agents.pkl); only the rung set differs: rungs 3.0 and 4.0 sigma, the rung-depth feature is the rung's own depth.
Decisions are taken once per bar at the bar open (state at the close of minute 0), exactly the v306 bar-open tables used in v338-v342.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUNGS = (3.0, 4.0)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_r2 = _load("v321_r2_for_manual", ROOT / "scripts/v321_r2_dip_agents.py")
load, size_multiplier, tp_multiple = _r2.load, _r2.size_multiplier, _r2.tp_multiple


class LiveState(_r2.sa.LiveState):
    """The seven v293 state features; the rung-depth feature is the MANUAL rung depth of rung index r."""

    def features(self, s: str, bar_start: pd.Timestamp, rung: int, minute: int = 0) -> np.ndarray:
        x = super().features(s, bar_start, 0, minute)
        x[1] = RUNGS[rung]
        return x
