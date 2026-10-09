"""oc_d_stagger: heavy spot-1m stagger rebuild (pre-sample).

VERBATIM presample core (build_ledger_presample) with ONLY the live-window split +
halved weights (see PLAN.md). REF ledger is read-only (reproduction gate checked in
compute_stagger_presample.py, not here).

Output: tmp/stagger_presample_V1.npz + tmp/stagger_presample_V2.npz with per-row
halves (a row = one (bar, coin, rung) where >= 1 half filled+kept):
  phase, coin, year, t_ord, rung, wA, yA, wB, yB, kindA, kindB
kinds: 0 tp / 1 time / 2 stop / 3 backstop (mu=1.0 branch).
Via heavy_slot. Heartbeat every 600 s. Resume-safe per-leg checkpoints.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TMP = HERE / "tmp"
SPOT = ROOT / "data" / "raw" / "spot_1m_presample_20261007"
sys.path.insert(0, str(HERE))
import stagger_rule as sr  # noqa: E402

RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
MAJORS4 = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
ORIGIN = pd.Timestamp("2020-01-01", tz="UTC")
PHASES = (0, 1, 2, 3)
LEGS = {
    "Y2017": (pd.Timestamp("2017-10-16", tz="UTC"), pd.Timestamp("2018-01-01", tz="UTC")),
    "Y2018": (pd.Timestamp("2018-01-01", tz="UTC"), pd.Timestamp("2019-01-01", tz="UTC")),
    "Y2019": (pd.Timestamp("2019-01-01", tz="UTC"), pd.Timestamp("2020-01-01", tz="UTC")),
    "Y2020p": (pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2020-09-01", tz="UTC")),
}
LEG_IDX = {"Y2017": 0, "Y2018": 1, "Y2019": 2, "Y2020p": 3}
EPOCH = pd.Timestamp("2017-08-01", tz="UTC")
SETTLE_HOURS = (0, 8, 16)
HB_S = 600
KIND = {"tp": 0, "time": 1, "stop": 2, "backstop": 3}

WINDOWS = {"V1": sr.windows_V1(), "V2": sr.windows_V2()}


def load_1m_spot(sym: str, start, end):
    m = pd.read_parquet(SPOT / f"{sym}.parquet")
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m[(m["open_time"] >= start) & (m["open_time"] <= end)]
    idx = pd.date_range(start, end, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    out = {k: m[k].to_numpy(dtype=np.float32) for k in ("o", "h", "l", "c")}
    del m
    return idx, out


def run_leg_variant(leg: str, variant: str):
    S, E = LEGS[leg]
    LS = S - pd.Timedelta(days=100)
    LE = E + pd.Timedelta(days=1)
    man = json.loads((SPOT / "manifest.json").read_text())["symbols"]
    store_warmup = {s: pd.Timestamp(man[s]["first_bar"]) + pd.Timedelta(days=60)
                    for s in MAJORS4}
    (wA0, wA1), (wB0, wB1) = WINDOWS[variant][0], WINDOWS[variant][1]
    idx = None
    D: dict = {}
    warmup_from: dict = {}
    for sym in MAJORS4:
        ii, d = load_1m_spot(sym, LS, LE)
        if idx is None:
            idx = ii
        dd = {"open": d["o"], "high": d["h"], "low": d["l"], "close": d["c"]}
        if np.isfinite(np.asarray(dd["close"], dtype=float)).sum() == 0:
            pass
        present = np.flatnonzero(np.isfinite(dd["close"]))
        if len(present) == 0:
            print(f"{leg} {variant} {sym}: no data; absent", flush=True)
            continue
        warmup_from[sym] = store_warmup[sym]
        D[sym] = dd
        print(f"{leg} {variant} {sym}: n={len(ii)} warm={warmup_from[sym]}", flush=True)
    coins = list(D.keys())
    grids = {}
    for s in PHASES:
        base = ORIGIN + pd.Timedelta(hours=s)
        j0 = int(np.floor(((idx[0] - pd.Timedelta(hours=4)) - base).total_seconds() / 14400))
        j1 = int(np.ceil(((idx[-1] + pd.Timedelta(hours=4)) - base).total_seconds() / 14400))
        bts = base + pd.to_timedelta(np.arange(j0, j1 + 1) * 4, unit="h")
        bts = bts[(bts >= idx[0]) & (bts + pd.Timedelta(hours=4) <= idx[-1])]
        offs = ((bts - idx[0]).total_seconds() // 60).astype(int)
        ob, sg = {}, {}
        for sym in coins:
            oo = D[sym]["open"][offs].astype(float)
            ob[sym] = oo
            sg[sym] = sr.compute_sigma(oo)
            mask = np.asarray(bts < warmup_from[sym])
            ob[sym] = np.where(mask, np.nan, ob[sym])
            sg[sym] = np.where(mask, np.nan, sg[sym])
        grids[s] = (bts, ob, sg)
    F = {k: [] for k in ("phase", "coin", "year", "t_ord", "rung",
                         "wA", "yA", "wB", "yB", "kindA", "kindB")}
    coin_ix = {s: i for i, s in enumerate(MAJORS4)}
    for s in PHASES:
        bts, ob, sg = grids[s]
        js = [j for j, T in enumerate(bts) if S <= T < E]
        print(f"{leg} {variant} s{s}: bars={len(js)}", flush=True)
        for j in js:
            T = bts[j]
            off = int((T - idx[0]).total_seconds() // 60)
            if off + 240 >= len(idx):
                continue
            settle = (T + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
            for sym in coins:
                o1, sgv = float(ob[sym][j]), float(sg[sym][j])
                if not (np.isfinite(o1) and np.isfinite(sgv)) or o1 <= 0 or sgv <= 0:
                    continue
                La = D[sym]["low"][off:off + 240].astype(float)
                Ha = D[sym]["high"][off:off + 240].astype(float)
                Ca = D[sym]["close"][off:off + 240].astype(float)
                Oa = D[sym]["open"][off:off + 240].astype(float)
                o2m = D[sym]["open"][off + 240]
                o2 = float(o2m) if np.isfinite(o2m) else np.nan
                others = [b for b in coins if b != sym]
                oo = np.array([float(ob[b][j]) for b in others])
                ss = np.array([float(sg[b][j]) for b in others])
                for ri, k in enumerate(RUNGS):
                    lv = o1 * (1 - k * sgv)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    halves = []
                    for (a0, a1) in ((wA0, wA1), (wB0, wB1)):
                        f = sr.find_fill_in(La, lv, a0, a1)
                        if f is None:
                            halves.append((0.0, 0.0, -1))
                            continue
                        if others:
                            c_others = np.array(
                                [float(D[b]["close"][off + f - 1]) for b in others])
                        else:
                            c_others = np.array([])
                        nf = sr.n_at(c_others, oo, ss)
                        w = 0.5 / (1 + nf)
                        r09, _, _ = sr.outcome_mu(Ha, La, Ca, Oa, f, lv, sgv, 0.9, o2, settle)
                        r10, x10, k10 = sr.outcome_mu(Ha, La, Ca, Oa, f, lv, sgv, 1.0, o2, settle)
                        r11, _, _ = sr.outcome_mu(Ha, La, Ca, Oa, f, lv, sgv, 1.1, o2, settle)
                        if not (np.isfinite(r09) and np.isfinite(r10) and np.isfinite(r11)):
                            halves.append((0.0, 0.0, -2))
                            continue
                        halves.append((w, float(r10), KIND[k10]))
                    (wA, yA, kA), (wB, yB, kB) = halves
                    if wA == 0.0 and wB == 0.0:
                        continue
                    F["phase"].append(s)
                    F["coin"].append(coin_ix[sym])
                    F["year"].append(LEG_IDX[leg])
                    F["t_ord"].append(int((T - EPOCH).total_seconds() // 60))
                    F["rung"].append(ri)
                    F["wA"].append(wA)
                    F["yA"].append(yA)
                    F["wB"].append(wB)
                    F["yB"].append(yB)
                    F["kindA"].append(kA)
                    F["kindB"].append(kB)
    del D, grids
    return F


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="ALL")
    ap.add_argument("--leg", default="ALL")
    args = ap.parse_args()
    t0 = time.time()
    last_hb = t0
    TMP.mkdir(parents=True, exist_ok=True)
    variants = ("V1", "V2") if args.variant == "ALL" else (args.variant,)
    legs = ("Y2017", "Y2018", "Y2019", "Y2020p") if args.leg == "ALL" else (args.leg,)
    for variant in variants:
        for leg in legs:
            ck = TMP / f"stagger_presample_{leg}_{variant}.npz"
            if ck.exists():
                print(f"{leg} {variant}: cached {ck.name}", flush=True)
                continue
            F = run_leg_variant(leg, variant)
            arr = {k: np.array(v) for k, v in F.items()}
            for k in ("phase", "coin", "year", "t_ord", "rung", "kindA", "kindB"):
                arr[k] = arr[k].astype(np.int64)
            for k in ("wA", "yA", "wB", "yB"):
                arr[k] = arr[k].astype(np.float64)
            np.savez_compressed(ck, **arr)
            print(f"{leg} {variant}: rows={len(arr['wA'])} elapsed {(time.time()-t0)/60:.1f}min",
                  flush=True)
            if time.time() - last_hb >= HB_S:
                last_hb = time.time()
                print(f"[hb] build_stagger_presample alive elapsed {last_hb-t0:.0f}s", flush=True)
        # merge legs
        parts = []
        for leg in ("Y2017", "Y2018", "Y2019", "Y2020p"):
            d = np.load(TMP / f"stagger_presample_{leg}_{variant}.npz")
            parts.append(d)
        keys = ("phase", "coin", "year", "t_ord", "rung", "wA", "yA", "wB", "yB", "kindA", "kindB")
        merged = {k: np.concatenate([p[k] for p in parts]).astype(
            np.int64 if k not in ("wA", "yA", "wB", "yB") else np.float64) for k in keys}
        np.savez_compressed(TMP / f"stagger_presample_{variant}.npz", **merged)
        print(f"{variant}: merged rows={len(merged['wA'])}", flush=True)


if __name__ == "__main__":
    main()
