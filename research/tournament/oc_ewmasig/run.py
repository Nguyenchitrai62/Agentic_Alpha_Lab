"""oc_ewmasig run: BASE (sigma360) vs EWMA (sigma_ewma, halflife 60) exact comparison.

One process, one coin's H/L in RAM at a time; all-five-coins 1m opens/closes
held as float32 arrays; bar opens/sigmas precomputed per coin. See PLAN.md.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd

import ewma as E

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
SETTLE_HOURS = (0, 8, 16)
W = E.LIVE_B - E.LIVE_A + 1  # 223 live minutes


def load_oc(sym: str):
    """Full-length 1m open + close as float32 (+ minute index)."""
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "close"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    idx = pd.date_range(START, END, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    O = m["open"].to_numpy(dtype=np.float32)
    C = m["close"].to_numpy(dtype=np.float32)
    del m, parts
    return idx, O, C


def load_hl(sym: str, idx):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "high", "low"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    m = m.set_index("open_time").reindex(idx)
    H = m["high"].to_numpy(dtype=np.float32)
    L = m["low"].to_numpy(dtype=np.float32)
    del m, parts
    return H, L


def year_of(t0):
    for i in range(5):
        lo = ANCHORS[i]
        hi = ANCHORS[i + 1] if i < 4 else YEAR_END
        if lo <= t0 < hi:
            return i
    return None


def daily_path(recs):
    """recs: list of (exit_date_iso, w_y). Returns (S, worst_day, maxDD, ndays)."""
    if not recs:
        return 0.0, 0.0, 0.0, 0
    daily = {}
    for d, v in recs:
        daily[d] = daily.get(d, 0.0) + v
    days = sorted(daily)
    cum, peak, dd = 0.0, 0.0, 0.0
    for d in days:
        cum += daily[d]
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return float(sum(daily.values())), float(min(daily.values())), float(-dd), len(days)


def efficiency(s: float, dd: float) -> float:
    if not np.isfinite(s) or not np.isfinite(dd):
        return float("nan")
    if dd == 0:
        return float("inf") if s > 0 else 0.0
    if dd < 0:
        return float("nan")
    return float(s / dd)


def main():
    idx, O, C = {}, {}, {}
    for sym in MAJORS:
        ii, o, c = load_oc(sym)
        idx[sym], O[sym], C[sym] = ii, o, c
        print(f"loaded OC {sym}", flush=True)
    base_idx = idx[MAJORS[0]]
    n_all = len(base_idx)
    nb = (n_all - 1) // 240
    t0 = base_idx[:nb * 240:240]
    opens_bar, s360_bar, sewma_bar = {}, {}, {}
    for sym in MAJORS:
        ob = O[sym][:nb * 240:240].astype(float)
        r = pd.Series(ob).pct_change()
        s360 = r.rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
        sew = r.ewm(halflife=E.HALFLIFE, min_periods=120, adjust=True).std(bias=False).shift(1).to_numpy()
        opens_bar[sym], s360_bar[sym], sewma_bar[sym] = ob, s360, sew
    del ob, r, s360, sew

    rows = []
    fills_raw = {"BASE": {s: 0 for s in MAJORS}, "EWMA": {s: 0 for s in MAJORS}}
    share_num = [0] * 5
    share_den = [0] * 5
    ratio_med: list[list[float]] = [[] for _ in range(5)]
    for ai, sym in enumerate(MAJORS):
        H, L = load_hl(sym, base_idx)
        Oa, Ca, La, Ha = O[sym], C[sym], L, H
        others = [s for s in MAJORS if s != sym]
        n_bar = 0
        for j in range(nb):
            bt = t0[j]
            if not (TRADE_START <= bt < YEAR_END):
                continue
            o1 = float(opens_bar[sym][j])
            s360 = float(s360_bar[sym][j])
            sew = float(sewma_bar[sym][j])
            if not (np.isfinite(o1) and np.isfinite(s360)) or o1 <= 0 or s360 <= 0:
                continue
            yi = year_of(bt)
            if np.isfinite(sew):
                share_den[yi] += 1
                if sew > s360:
                    share_num[yi] += 1
                if s360 > 0:
                    ratio_med[yi].append(sew / s360)
            base = j * 240
            if base + 240 >= n_all:
                continue
            o2m = Oa[base + 240]
            o2 = float(o2m) if np.isfinite(o2m) else np.nan
            settle = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
            low_win = La[base + E.LIVE_A:base + E.LIVE_B + 1].astype(float)
            cmat = np.stack([C[b][base + E.LIVE_A - 1:base + E.LIVE_B].astype(float)
                             for b in others])  # (4, W) closes at T+m-1
            oo = np.array([opens_bar[b][j] for b in others], dtype=float)
            ss360 = np.array([s360_bar[b][j] for b in others], dtype=float)
            ssew = np.array([sewma_bar[b][j] for b in others], dtype=float)
            nvec_base = E.n_vector(cmat, oo, ss360)
            nvec_ewma = E.n_vector(cmat, oo, ssew)
            Ha_b = Ha[base:base + 240].astype(float)
            La_b = La[base:base + 240].astype(float)
            Ca_b = Ca[base:base + 240].astype(float)
            Oa_b = Oa[base:base + 240].astype(float)
            for k in E.RUNGS:
                lv_b = o1 * (1 - k * s360)
                if np.isfinite(lv_b) and lv_b > 0:
                    ib = E.find_fill(low_win, np.full(W, lv_b))
                    if ib is not None:
                        f = E.LIVE_A + ib
                        nf = int(nvec_base[ib])
                        ret, x, _ = E.outcome_from_fill(Ha_b, La_b, Ca_b, Oa_b, f, float(lv_b), s360, o2, settle)
                        if np.isfinite(ret):
                            xd = (bt + pd.Timedelta(minutes=int(x))).date().isoformat() if int(x) < 240 else \
                                (bt + pd.Timedelta(hours=4)).date().isoformat()
                            rows.append(dict(sym=sym, y=yi, k=k, arm="BASE", f=int(f),
                                              n=int(nf), w=float(E.size_mult(nf)),
                                              ret=float(ret), x=int(x), xd=xd,
                                              fill=float(lv_b), t_bar=bt))
                            fills_raw["BASE"][sym] += 1
                if np.isfinite(sew) and sew > 0:
                    lv_e = o1 * (1 - k * sew)
                    if np.isfinite(lv_e) and lv_e > 0:
                        ia = E.find_fill(low_win, np.full(W, lv_e))
                        if ia is not None:
                            f = E.LIVE_A + ia
                            nf = int(nvec_ewma[ia])
                            ret, x, _ = E.outcome_from_fill(Ha_b, La_b, Ca_b, Oa_b, f, float(lv_e), sew, o2, settle)
                            if np.isfinite(ret):
                                xd = (bt + pd.Timedelta(minutes=int(x))).date().isoformat() if int(x) < 240 else \
                                    (bt + pd.Timedelta(hours=4)).date().isoformat()
                                rows.append(dict(sym=sym, y=yi, k=k, arm="EWMA", f=int(f),
                                                  n=int(nf), w=float(E.size_mult(nf)),
                                                  ret=float(ret), x=int(x), xd=xd,
                                                  fill=float(lv_e), t_bar=bt))
                                fills_raw["EWMA"][sym] += 1
            n_bar += 1
        print(f"{sym}: bars={n_bar} fills BASE={fills_raw['BASE'][sym]} EWMA={fills_raw['EWMA'][sym]}", flush=True)
        del H, L, Ha, La, Oa_b, Ca_b, La_b, Ha_b

    df = pd.DataFrame(rows)
    per_year, full = {}, {}
    for arm in ("BASE", "EWMA"):
        per_year[arm] = []
        for yi in range(5):
            sub = df[(df["arm"] == arm) & (df["y"] == yi)]
            n = len(sub)
            if n:
                w = sub["w"].to_numpy(float)
                wprime = w / w.mean()
                wy = wprime * sub["ret"].to_numpy(float)
                s_raw = float((w * sub["ret"].to_numpy(float)).sum())
                recs = list(zip(sub["xd"].tolist(), wy.tolist()))
                S, Wd, DD, nd = daily_path(recs)
                E_ = efficiency(S, DD)
                win = float((sub["ret"].to_numpy(float) > 0).mean())
                mean = float(sub["ret"].to_numpy(float).mean())
            else:
                S, Wd, DD, nd, win, mean, s_raw, E_ = 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, float("nan")
            per_year[arm].append({"year": ANCHORS[yi].date().isoformat(), "n": int(n),
                                  "mean": mean, "win_rate": win, "sum": S,
                                  "sum_raw": s_raw, "worst_day": Wd,
                                  "max_dd": DD, "efficiency": E_, "ndays": nd})
        sub = df[df["arm"] == arm]
        n = len(sub)
        if n:
            w = sub["w"].to_numpy(float)
            recs = list(zip(sub["xd"].tolist(), (w / w.mean() * sub["ret"].to_numpy(float)).tolist()))
            S, Wd, DD, nd = daily_path(recs)
            E_ = efficiency(S, DD)
            full[arm] = {"n": int(n), "mean": float(sub["ret"].mean()),
                         "win_rate": float((sub["ret"].to_numpy(float) > 0).mean()),
                         "sum": S, "worst_day": Wd, "max_dd": DD, "efficiency": E_, "ndays": nd}
        else:
            full[arm] = {"n": 0, "mean": 0.0, "win_rate": 0.0, "sum": 0.0,
                         "worst_day": 0.0, "max_dd": 0.0, "efficiency": float("nan"), "ndays": 0}

    def pass_sum(y):
        a, b = per_year["EWMA"][y]["sum"], per_year["BASE"][y]["sum"]
        if not (np.isfinite(a) and np.isfinite(b)):
            return False
        return bool(a >= b)

    def pass_dd(y):
        a, b = per_year["EWMA"][y]["max_dd"], per_year["BASE"][y]["max_dd"]
        if not (np.isfinite(a) and np.isfinite(b)):
            return False
        return bool(a <= b)

    sum_pass = sum(1 for y in range(5) if pass_sum(y))
    dd_pass = sum(1 for y in range(5) if pass_dd(y))
    decision = {"years_sum_not_lower": int(sum_pass),
                "years_dd_not_worse": int(dd_pass),
                "promising": bool(sum_pass >= 4 and dd_pass >= 4),
                "sum_pass_years": [bool(pass_sum(y)) for y in range(5)],
                "dd_pass_years": [bool(pass_dd(y)) for y in range(5)]}
    share = []
    for yi in range(5):
        den = share_den[yi]
        frac = (share_num[yi] / den) if den else float("nan")
        med = float(np.median(ratio_med[yi])) if ratio_med[yi] else float("nan")
        share.append({"year": ANCHORS[yi].date().isoformat(),
                      "coin_bars": int(den),
                      "frac_sewma_gt_sg360": frac,
                      "median_sewma_over_sg360": med})
    full_den = sum(share_den)
    full_num = sum(share_num)
    share_full = {"coin_bars": int(full_den),
                  "frac_sewma_gt_sg360": (full_num / full_den) if full_den else float("nan"),
                  "median_sewma_over_sg360": float(np.median([v for lst in ratio_med for v in lst])) if full_den else float("nan")}
    chk = hashlib.sha256(
        np.round(df[["ret", "w", "fill"]].to_numpy(), 9).tobytes()).hexdigest()[:16] if len(df) else "empty"
    out = {"config": {"coins": list(MAJORS), "rungs": list(E.RUNGS),
                       "bars": "open in [2021-09-24, 2026-09-24)",
                       "grid": "4h from 2020-08-01 00:00 UTC",
                       "live": [E.LIVE_A, E.LIVE_B],
                       "maker": E.MAKER, "taker": E.TAKER, "fund_long": 0.0001,
                       "settle_hours": list(SETTLE_HOURS),
                       "sigma360": "pct_change of 4h opens, rolling 360 std ddof=1 min 120, shift 1",
                       "sigma_ewma": "r.ewm(halflife=60, min_periods=120, adjust=True).std(bias=False).shift(1)",
                       "sigma_eff": "sg_ewma directly (replaces sg360 everywhere)",
                       "n": "other majors C(T+m-1) <= O(T)*(1-2.5*sg_arm(T)), v399-exact",
                       "fill": "B1 static bid at arm lv; strict low<lv",
                       "size": "1/(1+n_fill) both arms; renorm per year-arm to mean 1 (primary)",
                       "exits": "D0 replica from fill px with ARM sigma (TP=px*(1+sg), sl 4sg, bl 8sg, timeout next open)",
                       "daily": "exit-date UTC sums; maxDD of cumulative daily-sum path from 0; E=S/maxDD",
                       "note": "fills with non-finite exit nets dropped per arm"},
           "fills_per_coin_raw": fills_raw,
           "n_fills": int(len(df)),
           "ledger_checksum": chk,
           "per_year": per_year, "full": full,
           "ewma_share": {"per_year": share, "full": share_full},
           "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_fills", len(df), "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))
    print(json.dumps(share_full, indent=1))


if __name__ == "__main__":
    main()
