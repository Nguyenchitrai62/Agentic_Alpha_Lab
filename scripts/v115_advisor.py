"""Live advisory for the v115 candidate (advisory only, no orders).

v115 = v104 with the v92/v94 models trained on the v114 extended history (Bitstamp 2013 + Coinbase + Binance for BTC,
Coinbase + Binance for ETH). Live features come from Binance exactly as v104; only the training history differs.

  python scripts/v115_advisor.py freeze [YYYY-MM-DD]
  python scripts/v115_advisor.py advise
"""

from __future__ import annotations

import importlib.util
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


base = _load("v104_advisor_base", ROOT / "scripts/v104_advisor.py")
base.MODELS = ROOT / "models/frozen/v115_models.pkl"


def freeze(cutoff: pd.Timestamp) -> None:
    v114 = _load("v114", RD / "v114/v114_bitstamp_history.py")
    v114.v113.cb_bars = v114.cb_bars_ext
    ext = v114.v113
    ext.v92.load_asset = ext.load_asset_ext
    p94 = ext.v94.add_targets(ext.v92.build())
    f92 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    p103 = base.v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    models = {"feats92": f92, "feats103": f103, "cutoff": str(cutoff), "frozen_at": datetime.now(timezone.utc).isoformat(), "history": "v114 extended"}
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
    r["candidate"] = "v115_models_portfolio"
    r["note"] = "advisory only; v115 candidate: 2.61%/month OOS 2021-2026 at the logged 00:00 UTC rebalance phase, luck-free phase mean 2.31% (execution stress 1.82%), full-path DD up to 24% across phases; not a guarantee"
    return r


if __name__ == "__main__":
    if sys.argv[1] == "freeze":
        cutoff = pd.Timestamp(sys.argv[2], tz="UTC") if len(sys.argv) > 2 else pd.Timestamp.now(tz="UTC").floor("D") - pd.Timedelta(days=17)
        freeze(cutoff)
    else:
        print(json.dumps(advise(), indent=1))
