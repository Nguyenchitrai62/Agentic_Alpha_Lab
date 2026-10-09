"""Derive CTRL_C per-year constants from B7's own engine run (mechanical, no choice).

c_y = sum_s sized_mean_{s,y} * n_sized_{s,y} / sum_s n_sized_{s,y} over B7 runs.
--stage dev  reads tmp/runs_dev.pkl  (B7) -> tmp/ctrlC_dev.json  (c_0..c_3)
--stage last reads tmp/runs_last.pkl (B7) -> tmp/ctrlC_last.json (c_0..c_4)
Degenerate (no sizings / non-finite) -> 1.0, counted.
"""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

HERE = Path(__file__).resolve().parent
TMP = HERE / "tmp"


def constants_from(runs, years) -> dict:
    out: dict[str, dict] = {}
    for y in years:
        num, den = 0.0, 0
        for s in range(4):
            m = runs[s]["B7"]["mult"][str(y)]
            sm, n = m["sized_mean"], int(m["n_sized"])
            if sm is not None and n:
                num += float(sm) * n
                den += n
        c = float(num / den) if den else 1.0
        if not (c == c and 1.0 <= c <= 1.5):
            c = 1.0
        out[str(y)] = {"c": round(float(c), 6), "n_sized": int(den),
                       "fallback": bool(den == 0)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["dev", "last"], required=True)
    args = ap.parse_args()
    src = TMP / ("runs_dev.pkl" if args.stage == "dev" else "runs_last.pkl")
    dst = TMP / ("ctrlC_dev.json" if args.stage == "dev" else "ctrlC_last.json")
    years = [0, 1, 2, 3] if args.stage == "dev" else [0, 1, 2, 3, 4]
    runs = pickle.loads(src.read_bytes())
    assert all("B7" in runs[s] for s in range(4)), \
        {s: sorted(runs[s]) for s in range(4)}
    out = constants_from(runs, years)
    dst.write_text(json.dumps(out, indent=1))
    print(f"CTRL_C {args.stage}: {out}", flush=True)


if __name__ == "__main__":
    main()
