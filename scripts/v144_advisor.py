"""Live advisory for the v144 candidate (advisory only, no orders).

v144 = v142 books (v92/v94 on the extended-history panel and v103, all with per-bar cross-sectional deviation/rank
features), v129 vol-forecast sizing (the v133 vol models), tranched daily schedule, portfolio vol target 0.25.
Logged weights are UNGOVERNED; the v110 drawdown governor g = clip((0.20 - DD)/0.10, 0, 1) on the 90-day peak of the
paper equity (from the prospective log, lagged 2 bars) must be applied when evaluating/using the log. Execution (v135):
limits 0.10% better than the 4h bar open, market fallback at minute 15.

  python scripts/v144_advisor.py freeze [YYYY-MM-DD]
  python scripts/v144_advisor.py advise
"""

from __future__ import annotations

import importlib.util
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


base = _load("v104_advisor_v144", ROOT / "scripts/v104_advisor.py")
base.MODELS = ROOT / "models/frozen/v144_models.pkl"
base.PORT_TARGET = 0.25
v133a = _load("v133_advisor_v144", ROOT / "scripts/v133_advisor.py")
v142 = _load("v142", RD / "v142/v142_cross_sectional_features.py")
base._w_lo, base._w_ls, base._prep = v133a.base._w_lo, v133a.base._w_ls, v133a._prep


def _augment(recent):
    return v142.add_xs(v142.add_xs(recent, v142.BASE), v142.FLOWX)


base._augment = _augment


def freeze(cutoff: pd.Timestamp) -> None:
    v114 = _load("v114", RD / "v114/v114_bitstamp_history.py")
    v114.v113.cb_bars = v114.cb_bars_ext
    ext = v114.v113
    ext.v92.load_asset = ext.load_asset_ext
    p94 = ext.v94.add_targets(v142.add_xs(ext.v92.build(), v142.BASE))
    f92 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    p103 = v142.add_xs(base.v103.build(), v142.BASE + v142.FLOWX)
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    models = {"feats92": f92, "feats103": f103, "cutoff": str(cutoff), "frozen_at": datetime.now(timezone.utc).isoformat(), "xs": True}
    for h in (42,) + base.v94.HORIZONS:
        models[f"h{h}"], n = base._fit(p94, f92, f"y{h}", h, cutoff)
        print("v92/v94 horizon", h, "rows", n, flush=True)
    for h in base.v103.HS:
        models[f"f{h}"], n = base._fit(p103, f103, f"y{h}", h, cutoff)
        print("v103 horizon", h, "rows", n, flush=True)
    base.MODELS.write_bytes(pickle.dumps(models))
    print("saved", base.MODELS)


def advise() -> dict:
    r = base.advise()
    r["candidate"] = "v144_deploy_v3"
    r["note"] = ("advisory only; v144 = v142 books + vol-forecast sizing + tranching at portfolio target 0.25; weights are "
                 "UNGOVERNED - apply the v110 drawdown governor on paper equity; realistic 1m execution OOS 2021-2026: "
                 "3.37%/month, full-path DD 19.6% (target 0.25 chosen ex post); execution: limits 0.10% better than the "
                 "4h open, market at minute 15; not a guarantee")
    return r


if __name__ == "__main__":
    if sys.argv[1] == "freeze":
        freeze(pd.Timestamp(sys.argv[2], tz="UTC") if len(sys.argv) > 2 else pd.Timestamp.now(tz="UTC").floor("D") - pd.Timedelta(days=17))
    else:
        print(json.dumps(advise(), indent=1))
