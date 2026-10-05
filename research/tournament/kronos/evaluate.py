"""Evaluation of the zero-shot Kronos features (PLAN.md): (a) book IC tables, (b) dip sizing variants V1-V3 scored once with the harness.
Usage: python evaluate.py [features_file] [tag]   (tag '' = primary Kronos-small run; DIP variants are scored only for the primary run)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
import harness  # noqa: E402

FEAT_FILE = HERE / (sys.argv[1] if len(sys.argv) > 1 else "kronos_4h_features.parquet")
TAG = sys.argv[2] if len(sys.argv) > 2 else ""
KF = ["er1", "er6", "vol1", "vol6", "rng1", "low1", "pdrop2", "pdrop3"]
YEARS = [(str(a.date()), a, a + pd.Timedelta(days=365)) for a in harness.ANCHORS]


def md(df, index=True):
    df = df.reset_index() if index else df
    cols = [str(c) for c in df.columns]
    fmt = lambda v: f"{v:.4f}" if isinstance(v, (float, np.floating)) else str(v)
    rows = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    rows += ["| " + " | ".join(fmt(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(rows)


def sp(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    return float(pd.Series(a[m]).corr(pd.Series(b[m]), method="spearman")) if m.sum() > 30 else np.nan


def book_table(k):
    bars = pd.read_parquet(HERE / "bars_4h.parquet")
    lab = []
    for sym, b in bars.groupby("sym"):
        b = b.sort_values("T").reset_index(drop=True)
        lo = np.log(b.open.to_numpy())
        ret = np.r_[np.nan, np.diff(lo)]
        n = len(lo)
        nxt = lambda h: np.r_[lo[h:], np.full(h, np.nan)] - lo  # NaN where the label needs bars >= 2025-09-24 (never read)
        lab.append(pd.DataFrame(dict(sym=sym, T=b["T"], r1raw=nxt(1), f42raw=nxt(42), last1=ret,
                                     sig42=pd.Series(ret).rolling(42).std().to_numpy())))
    lab = pd.concat(lab)
    x = k.merge(lab, on=["sym", "T"], how="left")
    x["r1"] = x.r1raw / x.sigma
    x["f42"] = x.f42raw / (x.sigma * np.sqrt(42))
    x["absr1"] = x.r1raw.abs()
    x["absr1s"] = x["absr1"] / x.sigma
    x["vol1raw"] = x.vol1 * x.sigma
    x["sig42ratio"] = x.sig42 / x.sigma
    x["year"] = None
    for y, a0, a1 in YEARS:
        x.loc[(x["T"] >= a0) & (x["T"] < a1), "year"] = y
    return x[x.year.notna()].copy()


def ic_tables(x):
    out = {}
    for lab in ("f42", "r1"):
        rows = []
        for f in KF:
            r = dict(feature=f)
            for y, *_ in YEARS:
                g = x[x.year == y]
                r[f"{y} pooled"] = sp(g[f].to_numpy(), g[lab].to_numpy())
                r[f"{y} coin-avg"] = np.nanmean([sp(h[f].to_numpy(), h[lab].to_numpy()) for _, h in g.groupby("sym")])
            pooled = [r[f"{y} pooled"] for y, *_ in YEARS]
            r["mean pooled"] = float(np.mean(pooled))
            r["years>0"] = int(sum(v > 0 for v in pooled))
            rows.append(r)
        out[lab] = pd.DataFrame(rows).set_index("feature").round(4)
        rows = []
        for f in KF:
            r = dict(feature=f)
            for s, h in x.groupby("sym"):
                r[s] = sp(h[f].to_numpy(), h[lab].to_numpy())
            rows.append(r)
        out[lab + "_by_coin"] = pd.DataFrame(rows).set_index("feature").round(4)
    rows = []
    for name, f, lab in [("Kronos vol1 raw vs abs(r1)", "vol1raw", "absr1"), ("trailing sigma360 vs abs(r1)", "sigma", "absr1"),
                         ("trailing sigma42 vs abs(r1)", "sig42", "absr1"), ("Kronos rng1*sigma vs abs(r1)", "rng1raw", "absr1"),
                         ("INCREMENTAL Kronos vol1 vs abs(r1)/sigma", "vol1", "absr1s"), ("INCREMENTAL Kronos rng1 vs abs(r1)/sigma", "rng1", "absr1s"),
                         ("INCREMENTAL sigma42/sigma vs abs(r1)/sigma", "sig42ratio", "absr1s")]:
        r = dict(test=name)
        for y, *_ in YEARS:
            g = x[x.year == y]
            r[f"{y} coin-avg"] = np.nanmean([sp(h[f].to_numpy(), h[lab].to_numpy()) for _, h in g.groupby("sym")])
        rows.append(r)
    out["vol"] = pd.DataFrame(rows).set_index("test").round(4)
    x["last1s"] = x.last1 / x.sigma
    rows = []
    for lab in ("r1", "f42"):
        r = dict(test=f"naive baseline: last 4h return / sigma vs {lab}")
        for y, *_ in YEARS:
            g = x[x.year == y]
            r[f"{y} pooled"] = sp(g.last1s.to_numpy(), g[lab].to_numpy())
        rows.append(r)
    out["naive_baseline"] = pd.DataFrame(rows).set_index("test").round(4)
    rows = []
    for f in KF:
        rows.append(dict(feature=f, corr_with_last_bar_return=sp(x[f].to_numpy(), (x.last1 / x.sigma).to_numpy()),
                         corr_with_sigma42_ratio=sp(x[f].to_numpy(), x.sig42ratio.to_numpy()), mean=x[f].mean(), std=x[f].std()))
    out["descr"] = pd.DataFrame(rows).set_index("feature").round(4)
    return out


def dip(k):
    d = harness.load()
    bo = pd.read_parquet(ROOT / "research/tournament/data/bar_open.parquet")
    assert not bo.duplicated(["j", "sym", "r"]).any()
    bof = [c for c in bo.columns if c not in ("j", "sym", "r")]
    n0 = len(d)
    d = d.merge(bo, on=["j", "sym", "r"], how="left")  # harness rows (t_fill < 2025-09-24) keep their order
    assert len(d) == n0 and d.bo_trend.notna().mean() > 0.9
    d = d.merge(k[["sym", "T"] + KF], on=["sym", "T"], how="left")
    assert len(d) == n0
    maj = d.sym.isin(harness.MAJORS).to_numpy()
    print("majors rows with Kronos features:", int((maj & d.er1.notna()).sum()), "of", int(maj.sum()))
    v1, v2, v3 = (np.full(len(d), np.nan) for _ in range(3))
    info = []
    for y, a0, tr, te in harness.folds(d):
        trm = tr & maj
        # V1 rule
        risk = -d.low1.to_numpy()
        ok = trm & np.isfinite(risk)
        rho = sp(risk[ok], d.y_dep.to_numpy()[ok])
        q20, q80 = np.quantile(risk[ok], [0.2, 0.8])
        hi, lo_ = (1.5, 0.5) if rho > 0 else (0.5, 1.5)
        m = np.where(risk >= q80, hi, np.where(risk <= q20, lo_, 1.0))
        m = np.where(np.isfinite(risk), m, 1.0)
        v1[te] = d.size_dep.to_numpy()[te] * m[te]
        # V2 / V3 HGB
        for arr, cols in ((v2, bof + ["k"] + KF), (v3, bof + ["k"])):
            Xtr, ytr = d.loc[trm, cols].to_numpy(float), d.y_dep.to_numpy()[trm]
            mdl = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, random_state=0)
            mdl.fit(Xtr, ytr)
            pr = mdl.predict(d.loc[te, cols].to_numpy(float))
            mu = ytr.mean()
            arr[te] = np.where(pr > 2 * mu, 1.5, np.where(pr < 0, 0.5, 1.0))
        info.append(dict(year=str(a0.date()), n_train_majors=int(trm.sum()), n_train_with_kronos=int(ok.sum()), v1_rho_train=round(rho, 4),
                         v1_q20=round(float(q20), 4), v1_q80=round(float(q80), 4), train_mean_y=round(float(d.y_dep.to_numpy()[trm].mean()), 5)))
    # descriptive (NOT used for any choice): test-row IC of each Kronos feature vs y_dep per year
    desc = []
    for y, a0, tr, te in harness.folds(d):
        desc.append(dict(year=str(a0.date()), **{f: round(sp(d[f].to_numpy()[te], d.y_dep.to_numpy()[te]), 4) for f in KF}))
    res = {}
    for name, arr in (("V1_rule_low1", v1), ("V2_hgb_bar_open_plus_kronos", v2), ("V3_hgb_bar_open_only_control", v3)):
        r = harness.score(d, arr, name)
        r["fold_info"] = info if name.startswith("V1") else None
        (HERE / f"score_{name.split('_')[0]}.json").write_text(json.dumps(r, indent=1))
        res[name] = r
    return res, pd.DataFrame(desc).set_index("year"), info


def main():
    k = pd.read_parquet(FEAT_FILE)
    k["rng1raw"] = k.rng1 * k.sigma
    x = book_table(k)
    t = ic_tables(x)
    lines = [f"# IC tables {TAG or 'Kronos-small'} (rows: {len(x)}, coins: {x.sym.nunique()})\n"]
    for key, df in t.items():
        lines.append(f"\n## {key}\n\n" + md(df) + "\n")
    if not TAG:
        res, desc, info = dip(k)
        lines.append("\n## DIP test-row IC of Kronos features vs y_dep (descriptive only)\n\n" + md(desc) + "\n")
        lines.append("\n## DIP fold info (V1)\n\n" + md(pd.DataFrame(info), index=False) + "\n")
        for name, r in res.items():
            lines.append(f"\n## {name}: total gain {r['total_gain']}, graduates {r['graduates']}\n\n" + md(pd.DataFrame(r["years"]), index=False) + "\n")
    (HERE / f"eval_tables{('_' + TAG) if TAG else ''}.md").write_text("".join(lines), encoding="utf-8")
    print("".join(lines))


if __name__ == "__main__":
    main()
