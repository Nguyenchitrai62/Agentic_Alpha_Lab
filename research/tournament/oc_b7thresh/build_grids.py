"""Build 12-cell post-cascade boost grids (CPU-only, closes only).

Verbatim arithmetic from oc_cascadedelay build_delay.py / oc_cascadeboost build_boost.py,
parameterized over k in {3.5,4.0,4.5} x W in {3,5,7,10} days, mult 1.5.

Outputs (this folder only):
  boost_grid_main.parquet (shift, T + 12 bool + 12 mult columns)
  boost_grid_pre.parquet  (same on the pre-sample grid)
Read-only inputs: oc_kronoshidden/bars_4h_4shift.parquet, oc_presampletilt/bars_4h_presample.parquet.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BARS_MAIN = ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet"
BARS_PRE = ROOT / "research/tournament/oc_presampletilt/bars_4h_presample.parquet"

sys.path.insert(0, str(HERE))
from thresh_rule import BOOST, THRESH_GRID, WINDOW_GRID, boosted_mask, cell_of, triggers_of

MAJORS_MAIN = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
MAJORS_PRE = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]  # SOL absent pre-sample
SHIFTS = [0, 1, 2, 3]
HB_S = 600


def build_one(bars: pd.DataFrame, majors: list, tag: str):
    t0 = time.time()
    last_hb = t0
    # triggers per (k, shift): union tc over majors
    trig = {(k, s): [] for k in THRESH_GRID for s in SHIFTS}
    counts = {}
    for sym in majors:
        for s in SHIFTS:
            sub = bars[(bars["sym"] == sym) & (bars["shift"] == s)].sort_values("T")
            t = pd.to_datetime(sub["T"], utc=True)
            c = sub["close"].to_numpy(dtype=float)
            for k in THRESH_GRID:
                fire = triggers_of(c, thresh=k)
                n = int(fire.sum())
                counts[(sym, s, k)] = (len(sub), n)
                tc = (t[fire] + pd.Timedelta(hours=4)).tolist()
                trig[(k, s)].extend(tc)
            print(f"[{tag}] triggers {sym} shift{s}: " +
                  ", ".join(f"k{k}={counts[(sym, s, k)][1]}/{counts[(sym, s, k)][0]}"
                             for k in THRESH_GRID), flush=True)
            if time.time() - last_hb >= HB_S:
                last_hb = time.time()
                print(f"[hb] build_grids {tag} alive elapsed {last_hb - t0:.0f}s", flush=True)
    # union + sort per (k, shift)
    for k in THRESH_GRID:
        for s in SHIFTS:
            trig[(k, s)] = sorted(set(pd.to_datetime(trig[(k, s)], utc=True)))
    rows = []
    for s in SHIFTS:
        grid = np.array(sorted(set(
            bars[bars["shift"] == s]["T"].values.astype("datetime64[ns]").astype(np.int64))),
            dtype=np.int64)
        gt = pd.to_datetime(grid, utc=True)
        masks = {}
        for k in THRESH_GRID:
            tc_ns = np.array([t.value for t in trig[(k, s)]], dtype=np.int64)
            for w in WINDOW_GRID:
                masks[(k, w)] = boosted_mask(grid, tc_ns, w)
        for i, T in enumerate(gt):
            row = {"shift": s, "T": T}
            for k in THRESH_GRID:
                for w in WINDOW_GRID:
                    b = bool(masks[(k, w)][i])
                    row[f"boosted_{cell_of(k, w)}"] = b
                    row[f"mult_{cell_of(k, w)}"] = BOOST if b else 1.0
            rows.append(row)
        # monotonicity asserts (superset relations)
        for w in WINDOW_GRID:
            a35 = masks[(3.5, w)]
            a40 = masks[(4.0, w)]
            a45 = masks[(4.5, w)]
            assert (a35 | a40).sum() == a35.sum() and (a40 | a45).sum() == a40.sum(), \
                f"k-monotonicity failed shift{s} W{w}"
        for k in THRESH_GRID:
            m3 = masks[(k, 3)]
            m5 = masks[(k, 5)]
            m7 = masks[(k, 7)]
            m10 = masks[(k, 10)]
            assert (m3 | m5).sum() == m5.sum() and (m5 | m7).sum() == m7.sum() and \
                (m7 | m10).sum() == m10.sum(), f"W-monotonicity failed shift{s} k{k}"
        print(f"[{tag}] shift{s}: grid={len(grid)} " +
              ", ".join(f"k{k} trig={len(trig[(k, s)])}" for k in THRESH_GRID), flush=True)
    out = pd.DataFrame(rows).sort_values(["shift", "T"]).reset_index(drop=True)
    return out, trig


def main() -> None:
    print("loading main bars...", flush=True)
    b = pd.read_parquet(BARS_MAIN)
    b["T"] = pd.to_datetime(b["T"], utc=True)
    print(f"main bars rows={len(b)} Trange={b['T'].min()}..{b['T'].max()}", flush=True)
    out_main, trig_main = build_one(b, MAJORS_MAIN, "main")
    out_main.to_parquet(HERE / "boost_grid_main.parquet", index=False)
    print(f"wrote boost_grid_main.parquet rows={len(out_main)}", flush=True)
    del b

    print("loading pre-sample bars...", flush=True)
    p = pd.read_parquet(BARS_PRE)
    p["T"] = pd.to_datetime(p["T"], utc=True)
    print(f"pre bars rows={len(p)} Trange={p['T'].min()}..{p['T'].max()}", flush=True)
    out_pre, trig_pre = build_one(p, MAJORS_PRE, "pre")
    out_pre.to_parquet(HERE / "boost_grid_pre.parquet", index=False)
    print(f"wrote boost_grid_pre.parquet rows={len(out_pre)}", flush=True)

    # trigger counts per (k, year, shift) for the report
    import json
    anch_main = [pd.Timestamp(a, tz="UTC") for a in
                 ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24",
                  "2026-09-24")]
    trig_counts = {}
    for k in THRESH_GRID:
        for y in range(5):
            lo, hi = anch_main[y], anch_main[y + 1]
            for s in SHIFTS:
                trig_counts[f"k{k}_y{y}_s{s}"] = sum(
                    1 for t in trig_main[(k, s)] if lo <= t < hi)
    legs = {"Y2017": (pd.Timestamp("2017-10-16", tz="UTC"), pd.Timestamp("2018-01-01", tz="UTC")),
            "Y2018": (pd.Timestamp("2018-01-01", tz="UTC"), pd.Timestamp("2019-01-01", tz="UTC")),
            "Y2019": (pd.Timestamp("2019-01-01", tz="UTC"), pd.Timestamp("2020-01-01", tz="UTC")),
            "Y2020p": (pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2020-09-01", tz="UTC"))}
    for k in THRESH_GRID:
        for leg, (lo, hi) in legs.items():
            for s in SHIFTS:
                trig_counts[f"pre_k{k}_{leg}_s{s}"] = sum(
                    1 for t in trig_pre[(k, s)] if lo <= t < hi)
    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/trigger_counts.json").write_text(json.dumps(
        {"main": {kk: v for kk, v in trig_counts.items() if not kk.startswith('pre_')},
         "pre": {kk: v for kk, v in trig_counts.items() if kk.startswith('pre_')}}, indent=1))
    print("wrote tmp/trigger_counts.json", flush=True)


if __name__ == "__main__":
    main()
