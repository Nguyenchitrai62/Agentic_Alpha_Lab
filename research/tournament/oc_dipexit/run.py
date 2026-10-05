"""oc_dipexit run: per-coin replica + E1-E4 exact rung outcomes -> results.json.

One process, one coin at a time, float32 1m arrays. See PLAN.md for definitions.
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

import exits as E
START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")


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


def main():
    _full_idx = pd.date_range(START, END, freq="1min")
    n_all = len(_full_idx)
    nb = (n_all - 1) // 240
    assert (START + pd.Timedelta(minutes=nb * 240)) == END - pd.Timedelta(minutes=(n_all - 1) % 240), "grid"
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
            Lw = La[E.LIVE_A:E.LIVE_B + 1]
            yi = year_of(bt)
            for k in E.RUNGS:
                lv = o1 * (1 - k * sg)
                if not np.isfinite(lv) or lv <= 0:
                    continue
                hit = Lw < lv
                if not hit.any():
                    continue
                f = E.LIVE_A + int(np.argmax(hit))
                r05, x05, _ = E.outcome_mu(Ha, La, Ca, Oa, f, lv, sg, 0.5, o2, settle)
                r10, x10, _ = E.outcome_mu(Ha, La, Ca, Oa, f, lv, sg, 1.0, o2, settle)
                r15, x15, _ = E.outcome_mu(Ha, La, Ca, Oa, f, lv, sg, 1.5, o2, settle)
                rE2, xE2, _ = E.outcome_e2(Ha, La, Ca, Oa, f, lv, sg, o2, settle)
                rE3, xE3, _ = E.outcome_e3(Ha, La, Ca, Oa, f, lv, sg, o2, settle)
                rE4, xE4, _ = E.outcome_e4(Ha, La, Ca, Oa, f, lv, sg, o1, o2, settle)
                vals = (r05, r10, r15, rE2, rE3, rE4)
                if not all(np.isfinite(v) for v in vals):
                    continue
                n_fill += 1
                t_fill = bt + pd.Timedelta(minutes=f)
                rungs.append(dict(sym=sym, y=yi, k=k, f=int(f), t_fill=t_fill,
                                  d0=r10, x10=int(x10), e1a=r05, xe1a=int(x05),
                                  e1b=r15, xe1b=int(x15), e2=rE2, xe2=int(xE2),
                                  e3=rE3, xe3=int(xE3), e4=rE4, xe4=int(xE4),
                                  t_bar=bt))
        fills_coin[sym] = n_fill
        print(f"{sym}: fills={n_fill}", flush=True)
        del idx, O, H, L, Cc, opens, sig, t0

    df = pd.DataFrame(rungs)
    df["e1"] = 0.5 * df["e1a"] + 0.5 * df["e1b"]
    variants = {"D0": "d0", "E1": "e1", "E2": "e2", "E3": "e3", "E4": "e4"}
    xcol = {"D0": "x10", "E1": None, "E2": "xe2", "E3": "xe3", "E4": "xe4"}

    def daily_stats(sub, vcol, xc):
        # exit-date daily sums; E1 splits halves to their own exit days
        daily = {}
        if vcol == "e1":
            for _, r in sub.iterrows():
                for leg, xx in (("e1a", "xe1a"), ("e1b", "xe1b")):
                    xd = (r["t_bar"] + pd.Timedelta(minutes=int(r[xx]))).date().isoformat()
                    daily[xd] = daily.get(xd, 0.0) + 0.5 * float(r[leg])
        else:
            for _, r in sub.iterrows():
                xd = (r["t_bar"] + pd.Timedelta(minutes=int(r[xc]))).date().isoformat()
                daily[xd] = daily.get(xd, 0.0) + float(r[vcol])
        if not daily:
            return {"worst_day": 0.0, "max_dd": 0.0, "ndays": 0}
        days = sorted(daily)
        cum, peak, dd = 0.0, 0.0, 0.0
        worst = min(daily.values())
        for d in days:
            cum += daily[d]
            peak = max(peak, cum)
            dd = min(dd, cum - peak)
        return {"worst_day": float(worst), "max_dd": float(dd), "ndays": len(days)}

    per_year, full = {}, {}
    for v, col in variants.items():
        per_year[v] = []
        for yi in range(5):
            sub = df[df["y"] == yi]
            n = len(sub)
            s = float(sub[col].sum()) if n else 0.0
            per_year[v].append({
                "year": ANCHORS[yi].date().isoformat(),
                "n": int(n),
                "mean": float(sub[col].mean()) if n else 0.0,
                "win_rate": float((sub[col] > 0).mean()) if n else 0.0,
                "sum": s,
                **daily_stats(sub, col, xcol[v]),
            })
        n = len(df)
        full[v] = {"n": int(n), "mean": float(df[col].mean()) if n else 0.0,
                   "win_rate": float((df[col] > 0).mean()) if n else 0.0,
                   "sum": float(df[col].sum()) if n else 0.0,
                   **daily_stats(df, col, xcol[v])}

    beats = {}
    for v in ("E1", "E2", "E3", "E4"):
        w = sum(1 for yi in range(5) if per_year[v][yi]["sum"] >= per_year["D0"][yi]["sum"])
        wd_ok = all(per_year[v][yi]["worst_day"] >= per_year["D0"][yi]["worst_day"] for yi in range(5))
        beats[v] = {"years_ge_D0": int(w), "worst_day_not_worse_all_years": bool(wd_ok),
                    "promising": bool(w >= 4 and wd_ok)}
    chk = hashlib.sha256(np.round(df[["d0", "e1", "e2", "e3", "e4"]].to_numpy(), 9).tobytes()).hexdigest()[:16]
    out = {"config": {"coins": list(MAJORS), "rungs": list(E.RUNGS),
                       "bars": "open in [2021-09-24, 2026-09-24)",
                       "grid": "4h from 2020-08-01 00:00 UTC", "live": [16, 238],
                       "maker": E.MAKER, "taker": E.TAKER, "fund_long": 0.0001,
                       "settle_hours": [0, 8, 16], "E1": "0.5*y0.5+0.5*y1.5 halves to own exit days",
                       "E2": "TP1 + time exit at open(f+120), taker, no funding",
                       "E3": "TP1 + close5 stop -> breakeven after +0.5sg touch",
                       "E4": "TP=min(bar_open, lv*(1+2sg))",
                       "note": "paired rungs: kept only if D0,E1 legs,E2,E3,E4 all finite"},
           "fills_per_coin": fills_coin, "n_rungs": len(df),
           "ledger_checksum": chk,
           "per_year": per_year, "full": full, "decision": beats}
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    df.to_parquet(HERE / "rungs.parquet", index=False)
    print("n_rungs", len(df), "checksum", chk, flush=True)
    print(json.dumps(beats, indent=1))


if __name__ == "__main__":
    main()
