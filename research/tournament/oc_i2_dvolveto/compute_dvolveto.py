"""oc_i2_dvolveto: DVOL-spike (CHANGE, not level) dip veto — IDEAS2 §1.

Pre-registered in REPORT.md §0 BEFORE any run (V1 dip veto; V2 = V1 +
halve book longs on spike days, diagnostic only). Read-only inputs, no
engine reruns unless the dip screen passes its gate.

Spike definition (leak-free, day level):
  D(d)     = BTC DVOL hourly close of the bar END == midnight (d+1) 00:00 UTC
             (the 23:00-00:00 bar; uses only closes with END <= that midnight).
  chg(d)   = D(d) - D(d-1), finalised at the start of day d+1.
  q95_k    = 95th pct of chg over the trailing 90d window FIT_k =
             [A_k - 100d, A_k - 10d) (pre-anchor + 10d embargo; never test data).
  veto(x)  = chg(x-1) > q95_k for calendar day x in anchor year k
             (yesterday's FINALISED daily change only; never the spike-day
             close itself). A 4h signal bar T is flagged iff veto(date(T)).
  Expectation: ~5% x 365 ≈ 18 veto-days/yr (matches the idea's 10-20/yr).

V1: skip NEW dip bids on flagged signal bars (holds/exits unchanged).
V2: V1 + halve BOOK longs (w>0 -> 0.5w) on flagged bars (vectorised
    open-to-open diagnostic only; book claims need the 4-phase engine).

Screen: exact oc_dipexit D0 + B1 replica on all 4 clock phases (reuses the
audited oc_placebo_dip core by import; same costs), scored with the same
4-phase-mean criterion + placebo gate dSum5y >= +0.273. Engine only if pass.

Usage:
  python research/tournament/oc_i2_dvolveto/compute_dvolveto.py --spike-only
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_i2_dvolveto \\
    --min-free-gb 2.0 -- .venv/Scripts/python.exe \\
    research/tournament/oc_i2_dvolveto/compute_dvolveto.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RAW = ROOT / "data/raw/deribit_dvol_20261005"
RAW_OLD = ROOT / "data/raw/dvol_20260924"
PLACEBO = ROOT / "research/tournament/oc_placebo_dip"
CACHE = ROOT / "artifacts/research/engine_real"

ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
FIT_LEN_D = 90
EMBARGO_D = 10
NS = 1_000_000_000
H = 3_600 * NS
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
MAKER = 0.0002


# --------------------------------------------------------------------------
# DVOL loading (same raw parse as oc_dvol.load_dvol, BTC only here)
# --------------------------------------------------------------------------
def load_dvol_btc(raw_dir: Path = RAW) -> tuple[np.ndarray, np.ndarray]:
    """(bar_END_ns sorted int64, closes float64) for BTC DVOL, END < CUTOFF."""
    ts, cl = [], []
    for fp in sorted(raw_dir.glob("BTC_*.json")):
        p = json.loads(fp.read_text())
        for c in p["candles"]:
            ts.append((int(c[0]) + 3_600_000) * 1_000_000)  # bar END, ns
            cl.append(float(c[4]))
    ts = np.array(ts, dtype=np.int64)
    cl = np.array(cl, dtype=float)
    o = np.argsort(ts)
    ts, cl = ts[o], cl[o]
    _, u = np.unique(ts, return_index=True)
    mask = np.zeros(len(ts), bool)
    mask[u] = True
    cutoff_ns = int(pd.Timestamp("2026-09-24", tz="UTC").value)
    mask &= (ts - 3_600 * NS) < cutoff_ns
    return ts[mask], cl[mask]


def daily_series(ends: np.ndarray, closes: np.ndarray) -> pd.DataFrame:
    """Daily DVOL closes D(d) at each midnight END; chg(d) = D(d)-D(d-1)."""
    idx = pd.to_datetime(ends, utc=True, unit="ns")
    s = pd.Series(closes, index=idx).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    midnights = pd.date_range(s.index[0].ceil("D"), s.index[-1].floor("D"),
                              freq="D", tz="UTC")
    D = s.reindex(midnights)
    out = pd.DataFrame({"midnight": midnights, "D": D.to_numpy(float)})
    out["day"] = out["midnight"] - pd.Timedelta(days=1)  # day the close belongs to
    out["chg"] = out["D"].diff()
    return out.reset_index(drop=True)


def fit_thresholds(daily: pd.DataFrame) -> dict:
    """q95_k per anchor year over FIT_k = [A_k-100d, A_k-10d), on chg only."""
    q = {}
    for k, a0 in enumerate(ANCHORS):
        lo = a0 - pd.Timedelta(days=FIT_LEN_D + EMBARGO_D)
        hi = a0 - pd.Timedelta(days=EMBARGO_D)
        m = (daily["day"] >= lo.normalize()) & (daily["day"] < hi.normalize())
        v = daily.loc[m, "chg"].to_numpy(float)
        v = v[np.isfinite(v)]
        q[str(a0.date())] = {
            "q95": float(np.quantile(v, 0.95)) if len(v) >= 30 else float("nan"),
            "n_fit": int(len(v)),
            "fit_lo": str(lo.date()),
            "fit_hi_excl": str(hi.date()),
        }
    return q


def year_of(t: pd.Timestamp) -> int | None:
    for i in range(5):
        lo = ANCHORS[i]
        hi = ANCHORS[i + 1] if i < 4 else YEAR_END + pd.Timedelta(days=1)
        if lo <= t < hi:
            return i
    return None


def veto_for_days(days: pd.DatetimeIndex, daily: pd.DataFrame, q: dict) -> pd.Series:
    """veto(x) = chg(x-1) > q95_k(x). Strictly uses finalised values only."""
    chg_by_day = daily.set_index("day")["chg"]
    out = pd.Series(False, index=days)
    for x in days:
        k = year_of(x)
        if k is None:
            continue
        thr = q[str(ANCHORS[k].date())]["q95"]
        if not np.isfinite(thr):
            continue
        prev = x - pd.Timedelta(days=1)
        c = chg_by_day.get(prev, np.nan)
        out[x] = bool(np.isfinite(c) and c > thr)
    return out


def flag_for_bar(t: pd.Timestamp, veto_by_day: pd.Series) -> bool:
    """Signal bar T is flagged iff its calendar day is a veto day."""
    x = t.normalize()
    return bool(veto_by_day.get(x, False))


# --------------------------------------------------------------------------
# steps
# --------------------------------------------------------------------------
def step_baseline() -> dict:
    v = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421"
                    / "v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    c = json.loads((ROOT / "research/tournament/oc_carrycompound/results.json").read_text())
    g0, g1 = c["rows"]["G2_f0.0"], c["rows"]["G2_f0.25"]
    assert g0["R"] == v["R"] == 5.41 and g0["W"] == v["W"] == 2.588
    assert g0["DD"] == v["DD"] == 16.91 and g0["full_path_dd"]["full"] == v["full_path_dd"] == 16.82
    assert g1["R"] == 5.634 and g1["W"] == 2.778 and g1["DD"] == 16.75
    assert g1["full_path_dd"]["full"] == 16.66 and c["carry_add_pp_per_month"] == 0.224
    return {"v421_G2": v, "G2_f0": g0, "G2_carry_f025": g1,
            "carry_add": c["carry_add_pp_per_month"], "repro": "OK to the digit"}


def step_spike() -> dict:
    ends, closes = load_dvol_btc()
    dt0 = pd.to_datetime(ends[0], utc=True, unit="ns")
    dt1 = pd.to_datetime(ends[-1], utc=True, unit="ns")
    gaps = np.diff(ends) // H
    daily = daily_series(ends, closes)
    q = fit_thresholds(daily)
    days = pd.date_range("2021-09-24", "2026-09-23", freq="D", tz="UTC")
    veto = veto_for_days(days, daily, q)
    # cross-check vs the older dvol_20260924 BTC file
    old = pd.read_parquet(RAW_OLD / "dvol_hourly.parquet").sort_values("ts_utc")
    old["avail"] = pd.to_datetime(old["avail_utc"], utc=True)
    mg = daily.merge(old[["avail", "dvol_close"]], left_on="midnight",
                     right_on="avail", how="inner")
    xchk = (float(np.nanmax(np.abs(mg["D"] - mg["dvol_close"]))), int(len(mg))) \
        if len(mg) else (float("nan"), 0)
    per_year = []
    for k, a0 in enumerate(ANCHORS):
        m = (days >= a0) & (days < a0 + pd.Timedelta(days=365))
        per_year.append({"year": str(a0.date()), "q95": round(q[str(a0.date())]["q95"], 4),
                         "n_fit": q[str(a0.date())]["n_fit"],
                         "veto_days": int(veto[m].sum()), "n_days": int(m.sum())})
    veto.to_frame("veto").to_parquet(HERE / "tmp" / "veto_days.parquet")
    daily.to_parquet(HERE / "tmp" / "dvol_daily.parquet")
    (HERE / "tmp" / "spike_thresholds.json").write_text(json.dumps(q, indent=1))
    return {"span": [str(dt0), str(dt1)], "max_step_h": int(gaps.max()),
            "n_hourly": int(len(ends)),
            "old_file_maxabsdiff_n": list(xchk),
            "per_year": per_year,
            "veto_total_days": int(veto.sum())}


def _placebo():
    if str(PLACEBO) not in sys.path:
        sys.path.insert(0, str(PLACEBO))
    import compute_placebo_dip as P
    return P


def step_replica(veto: pd.Series) -> dict:
    """Full 4-phase D0+B1 replica (audited placebo core), V1 = skip flagged fills."""
    P = _placebo()
    led = P.build_base()
    START = P.START
    ts = START + pd.to_timedelta(led["bar_time"].astype(np.int64), unit="m")
    day = pd.DatetimeIndex(pd.to_datetime(ts).tz_convert("UTC").normalize())
    flag = np.array([bool(veto.get(d, False)) for d in day])
    keep = ~flag
    base_sc = P.score_assignment(led["phase"], led["year"], led["w"],
                                 led["y10"], led["d10"])
    v1_sc = P.score_assignment(led["phase"][keep], led["year"][keep],
                               led["w"][keep], led["y10"][keep], led["d10"][keep])
    dec = P.decide(v1_sc, base_sc)
    # fidelity vs the published placebo base
    ref_p0 = [2.388, 0.183, 3.810, 2.579, 0.712]
    got_p0 = []
    for y in range(5):
        m = (led["phase"] == 0) & (led["year"] == y)
        got_p0.append(float((led["w"][m] * led["y10"][m]).sum()))
    np.save(HERE / "tmp" / "ledger_flag.npy", flag)
    return {
        "n_fills": int(len(led["w"])), "n_skipped_veto": int(flag.sum()),
        "skip_share": round(float(flag.mean()), 6),
        "phase0_fidelity_got": [round(s, 4) for s in got_p0],
        "phase0_fidelity_ref": ref_p0,
        "phase0_maxabsdiff": round(float(max(abs(g - r) for g, r in zip(got_p0, ref_p0))), 4),
        "base_per_year": [
            {"S": round(r["S"], 6), "DD": round(r["DD"], 6),
             "n": round(r["n"], 2), "win": round(r["win"], 6)} for r in base_sc["per_year"]],
        "base_sum5y": round(base_sc["sum5y"], 6),
        "v1_per_year": [
            {"S": round(r["S"], 6), "DD": round(r["DD"], 6),
             "n": round(r["n"], 2), "win": round(r["win"], 6)} for r in v1_sc["per_year"]],
        "v1_sum5y": round(v1_sc["sum5y"], 6),
        "decision": dec,
        "gate": 0.273,
    }


def step_book_diagnostic(veto: pd.Series) -> dict:
    """V2 book leg, vectorised open-to-open diagnostic (NOT an engine claim)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "oc_dvolshort_mod",
        ROOT / "research/tournament/oc_dvolshort/compute_dvolshort.py")
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)
    books = M.research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books.index)
    grid = books.index.intersection(opens.dropna(how="all").index)
    grid = grid[(grid >= ANCHORS[0]) & (grid < M.CUTOFF)].sort_values()
    books, opens = books.reindex(grid), opens.reindex(grid)
    o = opens[SYMS]
    fwd1 = o.shift(-1) / o - 1.0
    keep = (grid.shift(-1, freq=None) <= M.CUTOFF) if False else pd.Series(True, index=grid)
    # exit must exist: last bar dropped (same as oc_dvolshort via valid1)
    valid1 = fwd1.notna().all(axis=1)
    books, opens, fwd1 = books[valid1], opens[valid1], fwd1[valid1]
    grid = books.index
    day = grid.normalize()
    flag = np.array([bool(veto.get(d, False)) for d in day])
    flag_by_row = {}
    rows = []
    for s in SYMS:
        rows.append(pd.DataFrame({"T": grid, "sym": s,
                                  "w": books[s].to_numpy(float),
                                  "r1": fwd1[s].to_numpy(float),
                                  "flag": flag}))
    panel = pd.concat(rows, ignore_index=True)
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    w = panel["w"].to_numpy(float)
    r1 = panel["r1"].to_numpy(float)
    fl = panel["flag"].to_numpy(bool)
    w_g = w.copy()
    gated = fl & (w > 0)
    w_g[gated] = 0.5 * w[gated]
    cost = np.zeros(len(panel))
    cost_g = np.zeros(len(panel))
    sym = panel["sym"].to_numpy()
    T = panel["T"].to_numpy()
    for s in SYMS:
        sm = sym == s
        idx = np.where(sm)[0]
        order = np.argsort(T[idx])
        ii = idx[order]
        prev_w = np.concatenate([[0.0], w[ii][:-1]])
        prev_g = np.concatenate([[0.0], w_g[ii][:-1]])
        cost[ii] = MAKER * np.abs(w[ii] - prev_w)
        cost_g[ii] = MAKER * np.abs(w_g[ii] - prev_g)
    pnl = w * r1 - cost
    pnl_g = w_g * r1 - cost_g
    bounds = ANCHORS + [ANCHORS[-1] + pd.Timedelta(days=365)]
    bar = panel.groupby("T", sort=True)[["w"]].sum()  # placeholder index
    bar = pd.DataFrame({"pnl": panel.groupby("T", sort=True).apply(
        lambda g: float(pnl[g.index].sum()), include_groups=False),
        "pnl_g": panel.groupby("T", sort=True).apply(
        lambda g: float(pnl_g[g.index].sum()), include_groups=False)}).sort_index()
    years = []
    for k, a0 in enumerate(ANCHORS):
        sel = (bar.index >= bounds[k]) & (bar.index < bounds[k + 1])
        rp = bar.loc[sel, "pnl"].to_numpy()
        rp_g = bar.loc[sel, "pnl_g"].to_numpy()
        eq = np.concatenate([[1.0], np.cumprod(1.0 + rp)])
        eq_g = np.concatenate([[1.0], np.cumprod(1.0 + rp_g)])
        dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
        dd_g = float(np.max(1 - eq_g / np.maximum.accumulate(eq_g)))
        years.append({"year": str(a0.date()),
                      "total_pnl": round(float(rp.sum()), 6),
                      "total_pnl_gated": round(float(rp_g.sum()), 6),
                      "maxDD": round(dd, 6), "maxDD_gated": round(dd_g, 6),
                      "share_bars_flagged": round(float(fl[(panel["T"] >= bounds[k]) & (panel["T"] < bounds[k + 1])].mean()), 4)})
    return {"meta": "vectorised open-to-open diagnostic; longs x0.5 on spike-flagged bars; NOT a 4-phase engine claim",
            "years": years}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spike-only", action="store_true")
    ap.add_argument("--skip-replica", action="store_true")
    args = ap.parse_args()
    (HERE / "tmp").mkdir(parents=True, exist_ok=True)
    out: dict = {"meta": {
        "idea": "IDEAS2 §1 DVOL-spike (change) dip veto; pre-reg REPORT.md §0",
        "variants": ["V1 veto new dip bids on spike days",
                     "V2 V1 + halve book longs on spike days (diagnostic)"],
        "gate_costs": "maker 0.0002 / taker 0.00055 / longs 0.0001 per 8h settle",
        "placebo_gate": 0.273,
        "selection": "choose ONLY on dev years 2021-2024; 2025 scored once for the chosen variant, POST-HOC",
    }}
    out["baseline"] = step_baseline()
    print("baseline repro OK", flush=True)
    out["spike"] = step_spike()
    print(json.dumps(out["spike"]["per_year"], indent=1), flush=True)
    if args.spike_only:
        (HERE / "tmp" / "spike_only.json").write_text(json.dumps(out, indent=1))
        print("spike-only done", flush=True)
        return
    veto = pd.read_parquet(HERE / "tmp" / "veto_days.parquet")["veto"]
    if args.skip_replica:
        print("skipping replica (--skip-replica)", flush=True)
    else:
        out["replica"] = step_replica(veto)
        print(json.dumps(out["replica"]["decision"], indent=1), flush=True)
    out["book_diag"] = step_book_diagnostic(veto)
    print(json.dumps(out["book_diag"]["years"], indent=1), flush=True)
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
