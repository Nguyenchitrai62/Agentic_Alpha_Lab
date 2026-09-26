"""v172 blind audit Part A replication.

Blind rule: does NOT read research/.../v172/*, v172_result.json nor
v172_sleeve_realistic.py until replication.json is saved. Independent
implementation from OPENCODE_V172_AUDIT.md + OPENCODE_V171_AUDIT.md only.
May import engine_real for v154_books, context, constants (like v171 audit),
and v144/v135 for the W=60 execution arrays (like v170 audit).

Spec (frozen before running):
  Identical to the v171 sleeve except the fill cost:
    slippage per side = max(0.0002, 0.25 * (high - low) / open) of the fill
    minute (entry: minute m+1 of the holding bar T; exit: minute 0 of the
    next 4h bar T + 4h);
    entry = open(m+1) * (1 + s_in), exit = open(T + 4h) * (1 - s_out);
    r = exit / entry - 1 - 0.001 - funding settled at T + 4h.
  Sleeve symbols BNB/BTC/ETH/SOL/XRP perps, grid t = 4h bars from
  2020-02-01 00:00 UTC to last books bar, holding bar T = t + 4h.
  sigma(t) = std of 4h open-to-open pct changes over 360 bars ending at t
  (min 120). Event: first m in 16..238 of T with
  close1m(m) / open4h(T) - 1 <= -k * sigma(t).
  k per anchor from (2, 2.5, 3, 3.5, 4) by pre-anchor Sharpe (mean/std) of
  0.25 * sum_sym r with THIS cost, selection [2020-02-01+30d, anchor-1d),
  applied [anchor, anchor+365d).
  Books: engine_real (all realism), execution W = 60 minutes (v170),
  target 0.25, governor; net[i] += g[i] * size / 0.25 * sleeve[i] live.
  Rows: books alone (must be 3.802 / 18.93), size 0.25, 0.20, 0.15;
  sleeve alone per anchor (k, net, DD, events).

Frozen blind assumptions (documented before running):
  A1 Grid pd.date_range(2020-02-01 00:00 UTC, last books bar, freq 4h).
  A2 Windows half-open; anchors = v92.ANCHORS (2021-09-24 ... 2025-09-24).
  A3 sigma finite and > 0 else no event.
  A4 1m grids: drop duplicate open_time keep last, sort, reindex to the
     full minute grid, within-bar forward-fill only (leading NaNs stay NaN)
     for open/high/low/close separately. Trigger close and entry open use
     the ffilled close/open grids (same as v171 audit).
  A5 s_in from the ENTRY minute (m+1) ffilled H/L/O:
     s_in = max(0.0002, 0.25 * (H - L) / O); if H/L/O non-finite, O <= 0,
     or H < L -> s_in = 0.0002. Entry = O(m+1) * (1 + s_in).
  A6 s_out / exit base from cube row i+1 minute 0 (the minute starting at
     T + 4h): base = O[i+1, 0] if finite and > 0 else the 4h open(T+4h)
     fallback; s_out = max(0.0002, 0.25 * (H[i+1,0]-L[i+1,0]) / O[i+1,0])
     when H/L/O finite, O > 0, H >= L, else 0.0002. Exit = base*(1-s_out).
     i + 1 >= n -> r = 0. If both 1m and 4h exit opens missing/nonpositive
     -> r = 0. Funding missing -> 0.0.
  A7 No-event (r=0) whenever: 4h open(T) missing/nonpositive, trigger needs
     finite dip, entry open missing/nonpositive, or no trigger minute.
  A8 Score = mean/std over selection window (zeros included); bad std ->
     -inf; ties -> lowest k.
  A9 Bars outside anchor windows -> sleeve 0.
  A10 Books execution = v170 W=60 arrays via v135.load_1m (keep-first dedup
     as v135 does): p0 = open@0, lo/hi = min/max over 2..59, pW = open@60
     (NaN -> p0); maker/fee/rel exactly as v170 audit. Combined loop
     mirrors engine_real.run FULL (vol scale, 20% governor with 2-bar lag
     on combined equity, budget, min-notional, funding, carry_real) with
     net[i] += g[i] * size / 0.25 * sleeve[i] on live bars.
  A11 Per-anchor sleeve report from sleeve-only equity in applied window.
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
SIZES = (0.25, 0.20, 0.15)
W_EXEC = 60
D = 0.001


def _load_engine_real():
    spec = importlib.util.spec_from_file_location(
        "v172_audit_engine_real", ROUND2 / "engine_real" / "engine_real.py")
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
    close_g = np.zeros((n, 240, len(SYMS)))
    open_g = np.zeros((n, 240, len(SYMS)))
    high_g = np.zeros((n, 240, len(SYMS)))
    low_g = np.zeros((n, 240, len(SYMS)))
    for j, sym in enumerate(SYMS):
        if sym == "BTCUSDT":
            files = sorted(glob.glob(str(ROOT / "data/raw/btc_intraday_20260924/klines_1m_20*.parquet")))
        else:
            files = sorted(glob.glob(str(ROOT / f"data/raw/majors_intraday_20260924/{sym}_1m_20*.parquet")))
        assert files, f"no 1m files for {sym}"
        parts = [pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in files]
        d = pd.concat(parts, ignore_index=True)
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        d = d.sort_values("open_time").drop_duplicates("open_time", keep="last").set_index("open_time")
        co = d["close"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        op = d["open"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        hi = d["high"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        lo = d["low"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        close_g[:, :, j] = _ffill_rows(co)
        open_g[:, :, j] = _ffill_rows(op)
        high_g[:, :, j] = _ffill_rows(hi)
        low_g[:, :, j] = _ffill_rows(lo)
        print(f"{sym}: 1m rows={len(d)} files={len(files)}", flush=True)

    MO = np.arange(16, 239)
    dip = np.zeros((n, len(MO), len(SYMS)))
    for j in range(len(SYMS)):
        with np.errstate(invalid="ignore", divide="ignore"):
            dip[:, :, j] = close_g[:, MO, j] / openT[:, j:j + 1] - 1

    # ---- per (t, sym, k) returns with v172 slippage cost ----
    r_sym_k = {}
    sin_mean_acc = {}
    sout_mean_acc = {}
    range_bind_acc = {}
    for j, sym in enumerate(SYMS):
        sig = sigma[:, j]
        oT = openT[:, j]
        e4 = exitOpen4h[:, j]
        fu = fundT2[:, j]
        base_ok = (np.isfinite(sig) & (sig > 0) & np.isfinite(oT) & (oT > 0))
        d = dip[:, :, j]
        per_k = {}
        for k in KS:
            with np.errstate(invalid="ignore"):
                mask = base_ok[:, None] & np.isfinite(d) & (d <= (-k * sig)[:, None])
            has = mask.any(axis=1)
            first = mask.argmax(axis=1)
            m_abs = MO[first]
            m1 = np.clip(m_abs + 1, 0, 239)
            idx = np.arange(n)
            entry_o = np.where(has, open_g[idx, m1, j], np.nan)
            entry_h = np.where(has, high_g[idx, m1, j], np.nan)
            entry_l = np.where(has, low_g[idx, m1, j], np.nan)
            with np.errstate(invalid="ignore", divide="ignore"):
                rng = (entry_h - entry_l) / entry_o
            s_in = np.where(np.isfinite(rng) & np.isfinite(entry_o) & (entry_o > 0)
                            & np.isfinite(entry_h) & np.isfinite(entry_l)
                            & (entry_h >= entry_l),
                            np.maximum(0.0002, 0.25 * rng), 0.0002)
            s_in = np.where(np.isfinite(s_in) & (s_in >= 0), s_in, 0.0002)
            # exit: cube row i+1 minute 0, fallback to 4h open
            nxt = np.clip(idx + 1, 0, n - 1)
            exit_o1m = open_g[nxt, 0, j]
            exit_h = high_g[nxt, 0, j]
            exit_l = low_g[nxt, 0, j]
            use_1m = has & (idx + 1 < n) & np.isfinite(exit_o1m) & (exit_o1m > 0)
            exit_base = np.where(use_1m, exit_o1m, np.where(has, e4, np.nan))
            with np.errstate(invalid="ignore", divide="ignore"):
                rng_out = (exit_h - exit_l) / exit_o1m
            s_out_raw = np.maximum(0.0002, 0.25 * rng_out)
            s_out_ok = (use_1m & np.isfinite(rng_out) & np.isfinite(exit_h)
                        & np.isfinite(exit_l) & (exit_h >= exit_l))
            s_out = np.where(s_out_ok, np.where(np.isfinite(s_out_raw), s_out_raw, 0.0002), 0.0002)
            ok = (has & np.isfinite(entry_o) & (entry_o > 0)
                  & np.isfinite(exit_base) & (exit_base > 0))
            r = np.zeros(n)
            with np.errstate(invalid="ignore", divide="ignore"):
                entry_px = entry_o[ok] * (1 + s_in[ok])
                exit_px = exit_base[ok] * (1 - s_out[ok])
                r[ok] = exit_px / entry_px - 1 - 0.001 - fu[ok]
            r[~np.isfinite(r)] = 0.0
            # zero out rows where exit bar does not exist
            r[idx + 1 >= n] = 0.0
            ok = ok & (idx + 1 < n)
            per_k[k] = r
            sin_mean_acc[(sym, k)] = float(s_in[ok].mean()) if ok.any() else 0.0
            sout_mean_acc[(sym, k)] = float(s_out[ok].mean()) if ok.any() else 0.0
            range_bind_acc[(sym, k)] = float(np.mean(
                (0.25 * np.where(np.isfinite(rng[ok]), rng[ok], 0) > 0.0002))) if ok.any() else 0.0
            print(f"{sym} k={k}: events={int(ok.sum())} "
                  f"mean_s_in={sin_mean_acc[(sym, k)] * 1e4:.1f}bps "
                  f"mean_s_out={sout_mean_acc[(sym, k)] * 1e4:.1f}bps", flush=True)
        r_sym_k[sym] = per_k

    sleeve_k = {}
    for k in KS:
        sleeve_k[k] = 0.25 * sum(r_sym_k[s][k] for s in SYMS)

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

    final_k_idx = np.full(n, np.nan)
    sleeve = np.zeros(n)
    hits = np.zeros(n, dtype=int)
    for i in range(n):
        t = grid[i]
        use = None
        for a, a_ts in zip(ANCHORS, anchors_ts):
            if a_ts <= t < a_ts + pd.Timedelta(days=365):
                use = a
                break
        if use is None:
            continue
        k = best_k[use]
        final_k_idx[i] = k
        sleeve[i] = sleeve_k[k][i]
        hits[i] = sum(1 for s in SYMS if r_sym_k[s][k][i] != 0)

    per_anchor = []
    for a, a_ts in zip(ANCHORS, anchors_ts):
        mk = (grid >= a_ts) & (grid < a_ts + pd.Timedelta(days=365))
        s = sleeve[mk]
        eq = np.cumprod(1 + s)
        net_pct = 100 * (float(eq[-1]) - 1) if len(s) else 0.0
        dd = 100 * float(np.max(1 - eq / np.maximum.accumulate(eq))) if len(s) else 0.0
        k = best_k[a]
        nev = int(sum((r_sym_k[sy][k][mk] != 0).sum() for sy in SYMS))
        per_anchor.append({
            "anchor": a, "k": k,
            "sleeve_net_pct": round(float(net_pct), 2),
            "sleeve_dd_pct": round(float(dd), 2),
            "events": nev,
            "bars_nonzero": int((s != 0).sum()),
            "bars": int(mk.sum()),
            "sleeve_sum": float(s.sum()),
        })
        print(per_anchor[-1], flush=True)

    # ---- books + W=60 execution + combined loop ----
    idx = books.index
    cols = list(books.columns)
    pos = grid.get_indexer(idx)
    assert (pos >= 0).all(), "books times must exist in sleeve grid"
    sleeve_books = sleeve[pos]

    ctx = er.context(books, opens_full)
    # replace exec with W=60 arrays
    fee_b = np.zeros((len(idx), len(cols)))
    rel_b = np.zeros((len(idx), len(cols)))
    fee_s = np.zeros((len(idx), len(cols)))
    rel_s = np.zeros((len(idx), len(cols)))
    for j, s in enumerate(cols):
        m = v135.load_1m(s)
        st = _bar_stats_W(m, W_EXEC).reindex(idx + pd.Timedelta(hours=4)).set_axis(idx)
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
        fee_b[:, j] = np.where(fb, 0.0002, 0.0005)
        rel_b[:, j] = np.where(fb, -D, mv + 0.0002)
        fee_s[:, j] = np.where(fs, 0.0002, 0.0005)
        rel_s[:, j] = np.where(fs, D, mv - 0.0002)

    o = ctx["opens"].reindex(idx)[cols]
    r_next, _, _, fund = ctx["mkt"]
    carry, expo = ctx["carry_real"]
    B = books.to_numpy(dtype=float)
    v99 = er.v144.v99
    PD = er.v144.PD
    live = np.asarray((idx >= START) & (idx < END))
    nB = len(idx)
    realized = (v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
                + v99.W_CARRY * v99.CARRY_LEV * pd.Series(carry, index=idx).shift(1))
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy(dtype=float)
    s_arr = np.where(np.isnan(vol), 1.0, np.minimum(TARGET / np.where(np.isnan(vol), 1.0, vol), v99.CAP))
    mins = np.array([er.MIN_NOTIONAL.get(c, 5.0) for c in cols])

    def run_loop(sleeve_arr, size):
        m = len(cols)
        net = np.zeros(nB)
        turn = np.zeros(nB)
        g = np.ones(nB)
        eq = np.ones(nB)
        prev_w = np.zeros(m)
        prev_c = 0.0
        for i in range(nB):
            if i >= 2:
                j = i - 2
                peak = eq[max(0, j - 90 * PD + 1): j + 1].max()
                g[i] = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0.0, 1.0))
            if live[i]:
                w = v99.W_BOOKS * s_arr[i] * B[i] * g[i]
                c = v99.W_CARRY * v99.CARRY_LEV * s_arr[i] * g[i]
            else:
                w = np.zeros(m)
                c = 0.0
            ex = expo[i]
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
            exec_c = float(np.sum(np.abs(dw) * np.where(buy, fee_b[i], fee_s[i])
                                  + dw * np.where(buy, rel_b[i], rel_s[i])))
            gross = float(np.sum(w * r_next[i]))
            fundp = float(-np.sum(w * fund[i]))
            carry_p = float(c * carry[i])
            dc = c - prev_c
            carry_c = float(abs(dc) / er.CARRY_CAPITAL * ex * (er.SPOT_FEE + er.PERP_TAKER))
            ni = gross - exec_c + fundp + carry_p - carry_c
            if live[i]:
                ni += g[i] * float(sleeve_arr[i]) * size / 0.25
            net[i] = ni
            turn[i] = float(np.abs(dw).sum())
            eq[i] = (eq[i - 1] if i else 1.0) * (1 + ni)
            prev_w, prev_c = w.copy(), c
        return net, turn, g, eq

    net0, turn0, g0, _ = run_loop(np.zeros(nB), 0.25)
    s0 = v110.summarize(pd.Series(net0, index=idx), pd.Series(turn0, index=idx), pd.Series(g0, index=idx))
    print("books-alone W60 monthly", s0["monthly_pct"], "DD", s0["full_path_dd"], flush=True)
    assert s0["monthly_pct"] == 3.802, s0["monthly_pct"]
    assert s0["full_path_dd"] == 18.93, s0["full_path_dd"]
    print("audit loop books-alone reproduces 3.802/18.93", flush=True)

    combined_rows = {}
    for size in SIZES:
        netC, turnC, gC, _ = run_loop(sleeve_books, size)
        summC = v110.summarize(pd.Series(netC, index=idx), pd.Series(turnC, index=idx), pd.Series(gC, index=idx))
        key = str(size)
        combined_rows[key] = {
            "monthly_pct": summC["monthly_pct"],
            "yearly": summC["yearly"],
            "full_path_dd": summC["full_path_dd"],
            "worst_year_dd": summC["worst_year_dd"],
        }
        print(f"size {size}: monthly {summC['monthly_pct']} DD {summC['full_path_dd']}", flush=True)

    sym_events = {s: {str(k): int((r_sym_k[s][k] != 0).sum()) for k in KS} for s in SYMS}

    replication = {
        "version": "v172_audit_replication",
        "blind": "did_not_open_research_v172_until_this_file_saved",
        "books": "cached v154 books (A+B+D)/3",
        "target": TARGET,
        "governor": "20% with 2-bar lag on combined equity",
        "realism": "all on (funding, carry_real, budget, min_notional); W=60 execution",
        "engine_real_reference_W60": {"monthly_pct": s0["monthly_pct"], "full_path_dd": s0["full_path_dd"]},
        "spec": {
            "symbols": SYMS,
            "grid": f"{grid.min()} -> {grid.max()} ({n} 4h bars)",
            "holding_bar": "T = t + 4h",
            "sigma": "std of 4h open-to-open pct changes, 360 bars ending at t, min 120",
            "trigger": "first m in 16..238 with close1m(m)/open4h(T)-1 <= -k*sigma(t)",
            "entry": "open1m(m+1)*(1+s_in), s_in=max(0.0002,0.25*(H-L)/O of minute m+1)",
            "exit": "open(T+4h)*(1-s_out), base=O[i+1,0] else 4h open, s_out=max(0.0002,0.25*(H-L)/O of minute 0 of T+4h)",
            "r": "exit/entry-1-0.001-funding(T+4h floored-4h sum)",
            "sleeve_per_bar": "0.25*sum_sym r (0 without event)",
            "k_candidates": list(KS),
            "selection": "[2020-02-01+30d, anchor-1d) maximising mean/std with THIS cost",
            "applied": "[anchor, anchor+365d)",
            "books_exec": "W=60 (p0@0, lo/hi 2..59, pW@60 NaN->p0; maker 0.0002 rel -/+0.001 else taker 0.0005 + drift)",
            "combined": "net[i] += g[i]*size/0.25*sleeve[i] on live bars",
        },
        "assumptions": {f"A{i}": v for i, v in enumerate(
            ["grid date_range 2020-02-01 to last books bar",
             "half-open selection/applied windows; v92 anchors",
             "sigma finite and > 0 else no event",
             "1m grids keep-last dedup + within-bar ffill",
             "s_in from entry-minute H/L/O else 0.0002",
             "exit base O[i+1,0] else 4h open; s_out else 0.0002; i+1>=n -> 0",
             "missing/nonpositive opens or entry -> r=0; funding missing -> 0",
             "score mean/std, -inf on bad std; ties -> lowest k",
             "bars outside anchor windows -> sleeve 0",
             "W60 exec via v135.load_1m; combined loop mirrors engine_real FULL; governor on combined equity",
             "per-anchor sleeve net/DD from sleeve-only equity"], start=1)},
        "k_selection": {a: {"best_k": best_k[a], "candidates": sel_detail[a]} for a in ANCHORS},
        "per_anchor": per_anchor,
        "symbol_events_full_grid": sym_events,
        "slippage_diagnostics_bps": {
            f"{s}_k{k}": {"mean_s_in_bps": round(sin_mean_acc[(s, k)] * 1e4, 2),
                          "mean_s_out_bps": round(sout_mean_acc[(s, k)] * 1e4, 2)}
            for s in SYMS for k in KS
        },
        "sleeve_totals": {
            "bars_nonzero": int((sleeve != 0).sum()),
            "events": int(hits.sum()),
            "sum": float(sleeve.sum()),
        },
        "books_alone_W60": {
            "monthly_pct": s0["monthly_pct"],
            "yearly": s0["yearly"],
            "full_path_dd": s0["full_path_dd"],
            "worst_year_dd": s0["worst_year_dd"],
        },
        "combined_by_size": combined_rows,
        "params": {
            "start": str(START), "end": str(END),
            "account_usdt": er.ACCOUNT_USDT, "margin": er.MARGIN, "buffer": er.BUFFER,
            "vol": "rolling std 360 min 120 *sqrt(6*365); s=min(0.25/vol,2) else 1",
            "governor": "clip((0.20-(1-eq[j]/peak540))/0.10) j=i-2 on combined eq",
            "sizes": list(SIZES),
        },
    }
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print("saved", OUT)


if __name__ == "__main__":
    main()
