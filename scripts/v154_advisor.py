"""Live advisory for the v154 candidate (advisory only, no orders).

v154 = (v144 + options-flow model set + Coinbase-premium model set) / 3. Members: scripts/v144_advisor.py, the options
model set of scripts/v151_advisor.py, and a Coinbase-premium model set frozen here (v111 features cb_btc_dev, cb_btc_z,
cb_btc_chg, cb_eth_z, cb_eth_chg merged before the v142 xs step, v133 vol models, tranching, target 0.25).
Approximation vs research: the research blend averaged books before the portfolio vol scale; here the three final weight
vectors are averaged. Weights are UNGOVERNED: apply the v110 drawdown governor on paper equity. Execution (v135): limits
0.10% better than the 4h open, market fallback at minute 15. Each run first appends new Coinbase 1h / Binance spot 4h
candles (scripts/coinbase_spot_update.py) and new Deribit option bars (via the v151 advisor).

  python scripts/v154_advisor.py freeze [YYYY-MM-DD]   # Coinbase model set only
  python scripts/v154_advisor.py advise
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


v151a = _load("v151_advisor_v154", ROOT / "scripts/v151_advisor.py")
cbu = _load("coinbase_spot_update", ROOT / "scripts/coinbase_spot_update.py")
v111 = _load("v111", RD / "v111/v111_coinbase_premium.py")
v144a = v151a.v144a
v142 = v151a.v142
cbm = _load("v104_advisor_v154cb", ROOT / "scripts/v104_advisor.py")
cbm.MODELS = ROOT / "models/frozen/v154_cb_models.pkl"
cbm.PORT_TARGET = 0.25
cbm._w_lo, cbm._w_ls, cbm._prep = v144a.base._w_lo, v144a.base._w_ls, v144a.base._prep


def _cb_table(times: pd.Series) -> pd.DataFrame:
    return v111.add_cb(pd.DataFrame({"t": times, "sym": "X"})).drop(columns="sym").drop_duplicates("t")


def _augment_cb(recent):
    r = recent.merge(_cb_table(pd.Series(recent["t"].unique())), on="t", how="left")
    return v142.add_xs(v142.add_xs(r, v142.BASE), v142.FLOWX)


cbm._augment = _augment_cb


def freeze(cutoff: pd.Timestamp) -> None:
    v114 = _load("v114", RD / "v114/v114_bitstamp_history.py")
    v114.v113.cb_bars = v114.cb_bars_ext
    ext = v114.v113
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    cbf = _cb_table(pd.Series(p92["t"].unique()))
    p94 = ext.v94.add_targets(v142.add_xs(p92.merge(cbf, on="t", how="left"), v142.BASE))
    f92 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    p103 = v142.add_xs(cbm.v103.build().merge(cbf, on="t", how="left"), v142.BASE + v142.FLOWX)
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    models = {"feats92": f92, "feats103": f103, "cutoff": str(cutoff), "frozen_at": datetime.now(timezone.utc).isoformat(), "coinbase": True}
    for h in (42,) + cbm.v94.HORIZONS:
        models[f"h{h}"], n = cbm._fit(p94, f92, f"y{h}", h, cutoff)
        print("v92/v94 horizon", h, "rows", n, flush=True)
    for h in cbm.v103.HS:
        models[f"f{h}"], n = cbm._fit(p103, f103, f"y{h}", h, cutoff)
        print("v103 horizon", h, "rows", n, flush=True)
    cbm.MODELS.write_bytes(pickle.dumps(models))
    print("saved", cbm.MODELS)


def advise() -> dict:
    appended = cbu.update()
    ab = v151a.advise()                      # updates Deribit bars; contains v144 and options members
    a, b = ab["members"]["v144"], ab["members"]["options_model"]
    d = cbm.advise()
    syms = sorted(set(a) | set(b) | set(d["perp_weight"]))
    perp = {s: round((a.get(s, 0.0) + b.get(s, 0.0) + d["perp_weight"].get(s, 0.0)) / 3, 4) for s in syms}
    spot = {s: round((2 * ab["spot_weight"].get(s, 0.0) + d["spot_weight"].get(s, 0.0)) / 3, 4) for s in syms}
    return dict(candidate="v154_deploy_v5", decision_bar_close=ab["decision_bar_close"], perp_weight=perp, spot_weight=spot,
                portfolio_scale=round((2 * ab["portfolio_scale"] + d["portfolio_scale"]) / 3, 3), carry_on=ab["carry_on"],
                members={"v144": a, "options_model": b, "coinbase_model": d["perp_weight"]}, data_appended=appended,
                models_cutoff=d["models_cutoff"],
                note=("advisory only; v154 = (v144 + options + Coinbase-premium model sets)/3 (final weights averaged); UNGOVERNED - "
                      "apply the v110 governor on paper equity; realistic 1m execution OOS 2021-2026: 3.52%/month, full-path DD "
                      "19.2%, hidden year +56% (target 0.25 chosen ex post); execution: limits 0.10% better than the 4h open, market "
                      "at minute 15; not a guarantee"))


if __name__ == "__main__":
    if sys.argv[1] == "freeze":
        freeze(pd.Timestamp(sys.argv[2], tz="UTC") if len(sys.argv) > 2 else pd.Timestamp.now(tz="UTC").floor("D") - pd.Timedelta(days=17))
    else:
        print(json.dumps(advise(), indent=1))
