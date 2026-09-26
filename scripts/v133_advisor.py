"""Live advisory for the v133 candidate (advisory only, no orders).

v133 = v115 models (models/frozen/v115_models.pkl) + tranched books (v127) + sizing by a
forward-vol forecast (v129): two frozen HGB vol models (v114-panel features for the v92/v94 books, v103 features for
the v103 book) replace vol42 in the weight formulas.

  python scripts/v133_advisor.py freeze [YYYY-MM-DD]   # vol models only
  python scripts/v133_advisor.py advise
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
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
VOL_MODELS = ROOT / "models/frozen/v133_vol_models.pkl"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


base = _load("v104_advisor_v133", ROOT / "scripts/v104_advisor.py")
base.MODELS = ROOT / "models/frozen/v115_models.pkl"
v125 = _load("v125", RD / "v125/v125_tranching.py")
v129 = _load("v129", RD / "v129/v129_vol_forecast_sizing.py")
PHASES = list(range(6))
base._w_lo = lambda df: v125.phased(v125.raw_lo(df), PHASES)
base._w_ls = lambda df: v125.phased(v125.raw_ls(df), PHASES)


def _fit_vol(panel, feats, cutoff):
    p = v129.add_fv(panel)
    tr = p[(p.t < cutoff) & p.fv.notna() & np.isfinite(p.fv)]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (v129.HV + 2)) < cutoff]
    m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0)
    return m.fit(tr[feats], tr["fv"]), len(tr)


def freeze(cutoff: pd.Timestamp) -> None:
    v114 = _load("v114", RD / "v114/v114_bitstamp_history.py")
    v114.v113.cb_bars = v114.cb_bars_ext
    ext = v114.v113
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    f92 = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    p103 = base.v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    vm92, n92 = _fit_vol(p92, f92, cutoff)
    vm103, n103 = _fit_vol(p103, f103, cutoff)
    VOL_MODELS.write_bytes(pickle.dumps({"vol92": vm92, "feats92": f92, "vol103": vm103, "feats103": f103, "cutoff": str(cutoff),
                                         "frozen_at": datetime.now(timezone.utc).isoformat(), "rows": [n92, n103]}))
    print("saved", VOL_MODELS, "rows", n92, n103)


def _prep(lo, ls, fl, recent):
    vm = pickle.loads(VOL_MODELS.read_bytes())
    p92 = np.exp(vm["vol92"].predict(recent[vm["feats92"]]))
    p103 = np.exp(vm["vol103"].predict(recent[vm["feats103"]]))
    return lo.assign(vol42=p92), ls.assign(vol42=p92), fl.assign(vol42=p103)


base._prep = _prep


def advise() -> dict:
    r = base.advise()
    r["candidate"] = "v133_deploy_v2"
    r["note"] = ("advisory only; v133 = tranched v115 + vol-forecast sizing: 2.44%/month OOS 2021-2026 (fee 2.22, execution "
                 "1.95), full-path DD 15.2-18.4%, hidden year strict 1m execution +29.0% DD 10.1%. Execution (v135): rest limits 0.10% better than the 4h bar open, "
                 "fall back to market at minute 15; not a guarantee")
    return r


if __name__ == "__main__":
    if sys.argv[1] == "freeze":
        freeze(pd.Timestamp(sys.argv[2], tz="UTC") if len(sys.argv) > 2 else pd.Timestamp.now(tz="UTC").floor("D") - pd.Timedelta(days=17))
    else:
        print(json.dumps(advise(), indent=1))
