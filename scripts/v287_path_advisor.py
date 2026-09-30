"""Live path-label member (PA) for the v287 P1 paper pipeline - research output only, no orders.

v287 P1 = 0.8 x CB (v285 D2) + 0.2 x PA, where PA is the v240 O1 A model set (v144 + 4h TradingView + order-level whale flow) trained on
a first-touch (triple-barrier) label instead of the forward return: +1 / -1 when the +- vol42 x sqrt(h) barrier from the next open is
hit first within h bars (stop-first), else the clipped return (v287/v287_path_label_member.py). Features, live data and weights are
exactly the v240 A set's (scripts/v240_advisor.py); only the frozen models differ. Logged as candidate 'v287_PA' in the fast shadow.

  python scripts/v287_path_advisor.py freeze [YYYY-MM-DD]
  python scripts/v287_path_advisor.py advise
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


o1 = _load("v240_advisor_for_v287", ROOT / "scripts/v240_advisor.py")
v233a, v142, SYMS = o1.v233a, o1.v142, o1.SYMS
seta = _load("v104_advisor_v287", ROOT / "scripts/v104_advisor.py")
seta.MODELS = ROOT / "models/frozen/v287_pa_models.pkl"
seta.PORT_TARGET = 0.25
seta._w_lo, seta._w_ls, seta._prep, seta._augment = o1.seta._w_lo, o1.seta._w_ls, o1.seta._prep, o1._aug_a


def freeze(cutoff: pd.Timestamp) -> None:
    v287 = _load("v287_adv", RD / "v287/v287_path_label_member.py")
    v114 = _load("v114_adv_p", RD / "v114/v114_bitstamp_history.py")
    v114.v113.cb_bars = v114.cb_bars_ext
    ext = v114.v113
    ext.v92.load_asset = ext.load_asset_ext
    ohlc = {s: ext.load_asset_ext(s)[0][["open_time", "high", "low"]].drop_duplicates("open_time") for s in SYMS}
    tv = v233a.research_tv()
    times = {s: sorted(tv.loc[tv.sym == s, "t"].unique()) for s in SYMS}
    xf = tv.merge(o1.flow_frame(times, False), on=["t", "sym"], how="left")
    p92 = ext.v92.build().merge(xf, on=["t", "sym"], how="left")
    p103 = seta.v103.build().merge(xf, on=["t", "sym"], how="left")
    p94 = ext.v94.add_targets(v142.add_xs(p92, v142.BASE))
    p94 = v287.relabel(p94, [(f"y{h}", h) for h in seta.v94.HORIZONS], ohlc)  # y42 = the v92 target (h42 model)
    f92 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    p103 = v287.relabel(v142.add_xs(p103, v142.BASE + v142.FLOWX), [(f"y{h}", h) for h in seta.v103.HS], ohlc)
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    models = {"feats92": f92, "feats103": f103, "cutoff": str(cutoff), "frozen_at": datetime.now(timezone.utc).isoformat(),
              "tv": True, "flow": "orders", "label": "path (first touch of +-vol42*sqrt(h), stop-first; v287)"}
    for h in (42,) + seta.v94.HORIZONS:
        models[f"h{h}"], n = seta._fit(p94, f92, f"y{h}", h, cutoff)
        print("pa v92/v94 horizon", h, "rows", n, flush=True)
    for h in seta.v103.HS:
        models[f"f{h}"], n = seta._fit(p103, f103, f"y{h}", h, cutoff)
        print("pa v103 horizon", h, "rows", n, flush=True)
    seta.MODELS.write_bytes(pickle.dumps(models))
    print("saved", seta.MODELS, flush=True)


def advise() -> dict:
    a = seta.advise()
    return dict(candidate="v287_PA", decision_bar_close=a["decision_bar_close"], perp_weight=a["perp_weight"], spot_weight=a["spot_weight"],
                portfolio_scale=a["portfolio_scale"], carry_on=a.get("carry_on"), models_cutoff=a.get("models_cutoff"),
                note="advisory only; path-label member PA of the v287 P1 paper pipeline")


if __name__ == "__main__":
    if sys.argv[1] == "freeze":
        freeze(pd.Timestamp(sys.argv[2], tz="UTC") if len(sys.argv) > 2 else pd.Timestamp("2026-09-11", tz="UTC"))
    else:
        print(json.dumps(advise(), indent=1, default=str))
