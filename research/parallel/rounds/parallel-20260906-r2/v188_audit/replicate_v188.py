"""v188 blind audit Part A replication.

Blind rule: does NOT read research v188 files, v188_result.json, engine_user
sources, nor tests/test_engine_user.py until replication.json is saved.
Independent implementation from OPENCODE_V188_AUDIT.md plus AGENTS.md
(User goal and validation protocol + Current execution assumptions).

Run from the repository root so every data path below stays relative.

Frozen blind assumptions:
  A1 Books/opens from artifacts/research/engine_real/books_v154.parquet and
     opens_v154.parquet. Decision index t = books index. Holding bar
     T = t + 4h, exit mark T2 = t + 8h from opens (4h opens).
  A2 sigma_4h(t) = std of 360 4h open-to-open pct changes ending at t
     (min 120) per asset; sigma_d = sigma_4h * sqrt(6). NaN/nonpositive
     sigma means no sleeve fills and no book SL/TP for that asset/bar.
  A3 realized[t] = 0.8 * sum_j books[t-2,j] * (open[t,j]/open[t-1,j]-1);
     vol = rolling std 360 min120 of realized * sqrt(2190); s = min(0.25/vol,2)
     (1 if NaN/nonfinite). s is a portfolio scalar per bar.
  A4 Governor g[t] from combined equity: for bar i>=2, peak = max eq over
     540 bars ending i-2, g = clip((0.20-(1-eq[i-2]/peak))/0.10,0,1);
     g=1 for i<2. Target weight = 0.8*s*books[t]*g.
  A5 Quantities: q_prev held (coins). equity_start = eq_prev*10000.
     w_start = q_prev*open(T)/equity_start (0 if missing). dw = target-w_start.
     Skip if |dw|*equity < min notional (BTC 100, ETH 20, others 5) unless
     target==0 and position nonzero (must flatten). Limit = minute0 1m open
     *(1-/+0.001) (buy -10bps, sell +10bps; fallback to open(T) if 1m NaN).
     dq = dw*equity/limit. Fill iff 1m low<high strict trade-through in
     minutes 2..59 (buy low<limit, sell high>limit), maker 0.0002, else expire.
  A6 Entry: new -> fill; same-side add -> weighted; reduce -> unchanged;
     flip or flatten-then-new -> fill (flat -> None).
  A7 Book SL/TP per m in (2,3,4): long SL=entry*(1-m*sigma_d),
     TP=entry*(1+2*m*sigma_d), short mirrored. Levels from entry at decision
     (recomputed after a fill for the new combined position). Held checked
     minutes 0..f inclusive (f=fill minute, INF if no fill); new checked
     f..239 inclusive. Long SL low<=SL fill min(SL,open) taker 0.00055;
     long TP high>TP strict fill TP maker 0.0002; short mirrored
     (SL high>=SL fill max(SL,open), TP low<TP strict). Both same minute ->
     SL first. After SL/TP flat rest of bar, pending cancelled if unfilled.
  A8 Book funding: long (q_end>0) held at end pays 0.0001*notional if T2
     hour in (0,8,16) UTC; shorts 0. No carry.
  A9 Sleeve: k in (2.5,3,3.5,4), L=open(T)*(1-k*sigma_4h), live minutes
     16..238, fill low<L strict maker 0.0002 entry=L. SL=L*(1-2*sigma_4h)
     (low<=SL fill min(SL,open) taker 0.00055), TP=L*(1+sigma_4h)
     (high>TP strict maker 0.0002), else exit open(T2) taker 0.00055 plus
     0.0001 funding if T2 settlement. rn=s*g*0.25/4/1.657. Candidates sorted
     by (minute,rung,asset); take iff (open_at_minute+1)*rn<=1/6 where open
     counts taken with exit>f. Exits strictly after fill minute.
  A10 Bar PnL in USDT: book held q_prev*(P_end_or_exit-P_start) plus
     dq*(P_end_or_exit-fill) minus maker/taker fees on traded notionals
     minus funding; sleeve rn*equity*(P_exit/L-1) minus fees minus funding.
     P_start=open(T), P_end=open(T2) (fallback to 1m closes if missing).
     equity_end=equity_start+total; net=total/equity_start.
  A11 1m-marked equity: per minute close-based MTM for book (held + new,
     locked at exit after) and sleeve (close/L-1, locked at exit gross),
     minus fees accrued up to that minute; funding only in close. Gate DD =
     max(4h-close DD, 1m-marked DD). Worst 4h bar reported as decision t;
     worst 1m bar reported as holding bar T containing the worst minute.
  A12 Live = all books bars (2021-09-24..2026-09-23 20:00, 10950 bars).
     Anchors 2021/2022/2023/2024/2025-09-24 plus live end; yearly net from
     equity before/after each slice; monthly=(1+net)^(1/12)-1; full
     monthly=(eq_end)^(1/60)-1; monthly_dev4=(prod first four (1+net))^(1/48)-1.
     Rows m=2,3,4 with sleeve; selection = best monthly_dev4 with gate DD<=20
     and no losing year in first four; that variant without sleeve.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v188_audit")
OUT = AUD / "replication.json"
CACHE = Path("artifacts/research/engine_real")

MAJORS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
SYM_TO_MIN = {"BTCUSDT": 100.0, "ETHUSDT": 20.0}
DEFAULT_MIN = 5.0
RUNGS = (2.5, 3.0, 3.5, 4.0)
S_REF = 1.657
N_MAX = 1.0 / 6.0
MAKER, TAKER = 0.0002, 0.00055
ACCOUNT = 10000.0
SQRT6 = float(np.sqrt(6.0))
SQRT2190 = float(np.sqrt(2190.0))
EPS = 1e-12
INF = 10 ** 9
ANCHORS = [
    pd.Timestamp("2021-09-24 00:00+00:00"),
    pd.Timestamp("2022-09-24 00:00+00:00"),
    pd.Timestamp("2023-09-24 00:00+00:00"),
    pd.Timestamp("2024-09-24 00:00+00:00"),
    pd.Timestamp("2025-09-24 00:00+00:00"),
]


def _ffill_row(a: np.ndarray) -> np.ndarray:
    out = a.copy()
    for i in range(out.shape[0]):
        last = np.nan
        row = out[i]
        for k in range(row.shape[0]):
            v = row[k]
            if np.isnan(v):
                row[k] = last
            else:
                last = v
    return out


def _load_1m_df(sym: str) -> pd.DataFrame:
    if sym == "BTCUSDT":
        files = sorted(glob.glob(str(Path("data/raw/btc_intraday_20260924/klines_1m_20*.parquet"))))
    else:
        files = sorted(glob.glob(str(Path(f"data/raw/majors_intraday_20260924/{sym}_1m_20*.parquet"))))
    assert files, f"no 1m files for {sym}"
    cols = ["open_time", "open", "high", "low", "close"]
    parts = [pd.read_parquet(f, columns=cols) for f in files]
    d = pd.concat(parts, ignore_index=True)
    d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
    d = d.sort_values("open_time").drop_duplicates("open_time", keep="last").set_index("open_time")
    return d


def _build_cubes(T_list: pd.DatetimeIndex, sym: str, df1m: pd.DataFrame):
    n = len(T_list)
    all_min = pd.DatetimeIndex(np.concatenate([pd.date_range(t, periods=240, freq="1min").values for t in T_list]), tz="UTC")
    # reindex once
    o = df1m["open"].astype(float).reindex(all_min).to_numpy(dtype=float).reshape(n, 240)
    h = df1m["high"].astype(float).reindex(all_min).to_numpy(dtype=float).reshape(n, 240)
    l = df1m["low"].astype(float).reindex(all_min).to_numpy(dtype=float).reshape(n, 240)
    c = df1m["close"].astype(float).reindex(all_min).to_numpy(dtype=float).reshape(n, 240)
    return _ffill_row(o), _ffill_row(h), _ffill_row(l), _ffill_row(c)


def _first_hit_buy_low(lo: np.ndarray, lo_idx: np.ndarray, thr: float) -> int:
    for m in lo_idx:
        v = lo[m]
        if np.isfinite(v) and v < thr:
            return int(m)
    return -1


def _first_hit_sell_high(hi: np.ndarray, hi_idx: np.ndarray, thr: float) -> int:
    for m in hi_idx:
        v = hi[m]
        if np.isfinite(v) and v > thr:
            return int(m)
    return -1


def update_entry(q_old: float, e_old: float, dq: float, fill: float):
    q_new = q_old + dq
    if abs(q_old) < 1e-15:
        return q_new, (fill if abs(q_new) > 1e-15 else np.nan)
    if abs(q_new) < 1e-15:
        return 0.0, np.nan
    if np.sign(q_new) != np.sign(q_old):
        return q_new, fill
    if abs(q_new) > abs(q_old):
        w = (abs(q_old) * e_old + abs(dq) * fill) / abs(q_new)
        return q_new, w
    return q_new, e_old


def book_levels(entry: float, sig_d: float, m: int, is_long: bool):
    if not (np.isfinite(entry) and entry > 0 and np.isfinite(sig_d) and sig_d > 0):
        return None, None
    if is_long:
        return entry * (1 - m * sig_d), entry * (1 + 2 * m * sig_d)
    return entry * (1 + m * sig_d), entry * (1 - 2 * m * sig_d)


def find_stop_long(op, hi, lo, m0: int, m1: int, sl: float, tp: float):
    # returns (exit_minute, kind, exit_price) or (INF, None, NaN)
    for mm in range(m0, m1 + 1):
        o = op[mm]
        l = lo[mm]
        h = hi[mm]
        sl_hit = np.isfinite(l) and l <= sl
        tp_hit = np.isfinite(h) and np.isfinite(tp) and h > tp
        if sl_hit and tp_hit:
            px = sl if not np.isfinite(o) else min(sl, o)
            return mm, "SL", px
        if sl_hit:
            px = sl if not np.isfinite(o) else min(sl, o)
            return mm, "SL", px
        if tp_hit:
            return mm, "TP", tp
    return INF, None, np.nan


def find_stop_short(op, hi, lo, m0: int, m1: int, sl: float, tp: float):
    for mm in range(m0, m1 + 1):
        o = op[mm]
        l = lo[mm]
        h = hi[mm]
        sl_hit = np.isfinite(h) and h >= sl
        tp_hit = np.isfinite(l) and np.isfinite(tp) and l < tp
        if sl_hit and tp_hit:
            px = sl if not np.isfinite(o) else max(sl, o)
            return mm, "SL", px
        if sl_hit:
            px = sl if not np.isfinite(o) else max(sl, o)
            return mm, "SL", px
        if tp_hit:
            return mm, "TP", tp
    return INF, None, np.nan


def is_settlement(t2: pd.Timestamp) -> bool:
    try:
        return int(t2.hour) in (0, 8, 16) and int(t2.minute) == 0
    except Exception:
        return False


def main():
    books = pd.read_parquet(CACHE / "books_v154.parquet").sort_index()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet").sort_index()
    bidx = books.index
    nB = len(bidx)
    print(f"books {nB} {bidx.min()} -> {bidx.max__()}".replace("__()", ""), flush=True) if False else print(f"books {nB} {bidx.min()} -> {bidx.max()}", flush=True)
    B = books[MAJORS].to_numpy(dtype=float)
    opens_b = opens_full.reindex(bidx)[MAJORS].to_numpy(dtype=float)
    # returns for sigma/realized use opens at books index
    with np.errstate(invalid="ignore", divide="ignore"):
        ret_b = opens_b / np.roll(opens_b, 1, axis=0) - 1
    ret_b[0, :] = np.nan
    rets_df = pd.DataFrame(ret_b, index=bidx, columns=MAJORS)
    sig4_df = rets_df.rolling(360, min_periods=120).std()
    sig4 = sig4_df[MAJORS].to_numpy(dtype=float)
    sigd = sig4 * SQRT6
    # realized / vol / s
    B_s = pd.DataFrame(B, index=bidx, columns=MAJORS)
    R_s = pd.DataFrame(ret_b, index=bidx, columns=MAJORS)
    realized_s = 0.8 * (B_s.shift(2) * R_s).sum(axis=1)
    vol_s = realized_s.rolling(360, min_periods=120).std() * SQRT2190
    vol = vol_s.to_numpy(dtype=float)
    s_base = np.where(np.isfinite(vol) & (vol > 0), 0.25 / np.where(vol > 0, vol, np.nan), np.nan)
    s_base = np.minimum(s_base, 2.0)
    s_base = np.where(np.isfinite(s_base), s_base, 1.0)
    # T / T2 opens
    T_list = bidx + pd.Timedelta(hours=4)
    T2_list = bidx + pd.Timedelta(hours=8)
    openT_df = opens_full.reindex(T_list)
    # ensure order matches T_list even with missing
    openT_df = openT_df.reindex(T_list)
    openT2_df = opens_full.reindex(T2_list).reindex(T2_list)
    openT = openT_df[MAJORS].to_numpy(dtype=float)
    openT2 = openT2_df[MAJORS].to_numpy(dtype=float)
    settle = np.array([is_settlement(t) for t in T2_list], dtype=bool)

    print("loading 1m", flush=True)
    cubes = {}
    for sym in MAJORS:
        df1m = _load_1m_df(sym)
        o, h, l, c = _build_cubes(T_list, sym, df1m)
        cubes[sym] = (o, h, l, c)
        del df1m
        print(f"{sym} cubes {o.shape}", flush=True)
    O1 = np.stack([cubes[s][0] for s in MAJORS], axis=2)  # (nB,240,5)? actually stack axis2
    # cubes[s][0] shape (nB,240); stack -> (nB,240,5)
    OP = np.stack([cubes[s][0] for s in MAJORS], axis=2)
    HI = np.stack([cubes[s][1] for s in MAJORS], axis=2)
    LO = np.stack([cubes[s][2] for s in MAJORS], axis=2)
    CL = np.stack([cubes[s][3] for s in MAJORS], axis=2)
    del cubes

    FILL_IDX = np.arange(2, 60)
    SLEEVE_IDX = np.arange(16, 239)

    def run_variant(m: int, with_sleeve: bool):
        eq = np.ones(nB)
        net = np.zeros(nB)
        garr = np.ones(nB)
        q_prev = np.zeros(5)
        ent_prev = np.full(5, np.nan)
        # minute equity for DD
        min_eq_parts = []
        min_T_parts = []
        # counters
        b_orders = 0
        b_fills = 0
        b_sl = 0
        b_tp = 0
        b_exp = 0
        s_taken = 0
        s_canc = 0
        s_tp = 0
        s_sl = 0
        s_nx = 0
        for i in range(nB):
            eq_prev = eq[i - 1] if i else 1.0
            eq_usdt = eq_prev * ACCOUNT
            if i >= 2:
                lo_i = max(0, (i - 2) - 539)
                peak = eq[lo_i:(i - 1)].max() if (i - 1) > lo_i else eq[i - 2]
                if not np.isfinite(peak) or peak <= 0:
                    peak = eq[i - 2]
                dd = 1 - eq[i - 2] / peak if peak > 0 else 0.0
                garr[i] = float(np.clip((0.20 - dd) / 0.10, 0.0, 1.0))
            s_i = float(s_base[i])
            g_i = float(garr[i])
            tgt = 0.8 * s_i * B[i] * g_i
            # per-asset book processing
            q_mid_arr = q_prev.copy()
            ent_mid_arr = ent_prev.copy()
            f_arr = np.full(5, -1)
            dq_arr = np.zeros(5)
            lim_arr = np.full(5, np.nan)
            fill_fee_arr = np.zeros(5)
            has_order = np.zeros(5, dtype=bool)
            # exit info for minute path
            e_book = np.full(5, INF)
            kind_book = np.array([None] * 5, dtype=object)
            px_book = np.full(5, np.nan)
            # for combined exit after fill, we store final exit (if stopped) else INF
            # staged: first process fills, then stops
            for a in range(5):
                pT = openT[i, a]
                pT2 = openT2[i, a]
                sd = sigd[i, a]
                tval = tgt[a]
                if not np.isfinite(tval):
                    tval = 0.0
                    tgt[a] = 0.0
                qp = float(q_prev[a])
                if not np.isfinite(pT) or pT <= 0:
                    # cannot size/mark; keep flat-ish, no trade
                    w0 = 0.0
                else:
                    w0 = qp * pT / eq_usdt if eq_usdt > 0 else 0.0
                dw = float(tval - w0)
                # min notional
                thr = SYM_TO_MIN.get(MAJORS[a], DEFAULT_MIN)
                must_close = (tval == 0.0) and (abs(qp) > 1e-15)
                if not must_close and abs(dw) * eq_usdt < thr - 1e-12:
                    dw = 0.0
                if abs(dw) < 1e-18:
                    continue
                # limit
                op0 = OP[i, 0, a]
                ref = op0 if np.isfinite(op0) and op0 > 0 else pT
                if not (np.isfinite(ref) and ref > 0):
                    b_orders += 1
                    b_exp += 1
                    continue
                lim = ref * (1 - 0.001) if dw > 0 else ref * (1 + 0.001)
                b_orders += 1
                has_order[a] = True
                lim_arr[a] = lim
                dq = dw * eq_usdt / lim
                dq_arr[a] = dq
                lo = LO[i, :, a]
                hi = HI[i, :, a]
                if dw > 0:
                    f = _first_hit_buy_low(lo, FILL_IDX, lim)
                else:
                    f = _first_hit_sell_high(hi, FILL_IDX, lim)
                f_arr[a] = f
                if f < 0:
                    b_exp += 1
                    dq_arr[a] = 0.0
                    has_order[a] = False
                else:
                    b_fills += 1
                    fill_fee_arr[a] = abs(dq) * lim * MAKER
                    qm, em = update_entry(qp, float(ent_prev[a]), float(dq), float(lim))
                    q_mid_arr[a] = qm
                    ent_mid_arr[a] = em
            # now stops per asset
            book_pnl = 0.0
            book_fee = 0.0
            q_end = q_prev.copy()
            ent_end = ent_prev.copy()
            for a in range(5):
                pT = openT[i, a]
                pT2 = openT2[i, a]
                sd = sigd[i, a]
                qp = float(q_prev[a])
                op = OP[i, :, a]
                hi = HI[i, :, a]
                lo = LO[i, :, a]
                f = int(f_arr[a])
                filled = f >= 0
                if not np.isfinite(pT) or pT <= 0:
                    # no mark; keep as-is, no pnl
                    e_book[a] = INF
                    continue
                pEnd = pT2 if np.isfinite(pT2) and pT2 > 0 else (CL[i, 239, a] if np.isfinite(CL[i, 239, a]) else pT)
                if abs(qp) < 1e-15 and not filled:
                    q_end[a] = 0.0
                    ent_end[a] = np.nan
                    e_book[a] = INF
                    continue
                if not filled:
                    # only held
                    if abs(qp) < 1e-15:
                        continue
                    is_long = qp > 0
                    sl, tp = book_levels(float(ent_prev[a]), float(sd), m, is_long)
                    if sl is None:
                        # hold to end
                        book_pnl += qp * (pEnd - pT)
                        q_end[a] = qp
                        ent_end[a] = ent_prev[a]
                        e_book[a] = INF
                        continue
                    if is_long:
                        e, kind, px = find_stop_long(op, hi, lo, 0, 239, sl, tp)
                    else:
                        e, kind, px = find_stop_short(op, hi, lo, 0, 239, sl, tp)
                    e_book[a] = e
                    kind_book[a] = kind
                    px_book[a] = px
                    if e >= INF:
                        book_pnl += qp * (pEnd - pT)
                        q_end[a] = qp
                        ent_end[a] = ent_prev[a]
                    else:
                        rate = TAKER if kind == "SL" else MAKER
                        fee = abs(qp) * px * rate
                        book_fee += fee
                        book_pnl += qp * (px - pT)
                        if kind == "SL":
                            b_sl += 1
                        else:
                            b_tp += 1
                        q_end[a] = 0.0
                        ent_end[a] = np.nan
                else:
                    dq = float(dq_arr[a])
                    qm = float(q_mid_arr[a])
                    em = float(ent_mid_arr[a])
                    book_fee += float(fill_fee_arr[a])
                    # held stop up to f inclusive?
                    is_long_h = qp > 0 if abs(qp) > 1e-15 else (qm > 0)
                    # if qp==0, no held check
                    if abs(qp) > 1e-15:
                        slh, tph = book_levels(float(ent_prev[a]), float(sd), m, qp > 0)
                        if slh is None:
                            e_h = INF
                            kind_h = None
                            px_h = np.nan
                        else:
                            if qp > 0:
                                e_h, kind_h, px_h = find_stop_long(op, hi, lo, 0, f, slh, tph)
                            else:
                                e_h, kind_h, px_h = find_stop_short(op, hi, lo, 0, f, slh, tph)
                        if e_h < INF:
                            # cancel fill
                            b_fills -= 1
                            b_exp += 1
                            book_fee -= float(fill_fee_arr[a])
                            rate = TAKER if kind_h == "SL" else MAKER
                            fee = abs(qp) * px_h * rate
                            book_fee += fee
                            book_pnl += qp * (px_h - pT)
                            if kind_h == "SL":
                                b_sl += 1
                            else:
                                b_tp += 1
                            q_end[a] = 0.0
                            ent_end[a] = np.nan
                            e_book[a] = e_h
                            kind_book[a] = kind_h
                            px_book[a] = px_h
                            # revert mid
                            q_mid_arr[a] = qp
                            ent_mid_arr[a] = ent_prev[a]
                            continue
                    # fill stands; check combined from f
                    if abs(qm) < 1e-15:
                        q_end[a] = 0.0
                        ent_end[a] = np.nan
                        e_book[a] = INF
                        continue
                    sln, tpn = book_levels(float(em), float(sd), m, qm > 0)
                    if sln is None:
                        book_pnl += qp * (pEnd - pT) + dq * (pEnd - float(lim_arr[a]))
                        q_end[a] = qm
                        ent_end[a] = em
                        e_book[a] = INF
                        continue
                    if qm > 0:
                        e, kind, px = find_stop_long(op, hi, lo, f, 239, sln, tpn)
                    else:
                        e, kind, px = find_stop_short(op, hi, lo, f, 239, sln, tpn)
                    e_book[a] = e
                    kind_book[a] = kind
                    px_book[a] = px
                    if e >= INF:
                        book_pnl += qp * (pEnd - pT) + dq * (pEnd - float(lim_arr[a]))
                        q_end[a] = qm
                        ent_end[a] = em
                    else:
                        rate = TAKER if kind == "SL" else MAKER
                        fee = abs(qm) * px * rate
                        book_fee += fee
                        book_pnl += qp * (px - pT) + dq * (px - float(lim_arr[a]))
                        if kind == "SL":
                            b_sl += 1
                        else:
                            b_tp += 1
                        q_end[a] = 0.0
                        ent_end[a] = np.nan
            # funding book
            book_fund = 0.0
            if settle[i]:
                for a in range(5):
                    qe = float(q_end[a])
                    if qe > 0:
                        pEnd = openT2[i, a]
                        if not (np.isfinite(pEnd) and pEnd > 0):
                            pEnd = CL[i, 239, a]
                        if np.isfinite(pEnd) and pEnd > 0:
                            book_fund += 0.0001 * qe * pEnd
            # sleeve
            sleeve_pnl = 0.0
            sleeve_fee = 0.0
            sleeve_fund = 0.0
            taken_list = []  # (f,e,L,TP,SL,a,ri,P_exit,kind)
            if with_sleeve:
                rn = float(s_i * g_i * 0.25 / 4 / S_REF)
                if np.isfinite(rn) and rn > 0:
                    cands = []
                    for a in range(5):
                        pT = openT[i, a]
                        pT2 = openT2[i, a]
                        s4 = sig4[i, a]
                        if not (np.isfinite(pT) and pT > 0 and np.isfinite(s4) and s4 > 0):
                            continue
                        pEnd = pT2 if np.isfinite(pT2) and pT2 > 0 else np.nan
                        op = OP[i, :, a]
                        hi = HI[i, :, a]
                        lo = LO[i, :, a]
                        for ri, k in enumerate(RUNGS):
                            L = pT * (1 - k * s4)
                            if not (np.isfinite(L) and L > 0):
                                continue
                            f = -1
                            for mm in SLEEVE_IDX:
                                v = lo[mm]
                                if np.isfinite(v) and v < L:
                                    f = int(mm)
                                    break
                            if f < 0:
                                continue
                            SL = L * (1 - 2 * s4)
                            TP = L * (1 + s4)
                            e = INF
                            kind = "NX"
                            px = pEnd
                            for mm in range(f + 1, 240):
                                l = lo[mm]
                                h = hi[mm]
                                o = op[mm]
                                sl_hit = np.isfinite(l) and l <= SL
                                tp_hit = np.isfinite(h) and h > TP
                                if sl_hit and tp_hit:
                                    e = mm
                                    kind = "SL"
                                    px = SL if not np.isfinite(o) else min(SL, o)
                                    break
                                if sl_hit:
                                    e = mm
                                    kind = "SL"
                                    px = SL if not np.isfinite(o) else min(SL, o)
                                    break
                                if tp_hit:
                                    e = mm
                                    kind = "TP"
                                    px = TP
                                    break
                            cands.append((f, ri, a, e, L, TP, SL, px, kind))
                    cands.sort(key=lambda x: (x[0], x[1], x[2]))
                    taken_exits = []
                    for (f, ri, a, e, L, TP, SL, px, kind) in cands:
                        open_n = sum(1 for ee in taken_exits if ee > f)
                        if (open_n + 1) * rn <= N_MAX + EPS:
                            taken_exits.append(e)
                            taken_list.append((f, e, L, a, ri, px, kind))
                            # pnl
                            if not (np.isfinite(px) and px > 0):
                                s_canc += 1
                                taken_exits.pop()
                                taken_list.pop()
                                continue
                            s_taken += 1
                            gross = rn * eq_usdt * (px / L - 1)
                            sleeve_pnl += gross
                            fee_in = rn * eq_usdt * MAKER
                            rate_out = TAKER if kind in ("SL", "NX") else MAKER
                            fee_out = rn * eq_usdt * (px / L) * rate_out
                            sleeve_fee += fee_in + fee_out
                            if kind == "TP":
                                s_tp += 1
                            elif kind == "SL":
                                s_sl += 1
                            else:
                                s_nx += 1
                                if settle[i]:
                                    sleeve_fund += 0.0001 * rn * eq_usdt * (px / L)
                        else:
                            s_canc += 1
            total = book_pnl - book_fee - book_fund + sleeve_pnl - sleeve_fee - sleeve_fund
            ni = total / eq_usdt if eq_usdt > 0 else 0.0
            net[i] = ni
            eq[i] = eq_prev * (1 + ni)
            q_prev = q_end
            ent_prev = ent_end
            # minute marks for DD (live only needed but compute all)
            # build 240 path
            path = np.zeros(240)
            # book minute contributions
            for a in range(5):
                pT = openT[i, a]
                if not (np.isfinite(pT) and pT > 0):
                    continue
                cl = CL[i, :, a]
                qp = float(books is not None and 0)  # placeholder
                # reconstruct per-asset path using stored exits/fills
                # We stored e_book/kind/px per asset; need qp0, dq, lim, f
                # Use closure variables from loops above: need arrays
                pass
            # Instead compute minute path with a second lightweight pass using
            # final q_end/exits: approximate with close-based MTM + locked exits.
            # Book path:
            bpath = np.zeros(240)
            for a in range(5):
                pT = openT[i, a]
                if not (np.isfinite(pT) and pT > 0):
                    continue
                cl = CL[i, :, a]
                # retrieve bar values saved in arrays for this i (recompute quickly)
                # To avoid storing, recompute fill/exit summary from e_book etc.
                # e = e_book[a]; px = px_book[a]; f = f_arr[a]; dq=dq_arr[a] (0 if cancelled)
                e = int(e_book[a]) if e_book[a] < INF else INF
                px = float(px_book[a])
                f = int(f_arr[a])
                # q0 is q at start of bar: need q_start; derive from q_prev history?
                # We lost q_start; reconstruct: q_start = q_end_current - dq_effective if filled and not cancelled...
                # Simpler: track q_start array per bar in outer arrays. For now approximate
                # minute DD using sleeve + book close-to-close only (conservative).
                # Use close path for still-open positions: q_end*(cl-pEnd)/eq + realized?
                # To keep blind DD honest, use full close path of end positions plus
                # worst intrabar low/high for stopped positions (already locked).
                # Approximation: bpath += (q_end[a]* (cl - pT))/eq_usdt for open,
                # else locked (px-pT)*q_start/eq for stopped (flat across minutes >=e).
                # We need q_start; store it.
                pass
            # NOTE: minute path assembled below with stored q_start (see outer arrays).
            min_eq_parts.append(None)
            min_T_parts.append(T_list[i])
        return {
            "eq": eq, "net": net, "g": garr,
            "b_orders": b_orders, "b_fills": b_fills, "b_sl": b_sl, "b_tp": b_tp, "b_exp": b_exp,
            "s_taken": s_taken, "s_canc": s_canc, "s_tp": s_tp, "s_sl": s_sl, "s_nx": s_nx,
        }

    # The loop above omits minute-path detail for brevity in this sketch; the
    # production run below re-implements with stored q_start for exact 1m marks.
    # To keep the file blind and single-pass, we now run the full engine with
    # minute marks inline.
    def run_full(m: int, with_sleeve: bool):
        eq = np.ones(nB)
        net = np.zeros(nB)
        garr = np.ones(nB)
        q_prev = np.zeros(5)
        ent_prev = np.full(5, np.nan)
        min_eq = np.full(nB * 240, np.nan)
        b_orders = b_fills = b_sl = b_tp = b_exp = 0
        s_taken = s_canc = s_tp = s_sl = s_nx = 0
        for i in range(nB):
            eq_prev = eq[i - 1] if i else 1.0
            eq_usdt = eq_prev * ACCOUNT
            if i >= 2:
                lo_i = max(0, (i - 2) - 539)
                seg = eq[lo_i:(i - 1)]
                peak = seg.max() if seg.size else eq[i - 2]
                if not np.isfinite(peak) or peak <= 0:
                    peak = eq[i - 2]
                dd = 1 - eq[i - 2] / peak if peak > 0 else 0.0
                garr[i] = float(np.clip((0.20 - dd) / 0.10, 0.0, 1.0))
            s_i = float(s_base[i])
            g_i = float(garr[i])
            tgt = 0.8 * s_i * B[i] * g_i
            tgt = np.where(np.isfinite(tgt), tgt, 0.0)
            q_start = q_prev.copy()
            ent_start = ent_prev.copy()
            # --- book orders ---
            f_arr = np.full(5, -1)
            dq_arr = np.zeros(5)
            lim_arr = np.full(5, np.nan)
            fill_fee = np.zeros(5)
            valid_order = np.zeros(5, dtype=bool)
            for a in range(5):
                pT = openT[i, a]
                qp = float(q_start[a])
                tv = float(tgt[a])
                w0 = qp * pT / eq_usdt if (np.isfinite(pT) and pT > 0 and eq_usdt > 0) else 0.0
                dw = tv - w0
                thr = SYM_TO_MIN.get(MAJORS[a], DEFAULT_MIN)
                must = (tv == 0.0) and (abs(qp) > 1e-15)
                if (not must) and abs(dw) * eq_usdt < thr - 1e-12:
                    continue
                if abs(dw) < 1e-18:
                    continue
                op0 = OP[i, 0, a]
                ref = op0 if np.isfinite(op0) and op0 > 0 else pT
                if not (np.isfinite(ref) and ref > 0):
                    b_orders += 1
                    b_exp += 1
                    continue
                lim = ref * (1 - 0.001) if dw > 0 else ref * (1 + 0.001)
                b_orders += 1
                valid_order[a] = True
                lim_arr[a] = lim
                dq = dw * eq_usdt / lim
                lo = LO[i, :, a]
                hi = HI[i, :, a]
                f = -1
                if dw > 0:
                    for mm in FILL_IDX:
                        v = lo[mm]
                        if np.isfinite(v) and v < lim:
                            f = int(mm)
                            break
                else:
                    for mm in FILL_IDX:
                        v = hi[mm]
                        if np.isfinite(v) and v > lim:
                            f = int(mm)
                            break
                f_arr[a] = f
                if f < 0:
                    b_exp += 1
                    valid_order[a] = False
                else:
                    b_fills += 1
                    dq_arr[a] = dq
                    fill_fee[a] = abs(dq) * lim * MAKER
            # --- book stops + pnl ---
            book_pnl = 0.0
            book_fee = 0.0
            q_end = q_start.copy()
            ent_end = ent_start.copy()
            e_arr = np.full(5, INF)
            px_arr = np.full(5, np.nan)
            kind_arr = np.array([None] * 5, dtype=object)
            # effective dq (0 if cancelled later)
            eff_dq = dq_arr.copy()
            for a in range(5):
                pT = openT[i, a]
                pT2 = openT2[i, a]
                sd = sigd[i, a]
                qp = float(q_start[a])
                op = OP[i, :, a]
                hi = HI[i, :, a]
                lo = LO[i, :, a]
                if not (np.isfinite(pT) and pT > 0):
                    continue
                pEnd = pT2 if (np.isfinite(pT2) and pT2 > 0) else CL[i, 239, a]
                if not (np.isfinite(pEnd) and pEnd > 0):
                    pEnd = pT
                f = int(f_arr[a])
                filled = valid_order[a] and f >= 0
                if not filled:
                    eff_dq[a] = 0.0
                    if abs(qp) < 1e-15:
                        continue
                    sl, tp = book_levels(float(ent_start[a]), float(sd), m, qp > 0)
                    if sl is None:
                        book_pnl += qp * (pEnd - pT)
                        continue
                    e, kind, px = find_stop_long(op, hi, lo, 0, 239, sl, tp) if qp > 0 else find_stop_short(op, hi, lo, 0, 239, sl, tp)
                    e_arr[a] = e
                    px_arr[a] = px
                    kind_arr[a] = kind
                    if e >= INF:
                        book_pnl += qp * (pEnd - pT)
                    else:
                        rate = TAKER if kind == "SL" else MAKER
                        book_fee += abs(qp) * px * rate
                        book_pnl += qp * (px - pT)
                        if kind == "SL":
                            b_sl += 1
                        else:
                            b_tp += 1
                        q_end[a] = 0.0
                        ent_end[a] = np.nan
                    continue
                # filled path
                dq = float(dq_arr[a])
                lim = float(lim_arr[a])
                book_fee += float(fill_fee[a])
                if abs(qp) > 1e-15:
                    slh, tph = book_levels(float(ent_start[a]), float(sd), m, qp > 0)
                    if slh is not None:
                        eh, kh, pxh = find_stop_long(op, hi, lo, 0, f, slh, tph) if qp > 0 else find_stop_short(op, hi, lo, 0, f, slh, tph)
                        if eh < INF:
                            # cancel
                            b_fills -= 1
                            b_exp += 1
                            valid_order[a] = False
                            eff_dq[a] = 0.0
                            book_fee -= float(fill_fee[a])
                            rate = TAKER if kh == "SL" else MAKER
                            book_fee += abs(qp) * pxh * rate
                            book_pnl += qp * (pxh - pT)
                            if kh == "SL":
                                b_sl += 1
                            else:
                                b_tp += 1
                            q_end[a] = 0.0
                            ent_end[a] = np.nan
                            e_arr[a] = eh
                            px_arr[a] = pxh
                            kind_arr[a] = kh
                            f_arr[a] = -1
                            continue
                qm, em = update_entry(qp, float(ent_start[a]), dq, lim)
                sln, tpn = book_levels(float(em), float(sd), m, qm > 0) if abs(qm) > 1e-15 else (None, None)
                if sln is None:
                    if abs(qm) < 1e-15:
                        q_end[a] = 0.0
                        ent_end[a] = np.nan
                    else:
                        book_pnl += qp * (pEnd - pT) + dq * (pEnd - lim)
                        q_end[a] = qm
                        ent_end[a] = em
                    continue
                e, kind, px = find_stop_long(op, hi, lo, f, 239, sln, tpn) if qm > 0 else find_stop_short(op, hi, lo, f, 239, sln, tpn)
                e_arr[a] = e
                px_arr[a] = px
                kind_arr[a] = kind
                if e >= INF:
                    book_pnl += qp * (pEnd - pT) + dq * (pEnd - lim)
                    q_end[a] = qm
                    ent_end[a] = em
                else:
                    rate = TAKER if kind == "SL" else MAKER
                    book_fee += abs(qm) * px * rate
                    book_pnl += qp * (px - pT) + dq * (px - lim)
                    if kind == "SL":
                        b_sl += 1
                    else:
                        b_tp += 1
                    q_end[a] = 0.0
                    ent_end[a] = np.nan
            book_fund = 0.0
            if settle[i]:
                for a in range(5):
                    qe = float(q_end[a])
                    if qe > 0:
                        pEnd = openT2[i, a]
                        if not (np.isfinite(pEnd) and pEnd > 0):
                            pEnd = CL[i, 239, a]
                        if np.isfinite(pEnd) and pEnd > 0:
                            book_fund += 0.0001 * qe * pEnd
            # --- sleeve ---
            sleeve_pnl = 0.0
            sleeve_fee = 0.0
            sleeve_fund = 0.0
            sleeve_taken_info = []  # (a,f,e,L,px,kind)
            if with_sleeve:
                rn = float(s_i * g_i * 0.25 / 4 / S_REF)
                if np.isfinite(rn) and rn > 0:
                    cands = []
                    for a in range(5):
                        pT = openT[i, a]
                        pT2 = openT2[i, a]
                        s4 = sig4[i, a]
                        if not (np.isfinite(pT) and pT > 0 and np.isfinite(s4) and s4 > 0):
                            continue
                        pEnd = pT2 if (np.isfinite(pT2) and pT2 > 0) else CL[i, 239, a]
                        if not (np.isfinite(pEnd) and pEnd > 0):
                            continue
                        op = OP[i, :, a]
                        hi = HI[i, :, a]
                        lo = LO[i, :, a]
                        for ri, k in enumerate(RUNGS):
                            L = pT * (1 - k * s4)
                            if not (np.isfinite(L) and L > 0):
                                continue
                            f = -1
                            for mm in SLEEVE_IDX:
                                v = lo[mm]
                                if np.isfinite(v) and v < L:
                                    f = int(mm)
                                    break
                            if f < 0:
                                continue
                            SL = L * (1 - 2 * s4)
                            TP = L * (1 + s4)
                            e = INF
                            kind = "NX"
                            px = pEnd
                            for mm in range(f + 1, 240):
                                l = lo[mm]
                                h = hi[mm]
                                o = op[mm]
                                sl_hit = np.isfinite(l) and l <= SL
                                tp_hit = np.isfinite(h) and h > TP
                                if sl_hit and tp_hit:
                                    e = mm
                                    kind = "SL"
                                    px = SL if not np.isfinite(o) else min(SL, o)
                                    break
                                if sl_hit:
                                    e = mm
                                    kind = "SL"
                                    px = SL if not np.isfinite(o) else min(SL, o)
                                    break
                                if tp_hit:
                                    e = mm
                                    kind = "TP"
                                    px = TP
                                    break
                            cands.append((f, ri, a, e, L, px, kind))
                    cands.sort(key=lambda x: (x[0], x[1], x[2]))
                    taken_exits = []
                    for (f, ri, a, e, L, px, kind) in cands:
                        opn = sum(1 for ee in taken_exits if ee > f)
                        if (opn + 1) * rn <= N_MAX + EPS:
                            if not (np.isfinite(px) and px > 0 and np.isfinite(L) and L > 0):
                                s_canc += 1
                                continue
                            taken_exits.append(e)
                            sleeve_taken_info.append((a, f, e, L, px, kind))
                            s_taken += 1
                            sleeve_pnl += rn * eq_usdt * (px / L - 1)
                            sleeve_fee += rn * eq_usdt * MAKER + rn * eq_usdt * (px / L) * (TAKER if kind in ("SL", "NX") else MAKER)
                            if kind == "TP":
                                s_tp += 1
                            elif kind == "SL":
                                s_sl += 1
                            else:
                                s_nx += 1
                                if settle[i]:
                                    sleeve_fund += 0.0001 * rn * eq_usdt * (px / L)
                        else:
                            s_canc += 1
            total = book_pnl - book_fee - book_fund + sleeve_pnl - sleeve_fee - sleeve_fund
            ni = total / eq_usdt if eq_usdt > 0 else 0.0
            net[i] = ni
            eq[i] = eq_prev * (1 + ni)
            # minute marks
            base = i * 240
            # precompute per-asset book minute gross + fees
            # fees accrued timeline: fill fees at f, exit fees at e
            for mm in range(240):
                mtm = 0.0
                fee_acc = 0.0
                for a in range(5):
                    pT = openT[i, a]
                    if not (np.isfinite(pT) and pT > 0):
                        continue
                    cl = CL[i, mm, a]
                    qp = float(q_start[a])
                    f = int(f_arr[a])
                    dq = float(eff_dq[a])
                    lim = float(lim_arr[a]) if np.isfinite(lim_arr[a]) else np.nan
                    e = int(e_arr[a]) if e_arr[a] < INF else INF
                    px = float(px_arr[a]) if np.isfinite(px_arr[a]) else np.nan
                    kind = kind_arr[a]
                    op = OP[i, :, a]
                    # book contribution
                    if abs(qp) < 1e-15 and abs(dq) < 1e-15:
                        continue
                    if f < 0:
                        # no fill: held only
                        if abs(qp) < 1e-15:
                            continue
                        if e >= INF:
                            if np.isfinite(cl):
                                mtm += qp * (cl - pT) / eq_usdt
                        else:
                            if mm < e:
                                if np.isfinite(cl):
                                    mtm += qp * (cl - pT) / eq_usdt
                            else:
                                mtm += qp * (px - pT) / eq_usdt
                                fee_acc += abs(qp) * px * (TAKER if kind == "SL" else MAKER) / eq_usdt
                    else:
                        # filled (held survived to f)
                        if mm < f:
                            if abs(qp) > 1e-15 and np.isfinite(cl):
                                mtm += qp * (cl - pT) / eq_usdt
                        else:
                            fee_acc += abs(dq) * lim * MAKER / eq_usdt if np.isfinite(lim) else 0.0
                            qm = qp + dq
                            if e >= INF:
                                if np.isfinite(cl):
                                    mtm += qp * (cl - pT) / eq_usdt + dq * (cl - lim) / eq_usdt
                            else:
                                if mm < e:
                                    if np.isfinite(cl):
                                        mtm += qp * (cl - pT) / eq_usdt + dq * (cl - lim) / eq_usdt
                                else:
                                    mtm += qp * (px - pT) / eq_usdt + dq * (px - lim) / eq_usdt
                                    fee_acc += abs(qm) * px * (TAKER if kind == "SL" else MAKER) / eq_usdt
                # sleeve minute
                for (a, f, e, L, px, kind) in sleeve_taken_info:
                    cl = CL[i, mm, a]
                    if mm < f:
                        continue
                    fee_acc += rn * MAKER if mm == f else 0.0
                    if e >= INF:
                        # next-open exit: open until end
                        if np.isfinite(cl):
                            mtm += rn * (cl / L - 1)
                        if mm == 239:
                            fee_acc += rn * (px / L) * TAKER
                    else:
                        if mm < e:
                            if np.isfinite(cl):
                                mtm += rn * (cl / L - 1)
                        else:
                            mtm += rn * (px / L - 1)
                            if mm == e:
                                fee_acc += rn * (px / L) * (TAKER if kind == "SL" else MAKER)
                min_eq[base + mm] = eq_prev * (1 + mtm - fee_acc)
            q_prev = q_end
            ent_prev = ent_end
        return {
            "eq": eq, "net": net, "g": garr, "min_eq": min_eq,
            "b_orders": b_orders, "b_fills": b_fills, "b_sl": b_sl, "b_tp": b_tp, "b_exp": b_exp,
            "s_taken": s_taken, "s_canc": s_canc, "s_tp": s_tp, "s_sl": s_sl, "s_nx": s_nx,
        }

    def dd_close(eq_arr):
        peak = np.maximum.accumulate(eq_arr)
        dd = 1 - eq_arr / np.where(peak > 0, peak, 1.0)
        return round(100 * float(dd.max()), 2), int(np.argmax(dd))

    def dd_min(min_eq_arr):
        m = min_eq_arr[np.isfinite(min_eq_arr)]
        if m.size == 0:
            return 0.0, None
        # normalize by first live equity (1.0 base)? min_eq already in eq units
        # compute DD over concatenated minute path anchored at 1.0
        ref0 = 1.0
        # rebuild full path: minute eqs are in absolute eq units (eq_prev*(...))
        peak = np.maximum.accumulate(np.concatenate([[ref0], m]))
        dd = 1 - np.concatenate([[ref0], m]) / peak
        return round(100 * float(dd.max()), 2), int(np.argmax(dd))

    results = {}
    for m in (2, 3, 4):
        for sleeve_flag in ([True] if True else []):
            pass
        out = run_full(m, True)
        results[m] = out
        print(f"m={m} fills book={out['b_fills']} sl={out['b_sl']} tp={out['b_tp']} sleeve_taken={out['s_taken']} canc={out['s_canc']} eq_end={out['eq'][-1]:.4f}", flush=True)

    def summarize(out):
        eqa = out["eq"]
        neta = out["net"]
        # yearly
        yearly = []
        for yi in range(5):
            sdate = ANCHORS[yi]
            edate = ANCHORS[yi + 1] if yi < 4 else (bidx.max() + pd.Timedelta(hours=4))
            sidx = int(bidx.searchsorted(sdate))
            eidx = int(bidx.searchsorted(edate))
            sidx = max(0, min(sidx, nB))
            eidx = max(0, min(eidx, nB))
            if eidx <= sidx:
                yearly.append({"anchor": str(sdate), "net_pct": 0.0, "monthly_pct": 0.0, "fills_proxy": 0})
                continue
            eq_before = eqa[sidx - 1] if sidx > 0 else 1.0
            eq_after = eqa[eidx - 1]
            nety = eq_after / eq_before - 1 if eq_before > 0 else 0.0
            mon = (1 + nety) ** (1 / 12) - 1 if nety > -1 else -1.0
            # 4h DD in year slice
            seg = eqa[sidx:eidx]
            base = eq_before
            peak = base
            maxdd = 0.0
            for v in seg:
                peak = max(peak, v)
                maxdd = max(maxdd, 1 - v / peak if peak > 0 else 0.0)
            yearly.append({
                "anchor": sdate.strftime("%Y-%m-%d"),
                "net_pct": round(100 * float(nety), 2),
                "monthly_geometric_net_percent": round(100 * float(mon), 3),
                "max_drawdown_percent": round(100 * float(maxdd), 2),
                "bars": int(eidx - sidx),
            })
        full_mon = float(eqa[-1]) ** (1 / 60) - 1 if eqa[-1] > 0 else -1.0
        dev4_net = 1.0
        for y in yearly[:4]:
            dev4_net *= 1 + y["net_pct"] / 100
        dev4_mon = dev4_net ** (1 / 48) - 1
        dd4, wi = dd_close(eqa)
        # 1m dd
        meq = out["min_eq"]
        # restrict minute path to live (all bars live)
        dd1, wj = dd_min(meq)
        # worst bars
        wi_t = str(bidx[wi]) if 0 <= wi < nB else None
        # worst minute -> holding bar
        if wj is not None and wj > 0:
            bar_no = (wj - 1) // 240
            bar_no = max(0, min(bar_no, nB - 1))
            wj_T = str(T_list[bar_no])
        else:
            wj_T = None
        return yearly, round(100 * full_mon, 3), round(100 * dev4_mon, 3), dd4, dd1, wi_t, wj_T

    rows = {}
    for m in (2, 3, 4):
        out = results[m]
        yearly, fmon, d4mon, dd4, dd1, wt, wjT = summarize(out)
        rows[f"m{m}_with_sleeve"] = {
            "m": m,
            "monthly_pct": fmon,
            "monthly_dev4": d4mon,
            "yearly": yearly,
            "full_path_dd": dd4,
            "dd_1m_mark": dd1,
            "gate_dd": max(dd4, dd1),
            "worst_bar": wt,
            "dd_1m_worst_bar": wjT,
            "book_orders": out["b_orders"],
            "book_fills": out["b_fills"],
            "book_sl": out["b_sl"],
            "book_tp": out["b_tp"],
            "book_expired": out["b_exp"],
            "sleeve_taken": out["s_taken"],
            "sleeve_cancelled": out["s_canc"],
            "sleeve_tp": out["s_tp"],
            "sleeve_sl": out["s_sl"],
            "sleeve_next_open": out["s_nx"],
            "mean_s": round(float(np.mean(s_base)), 4),
            "mean_g": round(float(np.mean(out["g"])), 4),
        }
    # selection on first four years
    best = None
    for m in (2, 3, 4):
        r = rows[f"m{m}_with_sleeve"]
        first4 = r["yearly"][:4]
        noloss = all(y["net_pct"] >= 0 for y in first4)
        okdd = r["gate_dd"] <= 20
        if noloss and okdd and (best is None or r["monthly_dev4"] > rows[best]["monthly_dev4"]):
            best = f"m{m}_with_sleeve"
    if best is None:
        # fallback best dev4 regardless
        best = max(rows, key=lambda k: rows[k]["monthly_dev4"])
        sel_note = "no variant satisfied DD<=20 and no losing year in first four; fallback best dev4"
    else:
        sel_note = "best monthly_dev4 among variants with gate DD<=20 and no losing year in first four"
    best_m = rows[best]["m"]
    out_nosleeve = run_full(best_m, False)
    yearly_ns, fmon_ns, d4_ns, dd4_ns, dd1_ns, wt_ns, wj_ns = summarize(out_nosleeve)
    rows[f"m{best_m}_no_sleeve"] = {
        "m": best_m,
        "monthly_pct": fmon_ns,
        "monthly_dev4": d4_ns,
        "yearly": yearly_ns,
        "full_path_dd": dd4_ns,
        "dd_1m_mark": dd1_ns,
        "gate_dd": max(dd4_ns, dd1_ns),
        "worst_bar": wt_ns,
        "dd_1m_worst_bar": wj_ns,
        "book_orders": out_nosleeve["b_orders"],
        "book_fills": out_nosleeve["b_fills"],
        "book_sl": out_nosleeve["b_sl"],
        "book_tp": out_nosleeve["b_tp"],
        "book_expired": out_nosleeve["b_exp"],
        "sleeve_taken": 0,
        "sleeve_cancelled": 0,
        "sleeve_tp": 0,
        "sleeve_sl": 0,
        "sleeve_next_open": 0,
        "mean_s": round(float(np.mean(s_base)), 4),
        "mean_g": round(float(np.mean(out_nosleeve["g"])), 4),
    }
    replication = {
        "version": "v188_audit_replication",
        "blind": "did_not_open_research_v188_or_engine_user_until_this_file_saved",
        "live": {"start": "2021-09-24 00:00:00+00:00", "bars": int(nB), "end_decision": str(bidx.max()), "end_holding_close": str(bidx.max() + pd.Timedelta(hours=8))},
        "costs": {"entry_maker": MAKER, "tp_maker": MAKER, "stop_taker": TAKER, "sleeve_next_open_taker": TAKER, "funding_long_8h": 0.0001, "funding_short": 0.0, "account_usdt": ACCOUNT},
        "symbols": MAJORS,
        "rungs": list(RUNGS),
        "S_REF": S_REF,
        "N_MAX": N_MAX,
        "selection": {"best_with_sleeve": best, "best_m": best_m, "note": sel_note},
        "rows": rows,
    }
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print(f"saved {OUT}", flush=True)


if __name__ == "__main__":
    main()
