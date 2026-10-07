"""oc_xsrev: daily cross-sectional reversal sleeve (5 majors, 1-day reversal).

Fixed rule from PLAN.md (pre-registered before any outcome was computed).
Usage: .venv/Scripts/python.exe research/tournament/oc_xsrev/run_xsrev.py

Reads (all in repo, t < 2026-09-24 00:00 UTC):
  research/tournament/ext/hourly_ext.parquet (5 majors only)
  research/parallel/rounds/parallel-20260906-r2/v411/v411_runs.pkl (base mix)
  research/tournament/oc_kpi/results_equity.json (published reference only)
Writes: research/tournament/oc_xsrev/results.json
One process, no 1m data. Peak RAM well under 1 GB (five hourly series only).
"""
from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
RUNS_PKL = RD / "v411" / "v411_runs.pkl"
KPI_REF = ROOT / "research/tournament/oc_kpi" / "results_equity.json"

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
W_LONG = 0.25
W_SHORT = -0.25
ANCHORS = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TAKER = 0.00055
FUND_PER_DAY = 0.0003  # 0.0001 x 3 settlements on longs; shorts zero
ANN = 365.0


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_daily(hourly: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily O/C per coin from hourly bars.

    O(sym,D) = open of bar t = D 00:00; C(sym,D) = close of bar t = D 23:00.
    hourly must already be capped at t < 2026-09-24 UTC. No forward fill.
    Returns (opens, closes): DataFrames indexed by day (Timestamp 00:00 UTC),
    columns = MAJORS.
    """
    days = pd.date_range("2020-08-01", "2026-09-23", freq="D", tz="UTC")
    opens = pd.DataFrame(index=days, columns=MAJORS, dtype=float)
    closes = pd.DataFrame(index=days, columns=MAJORS, dtype=float)
    for sym in MAJORS:
        d = hourly[hourly["sym"] == sym].set_index("t").sort_index()
        o = d["open"]
        c = d["close"]
        opens[sym] = [o.get(x, np.nan) for x in days]
        closes[sym] = [c.get(x + pd.Timedelta(hours=23), np.nan) for x in days]
    return opens, closes


def compute_weights(closes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cross-sectional reversal weights w(sym,D), known at close D.

    ret1(sym,D) = C(D)/C(D-1)-1 (NaN if missing/zero). Rank valid ascending;
    ties -> symbol alphabetical. Long worst-2 (+0.25), short best-2 (-0.25).
    Thin days (<4 valid): longs = first min(2,n), shorts = last min(2, rest)
    from the remainder (disjoint; longs priority). Returns (ret1, weights).
    """
    ret1 = closes.astype(float) / closes.astype(float).shift(1) - 1.0
    # zero-division guard: C(D-1)==0 -> NaN
    prev_zero = closes.astype(float).shift(1) == 0
    ret1 = ret1.mask(prev_zero)
    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    for d in closes.index:
        r = ret1.loc[d]
        valid = r.dropna()
        if len(valid) == 0:
            continue
        ordered = sorted(valid.index, key=lambda s: (float(valid[s]), s))
        n = len(ordered)
        longs = ordered[: min(2, n)]
        rest = ordered[len(longs):]
        shorts = rest[-min(2, len(rest)):] if len(rest) else []
        for s in longs:
            w.loc[d, s] = W_LONG
        for s in shorts:
            w.loc[d, s] = W_SHORT
    return ret1, w


def sleeve_daily(opens: pd.DataFrame, w: pd.DataFrame, days: list[pd.Timestamp]) -> pd.DataFrame:
    """Net sleeve daily returns for holding days E in `days`.

    g(E) = sum w(sym,E-1)*(O(E+1)/O(E)-1); cost = TAKER*sum|w(E-1)-w(E-2)|
    (w before first holding day = 0); fund = 0.0003*sum max(w(E-1),0).
    A coin with a missing/zero open contributes 0 that day. Returns DataFrame
    with columns [gross, cost, fund, r_s] indexed by day.
    """
    out = []
    prev = pd.Series(0.0, index=MAJORS)  # w(E-2) for first day = 0
    for e in days:
        e_next = e + pd.Timedelta(days=1)
        d_prev = e - pd.Timedelta(days=1)
        p = w.loc[d_prev] if d_prev in w.index else pd.Series(0.0, index=MAJORS)
        p = p.fillna(0.0)
        gross = 0.0
        for sym in MAJORS:
            try:
                o0 = opens.loc[e, sym]
                o1 = opens.loc[e_next, sym]
            except KeyError:
                continue
            if pd.isna(o0) or pd.isna(o1) or o0 == 0:
                continue
            gross += float(p[sym]) * (float(o1) / float(o0) - 1.0)
        cost = TAKER * float((p - prev).abs().sum())
        fund = FUND_PER_DAY * float(p.clip(lower=0).sum())
        out.append((e, gross, cost, fund, gross - cost - fund))
        prev = p
    df = pd.DataFrame(out, columns=["day", "gross", "cost", "fund", "r_s"]).set_index("day")
    return df


def max_dd(equity: np.ndarray) -> float:
    """Max peak-to-trough drawdown (fraction) on path starting at 1.0."""
    eq = np.asarray(equity, float)
    path = np.concatenate([[1.0], eq])
    pk = np.maximum.accumulate(path)
    return float(np.max(1.0 - path / pk))


def sharpe_ann(r: np.ndarray) -> float:
    r = np.asarray(r, float)
    if len(r) < 2:
        return 0.0
    sd = float(np.std(r, ddof=1))
    if not np.isfinite(sd) or sd <= 0:
        return 0.0
    return float(np.mean(r) / sd * np.sqrt(ANN))


def equity_from(r: np.ndarray) -> np.ndarray:
    return np.cumprod(1.0 + np.asarray(r, float))


def sample_reset_base() -> tuple[dict[int, pd.Series], object]:
    """Per-year reset base (user-facing year metric, cf. reset_metric.year_reset).

    For anchor year y with anchor a0: F_s = e1_s / b_s per shift
    (b_s = last hourly value <= a0), F = mean(F_s) on the full hourly grid.
    F(a0) == 1.0 by construction; daily compounding reproduces oc_kpi R.
    Returns ({y: F}, v388 module).
    """
    v388 = _load("v388_xsrev", RD / "v388" / "v388_bot_stop_distance.py")
    runs = pickle.loads(RUNS_PKL.read_bytes())
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    g0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
    out = {}
    for y, a in enumerate(ANCHORS):
        a0 = pd.Timestamp(a, tz="UTC")
        parts = []
        for s in range(4):
            e1, _m1 = v388.hourly(runs[s]["R2B1D17BF"], g0, g1)
            b = float(e1[e1.index <= a0].iloc[-1]) if (e1.index <= a0).any() else 1.0
            parts.append(e1 / b)
        out[y] = sum(parts) / 4
    return out, v388


def leg_stats(rs: np.ndarray, rbv: np.ndarray) -> dict:
    """Sleeve/base/combined stats from aligned daily returns."""
    rc = rbv + 0.25 * rs
    eq_s, eq_b, eq_c = equity_from(rs), equity_from(rbv), equity_from(rc)
    m_s = float(eq_s[-1] ** (1 / 12) - 1) * 100
    m_b = float(eq_b[-1] ** (1 / 12) - 1) * 100
    m_c = float(eq_c[-1] ** (1 / 12) - 1) * 100
    dd_s, dd_b, dd_c = max_dd(eq_s) * 100, max_dd(eq_b) * 100, max_dd(eq_c) * 100
    corr = (float(np.corrcoef(rs, rbv)[0, 1])
            if len(rs) > 2 and np.std(rs) > 0 and np.std(rbv) > 0 else float("nan"))
    return {
        "sleeve": {"total_pct": round(float(eq_s[-1] - 1) * 100, 3),
                   "monthly_pct": round(m_s, 3),
                   "sharpe": round(sharpe_ann(rs), 3),
                   "maxDD_pct": round(dd_s, 2)},
        "base": {"total_pct": round(float(eq_b[-1] - 1) * 100, 3),
                 "monthly_pct": round(m_b, 3),
                 "maxDD_pct": round(dd_b, 2)},
        "combined": {"total_pct": round(float(eq_c[-1] - 1) * 100, 3),
                     "monthly_pct": round(m_c, 3),
                     "maxDD_pct": round(dd_c, 2)},
        "corr_sleeve_base": round(corr, 3) if np.isfinite(corr) else None,
        "pos_pass": bool(m_s > 0),
        "corr_pass": bool(np.isfinite(corr) and abs(corr) < 0.15),
        "dd_pass": bool(dd_c <= dd_b),
        "excess_monthly_pp": round(m_c - m_b, 3),
        "dd_delta_pp": round(dd_c - dd_b, 3),
        "r_comb": [round(float(v), 8) for v in rc],
    }


def reset_daily_returns(F: pd.Series, days: list[pd.Timestamp]) -> pd.Series:
    out = {}
    for day in days:
        b = day + pd.Timedelta(days=1)
        if day not in F.index or b not in F.index:
            continue
        out[day] = float(F.loc[b] / F.loc[day] - 1.0)
    return pd.Series(out).sort_index()


def main() -> None:
    hourly = pd.read_parquet(HOURLY)
    hourly["t"] = pd.to_datetime(hourly["t"], utc=True)
    assert bool((hourly["t"] < CAP).all()), "hourly data reaches beyond the cap"
    hourly = hourly[hourly["sym"].isin(MAJORS)].copy()
    assert set(hourly["sym"].unique()) == set(MAJORS)

    opens, closes = build_daily(hourly)
    # alignment spot-check: O(D) = D 00:00 open, C(D) = D 23:00 close.
    d = hourly[hourly["sym"] == "BTCUSDT"].set_index("t").sort_index()
    for spot in ["2021-09-24", "2023-01-15", "2025-09-23"]:
        want_c = float(d.loc[pd.Timestamp(spot + " 23:00", tz="UTC"), "close"])
        want_o = float(d.loc[pd.Timestamp(spot + " 00:00", tz="UTC"), "open"])
        got_c = float(closes.loc[pd.Timestamp(spot, tz="UTC"), "BTCUSDT"])
        got_o = float(opens.loc[pd.Timestamp(spot, tz="UTC"), "BTCUSDT"])
        assert want_c == got_c and want_o == got_o, spot

    ret1, w = compute_weights(closes)
    reset_F, _v388 = sample_reset_base()

    try:
        kpi_ref = json.loads(KPI_REF.read_text())
        kpi_years = {y["anchor"][:10]: y for y in kpi_ref["years"]}
    except FileNotFoundError:
        kpi_years = {}

    def year_days(a0: pd.Timestamp) -> list[pd.Timestamp]:
        cands = [a0 + pd.Timedelta(days=i) for i in range(365)]
        last_o = opens.index[-1]
        return [x for x in cands if x <= last_o - pd.Timedelta(days=1)]

    years = []
    all_rs = []
    for k, a in enumerate(ANCHORS):
        a0 = pd.Timestamp(a, tz="UTC")
        sc = year_days(a0)
        sdf = sleeve_daily(opens, w, sc)
        rb = reset_daily_returns(reset_F[k], sc)
        common = sorted(set(sdf.index) & set(rb.index))
        assert len(common) >= 360, (a, len(common))
        sdf = sdf.loc[common]
        rs = sdf["r_s"].to_numpy(float)
        rbv = rb.loc[common].to_numpy(float)
        st = leg_stats(rs, rbv)
        # thin-day diagnostics: days in year with gross exposure < 1.0x
        wdays = w.loc[[x - pd.Timedelta(days=1) for x in common]]
        gross_exp = wdays.abs().sum(axis=1).to_numpy(float)
        n_thin = int((gross_exp < 0.999).sum())
        n_missing_open = 0
        for e in common:
            e_next = e + pd.Timedelta(days=1)
            for sym in MAJORS:
                if abs(float(w.loc[e - pd.Timedelta(days=1), sym])) > 0:
                    try:
                        o0 = opens.loc[e, sym]
                        o1 = opens.loc[e_next, sym]
                    except KeyError:
                        n_missing_open += 1
                        continue
                    if pd.isna(o0) or pd.isna(o1) or o0 == 0:
                        n_missing_open += 1
        years.append({
            "year": k, "anchor": a,
            "n_days": len(common),
            "first_day": str(common[0].date()) if common else None,
            "last_day": str(common[-1].date()) if common else None,
            "sleeve": {
                **st["sleeve"],
                "mean_cost_bps_day": round(float(sdf["cost"].mean()) * 1e4, 3),
                "mean_fund_bps_day": round(float(sdf["fund"].mean()) * 1e4, 3),
                "mean_gross_bps_day": round(float(sdf["gross"].mean()) * 1e4, 3),
                "mean_gross_exposure": round(float(gross_exp.mean()), 4),
                "n_thin_days": n_thin,
                "n_missing_open_legs": n_missing_open,
            },
            "base": st["base"],
            "combined": st["combined"],
            "corr_sleeve_base": st["corr_sleeve_base"],
            "pos_pass": st["pos_pass"],
            "corr_pass": st["corr_pass"],
            "dd_pass": st["dd_pass"],
            "excess_monthly_pp": st["excess_monthly_pp"],
            "dd_delta_pp": st["dd_delta_pp"],
            "days": [x.strftime("%Y-%m-%d") for x in common],
            "r_sleeve": [round(float(v), 8) for v in rs],
            "r_base": [round(float(v), 8) for v in rbv],
            "r_comb": st["r_comb"],
            "kpi_reference": kpi_years.get(a, None),
        })
        all_rs.append(rs)

    # LOYO (descriptive): pooled mean sleeve return over other-4-years > 0
    rs_all = np.concatenate(all_rs)
    full_mean = float(np.mean(rs_all))
    loyo = []
    for h in range(5):
        pool = np.concatenate([all_rs[k] for k in range(5) if k != h])
        pm = float(np.mean(pool))
        loyo.append({
            "held_out": ANCHORS[h], "year": h,
            "pool_mean_bps_day": round(pm * 1e4, 4),
            "pass": bool(pm > 0) if np.isfinite(pm) else False,
        })

    n_pos = sum(1 for y in years if y["pos_pass"])
    n_corr = sum(1 for y in years if y["corr_pass"])
    n_dd = sum(1 for y in years if y["dd_pass"])
    n_loyo = sum(1 for L in loyo if L["pass"])
    promising = bool(n_pos >= 4 and n_corr >= 4 and n_dd >= 4)

    residuals = []
    for y in years:
        for key, tot in (("r_sleeve", "sleeve"), ("r_base", "base"), ("r_comb", "combined")):
            arr = np.array(y[key], float)
            net = float(np.prod(1 + arr) - 1) * 100
            residuals.append(abs(net - y[tot]["total_pct"]))
    kpi_gap = []
    for y in years:
        ref = y["kpi_reference"]
        if ref is not None:
            kpi_gap.append(abs(y["base"]["monthly_pct"] - ref["R"]))

    out = {
        "idea": 40,
        "rule": "daily cross-sectional reversal, 5 majors, rank by 1d close-to-close return at close D; long worst 2 (+0.25 each), short best 2 (-0.25 each), gross 1.0x dollar-neutral; hold one day entered at next-day open; taker 0.00055 on traded notional, longs fund 0.0001/8h, shorts zero; combined = base + 0.25xsleeve",
        "primary_base": "reset (per-shift normalised year segments, F(a0)=1.0; reproduces oc_kpi R; DD on daily-00:00 grid, same as oc_tsmom Variant B)",
        "anchors": ANCHORS,
        "data_cap": "2026-09-24T00:00:00Z",
        "g1": "2026-09-23 12:00:00+00:00",
        "years": years,
        "loyo_sleeve_pos": {
            "full_mean_bps_day": round(full_mean * 1e4, 4),
            "pools": loyo,
            "match": f"{n_loyo}/5",
        },
        "decision": {
            "sleeve_positive": f"{n_pos}/5",
            "corr_below_015": f"{n_corr}/5",
            "dd_not_worse": f"{n_dd}/5",
            "promising": promising,
        },
        "checks": {
            "hourly_cap_ok": True,
            "max_compound_residual_pp": round(float(max(residuals)), 10),
            "max_base_monthly_gap_vs_kpi_pp": round(float(max(kpi_gap)), 4) if kpi_gap else None,
            "v411_keys_ok": True,
            "n_days": [y["n_days"] for y in years],
        },
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"pos {n_pos}/5 corr {n_corr}/5 dd {n_dd}/5 loyo-pos {n_loyo}/5 promising={promising}", flush=True)
    for y in years:
        print(y["anchor"], "sleeve m=", y["sleeve"]["monthly_pct"], "dd=", y["sleeve"]["maxDD_pct"],
              "base m=", y["base"]["monthly_pct"], "dd=", y["base"]["maxDD_pct"],
              "comb m=", y["combined"]["monthly_pct"], "dd=", y["combined"]["maxDD_pct"],
              "corr=", y["corr_sleeve_base"], flush=True)
    print("kpi monthly-R gap (pp):", out["checks"]["max_base_monthly_gap_vs_kpi_pp"], flush=True)


if __name__ == "__main__":
    main()
