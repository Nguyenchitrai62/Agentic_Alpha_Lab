"""v184 blind audit Part A replication.

Blind rule: does NOT read research v184 files, result jsons, nor hourly
ladder sources, until replication.json is saved. Independent implementation
from OPENCODE_V184_AUDIT.md plus the v183 audit base only.
May import engine_real for v154_books/context/constants and v135 for W=60
execution (like prior audits).

A: v183 4h ladder plus an hourly ladder. Per 4h holding bar T and hour
h = 0..3: base = 1m open of minute 60h of T; sigma_1h = std of 1h
open-to-open returns (hourly opens = 1m opens at minutes 0/60/120/180 of
every holding bar, in time order) over the 1440 hours ending with the last
hour of the PREVIOUS holding bar (min 480). Rungs k 2.5/3/3.5/4:
L = base (1 - k sigma_1h); live minutes 16..57 for h = 0, else
60h+4 .. 60h+57; fill at L on 1m low < L (maker);
TP = L (1 + sigma_1h), exit at TP in the first minute m > fill and
< 60(h+1) with high > TP (maker both sides); else exit at the open of
minute 60(h+1) (h = 3: next 4h open, pays funding at T+4h) by taker with
slippage max(2 bps, 0.25 (high-low)/open of that minute). One shared
budget with the 4h ladder: all fills of the bar in
(minute, 4h ladder before hourly, rung, asset) order, taken iff
(open rungs at that minute + 1) * rn <= 1/6.
Vol leg: unbudgeted sum of both ladders shifted 2 bars. Normal and stress
rows: monthly, 4h DD, 1m DD, counts.

Frozen blind assumptions (documented before running):
  C1 Grid G=date_range(2020-02-01 UTC, last books bar, freq 4h); t=G[i],
     T=G[i]+4h, T2=G[i]+8h. Anchors=v92.ANCHORS (5). Live books bars in
     [START, END) from v110. No ML gate (like v183).
  C2 4h sigma(t)=std of 4h open-to-open pct changes, 360 bars ending at t,
     min 120, via opens.pct_change().rolling(360,min120).std() at G.
     Finite>0 required else no 4h fill. TP_4h=L*(1+sigma).
  C3 4h ladder L_k=open(T)*(1-k*sigma(t)), k in (2.5,3,3.5,4). Fill f=first
     m in 16..238 with 1m low<L strict. Entry=L exactly. TP exit first
     m>f with high>TP strict else 240 (next-open). TP net normal
     TP/L-1-0.0002-0.0002, stress -0.0004-0.0004, no funding/extra.
     Next-open legs: exit=o2*(1-s_out)/L-1-MAKER-TAKER-funding(T2);
     stress extra 0.0005 deducted as fee (v179 style). s_out from 1m
     minute 0 of T+4h else 0.0002.
  C4 sigma_1h per asset: hourly opens H[j,h]=1m open at offset 60h of
     holding bar j (within-bar ffilled), flattened k=j*4+h in time order;
     rets=pct_change; sigma_1h[i]=rolling(1440,min480).std() at
     k_prev=(i-1)*4+3 (last hour of PREVIOUS holding bar). Strictly before
     T. Finite>0 required else no hourly fills for that bar/asset.
  C5 Hourly base[i,h,a]=1m open at 60h of bar i (within-bar ffilled).
     L=base*(1-k*sigma_1h[i,a]). Live m in 16..57 for h=0 else
     60h+4..60h+57. Fill first low<L strict. Entry=L.
  C6 Hourly TP=L*(1+sigma_1h). Exit first m>fill with m<60(h+1) and
     high>TP strict (maker both sides, no funding). Else timeout at
     e=60(h+1) (h=3: 240=next 4h open). Timeout exit price: h=0..2 1m open
     at 60(h+1) of same bar; h=3 4h open(T+4h)=o2. Slippage
     s_out=max(0.0002,0.25*(H-L)/O of exit minute) else 0.0002.
     Timeout normal exit*(1-s_out)/L-1-0.0002-0.0005-fund(h3 only);
     stress -0.0004-0.0007-0.0005-fund(h3 only), extra as fee. TP legs as
     C3 (no funding/extra).
  C7 Shared budget per bar: candidates = 4h fills + hourly fills sorted by
     (fill minute, 4h before hourly, rung index, asset col BNB..XRP).
     e = TP minute or timeout minute (4h non-TP 240; hourly non-TP
     60(h+1), h3 non-TP 240). Take iff (count taken with e>f_cur + 1)
     * rn <= 1/6, rn=s*g*0.25/4/1.657. Uses only past highs (exits with
     e<=f_cur already closed).
  C8 Vol uses UNCAPPED sleeve (no budget) = RUNG_W*(sum 4h rets + sum
     hourly rets) per cost row, unit=sleeve/1.657, realized=
     0.8*sum books[i-2]*ret1+0.6*carry[i-1]+unit[i-2], vol=rolling
     std360 min120*sqrt(2190), s=min(0.25/vol,2) else 1.
  C9 Books loop mirrors engine_real FULL with W=60 execution for normal,
     stressed exec (maker 0.0004/taker 0.0007+5bps taker slippage) for
     stress; governor 20% 2-bar lag on combined equity; budget 0.95
     carry-first; min-notional 10k; funding/carry/carry_cost as
     engine_real.
  C10 1m mark taken rungs only: 4h as v183 (TP f..e-1 at close/L-1 locked
     at TP/L-1 gross after; non-TP f..239 at close/L-1). Hourly TP
     f..e-1 at close/L-1 locked at TP/L-1 gross for m>=e; hourly timeout
     f..e-1 at close/L-1 locked at exit_open/L-1 gross for m>=e.
     Minute eq=prev*(1+Rb+Rs-exec+min(funding,0)); fees/funding stay in
     bar-close payoff. DD=max over live span; worst bar=argmin net live.
  C11 1m grids: drop dup open_time keep last, sort, reindex full minute
     grid, within-bar forward-fill only for O/H/L/C; volume missing->0.
     Fill test on ffilled low; TP scan on ffilled high; s_out/exit opens
     on ffilled O/H/L.
"""

from __future__ import annotations

import glob
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[4]
ROUND2 = ROOT / "research" / "parallel" / "rounds" / "parallel-20260906-r2"
OUT = HERE / "replication.json"

MAJORS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
RUNGS = (2.5, 3.0, 3.5, 4.0)
GRID_START = pd.Timestamp("2020-02-01 00:00:00+00:00")
SIZE = 0.25
S_REF = 1.657
N_MAX = 0.05 / 0.30
TARGET = 0.25
CAP = 2.0
W_EXEC = 60
MAKER, TAKER = 0.0002, 0.0005
MAKER_S, TAKER_S, EXTRA_S = 0.0004, 0.0007, 0.0005
EPS = 1e-12
RUNG_W = 0.25 / 4.0
INF_EXIT = 999
H_WIN = 1440
H_MIN = 480


def _load_engine_real():
    spec = importlib.util.spec_from_file_location(
        "v184_audit_engine_real", ROUND2 / "engine_real" / "engine_real.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ffill_rows(a: np.ndarray) -> np.ndarray:
    out = a.copy()
    for i in range(out.shape[0]):
        last = np.nan
        row = out[i]
        for k in range(row.shape[0]):
            if np.isnan(row[k]):
                row[k] = last
            else:
                last = row[k]
    return out


def _bar_stats_W(m_1m: pd.DataFrame, W: int) -> pd.DataFrame:
    T = m_1m["open_time"].dt.floor("4h")
    off = ((m_1m["open_time"] - T).dt.total_seconds() // 60).astype(int)
    p0 = m_1m[off == 0].set_index(T[off == 0])["open"]
    wmask = (off >= 2) & (off <= W - 1)
    lo = m_1m[wmask].groupby(T[wmask])["low"].min()
    hi = m_1m[wmask].groupby(T[wmask])["high"].max()
    pW = m_1m[off == W].set_index(T[off == W])["open"]
    return pd.DataFrame({"p0": p0, "lo": lo, "hi": hi, "pW": pW})


def _exec_arrays(bidx, cols, v135, W, maker_fee, taker_fee, taker_extra):
    n = len(bidx)
    fee_b = np.zeros((n, len(cols)))
    rel_b = np.zeros((n, len(cols)))
    fee_s = np.zeros((n, len(cols)))
    rel_s = np.zeros((n, len(cols)))
    D = 0.001
    for j, s in enumerate(cols):
        m = v135.load_1m(s)
        st = _bar_stats_W(m, W).reindex(bidx + pd.Timedelta(hours=4)).set_axis(bidx)
        p0 = st["p0"].to_numpy(dtype=float)
        lo = st["lo"].to_numpy(dtype=float)
        hi = st["hi"].to_numpy(dtype=float)
        pW = st["pW"].to_numpy(dtype=float)
        have = ~np.isnan(p0)
        pWf = np.where(np.isnan(pW), p0, pW)
        with np.errstate(invalid="ignore", divide="ignore"):
            mv = np.where(have, pWf / np.where(have, p0, 1.0) - 1, 0.0)
        mv = np.nan_to_num(mv, nan=0.0, posinf=0.0, neginf=0.0)
        fb = have & (lo < p0 * (1 - D))
        fs = have & (hi > p0 * (1 + D))
        fee_b[:, j] = np.where(fb, maker_fee, taker_fee)
        rel_b[:, j] = np.where(fb, -D, mv + 0.0002 + np.where(have & (~fb), taker_extra, 0.0))
        fee_s[:, j] = np.where(fs, maker_fee, taker_fee)
        rel_s[:, j] = np.where(fs, D, mv - 0.0002 - np.where(have & (~fs), taker_extra, 0.0))
    return fee_b, rel_b, fee_s, rel_s


def _load_1m_cubes(sym, mgrid, n):
    if sym == "BTCUSDT":
        files = sorted(glob.glob(str(ROOT / "data/raw/btc_intraday_20260924/klines_1m_20*.parquet")))
    else:
        files = sorted(glob.glob(str(ROOT / f"data/raw/majors_intraday_20260924/{sym}_1m_20*.parquet")))
    assert files, f"no 1m files for {sym}"
    cols = ["open_time", "open", "high", "low", "close", "volume"]
    parts = [pd.read_parquet(f, columns=cols) for f in files]
    d = pd.concat(parts, ignore_index=True)
    d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
    d = d.sort_values("open_time").drop_duplicates("open_time", keep="last").set_index("open_time")
    op = d["open"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
    hi = d["high"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
    lo = d["low"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
    cl = d["close"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
    del d, parts
    return _ffill_rows(op), _ffill_rows(hi), _ffill_rows(lo), _ffill_rows(cl)


def main():
    er = _load_engine_real()
    v110 = er.v144.v110
    v135 = er.v144.v135
    START, END = v110.START, v110.END
    print("live", START, "->", END, flush=True)

    books, opens_full = er.v154_books()
    books = books.sort_index()
    opens_full = opens_full.sort_index()
    bidx = books.index
    bcols = list(books.columns)
    last_books = bidx.max()
    G = pd.date_range(GRID_START, last_books, freq="4h", tz="UTC")
    n = len(G)
    T_all = G + pd.Timedelta(hours=4)
    T2_all = G + pd.Timedelta(hours=8)
    print(f"grid {n} bars {G.min()} -> {G.max()}", flush=True)

    mj = len(MAJORS)
    nr = len(RUNGS)

    opens_G = pd.DataFrame({
        s: pd.Series(
            pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{s}_4h.parquet")["open"].to_numpy(dtype=float),
            index=pd.to_datetime(
                pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{s}_4h.parquet")["open_time"],
                utc=True)).sort_index().pipe(lambda o: o[~o.index.duplicated(keep="last")])
        for s in MAJORS
    }).reindex(G)
    o1 = opens_G.shift(-1).to_numpy(dtype=float)
    o2 = opens_G.shift(-2).to_numpy(dtype=float)
    sig4 = opens_G.pct_change().rolling(360, min_periods=120).std().to_numpy(dtype=float)
    fund = np.column_stack([
        er.funding_at_bar_open(s, G).shift(-2).fillna(0.0).to_numpy(dtype=float)
        for s in MAJORS])

    n_min = n * 240
    mgrid = pd.date_range(T_all.min(), periods=n_min, freq="1min", tz="UTC")
    MO = np.arange(16, 239)

    print("loading 1m cubes", flush=True)
    OP, HI, LO, CL = {}, {}, {}, {}
    for s in MAJORS:
        op, hi, lo, cl = _load_1m_cubes(s, mgrid, n)
        OP[s], HI[s], LO[s], CL[s] = op, hi, lo, cl
        print(f"{s} cubes ready", flush=True)
    op4 = np.stack([OP[s] for s in MAJORS], axis=2)
    hi4 = np.stack([HI[s] for s in MAJORS], axis=2)
    lo4 = np.stack([LO[s] for s in MAJORS], axis=2)
    cl4 = np.stack([CL[s] for s in MAJORS], axis=2)

    s_out_M = np.full((n, mj), 0.0002)
    for a in range(mj):
        op, hi, lo = op4[:, :, a], hi4[:, :, a], lo4[:, :, a]
        for i in range(n - 1):
            o0, h0, l0 = op[i + 1, 0], hi[i + 1, 0], lo[i + 1, 0]
            if np.isfinite(o0) and o0 > 0 and np.isfinite(h0) and np.isfinite(l0) and h0 >= l0:
                xr = (h0 - l0) / o0
                if np.isfinite(xr):
                    s_out_M[i, a] = max(0.0002, 0.25 * xr)
    s_out_M[n - 1, :] = 0.0002

    # ---- 4h ladder (v183 base) ----
    f4 = np.full((n, mj, nr), -1, dtype=int)
    e4 = np.full((n, mj, nr), INF_EXIT, dtype=int)
    L4 = np.full((n, mj, nr), np.nan)
    r4n = np.zeros((n, mj, nr))
    r4s = np.zeros((n, mj, nr))
    for a in range(mj):
        lo = lo4[:, :, a]
        hi = hi4[:, :, a]
        for ri, kk in enumerate(RUNGS):
            with np.errstate(invalid="ignore", divide="ignore"):
                L = o1[:, a] * (1 - kk * sig4[:, a])
            valid = (np.isfinite(sig4[:, a]) & (sig4[:, a] > 0) & np.isfinite(o1[:, a])
                     & (o1[:, a] > 0) & np.isfinite(L) & (L > 0))
            with np.errstate(invalid="ignore"):
                hit = valid[:, None] & np.isfinite(lo[:, MO]) & (lo[:, MO] < L[:, None])
            has = hit.any(axis=1)
            first = hit.argmax(axis=1)
            f = np.where(has, MO[first], -1)
            ok = has & valid & np.isfinite(o2[:, a]) & (o2[:, a] > 0) & (np.arange(n) + 1 < n)
            for i in np.flatnonzero(ok):
                fi = int(f[i])
                Li = float(L[i])
                TP = Li * (1 + float(sig4[i, a]))
                m_found = INF_EXIT
                hrow = hi[i]
                for m in range(fi + 1, 240):
                    hm = hrow[m]
                    if np.isfinite(hm) and np.isfinite(TP) and hm > TP:
                        m_found = m
                        break
                f4[i, a, ri] = fi
                L4[i, a, ri] = Li
                if m_found != INF_EXIT:
                    e4[i, a, ri] = m_found
                    r4n[i, a, ri] = TP / Li - 1 - MAKER - MAKER
                    r4s[i, a, ri] = TP / Li - 1 - MAKER_S - MAKER_S
                else:
                    e4[i, a, ri] = INF_EXIT
                    exn = o2[i, a] * (1 - s_out_M[i, a])
                    r4n[i, a, ri] = exn / Li - 1 - MAKER - TAKER - fund[i, a]
                    r4s[i, a, ri] = exn / Li - 1 - MAKER_S - TAKER_S - EXTRA_S - fund[i, a]
    fills4 = int((f4 >= 0).sum())
    tp4 = int(((e4 != INF_EXIT) & (f4 >= 0)).sum())
    print(f"4h fills={fills4} tp={tp4}", flush=True)

    # ---- hourly sigma_1h per asset (strictly before T) ----
    sig1h = np.full((n, mj), np.nan)
    for a, s in enumerate(MAJORS):
        op = op4[:, :, a]
        Hoff = np.stack([op[:, 0], op[:, 60], op[:, 120], op[:, 180]], axis=1)
        flat = Hoff.reshape(n * 4)
        ser = pd.Series(flat)
        rets = ser.pct_change()
        roll = rets.rolling(H_WIN, min_periods=H_MIN).std().to_numpy(dtype=float)
        for i in range(n):
            if i - 1 < 0:
                continue
            k_prev = (i - 1) * 4 + 3
            v = roll[k_prev] if k_prev < len(roll) else np.nan
            sig1h[i, a] = v
    finite_sig = np.isfinite(sig1h) & (sig1h > 0)
    print(f"sigma_1h finite frac={float(finite_sig.mean()):.4f}", flush=True)

    # ---- hourly ladder ----
    # fh[hour, ...]: shape (n, mj, 4 hours, nr)
    nh = 4
    fh = np.full((n, mj, nh, nr), -1, dtype=int)
    eh = np.full((n, mj, nh, nr), 240, dtype=int)
    Lh = np.full((n, mj, nh, nr), np.nan)
    rh_n = np.zeros((n, mj, nh, nr))
    rh_s = np.zeros((n, mj, nh, nr))
    tph = np.zeros((n, mj, nh, nr), dtype=bool)
    for a in range(mj):
        op = op4[:, :, a]
        hi = hi4[:, :, a]
        lo = lo4[:, :, a]
        for h in range(nh):
            base = op[:, 60 * h]
            if h == 0:
                live = np.arange(16, 58)
            else:
                live = np.arange(60 * h + 4, 60 * h + 58)
            e_timeout = 60 * (h + 1)
            for ri, kk in enumerate(RUNGS):
                with np.errstate(invalid="ignore", divide="ignore"):
                    L = base * (1 - kk * sig1h[:, a])
                valid = (np.isfinite(sig1h[:, a]) & (sig1h[:, a] > 0)
                         & np.isfinite(base) & (base > 0)
                         & np.isfinite(L) & (L > 0))
                with np.errstate(invalid="ignore"):
                    hit = valid[:, None] & np.isfinite(lo[:, live]) & (lo[:, live] < L[:, None])
                has = hit.any(axis=1)
                first = hit.argmax(axis=1)
                f = np.where(has, live[first], -1)
                if h == 3:
                    ok_exit = np.isfinite(o2[:, a]) & (o2[:, a] > 0) & (np.arange(n) + 1 < n)
                else:
                    eo = op[:, e_timeout]
                    eh_H = hi[:, e_timeout]
                    eh_L = lo[:, e_timeout]
                    ok_exit = np.isfinite(eo) & (eo > 0)
                ok = has & valid & ok_exit
                idx_ok = np.flatnonzero(ok)
                for i in idx_ok:
                    fi = int(f[i])
                    Li = float(L[i])
                    s1 = float(sig1h[i, a])
                    TP = Li * (1 + s1)
                    m_found = -1
                    hrow = hi[i]
                    for m in range(fi + 1, e_timeout):
                        hm = hrow[m]
                        if np.isfinite(hm) and np.isfinite(TP) and hm > TP:
                            m_found = m
                            break
                    fh[i, a, h, ri] = fi
                    Lh[i, a, h, ri] = Li
                    if m_found >= 0:
                        eh[i, a, h, ri] = m_found
                        tph[i, a, h, ri] = True
                        rh_n[i, a, h, ri] = TP / Li - 1 - MAKER - MAKER
                        rh_s[i, a, h, ri] = TP / Li - 1 - MAKER_S - MAKER_S
                    else:
                        eh[i, a, h, ri] = e_timeout
                        tph[i, a, h, ri] = False
                        if h == 3:
                            eo = float(o2[i, a])
                            h0, l0, o0 = hi[i + 1, 0], lo[i + 1, 0], op[i + 1, 0]
                            if np.isfinite(o0) and o0 > 0 and np.isfinite(h0) and np.isfinite(l0) and h0 >= l0:
                                xr = (h0 - l0) / o0
                                sout = max(0.0002, 0.25 * xr) if np.isfinite(xr) else 0.0002
                            else:
                                sout = 0.0002
                            fd = float(fund[i, a])
                        else:
                            eo = float(op[i, e_timeout])
                            h0, l0 = float(hi[i, e_timeout]), float(lo[i, e_timeout])
                            if np.isfinite(eo) and eo > 0 and np.isfinite(h0) and np.isfinite(l0) and h0 >= l0:
                                xr = (h0 - l0) / eo
                                sout = max(0.0002, 0.25 * xr) if np.isfinite(xr) else 0.0002
                            else:
                                sout = 0.0002
                                eo = np.nan
                            fd = 0.0
                        if not (np.isfinite(eo) and eo > 0):
                            fh[i, a, h, ri] = -1
                            Lh[i, a, h, ri] = np.nan
                            eh[i, a, h, ri] = e_timeout
                            rh_n[i, a, h, ri] = 0.0
                            rh_s[i, a, h, ri] = 0.0
                            continue
                        rh_n[i, a, h, ri] = eo * (1 - sout) / Li - 1 - MAKER - TAKER - fd
                        rh_s[i, a, h, ri] = eo * (1 - sout) / Li - 1 - MAKER_S - TAKER_S - EXTRA_S - fd
    fillsh = int((fh >= 0).sum())
    tph_n = int((tph & (fh >= 0)).sum())
    print(f"hourly fills={fillsh} tp={tph_n}", flush=True)

    sleeve_unc_n = RUNG_W * ((r4n * (f4 >= 0)).sum(axis=(1, 2)) + (rh_n * (fh >= 0)).sum(axis=(1, 2, 3)))
    sleeve_unc_s = RUNG_W * ((r4s * (f4 >= 0)).sum(axis=(1, 2)) + (rh_s * (fh >= 0)).sum(axis=(1, 2, 3)))
    pos = G.get_indexer(bidx)
    assert (pos >= 0).all()
    unit_G_n = sleeve_unc_n / S_REF
    unit_G_s = sleeve_unc_s / S_REF
    unit_books_n = pd.Series(unit_G_n[pos], index=bidx)
    unit_books_s = pd.Series(unit_G_s[pos], index=bidx)

    ctx = er.context(books, opens_full)
    o_df = ctx["opens"].reindex(bidx)[bcols]
    r_next, _, _, fund_b = ctx["mkt"]
    carry_arr, expo_arr = ctx["carry_real"]
    B = books.to_numpy(dtype=float)
    nB = len(bidx)
    live = np.asarray((bidx >= START) & (bidx < END))
    with np.errstate(invalid="ignore", divide="ignore"):
        ret1 = o_df / o_df.shift(1) - 1
    carry_s = pd.Series(carry_arr, index=bidx)

    def vol_s_from_unit(unit_s):
        realized = (0.8 * (books.shift(2) * ret1).sum(axis=1)
                    + 0.6 * carry_s.shift(1) + unit_s.shift(2))
        vol = realized.rolling(360, min_periods=120).std() * np.sqrt(2190)
        v = vol.to_numpy(dtype=float)
        s_arr = np.where(np.isnan(v), 1.0, np.minimum(TARGET / np.where(np.isnan(v), 1.0, v), CAP))
        return np.where(~np.isfinite(s_arr), 1.0, s_arr)

    s_n = vol_s_from_unit(unit_books_n)
    s_s = vol_s_from_unit(unit_books_s)
    fee_b, rel_b, fee_s_, rel_s_ = _exec_arrays(bidx, bcols, v135, W_EXEC, MAKER, TAKER, 0.0)
    fee_b_s, rel_b_s, fee_s_s, rel_s_s = _exec_arrays(
        bidx, bcols, v135, W_EXEC, MAKER_S, TAKER_S, EXTRA_S)
    mins = np.array([er.MIN_NOTIONAL.get(c, 5.0) for c in bcols])
    o1_books = o_df.shift(-1).to_numpy(dtype=float)
    close_books = cl4[pos]
    f4b = f4[pos]
    e4b = e4[pos]
    L4b = L4[pos]
    r4b_n = r4n[pos]
    r4b_s = r4s[pos]
    fhb = fh[pos]
    ehb = eh[pos]
    Lhb = Lh[pos]
    rhb_n = rh_n[pos]
    rhb_s = rh_s[pos]
    tphb = tph[pos]
    sig1h_b = sig1h[pos]
    sig4_b = sig4[pos]

    def run_shared(r4b, rhb, s_in, fee_b_in, rel_b_in, fee_s_in, rel_s_in):
        net = np.zeros(nB)
        turn = np.zeros(nB)
        g = np.ones(nB)
        eq = np.ones(nB)
        eq_min = np.zeros(nB)
        taken_total, canc_total, tp_taken = 0, 0, 0
        tk4, tkh = 0, 0
        prev_w = np.zeros(len(bcols))
        prev_c = 0.0
        for i in range(nB):
            if i >= 2:
                jj = i - 2
                peak = eq[max(0, jj - 90 * 6 + 1): jj + 1].max()
                g[i] = float(np.clip((0.20 - (1 - eq[jj] / peak)) / 0.10, 0.0, 1.0))
            if live[i]:
                w = 0.8 * s_in[i] * B[i] * g[i]
                c = 0.6 * s_in[i] * g[i]
            else:
                w = np.zeros(len(bcols))
                c = 0.0
            ex = expo_arr[i]
            tot = c * ex + np.abs(w).sum() / er.MARGIN
            if tot > er.BUFFER:
                c_allow = (er.BUFFER - np.abs(w).sum() / er.MARGIN) / max(ex, 1e-9)
                c = min(c, max(0.0, c_allow))
            if np.abs(w).sum() / er.MARGIN > er.BUFFER:
                w = w * er.BUFFER * er.MARGIN / np.abs(w).sum()
            eq_usdt = er.ACCOUNT_USDT * (eq[i - 1] if i else 1.0)
            small = (np.abs(w - prev_w) * eq_usdt < mins) & (w != 0)
            w = np.where(small, prev_w, w)
            dw = w - prev_w
            buy = dw > 0
            ex_c = float(np.sum(np.abs(dw) * np.where(buy, fee_b_in[i], fee_s_in[i])
                                + dw * np.where(buy, rel_b_in[i], rel_s_in[i])))
            gross = float(np.sum(w * r_next[i]))
            fundp = float(-np.sum(w * fund_b[i]))
            carry_p = float(c * carry_arr[i])
            dc = c - prev_c
            carry_c = float(abs(dc) / er.CARRY_CAPITAL * ex * (er.SPOT_FEE + er.PERP_TAKER))
            sleeve_pnl = 0.0
            taken4, takenh = [], []
            if live[i]:
                rn = float(s_in[i] * g[i] * SIZE / nr / S_REF)
                cands = []
                for a in range(mj):
                    for ri in range(nr):
                        f = int(f4b[i, a, ri])
                        if f >= 0:
                            cands.append((f, 0, ri, a, 0))
                for a in range(mj):
                    for h in range(nh):
                        for ri in range(nr):
                            f = int(fhb[i, a, h, ri])
                            if f >= 0:
                                cands.append((f, 1, ri, a, h))
                cands.sort()
                taken_exits = []
                for f, lad, ri, a, h in cands:
                    if lad == 0:
                        e = int(e4b[i, a, ri])
                    else:
                        e = int(ehb[i, a, h, ri])
                    open_n = sum(1 for ee in taken_exits if ee > f)
                    if (open_n + 1) * rn <= N_MAX + EPS:
                        taken_exits.append(e)
                        if lad == 0:
                            taken4.append((f, ri, a, e))
                            sleeve_pnl += rn * float(r4b[i, a, ri])
                        else:
                            takenh.append((f, ri, a, h, e))
                            sleeve_pnl += rn * float(rhb[i, a, h, ri])
                    else:
                        canc_total += 1
                taken_total += len(taken4) + len(takenh)
                tk4 += len(taken4)
                tkh += len(takenh)
                tp_taken += (sum(1 for (_, _, _, e) in taken4 if e != INF_EXIT)
                             + sum(1 for (_, _, _, _, e) in takenh
                                   if e < (60 * (takenh[0][3] + 1) if takenh else 0) or True))
                # count TP hourly via flag below (recompute exactly)
                tp_taken -= (sum(1 for (_, _, _, e) in taken4 if e != INF_EXIT)
                             + sum(1 for (_, _, _, _, e) in takenh
                                   if True))
                # exact TP counts
                tp4c = 0
                for (_, ri, a, e) in taken4:
                    if e != INF_EXIT:
                        tp4c += 1
                tphc = 0
                for (_, ri, a, h, e) in takenh:
                    # TP iff flagged and exit before timeout
                    if bool(tphb[i, a, h, ri]) and e < 60 * (h + 1):
                        tphc += 1
                tp_taken += tp4c + tphc
            ni = gross - ex_c + fundp + carry_p - carry_c + sleeve_pnl
            net[i] = ni
            turn[i] = float(np.abs(dw).sum())
            eq[i] = (eq[i - 1] if i else 1.0) * (1 + ni)
            if live[i]:
                Cm = close_books[i].astype(float)
                with np.errstate(invalid="ignore", divide="ignore"):
                    path2 = np.zeros(240)
                    for a in range(mj):
                        base = o1_books[i, a]
                        if np.isfinite(base) and base > 0:
                            clv = Cm[:, a]
                            vv = np.isfinite(clv)
                            path2[vv] += w[a] * (clv[vv] / base - 1)
                    q = float(s_in[i] * g[i] * SIZE / nr / S_REF)
                    marr = np.arange(240)
                    for f, ri, a, e in taken4:
                        L = float(L4b[i, a, ri])
                        if not (np.isfinite(L) and L > 0) or q == 0:
                            continue
                        clv = Cm[:, a]
                        if e != INF_EXIT:
                            TPv = L * (1 + float(sig4_b[i, a]))
                            pre = (marr >= f) & (marr < e) & np.isfinite(clv)
                            path2[pre] += q * (clv[pre] / L - 1)
                            post = marr >= e
                            path2[post] += q * (TPv / L - 1)
                        else:
                            vv = np.isfinite(clv) & (marr >= f)
                            path2[vv] += q * (clv[vv] / L - 1)
                    for f, ri, a, h, e in takenh:
                        L = float(Lhb[i, a, h, ri])
                        if not (np.isfinite(L) and L > 0) or q == 0:
                            continue
                        clv = Cm[:, a]
                        is_tp = bool(tphb[i, a, h, ri]) and e < 60 * (h + 1)
                        if is_tp:
                            TPv = L * (1 + float(sig1h_b[i, a]))
                            pre = (marr >= f) & (marr < e) & np.isfinite(clv)
                            path2[pre] += q * (clv[pre] / L - 1)
                            post = marr >= e
                            path2[post] += q * (TPv / L - 1)
                        else:
                            pre = (marr >= f) & (marr < e) & np.isfinite(clv)
                            path2[pre] += q * (clv[pre] / L - 1)
                            # locked timeout gross
                            if h == 3:
                                eo = float(o2[pos[i], a]) if pos[i] + 1 < n else np.nan
                            else:
                                eo = float(op4[pos[i], 60 * (h + 1), a])
                            if np.isfinite(eo) and eo > 0:
                                post = marr >= e
                                path2[post] += q * (eo / L - 1)
                    pm = float(np.nanmin(path2)) if np.isfinite(path2).any() else 0.0
                eq_min[i] = (eq[i - 1] if i else 1.0) * (1 + min(0.0, pm) - ex_c + min(fundp, 0.0))
            else:
                eq_min[i] = eq[i]
            prev_w, prev_c = w.copy(), c
        return net, turn, g, eq, eq_min, taken_total, canc_total, tp_taken, tk4, tkh

    net_n, turn_n, g_n, eq_n, eqmin_n, tk_n, cx_n, tp_n, tk4_n, tkh_n = run_shared(
        r4b_n, rhb_n, s_n, fee_b, rel_b, fee_s_, rel_s_)
    net_s, turn_s, g_s, eq_s, eqmin_s, tk_s, cx_s, tp_s, tk4_s, tkh_s = run_shared(
        r4b_s, rhb_s, s_s, fee_b_s, rel_b_s, fee_s_s, rel_s_s)
    summ_n = v110.summarize(pd.Series(net_n, index=bidx), pd.Series(turn_n, index=bidx),
                            pd.Series(g_n, index=bidx))
    summ_s = v110.summarize(pd.Series(net_s, index=bidx), pd.Series(turn_s, index=bidx),
                            pd.Series(g_s, index=bidx))

    def dd_1m(eq, eq_min):
        full = np.asarray((bidx >= START) & (bidx < END))
        e = eq[full] / eq[full][0]
        em = eq_min[full] / eq[full][0]
        dd = 1 - np.minimum(e, em) / np.maximum.accumulate(e)
        worst = int(np.argmax(dd))
        return round(100 * float(dd.max()), 2), str(bidx[full][worst])

    dd_n, worst_n = dd_1m(eq_n, eqmin_n)
    dd_s, worst_s = dd_1m(eq_s, eqmin_s)
    wi_n = int(np.argmin(np.where(live, net_n, np.inf)))
    wi_s = int(np.argmin(np.where(live, net_s, np.inf)))

    def pack(summ, dd1, worst_t, tk, cx, tp, s_in, tk4, tkh):
        return {
            "monthly_pct": summ["monthly_pct"],
            "yearly": summ["yearly"],
            "full_path_dd": summ["full_path_dd"],
            "worst_year_dd": summ["worst_year_dd"],
            "dd_1m_mark": dd1,
            "dd_1m_worst_bar": worst_t,
            "gate_dd": max(summ["full_path_dd"], dd1),
            "rungs_taken": int(tk),
            "rungs_cancelled": int(cx),
            "tp_exits_taken": int(tp),
            "taken_4h": int(tk4),
            "taken_hourly": int(tkh),
            "mean_s": round(float(np.mean(s_in[live])), 3),
        }

    row_n = pack(summ_n, dd_n, worst_n, tk_n, cx_n, tp_n, s_n, tk4_n, tkh_n)
    row_s = pack(summ_s, dd_s, worst_s, tk_s, cx_s, tp_s, s_s, tk4_s, tkh_s)
    row_n["worst_bar"] = {"time": str(bidx[wi_n]), "net": float(net_n[wi_n])}
    row_s["worst_bar"] = {"time": str(bidx[wi_s]), "net": float(net_s[wi_s])}

    replication = {
        "version": "v184_audit_replication",
        "blind": "did_not_open_research_v184_until_this_file_saved",
        "books": "cached v154 books (A+B+D)/3",
        "target": TARGET,
        "cap": CAP,
        "S_REF": S_REF,
        "N_MAX": N_MAX,
        "governor": "20% with 2-bar lag on combined equity",
        "realism": "all on (funding, carry_real, budget, min_notional); W=60 execution",
        "spec": {
            "symbols": MAJORS,
            "rungs_4h": list(RUNGS),
            "rungs_hourly": list(RUNGS),
            "grid": f"{G.min()} -> {G.max()} ({n} 4h bars)",
            "trigger_4h": "first m in 16..238 with 1m low < open(T)*(1-k*sigma(t)) strict",
            "tp_4h": "TP=L*(1+sigma); first m>f high>TP else next-open taker exit",
            "sigma_1h": "per asset hourly opens 1m opens 0/60/120/180 flattened; rolling 1440 min480 at last hour of previous holding bar",
            "trigger_hourly": "base=1m open 60h; L=base*(1-k*sigma_1h); live 16..57 h0 else 60h+4..60h+57; first low<L",
            "tp_hourly": "TP=L*(1+sigma_1h); first m>fill <60(h+1) high>TP maker else open 60(h+1) taker (h3 next-4h-open + funding)",
            "budget": "shared order (minute, 4h before hourly, rung, asset); take iff (open(e>f)+1)*rn<=1/6; rn=s*g*0.25/4/1.657",
            "vol": "uncapped sum both ladders shifted by 2",
            "mark": "taken only; 4h as v183; hourly TP f..e-1 close/L-1 locked TP/L-1; hourly timeout f..e-1 locked exit_open/L-1",
        },
        "assumptions": {
            "C1": "grid date_range 2020-02-01 to last books bar; live books bars; no ML gate",
            "C2": "4h sigma pct_change rolling 360 min120 at t; finite>0 else no 4h fill",
            "C3": "4h L/f/TP/next-open as v183 audit B3/B4/B7; stress extra as fee",
            "C4": "sigma_1h rolling 1440 min480 at (i-1)*4+3 strictly before T; finite>0 else no hourly fills",
            "C5": "hourly base 1m open 60h ffilled; L=base*(1-k*sigma_1h); live windows as spec",
            "C6": "hourly TP/timeout as spec; h3 timeout funding at T+4h; stress extra as fee",
            "C7": "shared budget (minute, 4h first, rung, asset); e=TP or timeout; past exits only",
            "C8": "vol uncapped sum both ladders shift2; s=min(0.25/vol,2) else 1",
            "C9": "loop mirrors engine_real FULL W60; governor/budget/min-notional on",
            "C10": "1m mark taken only; hourly TP locked TP/L-1, timeout locked exit_open/L-1 gross",
            "C11": "1m keep-last dedup + within-bar ffill prices",
        },
        "counts_grid": {
            "fills_4h": int(fills4),
            "tp_4h": int(tp4),
            "fills_hourly": int(fillsh),
            "tp_hourly": int(tph_n),
        },
        "sleeve_sums": {
            "normal": float(sleeve_unc_n.sum()),
            "stress": float(sleeve_unc_s.sum()),
        },
        "primary_normal": row_n,
        "stress": row_s,
        "params": {
            "start": str(START), "end": str(END),
            "account_usdt": er.ACCOUNT_USDT, "margin": er.MARGIN, "buffer": er.BUFFER,
        },
    }
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print("saved", OUT, flush=True)


if __name__ == "__main__":
    main()
