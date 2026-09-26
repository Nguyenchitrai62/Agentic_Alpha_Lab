"""v153: three-information-set ensemble: v144 books + v150 options books + positioning books (registry v153).

A = v144.books_v142(); B = the v150 builder (Deribit options-flow features in all return models); C = the v144 builder
with the v139 absolute positioning features (oi_chg6, oi_chg42, oi_z, top_ls, top_ls_chg6, top_ls_z, crowd_ls_z,
taker_ls6; last metrics row <= bar close - 5 min) added to the v103 panel only (vol models on original feature sets).
Books = (A + B + C) / 3, then the v144 realistic engine (10 bps 1m execution, 20% governor). Rows 0.15 ungoverned /
0.20 / 0.25 governed (primary). Reference v151 (A+B)/2: 3.526/19.41. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v153/v153_three_info_ensemble.py
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


def books_positioning():
    v144 = _load("v144_pos", "v144/v144_deploy_v3.py")
    v139 = _load("v139_pos", "v139/v139_positioning.py")
    v103 = v144.v103
    b103 = v103.build

    def build():
        p = b103()
        pos = pd.concat([v139.pos_features(g.sort_values("t"), s) for s, g in p.groupby("sym")], ignore_index=True)
        return p.merge(pos, on=["t", "sym"], how="left")

    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in v139.POS], anchors, emb)
    v103.build = build
    return v144.books_v142()


def main():
    v144 = _load("v144", "v144/v144_deploy_v3.py")
    v151 = _load("v151", "v151/v151_info_ensemble.py")
    p103, A = v144.books_v142()
    _, B = v151.books_with_options()
    _, C = books_positioning()
    idx = A.index.union(B.index).union(C.index)
    books = (A.reindex(idx).fillna(0.0) + B.reindex(idx).fillna(0.0) + C.reindex(idx).fillna(0.0)) / 3
    out = {"version": "v153", **v144.simulate(p103, books)}
    out["reference_v151"] = {"t25": (3.526, 19.41)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v153_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
