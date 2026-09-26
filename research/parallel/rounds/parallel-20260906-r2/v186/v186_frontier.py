"""Frontier DIAGNOSTIC (ex post, labelled; not a registry hypothesis): v183 (majors sleeve) and v186 (11-asset sleeve)
at portfolio vol targets 0.25 / 0.28 / 0.31 / 0.34 - monthly and gate DD (max of 4h and 1m-marked) under normal and
stress costs. Purpose: show the user the return/DD trade-off; no target is selected from it.

  python research/parallel/rounds/parallel-20260906-r2/v186/v186_frontier.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v186", HERE / "v186_sleeve_eleven_assets.py")
v186 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v186)
v183, v182, diag, v172, v171, v170, er = v186.v183, v186.v182, v186.diag, v186.v172, v186.v171, v186.v170, v186.er
TARGETS = (0.25, 0.28, 0.31, 0.34)


def patched_ns(eleven, target):
    src = Path(v183.__file__).read_text(encoding="utf-8")
    if eleven:
        src = src.replace("for a in range(len(cols)) if fmins[r, gi, a] >= 0", "for a in range(fmins.shape[2]) if fmins[r, gi, a] >= 0")
        src = src.replace("path = ((Cm / o1[i] - 1) * w).sum(axis=1)", "path = ((Cm[:, :len(cols)] / o1[i] - 1) * w).sum(axis=1)")
    a = "np.minimum(0.25 / np.where(np.isnan(vol), 1.0, vol), v99.CAP)"
    assert src.count(a) == 1
    src = src.replace(a, f"np.minimum({target} / np.where(np.isnan(vol), 1.0, vol), v99.CAP)")
    ns = {"__file__": v183.__file__, "__name__": "frontier"}
    exec(compile(src.replace('if __name__ == "__main__":\n    main()', ""), v183.__file__, "exec"), ns)
    return ns


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v172.cube_ohlc(G, cols)
    for s in v182.ALTS:
        one = v182.asset_cube(G, s, v182.ALT_DIR)
        for k in ("open", "high", "low", "close"):
            A[k] = np.concatenate([A[k], one[k][:, :, None]], axis=2)
        del one
    cols_all = cols + list(v182.ALTS)
    base = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    exs = diag.stress_exec(idx, cols)
    out = {"note": "DIAGNOSTIC ex post frontier; no target is selected from it", "rows": []}
    ns0 = patched_ns(False, 0.25)
    tables = {}
    for eleven in (False, True):
        cc = cols_all if eleven else cols
        AA = A if eleven else {k: A[k][:, :, :len(cols)] for k in A}
        tables[eleven] = {"normal": ns0["rung_table_tp"](G, cc, AA, 0.0002, 0.0005, 0.0),
                          "stress": ns0["rung_table_tp"](G, cc, AA, 0.0004, 0.0007, 0.0005), "close": AA["close"]}
    for eleven in (False, True):
        for tg in TARGETS:
            ns = patched_ns(eleven, tg)
            row = {"sleeve": "11 assets" if eleven else "majors", "target": tg}
            for key, ex in (("normal", ex60), ("stress", exs)):
                r = ns["run"](books, dict(base, exec=ex), tables[eleven]["close"], G, *tables[eleven][key])
                row[key] = {"monthly": r["monthly_pct"], "gate_dd": r["gate_dd"], "dd_1m": r["dd_1m_mark"], "dd_4h": r["full_path_dd"]}
            out["rows"].append(row)
            print(row, flush=True)
    (HERE / "v186_frontier.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
