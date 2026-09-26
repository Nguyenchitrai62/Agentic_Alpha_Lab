"""v171 blind audit Part A replication.

Blind rule: does NOT read research/.../v171/*, v171_result.json nor
v171_robustness.json until replication.json is saved. Independent
implementation from OPENCODE_V171_AUDIT.md only. May import engine_real for
v154_books, context, funding_at_bar_open, constants.

Spec (frozen before running):
  Sleeve symbols: BNB/BTC/ETH/SOL/XRP USDT perps.
  Decision grid t = 4h bars from 2020-02-01 00:00 UTC to the last books bar
  (inclusive). Holding bar T = t + 4h.
  4h opens from data/raw/xs_universe_20260924/<SYM>_4h.parquet.
  sigma(t) = std of 4h open-to-open pct changes over the 360 bars ending at t
    (min 120). ret[i] = open[i]/open[i-1]-1 on full 4h history; sigma(t) uses
    the window of returns ending at t inclusive (all known at/before the
    close of bar t, strictly before any minute of T).
  1m klines: BTCUSDT data/raw/btc_intraday_20260924/klines_1m_20*.parquet,
    others data/raw/majors_intraday_20260924/<SYM>_1m_20*.parquet
    (drop duplicate open_time keep last; sort; forward-fill missing minutes
    strictly within each 240-minute bar slice; leading NaNs stay NaN).
  Event for (t, sym): first minute offset m in 16..238 of T whose
    1m_close(m)/open4h(T)-1 <= -k*sigma(t).
    Entry = 1m open of minute m+1 * 1.0002; exit = 4h open(T+4h) * 0.9998;
    r = exit/entry - 1 - 0.001 - funding settled at T+4h
    (sum of fundingRate floored to 4h at timestamp T+4h).
  k per anchor from (2, 2.5, 3, 3.5, 4) maximising mean/std of the per-bar
    sleeve return 0.25*sum_sym r (0 without event) over
    [2020-02-01 + 30d, anchor - 1d); applied to [anchor, anchor + 365d).

Frozen blind assumptions (documented before running):
  A1 Grid: pd.date_range(2020-02-01 00:00 UTC, last books bar, freq 4h).
      Regular by construction; bar i minute slice is [T_i, T_i+239min].
  A2 Windows use half-open intervals: selection s0 <= t < anchor-1d with
      s0 = 2020-02-01 + 30d; applied anchor <= t < anchor + 365d.
      Anchors = v92.ANCHORS (2021-09-24 ... 2025-09-24).
  A3 sigma needs finite value with sigma > 0, else no event for (t, sym).
  A4 No-event (r=0) whenever: 4h open(T) missing/nonpositive, trigger test
      needs finite dip, 1m open(m+1) missing/nonpositive, 4h open(T+4h)
      missing, or trigger minute not found. Funding missing -> 0.0.
  A5 Score = mean/std over the selection window (zeros included). std == 0
      or non-finite -> score -inf. Ties -> first (lowest k) in listed order.
  A6 Bars covered by no anchor window (before first anchor, or the 2024-09-23
      gap when 2023-09-24+365d < 2024-09-24) get final sleeve 0.
  A7 Combined: engine_real FULL loop mirrored exactly (vol scale s from
      books/carry precomputed as engine_real; 20% governor with 2-bar lag on
      the COMBINED equity path; budget/min-notional/exec/funding/carry as
      engine_real) with net[i] += g[i]*sleeve[i] on live bars. Baseline
      (sleeve 0) must reproduce engine_real 3.708 / 18.87.
  A8 Per-anchor sleeve report: sleeve-only equity within [anchor, +365d):
      net% = 100*(prod(1+sleeve)-1), DD% = close-sampled max drawdown of
      that equity, events = (t,sym) triggers, bars = bars with sleeve != 0.
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


def _load_engine_real():
    spec = importlib.util.spec_from_file_location(
        "v171_audit_engine_real", ROUND2 / "engine_real" / "engine_real.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ffill_rows(a: np.ndarray) -> np.ndarray:
    """Forward-fill NaN along each row (within-bar only, no cross-bar carry)."""
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


def main():
    er = _load_engine_real()
    v110 = er.v144.v110
    v92 = er.v144.v110.v92
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

    # ---- per-symbol 4h opens, sigma, funding, exit opens ----
    openT = np.zeros((n, len(SYMS)))
    exitOpen = np.zeros((n, len(SYMS)))
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
        oo = o.reindex(T_all).to_numpy(dtype=float)
        openT[:, j] = oo
        exitOpen[:, j] = o.reindex(T2_all).to_numpy(dtype=float)
        f = pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{sym}_funding.parquet")
        ft = pd.to_datetime(f["fundingTime"], utc=True).dt.floor("4h")
        bucket = f.groupby(ft)["fundingRate"].sum()
        fundT2[:, j] = bucket.reindex(T2_all).fillna(0.0).to_numpy(dtype=float)
        print(f"{sym}: n4h={len(o)} sigma_finite={(np.isfinite(sigma[:, j])).sum()}/{n}", flush=True)

    # ---- per-symbol 1m open/close grids (n, 240) ----
    n_min = n * 240
    mgrid = pd.date_range(T_all.min(), T_all.min() + pd.Timedelta(minutes=n_min - 1),
                          freq="1min", tz="UTC")
    assert len(mgrid) == n_min
    close_g = np.zeros((n, 240, len(SYMS)))
    open_g = np.zeros((n, 240, len(SYMS)))
    for j, sym in enumerate(SYMS):
        if sym == "BTCUSDT":
            files = sorted(glob.glob(str(ROOT / "data/raw/btc_intraday_20260924/klines_1m_20*.parquet")))
        else:
            files = sorted(glob.glob(str(ROOT / f"data/raw/majors_intraday_20260924/{sym}_1m_20*.parquet")))
        assert files, f"no 1m files for {sym}"
        parts = [pd.read_parquet(f, columns=["open_time", "open", "close"]) for f in files]
        d = pd.concat(parts, ignore_index=True)
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        d = d.sort_values("open_time").drop_duplicates("open_time", keep="last").set_index("open_time")
        co = d["close"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        op = d["open"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        close_g[:, :, j] = _ffill_rows(co)
        open_g[:, :, j] = _ffill_rows(op)
        print(f"{sym}: 1m rows={len(d)} files={len(files)}", flush=True)

    # ---- dip matrix per symbol: close(m)/openT - 1 for m in 16..238 ----
    MO = np.arange(16, 239)  # 223 offsets
    dip = np.zeros((n, len(MO), len(SYMS)))
    for j in range(len(SYMS)):
        with np.errstate(invalid="ignore", divide="ignore"):
            dip[:, :, j] = close_g[:, MO, j] / openT[:, j:j + 1] - 1

    # ---- per (t,sym,k) returns ----
    r_sym_k = {}  # sym -> {k: (n,) array}
    for j, sym in enumerate(SYMS):
        sig = sigma[:, j]
        oT = openT[:, j]
        eO = exitOpen[:, j]
        fu = fundT2[:, j]
        base_ok = (np.isfinite(sig) & (sig > 0) & np.isfinite(oT) & (oT > 0)
                   & np.isfinite(eO) & (eO > 0))
        d = dip[:, :, j]
        per_k = {}
        for k in KS:
            with np.errstate(invalid="ignore"):
                mask = base_ok[:, None] & np.isfinite(d) & (d <= (-k * sig)[:, None])
            has = mask.any(axis=1)
            first = mask.argmax(axis=1)  # offset index into MO
            m_abs = MO[first]
            entry = np.where(has, open_g[np.arange(n), np.clip(m_abs + 1, 0, 239), j], np.nan)
            ok = has & np.isfinite(entry) & (entry > 0)
            r = np.zeros(n)
            with np.errstate(invalid="ignore", divide="ignore"):
                r[ok] = (eO[ok] * 0.9998 / (entry[ok] * 1.0002) - 1 - 0.001 - fu[ok])
            r[~np.isfinite(r)] = 0.0
            per_k[k] = r
            print(f"{sym} k={k}: events={int(ok.sum())}", flush=True)
        r_sym_k[sym] = per_k

    sleeve_k = {}
    for k in KS:
        sleeve_k[k] = 0.25 * sum(r_sym_k[s][k] for s in SYMS)

    # ---- k selection per anchor ----
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
                           "n_bars": int(win.sum()),
                           "n_nonzero": int((s != 0).sum())}
            if score > best_score:
                best_score, best = score, k
        if best is None:
            best = KS[0]
        best_k[a] = best
        sel_detail[a] = det
        print(f"anchor {a}: best_k={best} " + " ".join(
            f"k={k}:{det[str(k)]['score']}" for k in KS), flush=True)

    # ---- final sleeve per bar (anchor window k, else 0) ----
    final_k_idx = np.full(n, np.nan)
    sleeve = np.zeros(n)
    hits = np.zeros(n, dtype=int)  # (t,sym) events per bar under applied k
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

    # ---- per-anchor sleeve report ----
    per_anchor = []
    for a, a_ts in zip(ANCHORS, anchors_ts):
        mk = (grid >= a_ts) & (grid < a_ts + pd.Timedelta(days=365))
        s = sleeve[mk]
        eq = np.cumprod(1 + s)
        net_pct = 100 * (float(eq[-1]) - 1) if len(s) else 0.0
        dd = 100 * float(np.max(1 - eq / np.maximum.accumulate(eq))) if len(s) else 0.0
        nev = 0
        for kk in KS:
            pass
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

    # ---- combined engine_real loop ----
    idx = books.index
    cols = list(books.columns)
    assert set(cols) == set(SYMS), cols
    pos = grid.get_indexer(idx)
    assert (pos >= 0).all(), "books times must exist in sleeve grid"
    sleeve_books = sleeve[pos]

    ctx = er.context(books, opens_full)
    ref = er.run(books, ctx, TARGET, True, er.FULL)
    print("engine_real baseline monthly", ref["monthly_pct"], "DD", ref["full_path_dd"], flush=True)
    assert ref["monthly_pct"] == 3.708, ref["monthly_pct"]
    assert ref["full_path_dd"] == 18.87, ref["full_path_dd"]

    o = ctx["opens"].reindex(idx)[cols]
    r_next, _, _, fund = ctx["mkt"]
    fee_b, rel_b, fee_s, rel_s = ctx["exec"]
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

    def run_loop(sleeve_arr):
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
                ni += g[i] * float(sleeve_arr[i])
            net[i] = ni
            turn[i] = float(np.abs(dw).sum())
            eq[i] = (eq[i - 1] if i else 1.0) * (1 + ni)
            prev_w, prev_c = w.copy(), c
        return net, turn, g, eq

    net0, turn0, g0, _ = run_loop(np.zeros(nB))
    s0 = v110.summarize(pd.Series(net0, index=idx), pd.Series(turn0, index=idx), pd.Series(g0, index=idx))
    assert s0["monthly_pct"] == 3.708, s0["monthly_pct"]
    assert s0["full_path_dd"] == 18.87, s0["full_path_dd"]
    print("audit loop baseline reproduces engine_real 3.708/18.87", flush=True)

    netC, turnC, gC, eqC = run_loop(sleeve_books)
    summC = v110.summarize(pd.Series(netC, index=idx), pd.Series(turnC, index=idx), pd.Series(gC, index=idx))
    print("combined monthly", summC["monthly_pct"], "DD", summC["full_path_dd"], flush=True)
    for y in summC["yearly"]:
        print(y, flush=True)

    sym_events = {s: {str(k): int((r_sym_k[s][k] != 0).sum()) for k in KS} for s in SYMS}

    replication = {
        "version": "v171_audit_replication",
        "blind": "did_not_open_research_v171_until_this_file_saved",
        "books": "cached v154 books (A+B+D)/3",
        "target": TARGET,
        "governor": "20% with 2-bar lag on combined equity",
        "realism": "all on (funding, carry_real, budget, min_notional); 15-min execution",
        "engine_real_reference": {"monthly_pct": ref["monthly_pct"], "full_path_dd": ref["full_path_dd"]},
        "spec": {
            "symbols": SYMS,
            "grid": f"{grid.min()} -> {grid.max()} ({n} 4h bars)",
            "holding_bar": "T = t + 4h",
            "sigma": "std of 4h open-to-open pct changes, 360 bars ending at t, min 120",
            "trigger": "first m in 16..238 with close1m(m)/open4h(T)-1 <= -k*sigma(t)",
            "entry": "open1m(m+1)*1.0002",
            "exit": "open4h(T+4h)*0.9998",
            "r": "exit/entry-1-0.001-funding(T+4h floored-4h sum)",
            "sleeve_per_bar": "0.25*sum_sym r (0 without event)",
            "k_candidates": list(KS),
            "selection": "[2020-02-01+30d, anchor-1d) maximising mean/std",
            "applied": "[anchor, anchor+365d)",
        },
        "assumptions": {f"A{i}": v for i, v in enumerate(
            ["grid date_range 2020-02-01 to last books bar",
             "half-open selection/applied windows; v92 anchors",
             "sigma finite and > 0 else no event",
             "missing/nonpositive opens or entry -> r=0; funding missing -> 0",
             "score mean/std, -inf on bad std; ties -> lowest k",
             "bars outside anchor windows -> sleeve 0",
             "combined loop mirrors engine_real FULL; governor on combined equity",
             "per-anchor sleeve net/DD from sleeve-only equity"], start=1)},
        "k_selection": {a: {"best_k": best_k[a], "candidates": sel_detail[a]} for a in ANCHORS},
        "per_anchor": per_anchor,
        "symbol_events_full_grid": sym_events,
        "sleeve_totals": {
            "bars_nonzero": int((sleeve != 0).sum()),
            "events": int(hits.sum()),
            "sum": float(sleeve.sum()),
        },
        "combined": {
            "monthly_pct": summC["monthly_pct"],
            "yearly": summC["yearly"],
            "full_path_dd": summC["full_path_dd"],
            "worst_year_dd": summC["worst_year_dd"],
        },
        "params": {
            "start": str(START), "end": str(END),
            "account_usdt": er.ACCOUNT_USDT, "margin": er.MARGIN, "buffer": er.BUFFER,
            "vol": "rolling std 360 min 120 *sqrt(6*365); s=min(0.25/vol,2) else 1",
            "governor": "clip((0.20-(1-eq[j]/peak540))/0.10) j=i-2 on combined eq",
        },
    }
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print("saved", OUT)


if __name__ == "__main__":
    main()
