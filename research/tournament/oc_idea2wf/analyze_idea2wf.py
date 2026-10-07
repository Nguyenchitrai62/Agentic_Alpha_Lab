"""oc_idea2wf: walk-forward per-coin dip close-stop (4.0 vs 5.5 sigma).

Rung-level replica of oc_idea2 (oc_dipexit D0) with per-coin wide legs,
extended to ALL bars with open in [2020-08-01, 2026-09-24). See PLAN.md
(pre-registered before any outcome). One process, one coin in memory at a
time, float32 1m arrays, RAM < 1 GB. Writes results.json + choice.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
OUT = HERE / "results.json"
CHOICE = HERE / "choice.json"

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
BACKSTOP = 8.0
MU_TP = 1.0
M_NARROW = 4.0
M_WIDE = 5.5

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
A0 = pd.Timestamp("2021-09-24", tz="UTC")
ANCHORS = [A0 + pd.Timedelta(days=365 * k) for k in range(5)]
CUTOFFS = [a - pd.Timedelta(days=7) for a in ANCHORS]
ANCHOR_ISO = [a.date().isoformat() for a in ANCHORS]


def _first_idx(mask: np.ndarray):
    if mask.any():
        return int(np.argmax(mask))
    return None


def outcome_m(Ha, La, Ca, Oa, f: int, lv: float, sg: float, m_sl: float,
              o2: float, settle: bool):
    """Byte-identical copy of oc_idea2.analyze_idea2.outcome_m (M parameterized)."""
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
        if ANCHORS[i] <= t0 < ANCHORS[i] + pd.Timedelta(days=365):
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
        idx, O, H, L, Cc = load_1m(sym)
        assert len(idx) == n_all
        opens = O[:nb * 240:240].astype(float)
        sig = pd.Series(opens).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
        t0 = idx[:nb * 240:240]
        n_fill = 0
        for j in range(nb):
            bt = t0[j]
            if not (START <= bt < END):
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
                rU, xU, hU = outcome_m(Ha, La, Ca, Oa, f, lv, sg, M_NARROW, o2, settle)
                rV, xV, hV = outcome_m(Ha, La, Ca, Oa, f, lv, sg, M_WIDE, o2, settle)
                if not (np.isfinite(rU) and np.isfinite(rV)):
                    continue
                n_fill += 1
                t_exit_u = bt + pd.Timedelta(minutes=int(xU))
                t_exit_v = bt + pd.Timedelta(minutes=int(xV))
                t_exit_max = t_exit_u if t_exit_u >= t_exit_v else t_exit_v
                rungs.append(dict(sym=sym, y=yi, k=k, f=int(f), t_bar=bt,
                                  u=rU, xu=int(xU), hu=hU, v=rV, xv=int(xV), hv=hV,
                                  t_exit_max=t_exit_max))
        fills_coin[sym] = n_fill
        print(f"{sym}: fills={n_fill}", flush=True)
        del idx, O, H, L, Cc, opens, sig, t0

    df = pd.DataFrame(rungs)
    df["d"] = df["v"] - df["u"]

    # Walk-forward choice per (anchor, coin): S>0 -> 5.5 else 4.0.
    choice: dict[str, dict[str, float]] = {}
    train_table: dict[str, dict[str, dict]] = {}
    for ki in range(5):
        aiso = ANCHOR_ISO[ki]
        cut = CUTOFFS[ki]
        choice[aiso] = {}
        train_table[aiso] = {}
        for sym in MAJORS:
            sub = df[(df["sym"] == sym) & (df["t_exit_max"] < cut)]
            s = float(sub["d"].sum()) if len(sub) else 0.0
            m = M_WIDE if s > 0 else M_NARROW
            choice[aiso][sym] = m
            train_table[aiso][sym] = {"n_train": int(len(sub)),
                                      "sum_V_minus_U": float(s),
                                      "choice": float(m)}
    CHOICE.write_text(json.dumps(choice, indent=1))

    # Score WF vs U per anchor year (bar open in [A, A+365d)).
    def stats_for_year(yi: int, use_wf: bool):
        sub = df[df["y"] == yi]
        if len(sub) == 0:
            return {"n": 0, "mean": 0.0, "win_rate": 0.0, "sum": 0.0,
                    "worst_day": 0.0, "max_dd": 0.0, "ndays": 0}
        aiso = ANCHOR_ISO[yi]
        nets: list[float] = []
        daily: dict = {}
        for _, r in sub.iterrows():
            wide = choice[aiso][r["sym"]] == M_WIDE
            net = float(r["v"]) if (use_wf and wide) else float(r["u"])
            x = int(r["xv"]) if (use_wf and wide) else int(r["xu"])
            nets.append(net)
            xd = (r["t_bar"] + pd.Timedelta(minutes=x)).date().isoformat()
            daily[xd] = daily.get(xd, 0.0) + net
        arr = np.array(nets)
        ds = daily_stats(daily)
        return {"n": int(len(sub)), "mean": float(arr.mean()),
                "win_rate": float((arr > 0).mean()),
                "sum": float(arr.sum()), **ds}

    per_year = {"U": [], "WF": []}
    for yi in range(5):
        for name, wf in (("U", False), ("WF", True)):
            per_year[name].append(dict({"year": ANCHOR_ISO[yi],
                                       "window": f"[{ANCHOR_ISO[yi]}, +365d)"},
                                      **stats_for_year(yi, wf)))

    def stats_full(use_wf: bool):
        nets: list[float] = []
        daily: dict = {}
        for yi in range(5):
            aiso = ANCHOR_ISO[yi]
            sub = df[df["y"] == yi]
            for _, r in sub.iterrows():
                wide = choice[aiso][r["sym"]] == M_WIDE
                net = float(r["v"]) if (use_wf and wide) else float(r["u"])
                x = int(r["xv"]) if (use_wf and wide) else int(r["xu"])
                nets.append(net)
                xd = (r["t_bar"] + pd.Timedelta(minutes=x)).date().isoformat()
                daily[xd] = daily.get(xd, 0.0) + net
        arr = np.array(nets) if nets else np.array([0.0])
        ds = daily_stats(daily)
        return {"n": int(len(nets)), "mean": float(arr.mean()),
                "win_rate": float((arr > 0).mean()),
                "sum": float(arr.sum()), **ds}

    full = {"U": stats_full(False), "WF": stats_full(True)}

    D = [per_year["WF"][yi]["sum"] - per_year["U"][yi]["sum"] for yi in range(5)]
    n_pos = int(sum(v > 0 for v in D))
    loo = [float(np.mean([D[j] for j in range(5) if j != i])) for i in range(5)]
    n_loo = int(sum(v > 0 for v in loo))
    wdU = [per_year["U"][yi]["worst_day"] for yi in range(5)]
    wdW = [per_year["WF"][yi]["worst_day"] for yi in range(5)]
    wd_ok = [bool(b >= a) for a, b in zip(wdU, wdW)]
    n_wd = int(sum(wd_ok))
    promising = bool(n_pos >= 4 and n_loo >= 4 and n_wd >= 4)
    verdict = ("PROMISING: walk-forward per-coin stop beats uniform 4sg "
               f"in {n_pos}/5y with LOO>0 in {n_loo}/5 and worst-day-not-worse in {n_wd}/5."
               if promising else
               "NOT PROMISING: walk-forward per-coin stop fails the >=4/5-year "
               f"and LOO>=4/5 and worst-day>=4/5 rule (years>0: {n_pos}/5, LOO>0: {n_loo}/5, worst-day-not-worse: {n_wd}/5).")

    # Per-coin yearly context (WF vs U sums within scored years).
    per_coin = {}
    for sym in MAJORS:
        rows = []
        for yi in range(5):
            aiso = ANCHOR_ISO[yi]
            sub = df[(df["sym"] == sym) & (df["y"] == yi)]
            wide = choice[aiso][sym] == M_WIDE
            sU = float(sub["u"].sum()) if len(sub) else 0.0
            sW = float(sub["v"].sum()) if (len(sub) and wide) else sU
            rows.append({"year": ANCHOR_ISO[yi], "n": int(len(sub)),
                         "choice": float(choice[aiso][sym]),
                         "sum_U": sU, "sum_WF": sW,
                         "stop_rate_U": float((sub["hu"] == "stop").mean()) if len(sub) else 0.0,
                         "stop_rate_W": float((sub["hv"] == "stop").mean()) if (len(sub) and wide) else (float((sub["hu"] == "stop").mean()) if len(sub) else 0.0)})
        per_coin[sym] = rows

    res = {
        "config": {"coins": list(MAJORS), "rungs": list(RUNGS),
                   "bars": "open in [2020-08-01, 2026-09-24); scored years [A_k, A_k+365d)",
                   "anchors": ANCHOR_ISO,
                   "cutoffs": [c.date().isoformat() for c in CUTOFFS],
                   "grid": "4h from 2020-08-01 00:00 UTC", "live": [16, 238],
                   "maker": MAKER, "taker": TAKER, "fund_long": FUND,
                   "settle_hours": [0, 8, 16], "tp": "1.0 sigma",
                   "U": "uniform close-stop 4.0 sigma",
                   "W": "per-coin close-stop 5.5 sigma leg per coin; 8-sigma backstop unchanged; 5m-block CLOSE, exit next-minute open",
                   "rule": "m_c(A_k)=5.5 iff sum(Vc-U) over coin-c rungs with max(t_exit_U,t_exit_Vc) < A_k-7d is strictly > 0, else 4.0",
                   "choice_json": "choice.json {anchor_iso: {SYMBOL: m}}",
                   "note": "paired rungs: kept only if U and Vc both finite; fills identical (stop affects exits only); WF path daily sums use WF exits, U path uses U exits"},
        "fills_per_coin": fills_coin, "n_rungs": int(len(df)),
        "n_scored": int(df["y"].notna().sum()),
        "choice": choice,
        "train": train_table,
        "per_year": per_year, "full": full,
        "D_WF_minus_U": [round(v, 6) for v in D],
        "years_positive": n_pos,
        "loo_mean_D": [round(v, 6) for v in loo],
        "loo_positive": n_loo,
        "worst_day_not_worse_per_year": wd_ok,
        "worst_day_not_worse_count": n_wd,
        "per_coin": per_coin,
        "promising": promising,
        "verdict": verdict,
    }
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({"choice": choice,
                      "D_WF_minus_U": res["D_WF_minus_U"],
                      "years_positive": n_pos, "loo_mean_D": res["loo_mean_D"],
                      "loo_positive": n_loo,
                      "worst_day_not_worse_per_year": wd_ok,
                      "worst_day_not_worse_count": n_wd,
                      "promising": promising}, indent=1), flush=True)
    print(verdict, flush=True)


if __name__ == "__main__":
    main()
