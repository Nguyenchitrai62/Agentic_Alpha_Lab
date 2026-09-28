"""Live advisory for the v233 T3 foundation (advisory only, no orders).

v233 T3 = the v151 structure (0.5 v144 model set + 0.5 options-flow model set) with the 17 TradingView indicators
(research/parallel/rounds/parallel-20260906-r2/v231/tv_indicators.py, standard parameters) as extra features in every return
model (v92 / v94 / v103 panels, before the v142 cross-sectional step; the v133 vol models are unchanged). Walk-forward
(engine_user trade mode, v218 D2 settings): first four years 5.485%/month, 5-year 5.156%/month, most recent year 3.851%/month,
DD 18.41% - the 5%/month gate is NOT passed (most recent year). Research annual + quarterly schedules collapse to one frozen set here
(retrain quarterly in live use).
Live indicators are computed from the last 1500 closed 4h klines of each major (Binance USD-M): identical to the full-history values
for the recent rows (checked: max difference 0 over the last 50 rows with 1000 or 1500 bars).

  python scripts/v233_advisor.py freeze [YYYY-MM-DD]
  python scripts/v233_advisor.py advise
"""

from __future__ import annotations

import importlib.util
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tvm = _load("tv_indicators_adv", RD / "v231/tv_indicators.py")
v151a = _load("v151_advisor_v233", ROOT / "scripts/v151_advisor.py")
v142, v150, upd = v151a.v142, v151a.v150, v151a.upd
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
_TV_CACHE: dict = {}


def live_tv() -> pd.DataFrame:
    """TV features of the last 1500 closed 4h bars per major (rows keyed by the bar open, as the panels)."""
    if "df" in _TV_CACHE:
        return _TV_CACHE["df"]
    from agentic_alpha_lab.data.binance_usdm import BASE_URL
    s, rows = requests.Session(), []
    now = pd.Timestamp.now(tz="UTC")
    for sym in SYMS:
        k = s.get(f"{BASE_URL}/fapi/v1/klines", params={"symbol": sym, "interval": "4h", "limit": 1500}, timeout=60).json()
        b = pd.DataFrame(k, columns=["open_time", "open", "high", "low", "close", "volume", "close_time", "qv", "n", "tbv", "tbq", "x"])
        b["open_time"] = pd.to_datetime(b["open_time"], unit="ms", utc=True)
        b = b[b["open_time"] + pd.Timedelta(hours=4) <= now].reset_index(drop=True)  # closed bars only
        for c in ("open", "high", "low", "close", "volume"):
            b[c] = b[c].astype(float)
        rows.append(pd.concat([pd.DataFrame({"t": b["open_time"], "sym": sym}), tvm.tv_features(b)], axis=1))
    _TV_CACHE["df"] = pd.concat(rows, ignore_index=True)
    return _TV_CACHE["df"]


def research_tv() -> pd.DataFrame:
    v231 = _load("v231_adv", RD / "v231/v231_quality_features.py")
    v114 = _load("v114_adv_tv", RD / "v114/v114_bitstamp_history.py")
    v114.v113.cb_bars = v114.cb_bars_ext
    v114.v113.v92.load_asset = v114.v113.load_asset_ext
    return v231.extra_features(("tv",), v114.v113.v92.load_asset, None)


# model set A: v144 + TV
seta = _load("v104_advisor_v233a", ROOT / "scripts/v104_advisor.py")
seta.MODELS = ROOT / "models/frozen/v233_a_models.pkl"
seta.PORT_TARGET = 0.25
seta._w_lo, seta._w_ls, seta._prep = v151a.v144a.base._w_lo, v151a.v144a.base._w_ls, v151a.v144a.base._prep
# model set B: options + TV
setb = _load("v104_advisor_v233b", ROOT / "scripts/v104_advisor.py")
setb.MODELS = ROOT / "models/frozen/v233_b_models.pkl"
setb.PORT_TARGET = 0.25
setb._w_lo, setb._w_ls, setb._prep = seta._w_lo, seta._w_ls, seta._prep


def _aug_a(recent):
    r = recent.merge(live_tv(), on=["t", "sym"], how="left")
    return v142.add_xs(v142.add_xs(r, v142.BASE), v142.FLOWX)


def _aug_b(recent):
    r = recent.merge(v150.opt_features(), on="t", how="left").merge(live_tv(), on=["t", "sym"], how="left")
    return v142.add_xs(v142.add_xs(r, v142.BASE), v142.FLOWX)


seta._augment, setb._augment = _aug_a, _aug_b


def freeze(cutoff: pd.Timestamp) -> None:
    v114 = _load("v114_adv", RD / "v114/v114_bitstamp_history.py")
    v114.v113.cb_bars = v114.cb_bars_ext
    ext = v114.v113
    ext.v92.load_asset = ext.load_asset_ext
    tv, of = research_tv(), v150.opt_features()
    base92, base103 = ext.v92.build(), seta.v103.build()
    for name, mset, extra in (("a", seta, None), ("b", setb, of)):
        p92, p103 = base92.copy(), base103.copy()
        if extra is not None:
            p92, p103 = p92.merge(extra, on="t", how="left"), p103.merge(extra, on="t", how="left")
        p92, p103 = p92.merge(tv, on=["t", "sym"], how="left"), p103.merge(tv, on=["t", "sym"], how="left")
        p94 = ext.v94.add_targets(v142.add_xs(p92, v142.BASE))
        f92 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
        p103 = v142.add_xs(p103, v142.BASE + v142.FLOWX)
        f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
        models = {"feats92": f92, "feats103": f103, "cutoff": str(cutoff), "frozen_at": datetime.now(timezone.utc).isoformat(),
                  "tv": True, "options": extra is not None}
        for h in (42,) + mset.v94.HORIZONS:
            models[f"h{h}"], n = mset._fit(p94, f92, f"y{h}", h, cutoff)
            print(name, "v92/v94 horizon", h, "rows", n, flush=True)
        for h in mset.v103.HS:
            models[f"f{h}"], n = mset._fit(p103, f103, f"y{h}", h, cutoff)
            print(name, "v103 horizon", h, "rows", n, flush=True)
        mset.MODELS.write_bytes(pickle.dumps(models))
        print("saved", mset.MODELS, flush=True)


def advise() -> dict:
    appended = upd.update()
    a, b = seta.advise(), setb.advise()
    syms = sorted(set(a["perp_weight"]) | set(b["perp_weight"]))
    perp = {s: round(0.5 * a["perp_weight"].get(s, 0.0) + 0.5 * b["perp_weight"].get(s, 0.0), 4) for s in syms}
    spot = {s: round(0.5 * a["spot_weight"].get(s, 0.0) + 0.5 * b["spot_weight"].get(s, 0.0), 4) for s in syms}
    return dict(candidate="v233_T3", decision_bar_close=a["decision_bar_close"], perp_weight=perp, spot_weight=spot,
                portfolio_scale=round(0.5 * a["portfolio_scale"] + 0.5 * b["portfolio_scale"], 3), carry_on=a["carry_on"],
                members={"v144_tv": a["perp_weight"], "options_tv": b["perp_weight"]}, options_bars_appended=appended,
                models_cutoff=b["models_cutoff"],
                note=("advisory only; v233 T3 = v151 structure + TradingView indicator features; walk-forward 5y 5.156%/month, most "
                      "recent year 3.851%/month, DD 18.41%: the 5%/month gate is NOT passed; UNGOVERNED - apply the governor; not a guarantee"))


if __name__ == "__main__":
    if sys.argv[1] == "freeze":
        freeze(pd.Timestamp(sys.argv[2], tz="UTC") if len(sys.argv) > 2 else pd.Timestamp.now(tz="UTC").floor("D") - pd.Timedelta(days=17))
    else:
        print(json.dumps(advise(), indent=1))
