"""v145: cross-sectional deviation/rank features for ALL numeric features (registry v145, track C).

Same as v142 but xs_c / xr_c are added for every model feature c except asset, rib and the btc_* context columns
(v114 panel: all v92 features; v103 panel: v92 + flow features). v133 pipeline (vol-forecast sizing with the original
feature sets, tranching, v115 portfolio 15% target, flat-fee scenarios). Reference v142: 2.551/2.33/2.055 (full-path DD
16.26/17.15/18.26); v133: 2.44/2.222/1.95. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v145/v145_xs_all_features.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v142", HERE.parent / "v142" / "v142_cross_sectional_features.py")
v142 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v142)
SKIP = ("asset", "rib")


def main():
    ext = v142.v115.v114.v113
    v142.v115.v114.v113.cb_bars = v142.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    base92 = tuple(c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar") + SKIP and not c.startswith("btc_"))
    p103 = v142.v103.build()
    base103 = tuple(c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") + SKIP and not c.startswith("btc_") and not c.startswith("y"))
    print("xs features", len(base92), len(base103), flush=True)
    v142.BASE = base92
    v142.FLOWX = tuple(c for c in base103 if c not in base92)
    v142.HERE = HERE
    v142.main()
    p = HERE / "v142_result.json"
    res = json.loads(p.read_text())
    res["version"] = "v145"
    res["xs_features"] = {"v114_panel": list(base92), "v103_panel_extra": list(v142.FLOWX)}
    res["reference_v142"] = {"normal": 2.551, "fee_stress": 2.33, "execution_stress": 2.055}
    raw = json.dumps(res, indent=1, default=str)
    (HERE / "v145_result.json").write_text(raw)
    p.unlink()
    print("v145 sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
