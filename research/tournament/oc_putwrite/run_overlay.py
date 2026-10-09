"""oc_putwrite stage 2: overlay on G2 + MANUAL, recent year, sensitivities.

Chosen variant from dev4 (tmp/dev4.json) per robust criterion; the most recent
year is scored ONCE here. Reuses run_putwrite helpers (no code duplication).
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "research/diagnostics/r2_decompose5"))
import run_putwrite as RW

V421_RES = RW.ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json"
MANUAL_PKL = ROOT / "research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl"


def base_year(Es, Ms, a0, a1, grid):
    seg = (grid > a0) & (grid <= a1)
    idx = np.where(np.asarray(seg))[0]
    le = np.asarray(grid <= a0)
    b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
    E4 = [Es[s][idx] / b[s] for s in range(4)]
    M4 = [Ms[s][idx] / b[s] for s in range(4)]
    es = np.mean(E4, axis=0)
    ms = np.mean(M4, axis=0)
    es_prev = np.concatenate([[1.0], es[:-1]])
    return idx, es / es_prev, ms / es_prev


def daily_corr(leg_a, leg_b):
    n = (len(leg_a) // 24) * 24
    a = leg_a[:n].reshape(-1, 24).sum(axis=1)
    b = leg_b[:n].reshape(-1, 24).sum(axis=1)
    if np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return round(float(np.corrcoef(a, b)[0, 1]), 3)


def main():
    v388 = RW._load_v388()
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid = pd.date_range(RW.GRID0, g1, freq="1h")

    dev4 = json.loads((HERE / "tmp/dev4.json").read_text())
    # robust criterion on dev4: DD<=20, no losing year; prefer mean>=5 then worst
    cand = {k: v for k, v in dev4["variants"].items()
            if v["dev4_DD"] <= 20 and v["dev4_losing"] == 0}
    pool = cand if cand else {k: v for k, v in dev4["variants"].items() if v["dev4_DD"] <= 20}
    best = max(pool, key=lambda k: (pool[k]["dev4_worst"], pool[k]["dev4_mean"]))
    print("chosen variant:", best, "(qualifying set empty)" if not cand else "(robust winner)")
    exp = json.loads(V421_RES.read_text())["rows"][RW.STRAT]

    runs = pickle.loads(RW.V421.read_bytes())
    Es, Ms = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s][RW.STRAT], RW.GRID0, g1)
        Es.append(e1.to_numpy(dtype=float))
        Ms.append(m1.to_numpy(dtype=float))
    Es = np.stack(Es)
    Ms = np.stack(Ms)

    mcap = pickle.loads(MANUAL_PKL.read_bytes())
    MEs, MMs = [], []
    for s in range(4):
        e1, m1 = v388.hourly(mcap[s]["M5_human"]["run"], RW.GRID0, g1)
        MEs.append(e1.to_numpy(dtype=float))
        MMs.append(m1.to_numpy(dtype=float))
    MEs = np.stack(MEs)
    MMs = np.stack(MMs)

    data = {}
    for coin in RW.GRID_LIST:
        iv_t0, iv_put = RW.load_iv(coin)
        d_ms, d_cl = RW.load_dvol(coin)
        m_ts, m_cl = RW.load_1m(coin)
        data[coin] = {"iv_t0": iv_t0, "iv_put": iv_put, "d_ms": d_ms, "d_cl": d_cl,
                      "m_ts": m_ts, "m_cl": m_cl}
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    gh = {}
    for coin in RW.GRID_LIST:
        d = data[coin]
        px = np.array([RW.px_at(d["m_ts"], d["m_cl"], t)[0] for t in gn])
        ivs = np.array([RW.iv_known(d["iv_t0"], d["iv_put"], t) for t in gn])
        need = ~np.isfinite(ivs)
        if need.any():
            fb = np.array([RW.dvol_known(d["d_ms"], d["d_cl"], t) if nf else np.nan
                           for t, nf in zip(gn, need)])
            ivs[need] = fb[need]
        gh[coin] = {"px": px, "ivsrc": ivs}

    pos = {
        "base": RW.build_positions(grid, gh, data, best),
        "sig90": RW.build_positions(grid, gh, data, best, sigma_sell_mult=0.90 / 0.95),
        "fee2": RW.build_positions(grid, gh, data, best, fee_mult=2.0),
    }
    # NOTE: base uses sigma_sell = 0.95*sigma_e; sens row "0.90 haircut" needs
    # 0.90*sigma_e, hence mult 0.90/0.95 relative to base code path.

    slices = RW.year_slices(grid)
    out = {"chosen": best, "qualifying_empty": not bool(cand),
           "standalone": {}, "overlay_g2": {}, "overlay_manual": {},
           "sensitivity_dev4": {}, "meta": dev4["meta"]}

    # ---- standalone: chosen variant all 5 years (recent scored once, here) ----
    for key in ("base",):
        yrs = []
        for ay, idx in slices:
            r = RW.simulate_year(grid, idx, pos[key], standalone=True)
            yrs.append({"anchor": ay, "R": r["R"], "DD": r["DD"], "end": r["end"],
                        "trades": r["n"], "win": r["win"], "tp": r["tp"], "sl": r["sl"],
                        "expiry": r["expiry"], "worst_week": r["worst_week"],
                        "prem_yield_pct": r["prem_yield"]})
            if ay == "2025-09-24":
                pd.DataFrame([{**t, "anchor": ay} for t in r["trades"]]).to_parquet(
                    HERE / f"trades_{best}_recent.parquet")
        out["standalone"][best] = yrs

    # ---- sensitivities on dev4 only ----
    for key in ("sig90", "fee2"):
        yrs = []
        for ay, idx in slices[:4]:
            r = RW.simulate_year(grid, idx, pos[key], standalone=True)
            yrs.append({"anchor": ay, "R": r["R"], "DD": r["DD"], "end": r["end"],
                        "trades": r["n"], "win": r["win"]})
        R4 = float(np.prod([1 + y["R"] / 100 for y in yrs]) ** (1 / 4) - 1) * 100
        out["sensitivity_dev4"][key] = {"years": yrs, "dev4_mean": round(R4, 3),
                                        "dev4_worst": min(y["R"] for y in yrs),
                                        "dev4_DD": max(y["DD"] for y in yrs)}

    # ---- overlay on G2 ----
    for f in [0.0] + RW.F_OVERLAY:
        yrs = []
        for yi, (ay, idx) in enumerate(slices):
            _, g, hh = base_year(Es, Ms, RW.ANCH[yi], RW.ANCH[yi] + RW.YEAR, grid)
            r = RW.simulate_year(grid, idx, pos["base"], g=g, hh=hh, f=f, standalone=False)
            yrs.append({"anchor": ay, "R": r["R"], "DD": r["DD"], "end": r["end"],
                        "corr_daily_sleeve_g2": daily_corr(r["leg_sleeve"], r["leg_g2"])})
        R5 = float(np.prod([1 + y["R"] / 100 for y in yrs]) ** (1 / 5) - 1) * 100
        row = {"years": yrs, "R": round(R5, 3), "W": min(y["R"] for y in yrs),
               "DD": max(y["DD"] for y in yrs), "losing": sum(y["R"] < 0 for y in yrs)}
        out["overlay_g2"][f"G2_put_f{f}"] = row
        print(f"f={f}", row)
    # overlay-loop validation: f=0 must reproduce v421_result G2 to the digit
    z = out["overlay_g2"]["G2_put_f0.0"]
    assert [y["R"] for y in z["years"]] == [r for r, _ in exp["years"]], z
    assert [y["DD"] for y in z["years"]] == [d for _, d in exp["years"]], z
    assert (z["R"], z["W"], z["DD"]) == (exp["R"], exp["W"], exp["DD"]), (z, exp)
    print("overlay f=0 validation OK: reproduces v421_result G2 to the digit")

    # ---- continuous full-path pass (v421 convention) ----
    Etot = Es.mean(axis=0)
    Mtot = Ms.mean(axis=0)
    full = {}
    for f in [0.0] + RW.F_OVERLAY:
        n = len(grid)
        gg = np.empty(n)
        hhq = np.empty(n)
        gg[0], hhq[0] = 1.0, 1.0
        gg[1:] = Etot[1:] / Etot[:-1]
        hhq[1:] = Mtot[1:] / Etot[:-1]
        idx = np.arange(n)
        # keep only cycles expiring within the grid
        kept = [p for p in pos["base"]
                if not p.get("skip") and p["entry_step"] >= 0 and p["expiry_t"] <= gn[-1]]
        r = RW.simulate_year(grid, idx, kept, g=gg, hh=hhq, f=f, standalone=False)
        pk = np.maximum.accumulate(r["E"])
        dd_m = float(np.max(1 - r["M"] / pk)) * 100
        dd_c = float(np.max(1 - r["E"] / pk)) * 100
        full[f"G2_put_f{f}"] = {"marked": round(dd_m, 2), "close": round(dd_c, 2),
                                "full": round(max(dd_m, dd_c), 2)}
    assert full["G2_put_f0.0"]["full"] == exp["full_path_dd"], full
    print("full-path f=0 validation OK:", full["G2_put_f0.0"])
    out["overlay_g2_full_path_dd"] = full
    out["overlay_g2"]["G2_put_f0.0"]["full_path_dd"] = full["G2_put_f0.0"]
    for f in RW.F_OVERLAY:
        out["overlay_g2"][f"G2_put_f{f}"]["full_path_dd"] = full[f"G2_put_f{f}"]

    # ---- worst 5 combo weeks (Friday 09:00 -> +7d) on continuous f=0.25 path ----
    n = len(grid)
    gg = np.empty(n)
    gg[0] = 1.0
    gg[1:] = Etot[1:] / Etot[:-1]
    hhq = np.empty(n)
    hhq[0] = 1.0
    hhq[1:] = Mtot[1:] / Etot[:-1]
    kept = [p for p in pos["base"]
            if not p.get("skip") and p["entry_step"] >= 0 and p["expiry_t"] <= gn[-1]]
    rc = RW.simulate_year(grid, np.arange(n), kept, g=gg, hh=hhq, f=0.25, standalone=False)
    fri09 = [i for i, t in enumerate(grid)
             if t.weekday() == 4 and t.hour == 9 and gn[i] + 7 * 86400_000_000_000 <= gn[-1]]
    wk = []
    for i in fri09:
        j = i + 7 * 24
        wk.append((str(grid[i].date()), round(float(rc["E"][j] / rc["E"][i] - 1) * 100, 3)))
    wk.sort(key=lambda x: x[1])
    out["combo_worst5_weeks_f025"] = wk[:5]
    print("worst5 combo weeks:", wk[:5])

    # ---- MANUAL overlay (yearly reset, labelled) ----
    for f in [0.0] + RW.F_OVERLAY:
        yrs = []
        for yi, (ay, idx) in enumerate(slices):
            _, g, hh = base_year(MEs, MMs, RW.ANCH[yi], RW.ANCH[yi] + RW.YEAR, grid)
            r = RW.simulate_year(grid, idx, pos["base"], g=g, hh=hh, f=f, standalone=False)
            yrs.append({"anchor": ay, "R": r["R"], "DD": r["DD"], "end": r["end"]})
        R5 = float(np.prod([1 + y["R"] / 100 for y in yrs]) ** (1 / 5) - 1) * 100
        out["overlay_manual"][f"MANUAL_put_f{f}"] = {
            "years": yrs, "R": round(R5, 3), "W": min(y["R"] for y in yrs),
            "DD": max(y["DD"] for y in yrs)}
        print(f"MANUAL f={f}", out["overlay_manual"][f"MANUAL_put_f{f}"])

    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("wrote", HERE / "results.json")


if __name__ == "__main__":
    main()
