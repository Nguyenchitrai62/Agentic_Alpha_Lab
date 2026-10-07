"""oc_b1wide run: base B1 vs B1-wide (alt-augmented sizing) exact comparison.

Shared fills/exits (signal-only study); only the size weight differs.
One process, one traded coin's H/L in RAM at a time; all-ten-coins 1m
opens/closes held as float32 arrays; bar opens/sigmas precomputed per coin.
See PLAN.md.
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

import wide as W

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ALTS = ("BCHUSDT", "DOTUSDT", "ETCUSDT", "XLMUSDT", "ATOMUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
SETTLE_HOURS = (0, 8, 16)
LW = W.LIVE_B - W.LIVE_A + 1  # 223 live minutes


def load_oc(sym: str):
    """Full-length 1m open + close as float32 (+ minute index)."""
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    elif sym in MAJORS:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/alts2020_intraday_20260930").glob(f"{sym}_1m_20*.parquet"))
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


def eff_of(s, dd):
    if dd > 0:
        return float(s / dd)
    if s > 0:
        return float("inf")
    if s == 0:
        return 0.0
    return float("-inf")


def main():
    idx, O, C = {}, {}, {}
    for sym in MAJORS + ALTS:
        ii, o, c = load_oc(sym)
        idx[sym], O[sym], C[sym] = ii, o, c
        print(f"loaded OC {sym}", flush=True)
    base_idx = idx[MAJORS[0]]
    n_all = len(base_idx)
    nb = (n_all - 1) // 240
    t0 = base_idx[:nb * 240:240]
    opens_bar, sig_bar = {}, {}
    for sym in MAJORS + ALTS:
        ob = O[sym][:nb * 240:240].astype(float)
        sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
        opens_bar[sym], sig_bar[sym] = ob, sg
    del ob, sg

    rows = []
    fills_raw = {s: 0 for s in MAJORS}
    for sym in MAJORS:
        H, L = load_hl(sym, base_idx)
        Oa, Ca, La, Ha = O[sym], C[sym], L, H
        others = [s for s in MAJORS if s != sym]
        n_bar = 0
        for j in range(nb):
            bt = t0[j]
            if not (TRADE_START <= bt < YEAR_END):
                continue
            o1, sg = float(opens_bar[sym][j]), float(sig_bar[sym][j])
            if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                continue
            base = j * 240
            if base + 240 >= n_all:
                continue
            o2m = Oa[base + 240]
            o2 = float(o2m) if np.isfinite(o2m) else np.nan
            settle = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
            yi = year_of(bt)
            low_win = La[base + W.LIVE_A:base + W.LIVE_B + 1].astype(float)
            cmat = np.stack([C[b][base + W.LIVE_A - 1:base + W.LIVE_B].astype(float)
                             for b in others])  # (4, LW) closes at T+m-1
            oo = np.array([opens_bar[b][j] for b in others], dtype=float)
            ss = np.array([sig_bar[b][j] for b in others], dtype=float)
            nvec = W.n_vector(cmat, oo, ss)
            amat = np.stack([C[d][base + W.LIVE_A - 1:base + W.LIVE_B].astype(float)
                             for d in ALTS])  # (5, LW)
            ao = np.array([opens_bar[d][j] for d in ALTS], dtype=float)
            asg = np.array([sig_bar[d][j] for d in ALTS], dtype=float)
            nalt = W.n_alt_vector(amat, ao, asg)
            Ha_b = Ha[base:base + 240].astype(float)
            La_b = La[base:base + 240].astype(float)
            Ca_b = Ca[base:base + 240].astype(float)
            Oa_b = Oa[base:base + 240].astype(float)
            for k in W.RUNGS:
                lv = o1 * (1 - k * sg)
                if not np.isfinite(lv) or lv <= 0:
                    continue
                ib = W.find_fill(low_win, np.full(LW, lv))
                if ib is None:
                    continue
                f = W.LIVE_A + ib
                nf = int(nvec[ib])
                na = int(nalt[ib])
                nw = float(nf) + W.ALT_W * float(na)
                ret, x, _ = W.outcome_from_fill(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle)
                if not np.isfinite(ret):
                    continue
                xd = (bt + pd.Timedelta(minutes=int(x))).date().isoformat() if int(x) < 240 else \
                    (bt + pd.Timedelta(hours=4)).date().isoformat()
                rows.append(dict(sym=sym, y=yi, k=k, f=int(f),
                                 n=int(nf), n_alt=int(na), n_wide=float(nw),
                                 w_base=float(W.size_mult(nf)),
                                 w_wide=float(W.size_mult_wide(nw)),
                                 ret=float(ret), x=int(x), xd=xd,
                                 fill=float(lv), t_bar=bt))
                fills_raw[sym] += 1
            n_bar += 1
        print(f"{sym}: bars={n_bar} fills={fills_raw[sym]}", flush=True)
        del H, L, Ha, La, Oa_b, Ca_b, La_b, Ha_b

    df = pd.DataFrame(rows)
    per_year, full = {"BASE": [], "WIDE": []}, {}
    for arm, wcol in (("BASE", "w_base"), ("WIDE", "w_wide")):
        for yi in range(5):
            sub = df[df["y"] == yi]
            n = len(sub)
            if n:
                w = sub[wcol].to_numpy(float)
                wprime = w / w.mean()
                wy = wprime * sub["ret"].to_numpy(float)
                s_raw = float((w * sub["ret"].to_numpy(float)).sum())
                recs = list(zip(sub["xd"].tolist(), wy.tolist()))
                S, Wd, DD, nd = daily_path(recs)
                win = float((sub["ret"].to_numpy(float) > 0).mean())
                mean = float(sub["ret"].to_numpy(float).mean())
            else:
                S, Wd, DD, nd, win, mean, s_raw = 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0
            per_year[arm].append({"year": ANCHORS[yi].date().isoformat(), "n": int(n),
                                  "mean": mean, "win_rate": win, "sum": S,
                                  "sum_raw": s_raw, "worst_day": Wd,
                                  "max_dd": DD, "eff": eff_of(S, DD), "ndays": nd})
        sub = df
        n = len(sub)
        if n:
            w = sub[wcol].to_numpy(float)
            recs = list(zip(sub["xd"].tolist(), (w / w.mean() * sub["ret"].to_numpy(float)).tolist()))
            S, Wd, DD, nd = daily_path(recs)
            full[arm] = {"n": int(n), "mean": float(sub["ret"].mean()),
                         "win_rate": float((sub["ret"].to_numpy(float) > 0).mean()),
                         "sum": S, "worst_day": Wd, "max_dd": DD,
                         "eff": eff_of(S, DD), "ndays": nd}
        else:
            full[arm] = {"n": 0, "mean": 0.0, "win_rate": 0.0, "sum": 0.0,
                         "worst_day": 0.0, "max_dd": 0.0, "eff": 0.0, "ndays": 0}

    def ok_sum(a, b):
        if a is None or b is None:
            return False
        try:
            a, b = float(a), float(b)
        except Exception:
            return False
        if not (np.isfinite(a) and np.isfinite(b)):
            return False
        return a >= 0.97 * b

    def ok_dd(a, b):
        try:
            a, b = float(a), float(b)
        except Exception:
            return False
        if not (np.isfinite(a) and np.isfinite(b)):
            return False
        return a <= b

    sum_pass = sum(1 for yi in range(5)
                   if ok_sum(per_year["WIDE"][yi]["sum"], per_year["BASE"][yi]["sum"]))
    dd_pass = sum(1 for yi in range(5)
                  if ok_dd(per_year["WIDE"][yi]["max_dd"], per_year["BASE"][yi]["max_dd"]))
    loo = []
    for omit in range(5):
        keep = [yi for yi in range(5) if yi != omit]
        sp = sum(1 for yi in keep
                 if ok_sum(per_year["WIDE"][yi]["sum"], per_year["BASE"][yi]["sum"]))
        dp = sum(1 for yi in keep
                 if ok_dd(per_year["WIDE"][yi]["max_dd"], per_year["BASE"][yi]["max_dd"]))
        loo.append({"omit": ANCHORS[omit].date().isoformat(),
                    "years_sum_ge97": int(sp), "years_dd_not_worse": int(dp)})
    decision = {"years_sum_ge97": int(sum_pass),
                "years_dd_not_worse": int(dd_pass),
                "promising": bool(sum_pass >= 4 and dd_pass >= 4)}
    chk = hashlib.sha256(
        np.round(df[["ret", "w_base", "w_wide", "fill"]].to_numpy(), 9).tobytes()).hexdigest()[:16] \
        if len(df) else "empty"
    out = {"config": {"coins": list(MAJORS), "signal_alts": list(ALTS),
                       "rungs": list(W.RUNGS),
                       "bars": "open in [2021-09-24, 2026-09-24)",
                       "grid": "4h from 2020-08-01 00:00 UTC",
                       "live": [W.LIVE_A, W.LIVE_B],
                       "maker": W.MAKER, "taker": W.TAKER, "fund_long": 0.0001,
                       "settle_hours": list(SETTLE_HOURS),
                       "n": "other majors C(T+m-1) <= O(T)*(1-2.5*sg(T)), v399/oc_b1deeper-exact",
                       "n_alt": "5 alts same 2.5-sigma rule at C(T+m-1); NaN = not flushing",
                       "n_wide": "n + 0.5*n_alt; w_base=1/(1+n), w_wide=1/(1+n_wide)",
                       "fills": "shared static bid at lv, strict low<lv; same f/px/exits both arms",
                       "exits": "D0 replica from fill px (TP=px*(1+sg), sl 4sg, bl 8sg, timeout next open)",
                       "daily": "exit-date UTC sums; maxDD of cumulative daily-sum path from 0",
                       "weights": "renorm per year-arm to mean 1 (primary); raw sums descriptive",
                       "rule": "PROMISING iff DD_wide<=DD_base in >=4/5 yrs AND S_wide>=0.97*S_base in >=4/5 yrs",
                       "note": "fills with non-finite exit nets dropped (identical both arms); signal-only, majors-only trading"},
           "fills_per_coin": fills_raw,
           "n_fills": int(len(df)),
           "ledger_checksum": chk,
           "per_year": per_year, "full": full, "loo": loo, "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_fills", len(df), "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
