"""Rebuild the v205 book members split into their three components (v223 data step, no evaluation).

Each member book (v144 structure) = 0.25 * v92 long-only (7d) + 0.25 * v94 long/short (18/42/84-bar horizons) + 0.5 * v103
flow long/short (1d/3d), each vol-target scaled. The audited code paths are re-run unchanged (annual anchors, and the v202
quarterly wrapper); only the final weighted sum is kept apart. Members: A = v144 books, B = v150 options member. Output:
artifacts/research/engine_real/components_{A,B}_{annual,quarterly}.parquet with columns (component, symbol); the sum over the
components must reproduce members_v154.parquet (annual) and members_quarterly.parquet (quarterly) - checked at the end.

  python research/parallel/rounds/parallel-20260906-r2/v223/build_components.py
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
CACHE = Path("artifacts/research/engine_real")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, RD / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def components(v144):
    """books_v142 of v144_deploy_v3.py with the three weighted components returned separately."""
    v115, v142, v103, v129, v125, PD = v144.v115, v144.v142, v144.v103, v144.v129, v144.v125, v144.PD
    ext = v115.v114.v113
    v115.v114.v113.cb_bars = v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    f92_base = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    p92x = v142.add_xs(p92, v142.BASE)
    ext.v92.FEATS = [c for c in p92x.columns if c not in ("y", "t", "open", "sym", "bar")]
    lo = pd.concat([ext.v92.train_predict(p92x, a)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p94 = ext.v94.add_targets(p92x)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls = pd.concat([ext.v94.train_predict(p94, a, f94)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p103 = v103.build()
    f103_base = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    p103x = v142.add_xs(p103, v142.BASE + v142.FLOWX)
    f103 = [c for c in p103x.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    fl = pd.concat([v103.train_predict(p103x, a, f103)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    pv92, _ = v129.vol_predict(p92, f92_base, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)
    pv103, _ = v129.vol_predict(p103, f103_base, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)

    def swap(df, pv):
        d = df.merge(pv, on=["t", "sym"], how="left")
        d["vol42"] = d["pvol"].fillna(d["vol42"])
        return d.drop(columns="pvol")

    ph = list(range(PD))
    W_lo = v125.phased(v125.raw_lo(swap(lo, pv92)), ph)
    W94 = v125.phased(v125.raw_ls(swap(ls, pv92)), ph)
    W103 = v125.phased(v125.raw_ls(swap(fl, pv103)), ph)
    idx = W_lo.index.union(W94.index).union(W103.index)
    idx = idx[idx >= p103.t.min()]
    comp = {"lo": 0.25 * W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0),
            "ls": 0.25 * W94.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p92, W94).reindex(idx).fillna(1.0), axis=0),
            "fl": 0.5 * W103.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)}
    return pd.concat(comp, axis=1)


def options_member(v150):
    """Apply v150's option-feature patches (as in v150.main / v202.members_quarterly) to v150's own v144 instance."""
    v144 = v150.v144
    OPT, feats = v150.OPT, v150.opt_features()
    ext, v103 = v144.v115.v114.v113, v144.v103
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in OPT], anchors, emb)
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    ext.v92.build = lambda: b92().merge(feats, on="t", how="left")
    v103.build = lambda: b103().merge(feats, on="t", how="left")
    return v144


def quarterly_options(v202, v150):
    """As v202.members_quarterly: the quarterly wrapper on v150's v144 instance first, then the option-feature patches."""
    v202.quarterly(v150.v144)
    return options_member(v150)


def main():
    t0 = time.time()
    v202 = _load("v202_c", "v202/v202_quarterly_retrain.py")
    jobs = {
        "A_annual": lambda: _load("v144_ca", "v144/v144_deploy_v3.py"),
        "B_annual": lambda: options_member(_load("v150_cb", "v150/v150_options_flow.py")),
        "A_quarterly": lambda: v202.quarterly(_load("v144_cq", "v144/v144_deploy_v3.py")),
        "B_quarterly": lambda: quarterly_options(v202, _load("v150_cbq", "v150/v150_options_flow.py")),
    }
    for name, make in jobs.items():
        out = CACHE / f"components_{name}.parquet"
        if out.exists():
            print(name, "cached", flush=True)
            continue
        comp = components(make())
        comp.to_parquet(out)
        print(f"{name}: {comp.shape} ({time.time() - t0:.0f}s)", flush=True)
    # reproduction check against the audited member caches
    mem = pd.read_parquet(CACHE / "members_v154.parquet")
    mq = pd.read_parquet(CACHE / "members_quarterly.parquet")
    for name, ref in (("A_annual", mem.xs("A", axis=1, level=0)), ("B_annual", mem.xs("B", axis=1, level=0)),
                      ("A_quarterly", mq.xs("A", axis=1, level=0)), ("B_quarterly", mq.xs("B", axis=1, level=0))):
        comp = pd.read_parquet(CACHE / f"components_{name}.parquet")
        tot = sum(comp.xs(k, axis=1, level=0) for k in ("lo", "ls", "fl"))
        common = tot.index.intersection(ref.index)
        diff = float(np.nanmax(np.abs(tot.loc[common, ref.columns].to_numpy() - ref.loc[common].to_numpy())))
        print(f"check {name}: {len(common)} rows, max |sum - member| = {diff:.2e}", flush=True)


if __name__ == "__main__":
    main()
