"""oc_tsmom: daily 30-day time-series-momentum sleeve (BTC+ETH, vol-targeted).

Fixed rule from PLAN.md (pre-registered before any outcome was computed).
Usage: .venv/Scripts/python.exe research/tournament/oc_tsmom/run_tsmom.py

Reads (all in repo, t < 2026-09-24 00:00 UTC):
  research/tournament/ext/hourly_ext.parquet (BTCUSDT, ETHUSDT only)
  research/parallel/rounds/parallel-20260906-r2/v411/v411_runs.pkl (base mix)
  research/tournament/oc_kpi/results_equity.json (published reference only)
Writes: research/tournament/oc_tsmom/results.json
One process, no 1m data. Peak RAM well under 1 GB (two hourly series only).
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

COINS = ["BTCUSDT", "ETHUSDT"]
ANCHORS = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
VOL_TARGET = 0.10
POS_CAP = 1.0
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
    columns = COINS.
    """
    days = pd.date_range("2020-08-01", "2026-09-23", freq="D", tz="UTC")
    opens = pd.DataFrame(index=days, columns=COINS, dtype=float)
    closes = pd.DataFrame(index=days, columns=COINS, dtype=float)
    for sym in COINS:
        d = hourly[hourly["sym"] == sym].set_index("t").sort_index()
        o = d["open"]
        c = d["close"]
        # Exact timestamp mapping (no positional shift: robust to gaps).
        opens[sym] = [o.get(x, np.nan) for x in days]
        closes[sym] = [c.get(x + pd.Timedelta(hours=23), np.nan) for x in days]
    return opens, closes


def compute_positions(closes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Signal/vol/position per (day D, coin), known at close D.

    signal = sign(C(D)/C(D-30)-1); vol = std of 30 daily log returns ending D
    (ddof=1) * sqrt(365); pos = signal * min(0.10/vol, 1.0); NaN -> 0.
    Returns (signal, vol, pos) DataFrames indexed like closes.
    """
    signal = pd.DataFrame(0, index=closes.index, columns=closes.columns, dtype=int)
    vol = pd.DataFrame(np.nan, index=closes.index, columns=closes.columns)
    pos = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    logc = np.log(closes.astype(float))
    ret30 = closes.astype(float) / closes.astype(float).shift(30) - 1.0
    lr = logc.diff()  # daily log returns; lr.loc[D] uses C(D),C(D-1)
    for sym in closes.columns:
        r30 = ret30[sym]
        ok_ret = closes[sym].rolling(31).count() == 31  # all closes C(D-30)..C(D)
        s = pd.Series(0, index=closes.index, dtype=int)
        s[r30 > 0] = 1
        s[r30 < 0] = -1
        s[~ok_ret] = 0
        signal[sym] = s
        v = lr[sym].rolling(30).std(ddof=1) * np.sqrt(ANN)
        ok_vol = lr[sym].rolling(30).count() == 30
        v[~ok_vol] = np.nan
        v[~(v > 0)] = np.nan  # zero/negative/NaN -> NaN (position 0)
        vol[sym] = v
        raw = VOL_TARGET / v
        p = s.astype(float) * raw.clip(upper=POS_CAP)
        p[v.isna() | (s == 0)] = 0.0
        pos[sym] = p.fillna(0.0)
    return signal, vol, pos


def sleeve_daily(opens: pd.DataFrame, pos: pd.DataFrame, days: list[pd.Timestamp]) -> pd.DataFrame:
    """Net sleeve daily returns for holding days E in `days`.

    g(E) = sum pos(sym,E-1)*(O(E+1)/O(E)-1); cost = TAKER*sum|pos(E-1)-pos(E-2)|
    (pos before first holding day = 0); fund = 0.0003*sum max(pos(E-1),0).
    A coin with a missing open contributes 0 that day. Returns DataFrame with
    columns [gross, cost, fund, r_s] indexed by day.
    """
    out = []
    prev = pd.Series(0.0, index=COINS)  # pos(E-2) for first day = 0
    for e in days:
        e_next = e + pd.Timedelta(days=1)
        p = pos.loc[e - pd.Timedelta(days=1)] if (e - pd.Timedelta(days=1)) in pos.index else pd.Series(0.0, index=COINS)
        p = p.fillna(0.0)
        gross = 0.0
        for sym in COINS:
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


def sample_base_daily() -> pd.Series:
    """R2B1D17BF continuous 4-phase mix sampled daily; returns hourly mix e."""
    v388 = _load("v388_tsmom", RD / "v388" / "v388_bot_stop_distance.py")
    runs = pickle.loads(RUNS_PKL.read_bytes())
    assert set(runs) == {0, 1, 2, 3}, sorted(runs)
    for s in runs:
        assert set(runs[s]["R2B1D17BF"]) == {"t", "eq", "eq_min"}, runs[s]["R2B1D17BF"].keys()
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, _mn = v388.mix(runs, "R2B1D17BF", g1)
    return e


def sample_reset_base() -> tuple[dict[int, pd.Series], object]:
    """Per-year reset base (user-facing year metric, cf. reset_metric.year_reset).

    For anchor year y with anchor a0: F_s = e1_s / b_s per shift
    (b_s = last hourly value <= a0), F = mean(F_s) on the full hourly grid.
    F(a0) == 1.0 by construction; F restricted to (a0, a0+365d] equals the
    reset_metric segment mean, so daily compounding reproduces oc_kpi R exactly.
    Returns ({y: F}, v388 module).
    """
    v388 = _load("v388_tsmom", RD / "v388" / "v388_bot_stop_distance.py")
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
    """Sleeve/base/combined stats from aligned daily returns (variant-agnostic)."""
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
        "ret_pass": bool(m_c > m_b),
        "dd_pass": bool(dd_c <= dd_b),
        "excess_monthly_pp": round(m_c - m_b, 3),
        "dd_delta_pp": round(dd_c - dd_b, 3),
        "r_comb": [round(float(v), 8) for v in rc],
    }


def base_daily_returns(e: pd.Series, days: list[pd.Timestamp]) -> pd.Series:
    """r_b(E) = e(E+1 00:00)/e(E 00:00)-1; first day uses max(E 00:00, e.index[0])."""
    out = {}
    for day in days:
        a = day if day >= e.index[0] else e.index[0]
        b = day + pd.Timedelta(days=1)
        if a not in e.index or b not in e.index:
            continue
        out[day] = float(e.loc[b] / e.loc[a] - 1.0)
    return pd.Series(out).sort_index()


def main() -> None:
    hourly = pd.read_parquet(HOURLY)
    hourly["t"] = pd.to_datetime(hourly["t"], utc=True)
    assert bool((hourly["t"] < CAP).all()), "hourly data reaches beyond the cap"
    hourly = hourly[hourly["sym"].isin(COINS)].copy()
    assert set(hourly["sym"].unique()) == set(COINS)

    opens, closes = build_daily(hourly)
    # alignment check: O(D) must equal prior day's 23:00 open-chain sanity:
    # open of D 00:00 bar should match close of (D-1) 23:00 bar up to real gaps;
    # instead verify C(D) equals the 23:00 bar close directly on 5 spot days.
    d = hourly[hourly["sym"] == "BTCUSDT"].set_index("t").sort_index()
    for spot in ["2021-09-24", "2023-01-15", "2025-09-23"]:
        want_c = float(d.loc[pd.Timestamp(spot + " 23:00", tz="UTC"), "close"])
        want_o = float(d.loc[pd.Timestamp(spot + " 00:00", tz="UTC"), "open"])
        got_c = float(closes.loc[pd.Timestamp(spot, tz="UTC"), "BTCUSDT"])
        got_o = float(opens.loc[pd.Timestamp(spot, tz="UTC"), "BTCUSDT"])
        assert want_c == got_c and want_o == got_o, spot

    signal, vol, pos = compute_positions(closes)
    e = sample_base_daily()
    reset_F, _v388 = sample_reset_base()

    try:
        kpi_ref = json.loads(KPI_REF.read_text())
        kpi_years = {y["anchor"][:10]: y for y in kpi_ref["years"]}
    except FileNotFoundError:
        kpi_years = {}

    def year_days(a0: pd.Timestamp) -> list[pd.Timestamp]:
        cands = [a0 + pd.Timedelta(days=i) for i in range(365)]
        # sleeve needs O(E), O(E+1): E+1 <= last opens day
        last_o = opens.index[-1]
        return [x for x in cands if x <= last_o - pd.Timedelta(days=1)]

    def reset_daily_returns(F: pd.Series, days: list[pd.Timestamp]) -> pd.Series:
        out = {}
        for day in days:
            b = day + pd.Timedelta(days=1)
            if day not in F.index or b not in F.index:
                continue
            out[day] = float(F.loc[b] / F.loc[day] - 1.0)
        return pd.Series(out).sort_index()

    years = []
    all_rs = []
    for k, a in enumerate(ANCHORS):
        a0 = pd.Timestamp(a, tz="UTC")
        sc = year_days(a0)
        sdf = sleeve_daily(opens, pos, sc)
        # Variant A (pre-registered): continuous-mix daily base.
        rbA = base_daily_returns(e, sc)
        # Variant B (reset convention = user-facing year metric, oc_kpi R).
        rbB = reset_daily_returns(reset_F[k], sc)
        commonA = sorted(set(sdf.index) & set(rbA.index))
        commonB = sorted(set(sdf.index) & set(rbB.index))
        # One shared day set per year (drops at most the 2021-09-24 partial
        # day in year 0, where the mix grid starts at 04:00): both variants
        # then share the same sleeve subseries.
        common = sorted(set(commonA) & set(commonB))
        assert len(common) >= 360, (a, len(commonA), len(commonB))
        sdf = sdf.loc[common]
        rs = sdf["r_s"].to_numpy(float)
        rbvA = rbA.loc[common].to_numpy(float)
        rbvB = rbB.loc[common].to_numpy(float)
        stA = leg_stats(rs, rbvA)
        stB = leg_stats(rs, rbvB)
        years.append({
            "year": k, "anchor": a,
            "n_days": len(common),
            "first_day": str(common[0].date()) if common else None,
            "last_day": str(common[-1].date()) if common else None,
            "sleeve": {
                **stB["sleeve"],
                "avg_abs_pos": {s: round(float(pos.loc[[x - pd.Timedelta(days=1) for x in common], s].abs().mean()), 4) for s in COINS},
                "mean_cost_bps_day": round(float(sdf["cost"].mean()) * 1e4, 3),
                "mean_fund_bps_day": round(float(sdf["fund"].mean()) * 1e4, 3),
            },
            # Variant B is primary (reset convention, matches oc_kpi R).
            "base": stB["base"],
            "combined": stB["combined"],
            "corr_sleeve_base": stB["corr_sleeve_base"],
            "ret_pass": stB["ret_pass"],
            "dd_pass": stB["dd_pass"],
            "excess_monthly_pp": stB["excess_monthly_pp"],
            "dd_delta_pp": stB["dd_delta_pp"],
            # Variant A (pre-registered continuous-mix base) as sensitivity.
            "variantA_continuous_mix": {
                "base": stA["base"],
                "combined": stA["combined"],
                "corr_sleeve_base": stA["corr_sleeve_base"],
                "ret_pass": stA["ret_pass"],
                "dd_pass": stA["dd_pass"],
            },
            "days": [x.strftime("%Y-%m-%d") for x in common],
            "r_sleeve": [round(float(v), 8) for v in rs],
            "r_base": [round(float(v), 8) for v in rbvB],
            "r_base_A": [round(float(v), 8) for v in rbvA],
            "r_comb": stB["r_comb"],
            "kpi_reference": kpi_years.get(a, None),
        })
        all_rs.append(rs)

    # LOYO (descriptive): sign of pooled mean sleeve return, full vs leave-one-out
    rs_all = np.concatenate(all_rs)
    full_mean = float(np.mean(rs_all))
    loyo = []
    for h in range(5):
        pool = np.concatenate([all_rs[k] for k in range(5) if k != h])
        pm = float(np.mean(pool))
        loyo.append({
            "held_out": ANCHORS[h], "year": h,
            "pool_mean_bps_day": round(pm * 1e4, 4),
            "sign_match": bool(np.sign(pm) == np.sign(full_mean)) if full_mean != 0 and np.isfinite(pm) else False,
        })

    n_ret = sum(1 for y in years if y["ret_pass"])
    n_dd = sum(1 for y in years if y["dd_pass"])
    n_retA = sum(1 for y in years if y["variantA_continuous_mix"]["ret_pass"])
    n_ddA = sum(1 for y in years if y["variantA_continuous_mix"]["dd_pass"])
    n_loyo = sum(1 for L in loyo if L["sign_match"])
    promising = bool(n_ret >= 4 and n_dd >= 4)

    # compounding residuals (must be ~0)
    residuals = []
    for y in years:
        for key, tot in (("r_sleeve", "sleeve"), ("r_base", "base"), ("r_comb", "combined")):
            arr = np.array(y[key], float)
            net = float(np.prod(1 + arr) - 1) * 100
            residuals.append(abs(net - y[tot]["total_pct"]))
    # reset-base totals must reproduce oc_kpi R ordering (same convention)
    kpi_gap = []
    for y in years:
        ref = y["kpi_reference"]
        if ref is not None:
            kpi_gap.append(abs(y["base"]["monthly_pct"] - ref["R"]))

    out = {
        "idea": 36,
        "rule": "daily 30d TSMOM, BTC+ETH, 10% vol target, cap 1.0x, next-day-open rebalance, taker 0.00055, longs fund 0.0001/8h, shorts zero; combined = base + 0.25xsleeve",
        "primary_base": "B_reset (per-shift normalised year segments, F(a0)=1.0; reproduces oc_kpi R; DD on daily-00:00 grid)",
        "sensitivity_base": "A_continuous_mix (v388.mix sampled daily; pre-registered definition)",
        "anchors": ANCHORS,
        "data_cap": "2026-09-24T00:00:00Z",
        "g1": "2026-09-23 12:00:00+00:00",
        "years": years,
        "loyo_sleeve_sign": {
            "full_mean_bps_day": round(full_mean * 1e4, 4),
            "pools": loyo,
            "match": f"{n_loyo}/5",
        },
        "decision": {
            "ret_higher": f"{n_ret}/5",
            "dd_not_worse": f"{n_dd}/5",
            "promising": promising,
            "variantA": {"ret_higher": f"{n_retA}/5", "dd_not_worse": f"{n_ddA}/5",
                         "promising": bool(n_retA >= 4 and n_ddA >= 4)},
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
    print(f"PRIMARY(B) ret {n_ret}/5 dd {n_dd}/5 | VARIANT-A ret {n_retA}/5 dd {n_ddA}/5 | loyo-sign {n_loyo}/5 promising={promising}", flush=True)
    for y in years:
        print(y["anchor"], "sleeve m=", y["sleeve"]["monthly_pct"], "dd=", y["sleeve"]["maxDD_pct"],
              "base m=", y["base"]["monthly_pct"], "dd=", y["base"]["maxDD_pct"],
              "comb m=", y["combined"]["monthly_pct"], "dd=", y["combined"]["maxDD_pct"],
              "corr=", y["corr_sleeve_base"], flush=True)
    print("kpi monthly-R gap (pp):", out["checks"]["max_base_monthly_gap_vs_kpi_pp"], flush=True)


if __name__ == "__main__":
    main()
