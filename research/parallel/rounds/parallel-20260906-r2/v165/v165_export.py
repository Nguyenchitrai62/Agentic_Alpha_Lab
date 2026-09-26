"""v165 step 1: export the full-information panel for the Kaggle deep tabular ensemble.

Rows: the audited v103 panel (5 majors, 4h, spot 2017 prefix + USD-M, v92 + flow features, BTC context) with
- v142 cross-sectional features (xs_/xr_ of BASE + FLOWX),
- v150 BTC options-flow features (opt_*), v111 Coinbase-premium features (cb_*), both market-wide, joined on t,
- targets y6, y18 (v103), y (= y42, v92 definition), y84 (same definition, h = 84), fv (v129 forward-vol target).
Writes artifacts/kaggle/v165/dataset/v165_panel.parquet + meta.json + dataset-metadata.json (private dataset
nguynchtrai/v165-majors-full-panel). Numbers only; no code, no credentials.

  python research/parallel/rounds/parallel-20260906-r2/v165/v165_export.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
OUT = Path("artifacts/kaggle/v165/dataset")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v142 = _load("v142", "v142/v142_cross_sectional_features.py")
    v150 = _load("v150", "v150/v150_options_flow.py")
    v111 = _load("v111", "v111/v111_coinbase_premium.py")
    v129 = v142.v129
    p = v142.v103.build()
    p = p.merge(v150.opt_features(), on="t", how="left")
    p = v111.add_cb(p)
    p = v142.add_xs(p, v142.BASE + v142.FLOWX)
    out = []
    for s, g in p.groupby("sym", sort=False):
        g = g.sort_values("t").copy()
        o = g["open"].to_numpy()
        n = len(g)
        fwd = np.full(n, np.nan)
        fwd[: n - 1 - 84] = np.log(o[1 + 84:] / o[1: n - 84])
        g["y84"] = np.clip(fwd / (g["vol42"].to_numpy() * np.sqrt(84)), -4, 4)
        out.append(g)
    import pandas as pd
    p = v129.add_fv(pd.concat(out, ignore_index=True))
    targets = ["y6", "y18", "y", "y84", "fv"]
    feats = [c for c in p.columns if c not in ("t", "open", "sym", "bar") and c not in targets and not c.startswith("y")]
    exp = p[["t", "sym"] + feats + targets].copy()
    exp["t"] = exp["t"].astype("int64")
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "v165_panel.parquet"
    exp.to_parquet(f, index=False)
    (OUT / "meta.json").write_text(json.dumps({"features": feats, "targets": targets, "horizons": {"y6": 6, "y18": 18, "y": 42, "y84": 84, "fv": 43},
                                               "syms": sorted(exp.sym.unique().tolist()), "rows": len(exp),
                                               "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}, indent=1))
    (OUT / "dataset-metadata.json").write_text(json.dumps({"title": "v165-majors-full-panel", "id": "nguynchtrai/v165-majors-full-panel",
                                                            "licenses": [{"name": "CC0-1.0"}]}, indent=1))
    print("rows", len(exp), "features", len(feats), "MB", round(f.stat().st_size / 1e6, 1))


if __name__ == "__main__":
    main()
