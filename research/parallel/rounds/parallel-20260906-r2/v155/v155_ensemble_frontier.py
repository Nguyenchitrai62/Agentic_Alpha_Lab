"""v155: 20%-governor frontier of the v154 three-member ensemble (registry v155, track C).

v154 books ((A + B + D)/3: base, options-flow, Coinbase-premium members) in the v144 realistic engine with the unchanged
20% governor at portfolio targets 0.25 (= v154 primary), 0.28 and 0.30. Reporting frontier; any target choice is ex post.
Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v155/v155_ensemble_frontier.py
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


def main():
    v144 = _load("v144", "v144/v144_deploy_v3.py")
    v151 = _load("v151", "v151/v151_info_ensemble.py")
    v154 = _load("v154", "v154/v154_ensemble_coinbase.py")
    p103, A = v144.books_v142()
    _, B = v151.books_with_options()
    _, D = v154.books_coinbase()
    idx = A.index.union(B.index).union(D.index)
    books = (A.reindex(idx).fillna(0.0) + B.reindex(idx).fillna(0.0) + D.reindex(idx).fillna(0.0)) / 3
    v144.ROWS = (("t25_governed", 0.25, True), ("primary_t28_governed", 0.28, True), ("t30_governed", 0.30, True))
    out = {"version": "v155", **v144.simulate(p103, books)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v155_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
