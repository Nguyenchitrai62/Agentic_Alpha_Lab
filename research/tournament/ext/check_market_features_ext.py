"""Overlap check: ext/market_features_ext.parquet vs context/market_features.parquet on rows keyed by (sym, j, r)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import harness as H  # noqa: E402

sys.path.insert(0, str(HERE))
import harness5 as H5  # noqa: E402

out = {}
mo = pd.read_parquet(HERE.parent / "context/market_features.parquet")
mn = pd.read_parquet(HERE / "market_features_ext.parquet")
do = H.load()
dn = H5.load()
out["old_rows"], out["new_rows"] = len(mo), len(mn)
out["old_load_rows"], out["new_load_rows"] = len(do), len(dn)
assert len(mo) == len(do) and len(mn) == len(dn), (len(mo), len(do), len(mn), len(dn))
out["new_align_T_sym"] = bool((mn["T"].to_numpy() == dn["T"].to_numpy()).all() and (mn.sym.to_numpy() == dn.sym.to_numpy()).all())
ko = pd.DataFrame({"sym": do.sym.to_numpy(), "j": do.j.to_numpy(), "r": do.r.to_numpy(), "i_old": np.arange(len(do))})
kn = pd.DataFrame({"sym": dn.sym.to_numpy(), "j": dn.j.to_numpy(), "r": dn.r.to_numpy(), "i_new": np.arange(len(dn))})
m = ko.merge(kn, on=["sym", "j", "r"], how="left", indicator=True)
out["old_rows_missing_in_new"] = int((m._merge == "left_only").sum())
both = m[m._merge == "both"]
cols = [c for c in mo.columns if c not in ("T", "sym")]
d = {}
for c in cols:
    x = mo[c].to_numpy(float)[both.i_old.to_numpy()]
    y = mn[c].to_numpy(float)[both.i_new.to_numpy()]
    dd = x - y
    d[c] = dict(max_abs=float(np.nanmax(np.abs(dd))) if np.isfinite(dd).any() else 0.0,
                nan_mismatch=int((np.isnan(x) != np.isnan(y)).sum()))
out["diff"] = d
out["worst_max_abs"] = float(max(v["max_abs"] for v in d.values()))
out["total_nan_mismatch"] = int(sum(v["nan_mismatch"] for v in d.values()))
(HERE / "market_check.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
