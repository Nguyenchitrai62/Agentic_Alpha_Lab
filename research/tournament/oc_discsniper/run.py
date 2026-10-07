"""oc_discsniper run: discount-sniper sleeve on 4 clock phases + dip replica + placebo.

PLAN.md pre-registered. One process, sequential coins/phases, float32 1m arrays.
Heavy: wrap with scripts/heavy_slot.py run.

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_discsniper \
    --min-free-gb 2.0 -- .venv/Scripts/python.exe research/tournament/oc_discsniper/run.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import discsniper as D

START = pd.Timestamp("2020-08-01", tz="UTC")
CUTOFF = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
PHASES = (0, 1, 2, 3)
SETTLE_HOURS = (0, 8, 16)
N_PLACEBO = 300
SEED = 20261006


def year_of(t0):
    for i in range(5):
        lo = ANCHORS[i]
        hi = ANCHORS[i + 1] if i < 4 else YEAR_END
        if lo <= t0 < hi:
            return i
    return None


def load_1m(sym: str, cols):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time"] + cols) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= CUTOFF)]
    idx = pd.date_range(START, CUTOFF, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    out = {}
    for c in cols:
        out[c] = m[c].to_numpy(dtype=np.float32)
    del m, parts
    return idx, out


def load_prem(sym: str, idx):
    f = Path(f"data/raw/binance_premium_20260928/{sym}_premium_1m.parquet")
    df = pd.read_parquet(f, columns=["open_time", "close"])
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df.drop_duplicates("open_time").sort_values("open_time")
    df = df[(df["open_time"] >= START) & (df["open_time"] <= CUTOFF)]
    df = df.set_index("open_time").reindex(idx)
    return df["close"].to_numpy(dtype=np.float32)


def daily_stats(recs):
    """recs: list of (exit_date_iso, contrib). Returns (S, worst, DD, ndays)."""
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
    print("loading 1m O/C for n detector ...", flush=True)
    base_idx, O_all, C_all = None, {}, {}
    for sym in MAJORS:
        idx, d = load_1m(sym, ["open", "close"])
        if base_idx is None:
            base_idx = idx
        O_all[sym] = d["open"]
        C_all[sym] = d["close"]
        print(f"  OC {sym}", flush=True)
    n_min = len(base_idx)
    # settlement mask on minute grid
    hrs = base_idx.hour.to_numpy()
    mns = base_idx.minute.to_numpy()
    settle_mask = np.isin(hrs, list(SETTLE_HOURS)) & (mns == 0)

    def minute_pos(t):
        return int((t - START).total_seconds() // 60)

    # phase bar lists + per-coin Ob/sg per phase
    phase_bars = {}   # p -> DatetimeIndex of T
    Ob, Sg = {}, {}   # (sym,p) -> arrays
    for p in PHASES:
        t0 = START + pd.Timedelta(hours=p)
        tlast = CUTOFF - pd.Timedelta(minutes=240)
        bars = pd.date_range(t0, tlast, freq="4h")
        bars = bars[(bars >= TRADE_START) & (bars < YEAR_END)]
        phase_bars[p] = bars
        for sym in MAJORS:
            pos = np.array([minute_pos(t) for t in bars])
            ob = O_all[sym][pos].astype(float)
            sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            Ob[(sym, p)], Sg[(sym, p)] = ob, sg
    print("bars per phase:", {p: len(phase_bars[p]) for p in PHASES}, flush=True)

    disc_rows = []  # per kept fill
    dip_rows = []
    trig_counts = {}  # (p, year, sym) -> K trigger bars
    elig = {}         # (p, year, sym) -> list of bar positions j (eligible)
    drop_disc = 0
    drop_dip = 0
    # placebo sums per rule/phase/year (accumulated over coins)
    placebo_sums = np.zeros((N_PLACEBO, 4, 5), dtype=float)

    for ci, sym in enumerate(MAJORS):
        print(f"coin {sym} loading H/L + premium ...", flush=True)
        _, hl = load_1m(sym, ["high", "low"])
        H_arr, L_arr = hl["high"], hl["low"]
        P = load_prem(sym, base_idx).astype(float)
        p15 = D.p15_from_close(P)
        del P
        s = pd.Series(p15)
        rm = s.rolling(D.TRAIL_WIN, min_periods=D.TRAIL_MIN).mean().to_numpy()
        rs = s.rolling(D.TRAIL_WIN, min_periods=D.TRAIL_MIN).std(ddof=1).to_numpy()
        Oa, Ca = O_all[sym], C_all[sym]
        others = [c for c in MAJORS if c != sym]
        for p in PHASES:
            bars = phase_bars[p]
            ob = Ob[(sym, p)]
            sgarr = Sg[(sym, p)]
            ob_o = {b: Ob[(b, p)] for b in others}
            sg_o = {b: Sg[(b, p)] for b in others}
            # eligible + trigger collection for placebo
            for j, T in enumerate(bars):
                o1, sg = float(ob[j]), float(sgarr[j])
                if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                    continue
                yi = year_of(T)
                if yi is None:
                    continue
                elig.setdefault((p, yi, sym), []).append(j)
            # real pass
            n_trig_cell = {}
            for j, T in enumerate(bars):
                o1, sg = float(ob[j]), float(sgarr[j])
                if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                    continue
                yi = year_of(T)
                if yi is None:
                    continue
                i = minute_pos(T)
                if i + 240 >= n_min:
                    continue
                # z via precomputed rolling (equiv. PLAN slice)
                if i < 2:
                    z = np.nan
                else:
                    cur = float(p15[i - 1]) if (i - 1) < len(p15) else np.nan
                    mu = float(rm[i - 2]) if (i - 2) < len(rm) else np.nan
                    sd = float(rs[i - 2]) if (i - 2) < len(rs) else np.nan
                    z = (cur - mu) / sd if (np.isfinite(cur) and np.isfinite(mu)
                                            and np.isfinite(sd) and sd > 0) else np.nan
                trig = bool(np.isfinite(z) and z < D.Z_THRESH)
                if trig:
                    trig_counts[(p, yi, sym)] = trig_counts.get((p, yi, sym), 0) + 1
                # ---- disc entry ----
                if trig:
                    oT = float(Oa[i])
                    if np.isfinite(oT) and oT > 0:
                        lim = oT * (1 - D.ENTRY_OFF)
                        low_win = L_arr[i + 5:i + 60].astype(float)
                        ib = D.find_fill_disc(low_win, lim)
                        if ib is not None:
                            f = 5 + ib
                            Hb = H_arr[i:i + 240].astype(float)
                            Lb = L_arr[i:i + 240].astype(float)
                            Cb = Ca[i:i + 240].astype(float)
                            Obb = Oa[i:i + 240].astype(float)
                            p15b = p15[i:i + 240].astype(float)
                            o2 = float(Oa[i + 240])
                            ret, x, how = D.outcome_disc(
                                Hb, Lb, Cb, Obb, p15b, f, float(lim), float(sg),
                                o2, i + f, i, settle_mask)
                            if np.isfinite(ret):
                                T_exit = T + pd.Timedelta(minutes=int(x))
                                xd = T_exit.date().isoformat() if int(x) < 240 else \
                                    (T + pd.Timedelta(hours=4)).date().isoformat()
                                disc_rows.append(dict(sym=sym, phase=p, y=yi, f=int(f),
                                                      z=float(z), sg=float(sg),
                                                      ret=float(ret), c=float(D.SIZE * ret),
                                                      x=int(x), how=how, xd=xd,
                                                      tfill=int(i + f),
                                                      t_bar=str(T)))
                            else:
                                drop_disc += 1
                # ---- dip replica (same bar) ----
                settle = (T + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
                o2m = Oa[i + 240]
                o2 = float(o2m) if np.isfinite(o2m) else np.nan
                low_win_d = L_arr[i + 16:i + 239].astype(float)  # 16..238
                if not np.isfinite(o1):
                    continue
                cmat = np.stack([C_all[b][i + 15:i + 238].astype(float) for b in others])
                oo = np.array([float(ob_o[b][j]) for b in others], dtype=float)
                ss = np.array([float(sg_o[b][j]) for b in others], dtype=float)
                nvec = D.dip_n_vector(cmat, oo, ss)
                Ha_b = H_arr[i:i + 240].astype(float)
                La_b = L_arr[i:i + 240].astype(float)
                Ca_b = Ca[i:i + 240].astype(float)
                Oa_b = Oa[i:i + 240].astype(float)
                for k in D.DIP_RUNGS:
                    lv = o1 * (1 - k * sg)
                    if not (np.isfinite(lv) and lv > 0):
                        continue
                    ib = D.dip_find_fill(low_win_d, lv)
                    if ib is None:
                        continue
                    f = 16 + ib
                    nf = int(nvec[ib])
                    ret, x, how = D.dip_outcome(Ha_b, La_b, Ca_b, Oa_b, f, float(lv),
                                                float(sg), o2, settle)
                    if np.isfinite(ret):
                        w = float(D.dip_size_mult(nf))
                        T_exit = T + pd.Timedelta(minutes=int(x))
                        xd = T_exit.date().isoformat() if int(x) < 240 else \
                            (T + pd.Timedelta(hours=4)).date().isoformat()
                        dip_rows.append(dict(sym=sym, phase=p, y=yi, k=float(k),
                                              f=int(f), n=int(nf), w=w,
                                              ret=float(ret), wy=float(w * ret),
                                              x=int(x), how=how, xd=xd,
                                              tfill=int(i + f), t_bar=str(T)))
                    else:
                        drop_dip += 1
            print(f"  {sym} phase {p} done", flush=True)
            # ---- placebo for this (coin, phase) ----
            bars_p = phase_bars[p]
            ob_p = Ob[(sym, p)]
            for yi in range(5):
                key = (p, yi, sym)
                K = int(trig_counts.get(key, 0))
                pool = elig.get(key, [])
                if K <= 0 or not pool:
                    continue
                pool_arr = np.array(pool, dtype=np.int64)
                for r in range(N_PLACEBO):
                    seed = SEED + r * 10007 + p * 101 + yi * 1009 + ci * 7919
                    rng = np.random.RandomState(seed % (2 ** 32 - 1))
                    Kcl = min(K, len(pool_arr))
                    sel = rng.choice(pool_arr, size=Kcl, replace=False)
                    ssum = 0.0
                    for j in sel:
                        T = bars_p[int(j)]
                        sg = float(Sg[(sym, p)][int(j)])
                        o1 = float(ob_p[int(j)])
                        if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                            continue
                        i = minute_pos(T)
                        if i + 240 >= n_min:
                            continue
                        oT = float(Oa[i])
                        if not (np.isfinite(oT) and oT > 0):
                            continue
                        lim = oT * (1 - D.ENTRY_OFF)
                        low_win = L_arr[i + 5:i + 60].astype(float)
                        ib = D.find_fill_disc(low_win, lim)
                        if ib is None:
                            continue
                        f = 5 + ib
                        Hb = H_arr[i:i + 240].astype(float)
                        Lb = L_arr[i:i + 240].astype(float)
                        Cb = Ca[i:i + 240].astype(float)
                        Obb = Oa[i:i + 240].astype(float)
                        p15b = p15[i:i + 240].astype(float)
                        o2 = float(Oa[i + 240])
                        ret, x, how = D.outcome_disc(
                            Hb, Lb, Cb, Obb, p15b, f, float(lim), float(sg),
                            o2, i + f, i, settle_mask)
                        if np.isfinite(ret):
                            ssum += float(D.SIZE * ret)
                    placebo_sums[r, p, yi] += ssum
        del H_arr, L_arr, p15, rm, rs
        print(f"coin {sym} complete", flush=True)

    disc = pd.DataFrame(disc_rows)
    dip = pd.DataFrame(dip_rows)
    # per phase-year disc stats
    per_phase, s_bar, corr_y, ov_y = {}, [], {}, {}
    for yi in range(5):
        s_ph, per_phase[yi] = [], {}
        for p in PHASES:
            sub = disc[(disc["phase"] == p) & (disc["y"] == yi)] if len(disc) else disc
            n = int(len(sub)) if len(disc) else 0
            if n:
                wv = (sub["ret"].to_numpy(float) > 0).mean()
                mean = float(sub["ret"].mean())
                recs = list(zip(sub["xd"].tolist(), sub["c"].tolist()))
                S, Wd, DD, nd = daily_stats(recs)
            else:
                wv, mean, S, Wd, DD, nd = 0.0, 0.0, 0.0, 0.0, 0.0, 0
            per_phase[yi][p] = {"n": n, "mean": mean, "win_rate": float(wv),
                                 "sum": S, "worst_day": Wd, "max_dd": DD, "ndays": nd}
            s_ph.append(S)
        s_bar.append(float(np.mean(s_ph)))
    # dip daily maps per (phase,date) for correlation; disc too
    disc_map, dip_map = {}, {}
    if len(disc):
        for (p, d), g in disc.groupby(["phase", "xd"]):
            disc_map[(int(p), d)] = float(g["c"].sum())
    if len(dip):
        for (p, d), g in dip.groupby(["phase", "xd"]):
            dip_map[(int(p), d)] = float(g["wy"].sum())
    all_dates = sorted(pd.date_range("2021-09-24", "2026-09-23", freq="D").date.astype(str))
    # overall correlation pooled over (phase,date)
    xs, ys = [], []
    for p in PHASES:
        for d in all_dates:
            xs.append(disc_map.get((p, d), 0.0))
            ys.append(dip_map.get((p, d), 0.0))
    xs, ys = np.array(xs, float), np.array(ys, float)
    if np.std(xs, ddof=1) > 0 and np.std(ys, ddof=1) > 0:
        corr_all = float(np.corrcoef(xs, ys)[0, 1])
    else:
        corr_all = float("nan")
    for yi in range(5):
        lo, hi = (ANCHORS[yi].date().isoformat(),
                  (ANCHORS[yi + 1].date().isoformat() if yi < 4 else YEAR_END.date().isoformat()))
        xp, yp = [], []
        for p in PHASES:
            for d in all_dates:
                if lo <= d < hi:
                    xp.append(disc_map.get((p, d), 0.0))
                    yp.append(dip_map.get((p, d), 0.0))
        xp, yp = np.array(xp, float), np.array(yp, float)
        if len(xp) and np.std(xp, ddof=1) > 0 and np.std(yp, ddof=1) > 0:
            corr_y[yi] = float(np.corrcoef(xp, yp)[0, 1])
        else:
            corr_y[yi] = float("nan")
    # overlap: disc fills within 240 min of a same-coin dip fill
    dip_by_coin = {}
    if len(dip):
        for sym, g in dip.groupby("sym"):
            dip_by_coin[sym] = np.sort(g["tfill"].to_numpy(np.int64))
    ov_cell = {}
    for yi in range(5):
        for p in PHASES:
            sub = disc[(disc["phase"] == p) & (disc["y"] == yi)] if len(disc) else disc[:0]
            n = len(sub)
            if n == 0:
                ov_cell[(p, yi)] = {"n": 0, "share": 0.0}
                continue
            hit = 0
            for sym, g in sub.groupby("sym"):
                arr = dip_by_coin.get(sym, np.array([], dtype=np.int64))
                tf = g["tfill"].to_numpy(np.int64)
                if len(arr) == 0:
                    continue
                pos = np.searchsorted(arr, tf)
                for t, pp in zip(tf, pos):
                    ok = False
                    if pp < len(arr) and abs(int(arr[pp]) - int(t)) <= 240:
                        ok = True
                    if pp > 0 and abs(int(arr[pp - 1]) - int(t)) <= 240:
                        ok = True
                    if ok:
                        hit += 1
            ov_cell[(p, yi)] = {"n": int(n), "share": float(hit / n)}
    if len(disc):
        hit = sum(int(round(ov_cell[(p, yi)]["share"] * ov_cell[(p, yi)]["n"])) for p in PHASES for yi in range(5))
        ov_all = float(hit / len(disc))
    else:
        ov_all = 0.0
    # real 5y total (sum of yearly 4-phase means) + placebo distribution
    R_real = float(sum(s_bar))
    R_pla = []
    for r in range(N_PLACEBO):
        sb = [float(np.mean([placebo_sums[r, p, yi] for p in PHASES])) for yi in range(5)]
        R_pla.append(float(sum(sb)))
    R_pla = np.array(R_pla, float)
    pct = float((R_pla <= R_real).mean() * 100) if len(R_pla) else float("nan")
    n_pos = sum(1 for s in s_bar if s > 0)
    promising = bool(n_pos >= 4 and np.isfinite(pct) and pct >= 95
                     and np.isfinite(corr_all) and corr_all < 0.5)
    chk = hashlib.sha256(np.round(
        np.column_stack([disc["ret"].to_numpy(float), disc["c"].to_numpy(float)]) if len(disc)
        else np.zeros((0, 2)), 9).tobytes()).hexdigest()[:16] if len(disc) else "empty"
    out = {
        "config": {"coins": list(MAJORS), "phases": list(PHASES),
                   "bars": "open in [2021-09-24, 2026-09-24), 4h from 2020-08-01 +0/1/2/3h",
                   "trigger": "z=(p15[cur]-mean1440)/std1440 < -2, p15=mean(prem1m close,15), trailing 1440 overlapping p15 ending 1min before cur, min 1200, strictly <T",
                   "entry": "limit O(T)*(1-0.001), live offsets 5..59, strict low<trade-through, maker 0.0002",
                   "exits": "sl=px*(1-4sg) close5 (m+1)%5==0 -> next open taker; premium p15>=0 -> next open maker; else next-bar open taker; stop-first ties",
                   "funding": "longs pay 0.0001 per 00/08/16UTC settlement in (Tfill,Texit]",
                   "size": "0.25 x equity per coin; contribution c=0.25*y; daily sums by exit date UTC; maxDD of cumulative daily path from 0",
                   "dip": "D0(TP1sg,sl4sg close5,bl8sg,timeout)+B1 w=1/(1+n), R2 depths, live 16..238, v399-exact n",
                   "placebo": "300 rules seed 20261006, per (phase,year,coin) K=real trigger count, random bars w/o replacement from valid sigma/O bars, identical exits",
                   "note": "bars needing O(T+240) past CUTOFF skipped; NaN exits dropped"},
        "n_disc": int(len(disc)), "n_dip": int(len(dip)),
        "drop_disc_nan_exit": int(drop_disc), "drop_dip_nan_exit": int(drop_dip),
        "ledger_checksum_disc": chk,
        "trig_counts": {f"{p}/{ANCHORS[y].date()}/{s}": int(v) for (p, y, s), v in trig_counts.items()},
        "per_phase_year": {str(ANCHORS[y].date()): {str(p): per_phase[y][p] for p in PHASES} for y in range(5)},
        "s_bar_year": [float(s) for s in s_bar],
        "years_sum_pos": int(n_pos),
        "corr_daily_overall": corr_all,
        "corr_daily_year": {str(ANCHORS[y].date()): corr_y[y] for y in range(5)},
        "overlap_share_overall": ov_all,
        "overlap_cell": {f"{p}/{ANCHORS[y].date()}": ov_cell[(p, y)] for p in PHASES for y in range(5)},
        "R_real_5y": R_real,
        "placebo_R": [float(v) for v in R_pla],
        "placebo_percentile": pct,
        "decision": {"years_sum_pos": int(n_pos), "placebo_pct": pct,
                     "corr": corr_all, "promising": promising},
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    disc.to_parquet(HERE / "fills_disc.parquet", index=False) if len(disc) else None
    dip.to_parquet(HERE / "fills_dip.parquet", index=False) if len(dip) else None
    print("n_disc", len(disc), "n_dip", len(dip), "R", round(R_real, 4),
          "pct", round(pct, 2), "corr", corr_all, "pos_years", n_pos,
          "promising", promising, flush=True)


if __name__ == "__main__":
    main()
