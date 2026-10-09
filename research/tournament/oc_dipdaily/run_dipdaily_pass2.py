"""oc_dipdaily pass2: standalone + combined accounting, overlay, report tables.

Imported by run_dipdaily.py --step pass2. Frozen methods per PLAN.md 2026-10-08.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import dipdaily_core as C
from run_dipdaily import (ANCH, DAYNS, G1, MAJORS, PRE_COINS, PRE_LEGS,
                          STRAT, TMP, VARIANTS, YEAR)

GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")


def _fee_gross(sub: pd.DataFrame, Eb: dict, size: float):
    """Total fee legs, funding, and positive-trade gross for a record set."""
    if len(sub) == 0:
        return 0.0, 0.0, 0.0
    N = size * np.array([Eb[bb] for bb in sub["day_ns"]])
    how = sub["how"].to_numpy()
    fee_leg = np.where(how == "tp", 2 * C.MAKER, C.MAKER + C.TAKER)
    fees = float(np.sum(fee_leg * N))
    fund = float(np.sum(sub["nst"].to_numpy() * C.FUND * N))
    ratio = sub["exit"].to_numpy() / sub["fill"].to_numpy()
    gross_pos = float(np.sum(np.where(ratio > 1, (ratio - 1) * N, 0.0)))
    return fees, fund, gross_pos


def _summarise(sub: pd.DataFrame, Eb: dict, size: float, Eq: float, Epath: np.ndarray,
               norm_days: float | None):
    n = int(len(sub))
    fees, fund, gross_pos = _fee_gross(sub, Eb, size)
    wr = round(float(np.mean(sub["ret"].to_numpy() > 0)), 4) if n else None
    return {"R": round(C.pct_per_month(Eq, norm_days), 3),
            "DD": round(C.max_dd(Epath), 2),
            "end": round(float(Eq), 6), "trades": n, "win": wr,
            "fees": round(fees, 6), "funding": round(fund, 6),
            "fee_share": round(fees / max(gross_pos, 1e-12), 4) if n else None}


def _run_year_days(rec: pd.DataFrame, size: float, lo_ns: int, hi_ns: int,
                   norm_days: float | None):
    """Per-day-entry reset accounting over days with day_ns in [lo, hi)."""
    sub = rec[(rec["day_ns"] >= lo_ns) & (rec["day_ns"] < hi_ns)]
    days = np.sort(sub["day_ns"].unique()) if len(sub) else np.array([], dtype=np.int64)
    Eb, Eq, Epath = {}, 1.0, []
    for b in days:
        Eb[int(b)] = Eq
        m = (sub["exit_ns"].to_numpy() >= b) & (sub["exit_ns"].to_numpy() < int(b) + DAYNS)
        grp = sub[m]
        if len(grp):
            N = size * np.array([Eb.get(bb, Eq) for bb in grp["day_ns"]])
            Eq = Eq + float(np.sum(N * grp["ret"].to_numpy()))
        Epath.append(Eq)
    s = _summarise(sub, Eb, size, Eq, np.array(Epath), norm_days)
    return s, days


def step_pass2() -> None:
    z = np.load(TMP / "g2_hourly.npz")
    grid = pd.to_datetime(z["grid"], utc=True)
    Es, Ms, E, M = z["Es"], z["Ms"], z["E"], z["M"]
    gn = z["grid"]
    dfs = [pd.read_parquet(TMP / f"rec_{c}.parquet") for c in MAJORS]
    rec = pd.concat(dfs, ignore_index=True)
    del dfs
    print(f"pass2: {len(rec)} main rung records", flush=True)
    n_drop = int((~np.isfinite(rec["ret"].to_numpy())).sum())
    rec = rec[np.isfinite(rec["ret"].to_numpy())].copy()
    print(f"pass2: dropped {n_drop} non-finite-ret records", flush=True)
    rec = rec.sort_values(["day_ns", "coin", "k"]).reset_index(drop=True)
    pre = pd.concat([pd.read_parquet(TMP / f"rec_pre_{c}.parquet") for c in PRE_COINS],
                    ignore_index=True)
    n_drop_pre = int((~np.isfinite(pre["ret"].to_numpy())).sum())
    pre = pre[np.isfinite(pre["ret"].to_numpy())].copy()
    pre = pre.sort_values(["day_ns", "coin", "k"]).reset_index(drop=True)
    print(f"pass2: {len(pre)} pre-sample records (dropped {n_drop_pre})", flush=True)

    # ---- standalone main: per-year reset ----
    out_sa, cont = {}, {}
    for v in VARIANTS:
        size = C.SIZE[v]
        years = []
        for y in range(5):
            a0, a1 = ANCH[y].value, (ANCH[y] + YEAR).value
            s, _ = _run_year_days(rec, size, a0, a1, None)
            s["anchor"] = str(ANCH[y].date())
            years.append(s)
        R4 = round(float(np.prod([1 + years[y]["R"] / 100 for y in range(4)])
                         ** (1 / 4) - 1) * 100, 3)
        R5 = round(float(np.prod([1 + y["R"] / 100 for y in years])
                         ** (1 / 5) - 1) * 100, 3)
        out_sa[v] = {"years": years,
                     "dev4": {"R": R4, "W": min(y["R"] for y in years[:4]),
                              "DD": max(y["DD"] for y in years[:4]),
                              "losing": sum(y["R"] < 0 for y in years[:4])},
                     "R5": R5, "W5": min(y["R"] for y in years),
                     "DD5": max(y["DD"] for y in years),
                     "losing5": sum(y["R"] < 0 for y in years)}
        # continuous (no reset) for daily correlation
        days = np.sort(rec["day_ns"].unique())
        Eq, Eb, Eser = 1.0, {}, []
        for b in days:
            Eb[int(b)] = Eq
            m = (rec["exit_ns"].to_numpy() >= b) & (rec["exit_ns"].to_numpy() < int(b) + DAYNS)
            grp = rec[m]
            if len(grp):
                N = size * np.array([Eb.get(bb, Eq) for bb in grp["day_ns"]])
                Eq = Eq + float(np.sum(N * grp["ret"].to_numpy()))
            Eser.append(Eq)
        cont[v] = (days, np.array(Eser))

    # ---- standalone pre-sample legs ----
    out_pre = {}
    for v in VARIANTS:
        size = C.SIZE[v]
        legs = []
        for name, l0, l1, ndays in PRE_LEGS:
            norm = None if ndays == 365 else float(ndays)
            s, _ = _run_year_days(pre, size, l0.value, l1.value, norm)
            s["leg"] = name
            legs.append(s)
        out_pre[v] = {"legs": legs}

    # ---- combined overlay on TOTAL equity (frozen UTA method) ----
    def run_comb(v: str | None):
        rows = []
        for y, a0 in enumerate(ANCH):
            a1 = a0 + YEAR
            seg = (grid > a0) & (grid <= a1)
            idx = np.where(np.asarray(seg))[0]
            le = gn <= a0.value
            b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
            E4 = [Es[s][idx] / b[s] for s in range(4)]
            M4 = [Ms[s][idx] / b[s] for s in range(4)]
            es = np.mean(E4, axis=0)
            ms = np.mean(M4, axis=0)
            if v is None:
                A_arr, M_arr = es, ms
                skips = 0
            else:
                size = C.SIZE[v]
                sub = rec[(rec["day_ns"] > a0.value)
                          & (rec["day_ns"] <= (a0 + YEAR).value)]
                es_prev = np.concatenate([[1.0], es[:-1]])
                g = es / es_prev
                hh = ms / es_prev
                gh = grid[idx]
                A_prev = 1.0
                A_arr = np.empty(len(idx))
                M_arr = np.empty(len(idx))
                A_at: dict = {}
                skipped: set = set()
                skips = 0
                for i, t in enumerate(gh):
                    tns = t.value
                    m_entry = (sub["day_ns"].to_numpy() == tns)
                    if m_entry.any():
                        grp = sub[m_entry].sort_values(["f", "coin", "k"])
                        new_open: list = []
                        for rix, r in grp.iterrows():
                            N = size * A_prev
                            open_now = sum(N0 for xo, N0 in new_open
                                           if xo > r["f"])
                            if (open_now + N) / A_prev + 1.0 > 2.0:
                                skipped.add(rix)
                                skips += 1
                                continue
                            new_open.append((r["x"], N))
                    dU = 0.0
                    exn = sub["exit_ns"].to_numpy()
                    m_exit = (exn >= tns) & (exn < tns + 3_600_000_000_000)
                    if m_exit.any():
                        for rix, r in sub[m_exit].iterrows():
                            if rix in skipped:
                                continue
                            NA = size * A_at.get(r["day_ns"], A_prev)
                            dU += NA * r["ret"]
                    A_arr[i] = A_prev * g[i] + dU
                    M_arr[i] = A_prev * hh[i] + dU
                    A_at[tns] = A_prev
                    A_prev = A_arr[i]
            pk = np.maximum.accumulate(A_arr)
            R = round(100 * float(A_arr[-1] ** (1 / 12) - 1), 3)
            DD = round(100 * float(np.max(1 - M_arr / pk)), 2)
            rows.append({"anchor": str(a0.date()), "R": R, "DD": DD,
                         "end": round(float(A_arr[-1]), 6),
                         "skips": skips if v else 0})
        R4 = round(float(np.prod([1 + r["R"] / 100 for r in rows[:4]])
                         ** (1 / 4) - 1) * 100, 3)
        R5 = round(float(np.prod([1 + r["R"] / 100 for r in rows])
                         ** (1 / 5) - 1) * 100, 3)
        return {"years": rows,
                "dev4": {"R": R4, "W": min(r["R"] for r in rows[:4]),
                         "DD": max(r["DD"] for r in rows[:4]),
                         "losing": sum(r["R"] < 0 for r in rows[:4])},
                "R5": R5, "W5": min(r["R"] for r in rows),
                "DD5": max(r["DD"] for r in rows),
                "losing5": sum(r["R"] < 0 for r in rows)}

    comb = {"G2": run_comb(None)}
    for v in VARIANTS:
        comb[f"G2+{v}"] = run_comb(v)

    # full-path DD (v421 continuous convention)
    Etot, Mtot = E, M
    full = {}
    for key in ["G2"] + [f"G2+{v}" for v in VARIANTS]:
        if key == "G2":
            A_c, M_c = Etot.copy(), Mtot.copy()
        else:
            v = key.split("+")[1]
            size = C.SIZE[v]
            A_c = np.empty(len(grid))
            M_c = np.empty(len(grid))
            A_prev = float(Etot[0])
            A_c[0], M_c[0] = float(Etot[0]), float(Mtot[0])
            A_at = {int(grid[0].value): A_prev}
            rec_c = rec[rec["day_ns"] >= int(grid[0].value)].copy()
            skipped_c: set = set()
            exn_c = rec_c["exit_ns"].to_numpy()
            dayn_c = rec_c["day_ns"].to_numpy()
            for i in range(1, len(grid)):
                tns = int(grid[i].value)
                m_entry = (dayn_c == tns)
                if m_entry.any():
                    grp = rec_c[m_entry].sort_values(["f", "coin", "k"])
                    new_open = []
                    for rix, r in grp.iterrows():
                        N = size * A_prev
                        open_now = sum(N0 for xo, N0 in new_open if xo > r["f"])
                        if (open_now + N) / A_prev + 1.0 > 2.0:
                            skipped_c.add(rix)
                            continue
                        new_open.append((r["x"], N))
                m_exit = (exn_c >= tns - 3_600_000_000_000) & (exn_c < tns)
                dU = 0.0
                if m_exit.any():
                    for rix, r in rec_c[m_exit].iterrows():
                        if rix in skipped_c:
                            continue
                        NA = size * A_at.get(r["day_ns"], A_prev)
                        dU += NA * r["ret"]
                g = Etot[i] / Etot[i - 1]
                hh = Mtot[i] / Etot[i - 1]
                A_c[i] = A_prev * g + dU
                M_c[i] = A_prev * hh + dU
                A_prev = A_c[i]
                A_at[tns] = A_prev
        segf = np.asarray(grid > pd.Timestamp("2021-09-24", tz="UTC"))
        esf, msf = A_c[segf], M_c[segf]
        dd_m = round(100 * float(np.max(1 - msf / np.maximum.accumulate(esf))), 2)
        dd_c = round(100 * float(np.max(1 - esf / np.maximum.accumulate(esf))), 2)
        full[key] = {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)}
    for key in comb:
        comb[key]["full_path_dd"] = full[key]

    # daily-return correlation sleeve vs G2 (dev4 + post, labelled)
    def daily_ret(bars_ns, Eser):
        idx = pd.to_datetime(bars_ns, utc=True)
        s = pd.Series(Eser, index=idx)
        d = s.resample("1D", origin=pd.Timestamp("2021-09-24", tz="UTC")).last().ffill()
        return d.pct_change().dropna()
    g2d = pd.Series(E, index=grid).resample(
        "1D", origin=pd.Timestamp("2021-09-24", tz="UTC")).last().ffill().pct_change().dropna()
    corr = {}
    for v in VARIANTS:
        sd = daily_ret(*cont[v])
        for tag, lo, hi in (("dev4", "2021-09-24", "2025-09-24"),
                            ("post", "2025-09-24", "2026-09-24")):
            a = g2d.loc[lo:hi]
            b = sd.loc[lo:hi]
            ix = a.index.intersection(b.index)
            c = round(float(a.loc[ix].corr(b.loc[ix])), 4) if len(ix) > 10 else None
            corr[f"{v}_vs_G2_{tag}"] = {"n": int(len(ix)), "pearson": c}

    res = {
        "meta": {
            "g2_src": "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl strat R2B1D17BFG2",
            "grid": [str(grid[0]), str(grid[-1])],
            "metric": "reset per anchor year (fresh 1.0) + v421 continuous full-path DD; f=0 reproduces v421_result to the digit",
            "sizing": "rung notional = size_frac x equity at entry day (D05=0.0320656, D025=0.0160328); combined: off TOTAL A + 2x cap (G2 gross proxied 1.0x)",
            "rungs": list(C.RUNGS), "tp": "1.0 sigma", "stop": "4.0 sigma touch, stop-first",
            "costs": "maker 0.0002, taker 0.00055, funding 0.0001 per 8h settlement spanned (all exits)",
            "n_records": int(len(rec)), "n_records_pre": int(len(pre)),
            "presample_src": "data/raw/spot_1m_presample_20261007 (SPOT 1m; fills/exits on spot, perp gate costs)",
        },
        "standalone": out_sa,
        "presample": out_pre,
        "combined": comb,
        "corr_daily": corr,
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    for v in VARIANTS:
        print(v, out_sa[v]["dev4"], "R5", out_sa[v]["R5"], flush=True)
        print(" pre:", [(L["leg"], L["R"], L["DD"], L["trades"], L["win"])
                         for L in out_pre[v]["legs"]], flush=True)
    for k in comb:
        print(k, comb[k]["dev4"], "R5", comb[k]["R5"],
              "fullDD", comb[k]["full_path_dd"], flush=True)
    print(corr, flush=True)
