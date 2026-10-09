"""oc_governor descriptive (Task 1): G2 baseline reproduction + per-phase governor stats.

Light (4h data only, no 1m, no engine rerun). Run:
  .venv/Scripts/python.exe research/tournament/oc_governor/compute_descriptive.py
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
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"
STRAT = "R2B1D17BFG2"
GZ, GW = 0.20, 0.10
PD = 6
WIN = 90 * PD  # 540 bars trailing peak
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR = pd.Timedelta(days=365)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def recompute_g(eq: np.ndarray) -> np.ndarray:
    """Audited governor formula on one phase sub-account eq path (lagged 2 bars)."""
    n = len(eq)
    g = np.ones(n)
    for i in range(2, n):
        j = i - 2
        lo = max(0, j - WIN + 1)
        peak = float(np.max(eq[lo:j + 1]))
        dd = 1.0 - float(eq[j]) / peak if peak > 0 else 0.0
        g[i] = float(np.clip((GZ - dd) / GW, 0.0, 1.0))
    return g


def main() -> None:
    rm = _load("reset_for_govdesc", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    v388 = _load("v388_for_govdesc", RD / "v388/v388_bot_stop_distance.py")
    runs = pickle.loads(V421.read_bytes())
    assert set(runs) == {0, 1, 2, 3}, sorted(runs)
    assert set(runs[0]) >= {STRAT}, sorted(runs[0])

    # ---- 1. reproduce G2 baseline EXACTLY (common-header gate) ----
    exp = json.loads(V421_RES.read_text())["rows"][STRAT]
    got_years = [rm.year_reset(runs, STRAT, y) for y in range(5)]
    assert [(m["R"], m["DD"]) for m in got_years] == [(r, d) for r, d in exp["years"]], (got_years, exp["years"])
    geo5 = float(np.prod([1 + m["R"] / 100 for m in got_years]) ** (1 / 5) - 1) * 100
    assert round(geo5, 3) == exp["R"], (geo5, exp["R"])
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(runs, STRAT, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    assert full == exp["full_path_dd"], (full, exp["full_path_dd"])
    print(f"G2 baseline reproduction OK: R={exp['R']} W={exp['W']} DD={exp['DD']} full={full}", flush=True)

    # ---- 2. live governor check (read-only source inspection) ----
    ftp = (ROOT / "scripts/forward_trade_phase.py").read_text(encoding="utf-8")
    mph = (ROOT / "backend/multiphase.py").read_text(encoding="utf-8")
    eu_src = (RD / "engine_user/engine_user.py").read_text(encoding="utf-8")
    assert "eu.simulate(books, opens.reindex(grid), prep, trade=trade" in ftp, "live per-phase simulate call moved?"
    assert "0.25 * growth[s] / mix" in mph or "0.25 * growth" in mph, "merge capital formula moved?"
    assert "gz, gw = (0.20, 0.10) if gov is None else gov" in eu_src
    live_uses_per_phase = (
        "eu.simulate(books, opens.reindex(grid), prep, trade=trade" in ftp
        and "mix = sum(growth.values()) / len(phases)" in mph
        and "cap = {s: 0.25 * growth[s] / mix" in mph
    )
    print(f"LIVE governor check: per-phase sub-account equity = {live_uses_per_phase}", flush=True)

    # ---- 3. per-phase g series recomputed from stored eq ----
    phases = {}
    for s in range(4):
        r = runs[s][STRAT]
        t = pd.to_datetime(r["t"], utc=True)
        eq = np.asarray(r["eq"], float)
        g = recompute_g(eq)
        phases[s] = dict(t=t, eq=eq, g=g)
        print(f"shift {s}: bars {len(eq)}, mean_g {g.mean():.4f}, "
              f"frac<1 {(g < 1 - 1e-12).mean():.4f}, frac==0 {(g <= 1e-12).mean():.4f}", flush=True)

    # ---- 4. per phase x year table ----
    def longest_zero(gm: np.ndarray):
        best, cur, best_s, cur_s = 0, 0, None, None
        for k, v in enumerate(gm):
            if v <= 1e-12:
                if cur == 0:
                    cur_s = k
                cur += 1
                if cur > best:
                    best, best_s = cur, cur_s
            else:
                cur = 0
        return best, best_s

    table = []
    for s in range(4):
        t, eq, g = phases[s]["t"], phases[s]["eq"], phases[s]["g"]
        for yi, a0 in enumerate(ANCH):
            a1 = a0 + YEAR
            m = (t > a0) & (t <= a1)
            gm, tm, em = g[m], t[m], eq[m]
            n = int(m.sum())
            f_lt1 = float((gm < 1 - 1e-12).mean()) if n else 0.0
            f_eq0 = float((gm <= 1e-12).mean()) if n else 0.0
            lz, lz_s = longest_zero(gm)
            if lz:
                zs, ze = tm[lz_s], tm[lz_s + lz - 1]
                zspan = f"{zs.date()}..{ze.date()}"
            else:
                zspan = None
            end = float(em[-1] / em[0]) if n and em[0] else float("nan")
            R = round(100 * (end ** (1 / 12) - 1), 3) if n else None
            table.append(dict(shift=s, anchor=str(a0.date()), n=n,
                              frac_g_lt1=round(f_lt1, 4), frac_g_eq0=round(f_eq0, 4),
                              mean_g=round(float(gm.mean()), 4) if n else None,
                              longest_g0=lz, longest_g0_span=zspan,
                              phase_end_factor=round(end, 4) if n else None,
                              phase_R=round(R, 3) if R is not None else None))
            print(f"s{s} Y{a0.date()}: n={n} <1={f_lt1:.3f} =0={f_eq0:.3f} "
                  f"mean={gm.mean() if n else float('nan'):.3f} max0={lz} {zspan} Rend={end:.3f}", flush=True)

    # ---- 5. LABELLED missed-P&L proxy (vectorised book only, standard grid) ----
    eu = _load("eu_govdesc", RD / "engine_user/engine_user.py")
    fw = _load("fw_govdesc", ROOT / "scripts/forward_v205.py")
    books154, opens_std = eu.er.v154_books()
    cols = list(books154.columns)
    std = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    btc = opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    o = opens_std[cols].reindex(books154.index)
    r = (o.shift(-1) / o - 1)
    b = (sb * r).sum(axis=1)  # book proxy bar return (NO vol-scale, NO governor, NO costs)
    # shift-0 alignment is exact (phase-0 grid == standard grid, t = idx+8h)
    t0 = phases[0]["t"]
    idx0 = books154.index
    # map equity-time t0 (idx+8h) -> decision idx = t0 - 8h
    dec0 = (t0 - pd.Timedelta(hours=8))
    bb = b.reindex(dec0).to_numpy(float)
    g0 = phases[0]["g"]
    proxy = []
    for yi, a0 in enumerate(ANCH):
        a1 = a0 + YEAR
        m = (t0 > a0) & (t0 <= a1)
        bb_y, g_y = bb[m], g0[m]
        ok = np.isfinite(bb_y)
        missed = float(np.sum((1 - g_y[ok]) * bb_y[ok]))  # linear approx, labelled
        earned = float(np.sum(bb_y[ok]))
        proxy.append(dict(anchor=str(a0.date()), bars=int(ok.sum()),
                          proxy_earned=round(earned, 4),
                          proxy_missed_g0=round(missed, 4),
                          note="APPROXIMATION: sum((1-g)*b); no vol-scale/governor feedback, no costs/fills, no dip sleeve"))
        print(f"proxy s0 Y{a0.date()}: earned {earned:+.4f} missed {missed:+.4f} (approx)", flush=True)
    # per-phase scaling note: other phases share the same standard-grid b ffill-approximated;
    # report their sum((1-g)) mass as the relative exposure to the same proxy
    for s in range(1, 4):
        pass  # g stats in table already give (1-g) mass per phase-year

    out = dict(
        meta=dict(strat=STRAT, src="v421/v421_runs.pkl", gov="(0.20, 0.10), 90d peak, lag 2 bars",
                  g_formula="g[i]=clip((0.20-(1-eq[j]/max(eq[j-539..j])))/0.10), j=i-2; g=1 for i<2",
                  year_window="equity time t in (A, A+365d]",
                  proxy="APPROXIMATION: standard-grid vectorised book proxy (oc_bookattrib style, no vol-scale/governor/costs/fills, no dip); "
                        "shift-0 alignment exact, other phases same-proxy illustration only",
                  live_governor="YES: live (forward_trade_phase.build per-phase eu.simulate + multiphase.merge mean of sub-book growths) "
                                "also uses per-phase sub-account equity; pooled mix never feeds back into g"),
        g2_reproduction=dict(R=exp["R"], W=exp["W"], DD=exp["DD"], full_path_dd=exp["full_path_dd"],
                             years=[[rr, dd] for rr, dd in exp["years"]]),
        live_uses_per_phase_subaccount=bool(live_uses_per_phase),
        per_phase_year=table,
        book_proxy_shift0_approx=proxy,
    )
    (HERE / "tmp" / "descriptive.json").write_text(json.dumps(out, indent=1, default=str))
    print("wrote tmp/descriptive.json", flush=True)


if __name__ == "__main__":
    main()
