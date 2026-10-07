"""oc_stoptf run: D0 (close5) vs S15 (close15) vs S1 (close1) on 4 clock phases.

One process; majors 1m O/C held as float32, one coin H/L at a time.
See PLAN.md for frozen definitions. No outcome is computed at import time.
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

import stoptf as S

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
PHASES = (0, 1, 2, 3)
SETTLE_HOURS = (0, 8, 16)
W = S.LIVE_B - S.LIVE_A + 1


def load_oc(sym: str):
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


def exit_day(bt, x: int) -> str:
    if int(x) < 240:
        return (bt + pd.Timedelta(minutes=int(x))).date().isoformat()
    return (bt + pd.Timedelta(hours=4)).date().isoformat()


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
    O, C, base_idx = {}, {}, None
    for sym in MAJORS:
        ii, o, c = load_oc(sym)
        base_idx = ii if base_idx is None else base_idx
        O[sym], C[sym] = o, c
        print(f"loaded OC {sym}", flush=True)
    n_all = len(base_idx)

    grids = {}
    for p in PHASES:
        off = p * 60
        nb = (n_all - off) // 240
        t0 = base_idx[off:off + nb * 240:240]
        opens_bar, sig_bar = {}, {}
        for sym in MAJORS:
            ob = O[sym][off:off + nb * 240:240].astype(float)
            sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            opens_bar[sym], sig_bar[sym] = ob, sg
        js = [j for j in range(nb)
              if TRADE_START <= t0[j] < YEAR_END and (off + j * 240 + 240) < n_all]
        grids[p] = dict(off=off, nb=nb, t0=t0, opens=opens_bar, sig=sig_bar, js=js)
        print(f"shift {p}: nb={nb} traded={len(js)}", flush=True)
    del opens_bar, sig_bar

    rows = []
    fills_pp = {}
    for sym in MAJORS:
        H, L = load_hl(sym, base_idx)
        La, Ha = L, H
        others = [b for b in MAJORS if b != sym]
        Oa, Ca = O[sym], C[sym]
        for p in PHASES:
            g = grids[p]
            off, t0 = g["off"], g["t0"]
            opens_bar, sig_bar = g["opens"], g["sig"]
            n_fill = 0
            for j in g["js"]:
                bt = t0[j]
                o1, sg = float(opens_bar[sym][j]), float(sig_bar[sym][j])
                if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                    continue
                base = off + j * 240
                o2m = Oa[base + 240]
                o2 = float(o2m) if np.isfinite(o2m) else np.nan
                settle = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
                yi = year_of(bt)
                if yi is None:
                    continue
                low_win = La[base + S.LIVE_A:base + S.LIVE_B + 1].astype(float)
                cmat = np.stack([C[b][base + S.LIVE_A - 1:base + S.LIVE_B].astype(float)
                                 for b in others])  # (4, W) closes at T+m-1
                oo = np.array([opens_bar[b][j] for b in others], dtype=float)
                ss = np.array([sig_bar[b][j] for b in others], dtype=float)
                nvec = S.n_vector(cmat, oo, ss)
                Ha_b = Ha[base:base + 240].astype(float)
                La_b = La[base:base + 240].astype(float)
                Ca_b = Ca[base:base + 240].astype(float)
                Oa_b = Oa[base:base + 240].astype(float)
                for k in S.RUNGS:
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = S.find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = S.LIVE_A + ib
                    nf = int(nvec[ib])
                    w = float(S.size_mult(nf))
                    r0, x0, h0 = S.outcome_stop_tf(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle, "close5")
                    r15, x15, h15 = S.outcome_stop_tf(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle, "close15")
                    r1, x1, h1 = S.outcome_stop_tf(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle, "close1")
                    if not (np.isfinite(r0) and np.isfinite(r15) and np.isfinite(r1)):
                        continue
                    n_fill += 1
                    rows.append(dict(phase=int(p), sym=sym, y=int(yi), k=float(k),
                                     f=int(f), n=int(nf), w=w,
                                     d0=float(r0), x0=int(x0), h0=h0,
                                     s15=float(r15), x15=int(x15), h15=h15,
                                     s1=float(r1), x1=int(x1), h1=h1,
                                     xd0=exit_day(bt, int(x0)),
                                     xd15=exit_day(bt, int(x15)),
                                     xd1=exit_day(bt, int(x1)), t_bar=bt))
            fills_pp[f"{sym}/p{p}"] = n_fill
            print(f"{sym} p{p}: fills={n_fill}", flush=True)
        del H, L, La, Ha

    df = pd.DataFrame(rows)
    variants = {"D0": ("d0", "xd0", "x0", "h0"),
                "S15": ("s15", "xd15", "x15", "h15"),
                "S1": ("s1", "xd1", "x1", "h1")}

    per_phase = {}
    for p in PHASES:
        per_phase[str(p)] = {}
        for v, (col, xdc, xc, hc) in variants.items():
            per_phase[str(p)][v] = []
            for yi in range(5):
                sub = df[(df["phase"] == p) & (df["y"] == yi)]
                n = len(sub)
                if n:
                    yv = sub[col].to_numpy(float)
                    wv = sub["w"].to_numpy(float)
                    wy = wv * yv
                    recs = list(zip(sub[xdc].tolist(), wy.tolist()))
                    Ss, Wd, DD, nd = daily_path(recs)
                    win = float((yv > 0).mean())
                    mean = float(yv.mean())
                    hh = sub[hc].tolist()
                    stop_n = int(sum(1 for h in hh if h == "stop"))
                    bl_n = int(sum(1 for h in hh if h == "backstop"))
                    stop_bps = float(10000 * yv[np.array(hh) == "stop"].mean()) if stop_n else 0.0
                else:
                    Ss, Wd, DD, nd, win, mean = 0.0, 0.0, 0.0, 0, 0.0, 0.0
                    stop_n, stop_bps, bl_n = 0, 0.0, 0
                per_phase[str(p)][v].append({"year": ANCHORS[yi].date().isoformat(),
                                             "n": int(n), "mean": mean,
                                             "win_rate": win, "sum": Ss,
                                             "stop_n": stop_n,
                                             "stop_mean_bps": stop_bps,
                                             "backstop_n": bl_n,
                                             "worst_day": Wd, "max_dd": DD,
                                             "ndays": nd})

    mean4 = {}
    for v in variants:
        mean4[v] = []
        for yi in range(5):
            ss = [per_phase[str(p)][v][yi]["sum"] for p in PHASES]
            mean4[v].append({"year": ANCHORS[yi].date().isoformat(),
                             "sum_mean4": float(np.mean(ss)),
                             "trades_mean4": float(np.mean([per_phase[str(p)][v][yi]["n"] for p in PHASES])),
                             "win_mean4": float(np.mean([per_phase[str(p)][v][yi]["win_rate"] for p in PHASES])),
                             "stop_n_mean4": float(np.mean([per_phase[str(p)][v][yi]["stop_n"] for p in PHASES])),
                             "stop_bps_mean4": float(np.mean([per_phase[str(p)][v][yi]["stop_mean_bps"] for p in PHASES])),
                             "worst_mean4": float(np.mean([per_phase[str(p)][v][yi]["worst_day"] for p in PHASES])),
                             "maxdd_mean4": float(np.mean([per_phase[str(p)][v][yi]["max_dd"] for p in PHASES])),
                             "per_phase_sums": [float(s) for s in ss]})

    # cascade table: pooled-across-phases daily sums per variant; 10 worst D0 days
    cascade = []
    pooled_daily = {}
    for v, (col, xdc, xc, hc) in variants.items():
        daily = {}
        for _, r in df.iterrows():
            d = r[xdc]
            daily[d] = daily.get(d, 0.0) + float(r["w"]) * float(r[col])
        pooled_daily[v] = daily
    d0days = sorted(pooled_daily["D0"], key=lambda d: pooled_daily["D0"][d])[:10]
    for d in d0days:
        cascade.append({"date": d,
                        "D0": float(pooled_daily["D0"].get(d, 0.0)),
                        "S15": float(pooled_daily["S15"].get(d, 0.0)),
                        "S1": float(pooled_daily["S1"].get(d, 0.0))})

    decision = {}
    for v in ("S15", "S1"):
        ps = sum(1 for yi in range(5)
                 if mean4[v][yi]["sum_mean4"] >= mean4["D0"][yi]["sum_mean4"])
        pd_ = sum(1 for yi in range(5)
                  if mean4[v][yi]["maxdd_mean4"] <= mean4["D0"][yi]["maxdd_mean4"] + 0.01)
        decision[v] = {"years_sum_ge_D0": int(ps),
                       "years_dd_not_worse_1pp": int(pd_),
                       "promising": bool(ps >= 4 and pd_ >= 4)}
    chk = hashlib.sha256(
        np.round(df[["d0", "s15", "s1", "w"]].to_numpy(), 9).tobytes()).hexdigest()[:16] if len(df) else "empty"
    out = {"config": {"coins": list(MAJORS), "rungs": list(S.RUNGS),
                       "bars": "open in [2021-09-24, 2026-09-24) per phase",
                       "grids": "4h from 2020-08-01 00:00 UTC + 0/1/2/3h",
                       "live": [S.LIVE_A, S.LIVE_B], "maker": S.MAKER,
                       "taker": S.TAKER, "fund_long": 0.0001,
                       "settle_hours": list(SETTLE_HOURS),
                       "size": "B1 1/(1+n_fill), raw w*y sums, no renormalisation",
                       "D0": "oc_dipexit replica (TP1sg, sl4sg close5, bl8sg, timeout next open)",
                       "S15": "same levels, stop on (m+1)%15==0 closes (= absolute 15m closes)",
                       "S1": "same levels, stop on every 1m close",
                       "daily": "exit-date UTC sums of w*y; maxDD of cumulative daily-sum path from 0 (>=0)",
                       "mean4": "mean across 4 phases",
                       "cascade": "pooled-across-phases daily w*y sums; 10 worst D0 days",
                       "note": "paired rungs kept only if D0,S15,S1 all finite; fills identical across variants"},
           "fills_per_coin_phase": fills_pp, "n_rungs": int(len(df)),
           "ledger_checksum": chk, "per_phase": per_phase,
           "mean4": mean4, "cascade_worst10_D0": cascade, "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_rungs", len(df), "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
