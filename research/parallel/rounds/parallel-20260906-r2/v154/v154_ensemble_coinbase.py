"""v154: information-diverse ensemble with the Coinbase premium as third member (registry v154).

A = v144 books; B = v150 options-flow books (as in v151); D = v144 builder with the v111 Coinbase-premium market features
(cb_btc_dev, cb_btc_z, cb_btc_chg, cb_eth_z, cb_eth_chg; Coinbase 1h close vs Binance spot 4h close, known at the bar
close) merged on t into the v114 and v103 panels before the v142 xs step (no xs versions; vol models exclude them).
Books = (A + B + D)/3, v144 realistic engine rows (0.15 ungoverned, 0.20/0.25 governed, 10 bps 1m execution).
Reference v151 (A+B)/2: 3.526/19.41. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v154/v154_ensemble_coinbase.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def books_coinbase():
    v144 = _load("v144_cb", "v144/v144_deploy_v3.py")
    v111 = _load("v111_cb", "v111/v111_coinbase_premium.py")
    cbf = v111.add_cb(v144.v103.build()[["t", "sym"]]).drop(columns="sym").drop_duplicates("t")
    ext, v103 = v144.v115.v114.v113, v144.v103
    b92, b103 = ext.v92.build, v103.build
    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in v111.CB], anchors, emb)
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    ext.v92.build = lambda: b92().merge(cbf, on="t", how="left")
    v103.build = lambda: b103().merge(cbf, on="t", how="left")
    return v144.books_v142()


def main():
    v144 = _load("v144", "v144/v144_deploy_v3.py")
    v151 = _load("v151", "v151/v151_info_ensemble.py")
    p103, A = v144.books_v142()
    _, B = v151.books_with_options()
    _, D = books_coinbase()
    idx = A.index.union(B.index).union(D.index)
    books = (A.reindex(idx).fillna(0.0) + B.reindex(idx).fillna(0.0) + D.reindex(idx).fillna(0.0)) / 3
    out = {"version": "v154", **v144.simulate(p103, books)}
    out["reference_v151"] = {"t25": (3.526, 19.41)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v154_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
