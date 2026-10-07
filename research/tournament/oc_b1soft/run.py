"""oc_b1soft run: SOFT vs hard B1(F) exact comparison on shared static-bid fills.

One process, one coin's H/L in RAM at a time; all-five-coins 1m opens/closes
held as float32 arrays; bar opens/sigmas precomputed per coin. See PLAN.md.

All four arms share IDENTICAL fills and net returns (static bid at lv, D0
replica from px=lv); only the size weight differs:
  B1(F): w = 1/(1+n_hard(F)), F in {2.5, 2.0, 1.5}
  SOFT : w = 1/(1+n_soft), n_soft = sum clip((d_b-1)/1.5, 0, 1).
Both raw (w*y) and renormalised (w/mean_w_in_arm_year * y) daily paths
(exit-date UTC) are scored; efficiency = sum / maxDD with PLAN guards.
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

import soft as S

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
SETTLE_HOURS = (0, 8, 16)
W = S.LIVE_B - S.LIVE_A + 1  # 223 live minutes
ARMS = ("B25", "B20", "B15", "SOFT")
EXPECTED_B25 = {"BTCUSDT": 1067, "ETHUSDT": 1126, "SOLUSDT": 952,
                "BNBUSDT": 1179, "XRPUSDT": 1174}  # oc_b1deeper B1 replica check


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
    """PLAN guard: DD==0 with S>0 -> +inf; DD==0 with S<=0 -> 0."""
    if dd == 0.0:
        return float("inf") if s > 0 else 0.0
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
    opens_bar, sig_bar = {}, {}
    for sym in MAJORS:
        ob = O[sym][:nb * 240:240].astype(float)
        sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
        opens_bar[sym], sig_bar[sym] = ob, sg
    del ob, sg

    rows = []
    fills_per_coin = {s: 0 for s in MAJORS}
    parity_checked = 0
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
            low_win = La[base + S.LIVE_A:base + S.LIVE_B + 1].astype(float)
            cmat = np.stack([C[b][base + S.LIVE_A - 1:base + S.LIVE_B].astype(float)
                             for b in others])  # (4, W) closes at T+m-1
            oo = np.array([opens_bar[b][j] for b in others], dtype=float)
            ss = np.array([sig_bar[b][j] for b in others], dtype=float)
            nvec25 = S.n_hard_vector(cmat, oo, ss, 2.5)  # replica parity check
            Ha_b = Ha[base:base + 240].astype(float)
            La_b = La[base:base + 240].astype(float)
            Ca_b = Ca[base:base + 240].astype(float)
            Oa_b = Oa[base:base + 240].astype(float)
            for k in S.RUNGS:
                lv = o1 * (1 - k * sg)
                if not np.isfinite(lv) or lv <= 0:
                    continue
                ib = S.find_fill(low_win, np.full(W, lv))
                if ib is None:
                    continue
                f = S.LIVE_A + ib
                d = S.d_vector(cmat[:, ib], oo, ss)
                n25 = S.n_hard_from_d(d, 2.5)
                assert n25 == int(nvec25[ib]), (
                    f"d-form/price-form parity failed {sym} {bt} k={k}")
                parity_checked += 1
                n20 = S.n_hard_from_d(d, 2.0)
                n15 = S.n_hard_from_d(d, 1.5)
                ns = S.n_soft_from_d(d)
                w25, w20, w15, ws = (S.size_mult(n25), S.size_mult(n20),
                                    S.size_mult(n15), S.size_mult(ns))
                ret, x, _ = S.outcome_from_fill(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle)
                if not np.isfinite(ret):
                    continue
                xd = (bt + pd.Timedelta(minutes=int(x))).date().isoformat() if int(x) < 240 else \
                    (bt + pd.Timedelta(hours=4)).date().isoformat()
                rows.append(dict(sym=sym, y=yi, k=k, f=int(f),
                                 n25=int(n25), n20=int(n20), n15=int(n15),
                                 nsoft=float(ns), w25=w25, w20=w20, w15=w15,
                                 wsoft=ws, ret=float(ret), x=int(x), xd=xd,
                                 fill=float(lv), t_bar=bt))
                fills_per_coin[sym] += 1
            n_bar += 1
        print(f"{sym}: bars={n_bar} fills={fills_per_coin[sym]}", flush=True)
        del H, L, Ha, La, Oa_b, Ca_b, La_b, Ha_b

    # Replica provenance: B1(2.5) shares the oc_b1deeper B1 fill set exactly.
    for s in MAJORS:
        assert fills_per_coin[s] == EXPECTED_B25[s], (
            f"replica mismatch {s}: {fills_per_coin[s]} != {EXPECTED_B25[s]}")
    print(f"replica OK; parity checks={parity_checked}", flush=True)

    df = pd.DataFrame(rows)
    wcol = {"B25": "w25", "B20": "w20", "B15": "w15", "SOFT": "wsoft"}
    per_year, full = {}, {}
    for arm in ARMS:
        per_year[arm] = []
        for yi in range(5):
            sub = df[df["y"] == yi]
            n = len(sub)
            if n:
                w = sub[wcol[arm]].to_numpy(float)
                r = sub["ret"].to_numpy(float)
                s_raw = float((w * r).sum())
                recs_raw = list(zip(sub["xd"].tolist(), (w * r).tolist()))
                Sr, Wr, DDr, nd = daily_path(recs_raw)
                Er = efficiency(Sr, DDr)
                wp = w / w.mean()
                s_ren = float((wp * r).sum())
                recs = list(zip(sub["xd"].tolist(), (wp * r).tolist()))
                Sn, Wn, DDn, _ = daily_path(recs)
                En = efficiency(Sn, DDn)
                win = float((r > 0).mean())
                mean = float(r.mean())
            else:
                Sr, Wr, DDr, Er = 0.0, 0.0, 0.0, float("nan")
                Sn, Wn, DDn, En = 0.0, 0.0, 0.0, float("nan")
                win, mean, s_raw, s_ren, nd = 0.0, 0.0, 0.0, 0.0, 0
            per_year[arm].append({"year": ANCHORS[yi].date().isoformat(), "n": int(n),
                                  "mean": mean, "win_rate": win,
                                  "sum_raw": s_raw, "worst_day_raw": Wr,
                                  "max_dd_raw": DDr, "eff_raw": Er,
                                  "sum": Sn, "worst_day": Wn,
                                  "max_dd": DDn, "eff": En, "ndays": nd})
        sub = df
        n = len(sub)
        if n:
            out_f = {}
            for key, col in (("raw", None), ("ren", None)):
                pass
            w = sub[wcol[arm]].to_numpy(float)
            r = sub["ret"].to_numpy(float)
            recs_raw = list(zip(sub["xd"].tolist(), (w * r).tolist()))
            Sr, Wr, DDr, nd = daily_path(recs_raw)
            wp = w / w.mean()
            recs = list(zip(sub["xd"].tolist(), (wp * r).tolist()))
            Sn, Wn, DDn, _ = daily_path(recs)
            full[arm] = {"n": int(n), "mean": float(r.mean()),
                         "win_rate": float((r > 0).mean()),
                         "sum_raw": float((w * r).sum()), "max_dd_raw": DDr,
                         "eff_raw": efficiency(Sr, DDr),
                         "sum": Sn, "worst_day": Wn, "max_dd": DDn,
                         "eff": efficiency(Sn, DDn), "ndays": nd}
        else:
            full[arm] = {"n": 0, "mean": 0.0, "win_rate": 0.0, "sum_raw": 0.0,
                         "max_dd_raw": 0.0, "eff_raw": 0.0, "sum": 0.0,
                         "worst_day": 0.0, "max_dd": 0.0, "eff": 0.0, "ndays": 0}

    def eff_of(arm, yi):
        return per_year[arm][yi]["eff"]

    pass_ren, pass_raw = [], []
    for yi in range(5):
        e_s, e_25, e_20 = eff_of("SOFT", yi), eff_of("B25", yi), eff_of("B20", yi)
        ok = bool(np.isfinite(e_s) and np.isfinite(e_25) and np.isfinite(e_20)
                  and e_s > e_25 and e_s > e_20)
        pass_ren.append(ok)
        r_s = per_year["SOFT"][yi]["eff_raw"]
        r_25 = per_year["B25"][yi]["eff_raw"]
        r_20 = per_year["B20"][yi]["eff_raw"]
        pass_raw.append(bool(np.isfinite(r_s) and np.isfinite(r_25)
                             and np.isfinite(r_20) and r_s > r_25 and r_s > r_20))
    decision = {"years_soft_beats_both_renorm": int(sum(pass_ren)),
                "years_soft_beats_both_raw": int(sum(pass_raw)),
                "pass_renorm_by_year": [bool(v) for v in pass_ren],
                "pass_raw_by_year": [bool(v) for v in pass_raw],
                "promising": bool(sum(pass_ren) >= 4)}
    chk = hashlib.sha256(
        np.round(df[["ret", "w25", "w20", "w15", "wsoft", "fill"]].to_numpy(), 9).tobytes()
    ).hexdigest()[:16] if len(df) else "empty"
    out = {"config": {"coins": list(MAJORS), "rungs": list(S.RUNGS),
                       "bars": "open in [2021-09-24, 2026-09-24)",
                       "grid": "4h from 2020-08-01 00:00 UTC",
                       "live": [S.LIVE_A, S.LIVE_B],
                       "maker": S.MAKER, "taker": S.TAKER, "fund_long": 0.0001,
                       "settle_hours": list(SETTLE_HOURS),
                       "d": "(O_b-C_b(f-1))/(O_b*sg_b); NaN->0",
                       "n_hard": "#{d_b>=F}, F in {2.5,2.0,1.5}; exact boundary counts",
                       "n_soft": "sum clip((d_b-1)/1.5,0,1); NaN->0",
                       "size": "1/(1+n) all arms; shared fills/returns (static lv)",
                       "renorm": "w/mean(w in arm-year) to mean 1 (primary)",
                       "exits": "D0 replica from px=lv (TP=px*(1+sg), sl 4sg, bl 8sg, timeout next open)",
                       "daily": "exit-date UTC sums; maxDD of cumulative daily-sum path from 0",
                       "efficiency": "sum/maxDD; DD==0 & S>0 -> +inf; DD==0 & S<=0 -> 0; no fills -> NaN=FAIL",
                       "decision": "PROMISING iff SOFT renorm eff > B25 AND > B20 in >=4/5 yrs (strict; raw descriptive)",
                       "note": "fills with non-finite exit nets dropped (all arms same kept set)"},
           "fills_per_coin": fills_per_coin,
           "n_fills": int(len(df)),
           "ledger_checksum": chk,
           "per_year": per_year, "full": full, "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_fills", len(df), "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
