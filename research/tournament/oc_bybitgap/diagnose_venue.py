"""oc_bybitgap diagnose_venue: descriptive venue-gap decomposition (no rule change).

PLAN-fixed (see PLAN.md). Steps:
 0. Reproduction gate from published JSONs (no new 4-phase engine; two prior
    studies already reproduce G2/G2_S5 to the digit with the identical harness).
 1. Quote book-vs-dip (oc_bookvenue single-phase, labelled) and per-coin B1
    (oc_venuegap) aggregates read-only.
 2. NEW light price-series diagnostics per coin (streaming, one coin at a time):
    close basis, low/wick diffs, 4h-open shift, venue-native sigma ratio, and
    trade-through agreement at the book limit and dip rungs (strict low < lv,
    live minutes 16..238, venue-native O/sg).

Fill timing: strict trade-through, no fill first 5 min (live starts minute 16
here, stricter than win_start=5, so agreement rates are conservative labels);
stop-first and funding are quoted from oc_bookvenue, not recomputed here.

Usage (HEAVY slot because 1m scans exceed 0.4 GB without it):
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_bybitgap_diag --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_bybitgap/diagnose_venue.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"

MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
OVERLAP_START = pd.Timestamp("2021-11-15 00:00", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
WARM = pd.Timestamp("2021-09-01 00:00", tz="UTC")
BIN_BTC = ROOT / "data/raw/btc_intraday_20260924"
BIN_MAJ = ROOT / "data/raw/majors_intraday_20260924"
BYB_DIR = ROOT / "data/raw/bybit_linear_1m_20261004"

# Assignment facts to reproduce (oc_amihudrobust engine_results.json, dev4 + 5y)
EXP = {
    "G2_dev4": 5.601, "G2_5y": 5.410, "G2_full": 16.82,
    "G2S5_dev4": 4.994, "G2S5_5y": 4.883, "G2S5_full": 18.09,
    "G2_years": [2.588, 3.282, 6.045, 10.677],
    "G2S5_years": [2.129, 2.735, 4.932, 10.377],
    "G2_Y4": 4.648, "G2S5_Y4": 4.443,
}


def load_binance(sym: str) -> pd.DataFrame:
    if sym == "BTCUSDT":
        files = sorted(BIN_BTC.glob("klines_1m_20*.parquet"))
    else:
        files = sorted(BIN_MAJ.glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"])
             for f in files]
    m = pd.concat(parts, ignore_index=True)
    del parts
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= WARM) & (m["open_time"] < END)]
    return m.set_index("open_time").sort_index()


def load_bybit(sym: str) -> pd.DataFrame:
    m = pd.read_parquet(BYB_DIR / f"{sym}_1m.parquet",
                        columns=["open_time", "open", "high", "low", "close"])
    m["open_time"] = pd.to_datetime(m["open_time"], unit="ms", utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= WARM) & (m["open_time"] < END)]
    return m.set_index("open_time").sort_index()


def sigma_4h(opens_4h: pd.Series) -> pd.Series:
    return (opens_4h.astype(float).pct_change()
            .rolling(360, min_periods=120).std(ddof=1).shift(1))


def qstats_bps(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return dict(n=0, median=None, p50_abs=None, p90_abs=None,
                    p95_abs=None, mean_abs=None)
    a = np.abs(x)
    return dict(n=int(len(x)), median=round(float(np.median(x)), 3),
                p50_abs=round(float(np.median(a)), 3),
                p90_abs=round(float(np.percentile(a, 90)), 3),
                p95_abs=round(float(np.percentile(a, 95)), 3),
                mean_abs=round(float(a.mean()), 3))


def main() -> None:
    t_all = time.time()
    # ---- 0. reproduction gate (JSON only, read-only) ----
    rob = json.loads((ROOT / "research/tournament/oc_amihudrobust/engine_results.json").read_text())
    assert rob["dev4"]["G2"]["R"] == EXP["G2_dev4"], rob["dev4"]["G2"]
    assert rob["rows"]["G2"]["R"] == EXP["G2_5y"], rob["rows"]["G2"]
    assert rob["rows"]["G2"]["full_path_dd"] == EXP["G2_full"], rob["rows"]["G2"]
    assert rob["dev4"]["G2_S5"]["R"] == EXP["G2S5_dev4"], rob["dev4"]["G2_S5"]
    assert rob["rows"]["G2_S5"]["R"] == EXP["G2S5_5y"], rob["rows"]["G2_S5"]
    assert rob["rows"]["G2_S5"]["full_path_dd"] == EXP["G2S5_full"], rob["rows"]["G2_S5"]
    gy = [r for r, _ in rob["dev4"]["G2"]["years"]]
    sy = [r for r, _ in rob["dev4"]["G2_S5"]["years"]]
    assert gy == EXP["G2_years"], gy
    assert sy == EXP["G2S5_years"], sy
    assert rob["rows"]["G2"]["years"][4][0] == EXP["G2_Y4"]
    assert rob["rows"]["G2_S5"]["years"][4][0] == EXP["G2S5_Y4"]
    v421res = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    assert v421res["R"] == 5.41 and v421res["full_path_dd"] == 16.82
    print("reproduction gate PASS: G2 5.601/5.410/16.82 vs G2_S5 4.994/4.883/18.09", flush=True)
    gaps = [round(g - s, 3) for g, s in zip(gy, sy)]
    print(f"dev4 yearly gaps (G2-G2_S5): {gaps} mean={round(sum(gaps)/4,3)}; "
          f"5y gap={round(EXP['G2_5y']-EXP['G2S5_5y'],3)}; "
          f"Y4 gap={round(EXP['G2_Y4']-EXP['G2S5_Y4'],3)}", flush=True)

    # ---- quoted book/dip + per-coin blocks (read-only reuse) ----
    bookvenue = json.loads((ROOT / "research/diagnostics/oc_bookvenue/results.json").read_text())
    venuegap = json.loads((ROOT / "research/tournament/oc_venuegap/results.json").read_text())
    print("quoted aggregates loaded: oc_bookvenue shifts "
          f"{sorted(bookvenue['shifts'])}; oc_venuegap gap_total_sum="
          f"{round(venuegap['gap_total_sum'],3)}", flush=True)

    # ---- 1. new price diagnostics, streaming per coin ----
    grid = pd.date_range(WARM, END, freq="4h", tz="UTC")
    overlap_bars = grid[(grid >= OVERLAP_START) & (grid < END)]
    per_coin, fill_agree, sigma_cmp = [], [], []
    for ci, sym in enumerate(MAJORS):
        t0 = time.time()
        print(f"[{ci+1}/5] {sym}: loading 1m... (elapsed "
              f"{(time.time()-t_all)/60:.1f} min)", flush=True)
        b = load_binance(sym)
        y = load_bybit(sym)
        common = b.index.intersection(y.index).sort_values()
        # paired minute closes/lows over the overlap live region only
        ov = common[(common >= OVERLAP_START) & (common < END)]
        cb = b.loc[ov, "close"].to_numpy(float)
        cy = y.loc[ov, "close"].to_numpy(float)
        lb_all = b.loc[ov, "low"].to_numpy(float)
        ly_all = y.loc[ov, "low"].to_numpy(float)
        ob_all = b.loc[ov, "open"].to_numpy(float)
        oy_all = y.loc[ov, "open"].to_numpy(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            basis = (cy - cb) / cb * 1e4
            lowdiff = (ly_all - lb_all) / cb * 1e4
        # wick depth: min(O,C)-L per minute, paired diff (byb-bin) in bps of close
        wb = np.minimum(ob_all, cb) - lb_all
        wy = np.minimum(oy_all, cy) - ly_all
        with np.errstate(divide="ignore", invalid="ignore"):
            wdiff = (wy - wb) / cb * 1e4
        bs, ls, ws = qstats_bps(basis), qstats_bps(lowdiff), qstats_bps(wdiff)
        # 4h opens + venue-native sigma
        gb = b["open"].reindex(grid).to_numpy(float)
        gy_ = y["open"].reindex(grid).to_numpy(float)
        sgb = sigma_4h(pd.Series(gb, index=grid)).to_numpy(float)
        sgy = sigma_4h(pd.Series(gy_, index=grid)).to_numpy(float)
        m_ov = (grid >= OVERLAP_START) & (grid < END)
        with np.errstate(divide="ignore", invalid="ignore"):
            oshift = (gy_[m_ov] - gb[m_ov]) / gb[m_ov] * 1e4
        os_ = qstats_bps(oshift)
        ok = (np.isfinite(gb[m_ov]) & np.isfinite(gy_[m_ov])
              & np.isfinite(sgb[m_ov]) & np.isfinite(sgy[m_ov])
              & (gb[m_ov] > 0) & (gy_[m_ov] > 0)
              & (sgb[m_ov] > 0) & (sgy[m_ov] > 0))
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = sgy[m_ov][ok] / sgb[m_ov][ok]
            sdiff = (sgy[m_ov][ok] - sgb[m_ov][ok]) * 1e4  # sigma points x1e4
        sigma_cmp.append(dict(sym=sym, n=int(ok.sum()),
                              median_ratio=round(float(np.median(ratio)), 4) if ok.sum() else None,
                              p50_abs_ratio_dev=round(float(np.median(np.abs(ratio - 1)) * 1e4), 2) if ok.sum() else None,
                              median_sgb=round(float(np.median(sgb[m_ov][ok])), 6) if ok.sum() else None,
                              median_sgy=round(float(np.median(sgy[m_ov][ok])), 6) if ok.sum() else None))
        per_coin.append(dict(sym=sym, n_min=int(len(ov)), basis_bps=bs,
                             lowdiff_bps=ls, wickdiff_bps=ws, open_shift_bps=os_))
        # ---- trade-through agreement per bar ----
        # positional map: minute position of each bar start in `ov`
        pos = ov.searchsorted(overlap_bars)
        n_bars = int(len(overlap_bars))
        levels = {"book": None, **{f"k{k}": k for k in RUNGS}}
        acc = {lv: dict(bars=0, both=0, bin_only=0, byb_only=0, neither=0)
               for lv in levels}
        cov_both = 0
        lb = b["low"].reindex(ov).to_numpy(dtype=np.float32)
        ly = y["low"].reindex(ov).to_numpy(dtype=np.float32)
        for j in range(n_bars):
            p = int(pos[j])
            if p < 0 or p + 239 >= len(ov):
                continue
            # bar open must equal the minute open at p on both venues
            i4 = int(np.searchsorted(grid.values.astype(np.int64), overlap_bars[j].value))
            Ob, sb = float(gb[i4]), float(sgb[i4])
            Oy, sy_ = float(gy_[i4]), float(sgy[i4])
            if not (np.isfinite(Ob) and np.isfinite(Oy) and Ob > 0 and Oy > 0):
                continue
            win_b = lb[p + LIVE_A:p + LIVE_B + 1].astype(float)
            win_y = ly[p + LIVE_A:p + LIVE_B + 1].astype(float)
            if not (np.isfinite(win_b).all() and np.isfinite(win_y).all()):
                # require full live window on both venues (else skip bar)
                if not (np.isfinite(win_b).any() and np.isfinite(win_y).any()):
                    continue
            cov_both += 1
            lv_map = {}
            if np.isfinite(sb) and sb > 0:
                lv_map["book"] = Ob * (1 - max(0.001, 0.25 * sb))
                for k in RUNGS:
                    lv_map[f"k{k}"] = Ob * (1 - k * sb)
            else:
                continue
            if not (np.isfinite(sy_) and sy_ > 0):
                continue
            lv_map_y = {"book": Oy * (1 - max(0.001, 0.25 * sy_))}
            for k in RUNGS:
                lv_map_y[f"k{k}"] = Oy * (1 - k * sy_)
            for lvk in levels:
                a = acc[lvk]
                a["bars"] += 1
                fb = bool(np.any(win_b < lv_map[lvk]))
                fy = bool(np.any(win_y < lv_map_y[lvk]))
                if fb and fy:
                    a["both"] += 1
                elif fb:
                    a["bin_only"] += 1
                elif fy:
                    a["byb_only"] += 1
                else:
                    a["neither"] += 1
        for lvk, a in acc.items():
            d = a["both"] + a["bin_only"]
            e = a["both"] + a["byb_only"]
            fill_agree.append(dict(sym=sym, level=lvk, **a,
                                   p_byb_given_bin=round(a["both"]/d, 4) if d else None,
                                   p_bin_given_byb=round(a["both"]/e, 4) if e else None))
        print(f"[{ci+1}/5] {sym}: n_min={len(ov)} basis_med={bs['median']} "
              f"p95={bs['p95_abs']} open_med={os_['median']} cov_bars={cov_both} "
              f"({time.time()-t0:.0f}s; total {(time.time()-t_all)/60:.1f} min)", flush=True)
        del b, y, common, ov, cb, cy, lb_all, ly_all, lb, ly
        import gc
        gc.collect()

    out = {
        "meta": {
            "note": "descriptive only; no rule change; most-recent year quoted once as labelled byproduct",
            "overlap": "[2021-11-15, 2026-09-23]",
            "live_minutes": [LIVE_A, LIVE_B],
            "costs": "maker 0.0002 taker 0.00055 longs 0.0001/8h shorts 0; strict low<lv; stop-first (quoted)",
            "reproduction": "G2 dev4 5.601/5y 5.410/full 16.82; G2_S5 dev4 4.994/5y 4.883/full 18.09 (oc_amihudrobust to the digit); v421 5.41/16.82",
        },
        "reproduced_gaps": {
            "dev4_years_G2": EXP["G2_years"], "dev4_years_G2_S5": EXP["G2S5_years"],
            "dev4_gaps": gaps, "dev4_gap_mean": round(sum(gaps) / 4, 3),
            "gap_5y": round(EXP["G2_5y"] - EXP["G2S5_5y"], 3),
            "gap_Y4_labelled": round(EXP["G2_Y4"] - EXP["G2S5_Y4"], 3),
            "dd_full_G2": EXP["G2_full"], "dd_full_G2_S5": EXP["G2S5_full"],
        },
        "quoted_book_dip_split_single_phase": {
            s: {k: dict(monthly=bookvenue["shifts"][s]["runs"][k]["full"]["monthly"],
                        yearly=[r["monthly"] for r in bookvenue["shifts"][s]["runs"][k]["yearly"]],
                        book=bookvenue["shifts"][s]["runs"][k]["book"])
                for k in ("base", "s5", "book_byb", "book_bin")}
            for s in ("0", "2")
        },
        "quoted_B1_replica_rung_y": {
            "gap_total_sum": venuegap["gap_total_sum"],
            "per_coin_year": venuegap["per_coin_year"],
            "open_shift_bps": venuegap["open_shift_bps"],
        },
        "price_diagnostics": per_coin,
        "sigma_comparison": sigma_cmp,
        "fill_agreement": fill_agree,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("wrote results.json "
          f"(total {(time.time()-t_all)/60:.1f} min)", flush=True)


if __name__ == "__main__":
    sys.exit(main())
