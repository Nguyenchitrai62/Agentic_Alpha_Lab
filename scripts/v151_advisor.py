"""Live advisory for the v151 candidate (advisory only, no orders).

v151 = 0.5 * v144 (scripts/v144_advisor.py) + 0.5 * an options-flow model set (v150 recipe: Deribit BTC options-flow
features in all return models, v142 cross-sectional features, v133 vol models, tranching, portfolio target 0.25).
Approximation vs research: the research blend averaged the books before the portfolio vol scale; here the two final
weight vectors (each with its own portfolio scale) are averaged. Weights are UNGOVERNED: apply the v110 drawdown
governor on paper equity. Execution (v135): limits 0.10% better than the 4h open, market fallback at minute 15.

  python scripts/v151_advisor.py freeze [YYYY-MM-DD]   # options model set only
  python scripts/v151_advisor.py advise
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


v144a = _load("v144_advisor_v151", ROOT / "scripts/v144_advisor.py")
upd = _load("deribit_options_update", ROOT / "scripts/deribit_options_update.py")
v150 = _load("v150", RD / "v150/v150_options_flow.py")
v142 = v144a.v142
optb = _load("v104_advisor_v151opt", ROOT / "scripts/v104_advisor.py")
optb.MODELS = ROOT / "models/frozen/v151_opt_models.pkl"
optb.PORT_TARGET = 0.25
optb._w_lo, optb._w_ls, optb._prep = v144a.base._w_lo, v144a.base._w_ls, v144a.base._prep


def _augment_opt(recent):
    r = recent.merge(v150.opt_features(), on="t", how="left")
    return v142.add_xs(v142.add_xs(r, v142.BASE), v142.FLOWX)


optb._augment = _augment_opt


def freeze(cutoff: pd.Timestamp) -> None:
    v114 = _load("v114", RD / "v114/v114_bitstamp_history.py")
    v114.v113.cb_bars = v114.cb_bars_ext
    ext = v114.v113
    ext.v92.load_asset = ext.load_asset_ext
    of = v150.opt_features()
    p94 = ext.v94.add_targets(v142.add_xs(ext.v92.build().merge(of, on="t", how="left"), v142.BASE))
    f92 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    p103 = v142.add_xs(optb.v103.build().merge(of, on="t", how="left"), v142.BASE + v142.FLOWX)
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    models = {"feats92": f92, "feats103": f103, "cutoff": str(cutoff), "frozen_at": datetime.now(timezone.utc).isoformat(), "options": True}
    for h in (42,) + optb.v94.HORIZONS:
        models[f"h{h}"], n = optb._fit(p94, f92, f"y{h}", h, cutoff)
        print("v92/v94 horizon", h, "rows", n, flush=True)
    for h in optb.v103.HS:
        models[f"f{h}"], n = optb._fit(p103, f103, f"y{h}", h, cutoff)
        print("v103 horizon", h, "rows", n, flush=True)
    optb.MODELS.write_bytes(pickle.dumps(models))
    print("saved", optb.MODELS)


def advise() -> dict:
    appended = upd.update()
    a, b = v144a.advise(), optb.advise()
    syms = sorted(set(a["perp_weight"]) | set(b["perp_weight"]))
    perp = {s: round(0.5 * a["perp_weight"].get(s, 0.0) + 0.5 * b["perp_weight"].get(s, 0.0), 4) for s in syms}
    spot = {s: round(0.5 * a["spot_weight"].get(s, 0.0) + 0.5 * b["spot_weight"].get(s, 0.0), 4) for s in syms}
    return dict(candidate="v151_deploy_v4", decision_bar_close=a["decision_bar_close"], perp_weight=perp, spot_weight=spot,
                portfolio_scale=round(0.5 * a["portfolio_scale"] + 0.5 * b["portfolio_scale"], 3), carry_on=a["carry_on"],
                members={"v144": a["perp_weight"], "options_model": b["perp_weight"]}, options_bars_appended=appended,
                models_cutoff=b["models_cutoff"],
                note=("advisory only; v151 = 0.5 v144 + 0.5 options-flow model set (final weights averaged); UNGOVERNED - apply the "
                      "v110 governor on paper equity; realistic 1m execution OOS 2021-2026: 3.53%/month, full-path DD 19.4% "
                      "(target 0.25 chosen ex post); execution: limits 0.10% better than the 4h open, market at minute 15; not a guarantee"))


if __name__ == "__main__":
    if sys.argv[1] == "freeze":
        freeze(pd.Timestamp(sys.argv[2], tz="UTC") if len(sys.argv) > 2 else pd.Timestamp.now(tz="UTC").floor("D") - pd.Timedelta(days=17))
    else:
        print(json.dumps(advise(), indent=1))
