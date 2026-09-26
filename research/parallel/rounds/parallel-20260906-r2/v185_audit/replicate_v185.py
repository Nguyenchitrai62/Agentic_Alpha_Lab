"""v185 blind audit Part A replication.

Blind rule: does NOT read research v185 files, v185_result.json, nor the
v185 sleeve-outside-governor source, until replication.json is saved.
Independent implementation from OPENCODE_V185_AUDIT.md plus the v183 audit
base in v182_v183_audit only. May import engine_real for v154_books/context/
constants and v135 for W=60 execution (like prior audits).

A: identical to v183 except the rung notional is rn = s[i] * 0.25/4 / 1.657
(the governor g is NOT applied to the sleeve; it still scales books and
carry and is computed from total equity). Normal and stress rows: monthly,
4h DD, 1m-marked DD, worst bar, taken/TP/cancelled. Save replication.json.

Frozen blind assumptions (same as v183 audit B1-B12 except rn):
  B1 Grid G=date_range(2020-02-01 UTC, last books bar, freq 4h); t=G[i],
     T=G[i]+4h, T2=G[i]+8h. Live books bars in [START, END) from v110.
     No ML gate (like v183).
  B2 sigma(t)=std of 4h open-to-open pct changes, 360 bars ending at t,
     min 120, via opens.pct_change().rolling(360,min120).std() at G.
     Finite>0 required else no fill. TP=L*(1+sigma).
  B3 Ladder L_k=open(T)*(1-k*sigma(t)), k in (2.5,3,3.5,4). Fill f=first
     m in 16..238 with 1m low<L strict. Entry=L exactly.
  B4 Next-open exit base=open(T+4h). s_out=max(0.0002,0.25*(H-L)/O) of 1m
     minute 0 of T+4h when finite O>0 H>=L else 0.0002. Normal rung net
     y=exit/L-1-0.0002-0.0005-funding(T2); stress y=exit/L-1-0.0004-0.0007
     -0.0005-funding(T2) (extra deducted as fee, v179 style). Funding via
     funding_at_bar_open shift-2. No-fill/missing exit -> no candidate.
  B5 1m grids: drop dup open_time keep last, sort, reindex full minute grid,
     within-bar forward-fill only for O/H/L/C; volume/taker missing->0.
     Fill test on ffilled low; TP scan on ffilled high m in f+1..239 strict
     (>TP); s_out on ffilled H/L/O of row i+1 minute 0.
  B7 TP: TP=L*(1+sigma). e=first m>f with high>TP strict else INF(999)
     = next-open exit. TP net normal=TP/L-1-0.0002-0.0002, no funding, no
     extra; stress TP=TP/L-1-0.0004-0.0004, no funding, no extra. Next-open
     legs as B4. e shared both rows (TP price/trigger identical).
  B8 Vol uses UNCAPPED sleeve (no gate, concurrency-budget-free) shifted by
     2 bars per cost row: unit=sleeve/1.657, realized=
     0.8*sum books[i-2]*ret1+0.6*carry[i-1]+unit[i-2], vol=rolling
     std360 min120*sqrt(2190), s=min(0.25/vol,2) else 1. Uncapped TP-aware
     over majors (as v183).
  B9 Budget: concurrent-open (order (f, rung, col BNB..XRP);
     open_taken=count taken with e>f; take iff (open_taken+1)*rn<=1/6).
     rn = s[i]*0.25/4/1.657 (NO governor on the sleeve). Uses only
     fill-minute-known info + exits already happened (e>f iff no TP in
     (prior_f, current_f], i.e. past highs only).
  B10 Books loop mirrors engine_real FULL with W=60 execution for normal,
     stressed exec (maker 0.0004/taker 0.0007+5bps taker slippage) for
     stress; governor 20% 2-bar lag on combined equity (books AND sleeve);
     governor still scales books and carry; budget 0.95 carry-first;
     min-notional 10k; funding/carry/carry_cost as engine_real.
  B11 1m mark: rung marked from f to e (TP: minutes f..e-1 at close/L-1,
     locked at TP/L-1 gross for m>=e; non-TP: f..239 at close/L-1 like
     v179). Rung mark notional q = rn (also outside the governor).
     Minute eq=prev*(1+Rb+Rs-exec+min(funding,0)); fees/funding stay in
     bar-close payoff. DD=max over live span; worst bar=argmin net live.
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


def _load_engine_real():
    spec = importlib.util.spec_from_file_location(
        "v185_audit_engine_real", ROUND2 / "engine_real" / "engine_real.py")
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
    cols = ["open_time", "open", "high", "low", "close", "volume", "taker_buy_volume"]
    parts = [pd.read_parquet(f, columns=cols) for f in files]
    d = pd.concat(parts, ignore_index=True)
    d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
    d = d.sort_values("open_time").drop_duplicates("open_time", keep="last").set_index("open_time")
    op = d["open"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
    hi = d["high"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
    lo = d["low"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
    cl = d["close"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
    vo = d["volume"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
    tb = d["taker_buy_volume"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
    del d, parts
    return (_ffill_rows(op), _ffill_rows(hi), _ffill_rows(lo), _ffill_rows(cl),
            np.where(np.isfinite(vo), vo, 0.0), np.where(np.isfinite(tb), tb, 0.0))


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
        s: pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{s}_4h.parquet")
        .assign(t=lambda d: pd.to_datetime(d["open_time"], utc=True))
        .set_index("t")["open"].astype(float).sort_index()
        .pipe(lambda o: o[~o.index.duplicated(keep="last")])
        for s in MAJORS
    }).reindex(G)
    o1 = opens_G.shift(-1).to_numpy(dtype=float)
    o2 = opens_G.shift(-2).to_numpy(dtype=float)
    sig = opens_G.pct_change().rolling(360, min_periods=120).std().to_numpy(dtype=float)
    fund = np.column_stack([
        er.funding_at_bar_open(s, G).shift(-2).fillna(0.0).to_numpy(dtype=float)
        for s in MAJORS])

    n_min = n * 240
    mgrid = pd.date_range(T_all.min(), periods=n_min, freq="1min", tz="UTC")
    MO = np.arange(16, 239)

    print("loading 1m cubes", flush=True)
    cubes = {}
    for s in MAJORS:
        op, hi, lo, cl, vo, tb = _load_1m_cubes(s, mgrid, n)
        cubes[s] = (op, hi, lo, cl, vo, tb)
        print(f"{s} cubes ready", flush=True)

    f_v = np.full((n, mj, nr), -1, dtype=int)
    e_v = np.full((n, mj, nr), INF_EXIT, dtype=int)
    L_v = np.full((n, mj, nr), np.nan)
    r_v_n = np.zeros((n, mj, nr))
    r_v_s = np.zeros((n, mj, nr))
    tp_flag = np.zeros((n, mj, nr), dtype=bool)
    s_out_M = np.zeros((n, mj))
    for a, sym in enumerate(MAJORS):
        op, hi, lo, cl, vo, tb = cubes[sym]
        for i in range(n - 1):
            o0, h0, l0 = op[i + 1, 0], hi[i + 1, 0], lo[i + 1, 0]
            if np.isfinite(o0) and o0 > 0 and np.isfinite(h0) and np.isfinite(l0) and h0 >= l0:
                xr = (h0 - l0) / o0
                if np.isfinite(xr):
                    s_out_M[i, a] = max(0.0002, 0.25 * xr)
                else:
                    s_out_M[i, a] = 0.0002
            else:
                s_out_M[i, a] = 0.0002
        s_out_M[n - 1, a] = 0.0002
    for a in range(mj):
        op, hi, lo, cl, vo, tb = cubes[MAJORS[a]]
        sig_a = sig[:, a]
        o1_a = o1[:, a]
        o2_a = o2[:, a]
        fund_a = fund[:, a]
        for ri, kk in enumerate(RUNGS):
            with np.errstate(invalid="ignore", divide="ignore"):
                L = o1_a * (1 - kk * sig_a)
            valid_L = (np.isfinite(sig_a) & (sig_a > 0) & np.isfinite(o1_a) & (o1_a > 0)
                       & np.isfinite(L) & (L > 0))
            with np.errstate(invalid="ignore"):
                hit = valid_L[:, None] & np.isfinite(lo[:, MO]) & (lo[:, MO] < L[:, None])
            has = hit.any(axis=1)
            first = hit.argmax(axis=1)
            f = np.where(has, MO[first], -1)
            ok = has & valid_L & np.isfinite(o2_a) & (o2_a > 0) & (np.arange(n) + 1 < n)
            for i in np.flatnonzero(ok):
                fi = int(f[i])
                Li = float(L[i])
                TP = Li * (1 + float(sig_a[i]))
                m_found = INF_EXIT
                hrow = hi[i]
                for m in range(fi + 1, 240):
                    hm = hrow[m]
                    if np.isfinite(hm) and np.isfinite(TP) and hm > TP:
                        m_found = m
                        break
                f_v[i, a, ri] = fi
                L_v[i, a, ri] = Li
                if m_found != INF_EXIT:
                    e_v[i, a, ri] = m_found
                    tp_flag[i, a, ri] = True
                    r_v_n[i, a, ri] = TP / Li - 1 - MAKER - MAKER
                    r_v_s[i, a, ri] = TP / Li - 1 - MAKER_S - MAKER_S
                else:
                    e_v[i, a, ri] = INF_EXIT
                    tp_flag[i, a, ri] = False
                    exn = o2_a[i] * (1 - s_out_M[i, a])
                    r_v_n[i, a, ri] = exn / Li - 1 - MAKER - TAKER - fund_a[i]
                    r_v_s[i, a, ri] = exn / Li - 1 - MAKER_S - TAKER_S - EXTRA_S - fund_a[i]
            bad = ~ok
            f_v[bad, a, ri] = -1
            e_v[bad, a, ri] = INF_EXIT
            L_v[bad, a, ri] = np.nan
            r_v_n[bad, a, ri] = 0.0
            r_v_s[bad, a, ri] = 0.0
    fills = int((f_v >= 0).sum())
    tp_fills = int((tp_flag & (f_v >= 0)).sum())
    print(f"fills={fills} tp={tp_fills}", flush=True)
    sleeve_unc_n = RUNG_W * (r_v_n * (f_v >= 0)).sum(axis=(1, 2))
    sleeve_unc_s = RUNG_W * (r_v_s * (f_v >= 0)).sum(axis=(1, 2))

    pos = G.get_indexer(bidx)
    assert (pos >= 0).all()
    unit_books_n = pd.Series((sleeve_unc_n / S_REF)[pos], index=bidx)
    unit_books_s = pd.Series((sleeve_unc_s / S_REF)[pos], index=bidx)

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
    close_books = np.stack([cubes[s][3] for s in MAJORS], axis=2)[pos]
    f_b = f_v[pos]
    e_b = e_v[pos]
    L_b = L_v[pos]
    r_b_n = r_v_n[pos]
    r_b_s = r_v_s[pos]
    sig_b = sig[pos]

    def run_budget(r_b, s_in, fee_b_in, rel_b_in, fee_s_in, rel_s_in):
        net = np.zeros(nB)
        turn = np.zeros(nB)
        g = np.ones(nB)
        eq = np.ones(nB)
        eq_min = np.ones(nB)
        taken_total, canc_total, tp_taken = 0, 0, 0
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
            taken = []
            if live[i]:
                # v185: sleeve outside the governor (no g on rung notional)
                rn = float(s_in[i] * SIZE / nr / S_REF)
                cands = []
                for a in range(mj):
                    for ri in range(nr):
                        f = int(f_b[i, a, ri])
                        if f >= 0:
                            cands.append((f, ri, a))
                cands.sort()
                taken_exits = []
                for f, ri, a in cands:
                    e = int(e_b[i, a, ri])
                    open_n = sum(1 for ee in taken_exits if ee > f)
                    if (open_n + 1) * rn <= N_MAX + EPS:
                        taken_exits.append(e)
                        taken.append((f, ri, a, e))
                        sleeve_pnl += rn * float(r_b[i, a, ri])
                    else:
                        canc_total += 1
                taken_total += len(taken)
                tp_taken += sum(1 for (_, _, _, e) in taken if e != INF_EXIT)
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
                    # v185: mark notional also outside the governor
                    q = float(s_in[i] * SIZE / nr / S_REF)
                    marr = np.arange(240)
                    for f, ri, a, e in taken:
                        L = float(L_b[i, a, ri])
                        if not (np.isfinite(L) and L > 0) or q == 0:
                            continue
                        clv = Cm[:, a]
                        if e != INF_EXIT:
                            TPv = L * (1 + float(sig_b[i, a]))
                            pre = (marr >= f) & (marr < e) & np.isfinite(clv)
                            path2[pre] += q * (clv[pre] / L - 1)
                            post = marr >= e
                            path2[post] += q * (TPv / L - 1)
                        else:
                            vm = marr >= f
                            vv = np.isfinite(clv) & vm
                            path2[vv] += q * (clv[vv] / L - 1)
                    pm = float(np.nanmin(path2)) if np.isfinite(path2).any() else 0.0
                eq_min[i] = (eq[i - 1] if i else 1.0) * (1 + min(0.0, pm) - ex_c + min(fundp, 0.0))
            else:
                eq_min[i] = eq[i]
            prev_w, prev_c = w.copy(), c
        return net, turn, g, eq, eq_min, taken_total, canc_total, tp_taken

    net_n, turn_n, g_n, eq_n, eqmin_n, tk_n, cx_n, tp_n = run_budget(
        r_b_n, s_n, fee_b, rel_b, fee_s_, rel_s_)
    net_s, turn_s, g_s, eq_s, eqmin_s, tk_s, cx_s, tp_s = run_budget(
        r_b_s, s_s, fee_b_s, rel_b_s, fee_s_s, rel_s_s)
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

    def pack(summ, dd1, worst_t, tk, cx, tp, s_in, wi, net):
        return {
            "monthly_pct": summ["monthly_pct"],
            "yearly": summ["yearly"],
            "full_path_dd": summ["full_path_dd"],
            "worst_year_dd": summ["worst_year_dd"],
            "dd_1m_mark": dd1,
            "dd_1m_worst_bar": worst_t,
            "gate_dd": max(summ["full_path_dd"], dd1),
            "worst_bar": {"time": str(bidx[wi]), "net": float(net[wi])},
            "rungs_taken": int(tk),
            "rungs_cancelled": int(cx),
            "tp_exits_taken": int(tp),
            "mean_s": round(float(np.mean(s_in[live])), 3),
        }

    row_n = pack(summ_n, dd_n, worst_n, tk_n, cx_n, tp_n, s_n, wi_n, net_n)
    row_s = pack(summ_s, dd_s, worst_s, tk_s, cx_s, tp_s, s_s, wi_s, net_s)

    replication = {
        "version": "v185_audit_replication",
        "blind": "did_not_open_research_v185_until_this_file_saved",
        "books": "cached v154 books (A+B+D)/3",
        "target": TARGET,
        "cap": CAP,
        "S_REF": S_REF,
        "N_MAX": N_MAX,
        "governor": "20% with 2-bar lag on combined equity; scales books and carry only, NOT the sleeve",
        "rung_notional": "rn = s[i] * 0.25/4 / 1.657 (governor g NOT applied to sleeve)",
        "realism": "all on (funding, carry_real, budget, min_notional); W=60 execution",
        "spec": {
            "symbols": MAJORS,
            "rungs": list(RUNGS),
            "grid": f"{G.min()} -> {G.max()} ({n} 4h bars)",
            "trigger": "first m in 16..238 with 1m low < open(T)*(1-k*sigma(t)) strict",
            "tp": "TP=L*(1+sigma); exit TP at first m>f high>TP maker both sides no funding else next-4h-open taker exit",
            "budget": "order (f,rung,col); take iff (open_taken(e>f)+1)*rn<=1/6; rn=s*0.25/4/1.657",
            "vol": "uncapped TP-aware sleeve_unit shifted by 2",
            "mark": "rung marked f..e-1 at close/L-1, locked at TP/L-1 after; non-TP f..239 like v179; mark notional q=rn",
        },
        "assumptions": {
            "B1": "grid date_range 2020-02-01 to last books bar; live books bars; no ML gate",
            "B2": "sigma pct_change rolling 360 min120 at t; finite>0 else no candidate; TP=L*(1+sigma)",
            "B3": "L=open(T)*(1-k*sigma); f=first low<L strict; entry=L",
            "B4": "next-open exit base 4h open(T+4h); s_out from 1m minute-0 else 0.0002; stress extra deducted as fee",
            "B5": "1m keep-last dedup + within-bar ffill prices; volume/taker missing->0; TP scan f+1..239 strict",
            "B7": "TP net normal TP/L-1-0.0002-0.0002 / stress -0.0004-0.0004, no funding/extra; next-open legs as B4",
            "B8": "vol uncapped shift2 per cost; s=min(0.25/vol,2) else 1",
            "B9": "concurrent-open budget using e>f (past highs only); rn=s*0.0625/1.657 WITHOUT g",
            "B10": "loop mirrors engine_real FULL W60; governor/budget/min-notional on; g from total equity incl sleeve",
            "B11": "1m mark taken rungs only; mark notional q=rn WITHOUT g; minute eq=prev*(1+min(0,min path)-exec+min(funding,0))",
        },
        "counts_grid": {
            "fills_total": int(fills),
            "tp_fills": int(tp_fills),
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
