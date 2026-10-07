"""oc_seasondepth run: BASE (D0+B1) vs RULE (seasonal sigma_eff) on 4 clock phases.

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

import seasondepth as S

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


def main():
    O, C = {}, {}
    base_idx = None
    for sym in MAJORS:
        ii, o, c = load_oc(sym)
        base_idx = ii if base_idx is None else base_idx
        O[sym], C[sym] = o, c
        print(f"loaded OC {sym}", flush=True)
    n_all = len(base_idx)

    qall = S.weekly_slots(base_idx)

    # Seasonal-factor tables: per coin per anchor (walk-forward, < anchor only).
    stab = {}
    for sym in MAJORS:
        stab[sym] = S.factor_table(C[sym].astype(float), base_idx, ANCHORS)
        print(f"factors {sym}", flush=True)
    factor_ranges = {}
    for i, A in enumerate(ANCHORS):
        key = A.date().isoformat()
        per = {sym: [float(np.min(stab[sym][key])), float(np.max(stab[sym][key]))]
               for sym in MAJORS}
        allv = np.concatenate([stab[sym][key] for sym in MAJORS])
        factor_ranges[key] = {
            "per_coin_min_max": per,
            "global_min_max": [float(np.min(allv)), float(np.max(allv))],
            "sqrt_mult_min_max": [float(np.sqrt(np.min(allv))),
                                  float(np.sqrt(np.max(allv)))],
        }

    # Per-phase, per-coin bar opens / BASE sigmas (same-phase grid).
    opens_bar, sig_bar, nb_p = {}, {}, {}
    for p in PHASES:
        shift = p * 60
        nb = (n_all - shift - 1) // 240
        nb_p[p] = nb
        for sym in MAJORS:
            ob = O[sym][shift:shift + nb * 240:240].astype(float)
            sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            opens_bar[(p, sym)], sig_bar[(p, sym)] = ob, sg

    rows = []
    fills_pp = {}
    for sym in MAJORS:
        H, L = load_hl(sym, base_idx)
        Hf, Lf = H.astype(float), L.astype(float)
        Of, Cf = O[sym].astype(float), C[sym].astype(float)
        others = [s for s in MAJORS if s != sym]
        for p in PHASES:
            shift = p * 60
            nb = nb_p[p]
            ob, sg_arr = opens_bar[(p, sym)], sig_bar[(p, sym)]
            n_b = n_r = 0
            for j in range(nb):
                bt = START + pd.Timedelta(minutes=shift + j * 240)
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
                akey = ANCHORS[yi].date().isoformat()
                s = float(stab[sym][akey][int(qall[base])])
                sge = S.sigma_eff(sg, s)
                if not (np.isfinite(sge) and sge > 0):
                    continue
                low_win = Lf[base + S.LIVE_A:base + S.LIVE_B + 1]
                cmat = np.stack([C[b][base + S.LIVE_A - 1:base + S.LIVE_B].astype(float)
                                 for b in others])  # (4, W) closes at T+m-1
                oo = np.array([opens_bar[(p, b)][j] for b in others], dtype=float)
                ss = np.array([sig_bar[(p, b)][j] for b in others], dtype=float)
                nvec = S.n_vector(cmat, oo, ss)
                Ha_b = Hf[base:base + 240]
                La_b = Lf[base:base + 240]
                Ca_b = Cf[base:base + 240]
                Oa_b = Of[base:base + 240]
                for k in S.RUNGS:
                    # BASE arm
                    lv = o1 * (1 - k * sg)
                    if np.isfinite(lv) and lv > 0:
                        ib = S.find_fill(low_win, lv)
                        if ib is not None:
                            f = S.LIVE_A + ib
                            nf = int(nvec[ib])
                            ret, x, _ = S.outcome_from_fill(
                                Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle)
                            if np.isfinite(ret):
                                xd = (bt + pd.Timedelta(minutes=int(x))).date().isoformat() \
                                    if int(x) < 240 else (bt + pd.Timedelta(hours=4)).date().isoformat()
                                rows.append(dict(phase=int(p), sym=sym, y=int(yi),
                                                 k=float(k), arm="BASE", f=int(f),
                                                 n=int(nf), w=float(S.size_mult(nf)),
                                                 ret=float(ret), x=int(x), xd=xd,
                                                 fill=float(lv), s=1.0, sg=float(sg),
                                                 t_bar=bt))
                                n_b += 1
                    # RULE arm (seasonal depth + sigma_eff exits)
                    lvr = o1 * (1 - k * sge)
                    if np.isfinite(lvr) and lvr > 0:
                        ir = S.find_fill(low_win, lvr)
                        if ir is not None:
                            fr = S.LIVE_A + ir
                            nr = int(nvec[ir])
                            retr, xr, _ = S.outcome_from_fill(
                                Ha_b, La_b, Ca_b, Oa_b, fr, lvr, sge, o2, settle)
                            if np.isfinite(retr):
                                xdr = (bt + pd.Timedelta(minutes=int(xr))).date().isoformat() \
                                    if int(xr) < 240 else (bt + pd.Timedelta(hours=4)).date().isoformat()
                                rows.append(dict(phase=int(p), sym=sym, y=int(yi),
                                                 k=float(k), arm="RULE", f=int(fr),
                                                 n=int(nr), w=float(S.size_mult(nr)),
                                                 ret=float(retr), x=int(xr), xd=xdr,
                                                 fill=float(lvr), s=float(s),
                                                 sg=float(sge), t_bar=bt))
                                n_r += 1
            fills_pp[f"{sym}/p{p}"] = {"BASE": int(n_b), "RULE": int(n_r)}
            print(f"{sym} p{p}: BASE={n_b} RULE={n_r}", flush=True)
        del H, L, Hf, Lf, Of, Cf

    df = pd.DataFrame(rows)
    arms = ("BASE", "RULE")
    per_phase = {}
    for p in PHASES:
        per_phase[str(p)] = {}
        for arm in arms:
            per_phase[str(p)][arm] = []
            for yi in range(5):
                sub = df[(df["phase"] == p) & (df["arm"] == arm) & (df["y"] == yi)]
                n = len(sub)
                if n:
                    yv = sub["ret"].to_numpy(float)
                    wv = sub["w"].to_numpy(float)
                    recs = list(zip(sub["xd"].tolist(), (wv * yv).tolist()))
                    Sm, Wd, DD, nd = S.daily_path(recs)
                    mq = wv.mean()
                    recs_rn = list(zip(sub["xd"].tolist(),
                                       ((wv / mq) * yv).tolist())) if mq > 0 else recs
                    Srn, _, _, _ = S.daily_path(recs_rn)
                    win = float((yv > 0).mean())
                    mean = float(yv.mean())
                else:
                    Sm, Wd, DD, nd, win, mean, Srn = 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0
                per_phase[str(p)][arm].append({
                    "year": ANCHORS[yi].date().isoformat(), "n": int(n),
                    "mean": mean, "win_rate": win, "sum": Sm,
                    "sum_renorm": float(Srn), "worst_day": Wd,
                    "max_dd": DD, "ndays": nd})
    mean4 = {}
    for arm in arms:
        mean4[arm] = []
        for yi in range(5):
            ss = [per_phase[str(p)][arm][yi]["sum"] for p in PHASES]
            mean4[arm].append({
                "year": ANCHORS[yi].date().isoformat(),
                "sum_mean4": float(np.mean(ss)),
                "sum_renorm_mean4": float(np.mean(
                    [per_phase[str(p)][arm][yi]["sum_renorm"] for p in PHASES])),
                "trades_mean4": float(np.mean(
                    [per_phase[str(p)][arm][yi]["n"] for p in PHASES])),
                "win_mean4": float(np.mean(
                    [per_phase[str(p)][arm][yi]["win_rate"] for p in PHASES])),
                "worst_mean4": float(np.mean(
                    [per_phase[str(p)][arm][yi]["worst_day"] for p in PHASES])),
                "maxdd_mean4": float(np.mean(
                    [per_phase[str(p)][arm][yi]["max_dd"] for p in PHASES])),
                "per_phase_sums": [float(v) for v in ss]})
    ps = sum(1 for yi in range(5)
             if mean4["RULE"][yi]["sum_mean4"] >= mean4["BASE"][yi]["sum_mean4"])
    pd_ = sum(1 for yi in range(5)
              if mean4["RULE"][yi]["maxdd_mean4"] <= mean4["BASE"][yi]["maxdd_mean4"] + 0.01)
    decision = {"years_sum_ge_base": int(ps),
                "years_dd_not_worse_1pp": int(pd_),
                "promising": bool(ps >= 4 and pd_ >= 4)}
    chk = hashlib.sha256(
        np.round(df[["ret", "w", "fill"]].to_numpy(), 9).tobytes()).hexdigest()[:16] \
        if len(df) else "empty"
    out = {"config": {
        "coins": list(MAJORS), "rungs": list(S.RUNGS),
        "bars": "open in [2021-09-24, 2026-09-24) per phase",
        "grids": "4h from 2020-08-01 00:00 UTC + 0/1/2/3h",
        "live": [S.LIVE_A, S.LIVE_B], "maker": S.MAKER, "taker": S.TAKER,
        "fund_long": 0.0001, "settle_hours": list(SETTLE_HOURS),
        "years": "bar-open in [anchor_i, anchor_{i+1}); Y2 2023-09-24..2024-09-24 is 366d",
        "factor": "s_c(A,q)=mean|1m logret| in weekly-4h-slot q / overall mean, "
                  "window [A-365d, A), per coin per anchor (5x5x42); fallback s=1",
        "rule": "sg_eff=sg*sqrt(s); lv'=O*(1-k*sg_eff); sl/bl/tp from px' with sg_eff",
        "size": "B1 1/(1+n_fill) at own fill minute, n from BASE sigma; raw w*y sums primary",
        "base": "oc_dipexit D0 replica (TP1sg, sl4sg, bl8sg, timeout next open, stop-first)",
        "daily": "exit-date UTC sums of w*y; maxDD of cumulative daily-sum path from 0 (>=0)",
        "mean4": "mean across 4 phases; DD tolerance 0.01 w*y units",
        "side_row": "sum_renorm per (phase,year,arm) with w/mean(w)",
        "note": "unpaired arms: each rung kept iff that arm filled and its net is finite"},
        "factor_ranges": factor_ranges,
        "fills_per_coin_phase": fills_pp, "n_fills": int(len(df)),
        "ledger_checksum": chk, "per_phase": per_phase,
        "mean4": mean4, "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_fills", len(df), "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
