"""v158: options member with BTC + ETH option flow, inside the v154 three-member ensemble (registry v158).

B' = v144 builder with the five v150 BTC options-flow features plus the same five computed from ETH option trades
(data/raw/deribit_opt_20260926/ETH_options_4h.parquet, identical definitions, prefixed eth_), merged on t before the v142
xs step (no xs versions; vol models exclude them). Books = (A + B' + D)/3 with A = v144, D = v154 Coinbase member; v144
engine rows (0.15 ungoverned, 0.20/0.25 governed). Reference v154 (A + B + D)/3: 3.515/19.15. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v158/v158_eth_options_member.py
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


def books_btc_eth_options():
    v150 = _load("v150_be", "v150/v150_options_flow.py")
    v144, OPT = v150.v144, v150.OPT
    btc = v150.opt_features()
    src = Path(v150.__file__).read_text()
    code = src[src.index("def opt_features"):src.index("def main")].replace("BTC_options_4h.parquet", "ETH_options_4h.parquet")
    ns = dict(v150.__dict__)
    exec(code, ns)
    eth = ns["opt_features"]().rename(columns={c: f"eth_{c}" for c in OPT})
    feats = btc.merge(eth, on="t", how="outer")
    allc = list(OPT) + [f"eth_{c}" for c in OPT]
    ext, v103 = v144.v115.v114.v113, v144.v103
    b92, b103 = ext.v92.build, v103.build
    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in allc], anchors, emb)
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    ext.v92.build = lambda: b92().merge(feats, on="t", how="left")
    v103.build = lambda: b103().merge(feats, on="t", how="left")
    return v144.books_v142()


def main():
    v144 = _load("v144", "v144/v144_deploy_v3.py")
    v154 = _load("v154", "v154/v154_ensemble_coinbase.py")
    p103, A = v144.books_v142()
    _, B2 = books_btc_eth_options()
    _, D = v154.books_coinbase()
    idx = A.index.union(B2.index).union(D.index)
    books = sum(X.reindex(idx).fillna(0.0) for X in (A, B2, D)) / 3
    out = {"version": "v158", **v144.simulate(p103, books)}
    out["reference_v154"] = {"t25": (3.515, 19.15)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v158_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
