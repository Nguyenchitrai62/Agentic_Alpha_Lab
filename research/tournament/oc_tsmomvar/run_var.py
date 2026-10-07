"""oc_tsmomvar: two pre-registered TSMOM sleeve variants (V1/V2).

Frozen rules from PLAN.md (written before any outcome was computed).
Usage: .venv/Scripts/python.exe research/tournament/oc_tsmomvar/run_var.py

V1 = oc_tsmom rule on all five majors (BTC/ETH/SOL/BNB/XRP, 30d sign,
     10% vol target per coin, cap 1.0x, long/short).
V2 = BTC/ETH with 90d lookback, LONG-ONLY (flat when ret90 <= 0; 90d vol).

All other mechanics reuse research/tournament/oc_tsmom/run_tsmom.py exactly:
daily O/C from hourly, next-open execution, taker 0.00055 on |dpos|,
longs fund 0.0003/day (shorts zero), reset-convention R2B1D17BF base,
combined = base + 0.25*sleeve, same anchors/day sets.

Reads (t < 2026-09-24 00:00 UTC only):
  research/tournament/ext/hourly_ext.parquet
  research/parallel/rounds/parallel-20260906-r2/v411/v411_runs.pkl
  research/tournament/oc_kpi/results_equity.json (reference only)
Writes: research/tournament/oc_tsmomvar/results.json
One process, no 1m data, RAM < 1 GB.
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

V1_COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
V2_COINS = ["BTCUSDT", "ETHUSDT"]
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


def build_daily(hourly: pd.DataFrame, coins: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily O/C per coin from hourly bars (oc_tsmom definition, exact).

    O(sym,D) = open of bar t = D 00:00; C(sym,D) = close of bar t = D 23:00.
    hourly must already be capped at t < 2026-09-24 UTC. No forward fill.
    """
    days = pd.date_range("2020-08-01", "2026-09-23", freq="D", tz="UTC")
    opens = pd.DataFrame(index=days, columns=coins, dtype=float)
    closes = pd.DataFrame(index=days, columns=coins, dtype=float)
    for sym in coins:
        d = hourly[hourly["sym"] == sym].set_index("t").sort_index()
        o = d["open"]
        c = d["close"]
        opens[sym] = [o.get(x, np.nan) for x in days]
        closes[sym] = [c.get(x + pd.Timedelta(hours=23), np.nan) for x in days]
    return opens, closes


def compute_positions_30d(closes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """oc_tsmom 30d long/short rule, generalized to any coin set (V1).

    signal = sign(C(D)/C(D-30)-1), 0 if any of 31 closes missing;
    vol = std of 30 daily log returns ending D (ddof=1)*sqrt(365);
    pos = signal*min(0.10/vol, 1.0); NaN -> 0.
    """
    signal = pd.DataFrame(0, index=closes.index, columns=closes.columns, dtype=int)
    vol = pd.DataFrame(np.nan, index=closes.index, columns=closes.columns)
    pos = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    logc = np.log(closes.astype(float))
    ret30 = closes.astype(float) / closes.astype(float).shift(30) - 1.0
    lr = logc.diff()
    for sym in closes.columns:
        r30 = ret30[sym]
        ok_ret = closes[sym].rolling(31).count() == 31
        s = pd.Series(0, index=closes.index, dtype=int)
        s[r30 > 0] = 1
        s[r30 < 0] = -1
        s[~ok_ret] = 0
        signal[sym] = s
        v = lr[sym].rolling(30).std(ddof=1) * np.sqrt(ANN)
        ok_vol = lr[sym].rolling(30).count() == 30
        v[~ok_vol] = np.nan
        v[~(v > 0)] = np.nan
        vol[sym] = v
        raw = VOL_TARGET / v
        p = s.astype(float) * raw.clip(upper=POS_CAP)
        p[v.isna() | (s == 0)] = 0.0
        pos[sym] = p.fillna(0.0)
    return signal, vol, pos


def compute_positions_90d_longonly(closes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """V2: 90d lookback, LONG-ONLY (flat when ret90 <= 0).

    signal = +1 iff C(D)/C(D-90)-1 > 0 with all 91 closes present, else 0;
    vol90 = std of 90 daily log returns ending D (ddof=1)*sqrt(365);
    pos = signal*min(0.10/vol90, 1.0) >= 0 always.
    """
    signal = pd.DataFrame(0, index=closes.index, columns=closes.columns, dtype=int)
    vol = pd.DataFrame(np.nan, index=closes.index, columns=closes.columns)
    pos = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    logc = np.log(closes.astype(float))
    ret90 = closes.astype(float) / closes.astype(float).shift(90) - 1.0
    lr = logc.diff()
    for sym in closes.columns:
        r90 = ret90[sym]
        ok_ret = closes[sym].rolling(91).count() == 91
        s = pd.Series(0, index=closes.index, dtype=int)
        s[(r90 > 0) & ok_ret] = 1
        signal[sym] = s
        v = lr[sym].rolling(90).std(ddof=1) * np.sqrt(ANN)
        ok_vol = lr[sym].rolling(90).count() == 90
        v[~ok_vol] = np.nan
        v[~(v > 0)] = np.nan
        vol[sym] = v
        raw = VOL_TARGET / v
        p = s.astype(float) * raw.clip(upper=POS_CAP)
        p[v.isna() | (s == 0)] = 0.0
        pos[sym] = p.fillna(0.0)
    return signal, vol, pos


def sleeve_daily(opens: pd.DataFrame, pos: pd.DataFrame, days: list[pd.Timestamp],
                 coins: list[str]) -> pd.DataFrame:
    """Net sleeve daily returns for holding days E (oc_tsmom definition, exact).

    g(E) = sum pos(sym,E-1)*(O(E+1)/O(E)-1); cost = TAKER*sum|pos(E-1)-pos(E-2)|
    (pos before first holding day = 0); fund = 0.0003*sum max(pos(E-1),0).
    A coin with a missing open contributes 0 that day.
    """
    out = []
    prev = pd.Series(0.0, index=coins)
    for e in days:
        e_next = e + pd.Timedelta(days=1)
        d_prev = e - pd.Timedelta(days=1)
        if d_prev in pos.index:
            p = pos.loc[d_prev].fillna(0.0)
        else:
            p = pd.Series(0.0, index=coins)
        gross = 0.0
        for sym in coins:
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


def sample_reset_base() -> dict[int, pd.Series]:
    """Per-year reset base F (oc_tsmom Variant B, exact copy)."""
    v388 = _load("v388_tsmomvar", RD / "v388" / "v388_bot_stop_distance.py")
    runs = pickle.loads(RUNS_PKL.read_bytes())
    assert set(runs) == {0, 1, 2, 3}, sorted(runs)
    for s in runs:
        assert set(runs[s]["R2B1D17BF"]) == {"t", "eq", "eq_min"}
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
    return out


def leg_stats(rs: np.ndarray, rbv: np.ndarray) -> dict:
    """Sleeve/base/combined stats from aligned daily returns (oc_tsmom exact)."""
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


def reset_daily_returns(F: pd.Series, days: list[pd.Timestamp]) -> pd.Series:
    out = {}
    for day in days:
        b = day + pd.Timedelta(days=1)
        if day not in F.index or b not in F.index:
            continue
        out[day] = float(F.loc[b] / F.loc[day] - 1.0)
    return pd.Series(out).sort_index()


def run_variant(tag: str, coins: list[str], kind: str, opens_all, closes_all,
                reset_F, kpi_years) -> tuple[list[dict], np.ndarray]:
    """Score one variant; kind in {"30d", "90d_longonly"}."""
    opens = opens_all[coins]
    closes = closes_all[coins]
    if kind == "30d":
        _sig, _vol, pos = compute_positions_30d(closes)
    elif kind == "90d_longonly":
        _sig, _vol, pos = compute_positions_90d_longonly(closes)
    else:
        raise ValueError(kind)

    def year_days(a0: pd.Timestamp) -> list[pd.Timestamp]:
        cands = [a0 + pd.Timedelta(days=i) for i in range(365)]
        last_o = opens.index[-1]
        return [x for x in cands if x <= last_o - pd.Timedelta(days=1)]

    years = []
    all_rs = []
    for k, a in enumerate(ANCHORS):
        a0 = pd.Timestamp(a, tz="UTC")
        sc = year_days(a0)
        sdf = sleeve_daily(opens, pos, sc, coins)
        rbB = reset_daily_returns(reset_F[k], sc)
        common = sorted(set(sdf.index) & set(rbB.index))
        assert len(common) >= 360, (tag, a, len(common))
        sdf = sdf.loc[common]
        rs = sdf["r_s"].to_numpy(float)
        rbv = rbB.loc[common].to_numpy(float)
        st = leg_stats(rs, rbv)
        m_s = st["sleeve"]["monthly_pct"]
        corr = st["corr_sleeve_base"]
        pass_pos = bool(m_s > 0)
        pass_corr = bool(corr is not None and corr < 0.15)
        years.append({
            "year": k, "anchor": a,
            "n_days": len(common),
            "first_day": str(common[0].date()) if common else None,
            "last_day": str(common[-1].date()) if common else None,
            "sleeve": {
                **st["sleeve"],
                "avg_abs_pos": {s: round(float(
                    pos.loc[[x - pd.Timedelta(days=1) for x in common], s].abs().mean()), 4)
                    for s in coins},
                "mean_cost_bps_day": round(float(sdf["cost"].mean()) * 1e4, 3),
                "mean_fund_bps_day": round(float(sdf["fund"].mean()) * 1e4, 3),
            },
            "base": st["base"],
            "combined": st["combined"],
            "corr_sleeve_base": st["corr_sleeve_base"],
            "pass_pos": pass_pos,
            "pass_corr": pass_corr,
            "div_pass": bool(pass_pos and pass_corr),
            "ret_pass_descriptive": st["ret_pass"],
            "dd_pass_descriptive": st["dd_pass"],
            "excess_monthly_pp": st["excess_monthly_pp"],
            "dd_delta_pp": st["dd_delta_pp"],
            "days": [x.strftime("%Y-%m-%d") for x in common],
            "r_sleeve": [round(float(v), 8) for v in rs],
            "r_base": [round(float(v), 8) for v in rbv],
            "r_comb": st["r_comb"],
            "kpi_reference": kpi_years.get(a, None),
        })
        all_rs.append(rs)
    return years, np.concatenate(all_rs)


def loyo_sign(pooled_all: np.ndarray, all_rs: list[np.ndarray]) -> tuple[list[dict], int, float]:
    full_mean = float(np.mean(pooled_all))
    out = []
    for h in range(5):
        pool = np.concatenate([all_rs[k] for k in range(5) if k != h])
        pm = float(np.mean(pool))
        match = bool(np.sign(pm) == np.sign(full_mean)) if full_mean != 0 and np.isfinite(pm) else False
        out.append({"held_out": ANCHORS[h], "year": h,
                    "pool_mean_bps_day": round(pm * 1e4, 4), "sign_match": match})
    return out, sum(1 for L in out if L["sign_match"]), full_mean


def main() -> None:
    hourly = pd.read_parquet(HOURLY)
    hourly["t"] = pd.to_datetime(hourly["t"], utc=True)
    assert bool((hourly["t"] < CAP).all()), "hourly data reaches beyond the cap"
    need = sorted(set(V1_COINS) | set(V2_COINS))
    assert set(need) <= set(hourly["sym"].unique()), "missing coins in hourly_ext"
    hourly = hourly[hourly["sym"].isin(need)].copy()

    opens_all, closes_all = build_daily(hourly, need)
    # alignment spot-check (same as oc_tsmom)
    d = hourly[hourly["sym"] == "BTCUSDT"].set_index("t").sort_index()
    for spot in ["2021-09-24", "2023-01-15", "2025-09-23"]:
        want_c = float(d.loc[pd.Timestamp(spot + " 23:00", tz="UTC"), "close"])
        want_o = float(d.loc[pd.Timestamp(spot + " 00:00", tz="UTC"), "open"])
        got_c = float(closes_all.loc[pd.Timestamp(spot, tz="UTC"), "BTCUSDT"])
        got_o = float(opens_all.loc[pd.Timestamp(spot, tz="UTC"), "BTCUSDT"])
        assert want_c == got_c and want_o == got_o, spot

    reset_F = sample_reset_base()
    try:
        kpi_ref = json.loads(KPI_REF.read_text())
        kpi_years = {y["anchor"][:10]: y for y in kpi_ref["years"]}
    except FileNotFoundError:
        kpi_years = {}

    variants = {}
    for tag, coins, kind in [("V1_5coin_30d", V1_COINS, "30d"),
                             ("V2_btceth_90d_longonly", V2_COINS, "90d_longonly")]:
        years, pooled = run_variant(tag, coins, kind, opens_all, closes_all, reset_F, kpi_years)
        loyo, n_loyo, full_mean = loyo_sign(pooled, [np.array(y["r_sleeve"], float) for y in years])
        n_div = sum(1 for y in years if y["div_pass"])
        n_pos = sum(1 for y in years if y["pass_pos"])
        n_corr = sum(1 for y in years if y["pass_corr"])
        promising = bool(n_div >= 4 and n_loyo >= 4)
        variants[tag] = {
            "coins": coins, "kind": kind,
            "weight": 0.25,
            "years": years,
            "loyo_sleeve_sign": {"full_mean_bps_day": round(float(full_mean) * 1e4, 4),
                                 "pools": loyo, "match": f"{n_loyo}/5"},
            "decision": {"div_pass": f"{n_div}/5", "pos": f"{n_pos}/5",
                         "corr_lt_015": f"{n_corr}/5", "loyo": f"{n_loyo}/5",
                         "promising": promising},
        }
        print(f"{tag}: div {n_div}/5 (pos {n_pos}/5 corr<0.15 {n_corr}/5) loyo {n_loyo}/5 "
              f"promising={promising}", flush=True)
        for y in years:
            print(f"  {y['anchor']} sleeve m={y['sleeve']['monthly_pct']} "
                  f"sharpe={y['sleeve']['sharpe']} dd={y['sleeve']['maxDD_pct']} "
                  f"corr={y['corr_sleeve_base']} base m={y['base']['monthly_pct']} "
                  f"dd={y['base']['maxDD_pct']} comb m={y['combined']['monthly_pct']} "
                  f"dd={y['combined']['maxDD_pct']}", flush=True)

    residuals = []
    kpi_gap = []
    for tag, v in variants.items():
        for y in v["years"]:
            for key, tot in (("r_sleeve", "sleeve"), ("r_base", "base"), ("r_comb", "combined")):
                arr = np.array(y[key], float)
                net = float(np.prod(1 + arr) - 1) * 100
                residuals.append(abs(net - y[tot]["total_pct"]))
            ref = y["kpi_reference"]
            if ref is not None:
                kpi_gap.append(abs(y["base"]["monthly_pct"] - ref["R"]))

    out = {
        "idea": "tsmomvar",
        "rule": "V1: oc_tsmom 30d long/short on 5 majors (equal 10% risk each, cap 1.0x); "
                "V2: BTC/ETH 90d long-only (flat when ret90<=0; 90d vol, 10% target, cap 1.0x); "
                "both: next-day-open rebalance, taker 0.00055, longs fund 0.0001/8h, shorts zero; "
                "combined = R2B1D17BF-reset-base + 0.25xsleeve",
        "base": "B_reset (per-shift normalised year segments, F(a0)=1.0; DD on daily-00:00 grid)",
        "anchors": ANCHORS,
        "data_cap": "2026-09-24T00:00:00Z",
        "g1": "2026-09-23 12:00:00+00:00",
        "variants": variants,
        "checks": {
            "hourly_cap_ok": True,
            "max_compound_residual_pp": round(float(max(residuals)), 10),
            "max_base_monthly_gap_vs_kpi_pp": round(float(max(kpi_gap)), 4) if kpi_gap else None,
            "v411_keys_ok": True,
            "n_days": {tag: [y["n_days"] for y in v["years"]] for tag, v in variants.items()},
        },
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("kpi monthly-R gap (pp):", out["checks"]["max_base_monthly_gap_vs_kpi_pp"], flush=True)
    print("max compound residual (pp):", out["checks"]["max_compound_residual_pp"], flush=True)


if __name__ == "__main__":
    main()
