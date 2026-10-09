"""oc_d_stagger: heavy perp-1m stagger rebuild (2021-2026).

VERBATIM compute_placebo_dip.build_base core with ONLY the live-window split +
halved weights (see PLAN.md). REF ledger is read-only (gate in compute script).

Grid: START 2020-08-01, phase offsets p*60, bars every 240 min; opens/sigma
pct_change rolling-360/min_periods-120/shift-1; TRADE_START 2021-09-24..2026-09-24.
Windows: V1 A=[5,64]+B=[35,94]; V2 A=[5,64]+B=[95,154] (absolute bar offsets).
Weights 0.5*B1 at own fill minute; outcomes VERBATIM outcome_mu; kept per half iff
y09/y10/y11 all finite.

Output: tmp/stagger_2021_V1.npz + tmp/stagger_2021_V2.npz
(phase, coin, year, bar_time, rung, wA, yA, wB, yB, kindA, kindB).
Via heavy_slot, one coin H/L in RAM at a time, float32. Heartbeat 600 s.
Resume-safe per-(coin, phase) checkpoints.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TMP = HERE / "tmp"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "research" / "tournament" / "oc_placebo_dip"))
import stagger_rule as sr  # noqa: E402
import compute_placebo_dip as cpd  # noqa: E402 (read-only core reuse)

MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
PHASES = (0, 1, 2, 3)
WINDOWS = {"V1": sr.windows_V1(), "V2": sr.windows_V2()}
KIND = {"tp": 0, "time": 1, "stop": 2, "backstop": 3}
HB_S = 600


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="ALL")
    args = ap.parse_args()
    t0 = time.time()
    last_hb = t0
    TMP.mkdir(parents=True, exist_ok=True)
    variants = ("V1", "V2") if args.variant == "ALL" else (args.variant,)

    # shared OC grids (all coins O/C float32) + bar structure per phase
    O, C, base_idx = {}, {}, None
    for sym in MAJORS:
        ii, o, c = cpd.load_oc(sym)
        base_idx = ii if base_idx is None else base_idx
        O[sym], C[sym] = o, c
        print(f"loaded OC {sym}", flush=True)
    n_all = len(base_idx)
    grids = {}
    for p in PHASES:
        off = p * 60
        nb = (n_all - off) // 240
        t0b = base_idx[off:off + nb * 240:240]
        opens_bar, sig_bar = {}, {}
        for sym in MAJORS:
            ob = O[sym][off:off + nb * 240:240].astype(float)
            sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            opens_bar[sym], sig_bar[sym] = ob, sg
        js = [j for j in range(nb)
              if cpd.TRADE_START <= t0b[j] < cpd.YEAR_END and (off + j * 240 + 240) < n_all]
        grids[p] = dict(off=off, nb=nb, t0=t0b, opens=opens_bar, sig=sig_bar, js=js)
        print(f"shift {p}: nb={nb} traded={len(js)}", flush=True)

    coin_ix = {s: i for i, s in enumerate(MAJORS)}
    for variant in variants:
        (a0, a1), (b0, b1) = WINDOWS[variant][0], WINDOWS[variant][1]
        F = {k: [] for k in ("phase", "coin", "year", "bar_time", "rung",
                             "wA", "yA", "wB", "yB", "kindA", "kindB")}
        for sym in MAJORS:
            H, L = cpd.load_hl(sym, base_idx)
            others = [b for b in MAJORS if b != sym]
            for p in PHASES:
                ck = TMP / f"stagger_2021_{variant}_{sym}_p{p}.npz"
                if ck.exists():
                    d = np.load(ck)
                    for k in F:
                        F[k].extend(d[k].tolist())
                    print(f"{variant} {sym} p{p}: cached rows={len(d['wA'])}", flush=True)
                    continue
                G = {k: [] for k in F}
                g = grids[p]
                off, t0b = g["off"], g["t0"]
                opens_bar, sig_bar = g["opens"], g["sig"]
                n_rows = 0
                for j in g["js"]:
                    bt = t0b[j]
                    o1, sg = float(opens_bar[sym][j]), float(sig_bar[sym][j])
                    if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                        continue
                    base = off + j * 240
                    o2m = O[sym][base + 240]
                    o2 = float(o2m) if np.isfinite(o2m) else np.nan
                    settle = (bt + pd.Timedelta(hours=4)).hour in cpd.SETTLE_HOURS
                    yi = cpd.year_of(bt)
                    if yi is None:
                        continue
                    Ha_b = np.asarray(H[base:base + 240], dtype=float)
                    La_b = np.asarray(L[base:base + 240], dtype=float)
                    Ca_b = np.asarray(C[sym][base:base + 240], dtype=float)
                    Oa_b = np.asarray(O[sym][base:base + 240], dtype=float)
                    oo = np.array([opens_bar[b][j] for b in others], dtype=float)
                    ss = np.array([sig_bar[b][j] for b in others], dtype=float)
                    for ri, k in enumerate(cpd.RUNGS):
                        lv = o1 * (1 - k * sg)
                        if not np.isfinite(lv) or lv <= 0:
                            continue
                        halves = []
                        for (s0, s1) in ((a0, a1), (b0, b1)):
                            f = sr.find_fill_in(La_b, lv, s0, s1)
                            if f is None:
                                halves.append((0.0, 0.0, -1))
                                continue
                            c_others = np.array(
                                [float(C[b][base + f - 1]) for b in others])
                            nf = sr.n_at(c_others, oo, ss)
                            w = 0.5 / (1 + nf)
                            r09, _, _ = sr.outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg,
                                                      0.9, o2, settle)
                            r10, _, k10 = sr.outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg,
                                                        1.0, o2, settle)
                            r11, _, _ = sr.outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg,
                                                      1.1, o2, settle)
                            if not (np.isfinite(r09) and np.isfinite(r10) and np.isfinite(r11)):
                                halves.append((0.0, 0.0, -2))
                                continue
                            halves.append((w, float(r10), KIND[k10]))
                        (wA, yA, kA), (wB, yB, kB) = halves
                        if wA == 0.0 and wB == 0.0:
                            continue
                        G["phase"].append(p)
                        G["coin"].append(coin_ix[sym])
                        G["year"].append(yi)
                        G["bar_time"].append(base)
                        G["rung"].append(ri)
                        G["wA"].append(wA)
                        G["yA"].append(yA)
                        G["wB"].append(wB)
                        G["yB"].append(yB)
                        G["kindA"].append(kA)
                        G["kindB"].append(kB)
                        n_rows += 1
                arr = {k: np.array(v) for k, v in G.items()}
                for k in ("phase", "coin", "year", "bar_time", "rung", "kindA", "kindB"):
                    arr[k] = arr[k].astype(np.int64)
                for k in ("wA", "yA", "wB", "yB"):
                    arr[k] = arr[k].astype(np.float64)
                np.savez_compressed(ck, **arr)
                for k in F:
                    F[k].extend(G[k])
                print(f"{variant} {sym} p{p}: rows={n_rows} elapsed {(time.time()-t0)/60:.1f}min",
                      flush=True)
                if time.time() - last_hb >= HB_S:
                    last_hb = time.time()
                    print(f"[hb] build_2021 alive elapsed {last_hb-t0:.0f}s", flush=True)
            del H, L
        arr = {k: np.array(v) for k, v in F.items()}
        for k in ("phase", "coin", "year", "bar_time", "rung", "kindA", "kindB"):
            arr[k] = arr[k].astype(np.int64)
        for k in ("wA", "yA", "wB", "yB"):
            arr[k] = arr[k].astype(np.float64)
        np.savez_compressed(TMP / f"stagger_2021_{variant}.npz", **arr)
        print(f"{variant}: merged rows={len(arr['wA'])}", flush=True)


if __name__ == "__main__":
    main()
