"""oc_amihudrobust vectorised proxy: 500 timing placebos + per-coin decomposition.

PLAN-fixed (see PLAN.md). Reuses research/tournament/oc_bookattrib/
analyze_bookattrib.py READ-ONLY (G2 validation, standard books, shifted 1m
opens). Proxy: w = bear-filtered standard books (or A1-tilted) ffill to shifted
clocks; r = next-bar open-to-open on that shift's opens; B = sum(w*r) per bar;
cumprod per [A,A+365d) wall-clock year; monthly geometric; 4-phase mean of R.
Proxy is gross timing (no limit-fill/stop microstructure): levels need not match
the gated engine, only the ordering (A1 vs G2 vs placebo vs static-proxy).

Placebo (500 draws, seed 12345, pre-registered): per anchor year independently,
per coin independently, circular-shift the RAW Amihud30 series on the
standard-book index by a random multiple of 30 days (180 4h bars; offsets
{0,180,...,1980} bars drawn uniformly), then recompute the XS z at each T
(same ddof=1 rule) and the A1 multiplier (1+0.25*z, clip [0.5,1.5]); evaluate
the proxy dev4 mean. Report distribution + A1 percentile.

Per-coin decomposition: same proxy per coin c (bc = w_c*r_c) for G2 vs A1;
gain per coin per year and dev4; share of total A1-G2 proxy gain.

Run (1m opens -> shared semaphore):
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_amihudrobust_vec --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_amihudrobust/analyze_placebo_coin.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from amihud_signal import SYMS, a1_mult, clip_mult, raw_amihud_matrix, xs_z

BOOKATTRIB = ROOT / "research/tournament/oc_bookattrib/analyze_bookattrib.py"
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR = pd.Timedelta(days=365)
NPERM = 500
SEED = 12345
BAR30D = 180  # 30 days x 6 4h-bars/day
OFFSETS = [i * BAR30D for i in range(12)]  # 0..1980 bars


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def monthly_geometric(end_factor: float) -> float:
    return 100 * (float(end_factor) ** (1 / 12) - 1)


def proxy_year_R(w: np.ndarray, r: np.ndarray, t_idx: pd.DatetimeIndex,
                 valid: np.ndarray, a0: pd.Timestamp) -> tuple[float, float]:
    a1 = a0 + YEAR
    m = (t_idx >= a0) & (t_idx < a1) & valid
    b = (w[m] * r[m]).sum(axis=1)
    E = float(np.prod(1 + b))
    return monthly_geometric(E), float(np.prod(1 + b) - 1)


def main():
    t_start = time.time()
    BA = _load("ba_amihudrobust", BOOKATTRIB)
    print("validating G2 baseline ...", flush=True)
    BA.validate_g2()
    print("loading standard books ...", flush=True)
    books154, opens_std, std_nobear, sb_std, bear_std = BA.load_books_standard()
    cols = list(books154.columns)
    assert cols == SYMS or set(cols) == set(SYMS), cols
    # align column order to SYMS
    sb_std = sb_std[SYMS]
    print("loading shifted opens (1m open column only) ...", flush=True)
    shifted = BA.load_shifted_opens()

    # ---- standard-index A1 frame (frozen) ----
    T_std = sb_std.index
    Tts = pd.to_datetime(T_std, utc=True)
    f_a1, info_a1 = a1_mult(T_std, cols=SYMS)
    f_a1.loc[Tts < pd.Timestamp("2021-09-24", tz="UTC")] = 1.0
    print(f"A1 coverage all-finite: {info_a1['cov']:.4f}", flush=True)
    sbv = sb_std.to_numpy(float)
    a1v = f_a1.to_numpy(float)
    g2_books_std = sb_std
    a1_books_std = sb_std.copy()
    a1_books_std[:] = np.where(sbv != 0, sbv * a1v, sbv)

    # ---- proxy for G2 and A1 (per shift, per year) ----
    def proxy_rows(books_std: pd.DataFrame):
        per_shift = {}
        for shift in range(4):
            idx, opens = shifted[shift]
            o = opens[SYMS].to_numpy(float)
            r = o[1:] / o[:-1] - 1
            w = books_std.reindex(idx, method="ffill").fillna(0.0).to_numpy(float)[:-1]
            t_idx = idx[:-1]
            valid = np.isfinite(o[:-1]).all(axis=1) & np.isfinite(o[1:]).all(axis=1)
            yrs = []
            for a0 in ANCH:
                R, _ = proxy_year_R(w, r, t_idx, valid, a0)
                yrs.append(R)
            per_shift[shift] = yrs
        # 4-phase mean per year, then geometric dev4/5y
        mean_yrs = [round(float(np.mean([per_shift[s][y] for s in range(4)])), 3)
                    for y in range(5)]
        dev4 = round(float(100 * (np.prod([1 + v / 100 for v in mean_yrs[:4]]) ** (1 / 4) - 1)), 3)
        y5 = round(float(100 * (np.prod([1 + v / 100 for v in mean_yrs]) ** (1 / 5) - 1)), 3)
        return per_shift, mean_yrs, dev4, y5

    g2_ps, g2_my, g2_dev4, g2_5y = proxy_rows(g2_books_std)
    a1_ps, a1_my, a1_dev4, a1_5y = proxy_rows(a1_books_std)
    print(f"proxy G2 mean-years {g2_my} dev4 {g2_dev4} 5y {g2_5y}", flush=True)
    print(f"proxy A1 mean-years {a1_my} dev4 {a1_dev4} 5y {a1_5y}", flush=True)

    # ---- per-coin decomposition (proxy) ----
    per_coin = []
    for yi, a0 in enumerate(ANCH):
        row = {"anchor": str(a0.date()), "coins": []}
        for ci, sym in enumerate(SYMS):
            rs = []
            for shift in range(4):
                idx, opens = shifted[shift]
                o = opens[SYMS].to_numpy(float)
                r = o[1:] / o[:-1] - 1
                wg = g2_books_std.reindex(idx, method="ffill").fillna(0.0).to_numpy(float)[:-1]
                wa = a1_books_std.reindex(idx, method="ffill").fillna(0.0).to_numpy(float)[:-1]
                t_idx = idx[:-1]
                valid = np.isfinite(o[:-1]).all(axis=1) & np.isfinite(o[1:]).all(axis=1)
                a1x = a0 + YEAR
                m = (t_idx >= a0) & (t_idx < a1x) & valid
                bg = (wg[m][:, ci] * r[m][:, ci])
                ba = (wa[m][:, ci] * r[m][:, ci])
                Rg = monthly_geometric(float(np.prod(1 + bg)))
                Ra = monthly_geometric(float(np.prod(1 + ba)))
                rs.append((Rg, Ra))
            Rg4 = round(float(np.mean([x[0] for x in rs])), 3)
            Ra4 = round(float(np.mean([x[1] for x in rs])), 3)
            row["coins"].append({"sym": sym, "G2_R": Rg4, "A1_R": Ra4,
                                 "gain_pp": round(Ra4 - Rg4, 3)})
        gains = [c["gain_pp"] for c in row["coins"]]
        tot = round(float(sum(gains)), 3)
        row["total_gain_pp"] = tot
        # share of positive part (labelled; can be negative per coin)
        row["share"] = {c["sym"]: (round(c["gain_pp"] / tot, 4) if tot != 0 else 0.0)
                        for c in row["coins"]}
        per_coin.append(row)
        print(f"coin Y{yi} {a0.date()}: " + " ".join(
            f"{c['sym']} G2={c['G2_R']:.3f} A1={c['A1_R']:.3f} g={c['gain_pp']:+.3f}"
            for c in row["coins"]), flush=True)
    dev4_gain = [round(float(sum(y["coins"][ci]["gain_pp"] for y in per_coin[:4]
                                 for _ in [0]) / 4), 3) for ci in range(5)]
    # simpler: mean yearly gain per coin over dev4
    dev4_gain = [round(float(np.mean([per_coin[y]["coins"][ci]["gain_pp"] for y in range(4)])), 3)
                 for ci in range(5)]
    print("dev4 mean yearly gain per coin:",
          dict(zip(SYMS, dev4_gain)), flush=True)

    # ---- 500 placebos on the proxy ----
    ami_std = raw_amihud_matrix(T_std, 30, 20, SYMS)  # (nT, 5)
    # year slices on standard index
    bounds = ANCH + [ANCH[-1] + YEAR]
    year_sel = [np.asarray((Tts >= bounds[k]) & (Tts < bounds[k + 1])) for k in range(5)]
    rng = np.random.default_rng(SEED)
    # pre-draw offsets: (500, 5 years, 5 coins) indices into OFFSETS
    draw = rng.integers(0, len(OFFSETS), size=(NPERM, 5, 5))
    placebo_dev4 = np.empty(NPERM)
    t_p0 = time.time()
    for p in range(NPERM):
        ami_p = ami_std.copy()
        for k in range(5):
            sel = np.where(year_sel[k])[0]
            n = len(sel)
            if n == 0:
                continue
            for ci in range(5):
                off = OFFSETS[int(draw[p, k, ci])] % max(n, 1)
                if off:
                    ami_p[sel, ci] = np.roll(ami_std[sel, ci], off)
        z_p = xs_z(ami_p)
        m_p = clip_mult(1.0 + 0.25 * np.where(np.isfinite(z_p), z_p, np.nan))
        mp_frame = pd.DataFrame(m_p, index=T_std, columns=SYMS)
        mp_frame.loc[Tts < pd.Timestamp("2021-09-24", tz="UTC")] = 1.0
        books_p = sb_std.copy()
        books_p[:] = np.where(sbv != 0, sbv * mp_frame.to_numpy(float), sbv)
        _, mean_yrs_p, dev4_p, _ = proxy_rows(books_p)
        placebo_dev4[p] = dev4_p
        if (p + 1) % 50 == 0:
            print(f"placebo {p+1}/{NPERM} dev4={dev4_p:.3f} "
                  f"({(time.time()-t_p0)/60:.1f} min elapsed)", flush=True)
    pct = float((placebo_dev4 <= a1_dev4).mean())
    print(f"A1 proxy dev4 {a1_dev4:.3f}; placebo mean {placebo_dev4.mean():.3f} "
          f"sd {placebo_dev4.std():.3f} min {placebo_dev4.min():.3f} "
          f"max {placebo_dev4.max():.3f}; percentile {100*pct:.1f}%", flush=True)

    out = {
        "meta": {
            "proxy": "oc_bookattrib replica (bear-ffill books, next-bar open-to-open, "
                     "cumprod per [A,A+365d), 4-phase mean of R)",
            "placebo": "500 draws, seed 12345, per-year per-coin circular shift of RAW "
                       "Amihud30 by {0,30,...,330}d (180-bar multiples), XS z recomputed, "
                       "A1 mult 1+0.25z clip [0.5,1.5]; vectorised proxy (not engine), stated per PLAN",
            "engine_cost_note": "50 full-engine runs x4 phases would add ~200 phase replays; "
                               "used the assignment-allowed proxy instead",
            "g2_validation": "BA.validate_g2() asserts to the digit in-script",
        },
        "proxy_G2": {"mean_years": g2_my, "dev4": g2_dev4, "y5": g2_5y,
                     "per_shift": {str(k): v for k, v in g2_ps.items()}},
        "proxy_A1": {"mean_years": a1_my, "dev4": a1_dev4, "y5": a1_5y,
                     "per_shift": {str(k): v for k, v in a1_ps.items()}},
        "per_coin": per_coin,
        "per_coin_dev4_mean_gain_pp": dict(zip(SYMS, dev4_gain)),
        "placebo": {
            "n": NPERM, "seed": SEED,
            "dev4_list": [round(float(v), 3) for v in placebo_dev4],
            "mean": round(float(placebo_dev4.mean()), 3),
            "sd": round(float(placebo_dev4.std()), 3),
            "min": round(float(placebo_dev4.min()), 3),
            "max": round(float(placebo_dev4.max()), 3),
            "a1_dev4": a1_dev4,
            "percentile": round(100 * pct, 1),
        },
    }
    (HERE / "tmp" / "placebo_coin_raw.json").write_text(json.dumps(out, indent=1, default=str))
    (HERE / "placebo_coin_results.json").write_text(json.dumps(out, indent=1, default=str))
    print(f"wrote tmp/placebo_coin_raw.json ({(time.time()-t_start)/60:.1f} min total)", flush=True)


if __name__ == "__main__":
    main()
