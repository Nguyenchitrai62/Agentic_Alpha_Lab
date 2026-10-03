"""Compare prep_idx at s = 0 with engine_user.prepare on the dev rows (inputs only; nothing is simulated)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pof = _load("pof", Path(__file__).parent / "phase_offset_full.py")
pod = _load("pod", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
v221 = _load("v221c", RD / "v221/v221_grid_hysteresis.py")
eu = v221.eu
b154, opens_std = eu.er.v154_books()
std = eu.prepare(b154, opens_std)
idx = b154.index[b154.index <= pof.DEV1 + pd.Timedelta(hours=4)]
opens, mine = pof.prep_idx(pod.minutes(), idx, 0, list(b154.columns))
n = int((idx < pof.DEV1).sum())
for k in ("O", "H", "L", "C", "sig4", "o1", "o2", "settle"):
    a, b = np.asarray(std[k][:n], float), np.asarray(mine[k][:n], float)
    same = (a == b) | (np.isnan(a) & np.isnan(b))
    bad = np.argwhere(~same)
    print(k, "mismatches", int((~same).sum()), "max abs rel", float(np.nanmax(np.abs(a - b) / np.abs(a))) if (~same).any() else 0.0,
          "first rows", sorted({int(r[0]) for r in bad})[:8], [str(idx[int(r[0])]) for r in bad[:3]])
o_std = opens_std.reindex(idx[:n])[list(b154.columns)]
d = (o_std - opens.iloc[:n]).abs() / o_std
print("opens: rows differing", int((d > 0).any(axis=1).sum()), d.max().to_dict())
print(d[(d > 0).any(axis=1)].head(10))
