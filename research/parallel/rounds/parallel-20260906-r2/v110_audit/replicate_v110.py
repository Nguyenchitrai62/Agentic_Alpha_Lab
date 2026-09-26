"""Blind v110 audit replication (Part A). Does NOT read research/.../v110/*.

Base: audited v104 replication (books = 0.25 b_lo + 0.25 b94 + 0.5 b103,
carry, v104 portfolio vol estimate).

  b_lo  = v92 LO weights  * v92 vol scale   (20% cap 2, daily rebalance)
  b94   = v94 LS weights  * v94 scale       (20% cap 2, daily rebalance)
  b103  = v103 LS weights * own scale       (20% cap 2, daily rebalance)
  books = 0.25 b_lo + 0.25 b94 + 0.5 b103
  carry from artifacts/research/carry/carry_oos_fee0.0004.parquet

Spec (OPENCODE_V110_AUDIT.md):
  realized_t = 0.8*sum(books_{t-2}*(open_t/open_{t-1}-1)) + 0.6*carry_{t-1}
  vol = rolling-360 (min 120) std * sqrt(2190)
  s = min(target/vol, 2), NaN->1
    target 0.25 (primary gated), 0.30 (secondary gated),
    0.25 and 0.15 ungoverned references.
  Sequential loop over the 4h index; live bars [2021-09-24, 2026-09-23)
    (= start + 1825 days); outside, weights and carry exposure are 0.
  Governor at bar i >= 2: j = i-2, peak = max(E over bars j-539..j),
    DD = 1 - E_j/peak, g_i = clip((0.20-DD)/0.10, 0, 1)
    (g = 1 when ungoverned or i < 2).
  w_i = 0.8*s_i*books_i*g_i, c_i = 0.6*s_i*g_i
  net_i = sum(w_i*(open_{i+2}/open_{i+1}-1)) - sum|w_i-w_{i-1}|*(fee+slip)
    - 0.00005*sum(max(w_i,0)) + c_i*carry_i
    - |c_i-c_{i-1}|*2*0.0004/1.2
  E_i = E_{i-1}*(1+net_i), E before start = 1. Scenarios as v92.
  Report yearly net/DD, mean g per anchor year, full-path max DD over the
  live span for all four rows and scenarios.

Blind choices (documented):
  - 4h index = union of the three book weight frames (10950 bars,
    2021-09-24 00:00 .. 2026-09-23 20:00 UTC).
  - live mask = (idx >= 2021-09-24) & (idx < 2026-09-23 00:00 UTC), literal
    spec dates; bars on 2026-09-23 00:00+ have w=c=0.
  - s computed on the full union index with pandas rolling(360, min 120,
    ddof=1); NaN->1; inf->2 (cap); clip upper 2.
  - Forward return uses union opens: r_fwd_i = open_{i+2}/open_{i+1}-1;
    last two bars have no forward open -> 0.
  - Sequential loop per (row, scenario) since g depends on scenario E path.
    w_prev/c_prev for i=0 are 0; for the first live bar after a gap they are
    the actual previous bar values (0 when previous bar is outside live).
    Carry first-bar cost is |c_i - c_{i-1}| (NOT forced 0), unlike the v109
    wrapper which used fillna(0) for carry turnover.
  - peak_j = max(1.0, max(E over max(0,j-539)..j)); i.e. pre-start E=1 is
    included so early DD is measured against 1. DD uses E_j (equity after
    bar j). g is scenario/row specific.
  - Yearly slices [anchor, anchor+365d) on idx; slice net/DD recomputed from
    slice net series (slice-local DD); full-path max DD from live-span E.
  - Scenarios as v92: normal (0.0002, 0.0), fee_stress (0.0006, 0.0),
    execution_stress (0.0006, 0.0005).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
OUT_DIR = Path(__file__).resolve().parent
V92_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v92_audit/predictions_5asset.csv"
V94_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v93_v94_audit/predictions_v94.csv"
V103_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v103_v105_audit/predictions_v103.csv"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
LIVE_START = pd.Timestamp("2021-09-24", tz="UTC")
LIVE_END = pd.Timestamp("2026-09-23", tz="UTC")  # exclusive
PD = 6
BARS_PER_YEAR = 2190
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0), "execution_stress": (0.0006, 0.0005)}
W_BOOKS, W_CARRY = 0.8, 0.6  # 0.2*3.0
ROLL, ROLL_MIN = 360, 120
ANN = np.sqrt(2190)
CAP = 2.0
GOV_WIN = 540  # bars j-539..j inclusive
ROWS = {
    "primary_gated_0.25": {"target": 0.25, "governed": True},
    "secondary_gated_0.30": {"target": 0.30, "governed": True},
    "ref_ungov_0.25": {"target": 0.25, "governed": False},
    "ref_ungov_0.15": {"target": 0.15, "governed": False},
}


def weights_ls(oos, shorts):
    Wdict = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        p = g["pred"].astype(float)
        rib = g["rib"].astype(float)
        long_ = (p.clip(lower=0) / 0.5).clip(upper=1.0).where(rib != -1, 0.0)
        if shorts:
            short = ((-p).clip(lower=0) / 0.5).clip(upper=1.0).where(rib != 1, 0.0)
        else:
            short = 0.0 * long_
        raw = (long_ - short) / (g["vol42"].astype(float) * np.sqrt(PD * 365))
        raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        Wdict[s] = raw
    rawW = pd.DataFrame(Wdict).sort_index()
    row_sum = rawW.abs().sum(axis=1)
    n_nz = (rawW != 0).sum(axis=1).clip(lower=1)
    W = rawW.div(row_sum.clip(lower=1e-9), axis=0).mul(row_sum.gt(0), axis=0)
    W = W.mul((n_nz / 5).clip(upper=1.0), axis=0).fillna(0.0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    W = W.where(keep, np.nan).ffill().fillna(0.0)
    return W


def vol_target_scale(o, W, target=0.20, cap=2.0):
    ret1 = o / o.shift(1) - 1
    realized = (W.shift(2) * ret1).sum(axis=1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std(ddof=1) * np.sqrt(PD * 365)
    sc = (target / vol).clip(upper=cap).fillna(1.0)
    sc = sc.replace([np.inf, -np.inf], 2.0).fillna(1.0)
    return sc


def slice_stats(net, turn):
    eq = (1 + net).cumprod()
    days = len(net) / PD
    g = float(eq.iloc[-1]) if len(eq) else float("nan")
    dd = float(np.max(1 - eq / eq.cummax())) if len(eq) else float("nan")
    return dict(net_pct=round(100 * (g - 1), 2),
                monthly_geometric_net_percent=round(100 * (g ** (30.4375 / days) - 1), 3) if days > 0 else float("nan"),
                max_drawdown_percent=round(100 * dd, 2),
                fills=int((turn > 1e-6).sum()),
                months=round(days / 30.4375, 1),
                bars=int(len(net)))


def run_row(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip, governed):
    n = len(o_vals)
    # per-asset forward matrix for gross: fwd_mat[i] = o[i+2]/o[i+1]-1
    fwd_mat = np.full_like(o_vals, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        fm = o_vals[2:] / o_vals[1:-1] - 1.0
    fm = np.where(np.isfinite(fm), fm, 0.0)
    fwd_mat[: n - 2] = fm
    w = np.zeros_like(o_vals)
    c = np.zeros(n)
    g = np.ones(n)
    net = np.zeros(n)
    turn = np.zeros(n)
    E = np.ones(n)
    w_prev = np.zeros(o_vals.shape[1])
    c_prev = 0.0
    e_prev = 1.0
    # store E history for governor (equity after each bar)
    e_hist = np.ones(n)
    carry_cost_rate = 2 * 0.0004 / 1.2
    for i in range(n):
        if live_mask[i]:  # outside live: w=c=0; inside: trade from bar 0 (g=1 for i<2/ungoverned)
            if governed and i >= 2:
                j = i - 2
                lo = max(0, j - (GOV_WIN - 1))
                peak = float(np.max(e_hist[lo: j + 1][: j + 1 - lo])) if j >= 0 else 1.0
                # e_hist entries beyond current j not yet computed for j==i-1? j<i so done.
                # For j where some entries are still 1.0-init (future), restrict to <=j.
                peak = max(1.0, peak)
                ej = float(e_hist[j]) if j >= 0 else 1.0
                dd = 1.0 - ej / peak if peak > 0 else 0.0
                gi = (0.20 - dd) / 0.10
                gi = 1.0 if gi > 1.0 else (0.0 if gi < 0.0 else gi)
            else:
                gi = 1.0
            si = s_vals[i]
            wi = W_BOOKS * si * books_vals[i] * gi
            ci = W_CARRY * si * gi
        else:
            gi = 1.0
            wi = np.zeros(o_vals.shape[1])
            ci = 0.0
        gross = float(np.sum(wi * fwd_mat[i]))
        tcost = float(np.sum(np.abs(wi - w_prev)) * (fee + slip))
        fund = float(np.sum(np.maximum(wi, 0.0)) * 0.00005)
        cgross = float(ci * carry_vals[i])
        ccost = float(abs(ci - c_prev) * carry_cost_rate)
        ni = gross - tcost - fund + cgross - ccost
        ei = e_prev * (1.0 + ni)
        w[i] = wi
        c[i] = ci
        g[i] = gi
        net[i] = ni
        turn[i] = float(np.sum(np.abs(wi - w_prev)))
        E[i] = ei
        e_hist[i] = ei
        w_prev = wi
        c_prev = ci
        e_prev = ei
    return dict(net=net, turn=turn, E=E, g=g, w=w, c=c)


def main():
    o92 = pd.read_csv(V92_CSV, parse_dates=["t"])
    o94 = pd.read_csv(V94_CSV, parse_dates=["t"])
    o103 = pd.read_csv(V103_CSV, parse_dates=["t"])
    for df in (o92, o94, o103):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    o92 = o92.sort_values(["t", "sym"]).reset_index(drop=True)
    o94 = o94.sort_values(["t", "sym"]).reset_index(drop=True)
    o103 = o103.sort_values(["t", "sym"]).reset_index(drop=True)

    W_lo = weights_ls(o92, False)
    W94 = weights_ls(o94, True)
    W103 = weights_ls(o103, True)

    o = o92.pivot_table(index="t", columns="sym", values="open")
    o = o[list(SYMS)].sort_index()

    s_lo = vol_target_scale(o, W_lo.reindex(o.index).fillna(0.0), 0.20, 2.0)
    s94 = vol_target_scale(o, W94.reindex(o.index).fillna(0.0), 0.20, 2.0)
    s103 = vol_target_scale(o, W103.reindex(o.index).fillna(0.0), 0.20, 2.0)

    idx = pd.DatetimeIndex(sorted(set(W_lo.index) | set(W94.index) | set(W103.index)))
    W_lo_a = W_lo.reindex(idx).fillna(0.0)
    W94_a = W94.reindex(idx).fillna(0.0)
    W103_a = W103.reindex(idx).fillna(0.0)
    s_lo_a = s_lo.reindex(idx).fillna(1.0)
    s94_a = s94.reindex(idx).fillna(1.0)
    s103_a = s103.reindex(idx).fillna(1.0)
    o = o.reindex(idx).sort_index()

    b_lo = W_lo_a.mul(s_lo_a, axis=0)
    b94 = W94_a.mul(s94_a, axis=0)
    b103 = W103_a.mul(s103_a, axis=0)
    books = 0.25 * b_lo + 0.25 * b94 + 0.5 * b103
    # align book columns to open columns before numpy conversion (run_row is positional)
    books = books[o.columns]

    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    carry = carry.reindex(idx)["carry"].astype(float).fillna(0.0)

    # portfolio vol targeting from combined books (v104 convention)
    ret1 = o / o.shift(1) - 1
    s_by_target = {}
    realized_common = (books.shift(2) * ret1).sum(axis=1)
    for key, cfg in ROWS.items():
        realized = W_BOOKS * realized_common + W_CARRY * carry.shift(1)
        vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
        s = (cfg["target"] / vol).clip(upper=CAP).fillna(1.0)
        s = s.replace([np.inf, -np.inf], 2.0).fillna(1.0)
        s_by_target[key] = (realized, vol, s)

    live_mask = np.asarray((idx >= LIVE_START) & (idx < LIVE_END))
    o_vals = o.to_numpy(dtype=float)
    books_vals = books.to_numpy(dtype=float)
    carry_vals = carry.to_numpy(dtype=float)

    n_live = int(live_mask.sum())
    result_rows = {}
    artifacts = {}
    for key, cfg in ROWS.items():
        s_vals = s_by_target[key][2].to_numpy(dtype=float)
        per_sc = {}
        for sc, (fee, slip) in SCEN.items():
            out = run_row(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip, cfg["governed"])
            net_s = pd.Series(out["net"], index=idx)
            turn_s = pd.Series(out["turn"], index=idx)
            g_s = pd.Series(out["g"], index=idx)
            e_s = pd.Series(out["E"], index=idx)
            # yearly slices
            yearly = []
            gmeans = []
            for anchor in ANCHORS:
                a = pd.Timestamp(anchor, tz="UTC")
                m = (idx >= a) & (idx < a + pd.Timedelta(days=365))
                st = slice_stats(net_s[m], turn_s[m])
                st["anchor"] = anchor
                yearly.append(st)
                gm = (idx >= a) & (idx < a + pd.Timedelta(days=365)) & (idx >= LIVE_START) & (idx < LIVE_END)
                gmeans.append(dict(anchor=anchor, mean_g=round(float(g_s[gm].mean()), 4),
                                   n_bars=int(gm.sum())))
            # full-path live equity and max DD
            live_e = e_s[live_mask]
            # rebuild live equity from live nets to avoid pre/post flat effects
            live_net = net_s[live_mask]
            live_eq = (1 + live_net).cumprod()
            full_dd = float(np.max(1 - live_eq / live_eq.cummax())) if len(live_eq) else float("nan")
            per_sc[sc] = dict(yearly=yearly, mean_g_per_anchor_year=gmeans,
                              full_path_live_max_dd_pct=round(100 * full_dd, 2),
                              full_path_live_net_pct=round(100 * (float(live_eq.iloc[-1]) - 1), 2) if len(live_eq) else float("nan"))
            artifacts[(key, sc)] = (net_s, turn_s, g_s, e_s)
        result_rows[key] = per_sc

    out_json = {
        "anchors": list(ANCHORS),
        "live": {"start": str(LIVE_START), "end_exclusive": str(LIVE_END), "n_live_bars": n_live,
                 "union_bars": int(len(idx)),
                 "oos_span": [str(idx[0]), str(idx[-1])]},
        "books_spec": ("b_lo = v92 LO weights (shorts=False) * v92 20pct scale; b94 = v94 LS * 20pct scale; "
                       "b103 = v103 LS * own 20pct scale; books = 0.25 b_lo + 0.25 b94 + 0.5 b103; "
                       "OOS from audited CSVs (v92_audit/predictions_5asset.csv, "
                       "v93_v94_audit/predictions_v94.csv, v103_v105_audit/predictions_v103.csv)"),
        "wrapper_spec": ("realized_t = 0.8*sum(books_{t-2}*(open_t/open_{t-1}-1)) + 0.6*carry_{t-1}; "
                         "vol = rolling-360 (min 120) std * sqrt(2190); s = min(target/vol, 2) NaN->1; "
                         "live [2021-09-24, 2026-09-23), else w=c=0; governor i>=2: j=i-2, "
                         "peak=max(E j-539..j incl pre-start 1), DD=1-E_j/peak, "
                         "g=clip((0.20-DD)/0.10,0,1), 1 when ungoverned/i<2; w=0.8*s*books*g; c=0.6*s*g; "
                         "net=sum(w*(o_{i+2}/o_{i+1}-1))-sum|dw|*(fee+slip)-0.00005*sum(max(w,0))"
                         "+c*carry-|dc|*2*0.0004/1.2; E*=1+net, E_before=1"),
        "rows": {k: {"target": v["target"], "governed": v["governed"]} for k, v in ROWS.items()},
        "execution": {"scenarios": {k: {"fee": v[0], "slip": v[1]} for k, v in SCEN.items()},
                      "long_funding_per_4h_bar": 5e-05, "carry_cost_rate": 2 * 0.0004 / 1.2,
                      "governor": {"window_bars": GOV_WIN, "start_dd": 0.10, "stop_dd": 0.20}},
        "results": result_rows,
        "data": {"v92_oos": "v92_audit/predictions_5asset.csv",
                 "v94_oos": "v93_v94_audit/predictions_v94.csv",
                 "v103_oos": "v103_v105_audit/predictions_v103.csv",
                 "carry": "artifacts/research/carry/carry_oos_fee0.0004.parquet"},
        "assumptions": [
            "Weights/vol reimplemented from audited v92/v94 formulas (daily rebalance ffill, 20pct cap2).",
            "Live mask literal [2021-09-24, 2026-09-23); 2026-09-23 bars forced w=c=0.",
            "Forward return fillna 0 for last two bars; peak includes pre-start E=1.",
            "Carry first-bar cost |c_i-c_{i-1}| with c_prev=0 (differs from v109 wrapper fillna-0).",
            "Yearly net/DD are slice-local recompositions; full-path DD is over live-span equity.",
        ],
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out_json, f, indent=2)
    # supporting artifacts: per-row scale + per-row/scenario equity
    s_frame = pd.DataFrame({"t": idx}
                           | {f"s_{k}": s_by_target[k][2].values for k in ROWS})
    s_frame.to_csv(OUT_DIR / "scales.csv", index=False)
    pd.DataFrame({"t": idx, "books_BTC": books["BTCUSDT"].values,
                  "carry": carry.values, "live": live_mask.astype(int)}).to_csv(
        OUT_DIR / "books_carry.csv", index=False)
    for (key, sc), (net_s, turn_s, g_s, e_s) in artifacts.items():
        pd.DataFrame({"t": idx, "net": net_s.values, "turnover": turn_s.values,
                      "g": g_s.values, "equity": e_s.values}).to_csv(
            OUT_DIR / f"equity_{key}_{sc}.csv", index=False)
    print(json.dumps({"n_live": n_live, "union": len(idx),
                      "primary_normal": result_rows["primary_gated_0.25"]["normal"]}, indent=2))


if __name__ == "__main__":
    main()
