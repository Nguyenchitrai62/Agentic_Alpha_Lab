"""context: engine tables of the pre-registered V2 hgb_mono sizes on the 4 phase-shifted 4h grids (dev-only, 2026-10-05).

Models: EXACTLY the scored V2 (run_variants.py): same rows, features, target, halves, seeds (10 * fold + half), monotonic constraints and
training means; verified by re-scoring the reproduced test sizes against score_hgb_mono.json.
Grid s (0..3): holding bars start at START0 + s h + 4h j (as research/diagnostics/phase_agents/build_tables.py). For every majors bar T in
[2021-09-24 + s h, 2025-09-24 08:00 + s h] and R2 rung k: the 7 bar-open features at T on THAT grid (prep_features.py definitions: kk = 240 j
on the shifted arrays, sigma / volreg / trend from the shifted grid's own 4h opens, sp30 / dd24 at the close of minute 0, hour = T.hour), the
market features at T (hourly bars starting <= T - 1h, build_market_features.build), the fold model of the anchor year containing T, rule
1.5 if both halves > 2 mu, 0.5 if both < 0, else 1.0.
DATA CUT: no 1m / hourly data at or after 2025-09-24 is read (pyarrow filter on read). Bars with T >= 2025-09-24 (minute 0 is at/after the cut)
cannot be computed and get the neutral size 1.0 (reported).
Output: tables/ctx_v2_s{s}.parquet (T, sym, rung, size), tables/ctx_v2_feat_s{s}.parquet (audit features), tables/check.json.

  .venv/Scripts/python.exe research/tournament/context/build_engine_tables.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import harness as H  # noqa: E402
from build_market_features import FEATS as MKT, build as build_mkt, load_hourly  # noqa: E402
from run_variants import ALL, BASE, MONO, hgb  # noqa: E402

ROOT = HERE.parents[2]
MAJORS = list(H.MAJORS)
R2 = H.R2
START0 = pd.Timestamp("2020-08-01", tz="UTC")
CUT = H.DEV_END                                   # 2025-09-24: nothing at or after is read
TMAX = pd.Timestamp("2025-09-24 08:00", tz="UTC")
OUT = HERE / "tables"
BO7 = ["bo_sp30", "bo_volreg", "bo_trend", "bo_btc_sp30", "bo_dd24", "hour"]   # + k


def load_1m(s):
    """v293.load_1m with the data cut applied on read (no row >= CUT is ever loaded)."""
    if s == "BTCUSDT":
        files = sorted((ROOT / "data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted((ROOT / "data/raw/majors_intraday_20260924").glob(f"{s}_1m_20*.parquet"))
    files = [f for f in files if int(f.stem[-4:]) <= CUT.year]
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"], filters=[("open_time", "<", CUT)]) for f in files])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    m = m[(m.index >= START0) & (m.index < CUT)]
    assert m.index.max() < CUT
    return m.reindex(pd.date_range(START0, CUT - pd.Timedelta(minutes=1), freq="1min"))


class Asset:
    """Copy of v293.Asset on a given 1m frame (starting at the grid start); nb = ceil so a frame truncated at T + 1 min keeps bar j's minute 0."""

    def __init__(self, m):
        self.O, self.H, self.L, self.C = (m[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        nb = -(-len(m) // 240)
        opens = self.O[: nb * 240: 240]
        pc = pd.Series(opens).pct_change()
        self.sig = pc.rolling(360, min_periods=120).std().shift(1).to_numpy()
        self.volreg = (pd.Series(self.sig) / pd.Series(self.sig).rolling(540, min_periods=180).median()).to_numpy()
        self.trend = (np.log(pd.Series(opens)) - np.log(pd.Series(opens).shift(42))).to_numpy() / (self.sig * np.sqrt(42))
        lr = np.diff(np.log(pd.Series(self.C).ffill().to_numpy()), prepend=np.nan)
        self.sig1 = pd.Series(lr).rolling(1440, min_periods=720).std().to_numpy()
        self.hmax24 = pd.Series(self.H).rolling(1440, min_periods=720).max().to_numpy()
        self.t0 = m.index[: nb * 240: 240]

    def sp30(self, k):
        if k < 30 or not (self.sig1[k] > 0):
            return np.nan
        return np.log(self.C[k] / self.C[k - 30]) / (self.sig1[k] * np.sqrt(30))


def bar_feats(A, btc, j):
    kk, sg = 240 * j, A.sig[j]
    return dict(bo_sp30=A.sp30(kk), bo_volreg=A.volreg[j], bo_trend=A.trend[j], bo_btc_sp30=btc.sp30(kk),
                bo_dd24=np.log(A.C[kk] / A.hmax24[kk]) / sg if A.hmax24[kk] > 0 else np.nan, hour=A.t0[j].hour)


def fit_models():
    d = H.load()
    keep = (pd.read_parquet(H.FILLS).t_fill < H.DEV_END).to_numpy()
    bo = pd.read_parquet(HERE.parent / "data/bar_open.parquet")[keep].reset_index(drop=True)
    assert (bo.j.to_numpy() == d.j.to_numpy()).all() and (bo.sym.to_numpy() == d.sym.to_numpy()).all() and (bo.r.to_numpy() == d.r.to_numpy()).all()
    mf = pd.read_parquet(HERE / "market_features.parquet")
    assert (mf["T"].to_numpy() == d["T"].to_numpy()).all() and (mf.sym.to_numpy() == d.sym.to_numpy()).all()
    F = pd.concat([bo[[c for c in BASE if c != "k"]], d[["k"]], mf[MKT]], axis=1)[ALL]
    X = F.to_numpy(float)
    y = np.clip(d["y1.0"].to_numpy(float), -0.10, 0.08)
    half = (d.j % 2).to_numpy()
    models, size = [], np.full(len(d), np.nan)
    for yi, a0, tr, te in H.folds(d):
        mu = float(y[tr].mean())
        ms = [hgb(10 * yi + h, MONO, ALL).fit(X[tr & (half == h)], y[tr & (half == h)]) for h in (0, 1)]
        models.append((a0, mu, ms))
        size[te] = rule(ms, mu, X[te])
    res = H.score(d, size, "hgb_mono")
    ref = json.loads((HERE / "score_hgb_mono.json").read_text())
    assert [r["gain"] for r in res["years"]] == [r["gain"] for r in ref["years"]] and res["total_gain"] == ref["total_gain"], "not the scored model"
    test = np.zeros(len(d), bool)
    for *_, te in H.folds(d):
        test |= te
    scored = d.loc[test, ["T", "sym", "k"]].assign(size_scored=size[test], **{c: F.loc[test, c].to_numpy() for c in ALL})
    return models, scored


def rule(ms, mu, X):
    pa, pb = (m.predict(X) for m in ms)
    return np.where((pa > 2 * mu) & (pb > 2 * mu), 1.5, np.where((pa < 0) & (pb < 0), 0.5, 1.0))


def phase_features(raw, s, hourly):
    sh = pd.Timedelta(hours=s)
    btc = Asset(raw["BTCUSDT"][raw["BTCUSDT"].index >= START0 + sh])
    rows = []
    for sy in MAJORS:
        A = btc if sy == "BTCUSDT" else Asset(raw[sy][raw[sy].index >= START0 + sh])
        for j, T in enumerate(A.t0):
            if T < H.ANCHORS[0] + sh or T > TMAX + sh:
                continue
            rows.append(dict(T=T, sym=sy, j=j, **bar_feats(A, btc, j)))
        if sy != "BTCUSDT":
            del A
    # bars at/after the data cut (minute 0 >= CUT) cannot be computed: rows with NaN features -> neutral size in predict_table
    last = max(r_["T"] for r_ in rows)
    for T in pd.date_range(last + pd.Timedelta(hours=4), TMAX + sh, freq="4h"):
        assert T >= CUT
        rows += [dict(T=T, sym=sy, j=-1) for sy in MAJORS]
    f = pd.DataFrame(rows)
    mk = build_mkt(hourly, f[["T", "sym"]])
    return pd.concat([f, mk], axis=1)


def predict_table(feat, models):
    rows = []
    for r, k in enumerate(R2):
        g = feat.assign(k=k, rung=r)
        rows.append(g)
    g = pd.concat(rows, ignore_index=True)
    X = g[ALL].to_numpy(float)
    size = np.ones(len(g))
    T = g["T"]
    fold = np.full(len(g), -1)
    for q, (a0, mu, ms) in enumerate(models):
        fold[(T >= a0).to_numpy()] = q
    ok = (T < CUT).to_numpy()                             # bars needing data >= CUT -> neutral 1.0
    for q, (a0, mu, ms) in enumerate(models):
        sel = ok & (fold == q)
        if sel.any():
            size[sel] = rule(ms, mu, X[sel])
    g["size"], g["fold"], g["computed"] = size, fold, ok
    return g


def causality(raw, hourly, feats, n=20, seed=11):
    rng = np.random.default_rng(seed)
    worst, done = 0.0, []
    for _ in range(n):
        s = int(rng.integers(4))
        f = feats[s]
        f = f[f["T"] < CUT]
        row = f.iloc[int(rng.integers(len(f)))]
        T, sy, sh = row["T"], row["sym"], pd.Timedelta(hours=s)
        cut = T + pd.Timedelta(minutes=1)                  # keep minutes <= T (minute 0 closes at T + 1 min)
        tr = {q: raw[q][(raw[q].index >= START0 + sh) & (raw[q].index < cut)] for q in {sy, "BTCUSDT"}}
        btc = Asset(tr["BTCUSDT"])
        A = btc if sy == "BTCUSDT" else Asset(tr[sy])
        j = int(row["j"])
        assert A.t0[j] == T and len(A.C) == 240 * j + 1
        b = bar_feats(A, btc, j)
        mk = build_mkt(hourly[hourly.t < T], pd.DataFrame({"T": [T], "sym": [sy]})).iloc[0]
        new = np.array([b[c] for c in BO7] + [mk[c] for c in MKT], float)
        old = row[BO7 + MKT].to_numpy(float)
        assert (np.isnan(new) == np.isnan(old)).all(), (s, T, sy)
        dd = float(np.nanmax(np.abs(new - old)))
        assert dd == 0.0, (s, T, sy, dd)
        worst = max(worst, dd)
        done.append(f"s{s} {T} {sy}")
    return dict(n=n, max_abs_diff=worst, rows=done)


def main():
    t0 = time.time()
    OUT.mkdir(exist_ok=True)
    models, scored = fit_models()
    print("models reproduced (score matches score_hgb_mono.json)", f"{time.time() - t0:.0f}s", flush=True)
    hourly = load_hourly()
    raw = {s: load_1m(s) for s in MAJORS}
    print("1m loaded, last minute", max(m.index.max() for m in raw.values()), f"{time.time() - t0:.0f}s", flush=True)
    check, feats = {"phases": {}}, {}
    for s in range(4):
        feat = phase_features(raw, s, hourly)
        feats[s] = feat
        g = predict_table(feat, models)
        tab = g[["T", "sym", "rung", "size"]].reset_index(drop=True)
        tab.to_parquet(OUT / f"ctx_v2_s{s}.parquet")
        g.drop(columns=["size"]).to_parquet(OUT / f"ctx_v2_feat_s{s}.parquet")
        check["phases"][s] = dict(rows=len(tab), bars=int(len(feat)), T_min=str(tab["T"].min()), T_max=str(tab["T"].max()),
                                  hours=sorted(set(int(h) for h in tab["T"].dt.hour)),
                                  size_counts={str(k): int(v) for k, v in tab["size"].value_counts().sort_index().items()},
                                  neutral_rows_T_ge_cut=int((~g.computed).sum()),
                                  size_counts_by_fold={str(H.ANCHORS[q].date()): {str(k): int(v) for k, v in g[g.fold == q]["size"].value_counts().sort_index().items()}
                                                       for q in range(4)})
        print("phase", s, check["phases"][s], f"{time.time() - t0:.0f}s", flush=True)
        if s == 0:
            sc = scored.assign(rung=scored.k.map({k: r for r, k in enumerate(R2)}).astype(int))
            m = sc.merge(g, on=["T", "sym", "rung"], how="left", suffixes=("_sc", ""))
            diff = np.abs(m["size"] - m["size_scored"])
            fd = {c: float(np.nanmax(np.abs(m[c + "_sc"].to_numpy(float) - m[c].to_numpy(float)))) for c in BO7 + MKT}
            nan_mis = {c: int((m[c + "_sc"].isna() != m[c].isna()).sum()) for c in BO7 + MKT}
            check["s0_vs_scored"] = dict(scored_rows=len(sc), matched=int(m["size"].notna().sum()), max_abs_diff=float(diff.max()),
                                         match_share=float((diff == 0).mean()), feature_max_abs_diff=fd, feature_nan_mismatch=nan_mis)
            print("s0 vs scored", check["s0_vs_scored"], flush=True)
    check["causality"] = causality(raw, hourly, feats)
    print("causality", check["causality"], flush=True)
    check["seconds"] = round(time.time() - t0)
    (OUT / "check.json").write_text(json.dumps(check, indent=1, default=str))


if __name__ == "__main__":
    main()
