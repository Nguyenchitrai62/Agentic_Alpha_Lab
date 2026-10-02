"""v326 step 1: export the pooled 77-coin panel (v317 recipe: v92 + 17 TV + BTC cross features, v94 targets) for the Kaggle GPU sequence member.
Columns: t (4h bar open, UTC), sym, the 43 PT features (asset id included), y18 / y42 / y84 (v94 targets), is_major. float32. No fitting here.
  python research/parallel/rounds/parallel-20260906-r2/v326/v326_export_panel.py
"""
import importlib.util
from pathlib import Path

import numpy as np

RD = Path(__file__).parent.parent
OUT = Path("artifacts/kaggle/v326/ds/pooled_panel.parquet")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v317 = _load("v317_x", RD / "v317/v317_pooled_tv_member.py")
panel, feats, v92, v94 = v317.build_panel(print)
cols = ["t", "sym"] + feats + ["y18", "y42", "y84"]  # "asset" is one of the features
x = panel[cols].copy()
x["is_major"] = x.sym.isin(v92.SYMS).astype("int8")
for c in feats + ["y18", "y42", "y84"]:
    x[c] = x[c].astype(np.float32)
x = x.sort_values(["sym", "t"]).reset_index(drop=True)
OUT.parent.mkdir(parents=True, exist_ok=True)
x.to_parquet(OUT)
(OUT.parent / "features.txt").write_text("\n".join(feats))
print("saved", OUT, x.shape, "features", len(feats))
