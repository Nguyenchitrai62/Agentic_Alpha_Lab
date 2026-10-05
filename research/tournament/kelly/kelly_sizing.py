"""kelly: distributional / risk-adjusted dip-rung sizing (see PLAN.md, pre-registered). Dev-only data (< 2025-09-24); one run.

Usage: .venv/Scripts/python.exe research/tournament/kelly/kelly_sizing.py
Writes score_<variant>.json and diagnostics.json in this folder.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import harness as H  # noqa: E402

BO_FEATS = ["bo_sp30", "bo_volreg", "bo_trend", "bo_btc_sp30", "bo_dd24", "hour", "r1h", "r4h", "r24h", "r72h", "rng24", "dd7", "du7",
            "rv24", "btc_r4h", "btc_r24h", "btc_dd24"]
FEATS = BO_FEATS + ["k", "tp", "lsig"]
HGB = dict(max_depth=3, learning_rate=0.05, max_iter=300, min_samples_leaf=200, early_stopping=False, random_state=0)


def build():
    d = H.load()
    bo = pd.read_parquet(HERE.parent / "data/bar_open.parquet")
    assert not bo.duplicated(["j", "sym", "r"]).any() and not d.duplicated(["j", "sym", "r"]).any()
    n0 = len(d)
    d = d.merge(bo, on=["j", "sym", "r"], how="left", validate="one_to_one", indicator=True)
    assert len(d) == n0 and (d._merge == "both").all(), "bar_open join failed"
    d = d.drop(columns="_merge")
    # sanity of the join: the bar-open hour must equal the bar open T's hour
    assert (d.hour.astype(int) == d["T"].dt.hour).all(), "hour mismatch after join"
    d["tp"] = d.tp_dep.fillna(1.0)
    # volatility proxy: 2 x std of hourly log returns over the 168 hourly closes ending at T (hour start <= T - 1 h)
    h = pd.read_parquet(HERE.parent / "data/hourly.parquet").sort_values(["sym", "t"])
    h["lr"] = np.log(h.close).groupby(h.sym).diff()
    h["sig"] = 2 * h.groupby("sym").lr.transform(lambda s: s.rolling(168, min_periods=48).std())
    q = d[["sym", "T"]].copy()
    q["tq"] = q["T"] - pd.Timedelta(hours=1)
    q["_i"] = np.arange(len(q))
    q = q.sort_values("tq")
    m = pd.merge_asof(q, h[["sym", "t", "sig"]].sort_values("t"), left_on="tq", right_on="t", by="sym", direction="backward",
                      tolerance=pd.Timedelta(hours=6))
    m = m.sort_values("_i")
    assert (m.t.isna() | (m.t <= m["T"] - pd.Timedelta(hours=1))).all()
    d["sig"] = m.sig.to_numpy()
    d["lsig"] = np.log(d.sig)
    return d


def fit_pred(make, X, y, tr, te, half):
    """Cross-fit on j % 2 halves of the training rows. Returns (oof prediction on train rows, mean prediction on test rows)."""
    oof = np.full(tr.sum(), np.nan)
    pte = []
    Xtr, ytr, htr = X[tr], y[tr], half[tr]
    for hv in (0, 1):
        mdl = make().fit(Xtr[htr == hv], ytr[htr == hv])
        p_o = mdl.predict(Xtr[htr != hv]) if not hasattr(mdl, "predict_proba") else mdl.predict_proba(Xtr[htr != hv])
        p_t = mdl.predict(X[te]) if not hasattr(mdl, "predict_proba") else mdl.predict_proba(X[te])
        if p_o.ndim == 2:
            oof = oof if oof.ndim == 2 else np.full((tr.sum(), p_o.shape[1]), np.nan)
            oof[htr != hv] = p_o
        else:
            oof[htr != hv] = p_o
        pte.append(p_t)
    return oof, (pte[0] + pte[1]) / 2


def scale_c(raw_tr):
    """c such that mean(clip(c raw, 0, 2)) = 1 over the training rows."""
    raw_tr = np.nan_to_num(raw_tr, nan=0.0)
    lo, hi = 0.0, 1.0
    while np.clip(hi * raw_tr, 0, 2).mean() < 1 and hi < 1e12:
        hi *= 2
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if np.clip(mid * raw_tr, 0, 2).mean() < 1 else (lo, mid)
    return (lo + hi) / 2


def main():
    d = build()
    X = d[FEATS].to_numpy(float)
    y = d.y_dep.to_numpy(float)
    half = (d.j.to_numpy() % 2).astype(int)
    sizes = {v: np.full(len(d), np.nan) for v in ("V1_quantile_kelly", "V2_meanvar", "V3_bucket_ev")}
    mus = {v: np.full(len(d), np.nan) for v in sizes}
    diag = []
    for yi, a0, tr, te in H.folds(d):
        sig = d.sig.to_numpy()
        sig_med = np.nanmedian(sig[tr])
        sg = np.where(np.isfinite(sig), sig, sig_med)
        sg_tr, sg_te = sg[tr], sg[te]
        stop = (y < -2 * sg).astype(int)
        rec = dict(year=str(a0.date()), n_train=int(tr.sum()), n_test=int(te.sum()), stop_rate_train=round(float(stop[tr].mean()), 4))

        # ---- V1 quantile + stop probability
        Q = {}
        for qq in (0.1, 0.5, 0.9):
            Q[qq] = fit_pred(lambda: HistGradientBoostingRegressor(loss="quantile", quantile=qq, **HGB), X, y, tr, te, half)
        ps_o, ps_t = fit_pred(lambda: HistGradientBoostingClassifier(**HGB), X, stop, tr, te, half)
        ps_o, ps_t = ps_o[:, 1], ps_t[:, 1]
        m_stop = float(np.mean(y[tr][stop[tr] == 1] / sg_tr[stop[tr] == 1]))

        def v1(q10, q50, q90, ps, s):
            mu = 0.3 * q10 + 0.4 * q50 + 0.3 * q90
            V = np.maximum(q50 - q10, 0) ** 2 + ps * (s * m_stop) ** 2
            return mu, np.maximum(mu, 0) / np.maximum(V, 1e-10)
        _, raw_o = v1(Q[0.1][0], Q[0.5][0], Q[0.9][0], ps_o, sg_tr)
        mu_t, raw_t = v1(Q[0.1][1], Q[0.5][1], Q[0.9][1], ps_t, sg_te)
        c = scale_c(raw_o)
        sizes["V1_quantile_kelly"][te] = np.clip(c * raw_t, 0, 2)
        mus["V1_quantile_kelly"][te] = mu_t
        rec["V1"] = dict(m_stop=round(m_stop, 3), c=c, train_zero_share=round(float((c * raw_o <= 0).mean()), 3))

        # ---- V2 mean + |residual| model
        mo, mt = fit_pred(lambda: HistGradientBoostingRegressor(**HGB), X, y, tr, te, half)
        e = np.abs(y[tr] - mo)
        rm = HistGradientBoostingRegressor(**HGB).fit(X[tr], e)
        sd_o = np.sqrt(np.pi / 2) * np.maximum(rm.predict(X[tr]), 1e-4)
        sd_t = np.sqrt(np.pi / 2) * np.maximum(rm.predict(X[te]), 1e-4)
        raw_o, raw_t = np.maximum(mo, 0) / sd_o ** 2, np.maximum(mt, 0) / sd_t ** 2
        c = scale_c(raw_o)
        sizes["V2_meanvar"][te] = np.clip(c * raw_t, 0, 2)
        mus["V2_meanvar"][te] = mt
        rec["V2"] = dict(c=c, train_zero_share=round(float((raw_o <= 0).mean()), 3))

        # ---- V3 three outcome buckets
        bucket = np.where(y > 0, 0, np.where(stop == 1, 2, 1))
        po, pt = fit_pred(lambda: HistGradientBoostingClassifier(**HGB), X, bucket, tr, te, half)
        z = y / sg
        tpv = d.tp.to_numpy()
        m1 = np.zeros((3, len(d))); m2 = np.zeros((3, len(d)))
        cells = {}
        for cc in range(3):
            bm = tr & (bucket == cc)
            a1, a2 = z[bm].mean(), (z[bm] ** 2).mean()
            m1[cc], m2[cc] = a1, a2
            for t in (0.5, 1.0, 1.5):
                cm = bm & (tpv == t)
                if cm.sum() >= 50:
                    m1[cc, tpv == t], m2[cc, tpv == t] = z[cm].mean(), (z[cm] ** 2).mean()
                cells[f"{cc}_{t}"] = int(cm.sum())

        def v3(P, idx, s):
            mu = s * sum(P[:, cc] * m1[cc, idx] for cc in range(3))
            E2 = s ** 2 * sum(P[:, cc] * m2[cc, idx] for cc in range(3))
            V = np.maximum(E2 - mu ** 2, 1e-8)
            return mu, np.maximum(mu, 0) / V
        _, raw_o = v3(po, np.where(tr)[0], sg_tr)
        mu_t, raw_t = v3(pt, np.where(te)[0], sg_te)
        c = scale_c(raw_o)
        sizes["V3_bucket_ev"][te] = np.clip(c * raw_t, 0, 2)
        mus["V3_bucket_ev"][te] = mu_t
        rec["V3"] = dict(c=c, cells=cells, train_zero_share=round(float((raw_o <= 0).mean()), 3))

        for v in sizes:
            s_te = sizes[v][te]
            rec[v] = dict(ic_mu_y=round(float(pd.Series(mus[v][te]).corr(pd.Series(y[te]), method="spearman")), 4),
                          skip_share=round(float((s_te <= 0).mean()), 3), at_cap_share=round(float((s_te >= 2).mean()), 3),
                          mean_size_raw=round(float(s_te.mean()), 3))
        rec["ic_sizedep_y"] = round(float(pd.Series(d.size_dep.to_numpy()[te]).corr(pd.Series(y[te]), method="spearman")), 4)
        diag.append(rec)
        print(json.dumps(rec), flush=True)

    out = {}
    for v, s in sizes.items():
        res = H.score(d, s, v)
        (HERE / f"score_{v}.json").write_text(json.dumps(res, indent=1))
        out[v] = res
        print(json.dumps(res), flush=True)
    (HERE / "diagnostics.json").write_text(json.dumps(diag, indent=1, default=float))
    pd.DataFrame(sizes).assign(sym=d.sym.to_numpy(), T=d["T"].to_numpy(), sig=d.sig.to_numpy()).to_parquet(HERE / "sizes.parquet")


if __name__ == "__main__":
    main()
