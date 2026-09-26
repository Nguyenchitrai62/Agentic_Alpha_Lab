"""v162: monotone (non-decreasing) constraints on trend features in the 7-day models of the v154 ensemble (registry v162).

In every member (A = v144, B = options, D = Coinbase premium) the v92 long-only model and the three v94 horizon models are
HistGradientBoostingRegressor with monotonic_cst = +1 (prediction non-decreasing) for the trend features present:
ret6 ret42 ret90 ret180 ret540, snr6 snr42 snr90 snr180 snr540, ema20 ema200, d50 d200, rib, btc_ret42 btc_ret180
btc_rib btc_snr42; all other features unconstrained. The v103 short-horizon models are unchanged (reversal allowed).
Everything else = v154 ((A + B + D)/3, v144 realistic engine rows). Reference v154: 3.515/19.15. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v162/v162_monotone_trend.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
TREND = ("ret6", "ret42", "ret90", "ret180", "ret540", "snr6", "snr42", "snr90", "snr180", "snr540", "ema20", "ema200",
         "d50", "d200", "rib", "btc_ret42", "btc_ret180", "btc_rib", "btc_snr42")


class MonoHGB(HistGradientBoostingRegressor):
    def fit(self, X, y, sample_weight=None):
        self.monotonic_cst = {c: 1 for c in TREND if c in X.columns}
        return super().fit(X, y, sample_weight=sample_weight)


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fresh_v144(tag):
    v144 = _load(f"v144_{tag}", "v144/v144_deploy_v3.py")
    ext = v144.v115.v114.v113
    ext.v92.HistGradientBoostingRegressor = MonoHGB
    ext.v94.HistGradientBoostingRegressor = MonoHGB
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    return v144


def with_extra(v144, feats, excl):
    ext, v103 = v144.v115.v114.v113, v144.v103
    b92, b103 = ext.v92.build, v103.build
    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in excl], anchors, emb)
    ext.v92.build = lambda: b92().merge(feats, on="t", how="left")
    v103.build = lambda: b103().merge(feats, on="t", how="left")
    return v144.books_v142()


def main():
    A_mod = fresh_v144("A")
    p103, A = A_mod.books_v142()
    v150 = _load("v150_m", "v150/v150_options_flow.py")
    _, B = with_extra(fresh_v144("B"), v150.opt_features(), v150.OPT)
    v111 = _load("v111_m", "v111/v111_coinbase_premium.py")
    cbf = v111.add_cb(A_mod.v103.build()[["t", "sym"]]).drop(columns="sym").drop_duplicates("t")
    _, D = with_extra(fresh_v144("D"), cbf, v111.CB)
    idx = A.index.union(B.index).union(D.index)
    books = sum(X.reindex(idx).fillna(0.0) for X in (A, B, D)) / 3
    out = {"version": "v162", "trend_features": TREND, **A_mod.simulate(p103, books)}
    out["reference_v154"] = {"t25": (3.515, 19.15)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v162_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
