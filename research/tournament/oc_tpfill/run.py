"""oc_tpfill run: BASE (next-minute TP) vs FIX (same-minute close>=TP hook).

Majors x R2 depths x 5 anchor years x 4 clock phases, B1 sizes, paired rungs.
See PLAN.md for frozen definitions. One process; majors 1m O/C held as
float32, one coin H/L at a time.
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

import tpfill as T

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
PHASES = (0, 1, 2, 3)
SETTLE_HOURS = (0, 8, 16)


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
    idx0, O, C = {}, {}, {}
    for sym in MAJORS:
        ii, o, c = load_oc(sym)
        idx0[sym], O[sym], C[sym] = ii, o, c
        print(f"loaded OC {sym}", flush=True)
    base_idx = idx0[MAJORS[0]]
    n_all = len(base_idx)

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
    n_deep_same = 0
    for sym in MAJORS:
        H, L = load_hl(sym, base_idx)
        Hf = H.astype(float)
        Lf = L.astype(float)
        del H, L
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
                settle = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
                yi = year_of(bt)
                if yi is None:
                    continue
                low_win = Lf[base + T.LIVE_A:base + T.LIVE_B + 1]
                cmat = np.stack([C[b][base + T.LIVE_A - 1:base + T.LIVE_B].astype(float)
                                 for b in others])
                oo = np.array([opens_bar[(p, b)][j] for b in others], dtype=float)
                ss = np.array([sig_bar[(p, b)][j] for b in others], dtype=float)
                nvec = T.n_vector(cmat, oo, ss)
                Ha_b = Hf[base:base + 240]
                La_b = Lf[base:base + 240]
                Ca_b = Cf[base:base + 240]
                Oa_b = Of[base:base + 240]
                for k in T.RUNGS:
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = T.find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = T.LIVE_A + ib
                    nf = int(nvec[ib])
                    w = float(T.size_mult(nf))
                    rb, xb, hb = T.outcome_base(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle)
                    rf, xf, hf = T.outcome_fix(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle)
                    if not (np.isfinite(rb) and np.isfinite(rf)):
                        continue
                    if hf == "tp_same":
                        bl = lv * (1 - T.BACKSTOP * sg)
                        if float(La_b[f]) <= bl:
                            n_deep_same += 1
                    n_fill += 1
                    rows.append(dict(phase=int(p), sym=sym, y=int(yi), k=float(k),
                                     f=int(f), n=int(nf), w=w,
                                     base=float(rb), xb=int(xb), hbase=hb,
                                     fix=float(rf), xf=int(xf), hfix=hf,
                                     xd_base=exit_date(bt, int(xb)),
                                     xd_fix=exit_date(bt, int(xf)), t_bar=bt))
            fills_pp[f"{sym}/p{p}"] = n_fill
            print(f"{sym} p{p}: paired fills={n_fill}", flush=True)
        del Hf, Lf, Of, Cf

    df = pd.DataFrame(rows)
    if len(df) == 0:
        raise SystemExit("no paired fills")
    variants = {"BASE": ("base", "xd_base", "hbase"),
                "FIX": ("fix", "xd_fix", "hfix")}

    def cell_stats(sub, col, xdc, hc):
        n = len(sub)
        if n == 0:
            return {"n": 0, "mean": 0.0, "win_rate": 0.0, "sum": 0.0,
                    "worst_day": 0.0, "max_dd": 0.0, "ndays": 0,
                    "n_tp": 0, "n_tp_same": 0, "n_stop": 0,
                    "n_backstop": 0, "n_time": 0}
        yv = sub[col].to_numpy(float)
        wv = sub["w"].to_numpy(float)
        recs = list(zip(sub[xdc].tolist(), (wv * yv).tolist()))
        S, Wd, DD, nd = daily_path(recs)
        h = sub[hc].tolist()
        return {"n": int(n), "mean": float(yv.mean()),
                "win_rate": float((yv > 0).mean()), "sum": S,
                "worst_day": Wd, "max_dd": DD, "ndays": int(nd),
                "n_tp": int(sum(1 for v in h if v in ("tp", "tp_same"))),
                "n_tp_same": int(sum(1 for v in h if v == "tp_same")),
                "n_stop": int(sum(1 for v in h if v == "stop")),
                "n_backstop": int(sum(1 for v in h if v == "backstop")),
                "n_time": int(sum(1 for v in h if v == "time"))}

    per_phase = {}
    for p in PHASES:
        per_phase[str(p)] = {}
        for v, (col, xdc, hc) in variants.items():
            per_phase[str(p)][v] = []
            for yi in range(5):
                sub = df[(df["phase"] == p) & (df["y"] == yi)]
                per_phase[str(p)][v].append(
                    {"year": ANCHORS[yi].date().isoformat(),
                     **cell_stats(sub, col, xdc, hc)})

    mean4 = {}
    for v in variants:
        mean4[v] = []
        for yi in range(5):
            ss = [per_phase[str(p)][v][yi]["sum"] for p in PHASES]
            dd = [per_phase[str(p)][v][yi]["max_dd"] for p in PHASES]
            ww = [per_phase[str(p)][v][yi]["worst_day"] for p in PHASES]
            ts = [per_phase[str(p)][v][yi]["n_tp_same"] for p in PHASES]
            mean4[v].append({"year": ANCHORS[yi].date().isoformat(),
                             "sum_mean4": float(np.mean(ss)),
                             "trades_mean4": float(np.mean([per_phase[str(p)][v][yi]["n"] for p in PHASES])),
                             "win_mean4": float(np.mean([per_phase[str(p)][v][yi]["win_rate"] for p in PHASES])),
                             "worst_mean4": float(np.mean(ww)),
                             "maxdd_mean4": float(np.mean(dd)),
                             "tp_same_mean4": float(np.mean(ts)),
                             "tp_same_total": int(sum(ts)),
                             "per_phase_sums": [float(s) for s in ss],
                             "per_phase_tp_same": [int(t) for t in ts]})
    deltas = [mean4["FIX"][yi]["sum_mean4"] - mean4["BASE"][yi]["sum_mean4"] for yi in range(5)]
    years_ge = int(sum(1 for d in deltas if d >= 0))
    loo = []
    for h in range(5):
        s = float(sum(d for i, d in enumerate(deltas) if i != h))
        loo.append(s)
    loo_holds = int(sum(1 for s in loo if s >= 0))
    # strict-positive context (diagnostic aid)
    years_gt = int(sum(1 for d in deltas if d > 0))
    loo_holds_gt = int(sum(1 for s in loo if s > 0))
    decision = {"delta_mean4": [float(d) for d in deltas],
                "years_ge_base": years_ge, "years_gt_base": years_gt,
                "loo_sums": [float(s) for s in loo],
                "loo_holds_ge": loo_holds, "loo_holds_gt": loo_holds_gt,
                "default_rule_ge": bool(years_ge >= 4 and loo_holds >= 4),
                "diagnostic": True,
                "note": "NOT a selection; conservatism read from FIX>=BASE deltas"}
    chk = hashlib.sha256(
        np.round(df[["base", "fix", "w"]].to_numpy(), 9).tobytes()).hexdigest()[:16] if len(df) else "empty"
    out = {"config": {"coins": list(MAJORS), "rungs": list(T.RUNGS),
                       "bars": "open in [2021-09-24, 2026-09-24) per phase",
                       "grids": "4h from 2020-08-01 00:00 UTC + 0/1/2/3h",
                       "live": [T.LIVE_A, T.LIVE_B], "maker": T.MAKER,
                       "taker": T.TAKER, "fund_long": 0.0001,
                       "settle_hours": list(SETTLE_HOURS),
                       "size": "B1 1/(1+n_fill), raw w*y sums, no renormalisation; fills identical across arms",
                       "BASE": "oc_dipexit D0 replica (TP1sg limit from f+1 STRICT high>tp; close5 on last close; backstop on last low at min(bl,open); timeout next open)",
                       "FIX": "same as BASE except TP may also fill in fill minute f iff close(f) >= tp (non-strict), exit at tp 2*maker x=f how=tp_same; else BASE race; stops start f+1",
                       "daily": "exit-date UTC sums of w*y per arm's own exit date; maxDD of cumulative daily-sum path from 0 (>=0)",
                       "mean4": "mean across 4 phases",
                       "note": "paired rungs kept only if BASE and FIX nets both finite"},
           "fills_per_coin_phase": fills_pp, "n_rungs": int(len(df)),
           "n_same_minute_tp": int((df["hfix"] == "tp_same").sum()),
           "n_same_with_deep_low": int(n_deep_same),
           "ledger_checksum": chk, "per_phase": per_phase,
           "mean4": mean4, "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_rungs", len(df), "n_same", int((df["hfix"] == "tp_same").sum()), "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
