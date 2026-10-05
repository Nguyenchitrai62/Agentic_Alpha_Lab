"""Engine tables of the pre-registered V2 meanvar sizes (exactly the scored model / rule) on the 4h grids shifted by s = 0..3 h.

For each phase s: holding bars T = START + s h + 4h j of the 5 majors, 2021-09-24 + s h <= T <= 2025-09-24 08:00 + s h, R2 rungs
k in (2.5, 3.0, 3.5, 4.0, 5.0). Features = prep_features.py definitions computed on the SHIFTED v293.Asset (kk = 240 j), lsig from hourly
closes (1m resampled to clock hours, exactly as hourly.parquet) of hours that closed by T, tp = deployed per-phase TP from
v376/tables_hidden/r2_table_s{s}.parquet (default 1.0). Fold model = anchor year containing T (refit identically to kelly_sizing.py:
same rows, features, seeds, cross-fit halves, residual model and scale c). Minute data: files of 2026 are never opened, every frame is cut
at 2025-09-25 on load; the TP table is filtered to the stated T range right after reading.
Checks -> tables/build_check.json: phase-0 match with sizes.parquet, per-phase stats, causality (features recomputed from 1m data
truncated at T + 1 min for 20 random (T, sym) per phase 0).
  .venv/Scripts/python.exe research/tournament/kelly/build_tables.py   (run from the repo root)
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import kelly_sizing as K

H = K.H
ROOT = H.ROOT
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OUT = K.HERE / "tables"
END = pd.Timestamp("2025-09-25", tz="UTC")
TMIN, TMAX = pd.Timestamp("2021-09-24", tz="UTC"), pd.Timestamp("2025-09-24 08:00", tz="UTC")
R2 = H.R2
MAJ = list(H.MAJORS)


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


v293 = L("v293_kelly", RD / "v293/v293_pooled_exit_agent.py")
v293.END = END
START0 = v293.START
_RAW = {}


def raw_1m(s):
    """Full 1m frame < END (cached per symbol; 2026 files skipped)."""
    if s not in _RAW:
        if s == "BTCUSDT":
            files = sorted((ROOT / "data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
        else:
            files = sorted((ROOT / "data/raw/majors_intraday_20260924").glob(f"{s}_1m_20*.parquet"))
        files = [f for f in files if "2026" not in f.name]
        m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in files])
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        m = m[m.open_time < END]
        _RAW[s] = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    return _RAW[s]


TRUNC = {}  # sym -> last allowed minute start (inclusive) for the causality test


def load_1m(s):
    m = raw_1m(s)
    m = m[(m.index >= v293.START) & (m.index < v293.END)]
    m = m.reindex(pd.date_range(v293.START, v293.END - pd.Timedelta(minutes=1), freq="1min"))
    if s in TRUNC:
        m = m.copy()
        m.loc[m.index > TRUNC[s]] = np.nan
    return m


v293.load_1m = load_1m


def logret(C, k, n):
    return np.log(C[k] / C[k - n]) if k - n >= 0 and C[k] > 0 and C[k - n] > 0 else np.nan


def bar_feats(A, btc, j):
    """prep_features.py, verbatim definitions."""
    kk = int(j) * 240
    sg = A.sig[j]
    C = A.C
    f = dict(bo_sp30=A.sp30(kk), bo_volreg=A.volreg[j], bo_trend=A.trend[j], bo_btc_sp30=btc.sp30(kk),
             bo_dd24=np.log(C[kk] / A.hmax24[kk]) / sg if A.hmax24[kk] > 0 else np.nan, hour=A.t0[j].hour)
    for n, name in ((60, "r1h"), (240, "r4h"), (1440, "r24h"), (4320, "r72h")):
        f[name] = logret(C, kk, n) / sg
    lo24 = np.nanmin(A.L[max(0, kk - 1439): kk + 1]); hi24 = np.nanmax(A.H[max(0, kk - 1439): kk + 1])
    hi7 = np.nanmax(A.H[max(0, kk - 10079): kk + 1]); lo7 = np.nanmin(A.L[max(0, kk - 10079): kk + 1])
    f["rng24"] = (hi24 - lo24) / C[kk] / sg
    f["dd7"], f["du7"] = np.log(C[kk] / hi7) / sg, np.log(C[kk] / lo7) / sg
    h1 = C[max(0, kk - 1440): kk + 1: 60]
    f["rv24"] = np.nanstd(np.diff(np.log(h1))) / (sg / 2) if len(h1) > 3 else np.nan
    f["btc_r4h"], f["btc_r24h"] = logret(btc.C, kk, 240) / btc.sig[j], logret(btc.C, kk, 1440) / btc.sig[j]
    f["btc_dd24"] = np.log(btc.C[kk] / btc.hmax24[kk]) / btc.sig[j] if btc.hmax24[kk] > 0 else np.nan
    return f


def hourly_sig(m, s):
    """kelly_sizing's lsig source: 1m -> clock-hour closes (as prep_features' hourly.parquet), 2 x rolling-168 std of log returns."""
    m = m[m.index >= START0]
    h = m.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    h = h[h.index < END].dropna(how="all").reset_index().rename(columns={"index": "t", "open_time": "t"})
    h["lr"] = np.log(h.close).diff()
    h["sig"] = 2 * h.lr.rolling(168, min_periods=48).std()
    return h.assign(sym=s)[["sym", "t", "close", "sig"]]


def attach_sig(df, hs):
    q = df[["sym", "T"]].copy()
    q["tq"] = q["T"] - pd.Timedelta(hours=1)
    q["_i"] = np.arange(len(q))
    m = pd.merge_asof(q.sort_values("tq"), hs[["sym", "t", "sig"]].sort_values("t"), left_on="tq", right_on="t", by="sym",
                      direction="backward", tolerance=pd.Timedelta(hours=6)).sort_values("_i")
    return m.sig.to_numpy()


def fit_v2():
    """Refit the scored V2 models per fold exactly as kelly_sizing.main; returns models and the reproduced test sizes."""
    d = K.build()
    X = d[K.FEATS].to_numpy(float); y = d.y_dep.to_numpy(float); half = (d.j.to_numpy() % 2).astype(int)
    models, rep = [], np.full(len(d), np.nan)
    for yi, a0, tr, te in H.folds(d):
        Xtr, ytr, htr = X[tr], y[tr], half[tr]
        oof = np.full(tr.sum(), np.nan); ms = []
        for hv in (0, 1):
            mdl = HistGradientBoostingRegressor(**K.HGB).fit(Xtr[htr == hv], ytr[htr == hv])
            oof[htr != hv] = mdl.predict(Xtr[htr != hv]); ms.append(mdl)
        rm = HistGradientBoostingRegressor(**K.HGB).fit(Xtr, np.abs(ytr - oof))
        sd_o = np.sqrt(np.pi / 2) * np.maximum(rm.predict(Xtr), 1e-4)
        c = K.scale_c(np.maximum(oof, 0) / sd_o ** 2)
        models.append((a0, ms, rm, c))
        rep[te] = v2_size(models[-1], X[te])
    return d, models, rep


def v2_size(model, X):
    a0, ms, rm, c = model
    mt = (ms[0].predict(X) + ms[1].predict(X)) / 2
    sd = np.sqrt(np.pi / 2) * np.maximum(rm.predict(X), 1e-4)
    return np.clip(c * np.maximum(mt, 0) / sd ** 2, 0, 2)


def phase_features(sft):
    """Bar-open feature rows (one per (T, sym)) for phase sft, plus the per-symbol hourly sig frame."""
    v293.START = START0 + pd.Timedelta(hours=sft)
    btc = v293.Asset("BTCUSDT")
    rows, hs = [], []
    for s in MAJ:
        A = btc if s == "BTCUSDT" else v293.Asset(s)
        for j, T in enumerate(A.t0):
            if T < TMIN + pd.Timedelta(hours=sft) or T > TMAX + pd.Timedelta(hours=sft):
                continue
            rows.append(dict(T=T, sym=s, j=j, **bar_feats(A, btc, j)))
        hs.append(hourly_sig(raw_1m(s), s))
        if s != "BTCUSDT":
            del A
    del btc
    return pd.DataFrame(rows), pd.concat(hs, ignore_index=True)


def main():
    OUT.mkdir(exist_ok=True)
    d, models, rep = fit_v2()
    S = pd.read_parquet(K.HERE / "sizes.parquet")
    scored = S.V2_meanvar.to_numpy()
    ok = np.isfinite(scored)
    check = dict(refit_reproduces_scored=float(np.nanmax(np.abs(rep[ok] - scored[ok]))))
    print("refit max abs diff vs scored", check["refit_reproduces_scored"], flush=True)
    # hourly.parquet parity of the lsig source
    hp = pd.read_parquet(K.HERE.parent / "data/hourly.parquet")
    hp = hp[hp.sym.isin(MAJ)]
    for sft in (0, 1, 2, 3):
        F, hs = phase_features(sft)
        if sft == 0:
            hp2 = hp.merge(hs, on=["sym", "t"], suffixes=("", "_mine"))
            check["hourly_close_parity"] = dict(rows_ref=len(hp), rows_matched=len(hp2),
                                                max_abs_rel_diff=float(np.nanmax(np.abs(hp2.close_mine / hp2.close - 1))))
        F["sig"] = attach_sig(F, hs)
        F["lsig"] = np.log(F.sig)
        tpt = pd.read_parquet(RD / f"v376/tables_hidden/r2_table_s{sft}.parquet")
        tpt = tpt[(tpt["T"] >= TMIN + pd.Timedelta(hours=sft)) & (tpt["T"] <= TMAX + pd.Timedelta(hours=sft))]
        G = F.loc[F.index.repeat(len(R2))].reset_index(drop=True)
        G["rung"] = np.tile(np.arange(len(R2)), len(F))
        G["k"] = np.array(R2)[G.rung]
        G = G.merge(tpt[["T", "sym", "rung", "tp"]], on=["T", "sym", "rung"], how="left")
        tp_missing = int(G.tp.isna().sum())
        G["tp"] = G.tp.fillna(1.0)
        X = G[K.FEATS].to_numpy(float)
        size = np.full(len(G), np.nan)
        for i, m in enumerate(models):
            hi = models[i + 1][0] if i + 1 < len(models) else pd.Timestamp("2100-01-01", tz="UTC")
            sel = ((G["T"] >= m[0]) & (G["T"] < hi)).to_numpy()
            if sel.any():
                size[sel] = v2_size(m, X[sel])
        assert np.isfinite(size).all()
        G["size"] = size
        tab = G[["T", "sym", "rung", "size"]]
        tab.to_parquet(OUT / f"kelly_v2_s{sft}.parquet")
        st = dict(rows=len(tab), T_min=str(tab["T"].min()), T_max=str(tab["T"].max()), hours=sorted(set(tab["T"].dt.hour)),
                  mean_size=round(float(tab["size"].mean()), 4), share_0=round(float((tab["size"] <= 0).mean()), 4),
                  share_2=round(float((tab["size"] >= 2).mean()), 4), tp_rows_missing_default_1=tp_missing,
                  lsig_nan=int(G.lsig.isna().sum()),
                  mean_size_by_anchor={str(m[0].date()): round(float(tab["size"][(tab["T"] >= m[0]).to_numpy() & (tab["T"] < (models[i + 1][0] if i + 1 < len(models) else pd.Timestamp("2100-01-01", tz="UTC"))).to_numpy()].mean()), 4) for i, m in enumerate(models)})
        if sft == 0:
            ref = d[["T", "sym", "k"]].assign(scored=scored, tp_h=d.tp.to_numpy())[ok]
            ref["rung"] = ref.k.map({k: r for r, k in enumerate(R2)}).astype(int)
            mg = ref.merge(G[["T", "sym", "rung", "size", "tp"] + K.BO_FEATS + ["lsig"]], on=["T", "sym", "rung"], how="left")
            dd = d[ok].reset_index(drop=True)
            st["match"] = dict(scored_rows=len(ref), found=int(mg["size"].notna().sum()),
                               max_abs_diff=float(np.nanmax(np.abs(mg["size"] - mg.scored))),
                               share_exact_1e9=float((np.abs(mg["size"] - mg.scored) < 1e-9).mean()),
                               tp_match=float((mg.tp == mg.tp_h).mean()),
                               feat_max_abs_diff={f: float(np.nanmax(np.abs(mg[f].to_numpy() - dd[f].to_numpy()))) for f in K.BO_FEATS + ["lsig"]})
            # causality: 20 random (T, sym), 1m data truncated at T (minute 0 kept, i.e. data up to T + 1 min)
            rng = np.random.default_rng(0)
            pick = F.sample(20, random_state=0)
            worst = 0.0
            for _, r in pick.iterrows():
                T, s = r["T"], r["sym"]
                TRUNC.clear(); TRUNC.update({s: T, "BTCUSDT": T})
                bt = v293.Asset("BTCUSDT"); At = bt if s == "BTCUSDT" else v293.Asset(s)
                ft = bar_feats(At, bt, int(r.j))
                m1 = raw_1m(s); m1 = m1[m1.index <= T]
                ht = hourly_sig(m1, s)
                ft["lsig"] = float(np.log(attach_sig(pd.DataFrame(dict(sym=[s], T=[T])), ht))[0])
                for f in K.BO_FEATS + ["lsig"]:
                    a, b = ft[f], r[f]
                    same = (np.isnan(a) and np.isnan(b)) or a == b
                    assert same, (T, s, f, a, b)
                    if np.isfinite(a) and np.isfinite(b):
                        worst = max(worst, abs(a - b))
                del bt, At
            TRUNC.clear()
            st["causality"] = dict(samples=20, all_identical=True, max_abs_diff=worst,
                                   picks=[f"{r['sym']} {r['T']}" for _, r in pick.iterrows()])
        check[f"s{sft}"] = st
        print("phase", sft, json.dumps(st), flush=True)
        del F, G, hs
    (OUT / "build_check.json").write_text(json.dumps(check, indent=1, default=str))


if __name__ == "__main__":
    main()
