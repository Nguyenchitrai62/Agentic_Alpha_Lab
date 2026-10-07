"""oc_spreadcost run: quoted-spread measurement + half-spread taker-cost overlay.

(1) SPREAD: per coin x venue quoted-spread stats (median/p90/p99 bps) from the
    read-only top-of-book store `data/raw/topbook_live/` (sampled ~1/s since
    2026-10-04; whatever day files are on disk at run time, one file at a
    time, peak RAM < 100 MB), plus spread stats inside each coin's 20 most
    volatile minutes (ranked by 1m mid-price range, self-contained: no 1m
    kline data exists for the October sample window).
(2) REPLICA: B1 dip-ladder replica (R2 depths, 4 phase-shifted 4h grids
    0..3h, 5 anchor years, Binance 1m, no row >= 2026-09-24 00:00 UTC loaded
    into any comparison) with half the Bybit spread as extra cost on every
    taker exit (stops/backstops: 0.5 * p90; timeouts: 0.5 * median; TP maker
    legs unchanged). Reports 5y sums + DD change per coin and total.

Writes ONLY research/tournament/oc_spreadcost/results.json. HEAVY step
(replica, > 0.4 GB 1m arrays) must run through the shared semaphore, e.g.:
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_spreadcost \\
    --min-free-gb 2.0 -- .venv/Scripts/python.exe research/tournament/oc_spreadcost/run.py --step replica
The spread step is LIGHT and runs directly:
  .venv/Scripts/python.exe research/tournament/oc_spreadcost/run.py --step spread

Usage: .venv/Scripts/python.exe research/tournament/oc_spreadcost/run.py --step [spread|replica|all]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd

import spreadcost as S

BOOK_ROOT = Path("data/raw/topbook_live")
BIN_BTC = Path("data/raw/btc_intraday_20260924")
BIN_MAJ = Path("data/raw/majors_intraday_20260924")
VENUES = ("binance", "bybit")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
SETTLE_HOURS = (0, 8, 16)


# ------------------------------------------------------------------ step 1: spreads
def measure_spreads() -> dict:
    per_combo = {}
    for venue in VENUES:
        for sym in MAJORS:
            files = sorted((BOOK_ROOT / venue / sym).glob("*.parquet"))
            ts_all, sp_all, mid_all = [], [], []
            n_rows = n_invalid = 0
            span = [None, None]
            for f in files:
                df = pd.read_parquet(f, columns=["sample_time", "bid", "ask"])
                n_rows += len(df)
                st = df["sample_time"].to_numpy(dtype=np.int64)
                if span[0] is None:
                    span = [int(st.min()), int(st.max())]
                else:
                    span = [min(span[0], int(st.min())), max(span[1], int(st.max()))]
                bid = df["bid"].to_numpy(dtype=float)
                ask = df["ask"].to_numpy(dtype=float)
                del df
                sp = S.spread_bps(bid, ask)
                ok = np.isfinite(sp)
                n_invalid += int((~ok).sum())
                mid = (bid[ok] + ask[ok]) / 2.0
                ts_all.append(st[ok])
                sp_all.append(sp[ok])
                mid_all.append(mid)
            if ts_all:
                ts = np.concatenate(ts_all)
                sp = np.concatenate(sp_all)
                mid = np.concatenate(mid_all)
            else:
                ts = np.zeros(0, dtype=np.int64)
                sp = np.zeros(0)
                mid = np.zeros(0)
            del ts_all, sp_all, mid_all
            minute_ms = (ts // 60_000) * 60_000
            vol = S.top_volatile_minutes(minute_ms, mid, sp, top_n=20, min_n=20)
            per_combo[f"{venue}:{sym}"] = {
                "venue": venue, "symbol": sym, "n_files": len(files),
                "n_rows": int(n_rows), "n_invalid": int(n_invalid),
                "span_utc": [pd.to_datetime(span[0], unit="ms", utc=True).isoformat(),
                             pd.to_datetime(span[1], unit="ms", utc=True).isoformat()]
                if span[0] is not None else [None, None],
                "spread_bps": S.summarize(sp),
                "volatile_top20": vol,
            }
            print(f"{venue}:{sym} n={len(sp)} med={per_combo[f'{venue}:{sym}']['spread_bps']['median']:.4f} "
                  f"p90={per_combo[f'{venue}:{sym}']['spread_bps']['p90']:.4f} "
                  f"p99={per_combo[f'{venue}:{sym}']['spread_bps']['p99']:.4f} "
                  f"vol20_med={vol['spread']['median']:.4f}", flush=True)
    return per_combo


# ------------------------------------------------------------------ step 2: replica
def load_binance_oc(sym: str, idx):
    if sym == "BTCUSDT":
        files = sorted(BIN_BTC.glob("klines_1m_20*.parquet"))
    else:
        files = sorted(BIN_MAJ.glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "close"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    m = m.set_index("open_time").reindex(idx)
    O = m["open"].to_numpy(dtype=np.float32)
    C = m["close"].to_numpy(dtype=np.float32)
    del m, parts
    return O, C


def load_binance_hl(sym: str, idx):
    if sym == "BTCUSDT":
        files = sorted(BIN_BTC.glob("klines_1m_20*.parquet"))
    else:
        files = sorted(BIN_MAJ.glob(f"{sym}_1m_20*.parquet"))
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


def bar_sigmas(o_bar: np.ndarray):
    return (pd.Series(o_bar.astype(float)).pct_change()
            .rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy())


def run_replica(extra_med: dict, extra_p90: dict) -> dict:
    idx = pd.date_range(START, END, freq="1min")
    n_all = len(idx)
    O, C = {}, {}
    for sym in MAJORS:
        o, c = load_binance_oc(sym, idx)
        O[sym], C[sym] = o, c
        assert len(o) == n_all
        print(f"loaded OC {sym}", flush=True)

    rows = []
    n_drop = 0
    n_bar = 0
    W = S.LIVE_B - S.LIVE_A + 1
    for s in S.PHASES:
        starts = S.phase_bar_starts(n_all, s)
        t0 = idx[starts]
        keep = (t0 >= TRADE_START) & (t0 < YEAR_END)
        starts, t0 = starts[keep], t0[keep]
        opens, sigs = {}, {}
        for sym in MAJORS:
            ob = O[sym][starts].astype(float)
            opens[sym] = ob
            sigs[sym] = bar_sigmas(ob)
        print(f"phase {s}: bars={len(starts)}", flush=True)
        for sym in MAJORS:
            H, L = load_binance_hl(sym, idx)
            others = [b for b in MAJORS if b != sym]
            for j in range(len(starts)):
                bt = t0[j]
                base = int(starts[j])
                if base + 240 >= n_all:
                    continue
                o1, sg = float(opens[sym][j]), float(sigs[sym][j])
                if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                    continue
                o2m = O[sym][base + 240]
                o2 = float(o2m) if np.isfinite(o2m) else np.nan
                settle = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
                yi = S.year_of(bt, ANCHORS, YEAR_END)
                low_win = L[base + S.LIVE_A:base + S.LIVE_B + 1].astype(float)
                cmat = np.stack([C[b][base + S.LIVE_A - 1:base + S.LIVE_B].astype(float)
                                 for b in others])
                oo = np.array([opens[b][j] for b in others], dtype=float)
                ss = np.array([sigs[b][j] for b in others], dtype=float)
                nvec = S.n_vector(cmat, oo, ss)
                Ha = H[base:base + 240].astype(float)
                La = L[base:base + 240].astype(float)
                Ca = C[sym][base:base + 240].astype(float)
                Oa = O[sym][base:base + 240].astype(float)
                n_bar += 1
                for k in S.RUNGS:
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = S.find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = S.LIVE_A + ib
                    nf = int(nvec[ib])
                    w = S.size_mult(nf)
                    ret, x, how = S.outcome_from_fill(Ha, La, Ca, Oa, f, lv, sg, o2, settle)
                    if not np.isfinite(ret):
                        n_drop += 1
                        continue
                    adj = S.apply_extra_cost(ret, how, extra_med[sym], extra_p90[sym])
                    if int(x) < 240:
                        xd = (bt + pd.Timedelta(minutes=int(x))).date().isoformat()
                    else:
                        xd = (bt + pd.Timedelta(hours=4)).date().isoformat()
                    rows.append((sym, s, yi, float(k), int(f), nf, w,
                                       float(ret), float(adj), int(x), how, xd))
            del H, L
    df = pd.DataFrame(rows, columns=["sym", "phase", "y", "k", "f", "n", "w",
                                     "ret", "adj", "x", "how", "xd"])
    df.to_parquet(HERE / "fills.parquet", index=False)
    return {"df": df, "n_bar": int(n_bar), "n_drop": int(n_drop)}


def phase_sums(df: pd.DataFrame) -> list:
    """Per-phase yearly + total equal-weight sums (replica fidelity view)."""
    out = []
    for s in S.PHASES:
        sub = df[df["phase"] == s]
        per_year = []
        for yi in range(5):
            s2 = sub[sub["y"] == yi]
            per_year.append({"year": ANCHORS[yi].date().isoformat(), "n": int(len(s2)),
                             "sum_eq": float(s2["ret"].sum()) if len(s2) else 0.0,
                             "sum_w": float((s2["w"] * s2["ret"]).sum()) if len(s2) else 0.0})
        out.append({"phase": int(s), "n": int(len(sub)),
                    "sum_eq": float(sub["ret"].sum()) if len(sub) else 0.0,
                    "sum_w": float((sub["w"] * sub["ret"]).sum()) if len(sub) else 0.0,
                    "per_year": per_year})
    return out


def summarize_replica(df: pd.DataFrame, extra_med: dict, extra_p90: dict) -> dict:
    per_coin, per_coin_year = [], []
    for sym in MAJORS:
        sub = df[df["sym"] == sym]
        r = sub["ret"].to_numpy(float) if len(sub) else np.zeros(0)
        a = sub["adj"].to_numpy(float) if len(sub) else np.zeros(0)
        w = sub["w"].to_numpy(float) if len(sub) else np.zeros(0)
        recs = list(zip(sub["xd"].tolist(), r.tolist()))
        recs_a = list(zip(sub["xd"].tolist(), a.tolist()))
        recs_w = list(zip(sub["xd"].tolist(), (w * r).tolist())) if len(sub) else []
        recs_wa = list(zip(sub["xd"].tolist(), (w * a).tolist())) if len(sub) else []
        S_eq, _, DD_eq, _ = S.daily_path(recs)
        S_eqa, _, DD_eqa, _ = S.daily_path(recs_a)
        S_w, _, DD_w, _ = S.daily_path(recs_w)
        S_wa, _, DD_wa, _ = S.daily_path(recs_wa)
        per_coin.append({
            "sym": sym, "n": int(len(sub)),
            "n_tp": int((sub["how"] == "tp").sum()) if len(sub) else 0,
            "n_stop": int(sub["how"].isin(list(S.STOP_HOWS)).sum()) if len(sub) else 0,
            "n_time": int((sub["how"] == "time").sum()) if len(sub) else 0,
            "extra_med": float(extra_med[sym]), "extra_p90": float(extra_p90[sym]),
            "sum_eq": float(S_eq), "sum_eq_adj": float(S_eqa),
            "delta_eq": float(S_eqa - S_eq),
            "dd_eq": float(DD_eq), "dd_eq_adj": float(DD_eqa),
            "dd_eq_change": float(DD_eqa - DD_eq),
            "sum_w": float(S_w), "sum_w_adj": float(S_wa),
            "delta_w": float(S_wa - S_w),
            "dd_w": float(DD_w), "dd_w_adj": float(DD_wa),
            "dd_w_change": float(DD_wa - DD_w),
        })
        for yi in range(5):
            s2 = sub[sub["y"] == yi]
            per_coin_year.append({
                "sym": sym, "year": ANCHORS[yi].date().isoformat(), "n": int(len(s2)),
                "sum_eq": float(s2["ret"].sum()) if len(s2) else 0.0,
                "sum_eq_adj": float(s2["adj"].sum()) if len(s2) else 0.0,
                "sum_w": float((s2["w"] * s2["ret"]).sum()) if len(s2) else 0.0,
                "sum_w_adj": float((s2["w"] * s2["adj"]).sum()) if len(s2) else 0.0,
            })
    tot = {}
    for tag, col, wtd in (("eq", "ret", False), ("eq_adj", "adj", False),
                          ("w", "ret", True), ("w_adj", "adj", True)):
        vals = df[col].to_numpy(float) if len(df) else np.zeros(0)
        w = df["w"].to_numpy(float) if len(df) else np.zeros(0)
        v = w * vals if wtd else vals
        recs = list(zip(df["xd"].tolist(), v.tolist())) if len(df) else []
        Sm, _, DD, _ = S.daily_path(recs)
        tot[tag] = {"sum": float(Sm), "dd": float(DD)}
    tot["delta_eq"] = tot["eq_adj"]["sum"] - tot["eq"]["sum"]
    tot["delta_w"] = tot["w_adj"]["sum"] - tot["w"]["sum"]
    tot["dd_eq_change"] = tot["eq_adj"]["dd"] - tot["eq"]["dd"]
    tot["dd_w_change"] = tot["w_adj"]["dd"] - tot["w"]["dd"]
    tot["n"] = int(len(df))
    return {"per_coin": per_coin, "per_coin_year": per_coin_year, "total": tot,
            "how_counts": {h: int((df["how"] == h).sum()) for h in ("tp", "stop", "backstop", "time")}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=("spread", "replica", "all"), default="all")
    step = ap.parse_args().step
    out_path = HERE / "results.json"
    if step in ("spread", "all"):
        spreads = measure_spreads()
        extra_med = {s: 0.5 * spreads[f"bybit:{s}"]["spread_bps"]["median"] / 1e4 for s in MAJORS}
        extra_p90 = {s: 0.5 * spreads[f"bybit:{s}"]["spread_bps"]["p90"] / 1e4 for s in MAJORS}
        out = {"spreads": spreads, "extra_cost": {
            s: {"extra_med_frac": extra_med[s], "extra_p90_frac": extra_p90[s],
                "bybit_median_bps": spreads[f"bybit:{s}"]["spread_bps"]["median"],
                "bybit_p90_bps": spreads[f"bybit:{s}"]["spread_bps"]["p90"],
                "bybit_p99_bps": spreads[f"bybit:{s}"]["spread_bps"]["p99"]} for s in MAJORS}}
        if step == "spread":
            out["replica"] = None
            out_path.write_text(json.dumps(out, indent=1))
            print("wrote spreads only", flush=True)
            return
    else:
        prev = json.loads(out_path.read_text()) if out_path.exists() else {}
        spreads = prev.get("spreads")
        if not spreads:
            raise SystemExit("run --step spread first (results.json has no spreads)")
        extra_med = {s: 0.5 * spreads[f"bybit:{s}"]["spread_bps"]["median"] / 1e4 for s in MAJORS}
        extra_p90 = {s: 0.5 * spreads[f"bybit:{s}"]["spread_bps"]["p90"] / 1e4 for s in MAJORS}
        out = prev
    rep = run_replica(extra_med, extra_p90)
    df = rep["df"]
    summ = summarize_replica(df, extra_med, extra_p90)
    out["config"] = {
        "coins": list(MAJORS), "rungs": list(S.RUNGS), "phases": list(S.PHASES),
        "bars": "open in [2021-09-24, 2026-09-24) on each 0..3h-shifted 4h grid from 2020-08-01",
        "live": [S.LIVE_A, S.LIVE_B], "maker": S.MAKER, "taker": S.TAKER,
        "fund_long": S.FUND, "settle_hours": list(SETTLE_HOURS),
        "fill": "B1 static resting bid at lv, STRICT low<lv, size 1/(1+n) (oc_b1deeper-exact)",
        "exits": "D0 from actual fill px (TP=px*(1+sg), sl 4sg, bl 8sg, timeout next open), stop-first",
        "overlay": "taker exits only: stop/backstop -= 0.5*bybit_p90/1e4, timeout -= 0.5*bybit_median/1e4, TP unchanged",
        "pooling": "fills pooled over 4 phases (rung-y attribution units, not portfolio %/month)",
        "binance_store": "data/raw/btc_intraday_20260924 + data/raw/majors_intraday_20260924",
        "topbook_store": "data/raw/topbook_live (read-only)",
        "cap": "no 1m row with open_time >= 2026-09-24 00:00 UTC loaded into the replica",
        "note": "all five years are research data; overlay is a realism adjustment, not a rule",
    }
    out["replica"] = {"n_fills": int(len(df)), "n_bars": rep["n_bar"],
                      "n_dropped_nan_exit": rep["n_drop"],
                      "per_phase": phase_sums(df), **summ}
    out_path.write_text(json.dumps(out, indent=1, default=str))
    print("n_fills", len(df), "bars", rep["n_bar"], "dropped", rep["n_drop"], flush=True)
    print(json.dumps(summ["total"], indent=1), flush=True)


if __name__ == "__main__":
    main()
