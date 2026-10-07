"""oc_ethbtc analysis (PLAN.md): dip rung y1.0 + book gross P&L by regime tercile.

Previous-years cut-offs for anchor years; leave-one-year-out stability.
Single process, 4h + fills inputs only (no 1m).

  python research/tournament/oc_ethbtc/analyze_ethbtc.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import regimes_ethbtc as R

SYMS = R.SYMS
VARS = R.VARS
DEPTHS = [2.5, 3.0, 3.5, 4.0, 5.0]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR = pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
BPS = 1e4


def sgn(x: float) -> int:
    if x is None or not np.isfinite(x) or x == 0:
        return 0
    return 1 if x > 0 else -1


def tercile_stats(
    vals: pd.Series, outcome: pd.Series, lo: float, hi: float
) -> dict:
    """Split outcome by previous cut-offs; means in native units."""
    m_lo = vals < lo
    m_hi = vals > hi
    m_mid = ~(m_lo | m_hi)
    g = {}
    for name, m in (("lo", m_lo), ("mid", m_mid), ("hi", m_hi)):
        o = outcome[m]
        g[name] = (float(o.mean()), int(o.size))
    d = g["hi"][0] - g["lo"][0]
    return {
        "n": int(outcome.size),
        "n_lo": g["lo"][1], "n_mid": g["mid"][1], "n_hi": g["hi"][1],
        "mean_lo": g["lo"][0], "mean_mid": g["mid"][0], "mean_hi": g["hi"][0],
        "hilo": float(d),
    }


def main() -> None:
    opens = R.load_opens()
    regimes = R.compute_regimes(opens)

    # ---- (a) dip fills ----
    fills = pd.read_parquet(ROOT / "research/tournament/ext/fills_U_ext.parquet")
    fills["T"] = pd.to_datetime(fills["t_fill"], utc=True) - pd.to_timedelta(
        fills["f"].astype(float), unit="min"
    )
    fills = fills[(fills["T"] < CUTOFF)].copy()
    main_m = fills["sym"].isin(SYMS) & fills["x1"].isin(DEPTHS)
    mainf = fills[main_m].copy().reset_index(drop=True)
    asg = R.assign_to_fills(mainf["T"], regimes)
    for v in VARS:
        mainf[v] = asg[v].values
    mainf["grid_t"] = asg["grid_t"].values
    n_noreg = int(mainf[VARS[0]].isna().sum())
    mainf = mainf.dropna(subset=VARS).reset_index(drop=True)

    def year_of(T: pd.Series, k: int) -> pd.Series:
        return (T >= ANCHORS[k]) & (T < ANCHORS[k] + YEAR)

    dip_rows, dip_loo = [], {}
    for v in VARS:
        signs, loo_folds = [], []
        for k, a0 in enumerate(ANCHORS):
            hist = mainf[mainf["T"] < a0]
            lo_c, hi_c = hist[v].quantile(1 / 3), hist[v].quantile(2 / 3)
            ym = year_of(mainf["T"], k)
            sub = mainf[ym]
            st = tercile_stats(sub[v], sub["y1.0"], float(lo_c), float(hi_c))
            dip_rows.append({
                "year": str(a0.date()), "var": v,
                "cut_lo": round(float(lo_c), 6), "cut_hi": round(float(hi_c), 6),
                "hist_n": int(len(hist)),
                "n": st["n"], "n_lo": st["n_lo"], "n_mid": st["n_mid"], "n_hi": st["n_hi"],
                "mean_lo_bps": round(st["mean_lo"] * BPS, 2),
                "mean_mid_bps": round(st["mean_mid"] * BPS, 2),
                "mean_hi_bps": round(st["mean_hi"] * BPS, 2),
                "hilo_bps": round(st["hilo"] * BPS, 2),
                "sign": sgn(st["hilo"]),
            })
            signs.append(sgn(st["hilo"]))
        # LOO: cut-offs + training sign from the other 4 anchor years
        for h in range(5):
            # restrict train to the 5 anchor windows (exclude pre-2021 stub)
            in_any = pd.Series(False, index=mainf.index)
            for k in range(5):
                if k != h:
                    in_any |= year_of(mainf["T"], k)
            train = mainf[in_any]
            lo_c = float(train[v].quantile(1 / 3))
            hi_c = float(train[v].quantile(2 / 3))
            tr = tercile_stats(train[v], train["y1.0"], lo_c, hi_c)
            tsign = sgn(tr["hilo"])
            sub = mainf[year_of(mainf["T"], h)]
            te = tercile_stats(sub[v], sub["y1.0"], lo_c, hi_c)
            tsign2 = sgn(te["hilo"])
            ok_n = te["n_lo"] >= 30 and te["n_hi"] >= 30
            holds = bool(ok_n and tsign != 0 and tsign2 == tsign)
            loo_folds.append({
                "heldout": str(ANCHORS[h].date()),
                "cut_lo": round(lo_c, 6), "cut_hi": round(hi_c, 6),
                "train_hilo_bps": round(tr["hilo"] * BPS, 2),
                "train_sign": tsign,
                "test_hilo_bps": round(te["hilo"] * BPS, 2),
                "test_sign": tsign2,
                "test_n_lo": te["n_lo"], "test_n_hi": te["n_hi"],
                "holds": holds,
            })
        dip_loo[v] = loo_folds

    # ---- (b) book gross P&L ----
    books = R.research_books_d2()
    opens5 = opens.reindex(books.index)
    grid = books.index.intersection(opens5.dropna(how="all").index)
    books, opens5 = books.reindex(grid).sort_index(), opens5.reindex(grid).sort_index()
    reg = regimes.reindex(books.index)
    reg_full = regimes.dropna(how="any")  # full opens history for cut-offs (PLAN)
    fwd1 = opens5.shift(-1) / opens5 - 1.0
    pnl = books * fwd1
    valid = fwd1.notna().all(axis=1)
    books, opens5, pnl, reg = books[valid], opens5[valid], pnl[valid], reg[valid]
    pnl_tot = pnl.sum(axis=1)  # summed over 5 coins
    # orphan-bar disclosure: bars in no literal year window
    in_any_year = pd.Series(False, index=pnl.index)
    for a0 in ANCHORS:
        in_any_year |= (pnl.index >= a0) & (pnl.index < a0 + YEAR)
    n_orphan = int((~in_any_year).sum())

    book_rows, book_loo = [], {}
    for v in VARS:
        for k, a0 in enumerate(ANCHORS):
            hist_idx = reg_full.index[reg_full.index < a0]
            lo_c = float(reg_full.loc[hist_idx, v].quantile(1 / 3))
            hi_c = float(reg_full.loc[hist_idx, v].quantile(2 / 3))
            ym = (pnl.index >= a0) & (pnl.index < a0 + YEAR)
            st = tercile_stats(reg.loc[ym, v], pnl_tot[ym], lo_c, hi_c)
            book_rows.append({
                "year": str(a0.date()), "var": v,
                "cut_lo": round(lo_c, 6), "cut_hi": round(hi_c, 6),
                "hist_bars": int(len(hist_idx)),
                "n": st["n"], "n_lo": st["n_lo"], "n_mid": st["n_mid"], "n_hi": st["n_hi"],
                "sum_lo": round(float(pnl_tot[ym][reg.loc[ym, v] < lo_c].sum()), 6),
                "sum_mid": round(float(pnl_tot[ym][~(reg.loc[ym, v] < lo_c) & ~(reg.loc[ym, v] > hi_c)].sum()), 6),
                "sum_hi": round(float(pnl_tot[ym][reg.loc[ym, v] > hi_c].sum()), 6),
                "mean_lo_bps": round(st["mean_lo"] * BPS, 3),
                "mean_mid_bps": round(st["mean_mid"] * BPS, 3),
                "mean_hi_bps": round(st["mean_hi"] * BPS, 3),
                "hilo_bps": round(st["hilo"] * BPS, 3),
                "sign": sgn(st["hilo"]),
            })
        for h in range(5):
            in_train = pd.Series(False, index=pnl.index)
            for k in range(5):
                if k != h:
                    in_train |= (pnl.index >= ANCHORS[k]) & (pnl.index < ANCHORS[k] + YEAR)
            tr_reg = reg.loc[in_train, v].dropna()
            lo_c = float(tr_reg.quantile(1 / 3))
            hi_c = float(tr_reg.quantile(2 / 3))
            # train stats on valid-regime bars only
            vv = reg.loc[in_train, v].dropna().index
            tr = tercile_stats(reg.loc[vv, v], pnl_tot[vv], lo_c, hi_c)
            tsign = sgn(tr["hilo"])
            hm = (pnl.index >= ANCHORS[h]) & (pnl.index < ANCHORS[h] + YEAR)
            vv_h = reg.loc[hm, v].dropna().index
            te = tercile_stats(reg.loc[vv_h, v], pnl_tot[vv_h], lo_c, hi_c)
            tsign2 = sgn(te["hilo"])
            ok_n = te["n_lo"] >= 50 and te["n_hi"] >= 50
            holds = bool(ok_n and tsign != 0 and tsign2 == tsign)
            book_loo.setdefault(v, []).append({
                "heldout": str(ANCHORS[h].date()),
                "cut_lo": round(lo_c, 6), "cut_hi": round(hi_c, 6),
                "train_hilo_bps": round(tr["hilo"] * BPS, 3),
                "train_sign": tsign,
                "test_hilo_bps": round(te["hilo"] * BPS, 3),
                "test_sign": tsign2,
                "test_n_lo": te["n_lo"], "test_n_hi": te["n_hi"],
                "holds": holds,
            })

    def gate(rows, loo, v):
        yrs = [r for r in rows if r["var"] == v]
        signs = [r["sign"] for r in yrs]
        nz = [s for s in signs if s != 0]
        consistent = (
            len(nz) == 5 and (nz.count(1) >= 4 or nz.count(-1) >= 4)
        )
        holds = sum(1 for f in loo[v] if f["holds"])
        promising = bool(consistent and holds >= 4)
        return {"signs": signs, "n_same_sign": max(nz.count(1), nz.count(-1)) if nz else 0,
                "consistent_4of5": consistent, "loo_holds": holds, "promising": promising}

    out = {
        "meta": {
            "anchors": [str(a.date()) for a in ANCHORS],
            "year_def": "[A_k, A_k+365d) literal; orphan 4h bars excluded from per-year and 5y",
            "dip_universe": "MAIN = 5 majors x R2 depths [2.5,3.0,3.5,4.0,5.0]; outcome y1.0 per fill",
            "book": "forward_v205.research_books_d2 rebuilt exactly; pnl[t]=w[t]*r[t] gross, summed over 5 coins",
            "regimes": "ethbtc30=log(ETH/BTC change 180b); ethbtc90=same 540b; dom30=BTC30d - eqw-majors30d; all from 4h opens <= t",
            "cutoff_data": "2026-09-24T00:00Z",
            "T_min": str(mainf["T"].min()), "T_max": str(mainf["T"].max()),
            "n_main_fills": int(len(mainf)), "n_dropped_no_regime": n_noreg,
            "grid_start": str(pnl.index.min()), "grid_end": str(pnl.index.max()),
            "n_grid_bars": int(len(pnl)), "n_orphan_bars": n_orphan,
        },
        "dip_per_year": dip_rows,
        "book_per_year": book_rows,
        "dip_loo": dip_loo,
        "book_loo": book_loo,
        "gates": {
            "dip": {v: gate(dip_rows, dip_loo, v) for v in VARS},
            "book": {v: gate(book_rows, book_loo, v) for v in VARS},
        },
        "definitions": ("dip: fill tercile by previous-history fill quantiles, d=mean_hi-mean_lo y1.0; "
                        "book: bar tercile by previous-history grid quantiles, d=meanbar_hi-meanbar_lo pnl; "
                        "PROMISING = sign same >=4/5 years AND LOO holds >=4/5 (min n 30 fills / 50 bars per side)"),
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for part in ("dip", "book"):
        for v in VARS:
            g = out["gates"][part][v]
            print(f"{part:4s} {v:8s} signs={g['signs']} same={g['n_same_sign']} "
                  f"cons={g['consistent_4of5']} loo={g['loo_holds']}/5 PROMISING={g['promising']}")
    # regime parquet for audit
    regimes.dropna().to_parquet(HERE / "regimes_ethbtc.parquet")


if __name__ == "__main__":
    main()
