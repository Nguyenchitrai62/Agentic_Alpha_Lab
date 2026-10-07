"""oc_fillttl run: D0 vs fill-relative T240/T120 on 4 clock phases.

One process; majors 1m O/C held as float32, one coin H/L at a time.
See PLAN.md for frozen definitions.
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

import fillttl as F

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
PHASES = (0, 1, 2, 3)
SETTLE_HOURS = (0, 8, 16)
W = F.LIVE_B - F.LIVE_A + 1


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


def count_settlements(t_fill: pd.Timestamp, t_exit: pd.Timestamp) -> int:
    """# of 00/08/16 UTC stamps with t_fill < ts <= t_exit."""
    n = 0
    day0 = (t_fill - pd.Timedelta(hours=24)).floor("D")
    for d in range(4):
        base = day0 + pd.Timedelta(days=d)
        for h in SETTLE_HOURS:
            ts = base + pd.Timedelta(hours=h)
            if t_fill < ts <= t_exit:
                n += 1
    return n


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
    idx0, O, C = {}, {}, {}
    for sym in MAJORS:
        ii, o, c = load_oc(sym)
        idx0[sym], O[sym], C[sym] = ii, o, c
        print(f"loaded OC {sym}", flush=True)
    base_idx = idx0[MAJORS[0]]
    n_all = len(base_idx)

    # per-phase, per-coin bar opens/sigmas
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
        Hf, Lf = H.astype(float), L.astype(float)
        Of, Cf = O[sym].astype(float), C[sym].astype(float)
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
                settle_d0 = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
                yi = year_of(bt)
                if yi is None:
                    continue
                low_win = Lf[base + F.LIVE_A:base + F.LIVE_B + 1]
                cmat = np.stack([C[b][base + F.LIVE_A - 1:base + F.LIVE_B].astype(float)
                                 for b in others])  # (4, W) closes at T+m-1
                oo = np.array([opens_bar[(p, b)][j] for b in others], dtype=float)
                ss = np.array([sig_bar[(p, b)][j] for b in others], dtype=float)
                nvec = F.n_vector(cmat, oo, ss)
                Ha_b = Hf[base:base + 240]
                La_b = Lf[base:base + 240]
                Ca_b = Cf[base:base + 240]
                Oa_b = Of[base:base + 240]
                for k in F.RUNGS:
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = F.find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = F.LIVE_A + ib
                    nf = int(nvec[ib])
                    w = float(F.size_mult(nf))
                    r0, x0, _ = F.outcome_d0(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle_d0)
                    # T240
                    xt240 = f + 240
                    if base + xt240 >= n_all:
                        r240, x240 = np.nan, xt240
                    else:
                        t_fill = bt + pd.Timedelta(minutes=int(f))
                        t_exit = bt + pd.Timedelta(minutes=int(xt240))
                        ns = count_settlements(t_fill, t_exit)
                        r240, x240, _ = F.outcome_fillrel(
                            Hf, Lf, Cf, Of, base, f, lv, sg, xt240, ns)
                    # T120
                    xt120 = 240 if f + 120 < 240 else f + 120
                    if base + xt120 >= n_all:
                        r120, x120 = np.nan, xt120
                    else:
                        t_fill = bt + pd.Timedelta(minutes=int(f))
                        t_exit = bt + pd.Timedelta(minutes=int(xt120))
                        ns = count_settlements(t_fill, t_exit)
                        r120, x120, _ = F.outcome_fillrel(
                            Hf, Lf, Cf, Of, base, f, lv, sg, xt120, ns)
                    if not (np.isfinite(r0) and np.isfinite(r240) and np.isfinite(r120)):
                        continue
                    n_fill += 1
                    xd0 = (bt + pd.Timedelta(minutes=int(x0))).date().isoformat() if int(x0) < 240 else \
                        (bt + pd.Timedelta(hours=4)).date().isoformat()
                    xd240 = (bt + pd.Timedelta(minutes=int(x240))).date().isoformat()
                    xd120 = (bt + pd.Timedelta(minutes=int(x120))).date().isoformat() if int(x120) < 240 else \
                        (bt + pd.Timedelta(hours=4)).date().isoformat()
                    rows.append(dict(phase=int(p), sym=sym, y=int(yi), k=float(k),
                                     f=int(f), n=int(nf), w=w, d0=float(r0), x0=int(x0),
                                     t240=float(r240), x240=int(x240),
                                     t120=float(r120), x120=int(x120),
                                     xd0=xd0, xd240=xd240, xd120=xd120, t_bar=bt))
            fills_pp[f"{sym}/p{p}"] = n_fill
            print(f"{sym} p{p}: fills={n_fill}", flush=True)
        del H, L, Hf, Lf, Of, Cf

    df = pd.DataFrame(rows)
    variants = {"D0": ("d0", "xd0", "x0"), "T240": ("t240", "xd240", "x240"),
                "T120": ("t120", "xd120", "x120")}
    per_phase = {}
    for p in PHASES:
        per_phase[str(p)] = {}
        for v, (col, xdc, xc) in variants.items():
            per_phase[str(p)][v] = []
            for yi in range(5):
                sub = df[(df["phase"] == p) & (df["y"] == yi)]
                n = len(sub)
                if n:
                    yv = sub[col].to_numpy(float)
                    wv = sub["w"].to_numpy(float)
                    wy = wv * yv
                    recs = list(zip(sub[xdc].tolist(), wy.tolist()))
                    S, Wd, DD, nd = daily_path(recs)
                    win = float((yv > 0).mean())
                    mean = float(yv.mean())
                else:
                    S, Wd, DD, nd, win, mean = 0.0, 0.0, 0.0, 0, 0.0, 0.0
                per_phase[str(p)][v].append({"year": ANCHORS[yi].date().isoformat(),
                                             "n": int(n), "mean": mean,
                                             "win_rate": win, "sum": S,
                                             "worst_day": Wd, "max_dd": DD,
                                             "ndays": nd})
    # 4-phase means + dispersion of yearly sums
    mean4, disp = {}, {}
    for v in variants:
        mean4[v], disp[v] = [], []
        for yi in range(5):
            ss = [per_phase[str(p)][v][yi]["sum"] for p in PHASES]
            mean4[v].append({"year": ANCHORS[yi].date().isoformat(),
                             "sum_mean4": float(np.mean(ss)),
                             "trades_mean4": float(np.mean([per_phase[str(p)][v][yi]["n"] for p in PHASES])),
                             "win_mean4": float(np.mean([per_phase[str(p)][v][yi]["win_rate"] for p in PHASES])),
                             "worst_mean4": float(np.mean([per_phase[str(p)][v][yi]["worst_day"] for p in PHASES])),
                             "maxdd_mean4": float(np.mean([per_phase[str(p)][v][yi]["max_dd"] for p in PHASES])),
                             "dispersion": float(max(ss) - min(ss)),
                             "per_phase_sums": [float(s) for s in ss]})
    # overlap shares pooled over phases per (year, variant)
    overlap = {}
    for v, (col, xdc, xc) in variants.items():
        overlap[v] = []
        for yi in range(5):
            sub = df[df["y"] == yi]
            if len(sub):
                held = (sub[xc].to_numpy(int) - sub["f"].to_numpy(int)).astype(float)
                ov = np.array([F.overlap_minutes(f, x) for f, x in
                               zip(sub["f"].tolist(), sub[xc].tolist())], dtype=float)
                share = float(ov.sum() / held.sum()) if held.sum() > 0 else 0.0
                any_share = float((ov > 0).mean())
            else:
                share, any_share = 0.0, 0.0
            overlap[v].append({"year": ANCHORS[yi].date().isoformat(),
                               "rung_minutes_overlap_share": share,
                               "fills_with_any_overlap": any_share})

    decision = {}
    for v in ("T240", "T120"):
        ps = sum(1 for yi in range(5)
                 if mean4[v][yi]["sum_mean4"] >= mean4["D0"][yi]["sum_mean4"])
        pd_ = sum(1 for yi in range(5)
                  if mean4[v][yi]["maxdd_mean4"] <= mean4["D0"][yi]["maxdd_mean4"] + 0.01)
        pc = sum(1 for yi in range(5)
                 if mean4[v][yi]["dispersion"] < mean4["D0"][yi]["dispersion"])
        decision[v] = {"years_sum_ge_D0": int(ps),
                       "years_dd_not_worse_1pp": int(pd_),
                       "years_disp_lower": int(pc),
                       "promising": bool(ps >= 4 and pd_ >= 4 and pc >= 3)}
    chk = hashlib.sha256(
        np.round(df[["d0", "t240", "t120", "w"]].to_numpy(), 9).tobytes()).hexdigest()[:16] if len(df) else "empty"
    out = {"config": {"coins": list(MAJORS), "rungs": list(F.RUNGS),
                       "bars": "open in [2021-09-24, 2026-09-24) per phase",
                       "grids": "4h from 2020-08-01 00:00 UTC + 0/1/2/3h",
                       "live": [F.LIVE_A, F.LIVE_B], "maker": F.MAKER,
                       "taker": F.TAKER, "fund_long": 0.0001,
                       "settle_hours": list(SETTLE_HOURS),
                       "size": "B1 1/(1+n_fill), raw w*y sums, no renormalisation",
                       "D0": "oc_dipexit replica (TP1sg, sl4sg, bl8sg, timeout next open)",
                       "T240": "time exit at open(f+240), taker, funding per settlement in (fill,exit] on time exits",
                       "T120": "time exit at max(240, f+120), taker, same funding",
                       "daily": "exit-date UTC sums of w*y; maxDD of cumulative daily-sum path from 0 (>=0)",
                       "mean4": "mean across 4 phases; dispersion = max-min of yearly sums",
                       "overlap": "held=[f+1,x), next-bar live=[256,479); share=sum(overlap)/sum(held) pooled over phases",
                       "note": "paired rungs kept only if D0,T240,T120 all finite"},
           "fills_per_coin_phase": fills_pp, "n_rungs": int(len(df)),
           "ledger_checksum": chk, "per_phase": per_phase,
           "mean4": mean4, "overlap": overlap, "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_rungs", len(df), "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
