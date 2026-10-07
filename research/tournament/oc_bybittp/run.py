"""oc_bybittp run: Binance-1m vs Bybit-1m B1 TP near-miss diagnostic.

One process; all-five-coins 1m opens/closes per venue held as float32 arrays
for the venue-native n detector (oc_b1deeper pattern); H/L of ONE coin x TWO
venues at a time; RAM < 3 GB. See PLAN.md (frozen).

Usage: .venv/Scripts/python.exe research/tournament/oc_bybittp/run.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd

import core as C

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
OVERLAP_START = pd.Timestamp("2021-11-15 00:00", tz="UTC")  # S5 start
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
SETTLE_HOURS = (0, 8, 16)
W = C.LIVE_B - C.LIVE_A + 1  # 223 live minutes
BIN_BTC = Path("data/raw/btc_intraday_20260924")
BIN_MAJ = Path("data/raw/majors_intraday_20260924")
BYB_DIR = Path("data/raw/bybit_linear_1m_20261004")
OFFSETS = list(C.OFFSETS)
MISS_TH = (1, 2, 3, 5, 10, 25)


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
    Cc = m["close"].to_numpy(dtype=np.float32)
    del m, parts
    return O, Cc


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
    Cc = m["close"].to_numpy(dtype=np.float32)
    del m
    return O, H, L, Cc


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


def dist_stats(a: np.ndarray):
    a = np.asarray(a, dtype=float)
    a = a[np.isfinite(a)]
    if len(a) == 0:
        return dict(n=0, median=np.nan, p25=np.nan, p75=np.nan, p90=np.nan,
                    mean=np.nan, neg_share=np.nan,
                    **{f"le_{t}": np.nan for t in MISS_TH})
    return dict(
        n=int(len(a)), median=float(np.median(a)),
        p25=float(np.percentile(a, 25)), p75=float(np.percentile(a, 75)),
        p90=float(np.percentile(a, 90)), mean=float(np.mean(a)),
        neg_share=float((a < 0).mean()),
        **{f"le_{t}": float((a <= t).mean()) for t in MISS_TH})


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

    fills = []   # one row per kept venue fill (oc_venuegap-compatible)
    paired = []  # one row per both-fill rung with both exits kept
    cover = {}
    n_single_tp = {s: dict(bin=0, byb=0) for s in MAJORS}

    for sym in MAJORS:
        Hbin, Lbin = load_binance_hl(sym, idx)
        Hby, Lby = Hbyb_full.pop(sym), Lbyb_full.pop(sym)
        Oa_bin, Ca_bin, La_bin, Ha_bin = Obin[sym], Cbin[sym], Lbin, Hbin
        Oa_byb, Ca_byb, La_byb, Ha_byb = Obyb[sym], Cbyb[sym], Lby, Hby
        others = [s for s in MAJORS if s != sym]
        cov = dict(bars=0, both=0, bin_only=0, byb_only=0, neither=0)
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
            low_bin = La_bin[base + C.LIVE_A:base + C.LIVE_B + 1].astype(float)
            low_byb = La_byb[base + C.LIVE_A:base + C.LIVE_B + 1].astype(float)
            cmat_bin = np.stack([Cbin[b][base + C.LIVE_A - 1:base + C.LIVE_B].astype(float)
                                 for b in others])
            oo_bin = np.array([opens_bin[b][j] for b in others], dtype=float)
            ss_bin = np.array([sig_bin[b][j] for b in others], dtype=float)
            nvec_bin = C.n_vector(cmat_bin, oo_bin, ss_bin)
            cmat_byb = np.stack([Cbyb[b][base + C.LIVE_A - 1:base + C.LIVE_B].astype(float)
                                 for b in others])
            oo_byb = np.array([opens_byb[b][j] for b in others], dtype=float)
            ss_byb = np.array([sig_byb[b][j] for b in others], dtype=float)
            nvec_byb = C.n_vector(cmat_byb, oo_byb, ss_byb)
            Ha_b = Ha_bin[base:base + 240].astype(float)
            La_b = La_bin[base:base + 240].astype(float)
            Ca_b = Ca_bin[base:base + 240].astype(float)
            Oa_b = Oa_bin[base:base + 240].astype(float)
            Ha_y = Ha_byb[base:base + 240].astype(float)
            La_y = La_byb[base:base + 240].astype(float)
            Ca_y = Ca_byb[base:base + 240].astype(float)
            Oa_y = Oa_byb[base:base + 240].astype(float)
            for k in C.RUNGS:
                lvb = o1b * (1 - k * sgb)
                lvy = o1y * (1 - k * sgy)
                if not (np.isfinite(lvb) and lvb > 0 and np.isfinite(lvy) and lvy > 0):
                    continue
                ib = C.find_fill(low_bin, lvb)
                iy = C.find_fill(low_byb, lvy)
                fb = C.LIVE_A + ib if ib is not None else None
                fy = C.LIVE_A + iy if iy is not None else None
                res = {}
                for tag, f, lv, sg, nvec, Ha, La, Ca, Oa, o2 in (
                        ("bin", fb, lvb, sgb, nvec_bin, Ha_b, La_b, Ca_b, Oa_b, o2b),
                        ("byb", fy, lvy, sgy, nvec_byb, Ha_y, La_y, Ca_y, Oa_y, o2y)):
                    if f is None:
                        continue
                    iwin = f - C.LIVE_A
                    nf = int(nvec[iwin])
                    ret, x, how = C.outcome_from_fill(Ha, La, Ca, Oa, f, lv, sg, o2, settle)
                    if not np.isfinite(ret):
                        continue
                    exit_ts = bt + pd.Timedelta(minutes=int(x)) if int(x) < 240 else bt + pd.Timedelta(hours=4)
                    yi = year_of_exit(exit_ts)
                    if yi is None:
                        continue
                    low_f = float(La[f])
                    d_bps = (lv - low_f) / lv * 1e4 if np.isfinite(low_f) else np.nan
                    fills.append(dict(sym=sym, k=float(k), venue=tag, y=int(yi),
                                      f=int(f), n=int(nf), w=float(C.size_mult(nf)),
                                      ret=float(ret), x=int(x), how=how,
                                      d_bps=float(d_bps), fill=float(lv), t_bar=str(bt),
                                      exit=str(exit_ts)))
                    tp = C.tp_for(lv, sg, 0.0)
                    miss = C.max_high_miss_bps(Ha, f, tp)
                    res[tag] = dict(f=f, lv=lv, sg=sg, ret=ret, x=x, how=how,
                                    tp=tp, miss=miss, exit_ts=exit_ts, yi=yi,
                                    Ha=Ha, La=La, Ca=Ca, Oa=Oa, o2=o2)
                # single-venue TP counts (fill-gap TPs, not near-miss)
                if "bin" in res and "byb" not in res and res["bin"]["how"] == "tp":
                    n_single_tp[sym]["bin"] += 1
                if "byb" in res and "bin" not in res and res["byb"]["how"] == "tp":
                    n_single_tp[sym]["byb"] += 1
                if "bin" in res and "byb" in res:
                    rb, ry = res["bin"], res["byb"]
                    row = dict(sym=sym, k=float(k), t_bar=str(bt),
                               y_bin=int(rb["yi"]), y_byb=int(ry["yi"]),
                               f_bin=int(rb["f"]), f_byb=int(ry["f"]),
                               ret_bin=float(rb["ret"]), ret_byb=float(ry["ret"]),
                               how_bin=rb["how"], how_byb=ry["how"],
                               tp_bin=float(rb["tp"]), tp_byb=float(ry["tp"]),
                               miss_bin=float(rb["miss"]), miss_byb=float(ry["miss"]))
                    for d in OFFSETS:
                        sc = 1 - d / 1e4
                        rbd, xbd, hbd = C.outcome_from_fill(
                            rb["Ha"], rb["La"], rb["Ca"], rb["Oa"],
                            rb["f"], rb["lv"], rb["sg"], rb["o2"], settle, sc)
                        ryd, xyd, hyd = C.outcome_from_fill(
                            ry["Ha"], ry["La"], ry["Ca"], ry["Oa"],
                            ry["f"], ry["lv"], ry["sg"], ry["o2"], settle, sc)
                        row[f"how_bin_d{d}"] = hbd
                        row[f"ret_bin_d{d}"] = float(rbd) if np.isfinite(rbd) else np.nan
                        row[f"how_byb_d{d}"] = hyd
                        row[f"ret_byb_d{d}"] = float(ryd) if np.isfinite(ryd) else np.nan
                    paired.append(row)
        cover[sym] = cov
        print(f"{sym}: paired={sum(1 for r in paired if r['sym'] == sym)} cover={cov}", flush=True)
        del Hbin, Lbin, Hby, Lby, Ha_b, La_b, Ca_b, Oa_b, Ha_y, La_y, Ca_y, Oa_y

    df = pd.DataFrame(fills)
    pdf = pd.DataFrame(paired)

    # --- aggregates ---
    per_year = []
    for yi in range(5):
        r = dict(year=ANCHORS[yi].date().isoformat())
        for tag in ("bin", "byb"):
            sub = df[(df["y"] == yi) & (df["venue"] == tag)] if len(df) else df
            r[f"n_{tag}"] = int(len(sub))
            r[f"sum_{tag}"] = float(sub["ret"].sum()) if len(sub) else 0.0
            r[f"tp_{tag}"] = float((sub["how"] == "tp").mean() if len(sub) else 0.0)
        r["gap_sum"] = r["sum_bin"] - r["sum_byb"]
        per_year.append(r)
    tot = {}
    for tag in ("bin", "byb"):
        sub = df[df["venue"] == tag] if len(df) else df
        tot[tag] = dict(n=int(len(sub)), sum=float(sub["ret"].sum()) if len(sub) else 0.0,
                        tp=float((sub["how"] == "tp").mean()) if len(sub) else 0.0)

    # divergent classes on paired rungs
    div = {}
    if len(pdf):
        pdf = pdf.copy()
        pdf["bin_tp"] = pdf["how_bin"] == "tp"
        pdf["byb_tp"] = pdf["how_byb"] == "tp"
        pdf["cls"] = np.where(pdf["bin_tp"] & pdf["byb_tp"], "both_tp",
                       np.where(pdf["bin_tp"] & ~pdf["byb_tp"], "bin_only",
                       np.where(~pdf["bin_tp"] & pdf["byb_tp"], "byb_only", "neither")))
    div_counts = {}
    for sym in MAJORS:
        sub = pdf[pdf["sym"] == sym] if len(pdf) else pdf
        div_counts[sym] = {c: int((sub["cls"] == c).sum()) if len(sub) else 0
                           for c in ("both_tp", "bin_only", "byb_only", "neither")}
        div_counts[sym]["n_both"] = int(len(sub))
    div_counts["ALL"] = {c: int((pdf["cls"] == c).sum()) if len(pdf) else 0
                         for c in ("both_tp", "bin_only", "byb_only", "neither")}
    div_counts["ALL"]["n_both"] = int(len(pdf))

    # near-miss distributions: bin_only -> miss on byb side; byb_only -> miss on bin side
    miss_dist, miss_exit = {}, {}
    for sym in list(MAJORS) + ["ALL"]:
        for direction in ("bin_only", "byb_only"):
            sub = (pdf[(pdf["sym"] == sym) & (pdf["cls"] == direction)]
                   if (len(pdf) and sym != "ALL") else
                   (pdf[pdf["cls"] == direction] if len(pdf) else pdf))
            miss_col = "miss_byb" if direction == "bin_only" else "miss_bin"
            how_col = "how_byb" if direction == "bin_only" else "how_bin"
            key = f"{sym}.{direction}"
            miss_dist[key] = dist_stats(sub[miss_col].to_numpy() if len(sub) else np.array([]))
            ex = {}
            for h in ("tp", "stop", "backstop", "time"):
                ex[h] = float((sub[how_col] == h).mean()) if len(sub) else 0.0
            miss_exit[key] = dict(n=int(len(sub)), **ex)

    # per-coin-year divergent counts (year = bin-exit year)
    per_coin_year = []
    for yi in range(5):
        for sym in MAJORS:
            sub = pdf[(pdf["sym"] == sym) & (pdf["y_bin"] == yi)] if len(pdf) else pdf
            per_coin_year.append(dict(
                year=ANCHORS[yi].date().isoformat(), sym=sym, n_both=int(len(sub)),
                both_tp=int(((sub["cls"] == "both_tp")).sum()) if len(sub) else 0,
                bin_only=int((sub["cls"] == "bin_only").sum()) if len(sub) else 0,
                byb_only=int((sub["cls"] == "byb_only").sum()) if len(sub) else 0,
                neither=int((sub["cls"] == "neither").sum()) if len(sub) else 0))

    # offset recovery tables
    rec_byb, cost_bin, conv_bin, symm = {}, {}, {}, {}
    for sym in list(MAJORS) + ["ALL"]:
        sub_all = pdf[pdf["sym"] == sym] if (len(pdf) and sym != "ALL") else pdf
        bin_only = sub_all[sub_all["cls"] == "bin_only"] if len(sub_all) else sub_all
        byb_only = sub_all[sub_all["cls"] == "byb_only"] if len(sub_all) else sub_all
        bin_tp = sub_all[sub_all["bin_tp"]] if len(sub_all) else sub_all
        byb_tp = sub_all[sub_all["byb_tp"]] if len(sub_all) else sub_all
        bin_nontp = sub_all[~sub_all["bin_tp"]] if len(sub_all) else sub_all
        byb_nontp = sub_all[~sub_all["byb_tp"]] if len(sub_all) else sub_all
        for d in OFFSETS:
            # Bybit recovery on bin-only rungs
            rec_byb[f"{sym}.d{d}"] = dict(
                n=int(len(bin_only)),
                rec_share=float((bin_only[f"how_byb_d{d}"] == "tp").mean()) if len(bin_only) else 0.0,
                rec_n=int((bin_only[f"how_byb_d{d}"] == "tp").sum()) if len(bin_only) else 0)
            # Binance cost on its base-TP rungs (still TP + shave)
            st = bin_tp[bin_tp[f"how_bin_d{d}"] == "tp"] if len(bin_tp) else bin_tp
            shave = ((st[f"ret_bin_d{d}"] - st["ret_bin"]) * 1e4
                     if len(st) else pd.Series([], dtype=float))
            cost_bin[f"{sym}.d{d}"] = dict(
                n=int(len(bin_tp)),
                still_tp_share=float((bin_tp[f"how_bin_d{d}"] == "tp").mean()) if len(bin_tp) else 0.0,
                mean_shave_bps=float(shave.mean()) if len(shave) else 0.0)
            # Binance symmetric conversion on its base-non-TP paired rungs
            conv_bin[f"{sym}.d{d}"] = dict(
                n=int(len(bin_nontp)),
                conv_share=float((bin_nontp[f"how_bin_d{d}"] == "tp").mean()) if len(bin_nontp) else 0.0,
                conv_n=int((bin_nontp[f"how_bin_d{d}"] == "tp").sum()) if len(bin_nontp) else 0)
            # symmetry: byb-side recovery + cost
            rec_byb_sym = float((byb_only[f"how_bin_d{d}"] == "tp").mean()) if len(byb_only) else 0.0
            st2 = byb_tp[byb_tp[f"how_byb_d{d}"] == "tp"] if len(byb_tp) else byb_tp
            sh2 = ((st2[f"ret_byb_d{d}"] - st2["ret_byb"]) * 1e4
                   if len(st2) else pd.Series([], dtype=float))
            symm[f"{sym}.d{d}"] = dict(
                n_byb_only=int(len(byb_only)), n_byb_tp=int(len(byb_tp)),
                bin_rec_on_byb_only=float(rec_byb_sym),
                byb_still_tp_share=float((byb_tp[f"how_byb_d{d}"] == "tp").mean()) if len(byb_tp) else 0.0,
                byb_mean_shave_bps=float(sh2.mean()) if len(sh2) else 0.0,
                byb_conv_on_nontp=float((byb_nontp[f"how_byb_d{d}"] == "tp").mean()) if len(byb_nontp) else 0.0)

    out = {"config": {"venues": ["binance", "bybit"],
                       "bybit_store": "data/raw/bybit_linear_1m_20261004 (S5 store in v411_audit/robust_v411.py)",
                       "binance_store": "data/raw/btc_intraday_20260924 + data/raw/majors_intraday_20260924",
                       "overlap": "bar open T in [2021-11-15, 2026-09-24)",
                       "coins": list(MAJORS), "rungs": list(C.RUNGS),
                       "grid": "4h from 2020-08-01 00:00 UTC",
                       "live": [C.LIVE_A, C.LIVE_B], "maker": C.MAKER,
                       "taker": C.TAKER, "fund_long": 0.0001,
                       "offsets_bps_inside": OFFSETS,
                       "paired_year": "y_bin = year of the Binance exit (y_byb stored per rung)",
                       "note": "venue-native O/sg/levels/fills/exits (oc_b1deeper B1 replica); NaN exits dropped per venue; miss_bps on the non-TP venue's OWN tape vs its OWN tp; offsets re-evaluate exits exactly with same priority/fees; hypothesis arithmetic only"},
             "n_fills": int(len(df)), "n_paired": int(len(pdf)),
             "coverage": cover, "totals": tot,
             "gap_total_sum": tot["bin"]["sum"] - tot["byb"]["sum"],
             "per_year": per_year,
             "div_counts": div_counts,
             "single_venue_tp": n_single_tp,
             "miss_dist": miss_dist, "miss_exit": miss_exit,
             "per_coin_year": per_coin_year,
             "byb_recovery": rec_byb, "bin_cost": cost_bin,
             "bin_conversion": conv_bin, "symmetry": symm}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    pdf.to_parquet(HERE / "paired.parquet", index=False)
    print("n_fills", len(df), "n_paired", len(pdf),
          "gap_total", out["gap_total_sum"], flush=True)
    print(json.dumps({"div_ALL": div_counts["ALL"],
                      "miss_ALL.bin_only": miss_dist["ALL.bin_only"],
                      "miss_ALL.byb_only": miss_dist["ALL.byb_only"]}, indent=1))


if __name__ == "__main__":
    main()
