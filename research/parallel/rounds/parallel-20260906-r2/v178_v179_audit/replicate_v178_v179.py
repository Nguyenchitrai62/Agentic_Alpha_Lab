"""v178+v179 blind audit Part A replication.

Blind rule: does NOT read research/.../v178/*, research/.../v179/*, any
result/diagnostics JSON nor any v178/v179 sleeve script until
replication.json is saved. Independent implementation from
OPENCODE_V178_V179_AUDIT.md (+ v175/v176 audit base) only.
May import engine_real for v154_books, context, constants (like v171-v177
audits), and v135 for the W=60 execution arrays (like v170/v175/v176).

Spec (frozen before running, from OPENCODE_V178_V179_AUDIT.md):
  A1 (v178): ladder of resting bids at k in (2.5,3,3.5,4) sigma below
  open(T), minutes 16..238, maker 0.0002 at the bid on 1m trade-through,
  taker exit at open(T+4h) with crash-aware slippage, funding; per bar
  sleeve = sum over assets and rungs of 0.25/4 * r. Sleeve inside the
  portfolio vol target as v176 BUT the vol leg uses sleeve_unit shifted
  by 2 bars (the v176-audit causality fix). Rows: normal costs and stress
  (books maker 0.0004 / taker 0.0007 + 5bps on taker fills; sleeve maker
  0.0004, exit taker 0.0007 + 5bps).
  A2 (v179): as A1, but per holding bar rung fills taken in order
  (fill minute, shallower rung, column order BNB,BTC,ETH,SOL,XRP) while
  cumulative open notional (rung notional = s*g*0.25/4/1.657) <= 0.05/0.30;
  later fills cancelled; vol leg still uses uncapped sleeve unit shifted
  by 2.

Frozen blind assumptions (documented before running):
  C1 Grid pd.date_range(2020-02-01 00:00 UTC, last books bar, freq 4h).
  C2 sigma(t) = std of 360 4h open-to-open pct changes ending at t,
     min 120, from full pre-history (same as v175/v176 audits). Finite
     sigma > 0 required else no fill. T = t+4h, T2 = t+8h.
  C3 L(t,sym,k) = open4h(T)*(1-k*sigma(t)). Fill iff any 1m low in offsets
     16..238 of T < L (strict). Fill minute f = first such offset, -1 if
     none. Entry price = L (resting bid, maker fee).
  C4 s_out per (t,sym) from 1m minute 0 of T2: max(0.0002,
     0.25*(H-L)/O), fallback 0.0002 when missing/nonpositive/H<L (same as
     v175 A6). Exit = open4h(T2)*(1-s_out). Same s_out for all 4 rungs of
     that (t,sym).
  C5 r(t,sym,k) = exit/L-1-entry_fee-exit_fee-extra-funding(T2) for filled
     rungs with valid exit (finite positive 4h open, i+1<n), else 0.
     Normal: entry 0.0002, exit 0.0005, extra 0. Stress: entry 0.0004,
     exit 0.0007, extra 0.0005 (same as v176 B5: +5bps exit slippage).
     Funding = floored-4h summed fundingRate at T2, missing -> 0.
  C6 Sleeve per bar = 0.0625 * sum_{sym,k} r (0.25/4 per rung). No
     walk-forward k choice (ladder holds all 4 rungs). sleeve_unit =
     sleeve/1.657 (S_REF assignment constant).
  C7 Vol target as v176 with causality fix: on books index,
     ret1 = o/o.shift(1)-1 (o = ctx opens), realized[i] =
     0.8*sum_j books[i-2,j]*ret1[i,j] + 0.6*carry[i-1] +
     sleeve_unit[i-2] (all pandas shifts, NaN at head). vol = rolling std
     360 min 120 * sqrt(2190). s = min(0.25/vol,2), 1.0 where NaN or
     non-finite. W_BOOKS=0.8, C_REAL=0.6, CAP=2, TARGET=0.25, PD=6.
     Stressed s recomputed from stressed uncapped sleeve_unit.
  C8 Loop mirrors engine_real.run FULL with W=60 execution arrays via
     v135.load_1m (p0=open@0, lo/hi=min/max over 2..59, pW=open@60
     NaN->p0; maker fee / rel -/+0.001 else taker + drift; stress adds
     +5bps adverse on taker rel): w=0.8*s[i]*B[i]*g[i], c=0.6*s[i]*g[i]
     on live bars else 0. Budget 0.95 carry-first, books rescale to
     sum|w|=4.75 if over. Min notional at 10k account. Governor 20% with
     2-bar lag on combined equity. Funding/carry/carry_cost as engine_real
     FULL. Payoff: v178 net[i]+=s[i]*g[i]*sleeve_unit_uncapped[i];
     v179 net[i]+=s[i]*g[i]*taken_unit[i] (taken from budget below) on
     live bars. Vol leg (s) always from uncapped sleeve_unit shifted by 2.
  C9 v179 budget (per holding/decision bar i): candidate rung fills =
     filled rungs (valid L, f>=0) sorted by (fill minute, shallower rung
     = smaller k first, column order BNB=0,BTC=1,ETH=2,SOL=3,XRP=4).
     Rung notional q[i] = s[i]*g[i]*0.0625/1.657 (same for all rungs of
     bar i; s[i] precomputed uncapped vol scale, g[i] current governor).
     Iterate in order: keep rung iff (asset_cum[a]+q <= 0.05+eps) and
     (total_cum+q <= 0.30+eps); else cancel that rung and continue
     (equal-size rungs so a total-cap failure cancels all later too).
     "0.05/0.30" read as per-asset 0.05 AND total 0.30 simultaneous caps.
     Vol leg unchanged (uncapped). Taken/cancelled rung counts reported.
     Budget uses only (f, k, column) + s[i]*g[i] known at decision i and
     fill occurrence at its minute: no exit price, no future bar.
  C10 1m DD diagnostic per row (same as v176 B6, extended to rungs):
     for each live books bar i (grid p=pos[i], holding bar T): base
     o_j = 4h open(T); minute closes c_j(m) ffilled; R_b(m)=sum_j
     w_j*(c_j(m)/o_j-1); per open rung (v178: all filled; v179: taken
     only) with L,f and size q[i]=s[i]*g[i]*0.0625/1.657, for m>=f
     R_s(m)+=q[i]*(c(m)/L-1). Minute eq = prev_close_eq*(1+R_b+R_s-exec
     +min(funding,0)) with bar exec/funding contributions. Full-path 1m
     DD = max over live span of 1-min_eq/running_peak normalized to first
     live bar; worst minute time and worst bar (min single-bar net[i]
     among live) reported. Sleeve fees/funding stay in bar-close payoff,
     not in minute path (conservative gross marking, as v176).
  C11 1m grids: keep-last dedup + within-bar ffill for O/H/L/C; fill test
     on ffilled low; s_out on ffilled H/L/O of row i+1 minute 0.
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

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
KRUNGS = (2.5, 3.0, 3.5, 4.0)
GRID_START = pd.Timestamp("2020-02-01 00:00:00+00:00")
SEL_UNUSED = None
TARGET = 0.25
CAP = 2.0
S_REF = 1.657
W_EXEC = 60
D = 0.001
ENTRY_FEE = 0.0002
EXIT_FEE = 0.0005
ENTRY_FEE_STRESS = 0.0004
EXIT_FEE_STRESS = 0.0007
TAKER_EXTRA = 0.0005
W_BOOKS = 0.8
C_REAL = 0.6
PER_ASSET_CAP = 0.05
TOTAL_CAP = 0.30
EPS = 1e-12
RUNG_W = 0.25 / 4.0


def _load_engine_real():
    spec = importlib.util.spec_from_file_location(
        "v178_v179_audit_engine_real", ROUND2 / "engine_real" / "engine_real.py")
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


def build_ladder(entry_fee, exit_fee, extra, sigma, openT, exitOpen4h, fundT2,
                 low_g, open_g, high_g, idx, n):
    nK = len(KRUNGS)
    nS = len(SYMS)
    L_mat = np.full((n, nS, nK), np.nan)
    f_mat = np.full((n, nS, nK), -1, dtype=int)
    r_mat = np.zeros((n, nS, nK))
    MO = np.arange(16, 239)
    # s_out per (t, sym) shared across rungs
    s_out = np.zeros((n, nS))
    for j in range(nS):
        nxt = np.clip(idx + 1, 0, n - 1)
        o0 = open_g[nxt, 0, j]
        h0 = high_g[nxt, 0, j]
        l0 = low_g[nxt, 0, j]
        with np.errstate(invalid="ignore", divide="ignore"):
            rng = (h0 - l0) / o0
        ok = (np.isfinite(rng) & np.isfinite(o0) & (o0 > 0)
              & np.isfinite(h0) & np.isfinite(l0) & (h0 >= l0))
        s_raw = np.maximum(0.0002, 0.25 * rng)
        s_out[:, j] = np.where(ok, np.where(np.isfinite(s_raw), s_raw, 0.0002), 0.0002)
    for j in range(nS):
        sig = sigma[:, j]
        oT = openT[:, j]
        e4 = exitOpen4h[:, j]
        fu = fundT2[:, j]
        so = s_out[:, j]
        low = low_g[:, :, j]
        base_ok = (np.isfinite(sig) & (sig > 0) & np.isfinite(oT) & (oT > 0))
        for ki, k in enumerate(KRUNGS):
            with np.errstate(invalid="ignore", divide="ignore"):
                L = oT * (1 - k * sig)
            valid_L = base_ok & np.isfinite(L) & (L > 0)
            L_mat[:, j, ki] = np.where(valid_L, L, np.nan)
            with np.errstate(invalid="ignore"):
                hit = valid_L[:, None] & np.isfinite(low[:, MO]) & (low[:, MO] < L[:, None])
            has = hit.any(axis=1)
            first = hit.argmax(axis=1)
            f = np.where(has, MO[first], -1)
            f_mat[:, j, ki] = f
            okm = (has & valid_L & np.isfinite(e4) & (e4 > 0) & (idx + 1 < n))
            r = np.zeros(n)
            with np.errstate(invalid="ignore", divide="ignore"):
                exit_px = e4[okm] * (1 - so[okm])
                r[okm] = exit_px / L[okm] - 1 - entry_fee - exit_fee - extra - fu[okm]
            r[~np.isfinite(r)] = 0.0
            r[idx + 1 >= n] = 0.0
            r_mat[:, j, ki] = r
    sleeve = RUNG_W * r_mat.sum(axis=(1, 2))
    return L_mat, f_mat, r_mat, s_out, sleeve


def main():
    er = _load_engine_real()
    v110 = er.v144.v110
    v92 = er.v144.v110.v92
    v135 = er.v144.v135
    ANCHORS = list(v92.ANCHORS)
    START, END = v110.START, v110.END
    print("anchors", ANCHORS, "live", START, "->", END, flush=True)

    books, opens_full = er.v154_books()
    books = books.sort_index()
    opens_full = opens_full.sort_index()
    bidx = books.index
    cols = list(books.columns)
    last_books = books.index.max()
    grid = pd.date_range(GRID_START, last_books, freq="4h", tz="UTC")
    n = len(grid)
    T_all = grid + pd.Timedelta(hours=4)
    T2_all = grid + pd.Timedelta(hours=8)
    print(f"grid {n} bars {grid.min()} -> {grid.max()}", flush=True)

    openT = np.zeros((n, len(SYMS)))
    exitOpen4h = np.zeros((n, len(SYMS)))
    fundT2 = np.zeros((n, len(SYMS)))
    sigma = np.zeros((n, len(SYMS)))
    for j, sym in enumerate(SYMS):
        k = pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{sym}_4h.parquet")
        ot = pd.to_datetime(k["open_time"], utc=True)
        o = pd.Series(k["open"].to_numpy(dtype=float), index=ot).sort_index()
        o = o[~o.index.duplicated(keep="last")]
        ret = o / o.shift(1) - 1
        sig = ret.rolling(360, min_periods=120).std()
        sigma[:, j] = sig.reindex(grid).to_numpy(dtype=float)
        openT[:, j] = o.reindex(T_all).to_numpy(dtype=float)
        exitOpen4h[:, j] = o.reindex(T2_all).to_numpy(dtype=float)
        f = pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{sym}_funding.parquet")
        ft = pd.to_datetime(f["fundingTime"], utc=True).dt.floor("4h")
        bucket = f.groupby(ft)["fundingRate"].sum()
        fundT2[:, j] = bucket.reindex(T2_all).fillna(0.0).to_numpy(dtype=float)
        print(f"{sym}: sigma_finite={(np.isfinite(sigma[:, j])).sum()}/{n}", flush=True)

    n_min = n * 240
    mgrid = pd.date_range(T_all.min(), T_all.min() + pd.Timedelta(minutes=n_min - 1),
                          freq="1min", tz="UTC")
    assert len(mgrid) == n_min
    open_g = np.zeros((n, 240, len(SYMS)))
    high_g = np.zeros((n, 240, len(SYMS)))
    low_g = np.zeros((n, 240, len(SYMS)))
    close_g = np.zeros((n, 240, len(SYMS)))
    for j, sym in enumerate(SYMS):
        if sym == "BTCUSDT":
            files = sorted(glob.glob(str(ROOT / "data/raw/btc_intraday_20260924/klines_1m_20*.parquet")))
        else:
            files = sorted(glob.glob(str(ROOT / f"data/raw/majors_intraday_20260924/{sym}_1m_20*.parquet")))
        assert files, f"no 1m files for {sym}"
        use_cols = ["open_time", "open", "high", "low", "close"]
        parts = [pd.read_parquet(f, columns=use_cols) for f in files]
        d = pd.concat(parts, ignore_index=True)
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        d = d.sort_values("open_time").drop_duplicates("open_time", keep="last").set_index("open_time")
        op = d["open"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        hi = d["high"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        lo = d["low"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        cl = d["close"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        open_g[:, :, j] = _ffill_rows(op)
        high_g[:, :, j] = _ffill_rows(hi)
        low_g[:, :, j] = _ffill_rows(lo)
        close_g[:, :, j] = _ffill_rows(cl)
        print(f"{sym}: 1m rows={len(d)} files={len(files)}", flush=True)

    idx = np.arange(n)
    L_n, f_n, r_n, s_out, sleeve = build_ladder(
        ENTRY_FEE, EXIT_FEE, 0.0, sigma, openT, exitOpen4h, fundT2,
        low_g, open_g, high_g, idx, n)
    L_s, f_s, r_s, _, sleeve_str = build_ladder(
        ENTRY_FEE_STRESS, EXIT_FEE_STRESS, TAKER_EXTRA, sigma, openT,
        exitOpen4h, fundT2, low_g, open_g, high_g, idx, n)
    sleeve_unit = sleeve / S_REF
    sleeve_unit_str = sleeve_str / S_REF
    fills = int((f_n >= 0).sum())
    fills_s = int((f_s >= 0).sum())
    print(f"ladder fills normal={fills} stress={fills_s} (same L/f, fees differ)", flush=True)
    print(f"sleeve sum normal={sleeve.sum():.4f} unit={sleeve_unit.sum():.4f}", flush=True)
    print(f"sleeve sum stress={sleeve_str.sum():.4f} unit={sleeve_unit_str.sum():.4f}", flush=True)

    pos = grid.get_indexer(bidx)
    assert (pos >= 0).all()
    su_books = sleeve_unit[pos]
    su_books_s = sleeve_unit_str[pos]

    ctx = er.context(books, opens_full)
    o_df = ctx["opens"].reindex(bidx)[cols]
    r_next, _, _, fund = ctx["mkt"]
    carry_arr, expo_arr = ctx["carry_real"]
    B = books.to_numpy(dtype=float)
    nB = len(bidx)
    live = np.asarray((bidx >= START) & (bidx < END))
    with np.errstate(invalid="ignore", divide="ignore"):
        ret1 = o_df / o_df.shift(1) - 1
    carry_s = pd.Series(carry_arr, index=bidx)
    su_s = pd.Series(su_books, index=bidx)
    su_s_str = pd.Series(su_books_s, index=bidx)

    def vol_s_from(su_series):
        realized = (W_BOOKS * (books.shift(2) * ret1).sum(axis=1)
                    + C_REAL * carry_s.shift(1) + su_series.shift(2))
        vol = realized.rolling(360, min_periods=120).std() * np.sqrt(2190)
        v = vol.to_numpy(dtype=float)
        s_arr = np.where(np.isnan(v), 1.0, np.minimum(TARGET / np.where(np.isnan(v), 1.0, v), CAP))
        return np.where(~np.isfinite(s_arr), 1.0, s_arr)

    s_arr = vol_s_from(su_s)
    s_arr_s = vol_s_from(su_s_str)
    print(f"s normal mean_live={np.mean(s_arr[live]):.3f} min={np.min(s_arr[live]):.3f} max={np.max(s_arr[live]):.3f}", flush=True)
    print(f"s stress mean_live={np.mean(s_arr_s[live]):.3f}", flush=True)

    fee_b, rel_b, fee_s_, rel_s_ = _exec_arrays(bidx, cols, v135, W_EXEC, 0.0002, 0.0005, 0.0)
    fee_b_s, rel_b_s, fee_s_s, rel_s_s = _exec_arrays(
        bidx, cols, v135, W_EXEC, ENTRY_FEE_STRESS, EXIT_FEE_STRESS, TAKER_EXTRA)
    mins = np.array([er.MIN_NOTIONAL.get(c, 5.0) for c in cols])

    # rung grids mapped to books index for budget + DD
    Lb_n = L_n[pos]
    fb_n = f_n[pos]
    rb_n = r_n[pos]
    base_books = openT[pos]
    close_books = np.zeros((nB, 240, len(SYMS)))
    for j in range(len(SYMS)):
        close_books[:, :, j] = close_g[pos, :, j]
    Lb_s = L_s[pos]
    fb_s = f_s[pos]
    rb_s = r_s[pos]

    def budgeted_taken_for_bar(frow, s_i, g_i):
        # frow: (5,4) fill minutes; returns taken mask (5,4) bool
        if not (np.isfinite(s_i) and np.isfinite(g_i)) or s_i == 0 or g_i == 0:
            q = 0.0
        else:
            q = float(s_i * g_i * RUNG_W / S_REF)
        if q <= 0:
            # zero notional: take all filled (payoff zero anyway)
            taken = (frow >= 0)
            return taken, q
        cands = []
        for j in range(len(SYMS)):
            for ki in range(len(KRUNGS)):
                f = int(frow[j, ki])
                if f >= 0:
                    cands.append((f, ki, j))
        cands.sort(key=lambda t: (t[0], t[1], t[2]))
        taken = np.zeros((len(SYMS), len(KRUNGS)), dtype=bool)
        asset_cum = np.zeros(len(SYMS))
        total = 0.0
        for f, ki, j in cands:
            if asset_cum[j] + q <= PER_ASSET_CAP + EPS and total + q <= TOTAL_CAP + EPS:
                taken[j, ki] = True
                asset_cum[j] += q
                total += q
        return taken, q

    def run_loop(s_in, fee_b_in, rel_b_in, fee_s_in, rel_s_in, Lb, fb, rb, budgeted):
        m = len(cols)
        net = np.zeros(nB)
        turn = np.zeros(nB)
        g = np.ones(nB)
        eq = np.ones(nB)
        w_all = np.zeros((nB, m))
        exec_c = np.zeros(nB)
        fund_p = np.zeros(nB)
        taken_unit = np.zeros(nB)
        n_taken = 0
        n_cancel = 0
        prev_w = np.zeros(m)
        prev_c = 0.0
        for i in range(nB):
            if i >= 2:
                j = i - 2
                peak = eq[max(0, j - 90 * 6 + 1): j + 1].max()
                g[i] = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0.0, 1.0))
            if live[i]:
                w = W_BOOKS * s_in[i] * B[i] * g[i]
                c = C_REAL * s_in[i] * g[i]
            else:
                w = np.zeros(m)
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
            fundp = float(-np.sum(w * fund[i]))
            carry_p = float(c * carry_arr[i])
            dc = c - prev_c
            carry_c = float(abs(dc) / er.CARRY_CAPITAL * ex * (er.SPOT_FEE + er.PERP_TAKER))
            ni = gross - ex_c + fundp + carry_p - carry_c
            if live[i]:
                if budgeted:
                    taken, _q = budgeted_taken_for_bar(fb[i], s_in[i], g[i])
                    tk = taken & (fb[i] >= 0)
                    pay = float(s_in[i] * g[i] * (RUNG_W * (rb[i][tk]).sum() / S_REF))
                    taken_unit[i] = float(RUNG_W * (rb[i][tk]).sum() / S_REF)
                    n_taken += int(tk.sum())
                    n_cancel += int((fb[i] >= 0).sum() - int(tk.sum()))
                    ni += pay
                else:
                    ni += float(s_in[i] * g[i] * (RUNG_W * rb[i].sum() / S_REF))
                    taken_unit[i] = float(RUNG_W * rb[i].sum() / S_REF)
            net[i] = ni
            turn[i] = float(np.abs(dw).sum())
            eq[i] = (eq[i - 1] if i else 1.0) * (1 + ni)
            w_all[i] = w
            exec_c[i] = ex_c
            fund_p[i] = fundp
            prev_w, prev_c = w.copy(), c
        return net, turn, g, eq, w_all, exec_c, fund_p, taken_unit, n_taken, n_cancel

    def dd_1m(eq, w_all, exec_c, fund_p, s_in, g_arr, Lb, fb, rb, budgeted):
        first_live = int(np.flatnonzero(live)[0])
        base_eq = eq[first_live - 1] if first_live > 0 else 1.0
        if base_eq == 0:
            base_eq = 1.0
        eq_n = eq / base_eq
        peak = -np.inf
        worst = 0.0
        worst_t = None
        for i in range(nB):
            if not live[i]:
                continue
            run_peak = eq_n[i - 1] if i > 0 else eq_n[i]
            peak = max(peak, run_peak, eq_n[i])
            prev_eq = eq[i - 1] if i > 0 else 1.0
            w = w_all[i]
            q = float(s_in[i] * g_arr[i] * RUNG_W / S_REF)
            if budgeted:
                taken, _ = budgeted_taken_for_bar(fb[i], s_in[i], g_arr[i])
            else:
                taken = np.ones((len(SYMS), len(KRUNGS)), dtype=bool)
            with np.errstate(invalid="ignore", divide="ignore"):
                rb_m = np.zeros(240)
                rs_m = np.zeros(240)
                for j in range(len(SYMS)):
                    base = base_books[i, j]
                    if not (np.isfinite(base) and base > 0):
                        continue
                    cl = close_books[i, :, j]
                    valid = np.isfinite(cl)
                    rb_m[valid] += w[j] * (cl[valid] / base - 1)
                    for ki in range(len(KRUNGS)):
                        f = int(fb[i, j, ki])
                        if f < 0 or not taken[j, ki]:
                            continue
                        L = float(Lb[i, j, ki])
                        if not (np.isfinite(L) and L > 0) or q == 0:
                            continue
                        m_idx = np.arange(240) >= f
                        vm = valid & m_idx
                        rs_m[vm] += q * (cl[vm] / L - 1)
                r_min = rb_m + rs_m
                meq = prev_eq * (1 + r_min - exec_c[i] + min(fund_p[i], 0.0))
                meq_n = meq / base_eq
                lo_min = float(np.nanmin(meq_n[np.isfinite(meq_n)])) if np.isfinite(meq_n).any() else np.nan
                if np.isfinite(lo_min) and peak > 0:
                    dd = 1 - lo_min / peak
                    if dd > worst:
                        worst = float(dd)
                        worst_t = str(bidx[i])
        eq_live = eq_n[live]
        close_dd = float(np.max(1 - eq_live / np.maximum.accumulate(eq_live))) if len(eq_live) else 0.0
        return round(100 * max(worst, close_dd), 2), round(100 * close_dd, 2), worst_t

    rows = {}
    # v178 normal + stress, v179 normal + stress
    net178, turn178, g178, eq178, w178, ec178, fp178, tu178, _, _ = run_loop(
        s_arr, fee_b, rel_b, fee_s_, rel_s_, Lb_n, fb_n, rb_n, False)
    net178s, turn178s, g178s, eq178s, w178s, ec178s, fp178s, tu178s, _, _ = run_loop(
        s_arr_s, fee_b_s, rel_b_s, fee_s_s, rel_s_s, Lb_s, fb_s, rb_s, False)
    net179, turn179, g179, eq179, w179, ec179, fp179, tu179, tk179, cx179 = run_loop(
        s_arr, fee_b, rel_b, fee_s_, rel_s_, Lb_n, fb_n, rb_n, True)
    net179s, turn179s, g179s, eq179s, w179s, ec179s, fp179s, tu179s, tk179s, cx179s = run_loop(
        s_arr_s, fee_b_s, rel_b_s, fee_s_s, rel_s_s, Lb_s, fb_s, rb_s, True)

    def pack(net, turn, g_arr, eq, w_all, ec, fp, s_in, Lb, fb, rb, budgeted, tk, cx):
        summ = v110.summarize(pd.Series(net, index=bidx), pd.Series(turn, index=bidx),
                              pd.Series(g_arr, index=bidx))
        dd1m, ddclose, worst_t = dd_1m(eq, w_all, ec, fp, s_in, g_arr, Lb, fb, rb, budgeted)
        wi = int(np.argmin(np.where(live, net, np.inf)))
        return {
            "monthly_pct": summ["monthly_pct"],
            "yearly": summ["yearly"],
            "full_path_dd": summ["full_path_dd"],
            "worst_year_dd": summ["worst_year_dd"],
            "mean_s": round(float(np.mean(s_in[live])), 3),
            "full_path_dd_1m": dd1m,
            "full_path_dd_close_check": ddclose,
            "worst_1m_time": worst_t,
            "worst_bar": {"time": str(bidx[wi]), "net": float(net[wi])},
            "taken_rungs_live": int(tk) if budgeted else None,
            "cancelled_rungs_live": int(cx) if budgeted else None,
        }

    rows["v178_normal"] = pack(net178, turn178, g178, eq178, w178, ec178, fp178,
                               s_arr, Lb_n, fb_n, rb_n, False, 0, 0)
    rows["v178_stress"] = pack(net178s, turn178s, g178s, eq178s, w178s, ec178s, fp178s,
                               s_arr_s, Lb_s, fb_s, rb_s, False, 0, 0)
    rows["v179_normal"] = pack(net179, turn179, g179, eq179, w179, ec179, fp179,
                               s_arr, Lb_n, fb_n, rb_n, True, tk179, cx179)
    rows["v179_stress"] = pack(net179s, turn179s, g179s, eq179s, w179s, ec179s, fp179s,
                               s_arr_s, Lb_s, fb_s, rb_s, True, tk179s, cx179s)
    for k, v in rows.items():
        print(k, v["monthly_pct"], v["full_path_dd"], v["full_path_dd_1m"],
              v["worst_bar"], v.get("taken_rungs_live"), v.get("cancelled_rungs_live"), flush=True)

    # per-rung fill diagnostics on full grid
    rung_fills = {}
    for ki, k in enumerate(KRUNGS):
        rung_fills[str(k)] = int((f_n[:, :, ki] >= 0).sum())
    per_sym_rung = {s: {str(k): int((f_n[:, j, ki] >= 0).sum())
                        for ki, k in enumerate(KRUNGS)} for j, s in enumerate(SYMS)}

    replication = {
        "version": "v178_v179_audit_replication",
        "blind": "did_not_open_research_v178_v179_until_this_file_saved",
        "books": "cached v154 books (A+B+D)/3",
        "target": TARGET,
        "cap": CAP,
        "S_REF": S_REF,
        "governor": "20% with 2-bar lag on combined equity",
        "realism": "all on (funding, carry_real, budget, min_notional); W=60 execution",
        "spec": {
            "ladder": "resting bids at k in (2.5,3,3.5,4) sigma below open(T), minutes 16..238, maker at bid on trade-through, taker exit at open(T+4h) with crash-aware slippage + funding",
            "sleeve_per_bar": "sum over assets and rungs of 0.25/4 * r",
            "sleeve_unit": "sleeve / 1.657",
            "realized_total": "0.8*sum books[i-2]*(o[i]/o[i-1]-1)+0.6*carry[i-1]+sleeve_unit_uncapped[i-2] (shift-2 causality fix)",
            "vol": "rolling std 360 min 120 * sqrt(2190)",
            "s": "min(0.25/vol,2), 1 if NaN",
            "weights": "books 0.8*s*B*g, carry 0.6*s*g, sleeve s*g*sleeve_unit (uncapped v178; taken v179) on live bars",
            "exec": "W=60 (p0@0, lo/hi 2..59, pW@60 NaN->p0; maker 0.0002 rel -/+0.001 else taker 0.0005 + drift)",
            "budget_v179": "per holding bar take rung fills in order (fill minute, shallower rung, column BNB,BTC,ETH,SOL,XRP) while per-asset cum + q <= 0.05 and total cum + q <= 0.30; q=s*g*0.0625/1.657; later cancelled; vol still uncapped shift-2",
            "grid": f"{grid.min()} -> {grid.max()} ({n} 4h bars)",
        },
        "assumptions": {
            "C1": "grid date_range 2020-02-01 to last books bar",
            "C2": "sigma full pre-history rolling(360,min120); finite and > 0 else no fill",
            "C3": "L=openT*(1-k*sigma); fill iff any low[16..238] < L strict; f=first such minute; entry=L",
            "C4": "s_out=max(0.0002,0.25*(H-L)/O of 1m minute-0 of T+4h) else 0.0002; exit=open4h(T+4h)*(1-s_out)",
            "C5": "r=exit/L-1-entry-exit-extra-funding; normal 0.0002/0.0005/0; stress 0.0004/0.0007/0.0005",
            "C6": "sleeve=0.0625*sum r over 5 syms x 4 rungs; no k selection; unit=/1.657",
            "C7": "realized/vol/s on books idx with sleeve_unit.shift(2); stressed s from stressed uncapped unit",
            "C8": "loop mirrors engine_real FULL; governor/budget/min-notional on; payoff uncapped v178 / taken v179",
            "C9": "v179 budget order (f, smaller-k, column); caps per-asset 0.05 and total 0.30 on q=s*g*0.0625/1.657; uses only fill-minute-known info",
            "C10": "1m DD marks books w + open rungs (all v178 / taken v179) from f at close/L-1; minute eq=prev*(1+Rb+Rs-exec+min(funding,0))",
            "C11": "1m grids keep-last dedup + within-bar ffill",
        },
        "ladder_fill_diagnostics_full_grid": {
            "fills_per_rung": rung_fills,
            "fills_per_sym_rung": per_sym_rung,
            "fills_total": fills,
            "sleeve_sum": float(sleeve.sum()),
            "sleeve_unit_sum": float(sleeve_unit.sum()),
            "sleeve_sum_stress": float(sleeve_str.sum()),
            "sleeve_unit_sum_stress": float(sleeve_unit_str.sum()),
        },
        "rows": rows,
        "params": {
            "start": str(START), "end": str(END),
            "account_usdt": er.ACCOUNT_USDT, "margin": er.MARGIN, "buffer": er.BUFFER,
            "vol": "rolling std 360 min 120 *sqrt(2190); s=min(0.25/vol,2) else 1",
            "governor": "clip((0.20-(1-eq[j]/peak540))/0.10) j=i-2 on combined eq",
            "rungs": list(KRUNGS),
            "per_asset_cap": PER_ASSET_CAP,
            "total_cap": TOTAL_CAP,
        },
    }
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print("saved", OUT, flush=True)


if __name__ == "__main__":
    main()
