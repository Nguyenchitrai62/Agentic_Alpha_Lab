"""v169 blind audit, Part A: independent replication (do NOT open v169/ until replication.json saved).

Base: engine_real/engine_real.py (v154_books, context, FULL realism). Books = cached
v154 books, target 0.25, governor on, all realism on.

Spec (OPENCODE_V169_AUDIT.md):
- For every bar i with weights w (after budget and min notional), holding bar T = t_i + 4h.
- 1m klines: data/raw/btc_intraday_20260924/klines_1m_20*.parquet for BTCUSDT,
  data/raw/majors_intraday_20260924/<SYM>_1m_20*.parquet otherwise.
  Minute offsets 0..239 inside T (forward-fill missing minutes inside the bar).
- Base price o_j = engine's 4h open of bar T (opens parquet shifted -1).
  R(m) = sum_j w_j (close_j(m)/o_j - 1).
- S_i = rolling covariance (360 bars, min 120) of 4h open-to-open returns of the
  5 assets, row at bar i. L = k sqrt(w' S w).
- Stop: first m in 16..238 with R(m) <= -L ->
    gross = sum_j w_j (open_j(m+1)/o_j - 1),
    extra cost sum|w| * 0.001, no funding for that bar,
    next bar starts from zero weights (re-entry pays normal execution).
  Otherwise the bar is exactly engine_real.
- 1m DD: eq_min[i] = eq[i-1] * (1 + min(0, min over used path R(0..exit m, or 0..239)) - exec);
  DD = max over live span of 1 - min(eq, eq_min)/running max(eq), both normalised
  to the first live bar.
- Rows: no stop (must equal engine_real 3.708 / 18.87), k = 3, 2, 4.

Blind assumptions (frozen before running, documented here):
1. w/c/s/g/budget/min-notional/exec/funding/carry follow engine_real.run FULL exactly;
   stop overlay only replaces gross, adds extra cost, zeroes funding on stopped bars.
2. Carry sleeve (carry/carry_cost/expo) is NOT stopped; only directional w resets.
   prev_c carries on normally; prev_w = 0 after a stop (so next-bar dw = w - 0 and the
   min-notional small-change check compares against 0).
3. S_i uses open-to-open returns ret[t] = open[t]/open[t-1] - 1 on the full opens
   history (from 2017), window = last 360 returns ending at bar i inclusive, rows with
   any NaN dropped, need >= 120 rows else L = inf (no stop). Cov = sample covariance
   (np.cov, ddof=1). w'Sw clipped at 0 before sqrt.
4. Bars with sum|w| == 0 or non-live bars never stop (guard against 0 <= -0 trigger).
5. 1m ffill is strictly inside each 240-minute bar slice; a leading NaN (first minute(s)
   missing) is filled with o_j (R = 0). Global data is complete so this never triggers.
6. exec in eq_min is the bar's total exec drag (entry exec + extra exit cost if stopped).
   Funding/carry are excluded from eq_min by spec formula.
7. 1m DD normalisation cancels (common divisor), so DD = max over live i of
   1 - min(eq[i], eq_min[i]) / max_{live j<=i} eq[j].
8. Stop counts per anchor year are counted by decision bar i in [anchor, anchor+365d).
9. Governor uses stop-adjusted equity (same j=i-2 formula); vol scale s is precomputed
   from books/carry exactly as engine_real (independent of stops).
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

BTC_1M = sorted(glob.glob(str(ROOT / "data/raw/btc_intraday_20260924/klines_1m_20*.parquet")))
TARGET = 0.25
KS = (3, 2, 4)


def _load_engine_real():
    spec = importlib.util.spec_from_file_location("v169_audit_engine_real", ROUND2 / "engine_real" / "engine_real.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ffill_1d(a: np.ndarray) -> np.ndarray:
    out = a.copy()
    last = np.nan
    for k in range(len(out)):
        if np.isnan(out[k]):
            out[k] = last
        else:
            last = out[k]
    return out


def main():
    er = _load_engine_real()
    books, opens_full = er.v154_books()
    books = books.sort_index()
    opens_full = opens_full.sort_index()
    idx = books.index
    cols = list(books.columns)
    n = len(idx)
    print(f"books {books.shape} {idx.min()} -> {idx.max()}", flush=True)
    print(f"cols {cols}", flush=True)

    ctx = er.context(books, opens_full)
    ref = er.run(books, ctx, TARGET, True, er.FULL)
    print("engine_real ref monthly", ref["monthly_pct"], "fullDD", ref["full_path_dd"], flush=True)

    # Unpack context for the stop loop (mirror engine_real.run FULL exactly).
    o = ctx["opens"].reindex(idx)[cols]
    r_next, lo_unused, hi_unused, fund = ctx["mkt"]
    fee_b, rel_b, fee_s, rel_s = ctx["exec"]
    carry, expo = ctx["carry_real"]
    B = books.to_numpy(dtype=float)
    v99 = er.v144.v99
    v110 = er.v144.v110
    PD = er.v144.PD
    START, END = v110.START, v110.END
    live = np.asarray((idx >= START) & (idx < END))
    W_BOOKS, CARRY_LEV = v99.W_BOOKS, v99.CARRY_LEV
    CAP = v99.CAP
    C_REAL = v99.W_CARRY * v99.CARRY_LEV
    mins = np.array([er.MIN_NOTIONAL.get(c, 5.0) for c in cols])

    # Vol scale s: identical to engine_real.run (books/carry based, stop-independent).
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + v99.W_CARRY * v99.CARRY_LEV * pd.Series(carry, index=idx).shift(1)
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy(dtype=float)
    s_arr = np.where(np.isnan(vol), 1.0, np.minimum(TARGET / np.where(np.isnan(vol), 1.0, vol), CAP))

    # S_i: rolling covariance of open-to-open returns on full opens history.
    xu = opens_full[cols].sort_index()
    ret_full = xu / xu.shift(1) - 1
    # Map each books bar to its position in the full opens index.
    full_idx = xu.index
    pos_of = full_idx.get_indexer(idx)  # -1 if missing (should not happen)
    assert (pos_of >= 0).all(), "books times must exist in opens history"
    ret_mat = ret_full[cols].to_numpy(dtype=float)
    S_list: list[np.ndarray | None] = []
    for t in range(n):
        p = pos_of[t]
        lo = max(0, p - 360 + 1)
        win = ret_mat[lo:p + 1]
        win = win[~np.isnan(win).any(axis=1)]
        if len(win) < 120:
            S_list.append(None)
        else:
            S_list.append(np.cov(win, rowvar=False))

    # 1m minute grids aligned to T = idx + 4h.
    T_all = idx + pd.Timedelta(hours=4)
    grid_start = T_all.min()
    n_min = n * 240
    # Verify regular 4h grid so bar i starts at i*240.
    step = (idx[1:] - idx[:-1]).total_seconds().to_numpy() / 3600.0
    regular = bool(((step == 4.0)).all())
    print(f"regular_4h={regular} grid_start={grid_start} n_min={n_min}", flush=True)
    # Per-symbol 2D arrays (n, 240); stack later per bar.
    close_by_sym = {}
    open_by_sym = {}
    base_frame = opens_full.reindex(T_all)[cols]
    # Fallback for any T missing in opens (should not happen; opens extend past books).
    base_frame = base_frame.ffill()
    base_mat = base_frame.to_numpy(dtype=float)  # (n, m)
    for j, sym in enumerate(cols):
        if sym == "BTCUSDT":
            files = BTC_1M
        else:
            files = sorted(glob.glob(str(ROOT / "data/raw/majors_intraday_20260924" / f"{sym}_1m_20*.parquet")))
        assert files, f"no 1m files for {sym}"
        parts = [pd.read_parquet(f, columns=["open_time", "open", "close"]) for f in files]
        d = pd.concat(parts, ignore_index=True)
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        d = d.sort_values("open_time").drop_duplicates("open_time", keep="last").set_index("open_time")
        co = d["close"].astype(float)
        op = d["open"].astype(float)
        if regular:
            # Positional slicing: minute grid is contiguous 1min from grid_start.
            # Build full grid series once via reindex, then reshape to (n, 240).
            grid = pd.date_range(grid_start, grid_start + pd.Timedelta(minutes=n_min - 1), freq="1min", tz="UTC")
            co_g = co.reindex(grid).to_numpy(dtype=float)
            op_g = op.reindex(grid).to_numpy(dtype=float)
            assert len(co_g) == n_min
            close_by_sym[sym] = co_g.reshape(n, 240)
            open_by_sym[sym] = op_g.reshape(n, 240)
        else:
            arr_c = np.full((n, 240), np.nan)
            arr_o = np.full((n, 240), np.nan)
            for i in range(n):
                T = T_all[i]
                want = pd.date_range(T, T + pd.Timedelta(minutes=239), freq="1min", tz="UTC")
                arr_c[i] = co.reindex(want).to_numpy(dtype=float)
                arr_o[i] = op.reindex(want).to_numpy(dtype=float)
            close_by_sym[sym] = arr_c
            open_by_sym[sym] = arr_o
        print(f"{sym}: 1m rows={len(d)} files={len(files)}", flush=True)
    closes = np.stack([close_by_sym[s] for s in cols], axis=-1)  # (n, 240, m)
    opens1m = np.stack([open_by_sym[s] for s in cols], axis=-1)

    def run_with_stop(k: float | None):
        m = len(cols)
        net = np.zeros(n)
        turn = np.zeros(n)
        g = np.ones(n)
        eq = np.ones(n)
        eq_min = np.ones(n)
        exec_c = np.zeros(n)
        stopped = np.zeros(n, dtype=bool)
        exit_m = np.full(n, -1)
        prev_w = np.zeros(m)
        prev_c = 0.0
        for i in range(n):
            if i >= 2:
                j = i - 2
                peak = eq[max(0, j - 90 * PD + 1):j + 1].max()
                g[i] = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0.0, 1.0))
            if live[i]:
                w = W_BOOKS * s_arr[i] * B[i] * g[i]
                c = C_REAL * s_arr[i] * g[i]
            else:
                w = np.zeros(m)
                c = 0.0
            # Budget (carry first, then books) — engine_real FULL.
            ex = expo[i]
            tot = c * ex + np.abs(w).sum() / er.MARGIN
            if tot > er.BUFFER:
                c_allow = (er.BUFFER - np.abs(w).sum() / er.MARGIN) / max(ex, 1e-9)
                c = min(c, max(0.0, c_allow))
            if np.abs(w).sum() / er.MARGIN > er.BUFFER:
                w = w * er.BUFFER * er.MARGIN / np.abs(w).sum()
            # Min notional (prev_w is stop-adjusted: zero after a stop).
            eq_usdt = er.ACCOUNT_USDT * (eq[i - 1] if i else 1.0)
            small = (np.abs(w - prev_w) * eq_usdt < mins) & (w != 0)
            w = np.where(small, prev_w, w)
            dw = w - prev_w
            buy = dw > 0
            entry_exec = float(np.sum(np.abs(dw) * np.where(buy, fee_b[i], fee_s[i]) + dw * np.where(buy, rel_b[i], rel_s[i])))
            gross0 = float(np.sum(w * r_next[i]))
            fund0 = float(-np.sum(w * fund[i]))
            carry_p = float(c * carry[i])
            dc = c - prev_c
            carry_c = float(abs(dc) / er.CARRY_CAPITAL * ex * (er.SPOT_FEE + er.PERP_TAKER))
            do_stop = False
            gross = gross0
            fundp = fund0
            extra = 0.0
            rmin = 0.0
            if live[i] and float(np.abs(w).sum()) > 0:
                oj = base_mat[i]
                if bool(np.isfinite(oj).all() and (oj != 0).all()):
                    cseg = closes[i].copy()  # (240, m)
                    oseg = opens1m[i].copy()
                    cseg = np.apply_along_axis(_ffill_1d, 0, cseg)
                    oseg = np.apply_along_axis(_ffill_1d, 0, oseg)
                    # Leading NaNs -> base (R = 0).
                    for jj in range(m):
                        if np.isnan(cseg[0, jj]):
                            cseg[:, jj] = np.where(np.isnan(cseg[:, jj]), oj[jj], cseg[:, jj])
                        if np.isnan(oseg[0, jj]):
                            oseg[:, jj] = np.where(np.isnan(oseg[:, jj]), oj[jj], oseg[:, jj])
                    with np.errstate(invalid="ignore", divide="ignore"):
                        R = (cseg / oj - 1) @ w
                    R = np.nan_to_num(R, nan=0.0)
                    rmin = float(min(0.0, np.min(R)))
                    if k is not None:
                        S = S_list[i]
                        if S is not None:
                            q = float(w @ S @ w)
                            q = max(q, 0.0)
                            L = float(k) * float(np.sqrt(q))
                            if np.isfinite(L):
                                trig = -1
                                for mm in range(16, 239):
                                    if R[mm] <= -L:
                                        trig = mm
                                        break
                                if trig >= 0:
                                    do_stop = True
                                    with np.errstate(invalid="ignore", divide="ignore"):
                                        gross = float(np.sum(w * (oseg[trig + 1] / oj - 1)))
                                    extra = float(np.abs(w).sum() * 0.001)
                                    fundp = 0.0
                                    exit_m[i] = trig
                                    rmin = float(min(0.0, np.min(R[:trig + 1])))
            exec_tot = entry_exec + extra if do_stop else entry_exec
            # For bars where the 1m branch did not run, rmin stays 0.0.
            net[i] = gross - exec_tot + fundp + carry_p - carry_c
            turn[i] = float(np.abs(dw).sum())
            exec_c[i] = exec_tot
            prev_eq = eq[i - 1] if i else 1.0
            eq[i] = prev_eq * (1 + net[i])
            eq_min[i] = prev_eq * (1 + rmin - exec_tot)
            stopped[i] = do_stop
            if do_stop:
                prev_w = np.zeros(m)
            else:
                prev_w = w.copy()
            prev_c = c
        return dict(net=net, turn=turn, g=g, eq=eq, eq_min=eq_min, exec_c=exec_c, stopped=stopped, exit_m=exit_m)

    def summarize_row(res):
        net_s = pd.Series(res["net"], index=idx)
        turn_s = pd.Series(res["turn"], index=idx)
        g_s = pd.Series(res["g"], index=idx)
        summ = v110.summarize(net_s, turn_s, g_s)
        # 1m DD over live span.
        eq = res["eq"]
        eqm = res["eq_min"]
        run = -np.inf
        worst = 0.0
        for i in range(n):
            if not live[i]:
                continue
            run = max(run, float(eq[i]))
            lo = min(float(eq[i]), float(eqm[i]))
            if run > 0:
                worst = max(worst, 1 - lo / run)
        dd_1m = round(100 * float(worst), 2)
        # Stop counts per anchor year (decision bar i).
        counts = {}
        for a in v110.v92.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            mk = (idx >= a0) & (idx < a0 + pd.Timedelta(days=365))
            counts[a] = int(res["stopped"][mk].sum())
        return dict(summ, dd_1m=dd_1m, stop_counts=counts, n_stops=int(res["stopped"].sum()))

    rows = {}
    no_stop_loop = run_with_stop(None)
    # Verify loop reproduces engine_real on the no-stop path.
    assert abs(v110.summarize(pd.Series(no_stop_loop["net"], index=idx), pd.Series(no_stop_loop["turn"], index=idx), pd.Series(no_stop_loop["g"], index=idx))["monthly_pct"] - ref["monthly_pct"]) < 1e-9
    rows["no_stop"] = summarize_row(no_stop_loop)
    for k in KS:
        rows[f"k_{k}"] = summarize_row(run_with_stop(k))
        print(f"k={k} monthly", rows[f"k_{k}"]["monthly_pct"], "fullDD", rows[f"k_{k}"]["full_path_dd"],
              "1mDD", rows[f"k_{k}"]["dd_1m"], "stops", rows[f"k_{k}"]["n_stops"], flush=True)

    # Assignment gate: no-stop must equal engine_real 3.708 / 18.87.
    assert rows["no_stop"]["monthly_pct"] == 3.708, rows["no_stop"]["monthly_pct"]
    assert rows["no_stop"]["full_path_dd"] == 18.87, rows["no_stop"]["full_path_dd"]
    assert ref["monthly_pct"] == 3.708 and ref["full_path_dd"] == 18.87

    replication = {
        "blind": "did_not_open_research_v169_until_this_file_saved",
        "books": "cached v154 books (A+B+D)/3",
        "target": TARGET,
        "governor": True,
        "realism": "all on (funding, carry, budget, min_notional)",
        "engine_real_reference": {"monthly_pct": ref["monthly_pct"], "full_path_dd": ref["full_path_dd"]},
        "spec": {
            "holding_bar": "T = t_i + 4h",
            "minutes": "offsets 0..239 inside T, ffill inside bar",
            "base": "engine 4h open of bar T (opens shifted -1)",
            "R": "sum_j w_j (close_j(m)/o_j - 1)",
            "S": "rolling cov 360 min 120 of 4h open-to-open returns, row at bar i",
            "L": "k sqrt(w'Sw)",
            "trigger": "first m in 16..238 with R(m) <= -L",
            "exit_gross": "sum_j w_j (open_j(m+1)/o_j - 1)",
            "extra_cost": "sum|w| * 0.001",
            "funding_on_stop": 0.0,
            "next_bar": "prev_w = 0 (re-entry pays normal execution); carry continues",
            "eq_min": "eq[i-1]*(1 + min(0, min R over used path) - exec_total)",
            "dd_1m": "max over live of 1 - min(eq, eq_min)/running max(eq)",
        },
        "rows": rows,
        "params": {
            "account_usdt": er.ACCOUNT_USDT,
            "min_notional": {"BTCUSDT": 100.0, "ETHUSDT": 20.0, "others": 5.0},
            "margin": er.MARGIN,
            "buffer": er.BUFFER,
            "extra_exit_cost": 0.001,
            "trigger_range": [16, 238],
        },
    }
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print("saved", OUT)


if __name__ == "__main__":
    main()
