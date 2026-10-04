"""Truncation test of the shifted feature builders (leakage check).

For phase s and 10 random shifted bar times T (seed 0): every raw input is truncated to what is known at the shifted bar
close T + 4h (1h klines closed by then, 1m flow minutes before it, daily bars / funding stamped before it, standard 4h
options / spot / Coinbase rows closed by then), the full model-input panels are rebuilt (union of the A, B and D member
inputs: v92 panel with the Coinbase prefix + TradingView + order flow + options + cb premium, after the v142 xs step; v103
panel likewise) and the rows at t = T must equal the rows of the untruncated computation (labels y* excluded).

  python research/diagnostics/phase_books/truncation_test.py --phase 1
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase_books as pb  # noqa: E402


def union_panels(src):
    tag = f"tr_{src.s}_{int(time.time() * 1e6) % 10**9}"
    v144 = pb._load(f"v144_{tag}", pb.RD / "v144/v144_deploy_v3.py")
    tvm = pb._load(f"tv_{tag}", pb.RD / "v231/tv_indicators.py")
    flo = pb._load(f"flo_{tag}", pb.RD / "v236/flow_features.py")
    flo.D = pb.ORDERS
    ext, v103, _ = pb._patch_data(v144, src)
    v142 = v144.v142
    xf = pb._flow_frame(tvm, flo, ext.v92.load_asset, src)          # TV + order flow (A); TV alone = B's frame
    of = src.opt_frame()                                            # options (B)
    cbf = src.cb_frame(pb.standard_p103_grid())                     # Coinbase premium (D)
    add = lambda p: p.merge(of, on="t", how="left").merge(cbf, on="t", how="left").merge(xf, on=["t", "sym"], how="left")
    p92, p103 = add(ext.v92.build()), add(v103.build())
    return v142.add_xs(p92, v142.BASE), v142.add_xs(p103, v142.BASE + v142.FLOWX)


def rows_at(p, T):
    r = p[p.t == T].set_index("sym").sort_index()
    return r[[c for c in r.columns if not (c == "y" or (c.startswith("y") and c[1:].isdigit()))]]


def compare(a, b):
    cols = [c for c in a.columns if c != "t"]
    assert list(a.index) == list(b.index), (list(a.index), list(b.index))
    worst, bad = 0.0, []
    for c in cols:
        x, y = a[c].to_numpy(dtype=float), b[c].to_numpy(dtype=float)
        nan_mis = np.isnan(x) != np.isnan(y)
        d = np.where(np.isnan(x) | np.isnan(y), 0.0, np.abs(x - y))
        worst = max(worst, float(d.max()))
        if nan_mis.any() or (d > 0).any():
            bad.append({"col": c, "max_abs": float(d.max()), "nan_mismatch": int(nan_mis.sum())})
    return worst, bad, len(cols)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", type=int, required=True)
    ap.add_argument("--n", type=int, default=10)
    a = ap.parse_args()
    s = a.phase
    rng = np.random.default_rng(0)
    grid = pd.date_range(pd.Timestamp("2021-09-24", tz="UTC") + pd.Timedelta(hours=s), pd.Timestamp("2026-09-23 12:00", tz="UTC"), freq="4h")
    times = sorted(grid[rng.choice(len(grid), a.n, replace=False)])
    t0 = time.time()
    f92, f103 = union_panels(pb.Sources(s))
    print("full panels", f92.shape, f103.shape, f"{time.time() - t0:.0f}s", flush=True)
    out = {"phase": s, "times": [str(t) for t in times], "results": []}
    for T in times:
        t1 = time.time()
        g92, g103 = union_panels(pb.Sources(s, cut=T + pb.H4))
        r = {"T": str(T), "cut": str(T + pb.H4)}
        for name, full, tr in (("p92x", f92, g92), ("p103x", f103, g103)):
            a_, b_ = rows_at(full, T), rows_at(tr, T)
            w, bad, ncol = compare(a_, b_)
            r[name] = {"syms": list(a_.index), "n_cols": ncol, "max_abs_diff": w, "mismatches": bad,
                       "last_t_in_truncated": str(tr.t.max())}
        r["seconds"] = round(time.time() - t1, 1)
        out["results"].append(r)
        print(T, "p92x", r["p92x"]["max_abs_diff"], len(r["p92x"]["mismatches"]), "p103x", r["p103x"]["max_abs_diff"],
              len(r["p103x"]["mismatches"]), "cols", r["p92x"]["n_cols"], r["p103x"]["n_cols"], "last t", r["p92x"]["last_t_in_truncated"],
              f"{r['seconds']}s", flush=True)
    out["pass"] = all(not r[k]["mismatches"] for r in out["results"] for k in ("p92x", "p103x"))
    (pb.OUT / f"truncation_s{s}.json").write_text(json.dumps(out, indent=1, default=str))
    print("PASS" if out["pass"] else "FAIL", flush=True)


if __name__ == "__main__":
    main()
