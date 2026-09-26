"""v163: EMA smoothing of every model prediction before the weight formulas, v154 ensemble (registry v163, track C).

In all three members (A = v144, B = options, D = Coinbase premium), each OOS prediction frame (v92 LO, v94 LS, v103 LS)
gets pred := EMA over the asset's own time-ordered predictions with span 6 (one day of 4h bars, adjust=False) before the
v125/v129 weight pipeline (causal: uses current and past predictions only). Everything else = v154 ((A+B+D)/3, v144
realistic engine rows). Reference v154: 3.515/19.15. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v163/v163_prediction_smoothing.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
SPAN = 6


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def smooth(df):
    d = df.sort_values(["sym", "t"]).copy()
    d["pred"] = d.groupby("sym")["pred"].transform(lambda s: s.ewm(span=SPAN, adjust=False).mean())
    return d


def fresh_v144(tag):
    v144 = _load(f"v144_{tag}", "v144/v144_deploy_v3.py")
    r_lo, r_ls = v144.v125.raw_lo, v144.v125.raw_ls
    v144.v125.raw_lo = lambda df: r_lo(smooth(df))
    v144.v125.raw_ls = lambda df: r_ls(smooth(df))
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    v144.v115.v114.v113.v92.load_asset = v144.v115.v114.v113.load_asset_ext
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
    v150 = _load("v150_s", "v150/v150_options_flow.py")
    _, B = with_extra(fresh_v144("B"), v150.opt_features(), v150.OPT)
    v111 = _load("v111_s", "v111/v111_coinbase_premium.py")
    cbf = v111.add_cb(A_mod.v103.build()[["t", "sym"]]).drop(columns="sym").drop_duplicates("t")
    _, D = with_extra(fresh_v144("D"), cbf, v111.CB)
    idx = A.index.union(B.index).union(D.index)
    books = sum(X.reindex(idx).fillna(0.0) for X in (A, B, D)) / 3
    out = {"version": "v163", "ema_span": SPAN, **A_mod.simulate(p103, books)}
    out["reference_v154"] = {"t25": (3.515, 19.15)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v163_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
