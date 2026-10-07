"""oc_dvolbook: DVOL (Deribit implied vol) context for the deployed BOT book.

Per PLAN.md (pre-registered): causal DVOL features (as-of = last hourly close
with bar END <= T) joined to the rebuilt forward_v205.research_books_d2 grid;
(Q1) Spearman IC of each feature with next-6-bar / next-42-bar open-to-open
returns per anchor year (pooled + BTC-only + ETH-only); (Q2) book gross P&L
(weight x next-bar return, no costs) split by DVOL z90 tercile with cut-offs
from PREVIOUS data only, total + long/short legs, plus LOYO spreads;
(Q3) crash-risk descriptives per tercile. Single light process (4h inputs only).

  python research/tournament/oc_dvolbook/compute_dvolbook.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
OC_DVOL = ROOT / "research/tournament/oc_dvol"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
COINMAP = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "BTC",
           "BNBUSDT": "BTC", "XRPUSDT": "BTC"}
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
FEAT_START = pd.Timestamp("2021-06-30", tz="UTC")
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")  # no decision bar at/after this
NS = 1_000_000_000
H = 3_600 * NS
FEATURES = ["dvol_z90", "dvol_chg24", "vrp"]


# ---------------------------------------------------------------- inputs

def research_books_d2() -> pd.DataFrame:
    """Mirror of oc_bookic.compute_bookic.research_books_d2 (same files, same math)."""
    m = lambda f: pd.read_parquet(CACHE / f)[SYMS]  # noqa: E731
    A, Aq = m("member_A_O1_orders.parquet"), m("member_Aq_O1_orders.parquet")
    B, Bq = m("member_B_tv.parquet"), m("member_Bq_tv.parquet")
    idx = A.index.union(Aq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)  # noqa: E731
    o1 = 0.5 * (f(A) + f(B)) / 2 + 0.5 * (f(Aq) + f(Bq)) / 2
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    Dq = pd.read_parquet(CACHE / "members_quarterly_D.parquet")[SYMS]
    idx2 = o1.index.union(D.index).union(Dq.index)
    g = lambda X: X.reindex(idx2).fillna(0.0)  # noqa: E731
    return 0.8 * g(o1) + 0.2 * (g(D) + g(Dq)) / 2


def load_dvol() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per mapped coin: (bar_END_ns sorted int64, closes float64), t < CUTOFF."""
    panel = pd.read_parquet(OC_DVOL / "dvol_hourly.parquet")
    panel = panel[panel["t"] < CUTOFF].copy()
    out = {}
    for sym, cur in (("BTCDVOL", "BTC"), ("ETHDVOL", "ETH")):
        g = panel[panel["sym"] == sym].sort_values("t")
        ends = (g["t"] + pd.Timedelta(hours=1)).to_numpy(dtype="datetime64[ns]").astype(np.int64)
        out[cur] = (ends, g["close"].to_numpy(float))
    return out


def load_daily() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per mapped coin: (daily-close END_ns, closes). C(D) = 23:00-bar close."""
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h = h[(h["t"] < CUTOFF)]
    out = {}
    for sym, cur in (("BTCUSDT", "BTC"), ("ETHUSDT", "ETH")):
        g = h[h["sym"] == sym].sort_values("t").reset_index(drop=True)
        d = g[g["t"].dt.strftime("%H:%M") == "23:00"].copy()
        ends = (d["t"] + pd.Timedelta(hours=1)).to_numpy(dtype="datetime64[ns]").astype(np.int64)
        out[cur] = (ends, d["close"].to_numpy(float))
    return out


# ---------------------------------------------------------------- features

def asof_idx(ends: np.ndarray, Tns: np.ndarray) -> np.ndarray:
    """Index of last bar with end <= T. -1 if none."""
    return np.searchsorted(ends, Tns, side="right") - 1


def features_for_times(Tns: np.ndarray, dvol, daily) -> dict[str, pd.DataFrame]:
    """Causal features per unique decision time, per mapped coin (BTC/ETH)."""
    out = {}
    for cur in ("BTC", "ETH"):
        ends, cl = dvol[cur]
        Tn = Tns
        ii = asof_idx(ends, Tn)
        ok = ii >= 0
        v0 = np.full(len(Tn), np.nan)
        v0[ok] = cl[ii[ok]]
        cnt = np.zeros(len(Tn))
        s1 = np.zeros(len(Tn))
        s2 = np.zeros(len(Tn))
        for k in range(1, 2161):
            jk = np.searchsorted(ends, Tn - k * H, side="right") - 1
            okk = jk >= 0
            w = np.full(len(Tn), np.nan)
            w[okk] = cl[jk[okk]]
            v = np.isfinite(w)
            cnt[v] += 1
            s1[v] += w[v]
            s2[v] += w[v] ** 2
        good = cnt >= 1728
        mean = np.full(len(Tn), np.nan)
        std = np.full(len(Tn), np.nan)
        mean[good] = s1[good] / cnt[good]
        var_sub = (s2[good] - s1[good] ** 2 / cnt[good]) / (cnt[good] - 1)
        gidx = np.where(good)[0]
        pos = var_sub > 0
        std[gidx[pos]] = np.sqrt(var_sub[pos])
        z = (v0 - mean) / std
        jl = np.searchsorted(ends, Tn - 24 * H, side="right") - 1
        vl = np.full(len(Tn), np.nan)
        okkl = jl >= 0
        vl[okkl] = cl[jl[okkl]]
        chg = v0 - vl
        dends, dcl = daily[cur]
        di = asof_idx(dends, Tn)
        rv = np.full(len(Tn), np.nan)
        for i in np.where(di >= 30)[0]:
            seg = dcl[di[i] - 30: di[i] + 1]
            if np.all(np.isfinite(seg)) and np.all(seg > 0):
                r = np.log(seg[1:] / seg[:-1])
                rv[i] = float(np.std(r, ddof=1) * np.sqrt(365) * 100)
        out[cur] = pd.DataFrame({"dvol_z90": z, "dvol_chg24": chg, "vrp": v0 - rv})
    return out


def spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, int, float]:
    m = np.isfinite(x) & np.isfinite(y)
    n = int(m.sum())
    if n < 30:
        return np.nan, n, np.nan
    r, p = st.spearmanr(x[m], y[m])
    return float(r), n, float(p)


# ---------------------------------------------------------------- main

def main() -> None:
    dvol = load_dvol()
    daily = load_daily()
    for cur, (ends, _) in dvol.items():
        dt0 = pd.to_datetime(ends[0], utc=True, unit="ns")
        dt1 = pd.to_datetime(ends[-1], utc=True, unit="ns")
        print(f"{cur}: bars={len(ends)} span_end={dt0}..{dt1}", flush=True)

    books = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books.index)
    grid = books.index.intersection(opens.dropna(how="all").index)
    grid = grid[(grid >= ANCHORS[0]) & (grid < CUTOFF)].sort_values()
    books, opens = books.reindex(grid), opens.reindex(grid)
    print(f"book grid: {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)

    # Forward returns; exits must not use opens after CUTOFF (boundary incl.).
    o = opens[SYMS]
    ot = opens.index
    fwd1 = o.shift(-1) / o - 1.0
    fwd6 = o.shift(-6) / o - 1.0
    fwd42 = o.shift(-42) / o - 1.0
    exit1_ok = (ot.shift(-1) <= CUTOFF)
    exit6_ok = (ot.shift(-6) <= CUTOFF)
    exit42_ok = (ot.shift(-42) <= CUTOFF)
    fwd1 = fwd1[exit1_ok]
    fwd6, fwd42 = fwd6[exit6_ok], fwd42[exit42_ok]
    keep = exit1_ok  # pnl needs the 1-bar exit; IC horizons are pairwise
    books, opens = books[keep], opens[keep]
    pnl = books * fwd1.reindex(books.index)
    valid1 = pnl.notna().all(axis=1)  # PLAN: drop the last grid bar (no forward open)
    books, opens, pnl = books[valid1], opens[valid1], pnl[valid1]
    fwd1 = fwd1.reindex(books.index)

    # Extended feature grid: pre-anchor 4h bars (cut-off pool) + book grid.
    pre = opens_full.index[(opens_full.index >= FEAT_START) & (opens_full.index < ANCHORS[0])].sort_values()
    T_all = pre.union(books.index).sort_values()
    Tns = T_all.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    feat = features_for_times(Tns, dvol, daily)
    F = {}
    for s in SYMS:
        F[s] = feat[COINMAP[s]].set_index(T_all)

    rows = []
    for s in SYMS:
        Fs = F[s].reindex(books.index)
        rows.append(pd.DataFrame({
            "T": books.index, "sym": s, "w": books[s].to_numpy(float),
            "r1": fwd1[s].reindex(books.index).to_numpy(float),
            "pnl": pnl[s].to_numpy(float),
            "R6": fwd6[s].reindex(books.index).to_numpy(float),
            "R42": fwd42[s].reindex(books.index).to_numpy(float),
            "dvol_coin": COINMAP[s],
            "dvol_z90": Fs["dvol_z90"].to_numpy(float),
            "dvol_chg24": Fs["dvol_chg24"].to_numpy(float),
            "vrp": Fs["vrp"].to_numpy(float),
        }))
    panel = pd.concat(rows, ignore_index=True)
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")

    # Full (T, sym) feature pool for causal cut-offs (extended grid x 5 syms).
    pool_rows = []
    for s in SYMS:
        Fs = F[s]
        pool_rows.append(pd.DataFrame({
            "T": T_all, "sym": s, "dvol_z90": Fs["dvol_z90"].to_numpy(float),
        }))
    pool = pd.concat(pool_rows, ignore_index=True)
    pool["T"] = pd.to_datetime(pool["T"], utc=True)

    bounds = ANCHORS + [LAST_BOUND]
    year_m = [((panel["T"] >= bounds[k]) & (panel["T"] < bounds[k + 1])).to_numpy()
              for k in range(5)]
    pT = pool["T"].to_numpy()
    px = pool["dvol_z90"].to_numpy(float)

    res: dict = {"meta": {
        "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_bookic)",
        "opens": "engine_real opens_v154.parquet",
        "dvol": "research/tournament/oc_dvol/dvol_hourly.parquet (t<CUTOFF)",
        "asof": "last hourly bar with end <= T; z90 vs trailing 2160 asof samples",
        "symbols": SYMS, "cutoff": str(CUTOFF),
        "grid_start": str(panel["T"].min()), "grid_end": str(panel["T"].max()),
        "n_panel": int(len(panel)),
        "anchor_years": [str(a.date()) for a in ANCHORS],
        "outcome": "pnl=w*(open[t+1]/open[t]-1) gross, no costs; R6/R42 simple open-to-open",
    }}

    # ---- Q1: ICs
    ic = {}
    for feat_name in FEATURES:
        x = panel[feat_name].to_numpy(float)
        ic[feat_name] = {}
        for hname, hcol in (("R6", "R6"), ("R42", "R42")):
            y = panel[hcol].to_numpy(float)
            ic[feat_name][hname] = {}
            for pname, pm in (("pooled", np.ones(len(panel), bool)),
                              ("BTC", (panel["sym"] == "BTCUSDT").to_numpy()),
                              ("ETH", (panel["sym"] == "ETHUSDT").to_numpy())):
                rows_y = []
                for k in range(5):
                    m = year_m[k] & pm
                    rho, n, p = spearman(x[m], y[m])
                    cov = float(np.isfinite(x[m]).mean()) if m.sum() else 0.0
                    rows_y.append({"year": str(ANCHORS[k].date()),
                                   "n_bars": int(m.sum()), "n_valid": n,
                                   "rho": None if np.isnan(rho) else round(rho, 4),
                                   "p": None if (p is None or np.isnan(p)) else round(float(p), 4),
                                   "coverage": round(cov, 4)})
                ic[feat_name][hname][pname] = rows_y
    res["ic"] = ic

    # ---- Q2: z90 terciles of pnl, cut-offs from previous data only
    z = panel["dvol_z90"].to_numpy(float)
    p = panel["pnl"].to_numpy(float)
    w = panel["w"].to_numpy(float)
    legs = {"total": np.ones(len(panel), bool), "long": w > 0, "short": w < 0}
    terc, spreads = [], {k: [] for k in legs}
    for k, a0 in enumerate(ANCHORS):
        tr = (pT >= FEAT_START) & (pT < a0) & np.isfinite(px)
        cut = {}
        row = {"year": str(a0.date()), "legs": {}}
        if int(tr.sum()) >= 100:
            q33, q67 = float(np.quantile(px[tr], 1 / 3)), float(np.quantile(px[tr], 2 / 3))
            cut = {"q33": q33, "q67": q67, "n_train": int(tr.sum())}
            te = year_m[k]
            for lname, lm in legs.items():
                lo = te & lm & np.isfinite(z) & (z <= q33)
                hi = te & lm & np.isfinite(z) & (z > q67)
                mid = te & lm & np.isfinite(z) & (z > q33) & (z <= q67)
                cell = {}
                for nm, mm in (("lo", lo), ("mid", mid), ("hi", hi)):
                    yy = p[mm]
                    cell[nm] = {"mean_bps": round(float(np.mean(yy)) * 1e4, 2) if len(yy) else None,
                                "n": int(mm.sum())}
                if int(lo.sum()) >= 30 and int(hi.sum()) >= 30:
                    sp = float(np.mean(p[hi]) - np.mean(p[lo])) * 1e4
                else:
                    sp = None
                cell["spread_bps"] = None if sp is None else round(sp, 2)
                row["legs"][lname] = cell
        else:
            for lname in legs:
                row["legs"][lname] = {"lo": {"mean_bps": None, "n": 0},
                                      "mid": {"mean_bps": None, "n": 0},
                                      "hi": {"mean_bps": None, "n": 0},
                                      "spread_bps": None}
        row["cutoffs"] = cut
        terc.append(row)
        for lname in legs:
            spreads[lname].append(row["legs"][lname]["spread_bps"])
    res["terciles"] = terc

    # ---- Q2 LOYO
    loyo = {k: [] for k in legs}
    for h in range(5):
        tr = np.zeros(len(panel), bool)
        for k in range(5):
            if k != h:
                tr |= year_m[k]
        te = year_m[h]
        for lname, lm in legs.items():
            trm = tr & lm & np.isfinite(z)
            info: dict = {}
            spread = None
            if int(trm.sum()) >= 100:
                q33, q67 = float(np.quantile(z[trm], 1 / 3)), float(np.quantile(z[trm], 2 / 3))
                lo = te & lm & np.isfinite(z) & (z <= q33)
                hi = te & lm & np.isfinite(z) & (z > q67)
                if int(lo.sum()) >= 30 and int(hi.sum()) >= 30:
                    spread = float(np.mean(p[hi]) - np.mean(p[lo])) * 1e4
                info = {"q33": q33, "q67": q67, "n_train": int(trm.sum()),
                        "n_lo": int(lo.sum()), "n_hi": int(hi.sum())}
            loyo[lname].append({"heldout": str(ANCHORS[h].date()),
                                "spread_bps": None if spread is None else round(spread, 2),
                                **info})
    res["loyo"] = loyo

    # ---- Q3: crash-risk descriptives per year x tercile (total rows)
    crash = []
    for k, a0 in enumerate(ANCHORS):
        cut = terc[k]["cutoffs"]
        row = {"year": str(a0.date())}
        if cut:
            q33, q67 = cut["q33"], cut["q67"]
            te = year_m[k] & np.isfinite(z)
            for nm, mm in (("lo", te & (z <= q33)),
                           ("mid", te & (z > q33) & (z <= q67)),
                           ("hi", te & (z > q67))):
                yy = p[mm] * 1e4
                neg = yy[yy < 0]
                row[nm] = {"mean_bps": round(float(np.mean(yy)), 3) if len(yy) else None,
                           "std_bps": round(float(np.std(yy, ddof=1)), 3) if len(yy) >= 2 else None,
                           "p_loss": round(float((yy < 0).mean()), 4) if len(yy) else None,
                           "mean_neg_bps": round(float(np.mean(neg)), 3) if len(neg) else None,
                           "n": int(mm.sum())}
        else:
            for nm in ("lo", "mid", "hi"):
                row[nm] = {"mean_bps": None, "std_bps": None, "p_loss": None,
                           "mean_neg_bps": None, "n": 0}
        crash.append(row)
    res["crash"] = crash

    # ---- decisions
    dec = {}
    for lname in legs:
        ys = [s for s in spreads[lname]]
        ls = [d["spread_bps"] for d in loyo[lname]]
        sy = [np.sign(s) for s in ys if s is not None]
        sl = [np.sign(s) for s in ls if s is not None]
        ny = max(int((np.array(sy) > 0).sum()), int((np.array(sy) < 0).sum())) if sy else 0
        nl = max(int((np.array(sl) > 0).sum()), int((np.array(sl) < 0).sum())) if sl else 0
        dec[lname] = {"year_sign_count": f"{ny}/5", "loyo_sign_count": f"{nl}/5",
                      "year_spreads": ys,
                      "loyo_spreads": ls,
                      "promising": bool(ny >= 4 and nl >= 4)}
    res["decisions"] = dec

    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(dec, indent=1))


if __name__ == "__main__":
    main()
