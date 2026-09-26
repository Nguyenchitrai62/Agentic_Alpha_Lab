"""v180 blind audit Part A replication.

Blind rule: does NOT read research/.../v180/*, v180_result.json nor
v180_model_gated_ladder.py until replication.json is saved. Independent
implementation from OPENCODE_V180_AUDIT.md (+ v178/v179 spec in
OPENCODE_V178_V179_AUDIT.md) only.
May import engine_real for v154_books/context/constants, v170 for W=60
execution, v171/v172 for grid constants (like prior audits).

Spec (frozen before running, from OPENCODE_V180_AUDIT.md):
  candidates = every v178 ladder rung fill (k 2.5/3/3.5/4; fill minute f
  in 16..238). Features at minute f-1 (all sigma-scaled as in v173 but one
  minute earlier): depth=(close(f-1)/open(T)-1)/sigma; r5=(close(f-1)/
  close(f-6)-1)/sigma; r15 with f-16; vspike=volume(f-5..f-1)/(5*mean
  volume(0..f-6)); taker15=taker_buy(f-15..f-1)/volume(f-15..f-1);
  rng=(high(f-1)-low(f-1))/close(f-1)/sigma; breadth=other assets with
  depth<=-2 at f-1; btc_depth at f-1; trend=open(T)/mean(last 42 4h opens
  incl open(T))-1; r1d=(open(T)/open(T-24h)-1)/sigma; last non-zero settled
  funding at or before t; k; asset code. y=the rung's normal-cost net return.
  Per anchor HGB(max_depth=3, lr 0.03, 300 iters, min_samples_leaf 50,
  l2 1.0, random_state 0) on candidates with T+4h < anchor-1d and
  T>=2020-03-02; a test rung stays live iff pred>0. Then the v179 budget
  loop (normal and stress costs, same gate mask for both). Report IC, kept
  counts, monthly, 4h and 1m-marked DD. Save replication.json.

Frozen blind assumptions (documented before running):
  A1 Grid G=date_range(2020-02-01 UTC, last books bar, freq 4h); t=G[i],
     T=G[i]+4h, T2=G[i]+8h. Anchors=v92.ANCHORS. Test window t in
     [anchor, anchor+365d). Train mask (T2<anchor-1d)&(T>=2020-03-02).
  A2 sigma(t)=std of 4h open-to-open pct changes, 360 bars ending at t,
     min 120, via opens.pct_change().rolling(360,min120).std() reindexed at
     G (same as v171/v179 code). Needs finite>0 else no fill/candidate.
  A3 Ladder L_k=open(T)*(1-k*sigma(t)), k in (2.5,3,3.5,4). Fill minute f=
     first m in 16..238 with 1m low<T strict (<L). Entry=L exactly.
  A4 Exit base=open(T+4h) (4h open at T2). s_out=max(0.0002,0.25*(H-L)/O)
     of 1m minute 0 of T+4h when finite with O>0 and H>=L, else 0.0002.
     Normal y=exit/L-1-0.0002-0.0005-funding(T2); stress y uses
     s_out+0.0005, maker 0.0004, taker 0.0007 (same as v179 rung_table:
     exit=o2*(1-(s_out+extra))/lim-1-maker-taker-fund, extra 0/0.0005).
     Funding cost=funding_at_bar_open shifted -2 (settlement at T2).
     No-fill/missing exit (o2 NaN/nonpositive, i+1>=n) -> no candidate.
  A5 1m grids: drop duplicate open_time keep last, sort, reindex to full
     minute grid, within-bar forward-fill only (leading NaNs stay NaN) for
     open/high/low/close separately; volume/taker_buy missing->0, no ffill.
     Fill test uses ffilled low; s_out uses ffilled H/L/O of row i+1 minute 0.
  A6 Features at fm=f-1 of holding row i (all must be knowable at fill):
     depth needs finite close(fm), openT>0, sig>0 else skip candidate.
     r5/r15 fallback 0.0; vspike fallback 1.0; taker15 fallback 0.5 clip
     [0,1]; rng fallback 0.0; breadth counts finite depth<=-2 others;
     btc_depth fallback 0.0; trend rolling42 min42 else 0.0; r1d else 0.0;
     funding feat last non-zero rate at or before t else 0.0 (zeros treated
     missing, ffill). k numeric; asset one-hot in order BNB,BTC,ETH,SOL,XRP.
  A7 Train once on normal y; live=test pred>0. Same live mask applied to
     both normal and stress budget loops.
  A8 Vol leg uses UNCAPPED sleeve (no gate, no budget) shifted by 2 bars,
     per cost row (same as v179: unit=SIZE/nr*sum rets/S_REF, realized uses
     unit.shift(2), s=min(0.25/vol,2) else 1). Payoff leg uses gated+
     budgeted sleeve: rn=s*g*0.25/4/1.657, fills sorted by (f, rung idx
     shallower first, asset col order BNB,BTC,ETH,SOL,XRP), take while
     used+rn<=N_MAX=0.05/0.30, else cancel. N_MAX=1/6.
  A9 Books loop mirrors engine_real FULL with W=60 execution (v170) for
     normal, stressed exec (maker 0.0004/taker 0.0007+5bps taker slippage)
     for stress; governor 20% 2-bar lag on combined equity; budget 0.95
     carry-first; min-notional 10k account; funding/carry/carry_cost as
     engine_real. net+=sleeve_pnl (gated+budgeted) on live bars.
  A10 1m mark as v179: for each live books bar, Cm=1m closes of holding row
     gi, path=((Cm/o1-1)*w).sum + rn*seg for TAKEN rungs (seg[f:]=Cm/L-1),
     eq_min=prev_eq*(1+min(0,min path)-ex+min(fnd,0)); dd_1m from min(e,em)
     vs running max(e); worst bar argmax. Gate DD=max(4h DD,1m DD).
  A11 Bars outside anchor test windows -> no live rungs -> sleeve 0.
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
SHORT = ["BNB", "BTC", "ETH", "SOL", "XRP"]
RUNGS = (2.5, 3.0, 3.5, 4.0)
GRID_START = pd.Timestamp("2020-02-01 00:00:00+00:00")
TRAIN_T_MIN = pd.Timestamp("2020-03-02 00:00:00+00:00")
SIZE = 0.25
S_REF = 1.657
N_MAX = 0.05 / 0.30
TARGET = 0.25
CAP = 2.0
W_EXEC = 60
MAKER, TAKER = 0.0002, 0.0005
MAKER_S, TAKER_S, EXTRA_S = 0.0004, 0.0007, 0.0005
FEATURE_COLS = ["depth", "r5", "r15", "vspike", "taker15", "rng",
                "breadth", "btc_depth", "trend", "r1d", "funding", "k",
                "asset_BNB", "asset_BTC", "asset_ETH", "asset_SOL", "asset_XRP"]


def _load_engine_real():
    spec = importlib.util.spec_from_file_location(
        "v180_audit_engine_real", ROUND2 / "engine_real" / "engine_real.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_v170(er):
    spec = importlib.util.spec_from_file_location(
        "v180_audit_v170", ROUND2 / "v170" / "v170_exec_window.py")
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


def _stress_exec(fee_b, rel_b, fee_s, rel_s):
    maker_b = fee_b == 0.0002
    maker_s = fee_s == 0.0002
    fee_b2 = np.where(maker_b, 0.0004, 0.0007)
    fee_s2 = np.where(maker_s, 0.0004, 0.0007)
    rel_b2 = np.where(maker_b, rel_b, rel_b + 0.0005)
    rel_s2 = np.where(maker_s, rel_s, rel_s - 0.0005)
    return fee_b2, rel_b2, fee_s2, rel_s2


def main():
    from sklearn.ensemble import HistGradientBoostingRegressor

    er = _load_engine_real()
    v170 = _load_v170(er)
    v110 = er.v144.v110
    v92 = er.v144.v110.v92
    ANCHORS = list(v92.ANCHORS)
    START, END = v110.START, v110.END
    PD = er.v144.PD
    print("anchors", ANCHORS, "live", START, "->", END, flush=True)

    books, opens_full = er.v154_books()
    books = books.sort_index()
    opens_full = opens_full.sort_index()
    bidx = books.index
    bcols = list(books.columns)
    assert set(bcols) == set(SYMS), f"books cols {bcols} vs {SYMS}"
    # reorder maps: our SYMS order is alphabetical; books should match
    col_idx = [bcols.index(s) for s in SYMS]
    print("books cols", bcols, flush=True)
    last_books = bidx.max()
    G = pd.date_range(GRID_START, last_books, freq="4h", tz="UTC")
    n = len(G)
    print(f"grid {n} bars {G.min()} -> {G.max()}", flush=True)

    # ---- 4h opens/sigma/funding for rungs (v179 style) ----
    opens_df = {}
    for s in SYMS:
        k = pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{s}_4h.parquet")
        ot = pd.to_datetime(k["open_time"], utc=True)
        o = pd.Series(k["open"].to_numpy(dtype=float), index=ot).sort_index()
        o = o[~o.index.duplicated(keep="last")]
        opens_df[s] = o
    opens_G = pd.DataFrame({s: opens_df[s].reindex(G) for s in SYMS})
    o1 = opens_G.shift(-1).to_numpy(dtype=float)  # open(T)
    o2 = opens_G.shift(-2).to_numpy(dtype=float)  # open(T+4h)
    sig = opens_G.pct_change().rolling(360, min_periods=120).std().to_numpy(dtype=float)
    fund = np.column_stack([
        er.funding_at_bar_open(s, G).shift(-2).fillna(0.0).to_numpy(dtype=float)
        for s in SYMS])
    T_all = G + pd.Timedelta(hours=4)
    T2_all = G + pd.Timedelta(hours=8)

    # trend / r1d helpers from full history
    trend_base = np.zeros((n, len(SYMS)))
    open_m24 = np.zeros((n, len(SYMS)))
    for j, s in enumerate(SYMS):
        o = opens_df[s]
        trend_base[:, j] = o.rolling(42, min_periods=42).mean().reindex(T_all).to_numpy(dtype=float)
        open_m24[:, j] = o.reindex(T_all - pd.Timedelta(hours=24)).to_numpy(dtype=float)

    # funding feature: last non-zero at or before t
    fund_feat = np.zeros((n, len(SYMS)))
    for j, s in enumerate(SYMS):
        f = pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{s}_funding.parquet")
        ft = pd.to_datetime(f["fundingTime"], utc=True)
        fr = f["fundingRate"].to_numpy(dtype=float)
        fser = pd.Series(fr, index=ft).sort_index()
        fser = fser[~fser.index.duplicated(keep="last")]
        fser_nz = fser.mask(fser == 0.0).ffill()
        fund_feat[:, j] = fser_nz.reindex(G, method="ffill").fillna(0.0).to_numpy(dtype=float)

    # ---- 1m minute grid ----
    n_min = n * 240
    mgrid = pd.date_range(T_all.min(), periods=n_min, freq="1min", tz="UTC")
    assert len(mgrid) == n_min
    MO = np.arange(16, 239)
    btc_j = SYMS.index("BTCUSDT")

    # close cube for breadth/btc_depth + 1m mark
    print("loading close cube for breadth", flush=True)
    close_g = np.zeros((n, 240, len(SYMS)))
    for j, s in enumerate(SYMS):
        if s == "BTCUSDT":
            files = sorted(glob.glob(str(ROOT / "data/raw/btc_intraday_20260924/klines_1m_20*.parquet")))
        else:
            files = sorted(glob.glob(str(ROOT / f"data/raw/majors_intraday_20260924/{s}_1m_20*.parquet")))
        assert files, f"no 1m for {s}"
        parts = [pd.read_parquet(f, columns=["open_time", "close"]) for f in files]
        d = pd.concat(parts, ignore_index=True)
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        d = d.sort_values("open_time").drop_duplicates("open_time", keep="last").set_index("open_time")
        co = d["close"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        close_g[:, :, j] = _ffill_rows(co)
        print(f"{s} close done", flush=True)
        del d, parts, co

    # ---- per-asset rung fills + features ----
    nr = len(RUNGS)
    lims = np.full((nr, n, len(SYMS)), np.nan)
    fmins = np.full((nr, n, len(SYMS)), -1, dtype=int)
    rets_n = np.zeros((nr, n, len(SYMS)))
    rets_s = np.zeros((nr, n, len(SYMS)))

    rec_i, rec_j, rec_r = [], [], []
    rec_k, rec_f, rec_y, rec_ys = [], [], [], []
    F = {c: [] for c in FEATURE_COLS}

    for j, sym in enumerate(SYMS):
        if sym == "BTCUSDT":
            files = sorted(glob.glob(str(ROOT / "data/raw/btc_intraday_20260924/klines_1m_20*.parquet")))
        else:
            files = sorted(glob.glob(str(ROOT / f"data/raw/majors_intraday_20260924/{sym}_1m_20*.parquet")))
        cols1m = ["open_time", "open", "high", "low", "close", "volume", "taker_buy_volume"]
        parts = [pd.read_parquet(f, columns=cols1m) for f in files]
        d = pd.concat(parts, ignore_index=True)
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        d = d.sort_values("open_time").drop_duplicates("open_time", keep="last").set_index("open_time")
        op = d["open"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        hi = d["high"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        lo = d["low"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        cl = d["close"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        vo = d["volume"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        tb = d["taker_buy_volume"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        op = _ffill_rows(op)
        hi = _ffill_rows(hi)
        lo = _ffill_rows(lo)
        cl = _ffill_rows(cl)
        vo = np.where(np.isfinite(vo), vo, 0.0)
        tb = np.where(np.isfinite(tb), tb, 0.0)
        print(f"{sym} 1m cubes ready", flush=True)

        # s_out per bar for this asset
        s_out = np.full(n, 0.0002)
        for i in range(n - 1):
            o0, h0, l0 = op[i + 1, 0], hi[i + 1, 0], lo[i + 1, 0]
            if np.isfinite(o0) and o0 > 0 and np.isfinite(h0) and np.isfinite(l0) and h0 >= l0:
                xr = (h0 - l0) / o0
                if np.isfinite(xr):
                    s_out[i] = max(0.0002, 0.25 * xr)
        # last bar stays 0.0002 (no exit)

        sig_j = sig[:, j]
        o1_j = o1[:, j]
        o2_j = o2[:, j]
        fund_j = fund[:, j]
        low_j = lo
        n_cand_sym = 0
        for r, k in enumerate(RUNGS):
            with np.errstate(invalid="ignore", divide="ignore"):
                L = o1_j * (1 - k * sig_j)
            valid_L = (np.isfinite(sig_j) & (sig_j > 0) & np.isfinite(o1_j) & (o1_j > 0)
                       & np.isfinite(L) & (L > 0))
            with np.errstate(invalid="ignore"):
                hit = valid_L[:, None] & np.isfinite(low_j[:, MO]) & (low_j[:, MO] < L[:, None])
            has = hit.any(axis=1)
            first = hit.argmax(axis=1)
            f = np.where(has, MO[first], -1)
            # exit validity
            ok = has & valid_L & np.isfinite(o2_j) & (o2_j > 0) & (np.arange(n) + 1 < n)
            # rets
            rn = np.zeros(n)
            rs = np.zeros(n)
            idx_ok = np.flatnonzero(ok)
            rn[idx_ok] = (o2_j[idx_ok] * (1 - s_out[idx_ok]) / L[idx_ok] - 1
                          - MAKER - TAKER - fund_j[idx_ok])
            rs[idx_ok] = (o2_j[idx_ok] * (1 - (s_out[idx_ok] + EXTRA_S)) / L[idx_ok] - 1
                          - MAKER_S - TAKER_S - fund_j[idx_ok])
            rn[~np.isfinite(rn)] = 0.0
            rs[~np.isfinite(rs)] = 0.0
            # store (only where ok else f=-1 already? keep f for filled even if exit invalid? No: candidate needs valid y)
            fmins[r, :, j] = np.where(ok, f, -1)
            lims[r, :, j] = np.where(ok, L, np.nan)
            rets_n[r, :, j] = np.where(ok, rn, 0.0)
            rets_s[r, :, j] = np.where(ok, rs, 0.0)

            # features for each valid candidate
            for i in idx_ok:
                m = int(f[i])
                if m < 16 or m > 238:
                    continue
                fm = m - 1
                c_fm = cl[i, fm]
                if not (np.isfinite(c_fm) and np.isfinite(o1_j[i]) and o1_j[i] > 0
                        and np.isfinite(sig_j[i]) and sig_j[i] > 0):
                    # skip candidate (no depth) -> also zero its rets so it never trades
                    fmins[r, i, j] = -1
                    lims[r, i, j] = np.nan
                    rets_n[r, i, j] = 0.0
                    rets_s[r, i, j] = 0.0
                    continue
                depth = (c_fm / o1_j[i] - 1) / sig_j[i]
                if not np.isfinite(depth):
                    fmins[r, i, j] = -1
                    lims[r, i, j] = np.nan
                    rets_n[r, i, j] = 0.0
                    rets_s[r, i, j] = 0.0
                    continue
                c5 = cl[i, fm - 5]
                if np.isfinite(c5) and c5 > 0:
                    r5 = (c_fm / c5 - 1) / sig_j[i]
                else:
                    r5 = 0.0
                c15 = cl[i, fm - 15]
                if np.isfinite(c15) and c15 > 0:
                    r15 = (c_fm / c15 - 1) / sig_j[i]
                else:
                    r15 = 0.0
                if not np.isfinite(r5):
                    r5 = 0.0
                if not np.isfinite(r15):
                    r15 = 0.0
                v_num = float(vo[i, fm - 4:fm + 1].sum())
                v_den_win = vo[i, 0:fm - 4]
                v_den = 5 * float(v_den_win.mean()) if (fm - 4) > 0 else np.nan
                if np.isfinite(v_num) and np.isfinite(v_den) and v_den > 0:
                    vspike = v_num / v_den
                else:
                    vspike = 1.0
                if not np.isfinite(vspike):
                    vspike = 1.0
                tb_num = float(tb[i, fm - 14:fm + 1].sum())
                v15 = float(vo[i, fm - 14:fm + 1].sum())
                if np.isfinite(tb_num) and np.isfinite(v15) and v15 > 0:
                    taker15 = float(np.clip(tb_num / v15, 0.0, 1.0))
                else:
                    taker15 = 0.5
                h_fm, l_fm = hi[i, fm], lo[i, fm]
                if (np.isfinite(h_fm) and np.isfinite(l_fm) and c_fm > 0
                        and h_fm >= l_fm and np.isfinite(sig_j[i]) and sig_j[i] > 0):
                    rng = (h_fm - l_fm) / c_fm / sig_j[i]
                else:
                    rng = 0.0
                if not np.isfinite(rng):
                    rng = 0.0
                br = 0
                for oj in range(len(SYMS)):
                    if oj == j:
                        continue
                    co_o = close_g[i, fm, oj]
                    oT_o = o1[i, oj]
                    s_o = sig[i, oj]
                    if (np.isfinite(co_o) and np.isfinite(oT_o) and oT_o > 0
                            and np.isfinite(s_o) and s_o > 0):
                        dd = (co_o / oT_o - 1) / s_o
                        if np.isfinite(dd) and dd <= -2:
                            br += 1
                co_b = close_g[i, fm, btc_j]
                if (np.isfinite(co_b) and np.isfinite(o1[i, btc_j]) and o1[i, btc_j] > 0
                        and np.isfinite(sig[i, btc_j]) and sig[i, btc_j] > 0):
                    btc_depth = (co_b / o1[i, btc_j] - 1) / sig[i, btc_j]
                    if not np.isfinite(btc_depth):
                        btc_depth = 0.0
                else:
                    btc_depth = 0.0
                tb42 = trend_base[i, j]
                if np.isfinite(tb42) and tb42 > 0 and np.isfinite(o1_j[i]) and o1_j[i] > 0:
                    trend = o1_j[i] / tb42 - 1
                else:
                    trend = 0.0
                if not np.isfinite(trend):
                    trend = 0.0
                om24 = open_m24[i, j]
                if (np.isfinite(om24) and om24 > 0 and np.isfinite(o1_j[i]) and o1_j[i] > 0
                        and np.isfinite(sig_j[i]) and sig_j[i] > 0):
                    r1d = (o1_j[i] / om24 - 1) / sig_j[i]
                else:
                    r1d = 0.0
                if not np.isfinite(r1d):
                    r1d = 0.0
                y = float(rets_n[r, i, j])
                ys = float(rets_s[r, i, j])
                if not np.isfinite(y):
                    fmins[r, i, j] = -1
                    lims[r, i, j] = np.nan
                    rets_n[r, i, j] = 0.0
                    rets_s[r, i, j] = 0.0
                    continue
                rec_i.append(i)
                rec_j.append(j)
                rec_r.append(r)
                rec_k.append(float(k))
                rec_f.append(m)
                rec_y.append(y)
                rec_ys.append(ys)
                F["depth"].append(float(depth))
                F["r5"].append(float(r5))
                F["r15"].append(float(r15))
                F["vspike"].append(float(vspike))
                F["taker15"].append(float(taker15))
                F["rng"].append(float(rng))
                F["breadth"].append(float(br))
                F["btc_depth"].append(float(btc_depth))
                F["trend"].append(float(trend))
                F["r1d"].append(float(r1d))
                F["funding"].append(float(fund_feat[i, j]))
                F["k"].append(float(k))
                for sj, sn in enumerate(SHORT):
                    F[f"asset_{sn}"].append(1.0 if sj == j else 0.0)
                n_cand_sym += 1
        print(f"{sym}: candidates={n_cand_sym}", flush=True)
        del op, hi, lo, cl, vo, tb, d, parts

    rec_i = np.asarray(rec_i, dtype=int)
    rec_j = np.asarray(rec_j, dtype=int)
    rec_r = np.asarray(rec_r, dtype=int)
    rec_k = np.asarray(rec_k, dtype=float)
    rec_f = np.asarray(rec_f, dtype=int)
    rec_y = np.asarray(rec_y, dtype=float)
    rec_ys = np.asarray(rec_ys, dtype=float)
    X = np.column_stack([np.asarray(F[c], dtype=float) for c in FEATURE_COLS])
    t_arr = G[rec_i]
    T_arr = T_all[rec_i]
    T2_arr = T2_all[rec_i]
    n_pts = len(rec_y)
    print(f"total candidates={n_pts}", flush=True)

    anchors_ts = [pd.Timestamp(a, tz="UTC") for a in ANCHORS]
    # ---- per-anchor HGB ----
    live_mask = np.zeros(n_pts, dtype=bool)
    per_anchor = []
    ic_all, taken_pred_all = {}, {}
    train_n_all, test_n_all = {}, {}
    for a, a_ts in zip(ANCHORS, anchors_ts):
        train_mask = (T2_arr < a_ts - pd.Timedelta(days=1)) & (T_arr >= TRAIN_T_MIN)
        test_mask = (t_arr >= a_ts) & (t_arr < a_ts + pd.Timedelta(days=365))
        tr_idx = np.flatnonzero(train_mask)
        te_idx = np.flatnonzero(test_mask)
        train_n_all[a] = int(len(tr_idx))
        test_n_all[a] = int(len(te_idx))
        if len(tr_idx) == 0 or len(te_idx) == 0:
            ic = None
            pred_te = np.zeros(len(te_idx))
        else:
            mdl = HistGradientBoostingRegressor(
                max_depth=3, learning_rate=0.03, max_iter=300,
                min_samples_leaf=50, l2_regularization=1.0, random_state=0)
            mdl.fit(X[tr_idx], rec_y[tr_idx])
            pred_te = mdl.predict(X[te_idx])
            s_pred = pd.Series(pred_te)
            s_y = pd.Series(rec_y[te_idx])
            if len(te_idx) >= 3 and float(s_pred.std()) > 0 and float(s_y.std()) > 0:
                ic_v = float(s_pred.corr(s_y, method="spearman"))
                ic = ic_v if np.isfinite(ic_v) else None
            else:
                ic = None
            live_te = pred_te > 0
            live_mask[te_idx[live_te]] = True
        ic_all[a] = ic
        taken_pred_all[a] = int(live_mask[te_idx].sum()) if len(te_idx) else 0
        print(f"anchor {a}: train={len(tr_idx)} test={len(te_idx)} ic={ic} live={taken_pred_all[a]}", flush=True)

    # live lookup set for budget loop: (gi, rung, asset)
    live_set = set()
    for ii in np.flatnonzero(live_mask):
        live_set.add((int(rec_i[ii]), int(rec_r[ii]), int(rec_j[ii])))
    print(f"live rungs total={len(live_set)} / {n_pts}", flush=True)

    # ---- uncapped sleeve for vol (per cost row, no gate) ----
    sleeve_uncapped_n = (SIZE / nr) * rets_n.sum(axis=(0, 2))
    sleeve_uncapped_s = (SIZE / nr) * rets_s.sum(axis=(0, 2))
    unit_G_n = sleeve_uncapped_n / S_REF
    unit_G_s = sleeve_uncapped_s / S_REF

    pos = G.get_indexer(bidx)
    assert (pos >= 0).all(), "books times must exist in grid"
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
        realized = (er.v144.v99.W_BOOKS * (books.shift(2) * ret1).sum(axis=1)
                    + er.v144.v99.W_CARRY * er.v144.v99.CARRY_LEV * carry_s.shift(1)
                    + unit_s.shift(2))
        vol = realized.rolling(360, min_periods=120).std() * np.sqrt(PD * 365)
        s_arr = np.where(np.isnan(vol.to_numpy(dtype=float)), 1.0,
                         np.minimum(TARGET / np.where(np.isnan(vol.to_numpy(dtype=float)), 1.0,
                                                      vol.to_numpy(dtype=float)), CAP))
        return np.where(~np.isfinite(s_arr), 1.0, s_arr)

    s_n = vol_s_from_unit(unit_books_n)
    s_s = vol_s_from_unit(unit_books_s)

    ex60, _ = v170.exec_costs_w(bidx, bcols, W_EXEC)
    fee_b, rel_b, fee_s, rel_s = ex60
    fee_b_s, rel_b_s, fee_s_s, rel_s_s = _stress_exec(fee_b, rel_b, fee_s, rel_s)
    mins = np.array([er.MIN_NOTIONAL.get(c, 5.0) for c in bcols])
    o1_books = o_df.shift(-1).to_numpy(dtype=float)

    # closes per books bar for 1m mark: close_g[pos]
    close_books = close_g[pos]
    # lims/fmins/rets on G; need gpos map
    gpos = pos  # books idx i -> G index gi

    def run_budget(rets, s_in, fee_b_in, rel_b_in, fee_s_in, rel_s_in):
        nB_l = nB
        net = np.zeros(nB_l)
        turn = np.zeros(nB_l)
        g = np.ones(nB_l)
        eq = np.ones(nB_l)
        eq_min = np.ones(nB_l)
        w_all = np.zeros((nB_l, len(bcols)))
        exec_c = np.zeros(nB_l)
        fund_p = np.zeros(nB_l)
        taken_total, cancelled_total = 0, 0
        prev_w = np.zeros(len(bcols))
        prev_c = 0.0
        for i in range(nB_l):
            if i >= 2:
                jj = i - 2
                peak = eq[max(0, jj - 90 * PD + 1): jj + 1].max()
                g[i] = float(np.clip((0.20 - (1 - eq[jj] / peak)) / 0.10, 0.0, 1.0))
            if live[i]:
                w = er.v144.v99.W_BOOKS * s_in[i] * B[i] * g[i]
                c = er.v144.v99.W_CARRY * er.v144.v99.CARRY_LEV * s_in[i] * g[i]
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
            sleeve_pnl, taken = 0.0, []
            gi = int(gpos[i])
            if live[i] and gi >= 0:
                rn = float(s_in[i] * g[i] * SIZE / nr / S_REF)
                fills = []
                for r in range(nr):
                    for a in range(len(SYMS)):
                        # map SYMS asset a to books col? assume same order; verify via col_idx
                        f = int(fmins[r, gi, a])
                        if f >= 0 and (gi, r, a) in live_set:
                            fills.append((f, r, a))
                fills.sort()
                used = 0.0
                for f, r, a in fills:
                    if used + rn <= N_MAX + 1e-12:
                        used += rn
                        taken.append((f, r, a))
                        sleeve_pnl += rn * float(rets[r, gi, a])
                    else:
                        cancelled_total += 1
                taken_total += len(taken)
            ni = gross - ex_c + fundp + carry_p - carry_c + sleeve_pnl
            net[i] = ni
            turn[i] = float(np.abs(dw).sum())
            eq[i] = (eq[i - 1] if i else 1.0) * (1 + ni)
            w_all[i] = w
            exec_c[i] = ex_c
            fund_p[i] = fundp
            if live[i]:
                Cm = close_books[i].astype(float)
                with np.errstate(invalid="ignore", divide="ignore"):
                    path = ((Cm / o1_books[i] - 1) * w).sum(axis=1)
                    for f, r, a in taken:
                        L = float(lims[r, gi, a])
                        if np.isfinite(L) and L > 0:
                            seg = np.zeros(240)
                            seg[f:] = Cm[f:, a] / L - 1
                            path += float(s_in[i] * g[i] * SIZE / nr / S_REF) * seg
                    pm = float(np.nanmin(path)) if np.isfinite(path).any() else 0.0
                eq_min[i] = (eq[i - 1] if i else 1.0) * (1 + min(0.0, pm) - ex_c + min(fundp, 0.0))
            else:
                eq_min[i] = eq[i]
            prev_w, prev_c = w.copy(), c
        return net, turn, g, eq, eq_min, taken_total, cancelled_total

    net_n, turn_n, g_n, eq_n, eq_min_n, taken_n, canc_n = run_budget(
        rets_n, s_n, fee_b, rel_b, fee_s, rel_s)
    net_s, turn_s, g_s, eq_s, eq_min_s, taken_s, canc_s = run_budget(
        rets_s, s_s, fee_b_s, rel_b_s, fee_s_s, rel_s_s)

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

    dd_n, worst_n = dd_1m(eq_n, eq_min_n)
    dd_s, worst_s = dd_1m(eq_s, eq_min_s)

    per_anchor_live = []
    for a, a_ts in zip(ANCHORS, anchors_ts):
        mk = (t_arr >= a_ts) & (t_arr < a_ts + pd.Timedelta(days=365))
        per_anchor_live.append({
            "anchor": a,
            "train_points": int(train_n_all[a]),
            "test_points": int(test_n_all[a]),
            "ic_spearman": ic_all[a],
            "live_pred_pos": int(taken_pred_all[a]),
        })

    replication = {
        "version": "v180_audit_replication",
        "blind": "did_not_open_research_v180_until_this_file_saved",
        "books": "cached v154 books (A+B+D)/3",
        "target": TARGET,
        "cap": CAP,
        "S_REF": S_REF,
        "N_MAX": N_MAX,
        "governor": "20% with 2-bar lag on combined equity",
        "realism": "all on (funding, carry_real, budget, min_notional); W=60 execution",
        "model": {"name": "HistGradientBoostingRegressor", "max_depth": 3,
                  "learning_rate": 0.03, "max_iter": 300,
                  "min_samples_leaf": 50, "l2_regularization": 1.0,
                  "random_state": 0},
        "feature_columns": FEATURE_COLS,
        "spec": {
            "symbols": SYMS,
            "rungs": list(RUNGS),
            "grid": f"{G.min()} -> {G.max()} ({n} 4h bars)",
            "holding_bar": "T = t + 4h",
            "trigger": "first m in 16..238 with 1m low < open(T)*(1-k*sigma(t)) strict",
            "features": "at minute f-1 as assignment (depth/r5/r15/vspike/taker15/rng/breadth/btc_depth/trend/r1d/funding/k/one-hot)",
            "y": "normal-cost rung net: exit/L-1-0.0002-0.0005-funding(T+4h), exit=open(T+4h)*(1-s_out)",
            "train": "T+4h < anchor-1d and T >= 2020-03-02",
            "test": "t in [anchor, anchor+365d), live iff pred>0",
            "budget": "per holding bar sort (fill minute, shallower rung, col order BNB,BTC,ETH,SOL,XRP), rn=s*g*0.25/4/1.657, take while cum<=0.05/0.30",
            "vol": "uncapped sleeve_unit shifted by 2 bars, s=min(0.25/vol,2) else 1",
            "gate_mask": "same ML live mask for normal and stress payoff legs",
        },
        "assumptions": {
            "A1": "grid date_range 2020-02-01 to last books bar; v92 anchors; half-open test windows",
            "A2": "sigma pct_change rolling 360 min120 at t; finite>0 else no candidate",
            "A3": "L=open(T)*(1-k*sigma); f=first low<L strict; entry=L",
            "A4": "exit base 4h open(T+4h); s_out from 1m minute-0 else 0.0002; stress s_out+0.0005/maker0.0004/taker0.0007; funding via funding_at_bar_open shift-2",
            "A5": "1m keep-last dedup + within-bar ffill prices; volume/taker missing->0",
            "A6": "features at f-1 with fallbacks (r5/r15/rng/trend/r1d 0, vspike 1, taker15 0.5, btc_depth 0); depth invalid -> skip candidate",
            "A7": "train on normal y once; same live mask for both costs",
            "A8": "vol uncapped shift2 per cost; payoff gated+budgeted N_MAX=1/6",
            "A9": "loop mirrors engine_real FULL W60; governor/budget/min-notional on",
            "A10": "1m mark uses taken rungs only, minute eq=prev*(1+min(0,min path)-exec+min(funding,0))",
            "A11": "bars outside test windows -> no live rungs",
        },
        "candidates_total": int(n_pts),
        "live_total": int(len(live_set)),
        "per_anchor": per_anchor_live,
        "primary_normal": {
            "monthly_pct": summ_n["monthly_pct"],
            "yearly": summ_n["yearly"],
            "full_path_dd": summ_n["full_path_dd"],
            "worst_year_dd": summ_n["worst_year_dd"],
            "dd_1m_mark": dd_n,
            "dd_1m_worst_bar": worst_n,
            "gate_dd": max(summ_n["full_path_dd"], dd_n),
            "rungs_taken": int(taken_n),
            "rungs_cancelled": int(canc_n),
            "mean_s": round(float(np.mean(s_n[live])), 3),
        },
        "stress": {
            "monthly_pct": summ_s["monthly_pct"],
            "yearly": summ_s["yearly"],
            "full_path_dd": summ_s["full_path_dd"],
            "worst_year_dd": summ_s["worst_year_dd"],
            "dd_1m_mark": dd_s,
            "dd_1m_worst_bar": worst_s,
            "gate_dd": max(summ_s["full_path_dd"], dd_s),
            "rungs_taken": int(taken_s),
            "rungs_cancelled": int(canc_s),
            "mean_s": round(float(np.mean(s_s[live])), 3),
            "spec": "books maker 0.0004/taker 0.0007 +5bps taker; sleeve maker 0.0004/taker 0.0007 +5bps in s_out",
        },
        "params": {
            "start": str(START), "end": str(END),
            "account_usdt": er.ACCOUNT_USDT, "margin": er.MARGIN, "buffer": er.BUFFER,
        },
    }
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print("saved", OUT, flush=True)


if __name__ == "__main__":
    main()
