"""Train/serve-skew audit, item 4: execution-side inputs. scripts/forward_v205.py::build_prep (live trade plans: Binance USD-M REST 4h + 1m
klines via forward_v205.market) vs engine_user.prepare (research replay: 1m archive cube via v172.cube_ohlc, 4h opens from the research
panel opens_v154.parquet), on the same 4h decision grid. Cube rows compared for decision bars 2026-08-01 .. 2026-09-20 (holding bars up to
2026-09-21 00:00); sig4 / o1 / o2 / settle on the whole grid 2026-05-01 .. 2026-09-20 (sig4 needs 20 days of warmup).
engine_user is imported read-only. Output: parity/prep_parity.json.

  .venv/Scripts/python.exe research/diagnostics/system_audit/parity/prep_parity.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
os.chdir(ROOT)
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
START, NOW = pd.Timestamp("2026-08-01", tz="UTC"), pd.Timestamp("2026-09-21 04:00", tz="UTC")
GRID = pd.date_range("2026-05-01", "2026-09-20 20:00", freq="4h", tz="UTC")
CUBE_ROWS = (GRID >= START) & (GRID <= pd.Timestamp("2026-09-20 20:00", tz="UTC"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    fw = _load("par_prep_fw", ROOT / "scripts/forward_v205.py")
    SYMS = list(fw.SYMS)
    cache = HERE / "cache/prep_rest.pkl"
    if cache.exists():
        opens, k1 = pd.read_pickle(cache)
    else:
        o_all, k1 = {}, {}
        for s in SYMS:  # one symbol at a time with a pause (Binance weight limit; the backend shares this IP)
            fw.SYMS = [s]
            o, k = fw.market(START, NOW)
            o_all[s], k1[s] = o[s], k[s]
            print("fetched", s, len(k[s]), flush=True)
            time.sleep(30)
        fw.SYMS = SYMS
        opens = pd.DataFrame(o_all)
        pd.to_pickle((opens, k1), cache)
    live = fw.build_prep(opens, k1, GRID)
    eu = _load("par_prep_eu", RD / "engine_user/engine_user.py")
    ropens = pd.read_parquet(eu.er.CACHE / "opens_v154.parquet")
    books = pd.DataFrame(0.0, index=GRID, columns=SYMS)
    res = eu.prepare(books, ropens)
    out = {"grid": [str(GRID[0]), str(GRID[-1])], "cube_rows": [str(GRID[CUBE_ROWS][0]), str(GRID[CUBE_ROWS][-1])],
           "research_cube_dtype": str(res["O"].dtype), "live_cube_dtype": str(live["O"].dtype), "per_symbol": {}}
    for j, s in enumerate(SYMS):
        d = {}
        for k in ("O", "H", "L", "C"):
            a, b = live[k][CUBE_ROWS, :, j], res[k][CUBE_ROWS, :, j].astype(float)
            ok = np.isfinite(a) & np.isfinite(b)
            rel = np.abs(a[ok] / b[ok] - 1)
            d[k] = {"max_abs": float(np.abs(a[ok] - b[ok]).max()), "max_rel": float(rel.max()),
                    "frac_eq_float32": round(float((a[ok].astype(np.float32) == b[ok].astype(np.float32)).mean()), 6),
                    "n_rel_gt_1e-6": int((rel > 1e-6).sum()), "nan_live_only": int((~np.isfinite(a) & np.isfinite(b)).sum()),
                    "nan_research_only": int((np.isfinite(a) & ~np.isfinite(b)).sum())}
        for k in ("o1", "o2", "sig4"):
            a, b = live[k][:, j], res[k][:, j]
            ok = np.isfinite(a) & np.isfinite(b)
            d[k] = {"max_abs": float(np.abs(a[ok] - b[ok]).max()) if ok.any() else None,
                    "max_rel": float(np.abs(a[ok] / b[ok] - 1).max()) if ok.any() else None,
                    "n_both_finite": int(ok.sum()), "nan_mismatch": int((np.isfinite(a) ^ np.isfinite(b)).sum())}
        # 4h opens vs minute-0 open of the holding bar (internal consistency of each source)
        o0l, o0r = live["O"][CUBE_ROWS, 0, j], res["O"][CUBE_ROWS, 0, j].astype(float)
        d["o1_vs_cube_minute0_rel"] = {"live": float(np.nanmax(np.abs(live["o1"][CUBE_ROWS, j] / o0l - 1))),
                                       "research": float(np.nanmax(np.abs(res["o1"][CUBE_ROWS, j] / o0r - 1)))}
        out["per_symbol"][s] = d
    out["settle_equal"] = bool(np.array_equal(live["settle"], res["settle"]))
    out["keys_research_only"] = sorted(set(res) - set(live))
    out["max_rel_cube_all"] = max(out["per_symbol"][s][k]["max_rel"] for s in SYMS for k in ("O", "H", "L", "C"))
    out["max_rel_o1_o2_all"] = max(out["per_symbol"][s][k]["max_rel"] or 0 for s in SYMS for k in ("o1", "o2"))
    out["max_abs_sig4_all"] = max(out["per_symbol"][s]["sig4"]["max_abs"] or 0 for s in SYMS)
    (HERE / "prep_parity.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "per_symbol"}, indent=1))


if __name__ == "__main__":
    main()
