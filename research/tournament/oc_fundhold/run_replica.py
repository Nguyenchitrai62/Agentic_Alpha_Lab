"""oc_fundhold replica: BASE (D0 timeout at next open) vs V1/V2 conditional +8h holds.

Single 4h grid (holdext-exact, phase 0), majors x R2 depths, B1 sizes, D0 exits.
Conditional extension: at a BASE timeout, expensive-funding longs (last settled
F > trailing-90d q, strict) exit on time; else extend +8h (minutes 240..719,
same frozen sl/bl/tp, taker fallback, max once). V1 q=q70, V2 q=q50.

One process, one coin's H/L in RAM at a time; O/C float32; heartbeat 600 s.
Resume-safe per-coin caches in tmp/fills_{coin}.parquet. Via heavy_slot, nohup.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd

import fundhold as X
from fund_rule import ANCH5, should_extend

ROOT = HERE.parents[2]
TMP = HERE / "tmp"
START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
ANCH_NS = np.array([a.value for a in ANCHORS], dtype=np.int64)
SETTLE_HOURS = (0, 8, 16)
HEARTBEAT_S = 600
W = X.LIVE_B - X.LIVE_A + 1

_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print(f"[hb {datetime.now(timezone.utc):%H:%M:%S}Z] {tag} alive", flush=True)


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


def exit_date(bt, x: int):
    if int(x) < 720:
        return (bt + pd.Timedelta(minutes=int(x))).date().isoformat()
    return (bt + pd.Timedelta(hours=12)).date().isoformat()


def pad_n(a: np.ndarray, n: int):
    a = np.asarray(a, dtype=float)
    if len(a) >= n:
        return a[:n]
    out = np.full(n, np.nan)
    out[:len(a)] = a
    return out


def daily_path(recs):
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
    hb = threading.Thread(target=heartbeat, args=("run_replica",), daemon=True)
    hb.start()
    t_start = time.time()
    TMP.mkdir(parents=True, exist_ok=True)
    thresholds = json.loads((TMP / "thresholds.json").read_text())
    settle = {}
    for sym in MAJORS:
        df = pd.read_parquet(TMP / f"settle_{sym}.parquet")
        s_ns = pd.to_datetime(df["S"], utc=True).values.astype("datetime64[ns]").astype(np.int64)
        order = np.argsort(s_ns, kind="stable")
        settle[sym] = (s_ns[order], df["rate"].to_numpy(dtype=float)[order])

    idx, O, C = {}, {}, {}
    for sym in MAJORS:
        ii, o, c = load_oc(sym)
        idx[sym], O[sym], C[sym] = ii, o, c
        print(f"loaded OC {sym} [{time.time()-t_start:.0f}s]", flush=True)
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

    all_rows = []
    for sym in MAJORS:
        cache = TMP / f"fills_{sym}.parquet"
        if cache.exists():
            dfc = pd.read_parquet(cache)
            all_rows.append(dfc)
            print(f"{sym}: loaded cache {len(dfc)} fills", flush=True)
            continue
        H, L = load_hl(sym, base_idx)
        Oa, Ca, La, Ha = O[sym], C[sym], L, H
        others = [s for s in MAJORS if s != sym]
        sns, srate = settle[sym]
        rows = []
        n_bar = 0
        for j in range(nb):
            bt = t0[j]
            if not (TRADE_START <= bt < YEAR_END):
                continue
            o1, sg = float(opens_bar[sym][j]), float(sig_bar[sym][j])
            if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                continue
            base = j * 240
            if base + 720 >= n_all:
                continue
            o2m = Oa[base + 240]
            o2 = float(o2m) if np.isfinite(o2m) else np.nan
            o4m = Oa[base + 720]
            o4 = float(o4m) if np.isfinite(o4m) else np.nan
            settle_mid = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
            mid1 = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
            mid2 = (bt + pd.Timedelta(hours=8)).hour in SETTLE_HOURS
            final = (bt + pd.Timedelta(hours=12)).hour in SETTLE_HOURS
            yi = year_of(bt)
            t_out_ns = (bt + pd.Timedelta(hours=4)).value
            pos = int(np.searchsorted(sns, t_out_ns, side="left")) - 1
            F = float(srate[pos]) if pos >= 0 else float("nan")
            key = ANCHORS[yi].date().isoformat()
            q70 = float(thresholds[key][sym]["q70"])
            q50 = float(thresholds[key][sym]["q50"])
            ext1 = should_extend(F, q70)
            ext2 = should_extend(F, q50)
            low_win = La[base + X.LIVE_A:base + X.LIVE_B + 1].astype(float)
            cmat = np.stack([C[b][base + X.LIVE_A - 1:base + X.LIVE_B].astype(float)
                             for b in others])
            oo = np.array([opens_bar[b][j] for b in others], dtype=float)
            ss = np.array([sig_bar[b][j] for b in others], dtype=float)
            nvec = X.n_vector(cmat, oo, ss)
            Ha_b = Ha[base:base + 240].astype(float)
            La_b = La[base:base + 240].astype(float)
            Ca_b = Ca[base:base + 240].astype(float)
            Oa_b = Oa[base:base + 240].astype(float)
            H2 = L2 = C2 = O2 = None
            for k in X.RUNGS:
                lv = o1 * (1 - k * sg)
                if not np.isfinite(lv) or lv <= 0:
                    continue
                ib = X.find_fill(low_win, lv)
                if ib is None:
                    continue
                f = X.LIVE_A + ib
                nf = int(nvec[ib])
                w = float(X.size_mult(nf))
                b_ret, b_x, b_how = X.outcome_base(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle_mid)
                if not np.isfinite(b_ret):
                    continue
                if b_how != "time":
                    v1 = (b_ret, b_x, b_how, False)
                    v2 = (b_ret, b_x, b_how, False)
                else:
                    if H2 is None:
                        H2 = pad_n(Ha[base + 240:base + 720].astype(float), 480)
                        L2 = pad_n(La[base + 240:base + 720].astype(float), 480)
                        C2 = pad_n(Ca[base + 240:base + 720].astype(float), 480)
                        O2 = pad_n(Oa[base + 240:base + 720].astype(float), 480)
                    e_ret, e_x, e_how = X.outcome_ext8_phase(H2, L2, C2, O2, lv, sg, o4, mid1, mid2, final)
                    if ext1:
                        if not np.isfinite(e_ret):
                            continue
                        v1 = (float(e_ret), int(e_x), e_how, True)
                    else:
                        v1 = (float(b_ret), int(b_x), b_how, False)
                    if ext2:
                        if not np.isfinite(e_ret):
                            continue
                        v2 = (float(e_ret), int(e_x), e_how, True)
                    else:
                        v2 = (float(b_ret), int(b_x), b_how, False)
                rows.append(dict(sym=sym, y=yi, k=k, f=int(f), n=int(nf), w=w,
                                 fill=float(lv), t_bar=bt, F=float(F),
                                 q70=float(q70), q50=float(q50),
                                 mid1=bool(mid1), mid2=bool(mid2), final=bool(final),
                                 settle_mid=bool(settle_mid),
                                 base_ret=float(b_ret), base_x=int(b_x), base_how=b_how,
                                 v1_ret=float(v1[0]), v1_x=int(v1[1]), v1_how=v1[2],
                                 v1_ext=bool(v1[3]),
                                 v2_ret=float(v2[0]), v2_x=int(v2[1]), v2_how=v2[2],
                                 v2_ext=bool(v2[3]),
                                 xd_base=exit_date(bt, int(b_x)),
                                 xd_v1=exit_date(bt, int(v1[1])),
                                 xd_v2=exit_date(bt, int(v2[1]))))
            n_bar += 1
            if n_bar % 2000 == 0:
                print(f"{sym}: bar {n_bar}/{nb} rows={len(rows)} [{time.time()-t_start:.0f}s]", flush=True)
        dfc = pd.DataFrame(rows)
        dfc.to_parquet(cache, index=False)
        all_rows.append(dfc)
        print(f"{sym}: bars done kept_fills={len(dfc)} [{time.time()-t_start:.0f}s]", flush=True)
        del H, L
    _stop_hb.set()
    import hashlib
    df = pd.concat(all_rows, ignore_index=True) if len(all_rows) else pd.DataFrame()
    df.to_parquet(HERE / "fills.parquet", index=False)
    chk = hashlib.sha256(np.round(df[["base_ret", "v1_ret", "v2_ret", "w", "fill"]].to_numpy(), 9).tobytes()).hexdigest()[:16] if len(df) else "empty"
    print("n_fills", len(df), "checksum", chk, flush=True)
    (TMP / "replica_fills_checksum.txt").write_text(chk)


if __name__ == "__main__":
    main()
