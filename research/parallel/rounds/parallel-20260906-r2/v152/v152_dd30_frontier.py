"""v152: what drawdown does 5%/month require? v144 realistic engine with a 30% governor (registry v152, track C).

v144 books and realistic engine (10 bps limits on 1m data), but the governor is g = clip((0.30 - DD)/0.15, 0, 1) (full
size below 15% DD, zero at 30%) and portfolio targets 0.30 / 0.35 / 0.40 (cap 2x). Reporting frontier for the user's
risk decision (the user's current limit is DD <= 20%); nothing here is a recommendation to exceed it. Also the 20%
governor rows are NOT recomputed (see v144). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v152/v152_dd30_frontier.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v144", HERE.parent / "v144" / "v144_deploy_v3.py")
v144 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v144)
ROWS = (("t30_gov30", 0.30), ("primary_t35_gov30", 0.35), ("t40_gov30", 0.40))


def main():
    src = Path(v144.__file__).read_text()
    assert "(0.20 - (1 - eq[j] / peak)) / 0.10" in src
    p103, books = v144.books_v142()
    # same engine as v144.simulate with the governor constants changed to 0.30 / 0.15
    code = src[src.index("def simulate"):src.index("def main")].replace("(0.20 - (1 - eq[j] / peak)) / 0.10", "(0.30 - (1 - eq[j] / peak)) / 0.15")
    ns = dict(v144.__dict__)
    ns["ROWS"] = tuple((k, t, True) for k, t in ROWS)
    exec(code, ns)
    out = {"version": "v152", "governor": "clip((0.30 - DD)/0.15, 0, 1)", **ns["simulate"](p103, books)}
    out["reference_v144_gov20"] = {"t25": (3.374, 19.63)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v152_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
