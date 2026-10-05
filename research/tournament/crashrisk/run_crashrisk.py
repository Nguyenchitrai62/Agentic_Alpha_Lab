"""crashrisk: walk-forward crash-risk models, AUC / IC per test year, dial variants D1-D3 and the R2 / R2K portfolio screen (see PLAN.md).

Reads panel.parquet (build_panel.py) and v391_runs.pkl (dev equity paths, bar end <= 2025-09-24 07:00; only used as returns to dial).
Each variant is scored once. Writes results.json, dial_hourly.parquet (m per hour T for each variant) and, only if the pre-registered step-4
rule passes, tables/riskmult_s{s}.parquet.

  .venv/Scripts/python.exe research/tournament/crashrisk/run_crashrisk.py
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from build_panel import CUT, FEATS

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNS = ROOT / "research/parallel/rounds/parallel-20260906-r2/v391/v391_runs.pkl"
ANCH = [pd.Timestamp(a, tz="UTC") for a in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")]
EMB = pd.Timedelta(days=7)
H24 = pd.Timedelta(hours=24)
YEAR = pd.Timedelta(days=365)
HGB = dict(max_depth=3, min_samples_leaf=200, learning_rate=0.05, max_iter=200, l2_regularization=1.0, early_stopping=False, random_state=0)
VARIANTS = {"D1_clf_80_95": ("clf", 80, 95), "D2_clf_90_99": ("clf", 90, 99), "D3_reg_80_95": ("reg", 80, 95)}


def fit(kind, X, y):
    if kind == "clf":
        return HistGradientBoostingClassifier(**HGB).fit(X, y.astype(int))
    if kind == "reg":
        return HistGradientBoostingRegressor(**HGB).fit(X, y)
    med = np.nanmedian(X, 0)
    Xi = np.where(np.isnan(X), med, X)
    mu, sd = Xi.mean(0), Xi.std(0) + 1e-12
    lr = LogisticRegression(C=1.0, max_iter=2000).fit((Xi - mu) / sd, y.astype(int))
    return ("logit", lr, med, mu, sd)


def pred(model, X):
    if isinstance(model, tuple):
        _, lr, med, mu, sd = model
        return lr.predict_proba((np.where(np.isnan(X), med, X) - mu) / sd)[:, 1]
    if isinstance(model, HistGradientBoostingClassifier):
        return model.predict_proba(X)[:, 1]
    return model.predict(X)


def oof(kind, T, X, y, nb=5):
    """Out-of-fold predictions on the training rows: contiguous chronological blocks, 8-day purge around the held-out block."""
    out = np.full(len(y), np.nan)
    edges = np.linspace(0, len(y), nb + 1).astype(int)
    for b in range(nb):
        i0, i1 = edges[b], edges[b + 1]
        t0, t1 = T[i0], T[i1 - 1]
        tr = (T < t0 - EMB - H24) | (T > t1 + EMB + H24)
        m = fit(kind, X[tr], y[tr])
        out[i0:i1] = pred(m, X[i0:i1])
    return out


def mult(score, lo, hi):
    return np.clip(1.0 - 0.5 * (score - lo) / np.maximum(hi - lo, 1e-12), 0.5, 1.0)


# ---------------- portfolio screen (v388 hourly / mix / year_stats, copied) ----------------
def hourly(run, g0, g1):
    t = pd.to_datetime(run["t"], utc=True)
    grid = pd.date_range(g0, g1, freq="1h")
    e = pd.Series(run["eq"], index=t).reindex(grid, method="ffill").fillna(1.0)
    lo = pd.Series(run["eq_min"], index=t - pd.Timedelta(hours=4)).reindex(grid, method="ffill").fillna(1.0)
    return e, np.minimum(lo, e)


def mix(runs, g1=pd.Timestamp("2025-09-24 12:00", tz="UTC")):
    hs = [hourly(runs[s], pd.Timestamp("2021-09-24 04:00", tz="UTC"), g1) for s in range(4)]
    return sum(h[0] for h in hs) / 4, sum(h[1] for h in hs) / 4


def year_stats(e, mn, ys):
    nets, dds = [], []
    for y in ys:
        a0 = ANCH[y]
        seg = (e.index > a0) & (e.index <= a0 + YEAR)
        b = float(e[e.index <= a0].iloc[-1]) if (e.index <= a0).any() else 1.0
        es, ms = e[seg] / b, mn[seg] / b
        pk = np.maximum.accumulate(np.concatenate([[1.0], es.to_numpy()]))[1:]
        nets.append(float(es.iloc[-1] - 1))
        dds.append(100 * float(np.max(1 - ms.to_numpy() / pk)))
    return dict(R=round(100 * (np.prod([1 + x for x in nets]) ** (1 / (12 * len(ys))) - 1), 3),
                W=round(min(100 * ((1 + x) ** (1 / 12) - 1) for x in nets), 3), DD=round(max(dds), 2), losing=sum(x < 0 for x in nets),
                year_R=[round(100 * ((1 + x) ** (1 / 12) - 1), 3) for x in nets], year_DD=[round(x, 2) for x in dds])


def full_dd(e, mn):
    seg = e.index > ANCH[0]
    b = float(e[e.index <= ANCH[0]].iloc[-1]) if (e.index <= ANCH[0]).any() else 1.0
    es, ms = e[seg].to_numpy() / b, mn[seg].to_numpy() / b
    pk = np.maximum.accumulate(np.concatenate([[1.0], es]))[1:]
    i = int(np.argmax(1 - ms / pk))
    return round(100 * float(np.max(1 - ms / pk)), 2), str(e[seg].index[i])


def dial_run(run, mfun):
    t = pd.to_datetime(run["t"], utc=True)
    m = mfun(t - pd.Timedelta(hours=4))
    eq, mn = np.asarray(run["eq"], float), np.asarray(run["eq_min"], float)
    prev = np.concatenate([[1.0], eq[:-1]])
    r, rm = eq / prev - 1, mn / prev - 1
    e2 = np.cumprod(1 + m * r)
    p2 = np.concatenate([[1.0], e2[:-1]])
    return dict(t=run["t"], eq=e2.tolist(), eq_min=(p2 * (1 + m * rm)).tolist()), m


def stats(runs):
    e, mn = mix(runs)
    out = year_stats(e, mn, [0, 1, 2, 3])
    out["DD_full"], out["DD_full_at"] = full_dd(e, mn)
    return out


def main():
    P = pd.read_parquet(HERE / "panel.parquet")
    P["T"] = pd.to_datetime(P["T"], utc=True)
    P = P[P["T"] < CUT].sort_values("T").reset_index(drop=True)          # T >= 2025-09-24 -> neutral m (PLAN)
    T = P["T"].to_numpy()
    Tser = P["T"]
    X = P[FEATS].to_numpy(float)
    res = {"base_rate": {}, "folds": {}, "variants": {}}
    lab = P.crash24.notna()
    res["base_rate"]["all"] = round(float(P.crash24[lab].mean()), 4)
    score_h = {k: pd.Series(np.nan, index=Tser) for k in ("clf", "reg", "logit")}
    thr = {}
    for y, A in enumerate(ANCH):
        tr = (lab & (Tser + H24 < A - EMB)).to_numpy()
        A1 = A + YEAR if y < 3 else CUT
        te = ((Tser >= A) & (Tser < A1)).to_numpy()
        tel = te & lab.to_numpy()
        Ttr, Xtr = T[tr], X[tr]
        yc, yr = P.crash24.to_numpy()[tr], P.mdd24.to_numpy()[tr]
        fr = {"n_train": int(tr.sum()), "train_pos_rate": round(float(yc.mean()), 4), "train_end": str(Tser[tr].max()),
              "n_test": int(te.sum()), "test_base_rate": round(float(P.crash24[tel].mean()), 4)}
        preds = {}
        for kind, ytr in (("clf", yc), ("reg", yr), ("logit", yc)):
            m = fit(kind, Xtr, ytr)
            preds[kind] = pred(m, X[te])
            score_h[kind].iloc[np.where(te)[0]] = preds[kind]
            if kind in ("clf", "reg"):
                o = oof(kind, Ttr, Xtr, ytr)
                thr[(y, kind)] = {q: float(np.nanpercentile(o, q)) for q in (80, 90, 95, 99)}
                fr[f"thr_{kind}"] = {q: round(v, 5) for q, v in thr[(y, kind)].items()}
                fr[f"oof_auc_{kind}"] = round(float(roc_auc_score(yc, o) if kind == "clf" else spearmanr(o, yr)[0]), 4)
        ytc, ytr_ = P.crash24.to_numpy()[tel], P.mdd24.to_numpy()[tel]
        sel = tel[te]
        for kind in ("clf", "reg", "logit"):
            p = preds[kind][sel]
            fr[f"auc_{kind}"] = round(float(roc_auc_score(ytc, p)), 4)
            fr[f"ic_mdd_{kind}"] = round(float(spearmanr(p, ytr_)[0]), 4)
            top = p >= np.quantile(p, 0.9)
            fr[f"top10_rate_{kind}"] = round(float(ytc[top].mean()), 4)
        # simple causal reference: current market drawdown / vol term structure alone (no fit)
        for c in ("m_vts", "j_vts", "x_br2"):
            v = P[c].to_numpy()[tel]
            ok = np.isfinite(v)
            fr[f"auc_raw_{c}"] = round(float(roc_auc_score(ytc[ok], v[ok])), 4)
        res["folds"][str(A.date())] = fr
        print(A.date(), fr, flush=True)

    # hourly dial series per variant
    def fold_of(ts):
        return np.searchsorted(np.array([a.value for a in ANCH]), pd.DatetimeIndex(ts).asi8, side="right") - 1

    dials = {}
    for name, (kind, qlo, qhi) in VARIANTS.items():
        s = score_h[kind]
        f = fold_of(s.index)
        lo = np.array([thr[(max(k, 0), kind)][qlo] for k in f])
        hi = np.array([thr[(max(k, 0), kind)][qhi] for k in f])
        m = pd.Series(mult(s.to_numpy(), lo, hi), index=s.index)
        m[(f < 0) | s.isna().to_numpy()] = 1.0
        dials[name] = m
    D = pd.DataFrame(dials)
    D.index.name = "T"
    D.reset_index().to_parquet(HERE / "dial_hourly.parquet")

    def lookup(m):
        def g(ts):
            v = m.reindex(pd.DatetimeIndex(ts)).to_numpy()
            return np.where(np.isnan(v), 1.0, v)                        # T >= 2025-09-24 -> 1.0
        return g

    allruns = pickle.loads(RUNS.read_bytes())
    for strat in ("R2", "R2K"):
        base = stats({s: allruns[s][strat] for s in range(4)})
        res["variants"].setdefault("undialled", {})[strat] = base
        print(strat, "undialled", base, flush=True)
        for name, m in dials.items():
            dr, ms = {}, []
            for s in range(4):
                dr[s], mm = dial_run(allruns[s][strat], lookup(m))
                ms.append(mm)
            st = stats(dr)
            mbar = float(np.mean(np.concatenate(ms)))
            st["mean_m"], st["share_m_lt_1"], st["share_m_eq_05"] = round(mbar, 4), round(float(np.mean(np.concatenate(ms) < 1)), 4), \
                round(float(np.mean(np.concatenate(ms) <= 0.5 + 1e-12)), 4)
            st["mean_m_year"] = []
            for y, A in enumerate(ANCH):
                tt = pd.to_datetime(allruns[0][strat]["t"], utc=True) - pd.Timedelta(hours=4)
                sel = (tt >= A) & (tt < A + YEAR)
                st["mean_m_year"].append(round(float(ms[0][sel].mean()), 4))
            fl = {s: dial_run(allruns[s][strat], lambda ts, c=mbar: np.full(len(ts), c))[0] for s in range(4)}
            st["flat_same_mean"] = stats(fl)
            res["variants"].setdefault(name, {})[strat] = st
            print(strat, name, st, flush=True)

    # step-4 rule
    passing = []
    for name in VARIANTS:
        ok = False
        for strat in ("R2", "R2K"):
            b, v = res["variants"]["undialled"][strat], res["variants"][name][strat]
            ddrop = b["DD"] - v["DD"]
            ret_ok = v["R"] >= 5.0 if strat == "R2K" else v["R"] >= 0.9 * b["R"]
            ok |= bool(ddrop >= 2.0 and ret_ok)
            res["variants"][name][strat]["DD_drop"] = round(ddrop, 2)
            res["variants"][name][strat]["step4_ok"] = bool(ddrop >= 2.0 and ret_ok)
        if ok:
            passing.append(name)
    res["step4_passing"] = passing
    print("STEP 4 passing:", passing, flush=True)
    if passing:
        best = max(passing, key=lambda n: max(res["variants"][n][s]["DD_drop"] for s in ("R2", "R2K")
                                              if res["variants"][n][s]["step4_ok"]))
        res["step4_table_variant"] = best
        (HERE / "tables").mkdir(exist_ok=True)
        for s in range(4):
            Tb = pd.date_range(pd.Timestamp("2021-09-24", tz="UTC") + pd.Timedelta(hours=s),
                               pd.Timestamp("2025-09-24 08:00", tz="UTC") + pd.Timedelta(hours=s), freq="4h")
            mm = lookup(dials[best])(Tb)
            mm[Tb >= CUT] = 1.0
            pd.DataFrame({"T": Tb, "mult": mm}).to_parquet(HERE / f"tables/riskmult_s{s}.parquet")
            print("table", s, len(Tb), "mean", round(float(mm.mean()), 4), "neutral (T >= cut)", int((Tb >= CUT).sum()), flush=True)
    (HERE / "results.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
