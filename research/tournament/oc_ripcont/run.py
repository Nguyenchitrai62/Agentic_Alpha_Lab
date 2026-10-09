"""oc_ripcont run: pullback-after-rip long sleeve on four 4h clocks.

PASS1 (dev4 only): C1 (k=2) + C2 (k=3) fills with fill_time in
[2021-09-24, 2025-09-24), placebo (200 draws, seed 7), G2 baseline check.
Choice per PLAN.md. PASS2: most-recent year [2025-09-24, 2026-09-24) scored
ONCE, only for the chosen variant. Overlay on G2 only if PROMISING.

Usage: .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_ripcont --min-free-gb 2.0 -- .venv/Scripts/python.exe research/tournament/oc_ripcont/run.py
"""
from __future__ import annotations

import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OC = Path(__file__).parent
sys.path.insert(0, str(OC))
import backtest as B

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
RAW_BTC = ROOT / "data/raw/btc_intraday_20260924"
RAW_MAJ = ROOT / "data/raw/majors_intraday_20260924"
END = pd.Timestamp("2026-09-24", tz="UTC")
START = pd.Timestamp("2020-01-01", tz="UTC")
DEV_ANCH = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24"]
LAST_ANCH = "2025-09-24"
DEV_END = pd.Timestamp("2025-09-24", tz="UTC")
VARIANTS = {"C1": 2.0, "C2": 3.0}
SHIFTS = [0, 1, 2, 3]
DIP_DD_REF = 1.2796  # oc_rips DIP _5y daily-sum DD (single grid, mirrored exits)
SEED = 7


def minute_files(sym: str):
    if sym == "BTCUSDT":
        return sorted(RAW_BTC.glob("klines_1m_*.parquet"))
    return sorted(RAW_MAJ.glob(f"{sym}_1m_*.parquet"))


def load_ohlc(sym: str) -> pd.DataFrame:
    parts = [pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"])
             for f in minute_files(sym)]
    m = pd.concat(parts)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    return m[(m.index >= START) & (m.index < END)]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def g2_baseline_check():
    """Reproduce v421 R2B1D17BFG2 yearly rows + full-path DD to the digit."""
    v421_res = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json").read_text())
    exp = v421_res["rows"]["R2B1D17BFG2"]
    runs = pickle.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl").read_bytes())
    v388 = _load("v388_oc_ripcont", ROOT / "research/parallel/rounds/parallel-20260906-r2/v388/v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    g0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
    Es, Ms = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s]["R2B1D17BFG2"], g0, g1)
        Es.append(e1.to_numpy(dtype=float))
        Ms.append(m1.to_numpy(dtype=float))
    Es = np.stack(Es)
    Ms = np.stack(Ms)
    emix = Es.mean(axis=0)
    mmix = Ms.mean(axis=0)
    grid = pd.date_range(g0, g1, freq="1h")
    e = pd.Series(emix, index=grid)
    mn = pd.Series(mmix, index=grid)
    got_years = []
    for a in list(v388.ANCH):
        a0 = pd.Timestamp(a, tz="UTC")
        a1 = a0 + pd.Timedelta(days=365)
        seg = (grid > a0) & (grid <= a1)
        E4, M4 = [], []
        for s in range(4):
            es_s = pd.Series(Es[s], index=grid)
            ms_s = pd.Series(Ms[s], index=grid)
            b = float(es_s[es_s.index <= a0].iloc[-1]) if (es_s.index <= a0).any() else 1.0
            E4.append((es_s[seg] / b).to_numpy(dtype=float))
            M4.append((ms_s[seg] / b).to_numpy(dtype=float))
        es = np.mean(E4, axis=0)
        ms = np.mean(M4, axis=0)
        R = round(100 * float(es[-1] ** (1 / 12) - 1), 3)
        pk = np.maximum.accumulate(es)
        DD = round(100 * float(np.max(1 - ms / pk)), 2)
        got_years.append([R, DD])
    assert got_years == [list(r) for r in exp["years"]], (got_years, exp["years"])
    R5 = round(float(np.prod([1 + r / 100 for r, _ in got_years]) ** (1 / 5) - 1) * 100, 3)
    assert R5 == exp["R"], (R5, exp["R"])
    assert max(d for _, d in got_years) == exp["DD"]
    segf = np.asarray(grid > pd.Timestamp("2021-09-24", tz="UTC"))
    esf, msf = emix[segf], mmix[segf]
    dd_m = round(100 * float(np.max(1 - msf / np.maximum.accumulate(esf))), 2)
    dd_c = round(100 * float(np.max(1 - esf / np.maximum.accumulate(esf))), 2)
    assert max(dd_m, dd_c) == exp["full_path_dd"], ((dd_m, dd_c), exp["full_path_dd"])
    print(f"G2 baseline OK: R={R5} W={min(r for r,_ in got_years)} DD={exp['DD']} full={exp['full_path_dd']}", flush=True)
    # daily returns of the 4-phase mix for correlation (dev4 + last year)
    rets = pd.Series(emix, index=grid).resample("1D").last().pct_change().fillna(0.0)
    rets.index = rets.index.tz_convert("UTC") if rets.index.tz is not None else rets.index.tz_localize("UTC")
    return rets


def summarize(nets: np.ndarray):
    nets = np.asarray(nets, dtype=float)
    if len(nets) == 0:
        return {"n": 0, "mean_bps": None, "win": None, "sum": 0.0,
                "sum_scaled": 0.0, "tp": 0, "sl": 0, "time": 0}
    return {"n": int(len(nets)), "mean_bps": round(1e4 * float(nets.mean()), 2),
            "win": round(float((nets > 0).mean()), 4),
            "sum": round(float(nets.sum()), 4),
            "sum_scaled": round(float(nets.sum()) * 0.025, 4)}


def placebo_draw_fast(H, Lw, O, idx_ns, b0_pool: np.ndarray, sig_pool: np.ndarray,
                      open_pool_bar: np.ndarray, n_need: int, rng: np.random.Generator):
    """Sample n_need (bar, minute) pairs; immediate fill at minute-open.

    Returns list of nets. Resamples up to 10 tries per slot for finite opens.
    """
    nets = []
    if n_need <= 0 or len(b0_pool) == 0:
        return nets
    n = len(O)
    for _ in range(n_need):
        ok = False
        for _try in range(10):
            bi = int(rng.integers(0, len(b0_pool)))
            b0 = int(b0_pool[bi])
            s = float(sig_pool[bi])
            if not np.isfinite(s) or s <= 0:
                continue
            off = int(rng.integers(5, 200))  # 5..199 inclusive
            f = b0 + off
            if f < 0 or f >= n:
                continue
            L = O[f]
            if not np.isfinite(L) or L <= 0:
                continue
            ok = True
            break
        if not ok:
            continue
        lo = f + 1
        hi = min(b0 + 239, n - 1)
        sl = L * float(np.exp(-B.SL_K * s))
        tp = L * float(np.exp(B.TP_K * s))
        how, px, x = None, None, None
        if lo <= hi:
            segL = Lw[lo:hi + 1]
            segH = H[lo:hi + 1]
            sh = np.isfinite(segL) & (segL <= sl)
            th = np.isfinite(segH) & (segH > tp)
            si = int(np.argmax(sh)) if np.any(sh) else None
            ti = int(np.argmax(th)) if np.any(th) else None
            if si is not None and (ti is None or si <= ti):
                how, px, x = "stop", sl, lo + si
            elif ti is not None:
                how, px, x = "tp", tp, lo + ti
        if how is None:
            x = b0 + 240
            if x >= n or not np.isfinite(O[x]):
                continue
            how, px = "time", float(O[x])
        nf = B.count_funding(int(idx_ns[f]), int(idx_ns[x]))
        nets.append(B.net_long(float(L), float(px), how, nf))
    return nets


def main():
    g2_daily = g2_baseline_check()

    gid = pd.date_range(START, END - pd.Timedelta(minutes=1), freq="1min", tz="UTC")
    gid_ns = gid.values.astype("datetime64[ns]").astype(np.int64)
    is_bar = {}
    for s in SHIFTS:
        sh = pd.Timedelta(hours=s)
        is_bar[s] = np.asarray((gid - sh).floor("4h") + sh == gid)

    DEV_A0 = pd.Timestamp(DEV_ANCH[0], tz="UTC")
    # ---------- PASS 1: dev4 ----------
    fills = {v: [] for v in VARIANTS}
    # placebo accumulators: per variant, per draw -> (sum, count)
    NDRAW = 200
    pbo_sum = {v: np.zeros(NDRAW) for v in VARIANTS}
    pbo_cnt = {v: np.zeros(NDRAW, dtype=int) for v in VARIANTS}
    rng = np.random.Generator(np.random.PCG64(SEED))

    for sym in SYMS:
        print("loading", sym, flush=True)
        m = load_ohlc(sym).reindex(gid)
        O = m["open"].to_numpy(dtype=float)
        H = m["high"].to_numpy(dtype=float)
        Lw = m["low"].to_numpy(dtype=float)
        C = m["close"].to_numpy(dtype=float)
        idx_ns = gid_ns
        for s in SHIFTS:
            bp_all = np.flatnonzero(is_bar[s])
            ok = bp_all + 240 < len(O)
            bp_all = bp_all[ok]
            bt_all = gid[bp_all]
            opens = O[bp_all]
            sig = B.sigma_from_bar_opens_log(opens)
            # dev bars: T in [DEV_A0 - 4h, DEV_END)
            dev_mask = (bt_all >= DEV_A0 - pd.Timedelta(hours=4)) & (bt_all < DEV_END)
            bp, bt, sg = bp_all[dev_mask], bt_all[dev_mask], sig[dev_mask]
            for v, k in VARIANTS.items():
                evs = B.simulate_clock(idx_ns, O, H, Lw, C, bp, bt.to_numpy(), sg, k)
                for e in evs:
                    e["sym"] = sym
                    e["shift"] = s
                # keep only fills with fill_time in dev4
                kept = []
                for e in evs:
                    ft = gid[e["fill_idx"]]
                    if DEV_A0 <= ft < DEV_END:
                        e["fill_time"] = ft
                        e["exit_time"] = gid[e["exit_idx"]]
                        e["bar_open"] = pd.to_datetime(e["bar_open"], utc=True)
                        kept.append(e)
                fills[v].extend(kept)
                print(f"  {sym} s={s} {v}: {len(kept)} dev fills", flush=True)
        # placebo per (coin, year) using this coin's arrays (all shifts pooled)
        # build per-year bar pools first
        for v, k in VARIANTS.items():
            dfv = [e for e in fills[v] if e["sym"] == sym]
            for A in DEV_ANCH:
                a0 = pd.Timestamp(A, tz="UTC")
                a1 = a0 + pd.Timedelta(days=365)
                n_need = sum(1 for e in dfv if a0 <= e["fill_time"] < a1)
                if n_need <= 0:
                    # still need zero contribution; draws get nothing for this cell
                    continue
                # pool: bars (all shifts) with T in [a0-4h, a1), sigma finite
                pool_b0, pool_sig = [], []
                for s in SHIFTS:
                    bp_all = np.flatnonzero(is_bar[s])
                    ok = bp_all + 240 < len(O)
                    bp_all = bp_all[ok]
                    bt_all = gid[bp_all]
                    opens = O[bp_all]
                    sig = B.sigma_from_bar_opens_log(opens)
                    ym = (bt_all >= a0 - pd.Timedelta(hours=4)) & (bt_all < a1)
                    for b0, sg in zip(bp_all[ym], sig[ym]):
                        if np.isfinite(sg) and sg > 0 and np.isfinite(O[b0]) and O[b0] > 0:
                            pool_b0.append(int(b0))
                            pool_sig.append(float(sg))
                pool_b0 = np.asarray(pool_b0, dtype=np.int64)
                pool_sig = np.asarray(pool_sig, dtype=float)
                for d in range(NDRAW):
                    nets = placebo_draw_fast(H, Lw, O, idx_ns, pool_b0, pool_sig, None, n_need, rng)
                    if nets:
                        pbo_sum[v][d] += float(np.sum(nets))
                        pbo_cnt[v][d] += len(nets)
        del m, O, H, Lw, C

    dev = {}
    for v in VARIANTS:
        df = pd.DataFrame(fills[v])
        if len(df):
            df["fill_time"] = pd.to_datetime(df["fill_time"], utc=True)
        per_year = {}
        for A in DEV_ANCH:
            a0 = pd.Timestamp(A, tz="UTC")
            a1 = a0 + pd.Timedelta(days=365)
            sub = df[(df["fill_time"] >= a0) & (df["fill_time"] < a1)] if len(df) else df
            s = summarize(sub["net"].to_numpy() if len(sub) else np.array([]))
            if len(sub):
                s["tp"] = int((sub["how"] == "tp").sum())
                s["sl"] = int((sub["how"] == "stop").sum())
                s["time"] = int((sub["how"] == "time").sum())
            per_year[A] = s
        # daily-sum DD over dev4 (scaled)
        days = pd.date_range(pd.Timestamp(DEV_ANCH[0], tz="UTC"), DEV_END, freq="D", tz="UTC", inclusive="left")
        if len(df):
            g = df.groupby(df["fill_time"].dt.floor("D"))["net"].sum() * 0.025
            dsum = g.reindex(days, fill_value=0.0)
        else:
            dsum = pd.Series(0.0, index=days)
        cum = dsum.cumsum()
        dd = float((cum.cummax() - cum).max())
        allnets = df["net"].to_numpy() if len(df) else np.array([])
        per_year["_dev4"] = {**summarize(allnets), "dd": round(dd, 4)}
        per_year["_daily"] = dsum
        dev[v] = {"df": df, "per_year": per_year}

    # placebo percentiles (pooled dev4 mean per draw)
    placebo = {}
    for v in VARIANTS:
        means = []
        for d in range(NDRAW):
            if pbo_cnt[v][d] > 0:
                means.append(1e4 * pbo_sum[v][d] / pbo_cnt[v][d])
        means = np.asarray(means, dtype=float)
        actual = dev[v]["per_year"]["_dev4"]["mean_bps"]
        if actual is None or len(means) == 0:
            pct = None
        else:
            pct = round(100 * float((means <= actual).mean()), 1)
        placebo[v] = {"n_draws": int(len(means)),
                      "actual_mean_bps": actual,
                      "pbo_mean_of_means_bps": round(float(means.mean()), 2) if len(means) else None,
                      "pbo_p95_bps": round(float(np.percentile(means, 95)), 2) if len(means) else None,
                      "percentile": pct}

    # correlation vs G2 daily (dev4)
    corr = {}
    for v in VARIANTS:
        dsum = dev[v]["per_year"].pop("_daily")
        g = g2_daily.reindex(dsum.index, fill_value=0.0).to_numpy()
        x = dsum.to_numpy()
        corr[v] = round(float(np.corrcoef(x, g)[0, 1]), 4) if x.std() > 0 and g.std() > 0 else None

    # decision + choice (dev4 only)
    decision = {}
    for v in VARIANTS:
        means = [dev[v]["per_year"][A]["mean_bps"] for A in DEV_ANCH]
        ok_years = sum(1 for m in means if m is not None and m > 5.0)
        ssum = dev[v]["per_year"]["_dev4"]["sum"]
        dd = dev[v]["per_year"]["_dev4"]["dd"]
        pct = placebo[v]["percentile"]
        reasons = []
        if not (ok_years >= 3):
            reasons.append(f"only {ok_years}/4 dev years > +5bps")
        if not (ssum > 0):
            reasons.append("dev sum not positive")
        if pct is None or not (pct >= 95):
            reasons.append(f"placebo percentile {pct} < 95")
        if not (dd < 2 * DIP_DD_REF):
            reasons.append(f"DD {dd} not < 2x dip DD {DIP_DD_REF}")
        decision[v] = {"promising": len(reasons) == 0, "ok_years": ok_years,
                       "dev_sum": ssum, "dd": dd, "placebo_pct": pct,
                       "reasons": reasons if reasons else ["all four gates pass"]}

    def worst_mean(v):
        ms = [dev[v]["per_year"][A]["mean_bps"] for A in DEV_ANCH]
        ms = [m for m in ms if m is not None]
        return min(ms) if ms else float("-inf")

    prom = [v for v in VARIANTS if decision[v]["promising"]]
    if len(prom) == 1:
        chosen = prom[0]
    elif len(prom) > 1:
        chosen = sorted(prom, key=lambda v: (worst_mean(v), dev[v]["per_year"]["_dev4"]["mean_bps"] or float("-inf")))[-1]
    else:
        chosen = sorted(list(VARIANTS), key=lambda v: (worst_mean(v), dev[v]["per_year"]["_dev4"]["mean_bps"] if dev[v]["per_year"]["_dev4"]["mean_bps"] is not None else float("-inf")))[-1]
    print("DEV4 decision:", json.dumps(decision, indent=1), flush=True)
    print("DEV4 placebo:", json.dumps(placebo, indent=1), flush=True)
    print("chosen (dev4 only):", chosen, flush=True)

    # ---------- PASS 2: most-recent year ONCE for the chosen variant ----------
    k = VARIANTS[chosen]
    LAST_A0 = pd.Timestamp(LAST_ANCH, tz="UTC")
    LAST_A1 = LAST_A0 + pd.Timedelta(days=365)
    last_fills = []
    for sym in SYMS:
        print("last-year loading", sym, flush=True)
        m = load_ohlc(sym).reindex(gid)
        O = m["open"].to_numpy(dtype=float)
        H = m["high"].to_numpy(dtype=float)
        Lw = m["low"].to_numpy(dtype=float)
        C = m["close"].to_numpy(dtype=float)
        for s in SHIFTS:
            bp_all = np.flatnonzero(is_bar[s])
            ok = bp_all + 240 < len(O)
            bp_all, bt_all = bp_all[ok], gid[bp_all[ok]]
            sig = B.sigma_from_bar_opens_log(O[bp_all])
            ym = (bt_all >= LAST_A0 - pd.Timedelta(hours=4)) & (bt_all < LAST_A1)
            bp, bt, sg = bp_all[ym], bt_all[ym], sig[ym]
            evs = B.simulate_clock(gid_ns, O, H, Lw, C, bp, bt.to_numpy(), sg, k)
            for e in evs:
                ft = gid[e["fill_idx"]]
                if LAST_A0 <= ft < LAST_A1:
                    e["sym"] = sym
                    e["shift"] = s
                    e["fill_time"] = ft
                    e["exit_time"] = gid[e["exit_idx"]]
                    e["bar_open"] = pd.to_datetime(e["bar_open"], utc=True)
                    last_fills.append(e)
        del m, O, H, Lw, C
    last_df = pd.DataFrame(last_fills)
    if len(last_df):
        last_df["fill_time"] = pd.to_datetime(last_df["fill_time"], utc=True)
        s = summarize(last_df["net"].to_numpy())
        s["tp"] = int((last_df["how"] == "tp").sum())
        s["sl"] = int((last_df["how"] == "stop").sum())
        s["time"] = int((last_df["how"] == "time").sum())
    else:
        s = summarize(np.array([]))

    # dip scale reference (cited, not recomputed): oc_rips DIP rows
    dip_ref = {"note": "oc_rips REPORT mirrored dip, single standard grid, different exits; cited for scale, not recomputed",
               "5y_sum": 11.6751, "dip_dd": DIP_DD_REF,
               "2025-09-24": {"n": 873, "mean_bps": 10.36, "win": 0.6403, "sum": 0.9041}}

    results = {
        "meta": {
            "coins": SYMS, "shifts": SHIFTS, "grid": "4h x 4 clocks (shift 0..3h), 1/4 capital each",
            "trigger": "first minute offset 5..239 with high >= O*exp(k*s)",
            "entry": "resting BUY L=O*exp((k-1)*s), offsets m+1..199, strict trade-through, maker 0.0002",
            "exits": "TP L*exp(+0.75s) maker; SL L*exp(-1.0s) taker stop-first; timeout next-bar open taker",
            "funding": "longs pay 0.0001 per 00/08/16 UTC settlement crossed",
            "size": "0.10 x sub-account (clock) equity per fill = 0.025 x total; sums scaled x0.025",
            "sigma": "std of 4h open-to-open LOG returns, 360 bars, min 120, known at bar open",
            "variants": {"C1": "k=2.0", "C2": "k=3.0", "C3": "DROPPED: no causal per-bar book weight for all four clocks (see PLAN.md)"},
            "anchors_dev": DEV_ANCH, "anchor_last": LAST_ANCH, "data_end": "2026-09-24T00:00Z",
            "placebo": "200 draws, seed 7, same N per (coin,year), random bar+minute 5..199, limit at minute-open with immediate fill, same TP/SL/timeout+funding; pooled dev4 mean",
            "dip_reference": dip_ref,
            "g2_check": "v421 R2B1D17BFG2 reproduced to the digit before overlay",
            "selection": "dev4 only; most-recent scored once for chosen variant only",
        },
        "dev4": {v: {A: dev[v]["per_year"][A] for A in DEV_ANCH + ["_dev4"]} for v in VARIANTS},
        "placebo": placebo,
        "corr_daily_vs_g2_dev4": corr,
        "decision_dev4": decision,
        "chosen": chosen,
        "last_year": {chosen: s},
        "overlay": None,
    }
    if any(decision[v]["promising"] for v in VARIANTS):
        results["overlay"] = {"note": "PROMISING path would overlay here; see REPORT.md"}
    (OC / "results.json").write_text(json.dumps(results, indent=1, default=str))
    print(json.dumps({v: results["dev4"][v] for v in VARIANTS}, indent=1, default=str))
    print("last-year (" + chosen + "):", json.dumps(s, default=str))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
