"""v176 blind audit Part A replication.

Blind rule: does NOT read research/.../v176/*, v176_result.json nor
v176_total_vol_target.py until replication.json is saved. Independent
implementation from OPENCODE_V176_AUDIT.md (+ v175 audit base) only.
May import engine_real for v154_books, context, constants (like v171/v172
audits), and v135 for the W=60 execution arrays (like v170/v175).

Spec (frozen before running, from OPENCODE_V176_AUDIT.md):
  sleeve_unit = v175 sleeve (size 0.25 per event, per-bar sum) / 1.657.
  realized_total[i] = 0.8*sum_j books[i-2,j]*(o[i,j]/o[i-1,j]-1)
      + 0.6*carry[i-1] + sleeve_unit[i-1];
  vol = rolling std 360 (min 120) * sqrt(2190);
  s = min(0.25/vol, 2) (1 if NaN).
  Loop exactly as engine_real (governor, budget, min notional,
  v170 60-minute execution, funding, carry) with
  net[i] += s[i]*g[i]*sleeve_unit[i] on live bars.
  Report monthly, yearly net/DD, full-path DD, mean s.

Frozen blind assumptions (documented before running):
  B1 Sleeve = v175 limit dip sleeve, same walk-forward k, size 0.25 per
     event, per-bar sum 0.25*sum_sym r. Grid date_range(2020-02-01 00:00 UTC,
     last books bar, freq 4h). sigma = std of 4h open-to-open pct changes,
     360 bars ending at t, min 120, from full pre-history. L=open(T)*(1-k*sigma),
     T=t+4h. Fill iff any 1m low in offsets 16..238 of T < L (strict).
     Entry=L. Exit=open4h(T+4h)*(1-s_out),
     s_out=max(0.0002,0.25*(H-L)/O of 1m minute 0 of T+4h).
     r=exit/L-1-0.0002-0.0005-funding(T+4h floored-4h sum).
     k per anchor from (2,2.5,3,3.5,4) by pre-anchor Sharpe (mean/std) of
     0.25*sum_sym r over [2020-02-01+30d, anchor-1d). Applied
     [anchor, anchor+365d). Anchors=v92.ANCHORS. Bars outside windows -> 0.
  B2 S_REF=1.657 (assignment constant; equals engine_real v154 mean_scale
     1.657 measured before any sleeve existed). sleeve_unit=sleeve/1.657.
  B3 realized_total on the books index: o=ctx opens reindexed (p103 opens),
     ret1=o/o.shift(1)-1, books.shift(2), carry=carry_real shifted 1,
     sleeve_unit shifted 1. realized=0.8*(books.shift(2)*ret1).sum(axis1)
     +0.6*carry.shift(1)+sleeve_unit.shift(1). Pandas shifts (NaN at head).
     vol=realized.rolling(360,min_periods=120).std()*sqrt(2190).
     s=min(0.25/vol,2), 1.0 where NaN/non-finite. W_BOOKS=0.8, C_REAL=0.6,
     CAP=2.0, TARGET=0.25, PD=6, sqrt(PD*365)=sqrt(2190).
  B4 Loop mirrors engine_real.run FULL with W=60 execution arrays via
     v135.load_1m (p0=open@0, lo/hi=min/max over 2..59, pW=open@60 NaN->p0;
     maker fee 0.0002 rel -/+0.001 else taker 0.0005 + drift, same as v175
     audit): w=0.8*s[i]*B[i]*g[i], c=0.6*s[i]*g[i] on live bars, else 0.
     Budget 0.95 with carry-first cut, books scaled to sum|w|=4.75 if over.
     Min notional at 10k account (BTC 100, ETH 20, others 5): keep prev_w
     if |dw|*equity<min and w!=0. Governor 20% with 2-bar lag on combined
     equity: g[i]=clip((0.20-(1-eq[j]/peak540))/0.10,0,1), j=i-2.
     Funding/carry/carry_cost exactly as engine_real FULL.
     net[i]+=s[i]*g[i]*sleeve_unit[i] on live bars.
  B5 Cost-stress row (diagnostic a): books exec maker fee 0.0004, taker
     0.0007, +5bps (0.0005) extra adverse slippage on every taker fill
     (rel taker buy=mv+0.0002+0.0005, sell=mv-0.0002-0.0005; maker rel
     unchanged -/+0.001). Sleeve stress: same fills/L/s_out, but
     r=exit/L-1-0.0004-0.0007-0.0005-funding (maker entry 0.0004, taker
     exit 0.0007, +5bps exit slippage). Vol/s recomputed from the stressed
     sleeve_unit (same B3 formula with stressed sleeve), then loop with
     stressed exec + stressed sleeve term.
  B6 1m DD diagnostic (b) for the primary row: for each live bar i with
     final weights w (after budget/min_notional), holding bar T=t_i+4h
     (row p in the 1m grids). Base o_j(T)=4h open of T (xs opens). Minute
     closes c_j(m) from 1m close grids (keep-last dedup + within-bar ffill).
     R_books(m)=sum_j w_j*(c_j(m)/o_j-1). Sleeve: per filled (t,sym) event
     with limit L and first fill minute f (first m in 16..238 with low<L),
     size_per_event=s[i]*g[i]*0.25/1.657; for m>=f,
     R_sleeve(m)+=size_per_event*(c(m)/L-1), else 0. Minute eq =
     eq_prev*(1+R_books(m)+R_sleeve(m)-exec_c[i]+min(fundp[i],0)),
     where exec_c/fundp are the primary bar return contributions
     (books exec cost, books funding pnl). Bar-close eq from the primary
     loop. DD=max over live span of 1-min(eq,eq_min)/running max(eq),
     normalised to the first live bar (as v169). Sleeve fees/funding are
     in the bar-close sleeve_unit, not in the minute path (conservative
     gross marking, documented).
  B7 1m grids: drop duplicate open_time keep last, sort, reindex to the
     full minute grid, within-bar forward-fill only (leading NaNs stay NaN)
     for open/high/low/close separately. Fill test uses ffilled low;
     s_out uses ffilled H/L/O of row i+1 minute 0; 1m DD uses ffilled close
     and the same L/f.
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
KS = (2, 2.5, 3, 3.5, 4)
GRID_START = pd.Timestamp("2020-02-01 00:00:00+00:00")
SEL_START = GRID_START + pd.Timedelta(days=30)
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


def _load_engine_real():
    spec = importlib.util.spec_from_file_location(
        "v176_audit_engine_real", ROUND2 / "engine_real" / "engine_real.py")
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


def main():
    er = _load_engine_real()
    v110 = er.v144.v110
    v92 = er.v144.v110.v92
    v135 = er.v144.v135
    v99 = er.v144.v99
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

    MO = np.arange(16, 239)
    idx = np.arange(n)

    s_out = np.zeros((n, len(SYMS)))
    for j in range(len(SYMS)):
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

    def build_sleeve(entry_fee, exit_fee, extra_exit):
        r_sym_k = {}
        for j in range(len(SYMS)):
            sig = sigma[:, j]
            oT = openT[:, j]
            e4 = exitOpen4h[:, j]
            fu = fundT2[:, j]
            so = s_out[:, j]
            low = low_g[:, :, j]
            base_ok = (np.isfinite(sig) & (sig > 0) & np.isfinite(oT) & (oT > 0))
            per_k = {}
            for k in KS:
                with np.errstate(invalid="ignore", divide="ignore"):
                    L = oT * (1 - k * sig)
                valid_L = base_ok & np.isfinite(L) & (L > 0)
                with np.errstate(invalid="ignore"):
                    hit = valid_L[:, None] & np.isfinite(low[:, MO]) & (low[:, MO] < L[:, None])
                has = hit.any(axis=1)
                okm = (has & valid_L & np.isfinite(e4) & (e4 > 0) & (idx + 1 < n))
                r = np.zeros(n)
                with np.errstate(invalid="ignore", divide="ignore"):
                    exit_px = e4[okm] * (1 - so[okm])
                    r[okm] = exit_px / L[okm] - 1 - entry_fee - exit_fee - extra_exit - fu[okm]
                r[~np.isfinite(r)] = 0.0
                r[idx + 1 >= n] = 0.0
                per_k[k] = r
            r_sym_k[SYMS[j]] = per_k
        sleeve_k = {k: 0.25 * sum(r_sym_k[s][k] for s in SYMS) for k in KS}
        return r_sym_k, sleeve_k

    r_sym_k, sleeve_k = build_sleeve(ENTRY_FEE, EXIT_FEE, 0.0)

    anchors_ts = [pd.Timestamp(a, tz="UTC") for a in ANCHORS]
    best_k = {}
    sel_detail = {}
    for a, a_ts in zip(ANCHORS, anchors_ts):
        win = (grid >= SEL_START) & (grid < a_ts - pd.Timedelta(days=1))
        det = {}
        best, best_score = None, -np.inf
        for k in KS:
            s = sleeve_k[k][win]
            mu, sd = float(s.mean()), float(s.std())
            score = mu / sd if (np.isfinite(mu) and np.isfinite(sd) and sd > 0) else -np.inf
            det[str(k)] = {"mean": mu, "std": sd, "score": score if np.isfinite(score) else None,
                           "n_bars": int(win.sum()), "n_nonzero": int((s != 0).sum())}
            if score > best_score:
                best_score, best = score, k
        if best is None:
            best = KS[0]
        best_k[a] = best
        sel_detail[a] = det
        print(f"anchor {a}: best_k={best}", flush=True)

    sleeve = np.zeros(n)
    for i in range(n):
        t = grid[i]
        use = None
        for a, a_ts in zip(ANCHORS, anchors_ts):
            if a_ts <= t < a_ts + pd.Timedelta(days=365):
                use = a
                break
        if use is None:
            continue
        sleeve[i] = sleeve_k[best_k[use]][i]
    sleeve_unit_grid = sleeve / S_REF

    pos = grid.get_indexer(bidx)
    assert (pos >= 0).all(), "books times must exist in sleeve grid"
    sleeve_books = sleeve[pos]
    sleeve_unit_books = sleeve_unit_grid[pos]

    # per (t,sym) L and fill minute for the chosen k (for 1m DD)
    L_chosen = np.zeros((n, len(SYMS)))
    fill_min = np.full((n, len(SYMS)), -1, dtype=int)
    for j in range(len(SYMS)):
        sig = sigma[:, j]
        oT = openT[:, j]
        low = low_g[:, :, j]
        L_all_k = {}
        for ii in range(n):
            t = grid[ii]
            use = None
            for a, a_ts in zip(ANCHORS, anchors_ts):
                if a_ts <= t < a_ts + pd.Timedelta(days=365):
                    use = a
                    break
            if use is None:
                L_chosen[ii, j] = np.nan
                continue
            k = best_k[use]
            if not (np.isfinite(sig[ii]) and sig[ii] > 0 and np.isfinite(oT[ii]) and oT[ii] > 0):
                L_chosen[ii, j] = np.nan
                continue
            L = oT[ii] * (1 - k * sig[ii])
            L_chosen[ii, j] = L
            if np.isfinite(L) and L > 0:
                row = low[ii, MO]
                hit = np.isfinite(row) & (row < L)
                if hit.any():
                    fill_min[ii, j] = int(MO[np.flatnonzero(hit)[0]])
        _ = L_all_k

    ctx = er.context(books, opens_full)
    o_df = ctx["opens"].reindex(bidx)[cols]
    r_next, _, _, fund = ctx["mkt"]
    carry_arr, expo_arr = ctx["carry_real"]
    B = books.to_numpy(dtype=float)
    nB = len(bidx)
    live = np.asarray((bidx >= START) & (bidx < END))

    carry_s = pd.Series(carry_arr, index=bidx)
    sleeve_unit_s = pd.Series(sleeve_unit_books, index=bidx)
    with np.errstate(invalid="ignore", divide="ignore"):
        ret1 = o_df / o_df.shift(1) - 1
    realized_total = (W_BOOKS * (books.shift(2) * ret1).sum(axis=1)
                      + C_REAL * carry_s.shift(1) + sleeve_unit_s.shift(1))
    vol = realized_total.rolling(360, min_periods=120).std() * np.sqrt(2190)
    s_arr = np.where(np.isnan(vol.to_numpy(dtype=float)), 1.0,
                     np.minimum(TARGET / np.where(np.isnan(vol.to_numpy(dtype=float)), 1.0,
                                                  vol.to_numpy(dtype=float)), CAP))
    s_arr = np.where(~np.isfinite(s_arr), 1.0, s_arr)
    print(f"s_total: mean_live={np.mean(s_arr[live]):.3f} min={np.min(s_arr[live]):.3f} "
          f"max={np.max(s_arr[live]):.3f}", flush=True)

    fee_b, rel_b, fee_s, rel_s = _exec_arrays(bidx, cols, v135, W_EXEC, 0.0002, 0.0005, 0.0)
    mins = np.array([er.MIN_NOTIONAL.get(c, 5.0) for c in cols])

    def run_total(sleeve_unit_arr, s_in, fee_b_in, rel_b_in, fee_s_in, rel_s_in):
        m = len(cols)
        net = np.zeros(nB)
        turn = np.zeros(nB)
        g = np.ones(nB)
        eq = np.ones(nB)
        w_all = np.zeros((nB, m))
        exec_c = np.zeros(nB)
        fund_p = np.zeros(nB)
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
                ni += float(s_in[i] * g[i] * sleeve_unit_arr[i])
            net[i] = ni
            turn[i] = float(np.abs(dw).sum())
            eq[i] = (eq[i - 1] if i else 1.0) * (1 + ni)
            w_all[i] = w
            exec_c[i] = ex_c
            fund_p[i] = fundp
            prev_w, prev_c = w.copy(), c
        return net, turn, g, eq, w_all, exec_c, fund_p

    net, turn, g_arr, eq, w_all, exec_c, fund_p = run_total(
        sleeve_unit_books, s_arr, fee_b, rel_b, fee_s, rel_s)
    summ = v110.summarize(pd.Series(net, index=bidx), pd.Series(turn, index=bidx),
                          pd.Series(g_arr, index=bidx))
    mean_s = float(np.mean(s_arr[live]))
    print("primary total-vol monthly", summ["monthly_pct"], "DD", summ["full_path_dd"],
          "mean_s", round(mean_s, 3), flush=True)

    # ---- cost-stress row ----
    r_sym_k_s, sleeve_k_s = build_sleeve(ENTRY_FEE_STRESS, EXIT_FEE_STRESS, TAKER_EXTRA)
    sleeve_s = np.zeros(n)
    for i in range(n):
        t = grid[i]
        use = None
        for a, a_ts in zip(ANCHORS, anchors_ts):
            if a_ts <= t < a_ts + pd.Timedelta(days=365):
                use = a
                break
        if use is None:
            continue
        sleeve_s[i] = sleeve_k_s[best_k[use]][i]
    sleeve_unit_grid_s = sleeve_s / S_REF
    sleeve_unit_books_s = sleeve_unit_grid_s[pos]
    sleeve_unit_s_s = pd.Series(sleeve_unit_books_s, index=bidx)
    realized_s = (W_BOOKS * (books.shift(2) * ret1).sum(axis=1)
                  + C_REAL * carry_s.shift(1) + sleeve_unit_s_s.shift(1))
    vol_s = realized_s.rolling(360, min_periods=120).std() * np.sqrt(2190)
    s_s = np.where(np.isnan(vol_s.to_numpy(dtype=float)), 1.0,
                   np.minimum(TARGET / np.where(np.isnan(vol_s.to_numpy(dtype=float)), 1.0,
                                                vol_s.to_numpy(dtype=float)), CAP))
    s_s = np.where(~np.isfinite(s_s), 1.0, s_s)
    fee_b_s, rel_b_s, fee_s_s, rel_s_s = _exec_arrays(
        bidx, cols, v135, W_EXEC, ENTRY_FEE_STRESS, EXIT_FEE_STRESS, TAKER_EXTRA)
    net_s, turn_s, g_s, eq_s, _, _, _ = run_total(
        sleeve_unit_books_s, s_s, fee_b_s, rel_b_s, fee_s_s, rel_s_s)
    summ_s = v110.summarize(pd.Series(net_s, index=bidx), pd.Series(turn_s, index=bidx),
                            pd.Series(g_s, index=bidx))
    print("stress monthly", summ_s["monthly_pct"], "DD", summ_s["full_path_dd"],
          "mean_s", round(float(np.mean(s_s[live])), 3), flush=True)

    # ---- 1m DD diagnostic for the primary row ----
    L_books = L_chosen[pos]
    fill_books = fill_min[pos]
    base_books = openT[pos]
    close_books = np.zeros((nB, 240, len(SYMS)))
    for j in range(len(SYMS)):
        close_books[:, :, j] = close_g[pos, :, j]
    first_live = int(np.flatnonzero(live)[0])
    base_eq = eq[first_live - 1] if first_live > 0 else 1.0
    if base_eq == 0:
        base_eq = 1.0
    eq_n = eq / base_eq
    peak = -np.inf
    worst_1m = 0.0
    worst_1m_time = None
    for i in range(nB):
        if not live[i]:
            continue
        run_peak = eq_n[i - 1] if i > 0 else eq_n[i]
        peak = max(peak, run_peak, eq_n[i])
        prev_eq = eq[i - 1] if i > 0 else 1.0
        w = w_all[i]
        per_event = float(s_arr[i] * g_arr[i] * 0.25 / S_REF)
        with np.errstate(invalid="ignore", divide="ignore"):
            rb = np.zeros(240)
            rs = np.zeros(240)
            for j in range(len(SYMS)):
                base = base_books[i, j]
                if not (np.isfinite(base) and base > 0):
                    continue
                cl = close_books[i, :, j]
                valid = np.isfinite(cl)
                rb[valid] += w[j] * (cl[valid] / base - 1)
                L = L_books[i, j]
                f = int(fill_books[i, j])
                if np.isfinite(L) and L > 0 and f >= 0 and per_event != 0:
                    m_idx = np.arange(240) >= f
                    vm = valid & m_idx
                    rs[vm] += per_event * (cl[vm] / L - 1)
            r_min = rb + rs
            # minute equity with full bar exec + negative funding only (as engine_real bound)
            meq = prev_eq * (1 + r_min - exec_c[i] + min(fund_p[i], 0.0))
            meq_n = meq / base_eq
            lo_min = float(np.nanmin(meq_n[np.isfinite(meq_n)])) if np.isfinite(meq_n).any() else np.nan
            if np.isfinite(lo_min) and peak > 0:
                dd = 1 - lo_min / peak
                if dd > worst_1m:
                    worst_1m = float(dd)
                    worst_1m_time = str(bidx[i])
        # bar-close DD also covered by eq path; update peak with eq already done
    # full-path close DD from summarize + worst including minutes
    eq_live = eq_n[live]
    close_dd = float(np.max(1 - eq_live / np.maximum.accumulate(eq_live))) if len(eq_live) else 0.0
    dd_1m_pct = round(100 * max(worst_1m, close_dd), 2)
    print(f"1m DD {dd_1m_pct} (close {round(100*close_dd,2)}) at {worst_1m_time}", flush=True)

    per_anchor_sleeve = []
    for a, a_ts in zip(ANCHORS, anchors_ts):
        mk_grid = (grid >= a_ts) & (grid < a_ts + pd.Timedelta(days=365))
        ssg = sleeve_unit_grid[mk_grid]
        eqs = np.cumprod(1 + ssg)
        net_pct = 100 * (float(eqs[-1]) - 1) if len(ssg) else 0.0
        dd = 100 * float(np.max(1 - eqs / np.maximum.accumulate(eqs))) if len(ssg) else 0.0
        per_anchor_sleeve.append({"anchor": a, "k": best_k[a],
                                  "sleeve_unit_net_pct": round(float(net_pct), 2),
                                  "sleeve_unit_dd_pct": round(float(dd), 2),
                                  "bars": int(mk_grid.sum())})

    replication = {
        "version": "v176_audit_replication",
        "blind": "did_not_open_research_v176_until_this_file_saved",
        "books": "cached v154 books (A+B+D)/3",
        "target": TARGET,
        "cap": CAP,
        "S_REF": S_REF,
        "governor": "20% with 2-bar lag on combined equity",
        "realism": "all on (funding, carry_real, budget, min_notional); W=60 execution",
        "spec": {
            "sleeve_unit": "v175 sleeve (0.25/event/bar sum, walk-forward k) / 1.657",
            "realized_total": "0.8*sum books[i-2]*(o[i]/o[i-1]-1)+0.6*carry[i-1]+sleeve_unit[i-1]",
            "vol": "rolling std 360 min 120 * sqrt(2190)",
            "s": "min(0.25/vol,2), 1 if NaN",
            "weights": "books 0.8*s*B*g, carry 0.6*s*g, sleeve s*g*sleeve_unit on live bars",
            "exec": "W=60 (p0@0, lo/hi 2..59, pW@60 NaN->p0; maker 0.0002 rel -/+0.001 else taker 0.0005 + drift)",
            "grid": f"{grid.min()} -> {grid.max()} ({n} 4h bars)",
        },
        "assumptions": {
            "B1": "v175 limit dip sleeve, same walk-forward k, size 0.25; selection [2020-02-01+30d, anchor-1d), applied [anchor, anchor+365d)",
            "B2": "S_REF=1.657 per assignment (=engine_real v154 mean_scale)",
            "B3": "realized_total/vol/s on books idx as spec; o=ctx opens, carry=carry_real, sleeve_unit shift 1",
            "B4": "loop mirrors engine_real FULL; governor on combined equity; budget+min_notional on",
            "B5": "stress: books maker 0.0004/taker 0.0007 +5bps taker slippage; sleeve entry 0.0004/exit 0.0007+5bps; vol/s recomputed",
            "B6": "1m DD marks books w + open sleeve (size s*g*0.25/1.657 per event, from fill minute at close/L-1) every minute vs 4h open(T); minute eq=prev*(1+R-exec+min(funding,0))",
            "B7": "1m grids keep-last dedup + within-bar ffill",
        },
        "k_selection": {a: {"best_k": best_k[a], "candidates": sel_detail[a]} for a in ANCHORS},
        "sleeve_unit_per_anchor": per_anchor_sleeve,
        "sleeve_totals": {"bars_nonzero": int((sleeve != 0).sum()),
                          "sum": float(sleeve.sum()),
                          "unit_sum": float(sleeve_unit_grid.sum())},
        "primary": {
            "monthly_pct": summ["monthly_pct"],
            "yearly": summ["yearly"],
            "full_path_dd": summ["full_path_dd"],
            "worst_year_dd": summ["worst_year_dd"],
            "mean_s": round(mean_s, 3),
            "full_path_dd_1m": dd_1m_pct,
        },
        "cost_stress": {
            "monthly_pct": summ_s["monthly_pct"],
            "yearly": summ_s["yearly"],
            "full_path_dd": summ_s["full_path_dd"],
            "worst_year_dd": summ_s["worst_year_dd"],
            "mean_s": round(float(np.mean(s_s[live])), 3),
            "spec": "book maker 0.0004/taker 0.0007 +5bps taker; sleeve maker 0.0004/taker exit 0.0007+5bps",
        },
        "params": {
            "start": str(START), "end": str(END),
            "account_usdt": er.ACCOUNT_USDT, "margin": er.MARGIN, "buffer": er.BUFFER,
            "vol": "rolling std 360 min 120 *sqrt(2190); s=min(0.25/vol,2) else 1",
            "governor": "clip((0.20-(1-eq[j]/peak540))/0.10) j=i-2 on combined eq",
        },
    }
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print("saved", OUT, flush=True)


if __name__ == "__main__":
    main()
