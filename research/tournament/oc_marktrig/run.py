"""oc_marktrig run: BASE (last-price stops) vs MARK (mark-trigger stops).

Majors x R2 depths x 5 anchor years x 4 clock phases, B1 sizes, paired rungs.
See PLAN.md for frozen definitions. One process; majors 1m O/C + premium
held as float32, one coin H/L at a time.
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

import marktrig as M

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
PHASES = (0, 1, 2, 3)
SETTLE_HOURS = (0, 8, 16)
W = M.LIVE_B - M.LIVE_A + 1
PREM_DIR = Path("data/raw/binance_premium_20260928")


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


def load_prem(sym: str, idx):
    f = PREM_DIR / f"{sym}_premium_1m.parquet"
    m = pd.read_parquet(f, columns=["open_time", "close"])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[m["open_time"] < END]  # cap: no premium row >= 2026-09-24 00:00 UTC
    m = m.set_index("open_time").reindex(idx)
    P = m["close"].to_numpy(dtype=np.float32)
    del m
    return P


def year_of(t0):
    for i in range(5):
        lo = ANCHORS[i]
        hi = ANCHORS[i + 1] if i < 4 else YEAR_END
        if lo <= t0 < hi:
            return i
    return None


def daily_path(recs):
    """recs: list of (exit_date_iso, w_y). Returns (S, worst_day, maxDD>=0, ndays)."""
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


def exit_date(bt, x: int) -> str:
    if int(x) < 240:
        return (bt + pd.Timedelta(minutes=int(x))).date().isoformat()
    return (bt + pd.Timedelta(hours=4)).date().isoformat()


def main():
    idx0, O, C, P = {}, {}, {}, {}
    for sym in MAJORS:
        ii, o, c = load_oc(sym)
        idx0[sym], O[sym], C[sym] = ii, o, c
        print(f"loaded OC {sym}", flush=True)
    base_idx = idx0[MAJORS[0]]
    n_all = len(base_idx)
    for sym in MAJORS:
        P[sym] = load_prem(sym, base_idx)
        print(f"loaded PREM {sym}", flush=True)

    opens_bar, sig_bar, nb_p, t0_p = {}, {}, {}, {}
    for p in PHASES:
        shift = p * 60
        nb = (n_all - shift - 1) // 240
        nb_p[p] = nb
        t0_p[p] = [START + pd.Timedelta(minutes=shift + j * 240) for j in range(nb)]
        for sym in MAJORS:
            ob = O[sym][shift:shift + nb * 240:240].astype(float)
            sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            opens_bar[(p, sym)], sig_bar[(p, sym)] = ob, sg

    rows = []
    fills_pp = {}
    for sym in MAJORS:
        H, L = load_hl(sym, base_idx)
        Hf = H.astype(float)
        Lf = L.astype(float)
        del H, L
        Of, Cf, Pf = O[sym].astype(float), C[sym].astype(float), P[sym].astype(float)
        others = [s for s in MAJORS if s != sym]
        for p in PHASES:
            shift = p * 60
            nb = nb_p[p]
            ob, sg_arr = opens_bar[(p, sym)], sig_bar[(p, sym)]
            n_fill = 0
            for j in range(nb):
                bt = t0_p[p][j]
                if not (TRADE_START <= bt < YEAR_END):
                    continue
                o1, sg = float(ob[j]), float(sg_arr[j])
                if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                    continue
                base = shift + j * 240
                if base + 240 >= n_all:
                    continue
                o2m = Of[base + 240]
                o2 = float(o2m) if np.isfinite(o2m) else np.nan
                settle = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
                yi = year_of(bt)
                if yi is None:
                    continue
                low_win = Lf[base + M.LIVE_A:base + M.LIVE_B + 1]
                cmat = np.stack([C[b][base + M.LIVE_A - 1:base + M.LIVE_B].astype(float)
                                 for b in others])
                oo = np.array([opens_bar[(p, b)][j] for b in others], dtype=float)
                ss = np.array([sig_bar[(p, b)][j] for b in others], dtype=float)
                nvec = M.n_vector(cmat, oo, ss)
                Ha_b = Hf[base:base + 240]
                La_b = Lf[base:base + 240]
                Ca_b = Cf[base:base + 240]
                Oa_b = Of[base:base + 240]
                if base >= 4:
                    prem_ext = Pf[base - 4:base + 240]
                else:
                    pad = np.full((4 - base,), np.nan)
                    prem_ext = np.concatenate([pad, Pf[0:base + 240]])
                if prem_ext.shape != (244,):
                    continue
                mark_b = M.build_mark(Ca_b, prem_ext)
                for k in M.RUNGS:
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = M.find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = M.LIVE_A + ib
                    nf = int(nvec[ib])
                    w = float(M.size_mult(nf))
                    rb, xb, hb = M.outcome_base(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle)
                    rm, xm, hm = M.outcome_mark(Ha_b, La_b, Ca_b, Oa_b, mark_b, f, lv, sg, o2, settle)
                    if not (np.isfinite(rb) and np.isfinite(rm)):
                        continue
                    n_fill += 1
                    rows.append(dict(phase=int(p), sym=sym, y=int(yi), k=float(k),
                                     f=int(f), n=int(nf), w=w,
                                     base=float(rb), xb=int(xb), hbase=hb,
                                     mark=float(rm), xm=int(xm), hmark=hm,
                                     xd_base=exit_date(bt, int(xb)),
                                     xd_mark=exit_date(bt, int(xm)), t_bar=bt))
            fills_pp[f"{sym}/p{p}"] = n_fill
            print(f"{sym} p{p}: paired fills={n_fill}", flush=True)
        del Hf, Lf, Of, Cf, Pf

    df = pd.DataFrame(rows)
    if len(df) == 0:
        raise SystemExit("no paired fills")
    variants = {"BASE": ("base", "xd_base", "xb", "hbase"),
                "MARK": ("mark", "xd_mark", "xm", "hmark")}

    def cell_stats(sub, col, xdc, hc):
        n = len(sub)
        if n == 0:
            return {"n": 0, "mean": 0.0, "win_rate": 0.0, "sum": 0.0,
                    "worst_day": 0.0, "max_dd": 0.0, "ndays": 0,
                    "n_stop": 0, "n_backstop": 0, "n_tp": 0, "n_time": 0}
        yv = sub[col].to_numpy(float)
        wv = sub["w"].to_numpy(float)
        recs = list(zip(sub[xdc].tolist(), (wv * yv).tolist()))
        S, Wd, DD, nd = daily_path(recs)
        h = sub[hc].tolist()
        return {"n": int(n), "mean": float(yv.mean()),
                "win_rate": float((yv > 0).mean()), "sum": S,
                "worst_day": Wd, "max_dd": DD, "ndays": int(nd),
                "n_stop": int(sum(1 for v in h if v == "stop")),
                "n_backstop": int(sum(1 for v in h if v == "backstop")),
                "n_tp": int(sum(1 for v in h if v == "tp")),
                "n_time": int(sum(1 for v in h if v == "time"))}

    per_phase = {}
    for p in PHASES:
        per_phase[str(p)] = {}
        for v, (col, xdc, xc, hc) in variants.items():
            per_phase[str(p)][v] = []
            for yi in range(5):
                sub = df[(df["phase"] == p) & (df["y"] == yi)]
                per_phase[str(p)][v].append(
                    {"year": ANCHORS[yi].date().isoformat(),
                     **cell_stats(sub, col, xdc, hc)})

    # avoided-stop decomposition per (phase, year)
    avoided = {}
    confusion = {}
    for p in PHASES:
        avoided[str(p)] = []
        confusion[str(p)] = []
        for yi in range(5):
            sub = df[(df["phase"] == p) & (df["y"] == yi)]
            bs = sub[sub["hbase"].isin(["stop", "backstop"])]
            n_bs = len(bs)
            av = bs[bs["hmark"].isin(["tp", "time"])]
            av_tp = int((bs["hmark"] == "tp").sum())
            av_tm = int((bs["hmark"] == "time").sum())
            deeper = int(((bs["hbase"] == "stop") & (bs["hmark"] == "backstop")).sum())
            still = int((bs["hmark"] == "stop").sum())
            kept_back = int((bs["hmark"] == "backstop").sum())
            conf = {}
            for bh in ("stop", "backstop", "tp", "time"):
                for mh in ("stop", "backstop", "tp", "time"):
                    conf[f"{bh}>{mh}"] = int(((sub["hbase"] == bh) & (sub["hmark"] == mh)).sum())
            avoided[str(p)].append({"year": ANCHORS[yi].date().isoformat(),
                                    "n_base_stops": int(n_bs),
                                    "n_avoided": int(len(av)),
                                    "n_avoid_tp": av_tp, "n_avoid_time": av_tm,
                                    "n_deeper_stop_to_backstop": deeper,
                                    "n_still_stop": still,
                                    "n_mark_backstop": kept_back,
                                    "avoid_rate": float(len(av) / n_bs) if n_bs else 0.0})
            confusion[str(p)].append({"year": ANCHORS[yi].date().isoformat(), **conf})

    mean4, disp = {}, {}
    for v in variants:
        mean4[v], disp[v] = [], []
        for yi in range(5):
            ss = [per_phase[str(p)][v][yi]["sum"] for p in PHASES]
            dd = [per_phase[str(p)][v][yi]["max_dd"] for p in PHASES]
            ww = [per_phase[str(p)][v][yi]["worst_day"] for p in PHASES]
            av = [avoided[str(p)][yi]["n_avoided"] for p in PHASES]
            bs = [avoided[str(p)][yi]["n_base_stops"] for p in PHASES]
            mean4[v].append({"year": ANCHORS[yi].date().isoformat(),
                             "sum_mean4": float(np.mean(ss)),
                             "trades_mean4": float(np.mean([per_phase[str(p)][v][yi]["n"] for p in PHASES])),
                             "win_mean4": float(np.mean([per_phase[str(p)][v][yi]["win_rate"] for p in PHASES])),
                             "worst_mean4": float(np.mean(ww)),
                             "maxdd_mean4": float(np.mean(dd)),
                             "stop_mean4": float(np.mean([per_phase[str(p)][v][yi]["n_stop"]
                                                          + per_phase[str(p)][v][yi]["n_backstop"]
                                                          for p in PHASES])),
                             "per_phase_sums": [float(s) for s in ss]})
            disp[v].append(float(max(ss) - min(ss)))
        # attach avoided means for MARK context (base-stop denominators)
    avoided_mean4 = []
    for yi in range(5):
        avoided_mean4.append({"year": ANCHORS[yi].date().isoformat(),
                              "base_stops_mean4": float(np.mean([avoided[str(p)][yi]["n_base_stops"] for p in PHASES])),
                              "avoided_mean4": float(np.mean([avoided[str(p)][yi]["n_avoided"] for p in PHASES])),
                              "avoid_tp_mean4": float(np.mean([avoided[str(p)][yi]["n_avoid_tp"] for p in PHASES])),
                              "avoid_time_mean4": float(np.mean([avoided[str(p)][yi]["n_avoid_time"] for p in PHASES])),
                              "deeper_mean4": float(np.mean([avoided[str(p)][yi]["n_deeper_stop_to_backstop"] for p in PHASES])),
                              "avoid_rate_mean4": float(np.mean([avoided[str(p)][yi]["avoid_rate"] for p in PHASES]))})

    # cascade table: 10 worst exit dates by BASE pooled daily sum
    brec = list(zip(df["xd_base"].tolist(), (df["w"].to_numpy(float) * df["base"].to_numpy(float)).tolist()))
    mrec = list(zip(df["xd_mark"].tolist(), (df["w"].to_numpy(float) * df["mark"].to_numpy(float)).tolist()))
    bd, md = {}, {}
    for d, v in brec:
        bd[d] = bd.get(d, 0.0) + v
    for d, v in mrec:
        md[d] = md.get(d, 0.0) + v
    worst10 = sorted(bd, key=lambda d: bd[d])[:10]
    bstop_d, mstop_d, btp_d, mtp_d = {}, {}, {}, {}
    for _, r in df.iterrows():
        if r["hbase"] in ("stop", "backstop"):
            bstop_d[r["xd_base"]] = bstop_d.get(r["xd_base"], 0) + 1
        if r["hmark"] in ("stop", "backstop"):
            mstop_d[r["xd_mark"]] = mstop_d.get(r["xd_mark"], 0) + 1
        if r["hbase"] == "tp":
            btp_d[r["xd_base"]] = btp_d.get(r["xd_base"], 0) + 1
        if r["hmark"] == "tp":
            mtp_d[r["xd_mark"]] = mtp_d.get(r["xd_mark"], 0) + 1
    cascade = [dict(date=d, base_sum=float(bd[d]), mark_sum=float(md.get(d, 0.0)),
                    delta=float(md.get(d, 0.0) - bd[d]),
                    base_stops=int(bstop_d.get(d, 0)), mark_stops=int(mstop_d.get(d, 0)),
                    base_tp=int(btp_d.get(d, 0)), mark_tp=int(mtp_d.get(d, 0)))
               for d in worst10]

    ps = sum(1 for yi in range(5) if mean4["MARK"][yi]["sum_mean4"] >= mean4["BASE"][yi]["sum_mean4"])
    pd_ = sum(1 for yi in range(5) if mean4["MARK"][yi]["maxdd_mean4"] <= mean4["BASE"][yi]["maxdd_mean4"])
    pw = sum(1 for yi in range(5) if mean4["MARK"][yi]["worst_mean4"] >= mean4["BASE"][yi]["worst_mean4"])
    decision = {"years_sum_ge_base": int(ps), "years_dd_not_worse": int(pd_),
                "years_wd_not_worse": int(pw),
                "promising": bool(ps >= 4 and pd_ >= 4 and pw >= 4)}
    chk = hashlib.sha256(
        np.round(df[["base", "mark", "w"]].to_numpy(), 9).tobytes()).hexdigest()[:16] if len(df) else "empty"
    out = {"config": {"coins": list(MAJORS), "rungs": list(M.RUNGS),
                       "bars": "open in [2021-09-24, 2026-09-24) per phase",
                       "grids": "4h from 2020-08-01 00:00 UTC + 0/1/2/3h",
                       "live": [M.LIVE_A, M.LIVE_B], "maker": M.MAKER,
                       "taker": M.TAKER, "fund_long": 0.0001,
                       "settle_hours": list(SETTLE_HOURS),
                       "size": "B1 1/(1+n_fill), raw w*y sums, no renormalisation; fills identical across arms",
                       "BASE": "oc_dipexit D0 replica (TP1sg limit; close5 on last close; backstop on last low at min(bl,open); timeout next open)",
                       "MARK": "same levels/TP/timeout; close5 fires on mark(m)<=sl exit next open; backstop fires on mark(t)<=bl exit next open (taker); mark(t)=close(t)*(1+mean5(premium close[t-4..t]))",
                       "premium": "data/raw/binance_premium_20260928/{SYM}_premium_1m.parquet close, rows >= 2026-09-24 dropped; NaN mark never triggers",
                       "daily": "exit-date UTC sums of w*y per arm's own exit date; maxDD of cumulative daily-sum path from 0 (>=0)",
                       "mean4": "mean across 4 phases",
                       "cascade": "10 worst exit dates by BASE pooled daily sum (all phases)",
                       "avoided": "over paired rungs with BASE stop/backstop: avoided=MARK tp/time; deeper=BASE stop and MARK backstop",
                       "note": "paired rungs kept only if BASE and MARK nets both finite"},
           "fills_per_coin_phase": fills_pp, "n_rungs": int(len(df)),
           "ledger_checksum": chk, "per_phase": per_phase,
           "mean4": mean4, "dispersion": disp, "avoided": avoided,
           "avoided_mean4": avoided_mean4, "confusion": confusion,
           "cascade": cascade, "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_rungs", len(df), "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
