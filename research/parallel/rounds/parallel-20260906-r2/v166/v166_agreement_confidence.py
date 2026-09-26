"""v166: confidence sizing by agreement between the three information-set members of v154 (registry v166).

For every asset and 4h bar, the three members' final book weights (A = v144, B = options, D = Coinbase premium; each
already vol-targeted) give signs s_A, s_B, s_D (sign of the member's weight, 0 if flat). Agreement multiplier per asset/bar:
m = 1.3 if all three non-zero signs agree (and at least two members are non-zero), 0.6 if the non-zero signs disagree,
1.0 otherwise. Ensemble weight = m * (A + B + D)/3, per asset (the multiplier is computed from same-bar weights only).
Everything else = v154 (v144 realistic engine rows; the portfolio vol target and governor apply on top). Reference v154:
3.515/19.15 (0.25). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v166/v166_agreement_confidence.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def agreement(A, B, D):
    S = np.stack([np.sign(X.to_numpy()) for X in (A, B, D)])  # members x bars x assets
    nz = (S != 0).sum(axis=0)
    pos, neg = (S > 0).sum(axis=0), (S < 0).sum(axis=0)
    m = np.ones(nz.shape)
    m[(nz >= 2) & ((pos == nz) | (neg == nz))] = 1.3
    m[(pos > 0) & (neg > 0)] = 0.6
    return m


def main():
    v144 = _load("v144", "v144/v144_deploy_v3.py")
    v151 = _load("v151", "v151/v151_info_ensemble.py")
    v154 = _load("v154", "v154/v154_ensemble_coinbase.py")
    p103, A = v144.books_v142()
    _, B = v151.books_with_options()
    _, D = v154.books_coinbase()
    idx = A.index.union(B.index).union(D.index)
    cols = A.columns
    A, B, D = (X.reindex(index=idx, columns=cols).fillna(0.0) for X in (A, B, D))
    m = agreement(A, B, D)
    books = (A + B + D) / 3 * m
    share = {"agree_1.3": round(float((m == 1.3).mean()), 3), "disagree_0.6": round(float((m == 0.6).mean()), 3)}
    print("multiplier shares", share, flush=True)
    out = {"version": "v166", "multiplier_shares": share, **v144.simulate(p103, books)}
    out["reference_v154"] = {"t25": (3.515, 19.15)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v166_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
