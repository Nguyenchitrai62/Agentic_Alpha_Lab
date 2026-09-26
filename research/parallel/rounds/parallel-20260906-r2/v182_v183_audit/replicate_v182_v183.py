"""v182 + v183 blind audit Part A replication.

Blind rule: does NOT read research/.../v182/*, v183/*, v182_result.json nor
v183_result.json, nor v182_pooled_gate.py / v183_tp_exit_open_budget.py, until
replication.json is saved. Independent implementation from
OPENCODE_V182_V183_AUDIT.md (+ v179 re-audit + v180 audit specs) only.
May import engine_real for v154_books/context/constants and v135 for W=60
execution (like prior audits).

A1 (v182): candidates = ladder rung fills (k 2.5/3/3.5/4) of 11 assets (five
  majors + DOGE/ADA/LINK/LTC/AVAX/TRX; 1m in data/raw/alts_intraday_20260926
  for alts, majors/btc 1m as v179/v180; 4h opens/funding from xs_universe).
  Target = normal-cost net rung return. Features at minute f-1 exactly as
  v180 EXCEPT: no asset code; breadth = number of the FIVE MAJORS with
  (close/open(T)-1)/sigma <= -2 at minute f-1 (same for every candidate,
  including the candidate itself if it is a major); btc_depth = BTC depth
  at f-1. HGB(max_depth 3, lr 0.03, 300 iters, min_samples_leaf 50, l2 1.0,
  random_state 0) per anchor on pooled candidates with T+4h < anchor-1d and
  T >= 2020-03-02; majors' test rungs live iff pred > 0; then the v179 loop
  (total cap 1/6), normal and stress rows. Report IC on majors' test fills,
  kept, monthly, 4h and 1m DD.
A2 (v183): ladder as v179 (5 majors) but after a fill at minute f a
  take-profit sell rests at TP = L*(1+sigma); exit at TP in the first minute
  m > f with 1m high > TP (maker fee both sides, no funding); else the usual
  next-4h-open taker exit. Budget: fills in (minute, rung, asset) order; take
  a fill iff (number of taken rungs of this bar still open at that minute,
  i.e. exit minute > fill minute, + 1) * rn <= 1/6; rn = s*g*0.25/4/1.657.
  1m mark: rung marked from fill minute to exit minute, locked after. Normal
  and stress rows: monthly, 4h DD, 1m DD, worst bar, taken, TP exits.

Frozen blind assumptions (documented before running):
  B1 Grid G=date_range(2020-02-01 UTC, last books bar, freq 4h); t=G[i],
     T=G[i]+4h, T2=G[i]+8h. Anchors=v92.ANCHORS (5). Test t in
     [anchor, anchor+365d). Train (T2<anchor-1d)&(T>=2020-03-02). Pooled over
     11 assets for v182; majors-only for v183.
  B2 sigma(t)=std of 4h open-to-open pct changes, 360 bars ending at t,
     min 120, via opens.pct_change().rolling(360,min120).std() at G (same as
     v179/v180). Finite>0 required else no fill/candidate. TP=L*(1+sigma).
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
  B6 v182 features at fm=f-1 (v180 A6 fallbacks): depth/r5/r15/vspike/
     taker15/rng per-candidate asset; breadth counts FIVE MAJORS depth<=-2
     at same fm (includes self if major); btc_depth=BTC depth at fm;
     trend/r1d/funding/k per-candidate asset; NO asset code (12 cols).
     Depth invalid -> skip candidate (zero rets). Train once on normal y
     pooled; live=majors test pred>0. Same live mask both cost rows. IC =
     spearman(pred, normal y) on majors test fills per anchor.
  B7 v183 TP: TP=L*(1+sigma). e=first m>f with high>TP strict else INF(999)
     = next-open exit. TP net normal=TP/L-1-0.0002-0.0002, no funding, no
     extra; stress TP=TP/L-1-0.0004-0.0004, no funding, no extra. Next-open
     legs as B4. e shared both rows (TP price/trigger identical).
  B8 Vol uses UNCAPPED sleeve (no gate, concurrency-budget-free) shifted by
     2 bars per cost row (v179 C7): unit=sleeve/1.657, realized=
     0.8*sum books[i-2]*ret1+0.6*carry[i-1]+unit[i-2], vol=rolling
     std360 min120*sqrt(2190), s=min(0.25/vol,2) else 1. v182 uncapped over
     majors (traded universe); v183 uncapped TP-aware over majors.
  B9 Budget v182: v179 total-only (order (f, shallower rung, col
     BNB,BTC,ETH,SOL,XRP), rn=s*g*0.0625/1.657, take while cum+rn<=1/6).
     Budget v183: concurrent-open (order (f, rung, col BNB..XRP);
     open_taken=count taken with e>f; take iff (open_taken+1)*rn<=1/6).
     Both use only fill-minute-known info + exits already happened
     (e>f iff no TP in (prior_f, current_f], i.e. past highs only).
  B10 Books loop mirrors engine_real FULL with W=60 execution (v135) for
     normal, stressed exec (maker 0.0004/taker 0.0007+5bps taker slippage)
     for stress; governor 20% 2-bar lag on combined equity; budget 0.95
     carry-first; min-notional 10k; funding/carry/carry_cost as engine_real.
  B11 1m mark: v182 as v179 (taken rungs from f at close/L-1 to end of bar).
     v183: rung marked from f to e (TP: minutes f..e-1 at close/L-1, locked
     at TP/L-1 gross for m>=e; non-TP: f..239 at close/L-1 like v179).
     Minute eq=prev*(1+Rb+Rs-exec+min(funding,0)); fees/funding stay in
     bar-close payoff. DD=max over live span; worst bar=argmin net live.
  B12 Bars outside anchor test windows -> no live rungs (v182); v183 trades
     every live books bar (no ML gate, ladder as v179).
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
ALTS = ["DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "AVAXUSDT", "TRXUSDT"]
ALL11 = MAJORS + ALTS
SHORT11 = ["BNB", "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "LINK", "LTC", "AVAX", "TRX"]
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
EPS = 1e-12
RUNG_W = 0.25 / 4.0
INF_EXIT = 999
FEAT12 = ["depth", "r5", "r15", "vspike", "taker15", "rng",
          "breadth", "btc_depth", "trend", "r1d", "funding", "k"]


def _load_engine_real():
    spec = importlib.util.spec_from_file_location(
        "v182_v183_audit_engine_real", ROUND2 / "engine_real" / "engine_real.py")
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
    elif sym in MAJORS:
        files = sorted(glob.glob(str(ROOT / f"data/raw/majors_intraday_20260924/{sym}_1m_20*.parquet")))
    else:
        files = sorted(glob.glob(str(ROOT / f"data/raw/alts_intraday_20260926/{sym}_1m_20*.parquet")))
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
    from sklearn.ensemble import HistGradientBoostingRegressor

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
    bcols = list(books.columns)
    last_books = bidx.max()
    G = pd.date_range(GRID_START, last_books, freq="4h", tz="UTC")
    n = len(G)
    T_all = G + pd.Timedelta(hours=4)
    T2_all = G + pd.Timedelta(hours=8)
    print(f"grid {n} bars {G.min()} -> {G.max()}", flush=True)

    # ---- 4h opens/sigma/funding/trend for 11 assets ----
    opens11 = {}
    for s in ALL11:
        k = pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{s}_4h.parquet")
        ot = pd.to_datetime(k["open_time"], utc=True)
        o = pd.Series(k["open"].to_numpy(dtype=float), index=ot).sort_index()
        o = o[~o.index.duplicated(keep="last")]
        opens11[s] = o
    opens_G = pd.DataFrame({s: opens11[s].reindex(G) for s in ALL11})
    o1 = opens_G.shift(-1).to_numpy(dtype=float)
    o2 = opens_G.shift(-2).to_numpy(dtype=float)
    sig = opens_G.pct_change().rolling(360, min_periods=120).std().to_numpy(dtype=float)
    fund = np.column_stack([
        er.funding_at_bar_open(s, G).shift(-2).fillna(0.0).to_numpy(dtype=float)
        for s in ALL11])
    trend_base = np.zeros((n, len(ALL11)))
    open_m24 = np.zeros((n, len(ALL11)))
    fund_feat = np.zeros((n, len(ALL11)))
    for j, s in enumerate(ALL11):
        o = opens11[s]
        trend_base[:, j] = o.rolling(42, min_periods=42).mean().reindex(T_all).to_numpy(dtype=float)
        open_m24[:, j] = o.reindex(T_all - pd.Timedelta(hours=24)).to_numpy(dtype=float)
        f = pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{s}_funding.parquet")
        ft = pd.to_datetime(f["fundingTime"], utc=True)
        fr = f["fundingRate"].to_numpy(dtype=float)
        fser = pd.Series(fr, index=ft).sort_index()
        fser = fser[~fser.index.duplicated(keep="last")]
        fser_nz = fser.mask(fser == 0.0).ffill()
        fund_feat[:, j] = fser_nz.reindex(G, method="ffill").fillna(0.0).to_numpy(dtype=float)

    n_min = n * 240
    mgrid = pd.date_range(T_all.min(), periods=n_min, freq="1min", tz="UTC")
    MO = np.arange(16, 239)
    btc11 = ALL11.index("BTCUSDT")

    # ---- majors close cube for breadth/btc_depth ----
    print("loading majors close cube", flush=True)
    close_major = np.zeros((n, 240, len(MAJORS)))
    majors_cubes = {}
    for j, s in enumerate(MAJORS):
        op, hi, lo, cl, vo, tb = _load_1m_cubes(s, mgrid, n)
        majors_cubes[s] = (op, hi, lo, cl, vo, tb)
        close_major[:, :, j] = cl
        print(f"{s} cubes ready", flush=True)

    # ================= A1 v182 pooled gate =================
    nr = len(RUNGS)
    lims11 = np.full((nr, n, len(ALL11)), np.nan)
    fmins11 = np.full((nr, n, len(ALL11)), -1, dtype=int)
    rets11_n = np.zeros((nr, n, len(ALL11)))
    rets11_s = np.zeros((nr, n, len(ALL11)))
    rec_i, rec_j, rec_r, rec_k, rec_f = [], [], [], [], []
    rec_y, rec_ys = [], []
    F = {c: [] for c in FEAT12}
    for j, sym in enumerate(ALL11):
        if sym in majors_cubes:
            op, hi, lo, cl, vo, tb = majors_cubes[sym]
        else:
            op, hi, lo, cl, vo, tb = _load_1m_cubes(sym, mgrid, n)
            print(f"{sym} cubes ready", flush=True)
        s_out = np.full(n, 0.0002)
        for i in range(n - 1):
            o0, h0, l0 = op[i + 1, 0], hi[i + 1, 0], lo[i + 1, 0]
            if np.isfinite(o0) and o0 > 0 and np.isfinite(h0) and np.isfinite(l0) and h0 >= l0:
                xr = (h0 - l0) / o0
                if np.isfinite(xr):
                    s_out[i] = max(0.0002, 0.25 * xr)
        sig_j = sig[:, j]
        o1_j = o1[:, j]
        o2_j = o2[:, j]
        fund_j = fund[:, j]
        n_cand = 0
        for r, kk in enumerate(RUNGS):
            with np.errstate(invalid="ignore", divide="ignore"):
                L = o1_j * (1 - kk * sig_j)
            valid_L = (np.isfinite(sig_j) & (sig_j > 0) & np.isfinite(o1_j) & (o1_j > 0)
                       & np.isfinite(L) & (L > 0))
            with np.errstate(invalid="ignore"):
                hit = valid_L[:, None] & np.isfinite(lo[:, MO]) & (lo[:, MO] < L[:, None])
            has = hit.any(axis=1)
            first = hit.argmax(axis=1)
            f = np.where(has, MO[first], -1)
            ok = has & valid_L & np.isfinite(o2_j) & (o2_j > 0) & (np.arange(n) + 1 < n)
            rn = np.zeros(n)
            rs = np.zeros(n)
            idx_ok = np.flatnonzero(ok)
            rn[idx_ok] = (o2_j[idx_ok] * (1 - s_out[idx_ok]) / L[idx_ok] - 1
                          - MAKER - TAKER - fund_j[idx_ok])
            rs[idx_ok] = (o2_j[idx_ok] * (1 - s_out[idx_ok]) / L[idx_ok] - 1
                          - MAKER_S - TAKER_S - EXTRA_S - fund_j[idx_ok])
            # NOTE: v179-style extra-as-fee (leader may fold extra into s_out;
            # known 0.01pp delta from v178/v179 audits).
            rn[~np.isfinite(rn)] = 0.0
            rs[~np.isfinite(rs)] = 0.0
            fmins11[r, :, j] = np.where(ok, f, -1)
            lims11[r, :, j] = np.where(ok, L, np.nan)
            rets11_n[r, :, j] = np.where(ok, rn, 0.0)
            rets11_s[r, :, j] = np.where(ok, rs, 0.0)
            for i in idx_ok:
                m = int(f[i])
                if m < 16 or m > 238:
                    continue
                fm = m - 1
                c_fm = cl[i, fm]
                if not (np.isfinite(c_fm) and np.isfinite(o1_j[i]) and o1_j[i] > 0
                        and np.isfinite(sig_j[i]) and sig_j[i] > 0):
                    fmins11[r, i, j] = -1
                    lims11[r, i, j] = np.nan
                    rets11_n[r, i, j] = 0.0
                    rets11_s[r, i, j] = 0.0
                    continue
                depth = (c_fm / o1_j[i] - 1) / sig_j[i]
                if not np.isfinite(depth):
                    fmins11[r, i, j] = -1
                    lims11[r, i, j] = np.nan
                    rets11_n[r, i, j] = 0.0
                    rets11_s[r, i, j] = 0.0
                    continue
                c5 = cl[i, fm - 5]
                r5 = (c_fm / c5 - 1) / sig_j[i] if (np.isfinite(c5) and c5 > 0) else 0.0
                c15 = cl[i, fm - 15]
                r15 = (c_fm / c15 - 1) / sig_j[i] if (np.isfinite(c15) and c15 > 0) else 0.0
                if not np.isfinite(r5):
                    r5 = 0.0
                if not np.isfinite(r15):
                    r15 = 0.0
                v_num = float(vo[i, fm - 4:fm + 1].sum())
                v_den_win = vo[i, 0:fm - 4]
                v_den = 5 * float(v_den_win.mean()) if (fm - 4) > 0 else np.nan
                vspike = v_num / v_den if (np.isfinite(v_num) and np.isfinite(v_den) and v_den > 0) else 1.0
                if not np.isfinite(vspike):
                    vspike = 1.0
                tb_num = float(tb[i, fm - 14:fm + 1].sum())
                v15 = float(vo[i, fm - 14:fm + 1].sum())
                taker15 = float(np.clip(tb_num / v15, 0.0, 1.0)) if (np.isfinite(tb_num) and np.isfinite(v15) and v15 > 0) else 0.5
                h_fm, l_fm = hi[i, fm], lo[i, fm]
                if (np.isfinite(h_fm) and np.isfinite(l_fm) and c_fm > 0 and h_fm >= l_fm
                        and np.isfinite(sig_j[i]) and sig_j[i] > 0):
                    rng = (h_fm - l_fm) / c_fm / sig_j[i]
                else:
                    rng = 0.0
                if not np.isfinite(rng):
                    rng = 0.0
                br = 0
                for oj in range(len(MAJORS)):
                    co_o = close_major[i, fm, oj]
                    oT_o = o1[i, oj]
                    s_o = sig[i, oj]
                    if (np.isfinite(co_o) and np.isfinite(oT_o) and oT_o > 0
                            and np.isfinite(s_o) and s_o > 0):
                        dd = (co_o / oT_o - 1) / s_o
                        if np.isfinite(dd) and dd <= -2:
                            br += 1
                co_b = close_major[i, fm, 1]
                if (np.isfinite(co_b) and np.isfinite(o1[i, 1]) and o1[i, 1] > 0
                        and np.isfinite(sig[i, 1]) and sig[i, 1] > 0):
                    btc_depth = (co_b / o1[i, 1] - 1) / sig[i, 1]
                    if not np.isfinite(btc_depth):
                        btc_depth = 0.0
                else:
                    btc_depth = 0.0
                tb42 = trend_base[i, j]
                trend = o1_j[i] / tb42 - 1 if (np.isfinite(tb42) and tb42 > 0 and np.isfinite(o1_j[i]) and o1_j[i] > 0) else 0.0
                if not np.isfinite(trend):
                    trend = 0.0
                om24 = open_m24[i, j]
                r1d = (o1_j[i] / om24 - 1) / sig_j[i] if (np.isfinite(om24) and om24 > 0 and np.isfinite(o1_j[i]) and o1_j[i] > 0 and np.isfinite(sig_j[i]) and sig_j[i] > 0) else 0.0
                if not np.isfinite(r1d):
                    r1d = 0.0
                y = float(rets11_n[r, i, j])
                ys = float(rets11_s[r, i, j])
                if not np.isfinite(y):
                    fmins11[r, i, j] = -1
                    lims11[r, i, j] = np.nan
                    rets11_n[r, i, j] = 0.0
                    rets11_s[r, i, j] = 0.0
                    continue
                rec_i.append(i)
                rec_j.append(j)
                rec_r.append(r)
                rec_k.append(float(kk))
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
                F["k"].append(float(kk))
                n_cand += 1
        print(f"{sym}: candidates={n_cand}", flush=True)
        if sym not in majors_cubes:
            del op, hi, lo, cl, vo, tb

    rec_i = np.asarray(rec_i, dtype=int)
    rec_j = np.asarray(rec_j, dtype=int)
    rec_r = np.asarray(rec_r, dtype=int)
    rec_f = np.asarray(rec_f, dtype=int)
    rec_y = np.asarray(rec_y, dtype=float)
    rec_ys = np.asarray(rec_ys, dtype=float)
    X = np.column_stack([np.asarray(F[c], dtype=float) for c in FEAT12])
    t_arr = G[rec_i]
    T_arr = T_all[rec_i]
    T2_arr = T2_all[rec_i]
    n_pts = len(rec_y)
    is_major_pt = rec_j < len(MAJORS)
    print(f"v182 total pooled candidates={n_pts} majors={int(is_major_pt.sum())}", flush=True)

    anchors_ts = [pd.Timestamp(a, tz="UTC") for a in ANCHORS]
    live_mask = np.zeros(n_pts, dtype=bool)
    per_anchor = []
    for a, a_ts in zip(ANCHORS, anchors_ts):
        train_mask = (T2_arr < a_ts - pd.Timedelta(days=1)) & (T_arr >= TRAIN_T_MIN)
        test_mask = (t_arr >= a_ts) & (t_arr < a_ts + pd.Timedelta(days=365))
        tr_idx = np.flatnonzero(train_mask)
        te_idx = np.flatnonzero(test_mask)
        te_major = te_idx[rec_j[te_idx] < len(MAJORS)]
        if len(tr_idx) == 0 or len(te_major) == 0:
            ic = None
            n_live = 0
        else:
            mdl = HistGradientBoostingRegressor(
                max_depth=3, learning_rate=0.03, max_iter=300,
                min_samples_leaf=50, l2_regularization=1.0, random_state=0)
            mdl.fit(X[tr_idx], rec_y[tr_idx])
            pred_all = mdl.predict(X[te_idx])
            pred_major = mdl.predict(X[te_major])
            live_major = pred_major > 0
            live_mask[te_major[live_major]] = True
            n_live = int(live_major.sum())
            s_pred = pd.Series(pred_major)
            s_y = pd.Series(rec_y[te_major])
            if len(te_major) >= 3 and float(s_pred.std()) > 0 and float(s_y.std()) > 0:
                ic_v = float(s_pred.corr(s_y, method="spearman"))
                ic = ic_v if np.isfinite(ic_v) else None
            else:
                ic = None
        per_anchor.append({
            "anchor": a,
            "train_points": int(len(tr_idx)),
            "test_points": int(len(te_idx)),
            "test_majors_points": int(len(te_major)) if len(te_idx) else 0,
            "ic_spearman_majors": ic,
            "live_pred_pos": int(n_live),
        })
        print(f"anchor {a}: train={len(tr_idx)} test={len(te_idx)} majors={len(te_major) if len(te_idx) else 0} ic={ic} live={n_live}", flush=True)
    live_set182 = set()
    for ii in np.flatnonzero(live_mask):
        live_set182.add((int(rec_i[ii]), int(rec_r[ii]), int(rec_j[ii])))
    print(f"v182 live majors rungs={len(live_set182)} / majors pts {int(is_major_pt.sum())}", flush=True)

    # ---- v182 books/vol/budget (majors, v179 loop) ----
    mj = len(MAJORS)
    retsM_n = rets11_n[:, :, :mj]
    retsM_s = rets11_s[:, :, :mj]
    fminsM = fmins11[:, :, :mj]
    limsM = lims11[:, :, :mj]
    sleeve_unc_n182 = (SIZE / nr) * retsM_n.sum(axis=(0, 2))
    sleeve_unc_s182 = (SIZE / nr) * retsM_s.sum(axis=(0, 2))
    unit_G_n182 = sleeve_unc_n182 / S_REF
    unit_G_s182 = sleeve_unc_s182 / S_REF
    pos = G.get_indexer(bidx)
    assert (pos >= 0).all()
    unit_books_n182 = pd.Series(unit_G_n182[pos], index=bidx)
    unit_books_s182 = pd.Series(unit_G_s182[pos], index=bidx)
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

    s_n182 = vol_s_from_unit(unit_books_n182)
    s_s182 = vol_s_from_unit(unit_books_s182)
    fee_b, rel_b, fee_s_, rel_s_ = _exec_arrays(bidx, bcols, v135, W_EXEC, MAKER, TAKER, 0.0)
    fee_b_s, rel_b_s, fee_s_s, rel_s_s = _exec_arrays(
        bidx, bcols, v135, W_EXEC, MAKER_S, TAKER_S, EXTRA_S)
    mins = np.array([er.MIN_NOTIONAL.get(c, 5.0) for c in bcols])
    o1_books = o_df.shift(-1).to_numpy(dtype=float)
    close_books182 = close_major[pos]
    # map (r, gi, a) -> books: build per-books arrays (nB, mj, nr)
    fmins_b182 = np.stack([fminsM[r][pos] for r in range(nr)], axis=-1)  # (nB, mj, nr)
    lims_b182 = np.stack([limsM[r][pos] for r in range(nr)], axis=-1)
    rets_b_n182 = np.stack([retsM_n[r][pos] for r in range(nr)], axis=-1)
    rets_b_s182 = np.stack([retsM_s[r][pos] for r in range(nr)], axis=-1)
    # live set on G -> books: live rungs keyed by (gi, r, a); books bar i has gi=pos[i]
    live_by_gi = {}
    for (gi, r, a) in live_set182:
        live_by_gi.setdefault(gi, set()).add((r, a))

    # need exec/fund arrays for dd: full loop storing them
    def run_budget_v179_full(rets_b, s_in, fee_b_in, rel_b_in, fee_s_in, rel_s_in):
        net = np.zeros(nB)
        turn = np.zeros(nB)
        g = np.ones(nB)
        eq = np.ones(nB)
        eq_min = np.ones(nB)
        exec_c = np.zeros(nB)
        fund_p = np.zeros(nB)
        w_all = np.zeros((nB, len(bcols)))
        taken_total, canc_total = 0, 0
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
            sleeve_pnl, taken = 0.0, []
            gi = int(pos[i])
            if live[i]:
                rn = float(s_in[i] * g[i] * SIZE / nr / S_REF)
                fills = []
                lv = live_by_gi.get(gi, set())
                for a in range(mj):
                    for r in range(nr):
                        f = int(fmins_b182[i, a, r])
                        if f >= 0 and (r, a) in lv:
                            fills.append((f, r, a))
                fills.sort()
                used = 0.0
                for f, r, a in fills:
                    if used + rn <= N_MAX + 1e-12:
                        used += rn
                        taken.append((f, r, a))
                        sleeve_pnl += rn * float(rets_b[i, a, r])
                    else:
                        canc_total += 1
                taken_total += len(taken)
            ni = gross - ex_c + fundp + carry_p - carry_c + sleeve_pnl
            net[i] = ni
            turn[i] = float(np.abs(dw).sum())
            eq[i] = (eq[i - 1] if i else 1.0) * (1 + ni)
            w_all[i] = w
            exec_c[i] = ex_c
            fund_p[i] = fundp
            if live[i]:
                Cm = close_books182[i].astype(float)
                with np.errstate(invalid="ignore", divide="ignore"):
                    path = np.zeros(240)
                    for a in range(mj):
                        base = o1_books[i, a]
                        if np.isfinite(base) and base > 0:
                            clv = Cm[:, a]
                            vv = np.isfinite(clv)
                            path[vv] += w[a] * (clv[vv] / base - 1)
                    q = float(s_in[i] * g[i] * SIZE / nr / S_REF)
                    for f, r, a in taken:
                        L = float(lims_b182[i, a, r])
                        if np.isfinite(L) and L > 0 and q != 0:
                            vm = np.arange(240) >= f
                            clv = Cm[:, a]
                            vv = np.isfinite(clv) & vm
                            path[vv] += q * (clv[vv] / L - 1)
                    pm = float(np.nanmin(path)) if np.isfinite(path).any() else 0.0
                eq_min[i] = (eq[i - 1] if i else 1.0) * (1 + min(0.0, pm) - ex_c + min(fundp, 0.0))
            else:
                eq_min[i] = eq[i]
            prev_w, prev_c = w.copy(), c
        return net, turn, g, eq, eq_min, exec_c, fund_p, taken_total, canc_total

    net182n, turn182n, g182n, eq182n, eqmin182n, _, _, tk182n, cx182n = run_budget_v179_full(
        rets_b_n182, s_n182, fee_b, rel_b, fee_s_, rel_s_)
    net182s, turn182s, g182s, eq182s, eqmin182s, _, _, tk182s, cx182s = run_budget_v179_full(
        rets_b_s182, s_s182, fee_b_s, rel_b_s, fee_s_s, rel_s_s)
    summ182n = v110.summarize(pd.Series(net182n, index=bidx), pd.Series(turn182n, index=bidx),
                              pd.Series(g182n, index=bidx))
    summ182s = v110.summarize(pd.Series(net182s, index=bidx), pd.Series(turn182s, index=bidx),
                              pd.Series(g182s, index=bidx))

    def dd_1m(eq, eq_min):
        full = np.asarray((bidx >= START) & (bidx < END))
        e = eq[full] / eq[full][0]
        em = eq_min[full] / eq[full][0]
        dd = 1 - np.minimum(e, em) / np.maximum.accumulate(e)
        worst = int(np.argmax(dd))
        return round(100 * float(dd.max()), 2), str(bidx[full][worst])

    dd182n, worst182n = dd_1m(eq182n, eqmin182n)
    dd182s, worst182s = dd_1m(eq182s, eqmin182s)

    # ================= A2 v183 TP ladder (5 majors) =================
    # reuse majors cubes (op/hi/lo/cl). Build L/f/TP/e/rets.
    f_v183 = np.full((n, mj, nr), -1, dtype=int)
    e_v183 = np.full((n, mj, nr), INF_EXIT, dtype=int)
    L_v183 = np.full((n, mj, nr), np.nan)
    r_v183_n = np.zeros((n, mj, nr))
    r_v183_s = np.zeros((n, mj, nr))
    tp_flag = np.zeros((n, mj, nr), dtype=bool)
    s_out_M = np.zeros((n, mj))
    for a, sym in enumerate(MAJORS):
        op, hi, lo, cl, vo, tb = majors_cubes[sym]
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
        op, hi, lo, cl, vo, tb = majors_cubes[MAJORS[a]]
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
                # first m > fi with high > TP
                m_found = INF_EXIT
                hrow = hi[i]
                for m in range(fi + 1, 240):
                    hm = hrow[m]
                    if np.isfinite(hm) and np.isfinite(TP) and hm > TP:
                        m_found = m
                        break
                f_v183[i, a, ri] = fi
                L_v183[i, a, ri] = Li
                if m_found != INF_EXIT:
                    e_v183[i, a, ri] = m_found
                    tp_flag[i, a, ri] = True
                    r_v183_n[i, a, ri] = TP / Li - 1 - MAKER - MAKER
                    r_v183_s[i, a, ri] = TP / Li - 1 - MAKER_S - MAKER_S
                else:
                    e_v183[i, a, ri] = INF_EXIT
                    tp_flag[i, a, ri] = False
                    exn = o2_a[i] * (1 - s_out_M[i, a])
                    r_v183_n[i, a, ri] = exn / Li - 1 - MAKER - TAKER - fund_a[i]
                    r_v183_s[i, a, ri] = exn / Li - 1 - MAKER_S - TAKER_S - EXTRA_S - fund_a[i]
            # invalidate non-ok
            bad = ~ok
            f_v183[bad, a, ri] = -1
            e_v183[bad, a, ri] = INF_EXIT
            L_v183[bad, a, ri] = np.nan
            r_v183_n[bad, a, ri] = 0.0
            r_v183_s[bad, a, ri] = 0.0
    # fix: loop above overwrote per-i inside ok only; ensure f for non-ok stays -1 (done)
    # recount fills
    fills183 = int((f_v183 >= 0).sum())
    tp_fills183 = int((tp_flag & (f_v183 >= 0)).sum())
    print(f"v183 fills={fills183} tp={tp_fills183}", flush=True)
    sleeve_unc_n183 = RUNG_W * (r_v183_n * (f_v183 >= 0)).sum(axis=(1, 2))
    sleeve_unc_s183 = RUNG_W * (r_v183_s * (f_v183 >= 0)).sum(axis=(1, 2))
    unit_G_n183 = sleeve_unc_n183 / S_REF
    unit_G_s183 = sleeve_unc_s183 / S_REF
    unit_books_n183 = pd.Series(unit_G_n183[pos], index=bidx)
    unit_books_s183 = pd.Series(unit_G_s183[pos], index=bidx)
    s_n183 = vol_s_from_unit(unit_books_n183)
    s_s183 = vol_s_from_unit(unit_books_s183)
    f_b183 = f_v183[pos]
    e_b183 = e_v183[pos]
    L_b183 = L_v183[pos]
    r_b_n183 = r_v183_n[pos]
    r_b_s183 = r_v183_s[pos]
    tp_b183 = tp_flag[pos]

    def run_budget_v183(r_b, s_in, fee_b_in, rel_b_in, fee_s_in, rel_s_in):
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
                rn = float(s_in[i] * g[i] * SIZE / nr / S_REF)
                cands = []
                for a in range(mj):
                    for ri in range(nr):
                        f = int(f_b183[i, a, ri])
                        if f >= 0:
                            cands.append((f, ri, a))
                cands.sort()
                taken_exits = []
                for f, ri, a in cands:
                    e = int(e_b183[i, a, ri])
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
                Cm = close_books182[i].astype(float)
                with np.errstate(invalid="ignore", divide="ignore"):
                    # books leg
                    path2 = np.zeros(240)
                    for a in range(mj):
                        base = o1_books[i, a]
                        if np.isfinite(base) and base > 0:
                            clv = Cm[:, a]
                            vv = np.isfinite(clv)
                            path2[vv] += w[a] * (clv[vv] / base - 1)
                    q = float(s_in[i] * g[i] * SIZE / nr / S_REF)
                    marr = np.arange(240)
                    for f, ri, a, e in taken:
                        L = float(L_b183[i, a, ri])
                        if not (np.isfinite(L) and L > 0) or q == 0:
                            continue
                        clv = Cm[:, a]
                        if e != INF_EXIT:
                            # mark f..e-1 at close/L-1, locked at TP/L-1 after (B11)
                            TPv = L * (1 + float(sig[pos[i], a]))
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

    net183n, turn183n, g183n, eq183n, eqmin183n, tk183n, cx183n, tp183n = run_budget_v183(
        r_b_n183, s_n183, fee_b, rel_b, fee_s_, rel_s_)
    net183s, turn183s, g183s, eq183s, eqmin183s, tk183s, cx183s, tp183s = run_budget_v183(
        r_b_s183, s_s183, fee_b_s, rel_b_s, fee_s_s, rel_s_s)
    summ183n = v110.summarize(pd.Series(net183n, index=bidx), pd.Series(turn183n, index=bidx),
                              pd.Series(g183n, index=bidx))
    summ183s = v110.summarize(pd.Series(net183s, index=bidx), pd.Series(turn183s, index=bidx),
                              pd.Series(g183s, index=bidx))
    dd183n, worst183n = dd_1m(eq183n, eqmin183n)
    dd183s, worst183s = dd_1m(eq183s, eqmin183s)
    wi183n = int(np.argmin(np.where(live, net183n, np.inf)))
    wi183s = int(np.argmin(np.where(live, net183s, np.inf)))

    def pack182(summ, dd1, worst_t, tk, cx, s_in):
        wi = 0  # filled below by caller
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
            "mean_s": round(float(np.mean(s_in[live])), 3),
        }

    v182n = pack182(summ182n, dd182n, worst182n, tk182n, cx182n, s_n182)
    v182s = pack182(summ182s, dd182s, worst182s, tk182s, cx182s, s_s182)
    v183n = pack182(summ183n, dd183n, worst183n, tk183n, cx183n, s_n183)
    v183s = pack182(summ183s, dd183s, worst183s, tk183s, cx183s, s_s183)
    v183n["worst_bar"] = {"time": str(bidx[wi183n]), "net": float(net183n[wi183n])}
    v183s["worst_bar"] = {"time": str(bidx[wi183s]), "net": float(net183s[wi183s])}
    v183n["tp_exits_taken"] = int(tp183n)
    v183s["tp_exits_taken"] = int(tp183s)

    replication = {
        "version": "v182_v183_audit_replication",
        "blind": "did_not_open_research_v182_v183_until_this_file_saved",
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
        "feature_columns_v182": FEAT12,
        "spec": {
            "symbols_v182": ALL11,
            "symbols_v183": MAJORS,
            "rungs": list(RUNGS),
            "grid": f"{G.min()} -> {G.max()} ({n} 4h bars)",
            "v182_trigger": "first m in 16..238 with 1m low < open(T)*(1-k*sigma(t)) strict",
            "v182_features": "at minute f-1 as v180 EXCEPT no asset code; breadth=#five-majors depth<=-2 incl self; btc_depth=BTC depth",
            "v182_y": "normal-cost rung net; train pooled T+4h<anchor-1d T>=2020-03-02; majors test pred>0; v179 total-only budget",
            "v182_vol": "uncapped majors sleeve_unit shifted by 2",
            "v183_trigger": "ladder as v179; TP=L*(1+sigma); exit TP at first m>f high>TP maker both sides no funding else next-4h-open taker exit",
            "v183_budget": "order (f,rung,col); take iff (open_taken(e>f)+1)*rn<=1/6; rn=s*g*0.25/4/1.657",
            "v183_vol": "uncapped TP-aware sleeve_unit shifted by 2",
            "v183_mark": "rung marked f..e-1 at close/L-1, locked at TP/L-1 after; non-TP f..239 like v179",
        },
        "assumptions": {
            "B1": "grid date_range 2020-02-01 to last books bar; v92 anchors; half-open test windows",
            "B2": "sigma pct_change rolling 360 min120 at t; finite>0 else no candidate; TP=L*(1+sigma)",
            "B3": "L=open(T)*(1-k*sigma); f=first low<L strict; entry=L",
            "B4": "next-open exit base 4h open(T+4h); s_out from 1m minute-0 else 0.0002; stress extra deducted as fee (v179 style)",
            "B5": "1m keep-last dedup + within-bar ffill prices; volume/taker missing->0; TP scan f+1..239 strict",
            "B6": "v182 features at f-1 with v180 fallbacks; no asset code; breadth over five majors incl self; train pooled normal y; IC on majors test",
            "B7": "v183 TP net normal TP/L-1-0.0002-0.0002 / stress -0.0004-0.0004, no funding/extra; next-open legs as B4",
            "B8": "vol uncapped shift2 per cost; s=min(0.25/vol,2) else 1",
            "B9": "v182 budget v179 total-only; v183 concurrent-open using e>f (past highs only); rn=s*g*0.0625/1.657",
            "B10": "loop mirrors engine_real FULL W60; governor/budget/min-notional on",
            "B11": "1m mark taken rungs only; minute eq=prev*(1+min(0,min path)-exec+min(funding,0))",
            "B12": "v182 bars outside test windows -> no live rungs; v183 every live bar (no ML gate)",
        },
        "v182": {
            "candidates_total_pooled": int(n_pts),
            "candidates_majors": int(is_major_pt.sum()),
            "live_total_majors": int(live_mask.sum()),
            "per_anchor": per_anchor,
            "primary_normal": v182n,
            "stress": v182s,
        },
        "v183": {
            "fills_total_grid": int(fills183),
            "tp_fills_grid": int(tp_fills183),
            "sleeve_sums": {
                "normal": float(sleeve_unc_n183.sum()),
                "stress": float(sleeve_unc_s183.sum()),
            },
            "primary_normal": v183n,
            "stress": v183s,
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
