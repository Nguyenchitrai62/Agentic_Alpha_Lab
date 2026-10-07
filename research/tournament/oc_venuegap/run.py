"""oc_venuegap run: Binance-1m vs Bybit-1m B1 dip-ladder comparison (diagnostic).

One process; all-five-coins 1m opens/closes per venue held as float32 arrays
for the venue-native n detector (same pattern as oc_b1deeper, peak ~0.5 GB);
H/L of ONE coin x TWO venues at a time; RAM < 3 GB. See PLAN.md (frozen).

Usage: .venv/Scripts/python.exe research/tournament/oc_venuegap/run.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd

import venue as V

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
OVERLAP_START = pd.Timestamp("2021-11-15 00:00", tz="UTC")  # S5 start
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
SETTLE_HOURS = (0, 8, 16)
W = V.LIVE_B - V.LIVE_A + 1  # 223 live minutes
BIN_BTC = Path("data/raw/btc_intraday_20260924")
BIN_MAJ = Path("data/raw/majors_intraday_20260924")
BYB_DIR = Path("data/raw/bybit_linear_1m_20261004")


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


def load_bybit_ohlc(sym: str, idx):
    m = pd.read_parquet(BYB_DIR / f"{sym}_1m.parquet",
                        columns=["open_time", "open", "high", "low", "close"])
    m["open_time"] = pd.to_datetime(m["open_time"], unit="ms", utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    m = m.set_index("open_time").reindex(idx)
    O = m["open"].to_numpy(dtype=np.float32)
    H = m["high"].to_numpy(dtype=np.float32)
    L = m["low"].to_numpy(dtype=np.float32)
    C = m["close"].to_numpy(dtype=np.float32)
    del m
    return O, H, L, C


def bar_sigmas(O_bar: np.ndarray):
    return (pd.Series(O_bar.astype(float)).pct_change()
            .rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy())


def year_of_exit(t) -> int | None:
    t = pd.Timestamp(t)
    a4 = ANCHORS[4]
    if t > a4 + pd.Timedelta(days=365):
        return 4
    for y in range(5):
        a0 = ANCHORS[y]
        if a0 < t <= a0 + pd.Timedelta(days=365):
            return y
    if ANCHORS[0] < t <= a4:  # leap-day gap 2024-09-23..2024-09-24
        return 3
    return None


def main():
    idx = pd.date_range(START, END, freq="1min")
    n_all = len(idx)
    nb = (n_all - 1) // 240
    t0 = idx[:nb * 240:240]

    Obin, Cbin, Obyb, Cbyb = {}, {}, {}, {}
    Hbyb_full, Lbyb_full = {}, {}
    for sym in MAJORS:
        o, c = load_binance_oc(sym, idx)
        Obin[sym], Cbin[sym] = o, c
        print(f"loaded binance OC {sym}", flush=True)
    for sym in MAJORS:
        o, h, lo, c = load_bybit_ohlc(sym, idx)
        Obyb[sym], Hbyb_full[sym], Lbyb_full[sym], Cbyb[sym] = o, h, lo, c
        print(f"loaded bybit OHLC {sym}", flush=True)

    opens_bin, sig_bin, opens_byb, sig_byb = {}, {}, {}, {}
    for sym in MAJORS:
        ob = Obin[sym][:nb * 240:240].astype(float)
        opens_bin[sym], sig_bin[sym] = ob, bar_sigmas(ob)
        ob2 = Obyb[sym][:nb * 240:240].astype(float)
        opens_byb[sym], sig_byb[sym] = ob2, bar_sigmas(ob2)
    del ob, ob2

    fills = []  # one row per kept venue fill
    pair_counts = {}  # (sym, k) -> dict(both, bin_only, byb_only, neither, bars)
    cover = {}  # sym -> dict counters
    o_shift = {s: [] for s in MAJORS}  # bps per both-tradeable bar
    lv_shift = {}  # (sym, k) -> list bps
    for s in MAJORS:
        for k in V.RUNGS:
            pair_counts[(s, k)] = dict(bars=0, both=0, bin_only=0, byb_only=0, neither=0)
            lv_shift[(s, k)] = []

    for sym in MAJORS:
        Hbin, Lbin = load_binance_hl(sym, idx)
        Hby, Lby = Hbyb_full.pop(sym), Lbyb_full.pop(sym)
        Oa_bin, Ca_bin, La_bin, Ha_bin = Obin[sym], Cbin[sym], Lbin, Hbin
        Oa_byb, Ca_byb, La_byb, Ha_byb = Obyb[sym], Cbyb[sym], Lby, Hby
        others = [s for s in MAJORS if s != sym]
        cov = dict(bars=0, both=0, bin_only=0, byb_only=0, neither=0)
        n_bar = 0
        for j in range(nb):
            bt = t0[j]
            if not (OVERLAP_START <= bt < YEAR_END):
                continue
            o1b, sgb = float(opens_bin[sym][j]), float(sig_bin[sym][j])
            o1y, sgy = float(opens_byb[sym][j]), float(sig_byb[sym][j])
            okb = np.isfinite(o1b) and np.isfinite(sgb) and o1b > 0 and sgb > 0
            oky = np.isfinite(o1y) and np.isfinite(sgy) and o1y > 0 and sgy > 0
            cov["bars"] += 1
            if okb and oky:
                cov["both"] += 1
                o_shift[sym].append((o1y - o1b) / o1b * 1e4)
            elif okb:
                cov["bin_only"] += 1
                continue
            elif oky:
                cov["byb_only"] += 1
                continue
            else:
                cov["neither"] += 1
                continue
            base = j * 240
            if base + 240 >= n_all:
                continue
            o2b = float(Oa_bin[base + 240]) if np.isfinite(Oa_bin[base + 240]) else np.nan
            o2y = float(Oa_byb[base + 240]) if np.isfinite(Oa_byb[base + 240]) else np.nan
            settle = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
            low_bin = La_bin[base + V.LIVE_A:base + V.LIVE_B + 1].astype(float)
            low_byb = La_byb[base + V.LIVE_A:base + V.LIVE_B + 1].astype(float)
            cmat_bin = np.stack([Cbin[b][base + V.LIVE_A - 1:base + V.LIVE_B].astype(float)
                                 for b in others])
            oo_bin = np.array([opens_bin[b][j] for b in others], dtype=float)
            ss_bin = np.array([sig_bin[b][j] for b in others], dtype=float)
            nvec_bin = V.n_vector(cmat_bin, oo_bin, ss_bin)
            cmat_byb = np.stack([Cbyb[b][base + V.LIVE_A - 1:base + V.LIVE_B].astype(float)
                                 for b in others])
            oo_byb = np.array([opens_byb[b][j] for b in others], dtype=float)
            ss_byb = np.array([sig_byb[b][j] for b in others], dtype=float)
            nvec_byb = V.n_vector(cmat_byb, oo_byb, ss_byb)
            Ha_b = Ha_bin[base:base + 240].astype(float)
            La_b = La_bin[base:base + 240].astype(float)
            Ca_b = Ca_bin[base:base + 240].astype(float)
            Oa_b = Oa_bin[base:base + 240].astype(float)
            Ha_y = Ha_byb[base:base + 240].astype(float)
            La_y = La_byb[base:base + 240].astype(float)
            Ca_y = Ca_byb[base:base + 240].astype(float)
            Oa_y = Oa_byb[base:base + 240].astype(float)
            for k in V.RUNGS:
                lvb = o1b * (1 - k * sgb)
                lvy = o1y * (1 - k * sgy)
                if not (np.isfinite(lvb) and lvb > 0 and np.isfinite(lvy) and lvy > 0):
                    continue
                pc = pair_counts[(sym, k)]
                pc["bars"] += 1
                lv_shift[(sym, k)].append((lvy - lvb) / lvb * 1e4)
                ib = V.find_fill(low_bin, lvb)
                iy = V.find_fill(low_byb, lvy)
                fb = V.LIVE_A + ib if ib is not None else None
                fy = V.LIVE_A + iy if iy is not None else None
                if fb is not None and fy is not None:
                    pc["both"] += 1
                elif fb is not None:
                    pc["bin_only"] += 1
                elif fy is not None:
                    pc["byb_only"] += 1
                else:
                    pc["neither"] += 1
                for tag, f, lv, sg, nvec, Ha, La, Ca, Oa, o2 in (
                        ("bin", fb, lvb, sgb, nvec_bin, Ha_b, La_b, Ca_b, Oa_b, o2b),
                        ("byb", fy, lvy, sgy, nvec_byb, Ha_y, La_y, Ca_y, Oa_y, o2y)):
                    if f is None:
                        continue
                    iwin = f - V.LIVE_A
                    nf = int(nvec[iwin])
                    ret, x, how = V.outcome_from_fill(Ha, La, Ca, Oa, f, lv, sg, o2, settle)
                    if not np.isfinite(ret):
                        continue
                    exit_ts = bt + pd.Timedelta(minutes=int(x)) if int(x) < 240 else bt + pd.Timedelta(hours=4)
                    yi = year_of_exit(exit_ts)
                    if yi is None:
                        continue
                    low_f = float(La[f])
                    d_bps = (lv - low_f) / lv * 1e4 if np.isfinite(low_f) else np.nan
                    fills.append(dict(sym=sym, k=float(k), venue=tag, y=int(yi),
                                      f=int(f), n=int(nf), w=float(V.size_mult(nf)),
                                      ret=float(ret), x=int(x), how=how,
                                      d_bps=float(d_bps), fill=float(lv), t_bar=str(bt),
                                      exit=str(exit_ts)))
            n_bar += 1
        cover[sym] = cov
        print(f"{sym}: bars={n_bar} cover={cov}", flush=True)
        del Hbin, Lbin, Hby, Lby, Ha_b, La_b, Ca_b, Oa_b, Ha_y, La_y, Ca_y, Oa_y

    df = pd.DataFrame(fills)
    # --- aggregates ---
    per_coin_depth, per_year, per_coin_year = [], [], []
    for sym in MAJORS:
        for k in V.RUNGS:
            pc = pair_counts[(sym, k)]
            for tag in ("bin", "byb"):
                sub = df[(df["sym"] == sym) & (df["k"] == k) & (df["venue"] == tag)]
                n = len(sub)
                if n:
                    per_coin_depth.append(dict(sym=sym, k=k, venue=tag, n=int(n),
                        mean_ret=float(sub["ret"].mean()), sum_ret=float(sub["ret"].sum()),
                        sum_w=float((sub["w"] * sub["ret"]).sum()),
                        tp_rate=float((sub["how"] == "tp").mean()),
                        mean_d_bps=float(sub["d_bps"].mean())))
                else:
                    per_coin_depth.append(dict(sym=sym, k=k, venue=tag, n=0,
                        mean_ret=0.0, sum_ret=0.0, sum_w=0.0, tp_rate=0.0, mean_d_bps=0.0))
    # paired both-fill exit agreement + depth diff
    paired = []
    if len(df):
        piv = df.pivot_table(index=["sym", "k", "t_bar"], columns="venue",
                             values=["ret", "how", "d_bps", "f"], aggfunc="first")
        both_idx = [i for i in piv.index
                    if ("ret", "bin") in piv.columns and ("ret", "byb") in piv.columns
                    and np.isfinite(piv.loc[i, ("ret", "bin")])
                    and np.isfinite(piv.loc[i, ("ret", "byb")])]
        for (sym, k, _) in both_idx:
            row = piv.loc[(sym, k, _)]
            paired.append(dict(sym=sym, k=float(k),
                               ret_bin=float(row[("ret", "bin")]),
                               ret_byb=float(row[("ret", "byb")]),
                               how_bin=str(row[("how", "bin")]),
                               how_byb=str(row[("how", "byb")]),
                               d_bin=float(row[("d_bps", "bin")]),
                               d_byb=float(row[("d_bps", "byb")])))
    pdf = pd.DataFrame(paired)
    pair_stats = []
    for sym in MAJORS:
        for k in V.RUNGS:
            sub = pdf[(pdf["sym"] == sym) & (pdf["k"] == k)] if len(pdf) else pdf
            if len(sub):
                pair_stats.append(dict(sym=sym, k=k, n_both=int(len(sub)),
                    mean_ret_diff=float((sub["ret_bin"] - sub["ret_byb"]).mean()),
                    sum_ret_diff=float((sub["ret_bin"] - sub["ret_byb"]).sum()),
                    mean_d_diff_bps=float((sub["d_bin"] - sub["d_byb"]).mean()),
                    both_tp=float(((sub["how_bin"] == "tp") & (sub["how_byb"] == "tp")).mean()),
                    bin_only_tp=float(((sub["how_bin"] == "tp") & (sub["how_byb"] != "tp")).mean()),
                    byb_only_tp=float(((sub["how_bin"] != "tp") & (sub["how_byb"] == "tp")).mean())))
            else:
                pair_stats.append(dict(sym=sym, k=k, n_both=0, mean_ret_diff=0.0,
                    sum_ret_diff=0.0, mean_d_diff_bps=0.0, both_tp=0.0,
                    bin_only_tp=0.0, byb_only_tp=0.0))
    for yi in range(5):
        row = dict(year=ANCHORS[yi].date().isoformat())
        for tag in ("bin", "byb"):
            sub = df[(df["y"] == yi) & (df["venue"] == tag)]
            row[f"n_{tag}"] = int(len(sub))
            row[f"sum_{tag}"] = float(sub["ret"].sum()) if len(sub) else 0.0
            row[f"sum_w_{tag}"] = float((sub["w"] * sub["ret"]).sum()) if len(sub) else 0.0
            row[f"tp_{tag}"] = float((sub["how"] == "tp").mean()) if len(sub) else 0.0
        row["gap_sum"] = row["sum_bin"] - row["sum_byb"]
        row["gap_sum_w"] = row["sum_w_bin"] - row["sum_w_byb"]
        per_year.append(row)
        for sym in MAJORS:
            r = dict(year=ANCHORS[yi].date().isoformat(), sym=sym)
            for tag in ("bin", "byb"):
                sub = df[(df["y"] == yi) & (df["sym"] == sym) & (df["venue"] == tag)]
                r[f"n_{tag}"] = int(len(sub))
                r[f"sum_{tag}"] = float(sub["ret"].sum()) if len(sub) else 0.0
            r["gap"] = r["sum_bin"] - r["sum_byb"]
            per_coin_year.append(r)
    open_stats = []
    for sym in MAJORS:
        a = np.array(o_shift[sym], dtype=float)
        a = a[np.isfinite(a)]
        open_stats.append(dict(sym=sym, n=int(len(a)),
            median_bps=float(np.median(a)) if len(a) else 0.0,
            p90_abs_bps=float(np.percentile(np.abs(a), 90)) if len(a) else 0.0,
            mean_abs_bps=float(np.abs(a).mean()) if len(a) else 0.0))
    lv_stats = []
    for sym in MAJORS:
        for k in V.RUNGS:
            a = np.array(lv_shift[(sym, k)], dtype=float)
            a = a[np.isfinite(a)]
            lv_stats.append(dict(sym=sym, k=k, n=int(len(a)),
                median_bps=float(np.median(a)) if len(a) else 0.0,
                mean_abs_bps=float(np.abs(a).mean()) if len(a) else 0.0))
    tot = {}
    for tag in ("bin", "byb"):
        sub = df[df["venue"] == tag]
        tot[tag] = dict(n=int(len(sub)), sum=float(sub["ret"].sum()) if len(sub) else 0.0,
                        sum_w=float((sub["w"] * sub["ret"]).sum()) if len(sub) else 0.0,
                        tp=float((sub["how"] == "tp").mean()) if len(sub) else 0.0)
    out = {"config": {"venues": ["binance", "bybit"],
                       "bybit_store": "data/raw/bybit_linear_1m_20261004 (S5 store in v411_audit/robust_v411.py)",
                       "binance_store": "data/raw/btc_intraday_20260924 + data/raw/majors_intraday_20260924",
                       "overlap": "bar open T in [2021-11-15, 2026-09-24)",
                       "coins": list(MAJORS), "rungs": list(V.RUNGS),
                       "grid": "4h from 2020-08-01 00:00 UTC",
                       "live": [V.LIVE_A, V.LIVE_B], "maker": V.MAKER,
                       "taker": V.TAKER, "fund_long": 0.0001,
                       "note": "venue-native O/sg/levels/fills/exits (B1 replica); NaN exits dropped per venue; Y0 short window from 2021-11-15; years by exit date"},
           "n_fills": int(len(df)),
           "coverage": cover,
           "totals": tot,
           "gap_total_sum": tot["bin"]["sum"] - tot["byb"]["sum"],
           "gap_total_sum_w": tot["bin"]["sum_w"] - tot["byb"]["sum_w"],
           "per_coin_depth": per_coin_depth,
           "pair_counts": [{**dict(sym=s, k=k), **pair_counts[(s, k)]} for s in MAJORS for k in V.RUNGS],
           "pair_stats": pair_stats,
           "per_year": per_year,
           "per_coin_year": per_coin_year,
           "open_shift_bps": open_stats,
           "level_shift_bps": lv_stats}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_fills", len(df), "gap_total", out["gap_total_sum"], flush=True)
    print(json.dumps({"per_year": per_year, "totals": tot}, indent=1))


if __name__ == "__main__":
    main()
