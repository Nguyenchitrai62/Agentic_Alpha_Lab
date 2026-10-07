"""oc_regimetrue: regime x depth dip P&L with TRUE per-rung pairs.

DIAGNOSTIC only (see PLAN.md, pre-registered before any outcome was computed).
Reads oc_kpi events_s{0..3}.parquet (IN PARQUET/APPEND ORDER for TRUE pairing)
+ hourly_ext.parquet (majors only) + oc_manual3 n_per_fill.parquet (s0 exact-n
cross-check). No 1m data. One process, RAM < 1 GB.
Writes results.json in this folder.
Usage: .venv/Scripts/python.exe research/tournament/oc_regimetrue/analyze_regimetrue.py
"""
from __future__ import annotations

import json
from bisect import bisect_left
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
KPI = HERE.parent / "oc_kpi"
EXT = HERE.parent / "ext"
MANUAL3 = HERE.parent / "oc_manual3"
DEEPCHECK = Path(__file__).parents[3] / "research/diagnostics/oc_deepcheck/results.json"
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
DEPTHS = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
ANCH_END = pd.Timestamp("2026-09-24", tz="UTC")
EMBARGO = pd.Timedelta(days=7)
H4_HOURS = {0, 4, 8, 12, 16, 20}
EXITS = ("rung_sl", "rung_tp", "rung_timeout")


def year_of(t) -> int | None:
    t = pd.Timestamp(t)
    for k in range(5):
        end = ANCH[k + 1] if k < 4 else ANCH_END
        if ANCH[k] <= t < end:
            return k
    return None


def pair_true(ev: pd.DataFrame):
    """Positional pairing (exact copy of oc_deepcheck pair_true).

    Engine appends, per bar in fill-sorted order, (rung_fill, its exit)
    consecutively; the parquet preserves that append order (NOT time-sorted).
    """
    rows, viol, maxwdiff = [], 0, 0.0
    for i in range(len(ev)):
        r = ev.iloc[i]
        if r["kind"] == "rung_fill":
            x = ev.iloc[i + 1]
            if x["kind"] not in EXITS or x["symbol"] != r["symbol"]:
                viol += 1
                continue
            maxwdiff = max(maxwdiff, abs(float(x["weight"]) - float(r["weight"])))
            rows.append(dict(
                fill_t=pd.Timestamp(r["t"]), exit_t=pd.Timestamp(x["t"]),
                symbol=r["symbol"], depth=float(r["rung"]),
                exit=x["kind"], weight=float(x["weight"]), ret=float(x["ret"]),
                pnl=float(x["weight"]) * float(x["ret"])))
    return rows, viol, maxwdiff


def floor_h4(ts: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    h = (ts.hour // 4) * 4
    return pd.Timestamp(ts.year, ts.month, ts.day, h, tz="UTC")


def build_4h(hourly: pd.DataFrame):
    out = {}
    for coin in MAJORS:
        g = hourly[hourly["sym"] == coin].sort_values("t")
        g = g[(g["t"].dt.hour.isin(H4_HOURS)) & (g["t"].dt.minute == 0)]
        g = g[g["t"] < ANCH_END].drop_duplicates("t").set_index("t").sort_index()
        o = g["open"].astype(float)
        sigma = o.pct_change().rolling(360, min_periods=120).std(ddof=1)
        out[coin] = pd.DataFrame({"open": o, "sigma": sigma})
    btc = out["BTCUSDT"]["open"]
    ma1200 = btc.rolling(1200, min_periods=600).mean()
    return out, btc, ma1200


def summ(v):
    n = len(v)
    pnl = float(sum(r["pnl"] for r in v))
    wins = sum(1 for r in v if r["ret"] > 0)
    return dict(n=n, pnl_sub_pct=round(pnl * 100, 3),
                pnl_mix_pct=round(pnl / 4 * 100, 3),
                win=round(wins / n, 4) if n else None)


def main():
    hourly = pd.read_parquet(EXT / "hourly_ext.parquet", columns=["t", "open", "sym"])
    hourly["t"] = pd.to_datetime(hourly["t"], utc=True)
    assert hourly["t"].max() < ANCH_END, hourly["t"].max()
    per4h, btc_open, ma1200 = build_4h(hourly)

    cutoffs: dict[str, dict[str, tuple[float, float]]] = {}
    for coin in MAJORS:
        s = per4h[coin]["sigma"].dropna()
        cutoffs[coin] = {}
        for k in range(5):
            hist = s[s.index < (ANCH[k] - EMBARGO)]
            cutoffs[coin][str(k)] = (float(hist.quantile(0.33)), float(hist.quantile(0.66)))

    # exact v399 n (s0 cross-check): key (sym, t_fill, depth)
    npf = pd.read_parquet(MANUAL3 / "n_per_fill.parquet",
                           columns=["sym", "t_fill", "x1", "n"])
    npf["t_fill"] = pd.to_datetime(npf["t_fill"], utc=True)
    exact_n = {}
    for r in npf.itertuples():
        exact_n.setdefault((r.sym, pd.Timestamp(r.t_fill), float(r.x1)), int(r.n))

    # ---- TRUE pairs over 4 shifts (parquet order preserved) ----
    all_rows = []
    checks = dict(adjacency_violations=0, max_fill_exit_wdiff=0.0)
    for s in range(4):
        ev = pd.read_parquet(KPI / f"events_s{s}.parquet")
        rows, viol, maxwd = pair_true(ev)
        checks["adjacency_violations"] += int(viol)
        checks["max_fill_exit_wdiff"] = max(checks["max_fill_exit_wdiff"], float(maxwd))
        for d in rows:
            d["shift"] = s
            d["year"] = year_of(d["fill_t"])
            all_rows.append(d)
    checks["n_rungs"] = len(all_rows)
    assert all_rows and max(r["fill_t"] for r in all_rows) < ANCH_END
    checks["outside_anchor_years"] = sum(1 for d in all_rows if d["year"] is None)
    rows = [d for d in all_rows if d["year"] is not None]

    # ---- same-shift event breadth n (primary B1 proxy) ----
    shift_fills: dict[int, list] = {}
    for d in rows:
        shift_fills.setdefault(d["shift"], []).append((d["fill_t"], d["symbol"]))
    per_coin_shift = {}
    for s, lst in shift_fills.items():
        for c in MAJORS:
            per_coin_shift[(s, c)] = sorted(t for t, cc in lst if cc == c)
    for d in rows:
        t, n = d["fill_t"], 0
        lo = t - pd.Timedelta(minutes=60)
        for c in MAJORS:
            if c == d["symbol"]:
                continue
            arr = per_coin_shift[(d["shift"], c)]
            j = bisect_left(arr, lo)
            if j < len(arr) and arr[j] <= t:
                n += 1
        d["n"] = int(n)
        d["n_bucket"] = "n0" if n == 0 else ("n1" if n == 1 else "n2p")
        # exact n (s0 only)
        if d["shift"] == 0:
            e = exact_n.get((d["symbol"], pd.Timestamp(d["fill_t"]), float(d["depth"])))
            d["n_exact"] = ("n0" if e == 0 else ("n1" if e == 1 else "n2p")) if e is not None else "unknown"
        else:
            d["n_exact"] = "na_shift"
    checks["n_exact_join_s0"] = sum(1 for d in rows if d["shift"] == 0 and d["n_exact"] != "unknown")
    checks["n_exact_unknown_s0"] = sum(1 for d in rows if d["shift"] == 0 and d["n_exact"] == "unknown")

    # ---- bear / sigma regimes at T0 ----
    btc_idx = btc_open.index
    for d in rows:
        t0 = floor_h4(d["fill_t"])
        d["T0"] = t0
        try:
            o = float(btc_open.loc[t0])
            m = float(ma1200.loc[t0])
            d["bear"] = "bear" if (np.isfinite(o) and np.isfinite(m) and o < m) else "bull"
        except KeyError:
            d["bear"] = "bull"
        coin, y = d["symbol"], d["year"]
        try:
            sg = float(per4h[coin]["sigma"].loc[t0])
        except KeyError:
            sg = float("nan")
        d["sigma_val"] = sg
        if y is None or not np.isfinite(sg):
            d["sigma_terc"] = "unknown"
        else:
            p33, p66 = cutoffs[coin][str(y)]
            d["sigma_terc"] = "low" if sg <= p33 else ("high" if sg > p66 else "mid")
    checks["unknown_sigma"] = sum(1 for d in rows if d["sigma_terc"] == "unknown")

    dims = {"bear": ("bear", ["bear", "bull"]),
            "sigma_terc": ("sigma_terc", ["low", "mid", "high"]),
            "n": ("n_bucket", ["n0", "n1", "n2p"])}
    tables, totals, flags = {}, {}, {}
    for dim, (key, vals) in dims.items():
        t = {}
        for y in list(range(5)) + ["pooled"]:
            sel_y = rows if y == "pooled" else [r for r in rows if r["year"] == y]
            yd = {}
            for dd in DEPTHS:
                yd[str(dd)] = {v: summ([r for r in sel_y if r["depth"] == dd and r[key] == v])
                               for v in vals}
            t[str(y)] = yd
        tables[dim] = t
    for y in list(range(5)) + ["pooled"]:
        sel_y = rows if y == "pooled" else [r for r in rows if r["year"] == y]
        totals[str(y)] = {str(dd): summ([r for r in sel_y if r["depth"] == dd]) for dd in DEPTHS}
        totals[str(y)]["all"] = summ(sel_y)
    for dim, (key, vals) in dims.items():
        fd = {}
        for dd in DEPTHS:
            gd = {}
            for v in vals:
                signs = []
                for y in range(5):
                    sel = [r for r in rows if r["year"] == y and r["depth"] == dd and r[key] == v]
                    signs.append(round(sum(r["pnl"] for r in sel) / 4 * 100, 3))
                gd[v] = dict(yearly_mix_pct=signs,
                             n_years_ge0=sum(1 for x in signs if x >= 0),
                             lose_ge4=sum(1 for x in signs if x < 0) >= 4,
                             win_5=all(x >= 0 for x in signs))
            fd[str(dd)] = gd
        flags[dim] = fd

    # s0-only exact-n secondary table
    s0 = [r for r in rows if r["shift"] == 0 and r["n_exact"] != "unknown"]
    exact_table = {}
    for y in list(range(5)) + ["pooled"]:
        sel_y = s0 if y == "pooled" else [r for r in s0 if r["year"] == y]
        exact_table[str(y)] = {str(dd): {v: summ([r for r in sel_y if r["depth"] == dd and r["n_exact"] == v])
                                          for v in ("n0", "n1", "n2p")} for dd in DEPTHS}
    exact_table["n_s0_joined"] = len(s0)

    # replication vs oc_deepcheck TRUE per-depth tables (fill year)
    dc = json.loads(DEEPCHECK.read_text())["by_depth_fill_year"]["true"]
    repdiff, repn = 0.0, {}
    for y in list(range(5)) + ["pooled"]:
        yy = "pooled" if y == "pooled" else str(y)
        for dd in DEPTHS:
            a = totals[str(y)][str(dd)]["pnl_mix_pct"]
            b = dc[yy][str(dd)]["pnl_mix_pct"]
            repdiff = max(repdiff, abs(a - b))
        repn[str(y)] = sum(totals[str(y)][str(dd)]["n"] for dd in DEPTHS)
    checks["replication_max_abs_mixdiff_vs_deepcheck_true"] = round(repdiff, 4)
    checks["per_year_n"] = repn
    assert repdiff < 0.002, repdiff
    assert len(rows) == 21389, len(rows)

    out = dict(
        variant="R2B1D17BF", diagnostic=True,
        selection_rule="none (diagnostic, no PROMISING rule)",
        methods=("TRUE pairs = positional adjacency in engine append order "
                 "(fill row + its own exit row, same symbol; weight diff recorded). "
                 "pnl = exit weight * engine ret (net of rung fees), "
                 "pnl_mix = pnl_sub/4. Year = FILL in anchor year "
                 "[A_k, A_k+365d). T0 = floor(fill_t to standard 4h grid); "
                 "bear = v410 BTC open4[T0] < MA1200[T0] incl T0 min600 NaN->bull; "
                 "sigma_terc = per-coin sigma4 (4h-open returns trailing360/min120) "
                 "vs walk-forward p33/p66 on T < anchor-7d; "
                 "n = same-shift distinct other majors with a rung_fill in "
                 "[fill_t-60min, fill_t] (event-based B1-breadth proxy; exact 1m "
                 "B1 n NOT recomputed, no 1m read per LIGHT); "
                 "n_exact = stored v399 n joined on (sym, t_fill, depth), s0 only. "
                 "No 1m data read."),
        anchors=[a.strftime("%Y-%m-%d") for a in ANCH],
        cutoffs_sigma={c: {k: [round(float(x[0]), 6), round(float(x[1]), 6)]
                           for k, x in v.items()} for c, v in cutoffs.items()},
        totals=totals, tables=tables, flags=flags,
        exact_n_s0=exact_table, checks=checks)
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("n_rungs", len(rows), "viol", checks["adjacency_violations"], flush=True)
    print("pooled all mix%", totals["pooled"]["all"]["pnl_mix_pct"], flush=True)
    print("repdiff", checks["replication_max_abs_mixdiff_vs_deepcheck_true"], flush=True)
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
