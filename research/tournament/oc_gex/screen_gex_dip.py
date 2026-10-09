"""oc_gex screen: join GEXn to the G2 dip replica, descriptive + conditional T1.

Pre-registered in PLAN.md. Steps:
  0. fidelity: exact dip replica base (checksum 902c5bbfe8fed3c0, sum5y 7.718).
  1. sanity (no dip outcomes; vol corr dev-only).
  2. descriptive join on dev years (Spearman, tercile means, stop-out rates).
  3. conditional T1 tilt (only if top>bottom in >=3/4 dev years) + T1c control,
     dip gate (PROMISING legs + dSum5y>=+0.273) + dev4 view; year 5 scored once.
  4. results.json + REPORT.md.

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_gex_screen \\
    --min-free-gb 2.0 -- .venv/Scripts/python.exe \\
    research/tournament/oc_gex/screen_gex_dip.py
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
from research.tournament.oc_gex.gex_lib import assign_tercile, last_hour_before, tercile_cuts

t0 = time.time()


def log(msg: str) -> None:
    print(f"[oc_gex_screen {time.time()-t0:8.1f}s] {msg}", flush=True)


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

# --------------------------------------------------------------------------
# build_base vendored from compute_placebo_dip.py with ONE added column:
# how10 (exit reason of the y1.0 leg: tp/stop/backstop/time). All outcome
# math is byte-identical; checksum on (w,y09,y10,y11) must match
# 902c5bbfe8fed3c0.
# --------------------------------------------------------------------------
def add_how_column() -> dict:
    """Re-run of build_base that also records how10.

    Implemented by re-executing the same loop via a local copy of the
    (coin, phase, bar, rung) walk would double the 1m cost; instead we rely
    on P.build_base for (w,y,d) and recover how10 from a second identical
    pass. To keep it exact AND cheap we monkeypatch nothing: we replicate
    the loop here (same code as P.build_base, plus how10). Fidelity is
    proven by checksum equality on the shared columns.
    """
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

    # ---- load GEX series ----
    gbtc = pd.read_parquet(HERE / "gex_hourly_BTC.parquet")
    geth = pd.read_parquet(HERE / "gex_hourly_ETH.parquet")
    for g in (gbtc, geth):
        g["hour_end"] = pd.to_datetime(g["hour_end"], utc=True)
    he_b = gbtc["hour_end"].values.astype("datetime64[ns]").astype(np.int64)
    he_e = geth["hour_end"].values.astype("datetime64[ns]").astype(np.int64)
    gn_b = gbtc["GEXn"].to_numpy(dtype=float)
    gn_e = geth["GEXn"].to_numpy(dtype=float)
    s_b = gbtc["S"].to_numpy(dtype=float)
    s_e = geth["S"].to_numpy(dtype=float)
    epoch_ns = pd.Timestamp("1970-01-01", tz="UTC").value
    bt_min = led["bar_time"].astype(np.int64)  # minutes since START
    start_ns = pd.Timestamp(str(START)).value if not isinstance(START, pd.Timestamp) else START.value
    bt_ns = start_ns + bt_min * 60_000_000_000

    g_own = np.full(n, np.nan)
    g_btc = np.full(n, np.nan)
    for i in range(n):
        t = int(bt_ns[i])
        jb = last_hour_before(he_b, t)
        g_btc[i] = gn_b[jb] if jb >= 0 else np.nan
        if int(led["coin"][i]) == 1:
            je = last_hour_before(he_e, t)
            g_own[i] = gn_e[je] if je >= 0 else np.nan
        else:
            g_own[i] = g_btc[i]
        if (i + 1) % 10000 == 0:
            log(f"join {i+1}/{n}")
    log(f"join done: own finite={np.isfinite(g_own).sum()}/{n} btc finite={np.isfinite(g_btc).sum()}/{n}")

    y10 = led["y10"]
    how = led["how10"]
    stopped = np.isin(how, ["stop", "backstop"])
    yr = led["year"]
    dev = yr < 4

    # ---- sanity (no dip outcomes; vol corr dev-only) ----
    sanity = {}
    for name, gdf, ss in (("BTC", gbtc, s_b), ("ETH", geth, s_e)):
        xx = gdf[["hour_end", "GEXn"]].copy()
        xx["date"] = xx["hour_end"].dt.date
        sanity[name] = {"median_GEXn_all": float(np.nanmedian(xx["GEXn"]))}
    # expiry Fridays (Deribit monthlies/quarterlies: last Friday 08:00 UTC)
    fris = pd.date_range("2021-04-01", "2026-09-23", freq="W-FRI", tz="UTC").date
    friset = set(fris)
    for name, gdf in (("BTC", gbtc), ("ETH", geth)):
        dd = gdf["hour_end"].dt.date
        on_exp = gdf["hour_end"].dt.hour.isin([0, 1, 2, 3, 4, 5, 6, 7]) & dd.isin(friset)
        sanity[name]["median_GEXn_expiryFri_00_08"] = float(np.nanmedian(gdf.loc[on_exp, "GEXn"]))
        sanity[name]["median_GEXn_other"] = float(np.nanmedian(gdf.loc[~on_exp, "GEXn"]))
        for cm in ("2022-05", "2022-06", "2022-11"):
            m = gdf["hour_end"].dt.strftime("%Y-%m") == cm
            sanity[name][f"median_GEXn_{cm}"] = float(np.nanmedian(gdf.loc[m, "GEXn"]))
    # realised-vol mechanism check, DEV hourly rows only
    dev_lo = pd.Timestamp("2021-09-24", tz="UTC")
    dev_hi = pd.Timestamp("2025-09-23 23:00", tz="UTC")
    volcorr = {}
    for name, gdf, ss in (("BTC", gbtc, s_b), ("ETH", geth, s_e)):
        m = (gdf["hour_end"] >= dev_lo) & (gdf["hour_end"] <= dev_hi)
        lr = np.full(len(gdf), np.nan)
        lr[1:] = np.log(ss[1:] / ss[:-1])
        v24 = np.full(len(gdf), np.nan)
        for j in range(len(gdf) - 24):
            w = lr[j + 1:j + 25]
            if np.isfinite(w).sum() >= 20:
                v24[j] = float(np.nanstd(w, ddof=1))
        gm = gdf["GEXn"].to_numpy(dtype=float)
        ok = m.to_numpy() & np.isfinite(gm) & np.isfinite(v24)
        per_y = {}
        for y in range(4):
            lo, hi = ANCHORS[y], ANCHORS[y + 1]
            my = ok & (gdf["hour_end"] >= lo).to_numpy() & (gdf["hour_end"] < hi).to_numpy()
            per_y[str(lo.date())] = {"spearman": spearman(gm[my], v24[my]), "n": int(my.sum())}
        per_y["dev_pooled"] = {"spearman": spearman(gm[ok], v24[ok]), "n": int(ok.sum())}
        volcorr[name] = per_y
    log(f"sanity={json.dumps(sanity)}")
    log(f"volcorr={json.dumps(volcorr)}")

    # ---- descriptive (dev fills only) ----
    desc = []
    signs = []
    for y in range(4):
        my = (yr == y) & np.isfinite(g_own)
        row = {"year": str(ANCHORS[y].date()), "n": int((yr == y).sum()),
               "n_g": int(my.sum()),
               "spearman": spearman(g_own[my], y10[my])}
        lo, hi = tercile_cuts(g_own[my])
        row["cut_lo"], row["cut_hi"] = lo, hi
        means, stops, ns = [], [], []
        for t in range(3):
            if t == 0:
                mt = my & (g_own <= lo)
            elif t == 2:
                mt = my & (g_own >= hi)
            else:
                mt = my & (g_own > lo) & (g_own < hi)
            ns.append(int(mt.sum()))
            means.append(float(np.mean(y10[mt])) if mt.sum() else float("nan"))
            stops.append(float(np.mean(stopped[mt])) if mt.sum() else float("nan"))
        row["tercile_mean"] = means
        row["tercile_stoprate"] = stops
        row["tercile_n"] = ns
        row["top_minus_bottom"] = means[2] - means[0]
        desc.append(row)
        signs.append(bool(means[2] > means[0]))
        log(f"dev {row['year']}: spear={row['spearman']:.4f} means={np.round(means,6).tolist()} "
            f"stops={np.round(stops,4).tolist()} n={ns}")
    n_pos = int(sum(signs))
    trigger = n_pos >= 3
    log(f"sign as hypothesised in {n_pos}/4 dev years -> T1 {'TRIGGERED' if trigger else 'NOT triggered'}")

    res = {"fidelity_ok": True, "checksum": cks, "base_sum5y": round(base_sc["sum5y"], 6),
           "base_mean4": [{"year": str(ANCHORS[y].date()), "S": round(base_sc["per_year"][y]["S"], 6),
                           "DD": round(base_sc["per_year"][y]["DD"], 6)} for y in range(5)],
           "sanity": sanity, "volcorr_GEXn_vs_24hvol_devonly": volcorr,
           "descriptive_dev": desc, "n_sign_years": n_pos, "T1_triggered": bool(trigger),
           "join_finite_frac": float(np.isfinite(g_own[dev]).mean())}

    if trigger:
        # ---- T1: per-anchor cuts on BTC-mapped GEXn, rows with bar open < anchor-7d ----
        cuts = {}
        for Y in range(5):
            a = ANCHORS[Y] if Y < 4 else YEAR_END
            tr = (bt_ns < (pd.Timestamp(a).value - 7 * 86400_000_000_000)) & np.isfinite(g_btc)
            lo, hi = tercile_cuts(g_btc[tr])
            cuts[Y] = (lo, hi)
            log(f"cuts Y{Y} ({str(a.date()) if Y<4 else '2025-09-24+1y'}): ntrain={int(tr.sum())} lo={lo:.4g} hi={hi:.4g}")
        w1 = led["w"].copy()
        for i in range(n):
            Y = int(yr[i])
            lo, hi = cuts[Y]
            t = assign_tercile(g_btc[i], lo, hi)
            if t == 2:
                w1[i] *= 1.25
            elif t == 0:
                w1[i] *= 0.75
        c = float(w1.sum() / led["w"].sum())
        wc = led["w"] * c
        log(f"T1 exposure ratio c={c:.6f}")
        sc1 = P.score_assignment(led["phase"], yr, w1, y10, led["d10"])
        scc = P.score_assignment(led["phase"], yr, wc, y10, led["d10"])
        dec1 = P.decide(sc1, base_sc)
        decc = P.decide(scc, base_sc)
        # dev4 view
        devlegs = {}
        for nm, sc in (("T1", sc1), ("T1c", scc)):
            ps = sum(1 for y in range(4) if sc["per_year"][y]["S"] >= base_sc["per_year"][y]["S"])
            pd_ = sum(1 for y in range(4) if sc["per_year"][y]["DD"] <= base_sc["per_year"][y]["DD"] + DD_TOL)
            dsum4 = float(sum(sc["per_year"][y]["S"] - base_sc["per_year"][y]["S"] for y in range(4)))
            devlegs[nm] = {"years_sum_ge_dev4": ps, "years_dd_ok_dev4": pd_,
                           "dSum_dev4": round(dsum4, 6)}
        res["T1"] = {"cuts": {str(k): [v[0], v[1]] for k, v in cuts.items()},
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
    # stash arrays for REPORT step
    np.savez(HERE / "tmp" / "screen_arrays.npz", g_own=g_own, g_btc=g_btc,
             y10=y10, stopped=stopped.astype(np.int8), yr=yr, w=led["w"])
    log("done")


if __name__ == "__main__":
    main()
