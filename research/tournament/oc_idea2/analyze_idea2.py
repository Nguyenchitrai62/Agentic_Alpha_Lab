"""oc_idea2: per-coin dip close-stop distance (XRP 5.5 sigma, rest 4 sigma).

Rung-level replica of oc_dipexit D0 (v293 Asset/outcomes) with a per-coin stop
leg. See PLAN.md (pre-registered before any outcome). One process, one coin in
memory at a time, float32 1m arrays, RAM < 1 GB. Writes results.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
OUT = HERE / "results.json"
D0_JSON = Path("research/tournament/oc_dipexit/results.json")

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
BACKSTOP = 8.0
MU_TP = 1.0
M_UNIFORM = 4.0
M_XRP = 5.5

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]


def _first_idx(mask: np.ndarray):
    if mask.any():
        return int(np.argmax(mask))
    return None


def outcome_m(Ha, La, Ca, Oa, f: int, lv: float, sg: float, m_sl: float,
              o2: float, settle: bool):
    """Exact copy of oc_dipexit exits.outcome_mu with parameterized stop M.

    sl = lv*(1-m_sl*sg); bl = lv*(1-8*sg); tp = lv*(1+1*sg). Same race/priority/
    fees/funding as PLAN.md. Returns (ret, x, how).
    """
    sl = lv * (1 - m_sl * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + MU_TP * sg)
    post = np.arange(f + 1, 240)
    trig = (Ca[f + 1:240] <= sl) & ((post + 1) % 5 == 0)
    ks = _first_idx(trig)
    hb = La[f + 1:240] <= bl
    kb = _first_idx(hb)
    ht = Ha[f + 1:240] > tp
    kt = _first_idx(ht)
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = Oa[x]
        if not np.isfinite(ox):
            return (np.nan, x, "backstop")
        px = bl if ox > bl else ox
        return (px / lv - 1 - MAKER - TAKER, x, "backstop")
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / lv - 1 - 2 * MAKER, x, "tp")
    if ks is not None:
        km = f + 1 + ks
        if km + 1 < 240:
            px = Oa[km + 1]
            x = km + 1
        else:
            px, x = o2, 240
        if not np.isfinite(px):
            return (np.nan, x, "stop")
        ret = px / lv - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop")
    x = 240
    if not np.isfinite(o2):
        return (np.nan, x, "time")
    ret = o2 / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0)
    return (ret, x, "time")


def load_1m(sym: str):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    idx = pd.date_range(START, END, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    O = m["open"].to_numpy(dtype=np.float32)
    H = m["high"].to_numpy(dtype=np.float32)
    L = m["low"].to_numpy(dtype=np.float32)
    C = m["close"].to_numpy(dtype=np.float32)
    del m, parts
    return idx, O, H, L, C


def year_of(t0):
    for i in range(5):
        lo = ANCHORS[i]
        hi = ANCHORS[i + 1] if i < 4 else YEAR_END
        if lo <= t0 < hi:
            return i
    return None


def daily_stats(day_sums: dict):
    if not day_sums:
        return {"worst_day": 0.0, "max_dd": 0.0, "ndays": 0}
    days = sorted(day_sums)
    cum, peak, dd = 0.0, 0.0, 0.0
    worst = min(day_sums.values())
    for d in days:
        cum += day_sums[d]
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return {"worst_day": float(worst), "max_dd": float(dd), "ndays": len(days)}


def main() -> None:
    _full_idx = pd.date_range(START, END, freq="1min")
    n_all = len(_full_idx)
    nb = (n_all - 1) // 240
    rungs = []
    fills_coin = {}
    for sym in MAJORS:
        m_sl_v = M_XRP if sym == "XRPUSDT" else M_UNIFORM
        idx, O, H, L, Cc = load_1m(sym)
        assert len(idx) == n_all
        opens = O[:nb * 240:240].astype(float)
        sig = pd.Series(opens).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
        t0 = idx[:nb * 240:240]
        n_fill = 0
        for j in range(nb):
            bt = t0[j]
            if not (TRADE_START <= bt < YEAR_END):
                continue
            o1, sg = float(opens[j]), float(sig[j])
            if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                continue
            base = j * 240
            if base + 240 >= n_all:
                continue
            o2m = O[base + 240]
            o2 = float(o2m) if np.isfinite(o2m) else np.nan
            settle = (bt + pd.Timedelta(hours=4)).hour in (0, 8, 16)
            Ha = H[base:base + 240].astype(float)
            La = L[base:base + 240].astype(float)
            Ca = Cc[base:base + 240].astype(float)
            Oa = O[base:base + 240].astype(float)
            Lw = La[LIVE_A:LIVE_B + 1]
            yi = year_of(bt)
            for k in RUNGS:
                lv = o1 * (1 - k * sg)
                if not np.isfinite(lv) or lv <= 0:
                    continue
                hit = Lw < lv
                if not hit.any():
                    continue
                f = LIVE_A + int(np.argmax(hit))
                rU, xU, hU = outcome_m(Ha, La, Ca, Oa, f, lv, sg, M_UNIFORM, o2, settle)
                rV, xV, hV = outcome_m(Ha, La, Ca, Oa, f, lv, sg, m_sl_v, o2, settle)
                if not (np.isfinite(rU) and np.isfinite(rV)):
                    continue
                n_fill += 1
                t_fill = bt + pd.Timedelta(minutes=f)
                rungs.append(dict(sym=sym, y=yi, k=k, f=int(f), t_fill=t_fill,
                                  u=rU, xu=int(xU), hu=hU, v=rV, xv=int(xV), hv=hV,
                                  t_bar=bt))
        fills_coin[sym] = n_fill
        print(f"{sym}: fills={n_fill}", flush=True)
        del idx, O, H, L, Cc, opens, sig, t0

    df = pd.DataFrame(rungs)

    def stats_for(col: str, xc: str, sub: pd.DataFrame):
        n = len(sub)
        s = float(sub[col].sum()) if n else 0.0
        daily: dict = {}
        for _, r in sub.iterrows():
            xd = (r["t_bar"] + pd.Timedelta(minutes=int(r[xc]))).date().isoformat()
            daily[xd] = daily.get(xd, 0.0) + float(r[col])
        ds = daily_stats(daily)
        return {"n": int(n),
                "mean": float(sub[col].mean()) if n else 0.0,
                "win_rate": float((sub[col] > 0).mean()) if n else 0.0,
                "sum": s, **ds}

    per_year, full = {}, {}
    for name, col, xc in (("U", "u", "xu"), ("V", "v", "xv")):
        per_year[name] = [dict({"year": ANCHORS[yi].date().isoformat()},
                               **stats_for(col, xc, df[df["y"] == yi])) for yi in range(5)]
        full[name] = stats_for(col, xc, df)

    # cross-check uniform leg vs oc_dipexit D0
    d0 = json.loads(D0_JSON.read_text())["per_year"]["D0"]
    max_abs = max(abs(per_year["U"][yi]["sum"] - d0[yi]["sum"]) for yi in range(5))
    print(f"uniform-vs-D0 max|sum diff|: {max_abs}", flush=True)
    assert max_abs < 1e-9, f"uniform leg diverges from oc_dipexit D0: {max_abs}"

    D = [per_year["V"][yi]["sum"] - per_year["U"][yi]["sum"] for yi in range(5)]
    n_pos = int(sum(v > 0 for v in D))
    loo = [float(np.mean([D[j] for j in range(5) if j != i])) for i in range(5)]
    n_loo = int(sum(v > 0 for v in loo))
    wdU = [per_year["U"][yi]["worst_day"] for yi in range(5)]
    wdV = [per_year["V"][yi]["worst_day"] for yi in range(5)]
    wd_ok = [bool(b >= a) for a, b in zip(wdU, wdV)]
    n_wd = int(sum(wd_ok))
    promising = bool(n_pos >= 4 and n_loo >= 4 and n_wd >= 4)
    verdict = ("PROMISING: per-coin stop (XRP 5.5sg) beats uniform 4sg "
               f"in {n_pos}/5y with LOO>0 in {n_loo}/5 and worst-day-not-worse in {n_wd}/5."
               if promising else
               "NOT PROMISING: per-coin stop (XRP 5.5sg) fails the >=4/5-year "
               f"and LOO>=4/5 and worst-day>=4/5 rule (years>0: {n_pos}/5, LOO>0: {n_loo}/5, worst-day-not-worse: {n_wd}/5).")

    # per-coin context: yearly sums + XRP stop rates
    per_coin = {}
    for sym in MAJORS:
        rows = []
        for yi in range(5):
            sub = df[(df["sym"] == sym) & (df["y"] == yi)]
            rows.append({"year": ANCHORS[yi].date().isoformat(),
                         "n": int(len(sub)),
                         "sum_U": float(sub["u"].sum()) if len(sub) else 0.0,
                         "sum_V": float(sub["v"].sum()) if len(sub) else 0.0,
                         "stop_rate_U": float((sub["hu"] == "stop").mean()) if len(sub) else 0.0,
                         "stop_rate_V": float((sub["hv"] == "stop").mean()) if len(sub) else 0.0})
        per_coin[sym] = rows

    res = {
        "config": {"coins": list(MAJORS), "rungs": list(RUNGS),
                   "bars": "open in [2021-09-24, 2026-09-24)",
                   "grid": "4h from 2020-08-01 00:00 UTC", "live": [16, 238],
                   "maker": MAKER, "taker": TAKER, "fund_long": FUND,
                   "settle_hours": [0, 8, 16], "tp": "1.0 sigma",
                   "U": "uniform close-stop 4.0 sigma (= oc_dipexit D0)",
                   "V": "per-coin close-stop: XRP 5.5 sigma, rest 4.0 sigma; 8-sigma backstop unchanged; 5m-block CLOSE, exit next-minute open",
                   "note": "paired rungs: kept only if U and V both finite; fills identical (stop affects exits only)",
                   "uniform_vs_D0_max_abs_sum_diff": max_abs},
        "fills_per_coin": fills_coin, "n_rungs": len(df),
        "per_year": per_year, "full": full,
        "D_V_minus_U": [round(v, 6) for v in D],
        "years_positive": n_pos,
        "loo_mean_D": [round(v, 6) for v in loo],
        "loo_positive": n_loo,
        "worst_day_not_worse_per_year": wd_ok,
        "worst_day_not_worse_count": n_wd,
        "per_coin": per_coin,
        "promising": promising,
        "verdict": verdict,
    }
    OUT.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("D_V_minus_U", "years_positive", "loo_mean_D",
                                          "loo_positive", "worst_day_not_worse_per_year",
                                          "worst_day_not_worse_count", "promising")}, indent=1), flush=True)
    print(verdict, flush=True)


if __name__ == "__main__":
    main()
