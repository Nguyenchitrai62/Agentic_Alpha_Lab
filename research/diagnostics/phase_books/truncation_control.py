"""Negative control for the truncation test: cutting the inputs 1 hour BEFORE the shifted bar close (bar T incomplete) must
change row T (otherwise the test could not detect anything). s = 1, 2 times."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase_books as pb  # noqa: E402
import truncation_test as tt  # noqa: E402


def main():
    s = 1
    f92, f103 = tt.union_panels(pb.Sources(s))
    out = []
    for T in (pd.Timestamp("2023-03-14 13:00", tz="UTC"), pd.Timestamp("2025-11-02 21:00", tz="UTC")):
        g92, g103 = tt.union_panels(pb.Sources(s, cut=T + pb.H4 - pd.Timedelta(hours=1)))
        r = {"T": str(T), "cut": str(T + pb.H4 - pd.Timedelta(hours=1))}
        for name, full, tr in (("p92x", f92, g92), ("p103x", f103, g103)):
            a = tt.rows_at(full, T)
            b = tt.rows_at(tr, T)
            if not len(b):
                r[name] = {"row_T_present": False}
                continue
            w, bad, n = tt.compare(a, b)
            r[name] = {"row_T_present": True, "n_cols_changed": len(bad), "n_cols": n, "examples": [x["col"] for x in bad[:8]]}
        out.append(r)
        print(r, flush=True)
    (pb.OUT / "truncation_control_s1.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
