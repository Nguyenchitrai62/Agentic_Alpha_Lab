"""v157: four-member information ensemble - v154 members + a macro member (registry v157, track B).

F = v144 builder with the audited W7 macro features (agentic_alpha_lab.patterns.macro.compute: SPY/QQQ/VIX/DXY/TNX/GLD
daily closes known after 22:00 UTC, as-of joined to each bar close; distances to SMA50/200, 20d returns/vol, risk-on score,
BTC-QQQ 60d correlation) computed on the BTC 4h bars (close_time = t + 4h - 1ms) and merged on t into the v114 and v103
panels before the v142 xs step (no xs versions; vol models exclude them). Books = (A + B + D + F)/4 with A = v144,
B = v150 options member, D = v154 Coinbase member; v144 engine rows. Reference v154: 3.515/19.15; compare with v156
(DVOL member). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v157/v157_ensemble_macro.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def books_macro():
    from agentic_alpha_lab.patterns import macro
    v144 = _load("v144_mac", "v144/v144_deploy_v3.py")
    ext, v103 = v144.v115.v114.v113, v144.v103
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    b92, b103 = ext.v92.build, v103.build
    p = b92()
    ts = pd.Series(sorted(p["t"].unique()))
    bars = pd.DataFrame({"t": ts, "close_time": ts + pd.Timedelta(hours=4) - pd.Timedelta(milliseconds=1)})
    mf = macro.compute(bars).reset_index(drop=True)
    cols = [c for c in mf.columns if c not in ("t", "close_time", "open_time")]
    feats = pd.concat([bars[["t"]], mf[cols]], axis=1)
    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in cols], anchors, emb)
    ext.v92.build = lambda: b92().merge(feats, on="t", how="left")
    v103.build = lambda: b103().merge(feats, on="t", how="left")
    print("macro features", len(cols), flush=True)
    return v144.books_v142()


def main():
    v144 = _load("v144", "v144/v144_deploy_v3.py")
    v151 = _load("v151", "v151/v151_info_ensemble.py")
    v154 = _load("v154", "v154/v154_ensemble_coinbase.py")
    p103, A = v144.books_v142()
    _, B = v151.books_with_options()
    _, D = v154.books_coinbase()
    _, F = books_macro()
    idx = A.index.union(B.index).union(D.index).union(F.index)
    books = sum(X.reindex(idx).fillna(0.0) for X in (A, B, D, F)) / 4
    out = {"version": "v157", **v144.simulate(p103, books)}
    out["reference_v154"] = {"t25": (3.515, 19.15)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v157_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
