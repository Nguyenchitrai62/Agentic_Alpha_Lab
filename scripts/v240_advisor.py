"""Live advisory for the v240 O1 foundation (advisory only, no orders).

v240 O1 = v236 W2 with the whale-vs-retail flow measured on REBUILT taker orders (consecutive aggTrades with the same time and side
merged, so a market order that swept several price levels counts once at its full size). A model set = v144 + TradingView + order-level
flow; B model set = the frozen v233 options + TradingView set. Walk-forward (engine_user trade mode, v218 D2 settings): first four years
5.690%/month with the best worst dev year so far (2.759), 5-year 5.364%/month, most recent year 4.069%/month, DD 19.08% - the 5%/month
gate is NOT passed (most recent year). Live flow = the order-level archive + the closed order-level live buckets of
scripts/aggflow_live.py --orders (kept current by the backend).

  python scripts/v240_advisor.py freeze [YYYY-MM-DD]      # A set only
  python scripts/v240_advisor.py advise
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


v233a = _load("v233_advisor_v240", ROOT / "scripts/v233_advisor.py")
flo = _load("flow_features_adv_o", RD / "v236/flow_features.py")
flo.D = ROOT / "data/raw/aggflow_20260928_orders"
live = _load("aggflow_live_adv_o", ROOT / "scripts/aggflow_live.py")
v142 = v233a.v142
SYMS = v233a.SYMS


def flow_frame(times_by_sym: dict, use_live: bool) -> pd.DataFrame:
    rows = []
    for s in SYMS:
        t = pd.DatetimeIndex(times_by_sym[s])
        fr = live.combined_flow(s, orders=True) if use_live else None
        rows.append(pd.concat([pd.DataFrame({"t": t, "sym": s}), flo.flow_features(s, t, fr).reset_index(drop=True)], axis=1))
    return pd.concat(rows, ignore_index=True)


seta = _load("v104_advisor_v240a", ROOT / "scripts/v104_advisor.py")
seta.MODELS = ROOT / "models/frozen/v240_a_models.pkl"
seta.PORT_TARGET = 0.25
seta._w_lo, seta._w_ls, seta._prep = v233a.seta._w_lo, v233a.seta._w_ls, v233a.seta._prep


def _aug_a(recent):
    r = recent.merge(v233a.live_tv(), on=["t", "sym"], how="left")
    times = {s: sorted(r.loc[r.sym == s, "t"].unique()) for s in SYMS}
    r = r.merge(flow_frame(times, True), on=["t", "sym"], how="left")
    return v142.add_xs(v142.add_xs(r, v142.BASE), v142.FLOWX)


seta._augment = _aug_a


def freeze(cutoff: pd.Timestamp) -> None:
    v114 = _load("v114_adv_o", RD / "v114/v114_bitstamp_history.py")
    v114.v113.cb_bars = v114.cb_bars_ext
    ext = v114.v113
    ext.v92.load_asset = ext.load_asset_ext
    tv = v233a.research_tv()
    times = {s: sorted(tv.loc[tv.sym == s, "t"].unique()) for s in SYMS}
    xf = tv.merge(flow_frame(times, False), on=["t", "sym"], how="left")
    p92 = ext.v92.build().merge(xf, on=["t", "sym"], how="left")
    p103 = seta.v103.build().merge(xf, on=["t", "sym"], how="left")
    p94 = ext.v94.add_targets(v142.add_xs(p92, v142.BASE))
    f92 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    p103 = v142.add_xs(p103, v142.BASE + v142.FLOWX)
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    models = {"feats92": f92, "feats103": f103, "cutoff": str(cutoff), "frozen_at": datetime.now(timezone.utc).isoformat(),
              "tv": True, "flow": "orders"}
    for h in (42,) + seta.v94.HORIZONS:
        models[f"h{h}"], n = seta._fit(p94, f92, f"y{h}", h, cutoff)
        print("a v92/v94 horizon", h, "rows", n, flush=True)
    for h in seta.v103.HS:
        models[f"f{h}"], n = seta._fit(p103, f103, f"y{h}", h, cutoff)
        print("a v103 horizon", h, "rows", n, flush=True)
    seta.MODELS.write_bytes(pickle.dumps(models))
    print("saved", seta.MODELS, flush=True)


def advise() -> dict:
    appended = v233a.upd.update()
    a, b = seta.advise(), v233a.setb.advise()
    syms = sorted(set(a["perp_weight"]) | set(b["perp_weight"]))
    perp = {s: round(0.5 * a["perp_weight"].get(s, 0.0) + 0.5 * b["perp_weight"].get(s, 0.0), 4) for s in syms}
    spot = {s: round(0.5 * a["spot_weight"].get(s, 0.0) + 0.5 * b["spot_weight"].get(s, 0.0), 4) for s in syms}
    return dict(candidate="v240_O1", decision_bar_close=a["decision_bar_close"], perp_weight=perp, spot_weight=spot,
                portfolio_scale=round(0.5 * a["portfolio_scale"] + 0.5 * b["portfolio_scale"], 3), carry_on=a["carry_on"],
                members={"v144_tv_orderflow": a["perp_weight"], "options_tv": b["perp_weight"]}, options_bars_appended=appended,
                models_cutoff=a["models_cutoff"],
                note=("advisory only; v240 O1 = T3 + order-level whale flow in the A set; walk-forward 5y 5.364%/month, most recent year "
                      "4.069%/month, DD 19.08%: the 5%/month gate is NOT passed; UNGOVERNED - apply the governor; not a guarantee"))


if __name__ == "__main__":
    if sys.argv[1] == "freeze":
        freeze(pd.Timestamp(sys.argv[2], tz="UTC") if len(sys.argv) > 2 else pd.Timestamp.now(tz="UTC").floor("D") - pd.Timedelta(days=17))
    else:
        print(json.dumps(advise(), indent=1))
