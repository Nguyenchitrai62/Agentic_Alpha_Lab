"""v143 step 1: export the audited v103 panel (features + targets) for the Kaggle cross-asset attention model.

Writes artifacts/kaggle/v143/dataset/v143_panel.parquet (t, sym, asset, feature columns, y6, y18, y) plus
feature_list.json and dataset-metadata.json (private dataset nguynchtrai/v143-majors-panel). No credentials, no code of
the research repo other than the exported numbers.

  python research/parallel/rounds/parallel-20260906-r2/v143/v143_export.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
OUT = Path("artifacts/kaggle/v143/dataset")
spec = importlib.util.spec_from_file_location("v103", HERE.parent / "v103" / "v103_flow_short_horizon.py")
v103 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v103)


def main():
    p = v103.build()
    feats = [c for c in p.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    out = p[["t", "sym"] + feats + ["y6", "y18", "y"]].copy()
    out["t"] = out["t"].astype("int64")
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "v143_panel.parquet"
    out.to_parquet(f, index=False)
    (OUT / "feature_list.json").write_text(json.dumps({"features": feats, "targets": ["y6", "y18", "y"], "syms": sorted(out.sym.unique().tolist()),
                                                        "sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "rows": len(out)}, indent=1))
    (OUT / "dataset-metadata.json").write_text(json.dumps({"title": "v143-majors-panel", "id": "nguynchtrai/v143-majors-panel",
                                                            "licenses": [{"name": "CC0-1.0"}]}, indent=1))
    print("rows", len(out), "features", len(feats), "file MB", round(f.stat().st_size / 1e6, 1))


if __name__ == "__main__":
    main()
