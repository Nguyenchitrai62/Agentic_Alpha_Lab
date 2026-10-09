"""oc_ivterm: option-implied TERM STRUCTURE TS = 7d ATM IV / DVOL.

Descriptive (dev years only) + conditional ONE tilt. See PLAN.md (frozen).
Light job: strike aggregates + DVOL hourly; dip ledger is read-only
research/tournament/oc_depthtilt/fills.parquet (identical D0+B1 replica);
BOOK bars from research/tournament/ext/hourly_ext.parquet. No 1m reads.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
DEV_YEARS = (0, 1, 2, 3)
FID_REF = [0.9113, 0.8326, 2.0998, 3.1974, 0.6772]  # uncapped S_bar base
DD_TOL = 0.01
GATE_DSUM = 0.273


def year_of(t) -> int | None:
    for i in range(5):
        lo = ANCHORS[i]
        hi = ANCHORS[i + 1] if i < 4 else YEAR_END
        if lo <= t < hi:
            return i
    return None


# ---------------------------------------------------------------- DVOL
def load_dvol_hourly(coin: str) -> pd.Series:
    """Hourly DVOL close indexed by hour START (UTC). Candle [t,t+1h) -> idx t."""
    d = Path("data/raw/deribit_dvol_20261005")
    recs = []
    for f in sorted(d.glob(f"{coin}_*.json")):
        j = json.loads(Path(f).read_text())
        for c in j["candles"]:
            ts_ms, _o, _h, _l, cl = c
            t = pd.Timestamp(int(ts_ms), unit="ms", tz="UTC")
            recs.append((t, float(cl)))
    s = pd.Series({t: v for t, v in recs})
    s = s[~s.index.duplicated(keep="last")].sort_index()
    # reindex to full hourly grid, ffill (latest known candle)
    full = pd.date_range(s.index.min().floor("h"), s.index.max().ceil("h"),
                         freq="h", tz="UTC")
    s = s.reindex(full).ffill()
    s.index.name = "hour"
    return s


# ---------------------------------------------------------------- strike -> TS
def load_strike_agg(coin_sym: str) -> pd.DataFrame:
    """Per-hour candidate aggregates: S1=sum(iv*amt), S0=sum(amt) for 3..10d, |m|<=2%."""
    short = coin_sym.replace("USDT", "")
    cols = ["hour", "expiry", "strike", "vwap_iv", "vwap_index", "sum_amount"]
    parts = []
    for folder in (f"data/raw/deribit_strike_20261007/{short}",
                   f"data/raw/deribit_strike_20261007_b/{short}"):
        d = Path(folder)
        if not d.exists():
            continue
        for f in sorted(d.glob(f"{short}_*.parquet")):
            if f.name == "manifest.json":
                continue
            try:
                df = pd.read_parquet(f, columns=cols)
            except Exception as e:
                print(f"skip {f}: {e}", flush=True)
                continue
            parts.append(df)
    m = pd.concat(parts, ignore_index=True)
    m["hour"] = pd.to_datetime(m["hour"], utc=True)
    m["expiry"] = pd.to_datetime(m["expiry"], utc=True)
    # dedupe overlapping months (identical) on (hour, instrument)? instrument col
    # not loaded; dedupe exact duplicates instead
    m = m.drop_duplicates()
    m = m[(m["sum_amount"] > 0) & np.isfinite(m["vwap_iv"].to_numpy())
          & np.isfinite(m["vwap_index"].to_numpy()) & (m["vwap_index"] > 0)]
    hour_end = m["hour"] + pd.Timedelta(hours=1)
    dte = (m["expiry"] - hour_end).dt.total_seconds() / 86400.0
    money = (m["strike"] / m["vwap_index"] - 1).abs()
    m = m[(dte >= 3.0) & (dte <= 10.0) & (money <= 0.02)]
    m["w"] = m["vwap_iv"] * m["sum_amount"]
    g = m.groupby("hour").agg(S1=("w", "sum"), S0=("sum_amount", "sum"))
    g = g.sort_index()
    return g


def build_ts(coin_sym: str, dvol: pd.Series, agg: pd.DataFrame) -> pd.Series:
    """Hourly TS(h) indexed by hour START; 6h window; <0.5 coin -> NaN; carry 24h."""
    if len(agg) == 0:
        raise SystemExit(f"empty strike agg {coin_sym}")
    h0 = min(agg.index.min().floor("h"), dvol.index.min())
    h1 = max(agg.index.max().ceil("h"), dvol.index.max())
    full = pd.date_range(h0, h1, freq="h", tz="UTC")
    s1 = agg["S1"].reindex(full, fill_value=0.0)
    s0 = agg["S0"].reindex(full, fill_value=0.0)
    w1 = s1.rolling(6, min_periods=6).sum()
    w0 = s0.rolling(6, min_periods=6).sum()
    iv = w1 / w0
    iv[w0 < 0.5] = np.nan
    dv = dvol.reindex(full).ffill()
    # DVOL causal: candle starting at h known at h+1h = hour_end; for signal at
    # hour h we need latest candle_end <= hour_end, i.e. candle starting at h.
    # reindex above gives exactly that; first hours without DVOL stay NaN.
    ts = iv / dv
    ts[~(np.isfinite(iv.to_numpy()) & np.isfinite(dv.to_numpy()) & (dv.to_numpy() > 0))] = np.nan
    # carry last value up to 24h
    ts = ts.ffill(limit=24)
    ts.index.name = "hour"
    return ts


# ---------------------------------------------------------------- scoring helpers (placebo-exact)
def cell_stats(dates: np.ndarray, wy: np.ndarray):
    if wy.size == 0:
        return 0.0, 0.0, 0.0
    order = np.argsort(dates, kind="stable")
    d = np.asarray(dates)[order]
    v = np.asarray(wy, dtype=float)[order]
    uniq, idx = np.unique(d, return_index=True)
    bounds = np.append(idx[1:], v.size)
    daily = np.array([v[s:e].sum() for s, e in zip(idx, bounds)])
    cum = np.cumsum(daily)
    peak = np.maximum.accumulate(cum)
    dd = float(np.min(cum - peak))
    return float(daily.sum()), float(daily.min()), float(-dd)


def main() -> None:
    print("loading DVOL...", flush=True)
    dvol = {c: load_dvol_hourly(c.replace("USDT", "")) for c in ("BTCUSDT", "ETHUSDT")}
    print({k: (str(v.index.min()), str(v.index.max()), len(v)) for k, v in dvol.items()}, flush=True)

    print("loading strike aggs...", flush=True)
    ts = {}
    for sym in ("BTCUSDT", "ETHUSDT"):
        agg = load_strike_agg(sym)
        print(sym, "agg hours:", len(agg), flush=True)
        ts[sym] = build_ts(sym, dvol[sym], agg)
        print(sym, "TS finite share:", float(ts[sym].notna().mean()),
              "range:", str(ts[sym].dropna().index.min()), str(ts[sym].dropna().index.max()), flush=True)
    ts_btc, ts_eth = ts["BTCUSDT"], ts["ETHUSDT"]
    ts_btc.to_frame("ts").to_parquet(HERE / "tmp" / "ts_btc.parquet")
    ts_eth.to_frame("ts").to_parquet(HERE / "tmp" / "ts_eth.parquet")

    # ---- fidelity: base replica sums from read-only fills ----
    fills = pd.read_parquet("research/tournament/oc_depthtilt/fills.parquet")
    got = []
    for y in range(5):
        ss = []
        for p in (0, 1, 2, 3):
            m = (fills["phase"] == p) & (fills["year"] == y)
            ss.append(float((fills.loc[m, "w_base"] * fills.loc[m, "ret"]).sum()))
        got.append(float(np.mean(ss)))
    print("fidelity got:", [round(v, 4) for v in got], flush=True)
    print("fidelity ref:", FID_REF, flush=True)
    for g, r in zip(got, FID_REF):
        assert abs(g - r) < 1e-3, f"fidelity fail {got} vs {FID_REF}"
    base_sum5y = float(sum(got))
    print(f"base_sum5y={base_sum5y:.4f} (expect ~7.718)", flush=True)

    # ---- join TS_used to fills (last full hour before bar open) ----
    fills = fills.copy()
    fills["t_bar"] = pd.to_datetime(fills["t_bar"], utc=True)
    for col, series in (("ts_btc", ts_btc), ("ts_eth", ts_eth)):
        df = pd.DataFrame({"hour": series.index, "v": series.to_numpy()})
        df = df.sort_values("hour")
        fills["_key"] = fills["t_bar"] - pd.Timedelta(hours=1)
        fills = fills.sort_values("_key")
        fills[col] = pd.merge_asof(fills[["_key"]], df, left_on="_key",
                                   right_on="hour", direction="backward")["v"].to_numpy()
    fills["ts_used"] = np.where(fills["coin"] == 1, fills["ts_eth"], fills["ts_btc"])
    fills["is_stop"] = fills["how"].isin(["stop", "backstop"]).to_numpy()
    fills.to_parquet(HERE / "tmp" / "fills_ts.parquet", index=False)
    print("join NaN share:", float(np.isnan(fills["ts_used"].to_numpy()).mean()), flush=True)

    # ---- D1 distribution (hourly TS rows, dev years) ----
    d1 = {}
    for name, s in (("BTC", ts_btc), ("ETH", ts_eth)):
        per = {}
        for y in DEV_YEARS:
            lo, hi = ANCHORS[y], ANCHORS[y + 1]
            v = s[(s.index >= lo) & (s.index < hi)].dropna().to_numpy(dtype=float)
            per[ANCHORS[y].date().isoformat()] = {
                "n": int(v.size),
                "mean": round(float(np.mean(v)), 6) if v.size else None,
                "median": round(float(np.median(v)), 6) if v.size else None,
                "p10": round(float(np.quantile(v, 0.10)), 6) if v.size else None,
                "p90": round(float(np.quantile(v, 0.90)), 6) if v.size else None,
                "share_gt1": round(float((v > 1).mean()), 6) if v.size else None,
            }
        nn = int(s.notna().sum())
        d1[name] = {"per_year": per, "n_finite_total": nn,
                    "overall_median": round(float(s.dropna().median()), 6)}
    print("D1:", json.dumps(d1, indent=1), flush=True)

    # ---- D2 DIPS per dev year ----
    d2 = []
    signs = []
    spreads_bps = []
    for y in DEV_YEARS:
        sub = fills[(fills["year"] == y) & np.isfinite(fills["ts_used"].to_numpy())].copy()
        n_nan = int(((fills["year"] == y) & ~np.isfinite(fills["ts_used"].to_numpy())).sum())
        out = {"year": ANCHORS[y].date().isoformat(), "n_nan_ts": n_nan,
               "n": int(len(sub))}
        if len(sub) == 0:
            out["terciles"] = None
            d2.append(out)
            signs.append(0)
            spreads_bps.append(0.0)
            continue
        q1, q2 = float(sub["ts_used"].quantile(1 / 3)), float(sub["ts_used"].quantile(2 / 3))
        out["tercile_cuts_inyear"] = [round(q1, 6), round(q2, 6)]
        ter = []
        for i, (lo, hi) in enumerate([(-np.inf, q1), (q1, q2), (q2, np.inf)]):
            if i == 0:
                m = sub["ts_used"] <= q1
            elif i == 1:
                m = (sub["ts_used"] > q1) & (sub["ts_used"] <= q2)
            else:
                m = sub["ts_used"] > q2
            g = sub[m]
            wy = (g["w_base"] * g["ret"]).to_numpy(float)
            r = g["ret"].to_numpy(float)
            ter.append({
                "tercile": ["Lo", "Mid", "Hi"][i], "n": int(len(g)),
                "mean_wy": round(float(wy.mean()), 8) if len(g) else None,
                "mean_ret_bps": round(float(r.mean()) * 1e4, 4) if len(g) else None,
                "stop_rate": round(float(g["is_stop"].mean()), 6) if len(g) else None,
            })
        out["terciles"] = ter
        inv = {}
        for nm, m in (("gt1", sub["ts_used"] > 1), ("le1", sub["ts_used"] <= 1)):
            g = sub[m]
            wy = (g["w_base"] * g["ret"]).to_numpy(float)
            r = g["ret"].to_numpy(float)
            inv[nm] = {"n": int(len(g)),
                       "mean_wy": round(float(wy.mean()), 8) if len(g) else None,
                       "mean_ret_bps": round(float(r.mean()) * 1e4, 4) if len(g) else None,
                       "stop_rate": round(float(g["is_stop"].mean()), 6) if len(g) else None}
        out["inversion"] = inv
        sgn = int(np.sign(ter[2]["mean_wy"] - ter[0]["mean_wy"])) if (
            ter[2]["mean_wy"] is not None and ter[0]["mean_wy"] is not None) else 0
        spread = float((ter[2]["mean_ret_bps"] or 0.0) - (ter[0]["mean_ret_bps"] or 0.0))
        out["sign_hi_minus_lo"] = sgn
        out["spread_bps_per_rung"] = round(spread, 4)
        d2.append(out)
        signs.append(sgn)
        spreads_bps.append(spread)
    print("D2 signs:", signs, "spreads:", spreads_bps, flush=True)

    # ---- D3 BOOK IC ----
    print("loading hourly_ext for BOOK...", flush=True)
    hx = pd.read_parquet("research/tournament/ext/hourly_ext.parquet",
                         columns=["t", "open", "sym"])
    hx["t"] = pd.to_datetime(hx["t"], utc=True)
    book = {}
    for sym in MAJORS:
        h = hx[hx["sym"] == sym].sort_values("t")
        h = h[(h["t"] >= pd.Timestamp("2020-08-01", tz="UTC"))]
        grid = h[h["t"].dt.hour % 4 == 0].copy().reset_index(drop=True)
        grid["ret"] = grid["open"].pct_change()
        grid["sigma"] = grid["ret"].rolling(360, min_periods=120).std(ddof=1).shift(1)
        grid["fwd6"] = grid["open"].shift(-6) / grid["open"] - 1
        grid["label"] = grid["fwd6"] / grid["sigma"]
        grid["T"] = grid["t"]
        grid = grid[np.isfinite(grid["open"]) & np.isfinite(grid["sigma"])
                    & (grid["sigma"] > 0) & np.isfinite(grid["label"])]
        s_use = ts_eth if sym == "ETHUSDT" else ts_btc
        df = pd.DataFrame({"hour": s_use.index, "v": s_use.to_numpy()}).sort_values("hour")
        grid = grid.sort_values("T")
        grid["_key"] = grid["T"] - pd.Timedelta(hours=1)
        grid["ts_used"] = pd.merge_asof(grid[["_key"]], df, left_on="_key",
                                        right_on="hour", direction="backward")["v"].to_numpy()
        grid["year"] = grid["T"].apply(year_of)
        per = {}
        for y in DEV_YEARS:
            g = grid[(grid["year"] == y) & np.isfinite(grid["ts_used"].to_numpy())
                     & np.isfinite(grid["label"].to_numpy())]
            ic = float(g[["ts_used", "label"]].corr(method="spearman").iloc[0, 1]) if len(g) > 10 else None
            per[ANCHORS[y].date().isoformat()] = {"n": int(len(g)),
                                                 "ic": round(ic, 6) if ic is not None and np.isfinite(ic) else None}
        book[sym] = per
    # pooled IC per year
    print("BOOK per-coin done", flush=True)

    # ---- candidate decision ----
    same_sign = len(set(signs)) == 1 and signs[0] != 0
    n_big = sum(1 for s in spreads_bps if abs(s) > 5.0)
    fires = bool(same_sign and n_big >= 3)
    direction = ("damp-x0.6" if signs[0] < 0 else "boost-x1.3") if fires else None
    print(f"candidate: signs={signs} same={same_sign} |spread|>5bps in {n_big}/4 -> fires={fires} dir={direction}", flush=True)

    tilt = None
    if fires:
        # walk-forward p80 from hourly history per signal
        p80 = {}
        for name, s in (("BTC", ts_btc), ("ETH", ts_eth)):
            row = {}
            for k in range(5):
                cutoff = ANCHORS[k] - pd.Timedelta(days=7)
                v = s[s.index < cutoff].dropna().to_numpy(dtype=float)
                row[ANCHORS[k].date().isoformat()] = float(np.quantile(v, 0.80)) if v.size else None
            p80[name] = row
        print("p80:", json.dumps(p80, indent=1), flush=True)
        fr = fills.copy()
        fr["p80"] = np.where(fr["coin"] == 1,
                             fr["year"].map({k: p80["ETH"][ANCHORS[k].date().isoformat()] for k in range(5)}),
                             fr["year"].map({k: p80["BTC"][ANCHORS[k].date().isoformat()] for k in range(5)}))
        hi = np.isfinite(fr["ts_used"].to_numpy()) & np.isfinite(fr["p80"].to_numpy()) & (fr["ts_used"] > fr["p80"])
        mult = np.where(hi, (0.6 if direction.startswith("damp") else 1.3), 1.0)
        fr["w_rule_ts"] = fr["w_base"] * mult
        # score uncapped 4-phase means, all 5 years + dev4 context
        per_year, dsum5 = [], 0.0
        for y in range(5):
            Sb, Sr, Db, Dr, Wb, Wr = [], [], [], [], [], []
            for p in (0, 1, 2, 3):
                for wcol, Slist, Dlist, Wlist in (("w_base", Sb, Db, Wb), ("w_rule_ts", Sr, Dr, Wr)):
                    m = (fr["phase"] == p) & (fr["year"] == y)
                    sub = fr[m]
                    wv = sub[wcol].to_numpy(float)
                    wy = wv * sub["ret"].to_numpy(float)
                    S, Wd, DD = cell_stats(sub["xd"].to_numpy(), wy)
                    Slist.append(S)
                    Dlist.append(DD)
                    Wlist.append(Wd)
            Sbb, Srr = float(np.mean(Sb)), float(np.mean(Sr))
            Dbb, Drr = float(np.mean(Db)), float(np.mean(Dr))
            dsum5 += Srr - Sbb
            Nbb = float(fr[(fr["year"] == y)]["w_base"].sum())
            Nrr = float(fr[(fr["year"] == y)]["w_rule_ts"].sum())
            R = float(Nrr / Nbb) if Nbb > 0 else 1.0
            ctrl = float(R * Sbb)
            per_year.append({
                "year": ANCHORS[y].date().isoformat() if y < 4 else "2025-09-24",
                "S_bar_base": round(Sbb, 6), "S_bar_rule": round(Srr, 6),
                "delta": round(Srr - Sbb, 6),
                "DD_bar_base": round(Dbb, 6), "DD_bar_rule": round(Drr, 6),
                "realised_ratio": round(R, 6), "S_ctrl_bar": round(ctrl, 6),
                "gain_over_ctrl": round(Srr - ctrl, 6),
                "pass_sum": bool(Srr >= Sbb), "pass_dd": bool(Drr <= Dbb + DD_TOL),
                "pass_ctrl": bool(Srr > ctrl)})
        ns = sum(1 for r in per_year if r["pass_sum"])
        nd = sum(1 for r in per_year if r["pass_dd"])
        nc = sum(1 for r in per_year if r["pass_ctrl"])
        tilt = {"direction": direction, "p80": p80, "per_year": per_year,
                "dSum5y": round(float(dsum5), 6), "gate": GATE_DSUM,
                "legs": {"sum": ns, "dd": nd, "ctrl": nc},
                "promising": bool(ns >= 4 and nd >= 4 and nc >= 4 and dsum5 >= GATE_DSUM)}

    res = {
        "config": {
            "feature": "TS(h)=IV_7d_ATM(h)/DVOL(h); 6h amount-weighted vwap_iv, 3..10d expiry, |K/idx-1|<=2%; <0.5 coin -> NaN; carry 24h; SOL/BNB/XRP use BTC TS",
            "join": "TS_used = last full hour with hour_end <= bar open (merge_asof T-1h backward)",
            "dip_base": "read-only oc_depthtilt/fills.parquet (D0+B1, 4 phases, R2 rungs); fidelity ref [0.9113,0.8326,2.0998,3.1974,0.6772]",
            "book": "phase-0 4h grid; sigma=std(360, min120, ddof1, shift1) of 4h-open returns; label=next-6-bar (24h) open-to-open / sigma; Spearman IC per year/coin, dev only",
            "candidate": "tilt scored IFF tercile sign same in 4/4 dev years AND |spread|>5bps in >=3/4 (spread on mean(ret) bps)",
            "tilt": "damp x0.6 above walk-forward hourly p80 (if high=worse) else boost x1.3; p80 per signal from hourly TS with hour_end < anchor-7d; NaN TS keeps base; gate legs + dSum5y>=+0.273 (5y calibration, labelled)",
            "leakage": "strike window uses hours ending <= signal hour; DVOL latest candle_end <= hour_end; join hour_end <= T; p80 hourly history before anchor-7d; no stat from 2025-09-24+ in descriptives/thresholds",
        },
        "fidelity": {"got_uncapped_S_bar": [round(v, 6) for v in got],
                     "ref": FID_REF, "base_sum5y": round(base_sum5y, 6)},
        "D1_hourly_TS": d1,
        "D2_dips_dev": d2,
        "D3_book_IC_dev": book,
        "candidate": {"signs_hi_minus_lo": signs,
                      "spreads_bps": [round(float(v), 4) for v in spreads_bps],
                      "same_sign_4of4": bool(same_sign),
                      "n_years_spread_gt5bps": int(n_big),
                      "fires": bool(fires), "direction": direction},
        "tilt_5y_calibration": tilt,
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({"candidate": res["candidate"],
                      "tilt": tilt["legs"] if tilt else None,
                      "dSum5y": tilt["dSum5y"] if tilt else None}, indent=1))


if __name__ == "__main__":
    main()
