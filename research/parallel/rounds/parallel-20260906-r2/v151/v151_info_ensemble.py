"""v151: information-diverse ensemble - average of the v144 books and the v150 (options-flow) books (registry v151).

Books A = v144.books_v142() (no options features); books B = the same builder with the v150 modifications (Deribit
options-flow features added to all return models, vol models unchanged). Portfolio books = 0.5 * A + 0.5 * B (both
already scaled by their own book vol targets), then the v144 realistic engine (10 bps limits on 1m data, governor).
Rows 0.15 ungoverned / 0.20 / 0.25 governed (primary). References: v144 3.374/19.63 (hidden +41.3%), v150 3.465/19.15
(hidden +26.8%). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v151/v151_info_ensemble.py
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


def books_with_options():
    v150 = _load("v150", "v150/v150_options_flow.py")
    v144, OPT = v150.v144, v150.OPT
    feats = v150.opt_features()
    ext, v103 = v144.v115.v114.v113, v144.v103
    b92, b103 = ext.v92.build, v103.build
    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in OPT], anchors, emb)
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    ext.v92.build = lambda: b92().merge(feats, on="t", how="left")
    v103.build = lambda: b103().merge(feats, on="t", how="left")
    return v144.books_v142()


def main():
    v144 = _load("v144", "v144/v144_deploy_v3.py")
    p103, A = v144.books_v142()
    _, B = books_with_options()
    idx = A.index.union(B.index)
    books = 0.5 * A.reindex(idx).fillna(0.0) + 0.5 * B.reindex(idx).fillna(0.0)
    out = {"version": "v151", "corr_book_returns_proxy": round(float((A.reindex(idx).fillna(0) * B.reindex(idx).fillna(0)).sum(axis=1).mean()), 6),
           **v144.simulate(p103, books)}
    out["references"] = {"v144_t25": (3.374, 19.63, "hidden +41.3%"), "v150_t25": (3.465, 19.15, "hidden +26.8%")}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v151_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
