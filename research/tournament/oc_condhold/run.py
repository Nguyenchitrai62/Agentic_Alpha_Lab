"""oc_condhold run: BASE (B1/D0 timeout at next open) vs CONDITIONAL paired test.

CONDITIONAL = BASE, except a BASE timeout that is IN PROFIT at the mid open
(base_ret > 0 strictly) runs the oc_holdext extended leg (+4h, same sl/bl/tp).
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

import condhold as X

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
SETTLE_HOURS = (0, 8, 16)
W = X.LIVE_B - X.LIVE_A + 1  # 223 live minutes


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


def exit_date(bt, x: int):
    if int(x) < 480:
        return (bt + pd.Timedelta(minutes=int(x))).date().isoformat()
    return (bt + pd.Timedelta(hours=8)).date().isoformat()


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


def pad240(a: np.ndarray):
    a = np.asarray(a, dtype=float)
    if len(a) >= 240:
        return a[:240]
    out = np.full(240, np.nan)
    out[:len(a)] = a
    return out


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
    fills_raw = {s: 0 for s in MAJORS}
    n_timeout_base = 0
    n_gate_true = 0
    n_extended = 0
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
            settle_mid = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
            settle_final = (bt + pd.Timedelta(hours=8)).hour in SETTLE_HOURS
            yi = year_of(bt)
            low_win = La[base + X.LIVE_A:base + X.LIVE_B + 1].astype(float)
            cmat = np.stack([C[b][base + X.LIVE_A - 1:base + X.LIVE_B].astype(float)
                             for b in others])  # (4, W) closes at T+m-1
            oo = np.array([opens_bar[b][j] for b in others], dtype=float)
            ss = np.array([sig_bar[b][j] for b in others], dtype=float)
            nvec = X.n_vector(cmat, oo, ss)
            Ha_b = Ha[base:base + 240].astype(float)
            La_b = La[base:base + 240].astype(float)
            Ca_b = Ca[base:base + 240].astype(float)
            Oa_b = Oa[base:base + 240].astype(float)
            H1 = pad240(Ha[base + 240:base + 480].astype(float))
            L1 = pad240(La[base + 240:base + 480].astype(float))
            C1 = pad240(Ca[base + 240:base + 480].astype(float))
            O1 = pad240(Oa[base + 240:base + 480].astype(float))
            o3 = float(Oa[base + 480]) if base + 480 < n_all and np.isfinite(Oa[base + 480]) else np.nan
            for k in X.RUNGS:
                lv = o1 * (1 - k * sg)
                if not np.isfinite(lv) or lv <= 0:
                    continue
                ib = X.find_fill(low_win, lv)
                if ib is None:
                    continue
                f = X.LIVE_A + ib
                nf = int(nvec[ib])
                w = float(X.size_mult(nf))
                b_ret, b_x, b_how, c_ret, c_x, c_how, extd, gate = X.outcome_pair(
                    Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle_mid,
                    H1, L1, C1, O1, o3, settle_final)
                if not (np.isfinite(b_ret) and np.isfinite(c_ret)):
                    continue  # paired-keep rule
                rows.append(dict(sym=sym, y=yi, k=k, f=int(f), n=int(nf), w=w,
                                 fill=float(lv), t_bar=bt,
                                 base_ret=float(b_ret), base_x=int(b_x), base_how=b_how,
                                 cond_ret=float(c_ret), cond_x=int(c_x), cond_how=c_how,
                                 extended=bool(extd), gate=bool(gate),
                                 xd_base=exit_date(bt, int(b_x)),
                                 xd_cond=exit_date(bt, int(c_x))))
                fills_raw[sym] += 1
                if b_how == "time":
                    n_timeout_base += 1
                if gate:
                    n_gate_true += 1
                if extd:
                    n_extended += 1
            n_bar += 1
        print(f"{sym}: bars={n_bar} kept_fills={fills_raw[sym]}", flush=True)
        del H, L, Ha, La, Oa_b, Ca_b, La_b, Ha_b

    df = pd.DataFrame(rows)
    per_year, full = {}, {}
    for arm, rcol, xcol in (("BASE", "base_ret", "xd_base"), ("COND", "cond_ret", "xd_cond")):
        hcol = "base_how" if arm == "BASE" else "cond_how"
        per_year[arm] = []
        for yi in range(5):
            sub = df[df["y"] == yi]
            n = len(sub)
            if n:
                yv = sub[rcol].to_numpy(float)
                w = sub["w"].to_numpy(float)
                wy = w * yv
                recs = list(zip(sub[xcol].tolist(), wy.tolist()))
                S, Wd, DD, nd = daily_path(recs)
                win = float((yv > 0).mean())
                mean = float(yv.mean())
                to = float((sub[hcol].to_numpy() == "time").mean())
                eff = float(S / DD) if DD > 0 else float("nan")
            else:
                S, Wd, DD, nd, win, mean, to, eff = 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, float("nan")
            per_year[arm].append({"year": ANCHORS[yi].date().isoformat(), "n": int(n),
                                  "mean": mean, "win_rate": win, "sum": S,
                                  "timeout_share": to, "worst_day": Wd,
                                  "max_dd": DD, "efficiency": eff, "ndays": nd})
        sub = df
        n = len(sub)
        if n:
            yv = sub[rcol].to_numpy(float)
            w = sub["w"].to_numpy(float)
            recs = list(zip(sub[xcol].tolist(), (w * yv).tolist()))
            S, Wd, DD, nd = daily_path(recs)
            full[arm] = {"n": int(n), "mean": float(yv.mean()),
                         "win_rate": float((yv > 0).mean()),
                         "timeout_share": float((sub[hcol].to_numpy() == "time").mean()),
                         "sum": S, "worst_day": Wd, "max_dd": DD,
                         "efficiency": float(S / DD) if DD > 0 else float("nan"),
                         "ndays": nd}
        else:
            full[arm] = {"n": 0, "mean": 0.0, "win_rate": 0.0, "timeout_share": 0.0,
                         "sum": 0.0, "worst_day": 0.0, "max_dd": 0.0,
                         "efficiency": float("nan"), "ndays": 0}
    # gate descriptives per entry year
    gate_share = []
    for yi in range(5):
        sub = df[df["y"] == yi]
        bt = sub[sub["base_how"] == "time"]
        gs = float(bt["gate"].mean()) if len(bt) else 0.0
        gate_share.append({"year": ANCHORS[yi].date().isoformat(),
                           "base_timeouts": int(len(bt)),
                           "gate_true": int(bt["gate"].sum()) if len(bt) else 0,
                           "gate_share_of_timeouts": gs})

    sum_pass = sum(1 for yi in range(5)
                   if per_year["COND"][yi]["sum"] > per_year["BASE"][yi]["sum"])
    dd_pass = sum(1 for yi in range(5)
                  if per_year["COND"][yi]["max_dd"] <= per_year["BASE"][yi]["max_dd"])
    loo = []
    for left in range(5):
        d = sum(per_year["COND"][yi]["sum"] - per_year["BASE"][yi]["sum"]
                for yi in range(5) if yi != left)
        loo.append({"left_out": ANCHORS[left].date().isoformat(), "diff_loo": d,
                    "cond_higher": bool(d > 0)})
    decision = {"years_sum_higher": int(sum_pass),
                "years_dd_not_worse": int(dd_pass),
                "loo_cond_higher": int(sum(r["cond_higher"] for r in loo)),
                "promising": bool(sum_pass >= 4 and dd_pass >= 4)}
    chk = hashlib.sha256(
        np.round(df[["base_ret", "cond_ret", "w", "fill"]].to_numpy(), 9).tobytes()).hexdigest()[:16] if len(df) else "empty"
    out = {"config": {"coins": list(MAJORS), "rungs": list(X.RUNGS),
                       "bars": "open in [2021-09-24, 2026-09-24)",
                       "grid": "4h from 2020-08-01 00:00 UTC",
                       "live": [X.LIVE_A, X.LIVE_B],
                       "maker": X.MAKER, "taker": X.TAKER, "fund_long": 0.0001,
                       "settle_hours": list(SETTLE_HOURS),
                       "n": "other majors C(T+m-1) <= O(T)*(1-2.5*sg(T)), v399-exact (B1 size only)",
                       "entry": "static lv=O*(1-k*sg), strict low<lv fill at lv, w=1/(1+n_fill), both arms",
                       "base": "D0 replica from fill px (TP=px*(1+sg), sl 4sg close5, bl 8sg, timeout o2)",
                       "conditional": "iff base how==time AND base_ret>0 strictly (o2 above fill+fees+mid fund): same sl/bl/tp into minutes 240..479, timeout o3=T+480; mid fund always, final fund on o3 timeouts; else exit at o2",
                       "keep": "paired: kept iff base AND conditional nets finite",
                       "year": "bar-open anchor year; daily sums by each arm's own exit date; maxDD of cumulative daily-sum path from 0",
                       "note": "all 5 years are research data; PROMISING needs prospective validation"},
           "fills_per_coin_paired": fills_raw,
           "n_fills": int(len(df)),
           "n_base_timeouts": int(n_timeout_base),
           "n_gate_true": int(n_gate_true),
           "n_extended_legs": int(n_extended),
           "ledger_checksum": chk,
           "per_year": per_year, "full": full, "gate": gate_share,
           "loo": loo, "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_fills", len(df), "base_timeouts", n_timeout_base, "gate_true", n_gate_true,
          "extended", n_extended, "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
