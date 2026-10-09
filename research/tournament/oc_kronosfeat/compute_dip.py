"""oc_kronosfeat dip side (HEAVY: 1m klines, run via heavy_slot)."""
from __future__ import annotations
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import rankdata

HERE = Path(__file__).parent
TMP = HERE / "tmp"
FEATS = Path("research/tournament/oc_kronoshidden/kronos_features_4shift.parquet")
ALL8 = ["er1", "er6", "vol1", "vol6", "rng1", "low1", "pdrop2", "pdrop3"]
MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0
DETECT_K = 2.5
START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
PHASES = (0, 1, 2, 3)
SETTLE_HOURS = (0, 8, 16)
B_BOOT = 500


def first_idx(mask):
    if mask.any():
        return int(np.argmax(mask))
    return None


def n_vector(close_others, open_others, sigma_others):
    W = close_others.shape[1]
    n = np.zeros(W, dtype=np.int64)
    for i in range(close_others.shape[0]):
        o, sg = float(open_others[i]), float(sigma_others[i])
        if not (np.isfinite(o) and np.isfinite(sg)) or o <= 0 or sg <= 0:
            continue
        thr = o * (1 - DETECT_K * sg)
        if not np.isfinite(thr):
            continue
        c = close_others[i]
        n += (np.isfinite(c) & (c <= thr)).astype(np.int64)
    return n


def size_mult(nf):
    return 1.0 / (1 + int(nf))


def find_fill(low_win, level):
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_mu_h(Ha, La, Ca, Oa, f, lv, sg, mu, o2, settle):
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + mu * sg)
    post = np.arange(f + 1, 240)
    trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
    ks = first_idx(trig)
    hb = np.asarray(La[f + 1:240], dtype=float) <= bl
    kb = first_idx(hb)
    ht = np.asarray(Ha[f + 1:240], dtype=float) > tp
    kt = first_idx(ht)
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = Oa[x]
        if not np.isfinite(ox):
            return (np.nan, x, "backstop")
        px = bl if ox > bl else ox
        return (px / lv - 1 - MAKER - TAKER, x, "backstop")
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / lv - 1 - 2 * MAKER, x, "tp")
    if ks is not None:
        km = f + 1 + ks
        if km + 1 < 240:
            px, x = Oa[km + 1], km + 1
        else:
            px, x = o2, 240
        if not np.isfinite(px):
            return (np.nan, x, "stop")
        ret = px / lv - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop")
    x = 240
    if not np.isfinite(o2):
        return (np.nan, x, "time")
    return (o2 / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0), x, "time")


def load_oc(sym):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob("%s_1m_20*.parquet" % sym))
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


def load_hl(sym, idx):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob("%s_1m_20*.parquet" % sym))
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


def exit_day_ordinal(bt, x):
    if int(x) < 240:
        d = (bt + pd.Timedelta(minutes=int(x))).date()
    else:
        d = (bt + pd.Timedelta(hours=4)).date()
    return (pd.Timestamp(d, tz="UTC") - pd.Timestamp("1970-01-01", tz="UTC")).days


def cell_stats(dates, wy):
    if wy.size == 0:
        return 0.0, 0.0, 0.0
    order = np.argsort(dates, kind="stable")
    d = dates[order]
    v = wy[order]
    uniq, idx = np.unique(d, return_index=True)
    bounds = np.append(idx[1:], v.size)
    daily = np.array([v[s:e].sum() for s, e in zip(idx, bounds)])
    cum = np.cumsum(daily)
    peak = np.maximum.accumulate(cum)
    dd = float(np.min(cum - peak))
    return float(daily.sum()), float(daily.min()), float(-dd)


def spearman_xy(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = int(len(x))
    if n < 3:
        return float("nan"), n
    if np.std(x) == 0.0 or np.std(y) == 0.0:
        return float("nan"), n
    rx, ry = rankdata(x), rankdata(y)
    if np.std(rx) == 0.0 or np.std(ry) == 0.0:
        return float("nan"), n
    return float(np.corrcoef(rx, ry)[0, 1]), n


def week_ids(T):
    d = pd.DatetimeIndex(T).tz_convert("UTC")
    epoch_mon = pd.Timestamp("1970-01-05", tz="UTC")
    days = ((d - epoch_mon).total_seconds() // 86400).astype(int)
    return (days // 7).astype(int)


def boot_spearman(x, wk, y, seed):
    ic, n = spearman_xy(x, y)
    ci = None
    weeks = np.unique(wk)
    nW = len(weeks)
    if nW >= 2 and np.isfinite(ic):
        rng = np.random.default_rng(seed)
        wpos = {w: np.where(wk == w)[0] for w in weeks}
        xa = np.asarray(x, dtype=float)
        ya = np.asarray(y, dtype=float)
        boots = np.full(B_BOOT, np.nan)
        for b in range(B_BOOT):
            pick = rng.integers(0, nW, size=nW)
            sel = np.concatenate([wpos[weeks[i]] for i in pick])
            xb, yb = xa[sel], ya[sel]
            m = np.isfinite(xb) & np.isfinite(yb)
            xx, yy = xb[m], yb[m]
            if len(xx) < 3 or np.std(xx) == 0.0 or np.std(yy) == 0.0:
                continue
            rx, ry = rankdata(xx), rankdata(yy)
            if np.std(rx) == 0.0 or np.std(ry) == 0.0:
                continue
            boots[b] = np.corrcoef(rx, ry)[0, 1]
        ok = boots[np.isfinite(boots)]
        if len(ok) >= 50:
            ci = [round(float(np.percentile(ok, 2.5)), 4),
                  round(float(np.percentile(ok, 97.5)), 4)]
    return (round(float(ic), 4) if np.isfinite(ic) else None), int(n), ci


def build_ledger():
    O, C, base_idx = {}, {}, None
    for sym in MAJORS:
        ii, o, c = load_oc(sym)
        base_idx = ii if base_idx is None else base_idx
        O[sym], C[sym] = o, c
        print("loaded OC %s" % sym, flush=True)
    n_all = len(base_idx)
    grids = {}
    for p in PHASES:
        off = p * 60
        nb = (n_all - off) // 240
        t0 = base_idx[off:off + nb * 240:240]
        opens_bar, sig_bar = {}, {}
        for sym in MAJORS:
            ob = O[sym][off:off + nb * 240:240].astype(float)
            sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            opens_bar[sym], sig_bar[sym] = ob, sg
        js = [j for j in range(nb) if TRADE_START <= t0[j] < YEAR_END and (off + j * 240 + 240) < n_all]
        grids[p] = dict(off=off, nb=nb, t0=t0, opens=opens_bar, sig=sig_bar, js=js)
        print("shift %d: nb=%d traded=%d" % (p, nb, len(js)), flush=True)
    F = {k: [] for k in ("phase", "coin", "year", "bar_time", "T", "rung",
                         "w", "nfill", "y10", "how10", "d10")}
    coin_ix = {s: i for i, s in enumerate(MAJORS)}
    for sym in MAJORS:
        H, L = load_hl(sym, base_idx)
        La, Ha = L, H
        others = [b for b in MAJORS if b != sym]
        Oa, Ca = O[sym], C[sym]
        for p in PHASES:
            g = grids[p]
            off, t0 = g["off"], g["t0"]
            opens_bar, sig_bar = g["opens"], g["sig"]
            cnt = 0
            for j in g["js"]:
                bt = t0[j]
                o1 = float(opens_bar[sym][j])
                sg = float(sig_bar[sym][j])
                if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                    continue
                base = off + j * 240
                o2m = Oa[base + 240]
                o2 = float(o2m) if np.isfinite(o2m) else np.nan
                settle = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
                yi = year_of(bt)
                if yi is None:
                    continue
                low_win = La[base + LIVE_A:base + LIVE_B + 1].astype(float)
                cmat = np.stack([C[b][base + LIVE_A - 1:base + LIVE_B].astype(float) for b in others])
                oo = np.array([opens_bar[b][j] for b in others], dtype=float)
                ss = np.array([sig_bar[b][j] for b in others], dtype=float)
                nvec = n_vector(cmat, oo, ss)
                Ha_b = Ha[base:base + 240].astype(float)
                La_b = La[base:base + 240].astype(float)
                Ca_b = Ca[base:base + 240].astype(float)
                Oa_b = Oa[base:base + 240].astype(float)
                for ri, k in enumerate(RUNGS):
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = LIVE_A + ib
                    nf = int(nvec[ib])
                    r10, x10, how10 = outcome_mu_h(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 1.0, o2, settle)
                    if not np.isfinite(r10):
                        continue
                    cnt += 1
                    F["phase"].append(p)
                    F["coin"].append(coin_ix[sym])
                    F["year"].append(yi)
                    F["bar_time"].append(off + j * 240)
                    F["T"].append(bt)
                    F["rung"].append(ri)
                    F["w"].append(size_mult(nf))
                    F["nfill"].append(nf)
                    F["y10"].append(r10)
                    F["how10"].append(how10)
                    F["d10"].append(exit_day_ordinal(bt, x10))
            print("%s p%d: fills=%d" % (sym, p, cnt), flush=True)
        del H, L, La, Ha
    led = {}
    for k in ("phase", "coin", "year", "bar_time", "rung", "nfill", "d10"):
        led[k] = np.array(F[k]).astype(np.int64)
    led["T"] = pd.DatetimeIndex(F["T"], tz="UTC")
    for k in ("w", "y10"):
        led[k] = np.array(F[k], dtype=float)
    led["how10"] = np.array(F["how10"], dtype=object)
    return led


def main():
    t0 = time.time()
    TMP.mkdir(parents=True, exist_ok=True)
    led = build_ledger()
    n = len(led["w"])
    print("ledger fills=%d" % n, flush=True)
    ph = led["phase"]
    yr = led["year"]
    base_per_year = []
    for y in range(5):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            if int(m.sum()):
                s, _, _ = cell_stats(led["d10"][m], (led["w"] * led["y10"])[m])
            else:
                s = 0.0
            ss.append(float(s))
        base_per_year.append(ss)
    base_sum5y = float(sum(float(np.mean(ss)) for ss in base_per_year))
    print("4-phase-mean sums: %s sum5y=%.4f" % (
        [round(float(np.mean(ss)), 4) for ss in base_per_year], base_sum5y), flush=True)
    got_p0 = []
    for y in range(5):
        m = (ph == 0) & (yr == y)
        got_p0.append(float((led["w"][m] * led["y10"][m]).sum()))
    print("phase0 sums: %s" % [round(s, 4) for s in got_p0], flush=True)
    (TMP / "dip_ledger_stats.json").write_text(json.dumps({
        "n_fills": int(n),
        "base_4phase_sums": [[round(float(v), 6) for v in ss] for ss in base_per_year],
        "base_mean4": [round(float(np.mean(ss)), 6) for ss in base_per_year],
        "base_sum5y": round(base_sum5y, 6),
        "phase0_raw_sums": [round(float(v), 6) for v in got_p0],
        "ref_base_sum5y": 7.718304,
        "ref_phase0": [2.388052, 0.182865, 3.809764, 2.579274, 0.711509]
    }, indent=1))
    print("joining features ...", flush=True)
    feats = pd.read_parquet(FEATS)
    inv_coin = {i: s for i, s in enumerate(MAJORS)}
    ldf = pd.DataFrame({"sym": [inv_coin[int(c)] for c in led["coin"]],
                        "shift": led["phase"].astype(int),
                        "T": led["T"],
                        "year_ledger": led["year"].astype(int),
                        "rung": led["rung"].astype(int),
                        "w": led["w"], "nfill": led["nfill"].astype(int),
                        "y10": led["y10"], "how10": led["how10"]})
    ldf["T"] = pd.to_datetime(ldf["T"], utc=True)
    j = ldf.merge(feats[["sym", "shift", "T"] + ALL8], on=["sym", "shift", "T"], how="left")
    cov = float(j[ALL8[0]].notna().mean())
    print("feature coverage %.4f (%d/%d)" % (cov, int(j[ALL8[0]].notna().sum()), len(j)), flush=True)
    j["stop"] = j["how10"].isin(["stop", "backstop"]).astype(int)
    j["wk"] = ((j["T"] - pd.Timestamp("1970-01-05", tz="UTC")).dt.total_seconds() // 86400 // 7).astype(int)
    j["year"] = -1
    for yi, a0 in enumerate(ANCHORS):
        a1 = a0 + pd.Timedelta(days=365)
        j.loc[(j["T"] >= a0) & (j["T"] < a1), "year"] = yi
    out = {"spear": [], "quint": [], "low1_by_coin": [], "coverage": cov,
           "n_fills": int(n)}
    for yi in range(5):
        dy = j[j["year"] == yi].reset_index(drop=True)
        dyf = dy[dy[ALL8[0]].notna()].reset_index(drop=True)
        print("dips Y%d fills=%d wfeat=%d elapsed %.0fs" % (yi, len(dy), len(dyf), time.time() - t0), flush=True)
        for fi, feat in enumerate(ALL8):
            xv = dyf[feat].to_numpy(dtype=float)
            yv = dyf["y10"].to_numpy(dtype=float)
            wk = dyf["wk"].to_numpy()
            ic, nn, ci = boot_spearman(xv, wk, yv, seed=(7, yi, fi))
            out["spear"].append({"year": yi, "feat": feat, "ic": ic, "n": nn, "ci": ci,
                                "stop_rate": round(float(dyf["stop"].mean()), 4) if len(dyf) else None,
                                "mean_y10": round(float(dyf["y10"].mean()), 6) if len(dyf) else None})
            qs = dyf[feat].quantile([0.2, 0.4, 0.6, 0.8]).to_list()
            edges = [-float("inf")] + [float(v) for v in qs] + [float("inf")]
            for q in range(5):
                lo, hi = edges[q], edges[q + 1]
                if q < 4:
                    m = (dyf[feat] >= lo) & (dyf[feat] < hi) if np.isfinite(lo) else (dyf[feat] < hi)
                    if not np.isfinite(lo):
                        m = dyf[feat] < hi
                else:
                    m = dyf[feat] >= lo
                dd = dyf[m]
                out["quint"].append({"year": yi, "feat": feat, "q": q,
                                    "lo": lo if np.isfinite(lo) else None,
                                    "hi": hi if np.isfinite(hi) else None,
                                    "n": int(len(dd)),
                                    "mean_y10": round(float(dd["y10"].mean()), 6) if len(dd) else None,
                                    "stop_rate": round(float(dd["stop"].mean()), 4) if len(dd) else None})
        ds = dyf
        xv = ds["low1"].to_numpy(dtype=float)
        yv = ds["y10"].to_numpy(dtype=float)
        for ci, sym in enumerate(MAJORS):
            m = (ds["sym"] == sym).to_numpy()
            ic, nn, cci = boot_spearman(xv[m], ds["wk"].to_numpy()[m], yv[m], seed=(7, yi, 50 + ci))
            out["low1_by_coin"].append({"year": yi, "coin": sym, "ic": ic, "n": nn, "ci": cci})
    bgrp = j[j[ALL8[0]].notna()].groupby(["sym", "shift", "T"], as_index=False).agg(
        flush_mean=("nfill", "mean"), flush_max=("nfill", "max"),
        low1=("low1", "first"), er1=("er1", "first"), er6=("er6", "first"),
        vol1=("vol1", "first"), vol6=("vol6", "first"), rng1=("rng1", "first"),
        pdrop2=("pdrop2", "first"), pdrop3=("pdrop3", "first"),
        year=("year", "first"), wk=("wk", "first"))
    out["flush"] = []
    for yi in range(5):
        dy = bgrp[bgrp["year"] == yi].reset_index(drop=True)
        dy0 = dy[dy["shift"] == 0].reset_index(drop=True)
        print("flush Y%d bars=%d (s0=%d) elapsed %.0fs" % (yi, len(dy), len(dy0), time.time() - t0), flush=True)
        for fi, feat in enumerate(ALL8):
            ic, nn, ci = boot_spearman(dy[feat].to_numpy(float), dy["wk"].to_numpy(), dy["flush_mean"].to_numpy(float), seed=(7, yi, 70 + fi))
            out["flush"].append({"year": yi, "scope": "all", "feat": feat, "ic": ic, "n": nn, "ci": ci})
            ic0, n0, ci0 = boot_spearman(dy0[feat].to_numpy(float), dy0["wk"].to_numpy(), dy0["flush_mean"].to_numpy(float), seed=(7, yi, 80 + fi))
            out["flush"].append({"year": yi, "scope": "s0", "feat": feat, "ic": ic0, "n": n0, "ci": ci0})
    (TMP / "dip_tables.json").write_text(json.dumps(out, indent=1))
    print("wrote tmp/dip_tables.json in %.0fs" % (time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
