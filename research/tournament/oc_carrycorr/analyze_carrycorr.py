"""oc_carrycorr: correlation of the frozen cash-carry sleeve with G2 (diagnostic).

Questions:
 (1) correlation of the carry sleeve's daily mark-to-market with G2's daily
     returns, overall and during G2's 10 worst weeks and DD episodes;
 (2) entry basis level vs the BOT's return in the same quarter window;
 (3) the carry pair's MtM during the 5 worst crash days (widening vs collapse).

Method (frozen inputs, nothing refit, LIGHT diagnostic, 1h+4h only, no 1m,
no engine reruns, one process):
- Carry rule reused VERBATIM from research/tournament/oc_cashcarry
  (PLAN pre-registered: roll next-quarter at <=7d, enter iff annualised basis
  ln(F/S)*365/DTE >= 4%, equal-notional spot long + quarterly short, hold to
  delivery, fees spot 0.001/side + fut 0.00055 entry / 0.0002 delivery).
  The 33 entered trades are read from oc_cashcarry/results.json (asserted).
- Carry marked HOURLY exactly as in research/tournament/oc_carryd13
  (combine_carryd13.py): mtm_alloc(t) = (S(t)/S_entry-1)
  + ((F_entry-F(t))/F_entry) - 0.00155 (entry fees only; full 0.00275 drag in
  the frozen ret_alloc), S(t)/F(t) = last CLOSED hourly bar strictly before t
  (causal), 0 before the entry-bar close, locked to frozen ret_alloc from the
  settlement-bar close, hourly ffill inside the holding window.
  Spot marks from research/tournament/ext/hourly_ext.parquet (t < 2026-09-24
  asserted); futures marks from data/raw/qbasis_20261003 um_*_1h.parquet;
  entry/settlement timestamps from the spot-4h grid (entry_close =
  entry_open + 4h; settlement = first spot-4h close_time > delivery 08:00).
- G2 = R2B1D17BFG2 continuous hourly mix from
  research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl via
  v388.hourly + mean of the 4 phases (v388.mix convention), grid
  G0 = 2021-09-24 04:00 .. g1 = Y1 + 12h (2026-09-23 12:00 UTC).
- Daily series sampled at 00:00 UTC: G2 logret = ln(E_d/E_{d-1});
  carry daily P&L quoted at f = 0.25 of unit capital
  (0.25 * delta(raw)); correlations are scale-free so f is labelling only.
- 10 worst weeks = 10 worst non-overlapping rolling 7-day G2 log returns
  (greedy, >= 7d apart). DD episodes = 3 deepest peak-to-trough episodes on
  the daily G2 path. Crash days = 5 worst G2 daily logret days, plus the 5
  worst BTC spot daily logret days as a market-crash cross-check.
- Basis vs BOT: per-trade ann_basis (frozen) vs G2 holding-window return
  (E_settle/E_entry - 1 on the continuous mix); Pearson + Spearman over all
  33 trades and over the 25 in-window trades (entry >= 2021-09-24).

Usage: .venv/Scripts/python.exe research/tournament/oc_carrycorr/analyze_carrycorr.py
Reads: oc_cashcarry/results.json, v421_runs.pkl, v388_bot_stop_distance.py,
  hourly_ext.parquet, qbasis um_*_1h.parquet, spot BTC 4h (delivery grid).
Writes: research/tournament/oc_carrycorr/results.json
"""

from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
CC = ROOT / "research/tournament/oc_cashcarry"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"

STRAT = "R2B1D17BFG2"
F_Q = 0.25  # labelling scale for carry magnitudes (correlations scale-free)
FEE_ENTRY_PAID = 0.001 + 0.00055
FEE_PAIR = 2 * 0.001 + 0.00055 + 0.0002
G0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def last_close_before(times_ns: np.ndarray, closes: np.ndarray,
                      ts_ns: np.ndarray) -> np.ndarray:
    """Close of the last bar with bar_time strictly before each query time."""
    idx = np.searchsorted(times_ns, ts_ns, side="left") - 1
    out = np.full(len(ts_ns), np.nan)
    ok = idx >= 0
    out[ok] = closes[idx[ok]]
    return out


def pearson(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 3 or x.std(ddof=1) == 0 or y.std(ddof=1) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 3:
        return float("nan")
    rx = pd.Series(x).rank().to_numpy(float)
    ry = pd.Series(y).rank().to_numpy(float)
    if rx.std(ddof=1) == 0 or ry.std(ddof=1) == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def worst_weeks(dates: pd.DatetimeIndex, g7: np.ndarray, c7: np.ndarray,
                k: int = 10):
    """Greedy non-overlapping worst-k 7-day windows (>= 7d apart)."""
    order = np.argsort(g7)
    picked: list[int] = []
    for i in order:
        if len(picked) >= k:
            break
        if all(abs(int(i) - int(j)) >= 7 for j in picked):
            picked.append(int(i))
    picked.sort(key=lambda i: g7[i])
    return [{"end": str(dates[i].date()), "g2_7d_logret": round(float(g7[i]), 6),
             "carry_7d_pnl_f025": round(float(c7[i]), 6)}
            for i in picked]


def dd_episodes(dates: pd.DatetimeIndex, eq: np.ndarray, raw: np.ndarray,
                k: int = 3):
    """k deepest peak-to-trough episodes on the daily path (non-overlapping)."""
    eq = np.asarray(eq, dtype=float)
    n = len(eq)
    peak = eq[0]
    peak_i = 0
    eps: list[tuple[int, int, float]] = []
    for i in range(1, n):
        if eq[i] > peak:
            if peak_i < i - 1:
                dd = float(1 - np.min(eq[peak_i:i + 1]) / peak)
                if dd > 0:
                    trough = int(peak_i + np.argmin(eq[peak_i:i + 1]))
                    eps.append((peak_i, trough, dd))
            peak = eq[i]
            peak_i = i
    if peak_i < n - 1:  # trailing episode
        dd = float(1 - np.min(eq[peak_i:]) / peak)
        if dd > 0:
            trough = int(peak_i + np.argmin(eq[peak_i:]))
            eps.append((peak_i, trough, dd))
    eps.sort(key=lambda e: -e[2])
    out = []
    used: list[tuple[int, int]] = []
    for pi, ti, dd in eps:
        if len(out) >= k:
            break
        if all(ti < u0 or pi > u1 for u0, u1 in used):
            used.append((pi, ti))
            carry_pnl = float(F_Q * (raw[ti] - raw[pi]))
            carry_min = float(F_Q * np.min(raw[pi:ti + 1] - raw[pi]))
            out.append({"peak": str(dates[pi].date()),
                        "trough": str(dates[ti].date()),
                        "g2_dd": round(dd, 6),
                        "carry_pnl_f025": round(carry_pnl, 6),
                        "carry_min_f025": round(carry_min, 6)})
    return out


def main() -> None:
    v388 = _load("v388_for_carrycorr", RD / "v388" / "v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid = pd.date_range(G0, g1, freq="1h")
    grid_ns = grid.values.astype("datetime64[ns]").astype(np.int64)

    # ---- frozen carry trades ----
    cc = json.loads((CC / "results.json").read_text())
    assert cc["meta"]["threshold_ann_basis"] == 0.04
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13
    assert cc["n_incomplete"] == 2
    for t in cc["trades"]:
        gross = ((t["S_del"] - t["S_entry"]) / t["S_entry"]
                 + (t["F_entry"] - t["S_del"]) / t["F_entry"])
        assert abs(t["ret_alloc"] - round(gross - FEE_PAIR, 6)) < 1e-9

    # ---- hourly spot (causal marks) ----
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert bool((h["t"] < CAP).all()), "hourly data reaches beyond the cap"
    spot: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for coin in ("BTC", "ETH"):
        d = h[h["sym"] == f"{coin}USDT"].sort_values("t")
        spot[coin] = (d["t"].values.astype("datetime64[ns]").astype(np.int64),
                      d["close"].to_numpy(dtype=float))

    # ---- quarterly hourly per traded contract ----
    qmap: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
    for t in cc["trades"]:
        key = (t["coin"], t["delivery"])
        if key in qmap:
            continue
        y, m, dd = t["delivery"].split("-")
        code = f"{y[2:]}{m}{dd}"
        (f,) = sorted(QDIR.glob(f"um_{t['coin']}USDT_{code}_1h.parquet"))
        q = pd.read_parquet(f, columns=["open_time", "close"])
        qo = pd.to_datetime(q["open_time"], utc=True).values.astype(
            "datetime64[ns]").astype(np.int64)
        o = np.argsort(qo)
        qmap[key] = (qo[o], q["close"].to_numpy(dtype=float)[o])

    # ---- entry/settlement timestamps on the spot-4h grid ----
    s4 = pd.read_parquet(SDIR / "BTCUSDT_spot_4h.parquet",
                         columns=["open_time", "close_time"])
    s4o = pd.to_datetime(s4["open_time"], utc=True)
    s4c = pd.to_datetime(s4["close_time"], utc=True)
    trades = []
    for t in cc["trades"]:
        te = pd.Timestamp(t["entry_open"], tz="UTC")
        tc = te + pd.Timedelta(hours=4)
        assert (s4o == te).any(), t
        D = pd.Timestamp(t["delivery"] + " 08:00", tz="UTC")
        si = int(np.searchsorted(s4c.values.astype("datetime64[ns]").astype(np.int64),
                                 D.value, side="right"))
        assert si < len(s4), t
        ts = s4c.iloc[si]
        assert ts > tc, t
        trades.append({"coin": t["coin"], "delivery": t["delivery"],
                       "ann_basis": float(t["ann_basis"]),
                       "F_entry": float(t["F_entry"]),
                       "S_entry": float(t["S_entry"]),
                       "ret_alloc": float(t["ret_alloc"]),
                       "entry_open": t["entry_open"],
                       "tc_ns": tc.value, "ts_ns": ts.value,
                       "tc": tc, "ts": ts})

    # ---- G2 continuous hourly mix ----
    runs = pickle.loads((RD / "v421" / "v421_runs.pkl").read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    E, _MN = v388.mix({s: runs[s] for s in range(4)}, STRAT, g1)
    assert (E.index == grid).all()
    g2_hourly = E.to_numpy(dtype=float)

    # ---- carry raw hourly curve (f=1 indexed units; sized later) ----
    G_ns = grid_ns
    raw = np.zeros(len(grid))
    for tr in trades:
        st, sc = spot[tr["coin"]]
        ft, fc = qmap[(tr["coin"], tr["delivery"])]
        S = last_close_before(st, sc, G_ns)
        F = last_close_before(ft, fc, G_ns)
        with np.errstate(divide="ignore", invalid="ignore"):
            mtm = ((S / tr["S_entry"] - 1.0)
                   + ((tr["F_entry"] - F) / tr["F_entry"]) - FEE_ENTRY_PAID)
        mtm[~np.isfinite(mtm)] = np.nan
        s = pd.Series(mtm, index=grid).ffill()
        mtm = s.to_numpy()
        v = np.zeros(len(grid))
        open_m = G_ns > tr["tc_ns"]
        settled_m = G_ns >= tr["ts_ns"]
        hold_m = open_m & ~settled_m
        v[hold_m] = mtm[hold_m]
        v[hold_m & ~np.isfinite(mtm)] = 0.0
        v[settled_m] = tr["ret_alloc"]
        raw += v

    # ---- daily sampling at 00:00 UTC ----
    days = pd.date_range("2021-09-25", "2026-09-23", freq="D", tz="UTC")
    e_d = pd.Series(g2_hourly, index=grid).reindex(days, method="ffill").to_numpy(float)
    r_d = pd.Series(raw, index=grid).reindex(days, method="ffill").to_numpy(float)
    g_log = np.log(e_d[1:] / e_d[:-1])
    g_smp = e_d[1:] / e_d[:-1] - 1.0
    c_pnl = F_Q * np.diff(r_d)  # carry daily P&L at f=0.25 of unit capital
    dts = days[1:]
    n_days = len(dts)
    assert n_days == len(g_log) == len(c_pnl)

    # BTC spot daily logret (market context, same sampling)
    bt, bc = spot["BTC"]
    b_d = last_close_before(bt, bc, days.values.astype("datetime64[ns]").astype(np.int64))
    b_d = pd.Series(b_d, index=days).ffill().to_numpy(float)
    b_log = np.log(b_d[1:] / b_d[:-1])

    corr_all = {"pearson_log_vs_pnl": round(float(pearson(g_log, c_pnl)), 4),
                "spearman_log_vs_pnl": round(float(spearman(g_log, c_pnl)), 4),
                "pearson_simple_vs_pnl": round(float(pearson(g_smp, c_pnl)), 4),
                "n_days": int(n_days),
                "mean_g2_logret": round(float(np.mean(g_log)), 6),
                "mean_carry_pnl_f025": round(float(np.mean(c_pnl)), 6),
                "std_g2_logret": round(float(np.std(g_log, ddof=1)), 6),
                "std_carry_pnl_f025": round(float(np.std(c_pnl, ddof=1)), 6)}

    # ---- 10 worst weeks (rolling 7d, non-overlapping) ----
    g7 = np.array([np.sum(g_log[i - 6:i + 1]) for i in range(6, len(g_log))])
    c7 = np.array([np.sum(c_pnl[i - 6:i + 1]) for i in range(6, len(c_pnl))])
    wdates = dts[6:]
    weeks = worst_weeks(wdates, g7, c7, 10)
    in_w = np.zeros(len(dts), dtype=bool)
    for w in weeks:
        j = int(np.where(dts == pd.Timestamp(w["end"], tz="UTC"))[0][0])
        in_w[max(0, j - 6):j + 1] = True
    corr_worst_weeks = {
        "pearson": round(float(pearson(g_log[in_w], c_pnl[in_w])), 4),
        "spearman": round(float(spearman(g_log[in_w], c_pnl[in_w])), 4),
        "n_days": int(in_w.sum()),
        "mean_g2_logret": round(float(np.mean(g_log[in_w])), 6),
        "mean_carry_pnl_f025": round(float(np.mean(c_pnl[in_w])), 6)}
    corr_rest = {
        "pearson": round(float(pearson(g_log[~in_w], c_pnl[~in_w])), 4),
        "spearman": round(float(spearman(g_log[~in_w], c_pnl[~in_w])), 4),
        "n_days": int((~in_w).sum()),
        "mean_g2_logret": round(float(np.mean(g_log[~in_w])), 6),
        "mean_carry_pnl_f025": round(float(np.mean(c_pnl[~in_w])), 6)}
    worst_week_carry_sum = round(float(sum(w["carry_7d_pnl_f025"] for w in weeks)), 6)
    worst_week_g2_sum = round(float(sum(w["g2_7d_logret"] for w in weeks)), 6)

    # ---- DD episodes (daily path) ----
    episodes = dd_episodes(dts, e_d[1:], r_d[1:], 3)
    in_dd = np.zeros(len(dts), dtype=bool)
    for ep in episodes:
        i0 = int(np.where(dts == pd.Timestamp(ep["peak"], tz="UTC"))[0][0])
        i1 = int(np.where(dts == pd.Timestamp(ep["trough"], tz="UTC"))[0][0])
        in_dd[min(i0, i1):max(i0, i1) + 1] = True
    corr_dd = {"pearson": round(float(pearson(g_log[in_dd], c_pnl[in_dd])), 4),
               "spearman": round(float(spearman(g_log[in_dd], c_pnl[in_dd])), 4),
               "n_days": int(in_dd.sum())}

    # ---- (2) entry basis vs BOT holding-window return ----
    e_ser = pd.Series(g2_hourly, index=grid)
    e_vals = e_ser.to_numpy(dtype=float)
    hold_rows = []
    n_pre_g0_excluded = 0
    for tr in trades:
        if tr["tc"] < G0:
            n_pre_g0_excluded += 1  # no G2 mix before G0; excluded (labelled)
            continue
        p0 = int(np.searchsorted(grid_ns, tr["tc"].value, side="right")) - 1
        p1 = int(np.searchsorted(grid_ns, tr["ts"].value, side="right")) - 1
        assert 0 <= p0 < len(e_vals) and 0 <= p1 < len(e_vals), tr
        e0 = float(e_vals[p0])
        e1 = float(e_vals[p1])
        hold_rows.append({"coin": tr["coin"], "delivery": tr["delivery"],
                          "entry_open": tr["entry_open"],
                          "ann_basis": round(tr["ann_basis"], 6),
                          "g2_hold_ret": round(float(e1 / e0 - 1), 6),
                          "carry_ret_alloc": round(tr["ret_alloc"], 6)})
    basis = np.array([r["ann_basis"] for r in hold_rows])
    ghold = np.array([r["g2_hold_ret"] for r in hold_rows])
    basis_corr_all = {"pearson": round(float(pearson(basis, ghold)), 4),
                      "spearman": round(float(spearman(basis, ghold)), 4),
                      "n": len(hold_rows),
                      "note": (f"{n_pre_g0_excluded} pre-G0 trades excluded "
                               "(no G2 mix before 2021-09-24 04:00)")}
    inwin = [r for r in hold_rows
             if pd.Timestamp(r["entry_open"], tz="UTC")
             >= pd.Timestamp("2021-09-24", tz="UTC")]
    bw = np.array([r["ann_basis"] for r in inwin])
    gw = np.array([r["g2_hold_ret"] for r in inwin])
    basis_corr_inwindow = {"pearson": round(float(pearson(bw, gw)), 4),
                           "spearman": round(float(spearman(bw, gw)), 4),
                           "n": len(inwin)}
    med = float(np.median(basis))
    hi = [r["g2_hold_ret"] for r in hold_rows if r["ann_basis"] >= med]
    lo = [r["g2_hold_ret"] for r in hold_rows if r["ann_basis"] < med]
    basis_split = {"median_basis": round(med, 6),
                   "mean_g2_hold_high_basis": round(float(np.mean(hi)), 6),
                   "mean_g2_hold_low_basis": round(float(np.mean(lo)), 6),
                   "n_high": len(hi), "n_low": len(lo)}

    # ---- (3) crash days ----
    order_g = np.argsort(g_log)[:5]
    crash_g2 = []
    for i in order_g:
        crash_g2.append({"date": str(dts[i].date()),
                         "g2_logret": round(float(g_log[i]), 6),
                         "g2_simple": round(float(g_smp[i]), 6),
                         "carry_pnl_f025": round(float(c_pnl[i]), 6),
                         "btc_logret": round(float(b_log[i]), 6),
                         "carry_sign": ("widening_or_flat"
                                        if c_pnl[i] >= 0 else "collapse")})
    crash_g2.sort(key=lambda r: r["g2_logret"])
    order_b = np.argsort(b_log)[:5]
    crash_btc = []
    for i in order_b:
        crash_btc.append({"date": str(dts[i].date()),
                          "btc_logret": round(float(b_log[i]), 6),
                          "g2_logret": round(float(g_log[i]), 6),
                          "carry_pnl_f025": round(float(c_pnl[i]), 6),
                          "carry_sign": ("widening_or_flat"
                                         if c_pnl[i] >= 0 else "collapse")})
    crash_btc.sort(key=lambda r: r["btc_logret"])

    out = {
        "meta": {
            "g2": "R2B1D17BFG2 continuous hourly mix (mean of 4 phases, "
                  "v388.hourly ffill, grid 2021-09-24 04:00 .. 2026-09-23 12:00 UTC)",
            "carry_rule": "frozen oc_cashcarry (33 entered / 13 skipped / "
                          "2 incomplete reused verbatim); hourly mark exactly as "
                          "oc_carryd13 (last closed hourly bar strictly before t, "
                          "entry fee 0.00155 in MtM, full 0.00275 in ret_alloc)",
            "carry_sizing_note": "carry magnitudes quoted at f=0.25 of unit "
                                 "capital (0.25 * delta(raw)); correlations are "
                                 "scale-free; no yearly rebalance on this "
                                 "diagnostic path (labelled)",
            "daily": "sampled at 00:00 UTC; G2 logret = ln(E_d/E_{d-1}); "
                     "carry = daily P&L in account units at f=0.25",
            "weeks": "10 worst non-overlapping rolling 7-day G2 log returns "
                     "(greedy, >= 7d apart)",
            "dd": "3 deepest peak-to-trough episodes on the daily G2 path",
            "crash_days": "5 worst G2 daily logret days + 5 worst BTC spot "
                          "daily logret days (market cross-check)",
            "basis_vs_bot": "per-trade frozen ann_basis vs G2 holding-window "
                            "return (mix at settlement / mix at entry - 1)",
            "data_cap": "2026-09-24T00:00:00Z",
            "no_1m": True,
            "diagnostic_only": True,
            "inputs": {"n_carry_trades": 33, "n_days": int(n_days),
                       "grid": [str(G0), str(g1)]},
        },
        "corr_daily_overall": corr_all,
        "worst_10_weeks": weeks,
        "worst_10_weeks_sums": {"g2_7d_logret_sum": worst_week_g2_sum,
                                "carry_7d_pnl_f025_sum": worst_week_carry_sum},
        "corr_in_worst_weeks": corr_worst_weeks,
        "corr_outside_worst_weeks": corr_rest,
        "dd_episodes": episodes,
        "corr_in_dd_episodes": corr_dd,
        "basis_vs_bot_holds": hold_rows,
        "basis_corr_all33": basis_corr_all,
        "basis_corr_inwindow25": basis_corr_inwindow,
        "basis_split": basis_split,
        "crash_5_worst_g2_days": crash_g2,
        "crash_5_worst_btc_days": crash_btc,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"days={n_days} corr_all={corr_all}")
    print(f"worst_weeks_sums g2={worst_week_g2_sum} carry_f025={worst_week_carry_sum}")
    print(f"corr_worst={corr_worst_weeks} corr_rest={corr_rest} corr_dd={corr_dd}")
    print(f"basis_all={basis_corr_all} basis_inwin={basis_corr_inwindow} split={basis_split}")
    for r in crash_g2:
        print("crash_g2", r)
    for r in crash_btc:
        print("crash_btc", r)


if __name__ == "__main__":
    main()
