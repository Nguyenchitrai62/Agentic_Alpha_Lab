"""oc_k2seeds engine: per-seed K2 full-window runs (PLAN fixed engine row).

Mechanism = oc_kronoshidden/run_engine.py tilt path on G2 (rule inv, k=1.0,
kd=1.7, bear, G=2.0), imported read-only and called directly. Per seed S:
combined Kronos lookup = ORIGINAL seed-1234 low1 for T < 2025-09-24 (years 0-3
frozen, bit-identical prior path) + seed-S low1 for T >= 2025-09-24 (year 4).
Fits = frozen anchor-2025 fit (fits.json) for year 4, frozen per-anchor fits
for years 0-3. Only variant K2. Stage semantics = "last" (full window
[DEV0, Y1), wins/mult per year). Costs/fills inherited from the engine
(win_start=5 trade-through, stop-first).

Usage: python run_engine_seed.py --seed 1 [--shifts 0,1,2,3]
Run through heavy_slot (one heavy job), AFTER GPU inference for that seed.
Output: tmp/runs_seed{S}.pkl  {shift: {"K2": {run, wins, mult}}}.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
KH = HERE.parent / "oc_kronoshidden"
TMP = HERE / "tmp"

sys.path.insert(0, str(KH))
import run_engine as re  # noqa: E402  (read-only import, never edited)

Y4_START = pd.Timestamp("2025-09-24", tz="UTC")


def combined_kron(seed: int):
    """(sym, T) -> low1 using original-1234 before Y4_START, seed-S in year 4."""
    ref = pd.read_parquet(KH / "kronos_features_4shift.parquet", columns=["sym", "shift", "T", "low1"])
    new = pd.read_parquet(HERE / f"kronos_features_seed{seed}.parquet", columns=["sym", "shift", "T", "low1"])
    lut: dict = {}
    for df, pred in ((ref, lambda t: pd.Timestamp(t) < Y4_START),
                     (new, lambda t: pd.Timestamp(t) >= Y4_START)):
        for s, sh, t, lo in zip(df["sym"], df["shift"], df["T"], df["low1"]):
            if pred(t):
                lut[(str(s), int(sh), pd.Timestamp(t))] = float(lo)
    del ref, new
    return lut


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--shifts", default="0,1,2,3")
    args = ap.parse_args()
    seed = int(args.seed)
    shifts = [int(s) for s in args.shifts.split(",")]
    assert (HERE / f"kronos_features_seed{seed}.parquet").exists(), f"seed {seed} features missing"
    fits = json.loads((KH / "fits.json").read_text())
    ctrl = json.loads((KH / "ctrl.json").read_text())
    lut = combined_kron(seed)
    print(f"seed {seed}: combined lookup bars={len(lut)}", flush=True)

    def patched_loader(shift):
        out = {}
        for (sym, sh, t), lo in lut.items():
            if sh == shift:
                out[(sym, pd.Timestamp(t))] = lo
        return out

    re.load_shift_kronos = patched_loader
    out_path = TMP / f"runs_seed{seed}.pkl"
    allres = {}
    if out_path.exists():
        allres = pickle.loads(out_path.read_bytes())
        print(f"seed {seed}: cached shifts {sorted(allres)}", flush=True)
    for shift in shifts:
        if "K2" in allres.get(shift, {}):
            print(f"seed {seed} shift {shift}: cached, skip", flush=True)
            continue
        s, res = re.run_shift(shift, ["K2"], "last", fits, ctrl)
        allres.setdefault(s, {}).update(res)
        out_path.write_bytes(pickle.dumps(allres))
        print(f"seed {seed} shift {s} cached", flush=True)
    print(f"seed {seed} ENGINE DONE shifts {sorted(allres)}", flush=True)


if __name__ == "__main__":
    main()
