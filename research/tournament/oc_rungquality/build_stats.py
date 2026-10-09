"""oc_rungquality step 1: trailing per-cell quality stats from oc_kpi engine fills.

Reads research/tournament/oc_kpi/events_s{0..3}.parquet (read-only), pairs FIFO
per (shift, symbol) (ladderfill-exact copy in quality.py), attaches holding-bar
open T, then per anchor computes trailing_stats + skip_sets -> tmp/quality_stats.json.

CPU-only, pandas, RAM < 1 GB. Prints progress at each stage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
KPI = ROOT / "research/tournament/oc_kpi"

sys.path.insert(0, str(HERE))
from quality import ANCH5, with_T, pair_shift, trailing_stats, skip_sets  # noqa: E402

SHIFTS = (0, 1, 2, 3)
COLS = ["t", "symbol", "kind", "rung", "weight", "ret"]


def main() -> None:
    all_pairs = []
    for s in SHIFTS:
        ev = pd.read_parquet(KPI / f"events_s{s}.parquet", columns=COLS)
        ev["t"] = pd.to_datetime(ev["t"], utc=True)
        ev = ev.sort_values("t").reset_index(drop=True)
        rungs, unpaired, left = pair_shift(ev, s)
        print(f"shift {s}: paired={len(rungs)} unpaired_exits={unpaired} left_open={left}",
              flush=True)
        for r in rungs:
            r["shift"] = s
        all_pairs.extend(rungs)
    pairs = pd.DataFrame(all_pairs)
    pairs["fill_t"] = pd.to_datetime(pairs["fill_t"], utc=True)
    pairs["exit_t"] = pd.to_datetime(pairs["exit_t"], utc=True)
    pairs = with_T(pairs)
    print(f"paired total={len(pairs)} T range={pairs['T'].min()}..{pairs['T'].max()}",
          flush=True)
    pairs.to_parquet(HERE / "tmp/pairs_all.parquet", index=False)

    out: dict = {"config": {
        "stats_ledger": "research/tournament/oc_kpi/events_s0..s3 rung_fill/exit FIFO pairs",
        "window": "T in [A-97d, A-7d) AND exit_t < A-7d (90d, pre-anchor + 7d embargo)",
        "stop": "matched exit kind == rung_sl",
        "fill_rate_denom": "N_BAR_WINDOW = 2160 (same for every cell; ranking == n_fill ranking)",
        "min_n": 10, "rule": "F1: stop_rate > p80 (strict); F2: F1 + fill_rate < p20 (strict)",
    }, "anchors": {}}
    for a in ANCH5:
        st = trailing_stats(pairs, a)
        sk = skip_sets(st)
        cells = st.to_dict("records")
        out["anchors"][a] = {"cells": cells, "p80": sk["p80"], "p20": sk["p20"],
                             "f1": sk["f1"], "f2": sk["f2"],
                             "n_stats_fills": int(st["n_fill"].sum())}
        print(f"anchor {a}: stats_fills={st['n_fill'].sum()} p80={sk['p80']} "
              f"p20={sk['p20']} n_f1={len(sk['f1'])} n_f2={len(sk['f2'])}", flush=True)
        if sk["f1"]:
            print(f"  F1 skip: {sk['f1']}", flush=True)
        if len(sk["f2"]) > len(sk["f1"]):
            print(f"  F2 extra: {[c for c in sk['f2'] if c not in sk['f1']]}", flush=True)
    (HERE / "tmp/quality_stats.json").write_text(json.dumps(out, indent=1))
    print("wrote tmp/quality_stats.json", flush=True)


if __name__ == "__main__":
    main()
