"""oc_k2seeds scoring: per-seed clean-year engine rows from tmp/runs_seed{S}.pkl.

Per seed S: year-4 R/DD via reset_metric.year_reset (4-phase reset), full-path
DD via v388.mix over [2021-09-24, Y1), book/rung wins from wins[4].
Determinism check: years 0-3 segments must equal oc_kronoshidden dev K2
(tmp/dev_table.json) to the digit (frozen prior path). REF frozen (4.648/12.90,
full 16.82) — NOT rescored. Light CPU. Output: tmp/engine.json.
"""
import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
KH = HERE.parent / "oc_kronoshidden"
TMP = HERE / "tmp"
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
SEEDS = (1, 2, 3, 4)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v388 = _load("v388_sc", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_sc", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    devtab = json.loads((KH / "tmp/dev_table.json").read_text())
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    out = {}
    for seed in SEEDS:
        runs = pickle.loads((TMP / f"runs_seed{seed}.pkl").read_bytes())
        assert set(runs) == {0, 1, 2, 3} and all(set(runs[s]) == {"K2"} for s in range(4)), \
            f"seed {seed}: incomplete runs { {s: sorted(v) for s, v in runs.items()} }"
        src = {s: {"K2": runs[s]["K2"]["run"]} for s in range(4)}
        # determinism: frozen prior path (years 0-3 == oc_kronoshidden dev K2)
        for y in range(4):
            a = rm.year_reset(src, "K2", y)
            assert a["R"] == devtab["table"]["K2"]["years_R"][y] and \
                a["DD"] == devtab["table"]["K2"]["years_DD"][y], (seed, y, a)
        print(f"seed {seed}: prior-path determinism OK (years 0-3 == dev K2)", flush=True)
        y4 = rm.year_reset(src, "K2", 4)
        e, mn = v388.mix(src, "K2", g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        fulldd = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        nb = sum(runs[s]["K2"]["wins"][4]["nb"] for s in range(4))
        wb = sum(runs[s]["K2"]["wins"][4]["wb"] for s in range(4))
        nr = sum(runs[s]["K2"]["wins"][4]["nr"] for s in range(4))
        wr = sum(runs[s]["K2"]["wins"][4]["wr"] for s in range(4))
        row = {"R": y4["R"], "DD": y4["DD"], "full_path_dd": fulldd,
               "book_trades": nb, "book_win": round(wb / nb, 4),
               "rung_trades": nr, "rung_win": round(wr / nr, 4),
               "all_win": round((wb + wr) / (nb + nr), 4)}
        out[str(seed)] = row
        print(f"seed {seed}: {row}", flush=True)
    (TMP / "engine.json").write_text(json.dumps(out, indent=1))
    print("wrote tmp/engine.json", flush=True)


if __name__ == "__main__":
    main()
