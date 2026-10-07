"""oc_deeptp run: BASE (all rungs TP 1.0) vs QUICK (deep rungs TP 0.5)
vs NODEEP (shallow rungs only, TP 1.0). B1 fills + D0 exits replica.

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

import quick as Q

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
SETTLE_HOURS = (0, 8, 16)
W = Q.LIVE_B - Q.LIVE_A + 1  # 223 live minutes
EXPECTED_B1 = {"BTCUSDT": 1067, "ETHUSDT": 1126, "SOLUSDT": 952,
               "BNBUSDT": 1179, "XRPUSDT": 1174}


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


def exit_date(bt, x: int) -> str:
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


def summarize(df, mask, label: str):
    """Renormalised-per-year primary stats for one variant over 5 years + full."""
    per_year, full = [], {}
    for yi in range(5):
        sub = df[mask(yi)]
        n = len(sub)
        if n:
            w = sub["w"].to_numpy(float)
            wprime = w / w.mean()
            wy = wprime * sub["ret"].to_numpy(float)
            s_raw = float((w * sub["ret"].to_numpy(float)).sum())
            recs = list(zip(sub["xd"].tolist(), wy.tolist()))
            S, Wd, DD, nd = daily_path(recs)
            win = float((sub["ret"].to_numpy(float) > 0).mean())
            mean = float(sub["ret"].to_numpy(float).mean())
        else:
            S, Wd, DD, nd, win, mean, s_raw = 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0
        per_year.append({"year": ANCHORS[yi].date().isoformat(), "n": int(n),
                         "mean": mean, "win_rate": win, "sum": S,
                         "sum_raw": s_raw, "worst_day": Wd,
                         "max_dd": DD, "ndays": nd})
    sub = df[mask(None)]
    n = len(sub)
    if n:
        w = sub["w"].to_numpy(float)
        recs = list(zip(sub["xd"].tolist(),
                        (w / w.mean() * sub["ret"].to_numpy(float)).tolist()))
        S, Wd, DD, nd = daily_path(recs)
        full = {"n": int(n), "mean": float(sub["ret"].mean()),
                "win_rate": float((sub["ret"].to_numpy(float) > 0).mean()),
                "sum": S, "worst_day": Wd, "max_dd": DD, "ndays": nd}
    else:
        full = {"n": 0, "mean": 0.0, "win_rate": 0.0, "sum": 0.0,
                "worst_day": 0.0, "max_dd": 0.0, "ndays": 0}
    return per_year, full


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
    fills_coin = {s: 0 for s in MAJORS}
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
            low_win = La[base + Q.LIVE_A:base + Q.LIVE_B + 1].astype(float)
            cmat = np.stack([C[b][base + Q.LIVE_A - 1:base + Q.LIVE_B].astype(float)
                             for b in others])  # (4, W) closes at T+m-1
            oo = np.array([opens_bar[b][j] for b in others], dtype=float)
            ss = np.array([sig_bar[b][j] for b in others], dtype=float)
            nvec = Q.n_vector(cmat, oo, ss)
            Ha_b = Ha[base:base + 240].astype(float)
            La_b = La[base:base + 240].astype(float)
            Ca_b = Ca[base:base + 240].astype(float)
            Oa_b = Oa[base:base + 240].astype(float)
            for k in Q.RUNGS:
                lv = o1 * (1 - k * sg)
                if not np.isfinite(lv) or lv <= 0:
                    continue
                ib = Q.find_fill(low_win, lv)
                if ib is None:
                    continue
                f = Q.LIVE_A + ib
                nf = int(nvec[ib])
                w = float(Q.size_mult(nf))
                mu_q = 0.5 if k >= Q.DEEP_RUNG else 1.0
                rb, xb, hb = Q.outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 1.0, o2, settle)
                if mu_q == 1.0:
                    rq, xq, hq = rb, xb, hb
                else:
                    rq, xq, hq = Q.outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, mu_q,
                                             o2, settle)
                deep = bool(k >= Q.DEEP_RUNG)
                # BASE leg (dropped when NaN, per-variant like oc_b1deeper)
                if np.isfinite(rb):
                    rows.append(dict(sym=sym, y=yi, k=k, deep=deep, variant="BASE",
                                     f=int(f), n=int(nf), w=w, ret=float(rb),
                                     x=int(xb), xd=exit_date(bt, int(xb)),
                                     how=hb, fill=float(lv), t_bar=bt))
                # QUICK leg (same fill; exit net may differ on deep rungs)
                if np.isfinite(rq):
                    rows.append(dict(sym=sym, y=yi, k=k, deep=deep, variant="QUICK",
                                     f=int(f), n=int(nf), w=w, ret=float(rq),
                                     x=int(xq), xd=exit_date(bt, int(xq)),
                                     how=hq, fill=float(lv), t_bar=bt))
                if np.isfinite(rb):
                    fills_coin[sym] += 1
            n_bar += 1
        print(f"{sym}: bars={n_bar} base_fills={fills_coin[sym]}", flush=True)
        del H, L, Ha, La, Oa_b, Ca_b, La_b, Ha_b

    df = pd.DataFrame(rows)
    base_df = df[df["variant"] == "BASE"].reset_index(drop=True)
    quick_df = df[df["variant"] == "QUICK"].reset_index(drop=True)

    # Replica check vs oc_b1deeper B1 fills.
    mism = {s: (int((base_df["sym"] == s).sum()), EXPECTED_B1[s]) for s in MAJORS}
    n_base = len(base_df)
    print("BASE fills", n_base, mism, flush=True)
    assert n_base == 5498, f"replica drift: BASE fills {n_base} != 5498"
    for s in MAJORS:
        assert mism[s][0] == mism[s][1], f"replica drift on {s}: {mism}"

    per_year, full = {}, {}
    per_year["BASE"], full["BASE"] = summarize(
        base_df, lambda yi: (base_df["y"] == yi) if yi is not None else slice(None), "BASE")
    per_year["QUICK"], full["QUICK"] = summarize(
        quick_df, lambda yi: (quick_df["y"] == yi) if yi is not None else slice(None), "QUICK")
    shallow_base = base_df[base_df["deep"] == False].reset_index(drop=True)  # noqa: E712
    per_year["NODEEP"], full["NODEEP"] = summarize(
        shallow_base, lambda yi: (shallow_base["y"] == yi) if yi is not None else slice(None),
        "NODEEP")

    # Deep-subset descriptive: SAME deep fills, BASE nets vs QUICK nets.
    deep_desc = []
    for yi in range(5):
        b = base_df[(base_df["y"] == yi) & (base_df["deep"])]
        q = quick_df[(quick_df["y"] == yi) & (quick_df["deep"])]
        # same fill keys; inner-join on (sym, t_bar, k) to be exact
        key = ["sym", "t_bar", "k"]
        m = pd.merge(b[key + ["ret", "w"]], q[key + ["ret", "w"]],
                     on=key, suffixes=("_b", "_q"))
        nb_ = len(m)
        if nb_:
            wb = m["w_b"].to_numpy(float)
            wq = m["w_q"].to_numpy(float)
            assert (wb == wq).all(), "BASE/QUICK weights differ on shared fills"
            deep_desc.append({
                "year": ANCHORS[yi].date().isoformat(),
                "n": int(nb_),
                "base_mean": float(m["ret_b"].mean()),
                "quick_mean": float(m["ret_q"].mean()),
                "base_win": float((m["ret_b"].to_numpy(float) > 0).mean()),
                "quick_win": float((m["ret_q"].to_numpy(float) > 0).mean()),
                "base_sum_raw": float((wb * m["ret_b"].to_numpy(float)).sum()),
                "quick_sum_raw": float((wq * m["ret_q"].to_numpy(float)).sum()),
            })
        else:
            deep_desc.append({"year": ANCHORS[yi].date().isoformat(), "n": 0,
                              "base_mean": 0.0, "quick_mean": 0.0,
                              "base_win": 0.0, "quick_win": 0.0,
                              "base_sum_raw": 0.0, "quick_sum_raw": 0.0})

    sum_pass, dd_pass = 0, 0
    sum_detail, dd_detail = [], []
    for yi in range(5):
        sb, sq, sn = (per_year[v][yi]["sum"] for v in ("BASE", "QUICK", "NODEEP"))
        db, dq, dn = (per_year[v][yi]["max_dd"] for v in ("BASE", "QUICK", "NODEEP"))
        ok_s = (sq >= sb) and (sq >= sn)
        ok_d = (dq <= db) and (dq <= dn)
        sum_pass += int(bool(ok_s))
        dd_pass += int(bool(ok_d))
        sum_detail.append({"year": per_year["BASE"][yi]["year"], "ok": bool(ok_s),
                           "S_BASE": sb, "S_QUICK": sq, "S_NODEEP": sn})
        dd_detail.append({"year": per_year["BASE"][yi]["year"], "ok": bool(ok_d),
                          "DD_BASE": db, "DD_QUICK": dq, "DD_NODEEP": dn})
    decision = {"years_sum_beats_both": int(sum_pass),
                "years_dd_not_worse_than_both": int(dd_pass),
                "promising": bool(sum_pass >= 4 and dd_pass >= 4)}

    chk = hashlib.sha256(
        np.round(df[["ret", "w", "fill"]].to_numpy(), 9).tobytes()).hexdigest()[:16] if len(df) else "empty"
    out = {"config": {"coins": list(MAJORS), "rungs": list(Q.RUNGS),
                       "deep": "k >= 4.0",
                       "bars": "open in [2021-09-24, 2026-09-24)",
                       "grid": "4h from 2020-08-01 00:00 UTC",
                       "live": [Q.LIVE_A, Q.LIVE_B],
                       "maker": Q.MAKER, "taker": Q.TAKER, "fund_long": 0.0001,
                       "settle_hours": list(SETTLE_HOURS),
                       "n": "other majors C(T+m-1) <= O(T)*(1-2.5*sg(T)), v399-exact",
                       "fill": "B1 static lv, strict low<lv, size 1/(1+n_fill)",
                       "exits": "D0 replica from fill px (sl 4sg, bl 8sg, TP mu*sg; "
                                "BASE mu=1.0 all rungs; QUICK mu=0.5 on deep, 1.0 shallow)",
                       "weights": "w=1/(1+n_fill); primary renorm per year-variant to mean 1",
                       "daily": "exit-date UTC sums; maxDD of cumulative daily-sum path from 0",
                       "note": "fills with non-finite exit nets dropped per variant; "
                               "BASE/QUICK share fills, exit dates may differ"},
           "fills_per_coin_base": fills_coin,
           "n_ledger_rows": int(len(df)),
           "ledger_checksum": chk,
           "replica_check": {"BASE_n": n_base, "per_coin": mism, "expected": EXPECTED_B1},
           "per_year": per_year, "full": full,
           "deep_subset_descriptive": deep_desc,
           "sum_detail": sum_detail, "dd_detail": dd_detail,
           "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_ledger_rows", len(df), "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
