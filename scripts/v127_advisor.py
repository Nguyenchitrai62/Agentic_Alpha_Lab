"""Live advisory for the v127 candidate: the v115 models with tranched books (advisory only, no orders).

Same frozen models as v115 (models/frozen/v115_models.pkl); each book's weights are the mean of the
six phase-shifted daily schedules (v125/v127), so the suggestion carries no rebalance-hour luck.

  python scripts/v127_advisor.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


base = _load("v104_advisor_v127", ROOT / "scripts/v104_advisor.py")
base.MODELS = ROOT / "models/frozen/v115_models.pkl"
v125 = _load("v125", RD / "v125/v125_tranching.py")
PHASES = list(range(6))
base._w_lo = lambda df: v125.phased(v125.raw_lo(df), PHASES)
base._w_ls = lambda df: v125.phased(v125.raw_ls(df), PHASES)


def advise() -> dict:
    r = base.advise()
    r["candidate"] = "v127_tranched_portfolio"
    r["note"] = ("advisory only; v127 = v115 models with tranched books: 2.38%/month OOS 2021-2026 (fee 2.16, execution "
                 "1.88), full-path DD 16.8-20.2%, hidden year strict 1m execution +30.2% DD 10.0%; not a guarantee")
    return r


if __name__ == "__main__":
    print(json.dumps(advise(), indent=1))
