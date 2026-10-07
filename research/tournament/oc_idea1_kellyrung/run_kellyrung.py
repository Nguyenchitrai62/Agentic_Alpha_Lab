"""oc_idea1_kellyrung runner: baseline + pooled fit + dip replica (light) + 4-phase engine (heavy).

Pre-reg: REPORT.md section 0 (K1 f=0.25, K2 f=0.50, rest identical G2).
Leakage: train rows t_exit < anchor-7d only; 2025 scored once for winner only.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "research/tournament/ext"))

ANCHORS = [pd.Timestamp(a, tz="UTC") for a in (
    "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
DEV4 = [0, 1, 2, 3]
EMBARGO = pd.Timedelta(days=7)
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
FRAC = {"K1": 0.25, "K2": 0.50}
KD = 1.7
PLACEBO_P95 = 0.273


def count_n(tfill, sym, T):
    n = np.zeros(len(tfill), int)
    pos = {t: ii for t, ii in
           pd.DataFrame({"T": T}).groupby("T", sort=False).groups.items()}
    for ii in pos.values():
        ii = np.asarray(list(ii))
        if len(ii) == 1:
            continue
        tf, sm = tfill[ii], sym[ii]
        dt = np.abs((tf[:, None] - tf[None, :]).astype(
            "timedelta64[s]").astype(float)) / 60.0
        near = dt <= 15.0 + 1e-9
        for a in range(len(ii)):
            n[ii[a]] = len({sm[b] for b in range(len(ii))
                            if sm[b] != sm[a] and near[a, b]})
    return n


def kelly_star(z, cap=20.0):
    z = np.asarray(z, float)
    assert np.isfinite(z).all() and len(z) > 0

    def gp(f):
        return float(np.mean(z / (1.0 + f * z)))

    if not np.isfinite(gp(0.0)) or gp(0.0) <= 0:
        return 0.0
    zmin = float(z.min())
    fmax = min(0.999 / (-zmin), cap) if zmin < 0 else cap
    if gp(fmax) >= 0:
        return fmax
    lo, hi = 0.0, fmax
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if gp(mid) >= 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def stage_baseline():
    cc = json.loads((ROOT / "research/tournament/oc_carrycompound/results.json").read_text())
    v421 = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json").read_text())
    g2 = cc["rows"]["G2_f0.0"]
    gc = cc["rows"]["G2_f0.25"]
    assert [y["R"] for y in g2["years"]] == [2.588, 3.282, 6.045, 10.677, 4.648], g2
    assert [y["DD"] for y in g2["years"]] == [10.86, 16.91, 15.81, 8.27, 12.9], g2
    assert g2["R"] == 5.41 and g2["W"] == 2.588 and g2["DD"] == 16.91, g2
    assert g2["full_path_dd"] == {"marked": 16.82, "close": 16.05, "full": 16.82}, g2
    assert gc["R"] == 5.634 and gc["W"] == 2.778 and gc["DD"] == 16.75, gc
    assert gc["full_path_dd"] == {"marked": 16.66, "close": 15.9, "full": 16.66}, gc
    assert cc["carry_add_pp_per_month"] == 0.224
    exp = v421["rows"]["R2B1D17BFG2"]
    assert exp["R"] == 5.41 and exp["W"] == 2.588 and exp["DD"] == 16.91, exp
    assert exp["full_path_dd"] == 16.82, exp
    out = {"G2_R": g2["R"], "G2_W": g2["W"], "G2_DD": g2["DD"],
           "G2_full": g2["full_path_dd"]["full"],
           "GC_R": gc["R"], "GC_W": gc["W"], "GC_DD": gc["DD"],
           "GC_full": gc["full_path_dd"]["full"], "carry_add": 0.224,
           "status": "reproduced exactly"}
    (HERE / "tmp" / "baseline.json").write_text(json.dumps(out, indent=1))
    print("BASELINE OK: G2 5.41/W2.588/DD16.91/full16.82; G2+carry 5.634/DD16.75/full16.66")
    return out


def load_harness5():
    import harness5 as H5
    d = H5.load()
    return H5, d


def load_harness4():
    sys.path.insert(0, str(ROOT / "research/tournament"))
    import harness as H
    d = H.load()
    return H, d


def fit_tables(H5, d):
    """Per-anchor pooled fit (train t_exit<anchor-7d). H5 may be harness(4) or harness5(5); train-only, no test look."""
    folds = H5.folds(d)
    y = d.y_dep.to_numpy()
    tables = {}
    # n over majors-R2 universe (timestamp-clustered, bot-executable proxy)
    uni = d[d.sym.isin(MAJORS) & d.k.isin(R2)].copy().reset_index(drop=True)
    uni_n = count_n(uni.t_fill.to_numpy(), uni.sym.to_numpy(), uni["T"].to_numpy())
    uni = uni.assign(n=uni_n)
    for yi, a0, tr, te in folds:
        key = str(a0.date())
        ytr_all = y[tr][np.isfinite(y[tr])]
        mu_all = float(ytr_all.mean()) if len(ytr_all) else float("nan")
        va_all = float(ytr_all.var()) if len(ytr_all) else float("nan")
        try:
            fs = float(kelly_star(ytr_all)) if len(ytr_all) > 100 else 0.0
        except Exception:
            fs = 0.0
        m_tr = tr & d.sym.isin(MAJORS).to_numpy() & d.k.isin(R2).to_numpy() \
            & d.size_dep.notna().to_numpy()
        row = {"anchor": key, "n_train_all": int(tr.sum()),
               "n_train_majR2": int(m_tr.sum()), "mu_all": mu_all,
               "var_all": va_all, "f_star_all": round(fs, 4)}
        per_k, raws = {}, {}
        for k in R2:
            mk = m_tr & (d.k.to_numpy() == k)
            yk = y[mk]
            yk = yk[np.isfinite(yk)]
            if len(yk) >= 50:
                mu = float(yk.mean())
                va = float(yk.var()) if float(yk.var()) > 1e-12 else 1e-12
                raws[k] = max(mu, 0.0) / va
                per_k[str(k)] = {"n": int(len(yk)), "mu": round(mu, 6),
                                 "var": round(float(yk.var()), 8),
                                 "raw": round(float(raws[k]), 4)}
            else:
                raws[k] = None
                per_k[str(k)] = {"n": int(len(yk)), "mu": None, "var": None, "raw": None}
        row["per_k"] = per_k
        valid = {k: v for k, v in raws.items() if v is not None}
        if len(valid) >= 2:
            mraw = float(np.mean(list(valid.values())))
            C = 1.0 / mraw if mraw > 0 else 1.0
            base = {str(k): (round(float(np.clip(C * valid[k], 0, 2)), 6)
                             if valid.get(k) is not None else 1.0) for k in R2}
            # train means for budget normalisation (majors R2 train rows)
            idx_tr = uni[uni["T"].isin(d["T"][m_tr])].index if m_tr.sum() else []
            b1_tr = 1.0 / (1.0 + uni.loc[uni.index.isin(
                uni[uni["T"].isin(d.loc[m_tr, 'T'])].index), "n"].to_numpy()) \
                if m_tr.sum() else np.array([0.5])
            dep_tr = d.size_dep.to_numpy()[m_tr]
            bk = np.array([base[str(k)] for k in d.k.to_numpy()[m_tr]])
            meanB1 = float(b1_tr.mean()) if len(b1_tr) else 0.5
            meanDep = float(dep_tr.mean()) if len(dep_tr) else 1.0
            meanB1Base = float((b1_tr[:len(bk)] * bk[:len(b1_tr)]).mean()) \
                if len(b1_tr) and len(bk) else meanB1
            C0 = KD * meanDep / max(meanB1Base, 1e-9)
            row.update({"mode": "per_k", "C_budget": round(float(C), 6),
                        "meanB1": round(meanB1, 6), "meanDep": round(meanDep, 6),
                        "C0": round(float(C0), 6), "base": base})
        else:
            row.update({"mode": "fallback_flat", "C_budget": 1.0,
                        "meanB1": 0.5, "meanDep": 1.0,
                        "C0": round(KD * 1.0 / 0.5, 6),
                        "base": {str(k): 1.0 for k in R2}})
        tables[key] = row
        print(json.dumps({k: row[k] for k in (
            "anchor", "n_train_all", "n_train_majR2", "mu_all", "var_all",
            "f_star_all", "mode", "C0")}), flush=True)
    (HERE / "tmp" / "fit_tables.json").write_text(json.dumps(tables, indent=1))
    return tables


def stage_replica(years, winner_only=None):
    # DEV4 selection MUST NOT touch 2025: use 4-fold harness (dev-only fills).
    # winner_only (e.g. "K2") with years=[4] uses harness5 once, for the chosen variant only.
    if years == [4]:
        assert winner_only in FRAC, "2025 scored once, winner only"
        H5mod, d = load_harness5()
        H5 = H5mod
        variants = [winner_only]
    else:
        H5mod, d = load_harness4()
        H5 = H5mod
        variants = ["B1"] + list(FRAC)
    tables = json.loads((HERE / "tmp" / "fit_tables.json").read_text())
    uni = d[d.sym.isin(MAJORS) & d.k.isin(R2)].copy().reset_index(drop=True)
    uni["n"] = count_n(uni.t_fill.to_numpy(), uni.sym.to_numpy(), uni["T"].to_numpy())
    uni["B1"] = 1.0 / (1.0 + uni["n"].to_numpy())
    # map each row to its test anchor year
    uni["anchor"] = ""
    for y, a0 in enumerate(H5.ANCHORS):
        m = (uni["T"] >= a0) & (uni["T"] < a0 + pd.Timedelta(days=365))
        uni.loc[m, "anchor"] = str(a0.date())
    for v, f in FRAC.items():
        w = np.full(len(uni), np.nan)
        for key, t in tables.items():
            m = (uni.anchor == key).to_numpy()
            if not m.any():
                continue
            bk = np.array([t["base"][str(k)] for k in uni.k.to_numpy()[m]])
            # s = B1 * Base_per_k * f_frac * C0  (C0 = KD*meanDep/mean(B1*Base) on train)
            w[m] = uni["B1"].to_numpy()[m] * bk * f * t["C0"]
        uni[v] = w
    # score per requested years: raw sums + harness equal-exposure
    folds = H5.folds(d)
    # align uni rows to d index for harness score: build full-length arrays
    res = {"variants": {}, "placebo_p95": PLACEBO_P95}
    for v in variants:
        if v == "B1":
            arr = np.full(len(d), np.nan)
            m_uni = d.merge(uni[["T", "sym", "k", "B1"]], on=["T", "sym", "k"], how="left")["B1"].to_numpy()
            arr = m_uni
        else:
            m_uni = d.merge(uni[["T", "sym", "k", v]], on=["T", "sym", "k"], how="left")[v].to_numpy()
            arr = m_uni
        sc = H5.score(d, arr, f"kelly_{v}")
        # restrict to requested year-indices for selection display
        want = {str(H5.ANCHORS[i].date()) for i in years}
        yrows = [r for r in sc["years"] if r["year"] in want]
        # raw (no rescale) sums for the same years
        raw_rows = []
        for yi in years:
            y, a0, tr, te = folds[yi]
            sd = d.size_dep.to_numpy()[te]
            yy = d.y_dep.to_numpy()[te]
            sn = arr[te]
            ok = np.isfinite(sn)
            snr = np.where(ok, sn, sd)
            Sb = float((sd * yy).sum())
            Sn = float((snr * yy).sum())
            day = d["T"][te].dt.floor("D").to_numpy()
            td = float(pd.Series(sd * yy).groupby(day).sum().min())
            tn = float(pd.Series(snr * yy).groupby(day).sum().min())
            raw_rows.append({"year": str(a0.date()), "S_dep_raw": round(Sb, 4),
                             "S_new_raw": round(Sn, 4), "gain_raw": round(Sn - Sb, 4),
                             "worst_dep": round(td, 4), "worst_new": round(tn, 4)})
        res["variants"][v] = {"harness_eqexp": {"years": yrows,
                                                "total_gain": sc["total_gain"],
                                                "graduates": sc["graduates"]},
                              "raw": raw_rows}
        print(v, json.dumps(res["variants"][v]), flush=True)
    # placebo side row (unit caveat: harness single-grid units vs 4-phase-mean w*y)
    for v in [x for x in FRAC if x in res["variants"]]:
        g = sum(r["gain_raw"] for r in res["variants"][v]["raw"])
        res["variants"][v]["dSum_raw_vs_placebo_p95"] = {
            "dSum_raw": round(g, 4), "gate": PLACEBO_P95,
            "pass": bool(g >= PLACEBO_P95),
            "caveat": "single-grid harness units; placebo +0.273 is 4-phase-mean w*y (~3.5% of base 7.718)"}
    (HERE / "tmp" / ("replica_dev4.json" if years == [0, 1, 2, 3]
                      else "replica_last.json")).write_text(json.dumps(res, indent=1))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["baseline", "fit", "replica", "replica_last",
                             "engine_dev", "engine_last", "all"])
    a = ap.parse_args()
    (HERE / "tmp").mkdir(parents=True, exist_ok=True)
    if a.stage in ("baseline", "all"):
        stage_baseline()
    if a.stage in ("fit", "all"):
        import harness5 as H5
        d = H5.load()
        fit_tables(H5, d)
    if a.stage in ("replica", "all"):
        assert (HERE / "tmp" / "fit_tables.json").exists(), "run --stage fit first"
        stage_replica([0, 1, 2, 3])
    if a.stage == "replica_last":
        stage_replica([4])
    if a.stage == "engine_dev":
        from engine_kelly import run_engine_dev
        run_engine_dev()
    if a.stage == "engine_last":
        from engine_kelly import run_engine_last
        run_engine_last()


if __name__ == "__main__":
    main()
