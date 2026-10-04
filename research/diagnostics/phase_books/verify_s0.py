"""s = 0 reproduction: rebuilt members (native 4h inputs or 1h/1m-aggregated inputs) vs the cached deployed members.

  python research/diagnostics/phase_books/verify_s0.py --single          # member A, anchor 2021-09-24 only (native inputs)
  python research/diagnostics/phase_books/verify_s0.py --tag native      # all member files of run_phase(0, native=True)
  python research/diagnostics/phase_books/verify_s0.py --tag agg         # all member files of run_phase(0)
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

C = pb.CACHE


def cached(name):
    if name == "A":
        return pd.read_parquet(C / "member_A_O1_orders.parquet")
    if name == "Aq":
        return pd.read_parquet(C / "member_Aq_O1_orders.parquet")
    if name == "B":
        return pd.read_parquet(C / "member_B_tv.parquet")
    if name == "Bq":
        return pd.read_parquet(C / "member_Bq_tv.parquet")
    if name == "D":
        return pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0)
    if name == "Dq":
        return pd.read_parquet(C / "members_quarterly_D.parquet")
    raise KeyError(name)


def diff(new, old, lo=None, hi=None):
    new, old = new[pb.SYMS], old[pb.SYMS]
    if lo is not None:
        new, old = new[(new.index >= lo) & (new.index < hi)], old[(old.index >= lo) & (old.index < hi)]
    i = new.index.intersection(old.index)
    d = (new.loc[i] - old.loc[i]).abs()
    yearly = {}
    for a in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"):
        A = pd.Timestamp(a, tz="UTC")
        m = (d.index >= A) & (d.index < A + pd.Timedelta(days=365))
        if m.any():
            yearly[a[:4]] = {"max_abs": float(d[m].max().max()), "rows_gt_1e-9": int((d[m].max(axis=1) > 1e-9).sum()), "rows": int(m.sum()),
                             "corr": float(np.corrcoef(new.loc[i][m].to_numpy().ravel(), old.loc[i][m].to_numpy().ravel())[0, 1])}
    return {"rows_new": len(new), "rows_old": len(old), "rows_common": len(i), "only_new": len(new.index.difference(old.index)),
            "only_old": len(old.index.difference(new.index)), "max_abs": float(d.max().max()) if len(i) else None,
            "mean_abs": float(d.to_numpy().mean()) if len(i) else None, "mean_abs_old": float(old.loc[i].abs().to_numpy().mean()) if len(i) else None,
            "rows_gt_1e-12": int((d.max(axis=1) > 1e-12).sum()), "yearly": yearly}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--single", action="store_true")
    ap.add_argument("--tag", default=None)
    a = ap.parse_args()
    out_p = pb.OUT / "verify_s0.json"
    res = json.loads(out_p.read_text()) if out_p.exists() else {}
    if a.single:
        t0 = time.time()
        bk, leak = pb.build_member("A", "annual", pb.Sources(0, native=True), print, anchors=["2021-09-24"])
        r = diff(bk, cached("A"), pd.Timestamp("2021-09-24", tz="UTC"), pd.Timestamp("2022-09-24", tz="UTC"))
        r["seconds"] = round(time.time() - t0, 1)
        res["single_A_2021_native"] = r
        print(json.dumps(r, indent=1))
    if a.tag:
        sfx = "_native" if a.tag == "native" else ""
        for name in ("A", "Aq", "B", "Bq", "D", "Dq"):
            p = pb.OUT / f"member_{name}_s0{sfx}.parquet"
            if p.exists():
                res[f"{a.tag}_{name}"] = diff(pd.read_parquet(p), cached(name))
                r = res[f"{a.tag}_{name}"]
                print(a.tag, name, "max_abs", r["max_abs"], "rows>1e-12", r["rows_gt_1e-12"], "only_new/old", r["only_new"], r["only_old"],
                      {y: (v["max_abs"], v["rows_gt_1e-9"], round(v["corr"], 6)) for y, v in r["yearly"].items()}, flush=True)
        bp = pb.OUT / f"books_s0{sfx}_v202sched.parquet"
        if bp.exists():
            fw = pb._load("fw205", pb.ROOT / "scripts/forward_v205.py")

            class _ER:
                CACHE = C

            class _EU:
                er = _ER
            ref = fw.research_books_d2(_EU)
            res[f"{a.tag}_books_cb_v202sched"] = r = diff(pd.read_parquet(bp), ref)
            print(a.tag, "CB books (v202 schedule) vs research_books_d2: max_abs", r["max_abs"], "rows>1e-12", r["rows_gt_1e-12"],
                  {y: (v["max_abs"], v["rows_gt_1e-9"], round(v["corr"], 6)) for y, v in r["yearly"].items()}, flush=True)
    out_p.write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
