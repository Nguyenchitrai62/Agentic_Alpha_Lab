"""oc_tpdecay run: BASE (fixed +1sg TP) vs DECAY (time-decaying TP) paired test.

One process, one coin's H/L in RAM at a time; all-five-coins 1m opens/closes
held as float32 arrays; bar opens/sigmas precomputed per coin. See PLAN.md.
Rung replica = oc_b1deeper B1 (static lv fill, size 1/(1+n_fill)).
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

import tpdecay as D

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
SETTLE_HOURS = (0, 8, 16)
W = D.LIVE_B - D.LIVE_A + 1  # 223 live minutes


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
    opens_bar, sig_bar = {}, {}
    for sym in MAJORS:
        ob = O[sym][:nb * 240:240].astype(float)
        sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
        opens_bar[sym], sig_bar[sym] = ob, sg
    del ob, sg

    rows = []
    fills_per_coin = {s: 0 for s in MAJORS}
    dropped = 0
    for ai, sym in enumerate(MAJORS):
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
            low_win = La[base + D.LIVE_A:base + D.LIVE_B + 1].astype(float)
            cmat = np.stack([C[b][base + D.LIVE_A - 1:base + D.LIVE_B].astype(float)
                             for b in others])  # (4, W) closes at T+m-1
            oo = np.array([opens_bar[b][j] for b in others], dtype=float)
            ss = np.array([sig_bar[b][j] for b in others], dtype=float)
            nvec = D.n_vector(cmat, oo, ss)
            Ha_b = Ha[base:base + 240].astype(float)
            La_b = La[base:base + 240].astype(float)
            Ca_b = Ca[base:base + 240].astype(float)
            Oa_b = Oa[base:base + 240].astype(float)
            for k in D.RUNGS:
                lv = o1 * (1 - k * sg)
                if not np.isfinite(lv) or lv <= 0:
                    continue
                ib = D.find_fill(low_win, lv)
                if ib is None:
                    continue
                f = D.LIVE_A + ib
                nf = int(nvec[ib])
                px = float(lv)
                rb, xb, hb = D.outcome_base(Ha_b, La_b, Ca_b, Oa_b, f, px, sg, o2, settle)
                rd, xd, hd, _ = D.outcome_decay(Ha_b, La_b, Ca_b, Oa_b, f, px, sg, o2, settle)
                if not (np.isfinite(rb) and np.isfinite(rd)):
                    dropped += 1
                    continue
                # Paired: exit dates may differ per arm (earlier TP vs timeout).
                if int(xb) < 240:
                    xdb = (bt + pd.Timedelta(minutes=int(xb))).date().isoformat()
                else:
                    xdb = (bt + pd.Timedelta(hours=4)).date().isoformat()
                if int(xd) < 240:
                    xdd = (bt + pd.Timedelta(minutes=int(xd))).date().isoformat()
                else:
                    xdd = (bt + pd.Timedelta(hours=4)).date().isoformat()
                rows.append(dict(sym=sym, y=yi, k=k, f=int(f), n=int(nf),
                                 w=float(D.size_mult(nf)),
                                 ret_base=float(rb), x_base=int(xb), how_base=hb, xd_base=xdb,
                                 ret_dec=float(rd), x_dec=int(xd), how_dec=hd, xd_dec=xdd,
                                 fill=px, t_bar=bt))
                fills_per_coin[sym] += 1
            n_bar += 1
        print(f"{sym}: bars={n_bar} paired_fills={fills_per_coin[sym]}", flush=True)
        del H, L, Ha, La, Oa_b, Ca_b, La_b, Ha_b

    df = pd.DataFrame(rows)
    per_year, full = {}, {}
    for arm, rcol, dcol in (("BASE", "ret_base", "xd_base"), ("DECAY", "ret_dec", "xd_dec")):
        per_year[arm] = []
        for yi in range(5):
            sub = df[df["y"] == yi]
            n = len(sub)
            if n:
                w = sub["w"].to_numpy(float)
                wprime = w / w.mean()
                wy = wprime * sub[rcol].to_numpy(float)
                recs = list(zip(sub[dcol].tolist(), wy.tolist()))
                S, Wd, DD, nd = daily_path(recs)
                win = float((sub[rcol].to_numpy(float) > 0).mean())
                to = float((sub["how_dec" if arm == "DECAY" else "how_base"].to_numpy() == "time").mean())
                mean = float(sub[rcol].to_numpy(float).mean())
                s_raw = float((w * sub[rcol].to_numpy(float)).sum())
            else:
                S, Wd, DD, nd, win, to, mean, s_raw = 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.0
            per_year[arm].append({"year": ANCHORS[yi].date().isoformat(), "n": int(n),
                                  "mean": mean, "win_rate": win, "timeout_share": to,
                                  "sum": S, "sum_raw": s_raw, "worst_day": Wd,
                                  "max_dd": DD, "ndays": nd})
        n = len(df)
        if n:
            w = df["w"].to_numpy(float)
            recs = list(zip(df[dcol].tolist(), (w / w.mean() * df[rcol].to_numpy(float)).tolist()))
            S, Wd, DD, nd = daily_path(recs)
            full[arm] = {"n": int(n), "mean": float(df[rcol].mean()),
                         "win_rate": float((df[rcol].to_numpy(float) > 0).mean()),
                         "timeout_share": float((df["how_dec" if arm == "DECAY" else "how_base"].to_numpy() == "time").mean()),
                         "sum": S, "worst_day": Wd, "max_dd": DD, "ndays": nd}
        else:
            full[arm] = {"n": 0, "mean": 0.0, "win_rate": 0.0, "timeout_share": 0.0,
                         "sum": 0.0, "worst_day": 0.0, "max_dd": 0.0, "ndays": 0}

    # Leave-one-year-out sums (renormalised within the kept 4 years, paired w').
    loyo = []
    for drop in range(5):
        sub = df[df["y"] != drop]
        if len(sub):
            w = sub["w"].to_numpy(float)
            wp = w / w.mean()
            sb = float((wp * sub["ret_base"].to_numpy(float)).sum())
            sd = float((wp * sub["ret_dec"].to_numpy(float)).sum())
        else:
            sb, sd = 0.0, 0.0
        loyo.append({"drop_year": ANCHORS[drop].date().isoformat(),
                     "sum_base": sb, "sum_dec": sd,
                     "pass": bool(sd >= sb)})

    sum_pass = sum(1 for yi in range(5)
                   if per_year["DECAY"][yi]["sum"] >= per_year["BASE"][yi]["sum"])
    dd_pass = sum(1 for yi in range(5)
                  if per_year["DECAY"][yi]["max_dd"] <= per_year["BASE"][yi]["max_dd"])
    decision = {"years_sum_not_lower": int(sum_pass),
                "years_dd_not_worse": int(dd_pass),
                "promising": bool(sum_pass >= 4 and dd_pass >= 4)}
    chk = hashlib.sha256(
        np.round(df[["ret_base", "ret_dec", "w", "fill"]].to_numpy(), 9).tobytes()).hexdigest()[:16] if len(df) else "empty"
    out = {"config": {"coins": list(MAJORS), "rungs": list(D.RUNGS),
                       "bars": "open in [2021-09-24, 2026-09-24)",
                       "grid": "4h from 2020-08-01 00:00 UTC",
                       "live": [D.LIVE_A, D.LIVE_B],
                       "maker": D.MAKER, "taker": D.TAKER, "fund_long": 0.0001,
                       "settle_hours": list(SETTLE_HOURS),
                       "n": "other majors C(T+m-1) <= O(T)*(1-2.5*sg(T)), v399-exact (sizes only)",
                       "fills": "B1 replica: static lv fill on strict low<lv; paired (drop if either arm NaN)",
                       "size": "1/(1+n_fill) both arms; renorm per year pooled to mean 1 (primary)",
                       "exits": "D0 replica from fill px; BASE TP=px*(1+sg) fixed; DECAY TP(t)=px*(1+sg*(1-0.5*(t-f)/(240-f))) on high(t)>TP(t)",
                       "daily": "exit-date UTC sums per arm; maxDD of cumulative daily-sum path from 0",
                       "note": "timeout/funding/stop-first identical both arms"},
           "fills_per_coin_paired": fills_per_coin,
           "n_fills": int(len(df)),
           "dropped_unpaired": int(dropped),
           "ledger_checksum": chk,
           "per_year": per_year, "full": full, "loyo": loyo, "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_fills", len(df), "dropped", dropped, "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
