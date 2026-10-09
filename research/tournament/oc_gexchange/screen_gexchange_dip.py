"""oc_gexchange screen: join dG/z (CHANGES in GEXn) to the G2 dip replica.

Pre-registered in PLAN.md. Steps:
  0. fidelity: exact dip replica base (checksum 902c5bbfe8fed3c0, sum5y 7.718).
  1. build causal z series per coin (d = GEXn[i0]-GEXn[i0-24h], sigma = trailing
     90-day std of 24 h changes over predecessors only, z = d/sigma).
  2. descriptive join on dev years (Spearman, bucket means, stop-out rates).
  3. conditional T1 tilt (only if LOW< MID/HIGH in 4/4 dev years AND spread>+5bps
     in 4/4) + T1c control, dip gate (PROMISING legs + dSum5y>=+0.273) + dev4 view;
     year 5 scored once. Otherwise stop after descriptive.
  4. results.json (+ arrays for REPORT).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_gexchange_screen \
    --min-free-gb 2.0 -- .venv/Scripts/python.exe \
    research/tournament/oc_gexchange/screen_gexchange_dip.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from research.tournament.oc_gex.gex_lib import last_hour_before
from research.tournament.oc_gexchange.gexchange_lib import (
    assign_bucket,
    build_changes,
    trailing_sigma,
)

t0 = time.time()


def log(msg: str) -> None:
    print(f"[oc_gexchange_screen {time.time()-t0:8.1f}s] {msg}", flush=True)


def load_placebo():
    p = ROOT / "research/tournament/oc_placebo_dip/compute_placebo_dip.py"
    spec = importlib.util.spec_from_file_location("oc_placebo_mod", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = load_placebo()
MAJORS = P.MAJORS
ANCHORS = P.ANCHORS
YEAR_END = P.YEAR_END
PHASES = P.PHASES
START = P.START
DD_TOL = P.DD_TOL
GATE_DSUM = 0.273  # pooled placebo p95 (5-year calibration, labelled)


def add_how_column() -> dict:
    """Byte-identical copy of oc_gex.add_how_column (itself identical to
    P.build_base + how10). Fidelity proven by checksum equality."""
    import pandas as pd  # noqa
    from pathlib import Path as _P

    O, C, base_idx = {}, {}, None
    for sym in P.MAJORS:
        ii, o, c = P.load_oc(sym)
        base_idx = ii if base_idx is None else base_idx
        O[sym], C[sym] = o, c
        log(f"loaded OC {sym}")
    n_all = len(base_idx)
    grids = {}
    for p in P.PHASES:
        off = p * 60
        nb = (n_all - off) // 240
        t0g = base_idx[off:off + nb * 240:240]
        opens_bar, sig_bar = {}, {}
        for sym in P.MAJORS:
            ob = O[sym][off:off + nb * 240:240].astype(float)
            sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            opens_bar[sym], sig_bar[sym] = ob, sg
        js = [j for j in range(nb)
              if P.TRADE_START <= t0g[j] < P.YEAR_END and (off + j * 240 + 240) < n_all]
        grids[p] = dict(off=off, nb=nb, t0=t0g, opens=opens_bar, sig=sig_bar, js=js)
        log(f"shift {p}: traded={len(js)}")
    F = {k: [] for k in ("phase", "coin", "year", "bar_time", "rung",
                         "w", "y09", "y10", "y11", "d09", "d10", "d11", "how10")}
    coin_ix = {s: i for i, s in enumerate(P.MAJORS)}
    for sym in P.MAJORS:
        H, L = P.load_hl(sym, base_idx)
        La, Ha = L, H
        others = [b for b in P.MAJORS if b != sym]
        Oa, Ca = O[sym], C[sym]
        for p in P.PHASES:
            g = grids[p]
            off, t0g = g["off"], g["t0"]
            opens_bar, sig_bar = g["opens"], g["sig"]
            n_fill = 0
            for j in g["js"]:
                bt = t0g[j]
                o1, sg = float(opens_bar[sym][j]), float(sig_bar[sym][j])
                if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                    continue
                base = off + j * 240
                o2m = Oa[base + 240]
                o2 = float(o2m) if np.isfinite(o2m) else np.nan
                settle = (bt + pd.Timedelta(hours=4)).hour in P.SETTLE_HOURS
                yi = P.year_of(bt)
                if yi is None:
                    continue
                low_win = La[base + P.LIVE_A:base + P.LIVE_B + 1].astype(float)
                if others:
                    cmat = np.stack([C[b][base + P.LIVE_A - 1:base + P.LIVE_B].astype(float)
                                     for b in others])
                    oo = np.array([opens_bar[b][j] for b in others], dtype=float)
                    ss = np.array([sig_bar[b][j] for b in others], dtype=float)
                    nvec = P.n_vector(cmat, oo, ss)
                else:
                    nvec = np.zeros(P.LIVE_B - P.LIVE_A + 1, dtype=np.int64)
                Ha_b = Ha[base:base + 240].astype(float)
                La_b = La[base:base + 240].astype(float)
                Ca_b = Ca[base:base + 240].astype(float)
                Oa_b = Oa[base:base + 240].astype(float)
                for ri, k in enumerate(P.RUNGS):
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = P.find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = P.LIVE_A + ib
                    nf = int(nvec[ib])
                    r09, x09, _ = P.outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 0.9, o2, settle)
                    r10, x10, h10 = P.outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 1.0, o2, settle)
                    r11, x11, _ = P.outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 1.1, o2, settle)
                    if not (np.isfinite(r09) and np.isfinite(r10) and np.isfinite(r11)):
                        continue
                    n_fill += 1
                    F["phase"].append(p)
                    F["coin"].append(coin_ix[sym])
                    F["year"].append(yi)
                    F["bar_time"].append(off + j * 240)
                    F["rung"].append(ri)
                    F["w"].append(P.size_mult(nf))
                    F["y09"].append(r09)
                    F["y10"].append(r10)
                    F["y11"].append(r11)
                    F["d09"].append(P.exit_day_ordinal(bt, x09, base))
                    F["d10"].append(P.exit_day_ordinal(bt, x10, base))
                    F["d11"].append(P.exit_day_ordinal(bt, x11, base))
                    F["how10"].append(h10)
            log(f"{sym} p{p}: fills={n_fill}")
        del H, L, La, Ha
    led = {k: np.array(v) for k, v in F.items() if k != "how10"}
    for k in ("phase", "coin", "year", "bar_time", "rung", "d09", "d10", "d11"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y09", "y10", "y11"):
        led[k] = led[k].astype(np.float64)
    led["how10"] = np.array(F["how10"])
    return led


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 10:
        return float("nan")
    return float(pd.Series(x[m]).corr(pd.Series(y[m]), method="spearman"))


def build_z_for_series(hour_end: pd.Series, g: np.ndarray):
    """Causal z series for one hourly GEXn series. Returns (d, sigma, z, regular)."""
    he_ns = hour_end.values.astype("datetime64[ns]").astype(np.int64)
    diffs = np.diff(he_ns)
    regular = bool((diffs == 3_600_000_000_000).all())
    if regular:
        # vectorized fast path, mathematically identical to the search form on a
        # regular grid: j(h) = h - 24.
        c = np.full(g.size, np.nan)
        c[24:] = g[24:] - g[:-24]
        m = np.isfinite(g[24:]) & np.isfinite(g[:-24])
        c[24:][~m] = np.nan
    else:
        c = build_changes(g, he_ns)
    sig = trailing_sigma(c)
    z = np.full(g.size, np.nan)
    m = np.isfinite(c) & np.isfinite(sig) & (sig > 0)
    z[m] = c[m] / sig[m]
    return c, sig, z, regular


def main() -> None:
    log("building dip ledger (vendored replica + how10)...")
    led = add_how_column()
    n = len(led["w"])
    log(f"ledger fills={n}")
    cks = hashlib.sha256(np.round(np.stack(
        [led["w"], led["y09"], led["y10"], led["y11"]]), 9).tobytes()).hexdigest()[:16]
    log(f"checksum={cks} (expect 902c5bbfe8fed3c0)")
    base_sc = P.score_assignment(led["phase"], led["year"], led["w"], led["y10"], led["d10"])
    log(f"base 4-phase-mean sums={[round(r['S'],4) for r in base_sc['per_year']]} sum5y={base_sc['sum5y']:.6f}")
    fidelity = (cks == "902c5bbfe8fed3c0" and abs(base_sc["sum5y"] - 7.718304) < 0.001)
    if not fidelity:
        out = {"fidelity_ok": False, "checksum": cks, "base_sum5y": base_sc["sum5y"]}
        (HERE / "results.json").write_text(json.dumps(out, indent=1))
        log("FIDELITY FAILED - stop and report")
        return
    log("fidelity OK")

    # ---- load GEX series (reuse oc_gex files unchanged) ----
    gbtc = pd.read_parquet(HERE.parent / "oc_gex" / "gex_hourly_BTC.parquet")
    geth = pd.read_parquet(HERE.parent / "oc_gex" / "gex_hourly_ETH.parquet")
    for g in (gbtc, geth):
        g["hour_end"] = pd.to_datetime(g["hour_end"], utc=True)
    gn_b = gbtc["GEXn"].to_numpy(dtype=float)
    gn_e = geth["GEXn"].to_numpy(dtype=float)

    log("building causal z series (BTC)...")
    d_b, sig_b, z_b, reg_b = build_z_for_series(gbtc["hour_end"], gn_b)
    log(f"BTC grid regular={reg_b} z finite={np.isfinite(z_b).sum()}/{len(z_b)}")
    log("building causal z series (ETH)...")
    d_e, sig_e, z_e, reg_e = build_z_for_series(geth["hour_end"], gn_e)
    log(f"ETH grid regular={reg_e} z finite={np.isfinite(z_e).sum()}/{len(z_e)}")

    he_b = gbtc["hour_end"].values.astype("datetime64[ns]").astype(np.int64)
    he_e = geth["hour_end"].values.astype("datetime64[ns]").astype(np.int64)
    bt_min = led["bar_time"].astype(np.int64)
    start_ns = START.value if isinstance(START, pd.Timestamp) else pd.Timestamp(str(START)).value
    bt_ns = start_ns + bt_min * 60_000_000_000

    z_own = np.full(n, np.nan)
    d_own = np.full(n, np.nan)
    sig_own = np.full(n, np.nan)
    for i in range(n):
        t = int(bt_ns[i])
        if int(led["coin"][i]) == 1:
            j = last_hour_before(he_e, t)
            if j >= 0:
                z_own[i], d_own[i], sig_own[i] = z_e[j], d_e[j], sig_e[j]
        else:
            j = last_hour_before(he_b, t)
            if j >= 0:
                z_own[i], d_own[i], sig_own[i] = z_b[j], d_b[j], sig_b[j]
        if (i + 1) % 10000 == 0:
            log(f"join {i+1}/{n}")
    log(f"join done: z finite={np.isfinite(z_own).sum()}/{n}")

    y10 = led["y10"]
    w = led["w"]
    how = led["how10"]
    stopped = np.isin(how, ["stop", "backstop"])
    yr = led["year"]
    dev = yr < 4
    buckets = np.array([assign_bucket(z) for z in z_own], dtype=np.int8)

    # ---- descriptive (dev fills only) ----
    desc = []
    low_worse = []
    spreads = []
    for y in range(4):
        my = (yr == y) & np.isfinite(z_own)
        row: dict = {"year": str(ANCHORS[y].date()), "n": int((yr == y).sum()),
                     "n_z": int(my.sum()),
                     "spearman_z_y10": spearman(z_own[my], y10[my])}
        means, stops, ns, wmeans = [], [], [], []
        for b in range(3):
            mt = my & (buckets == b)
            ns.append(int(mt.sum()))
            means.append(float(np.mean(y10[mt])) if mt.sum() else float("nan"))
            stops.append(float(np.mean(stopped[mt])) if mt.sum() else float("nan"))
            wmeans.append(float(np.sum(w[mt] * y10[mt]) / np.sum(w[mt])) if mt.sum() else float("nan"))
        row["bucket_mean"] = means  # [LOW z<-1, MID, HIGH z>1], unweighted
        row["bucket_stoprate"] = stops
        row["bucket_n"] = ns
        row["bucket_wmean"] = wmeans
        nonlow = my & (buckets >= 1)
        low = my & (buckets == 0)
        spread = (float(np.mean(y10[nonlow])) - float(np.mean(y10[low]))
                  if nonlow.sum() and low.sum() else float("nan"))
        row["spread_nonlow_minus_low"] = spread
        row["stop_nonlow"] = float(np.mean(stopped[nonlow])) if nonlow.sum() else float("nan")
        row["stop_low"] = float(np.mean(stopped[low])) if low.sum() else float("nan")
        ok = bool(means[0] < means[1] and means[0] < means[2]
                  and np.isfinite(spread) and spread > 0.0005)
        row["sign_and_spread_ok"] = ok
        desc.append(row)
        low_worse.append(ok)
        spreads.append(spread)
        log(f"dev {row['year']}: spear={row['spearman_z_y10']:.4f} means={np.round(means,6).tolist()} "
            f"stops={np.round(stops,4).tolist()} n={ns} spread={spread:.6f} ok={ok}")
    candidate = bool(all(low_worse))
    log(f"candidate rule (LOW worst + spread>5bps in 4/4): {low_worse} -> {'TRIGGERED' if candidate else 'NOT triggered'}")

    res: dict = {"fidelity_ok": True, "checksum": cks, "base_sum5y": round(base_sc["sum5y"], 6),
                 "base_mean4": [{"year": str(ANCHORS[y].date()), "S": round(base_sc["per_year"][y]["S"], 6),
                                 "DD": round(base_sc["per_year"][y]["DD"], 6)} for y in range(5)],
                 "feature": {"def": "d=GEXn[i0]-GEXn[i0-24h], sigma=trailing 90d std of 24h changes over 2160 predecessors excl current (min 720), z=d/sigma; LOW z<-1",
                             "grid_regular_BTC": bool(reg_b), "grid_regular_ETH": bool(reg_e),
                             "coin_map": "BTC series for BTC/SOL/BNB/XRP, ETH series for ETH; sigma from same series"},
                 "descriptive_dev": desc, "candidate_4of4": candidate,
                 "join_finite_frac_dev": float(np.isfinite(z_own[dev]).mean())}

    if candidate:
        w1 = w.copy()
        w1[buckets == 0] *= 0.7
        c = float(w1.sum() / w.sum())
        wc = w * c
        log(f"T1 exposure ratio c={c:.6f}")
        sc1 = P.score_assignment(led["phase"], yr, w1, y10, led["d10"])
        scc = P.score_assignment(led["phase"], yr, wc, y10, led["d10"])
        dec1 = P.decide(sc1, base_sc)
        decc = P.decide(scc, base_sc)
        devlegs = {}
        for nm, sc in (("T1", sc1), ("T1c", scc)):
            ps = sum(1 for y in range(4) if sc["per_year"][y]["S"] >= base_sc["per_year"][y]["S"])
            pd_ = sum(1 for y in range(4) if sc["per_year"][y]["DD"] <= base_sc["per_year"][y]["DD"] + DD_TOL)
            dsum4 = float(sum(sc["per_year"][y]["S"] - base_sc["per_year"][y]["S"] for y in range(4)))
            devlegs[nm] = {"years_sum_ge_dev4": ps, "years_dd_ok_dev4": pd_,
                           "dSum_dev4": round(dsum4, 6)}
        res["T1"] = {"rule": "rung weight x0.7 when z<-1 else x1.0 (missing x1.0); threshold -1 fixed pre-outcome",
                     "exposure_c": round(c, 6),
                     "per_year": [{"S": round(r["S"], 6), "DD": round(r["DD"], 6)} for r in sc1["per_year"]],
                     "sum5y": round(sc1["sum5y"], 6), "decide_vs_base": dec1, "dev4": devlegs["T1"]}
        res["T1c_control"] = {"per_year": [{"S": round(r["S"], 6), "DD": round(r["DD"], 6)} for r in scc["per_year"]],
                              "sum5y": round(scc["sum5y"], 6), "decide_vs_base": decc, "dev4": devlegs["T1c"]}
        promising = bool(dec1["promising"] and dec1["dSum5y"] >= GATE_DSUM)
        res["T1_PROMISING_by_dip_gate"] = promising
        log(f"T1 decide={dec1} PROMISING={promising}")
        log(f"T1c decide={decc}")
    else:
        res["T1"] = None

    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    log("wrote results.json")
    (HERE / "tmp").mkdir(exist_ok=True)
    np.savez(HERE / "tmp" / "screen_arrays.npz", z_own=z_own, d_own=d_own, sig_own=sig_own,
             buckets=buckets, y10=y10, stopped=stopped.astype(np.int8), yr=yr, w=w)
    log("done")


if __name__ == "__main__":
    main()
