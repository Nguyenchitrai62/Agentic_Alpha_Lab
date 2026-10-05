"""context: V2 hgb_mono size tables for the HIDDEN year (leader-authorised 2026-10-05, features only - no outcome is read or computed).

Recipe = run_variants.py V2 exactly, plus ONE new fold model: anchor 2025-09-24, trained on harness rows with t_exit < 2025-09-17 (anchor - 7 d),
same features / target clip(y1.0) / halves j % 2 / seeds 10 * 4 + half / monotonic constraints / training mean.
Market data read: 1m up to 2026-09-24 12:00 UTC (pyarrow filter on read). Hourly panel = research/tournament/data/hourly.parquet (< 2025-09-24)
+ hours >= 2025-09-24 resampled from 1m exactly as prep_features.py (first / max / min / last per hour, empty hours dropped), alts from the same
two directories as v294.load_1m. The resampling is verified on the overlap 2025-08-01 .. 2025-09-23 against hourly.parquet.
Missing / delisted coins: the builder's rule (a coin without a return in an hour / window is simply absent from cross-sectional stats; >= 8 coins
needed) - coverage reported.
Output: tables/ctx_v2_hidden_s{s}.parquet (T, sym, rung, size), tables/ctx_v2_hidden_feat_s{s}.parquet, tables/check_hidden.json.

  .venv/Scripts/python.exe research/tournament/context/build_hidden_tables.py
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
from build_engine_tables import BO7, MAJORS, R2, ROOT, START0, Asset, bar_feats, rule  # noqa: E402
from run_variants import ALL, BASE, MONO, hgb  # noqa: E402

OUT = HERE / "tables"
A4 = pd.Timestamp("2025-09-24", tz="UTC")
TRAIN_CUT = A4 - pd.Timedelta(days=7)
HID_END = pd.Timestamp("2026-09-24 12:00", tz="UTC")       # nothing at or after is read
T_LAST = pd.Timestamp("2026-09-24 08:00", tz="UTC")
OVL_FROM = pd.Timestamp("2025-08-01", tz="UTC")
PRE_FROM = pd.Timestamp("2025-09-01", tz="UTC")             # pre-cut bars recomputed with the extended data (must equal ctx_v2_s*)
ALT_DIRS = (ROOT / "data/raw/alts_intraday_20260926", ROOT / "data/raw/alts2020_intraday_20260930")


def files_of(s):
    if s == "BTCUSDT":
        return sorted((ROOT / "data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    if s in MAJORS:
        return sorted((ROOT / "data/raw/majors_intraday_20260924").glob(f"{s}_1m_20*.parquet"))
    return sorted(f for d in ALT_DIRS for f in d.glob(f"{s}_1m_20*.parquet"))


def read_1m(s, lo, hi):
    fs = [f for f in files_of(s) if lo.year <= int(f.stem[-4:]) <= hi.year]
    if not fs:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"],
                                   filters=[("open_time", ">=", lo), ("open_time", "<", hi)]) for f in fs])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    m = m[(m.index >= lo) & (m.index < hi)]
    assert len(m) == 0 or m.index.max() < HID_END
    return m


def majors_1m(s):
    m = read_1m(s, START0, HID_END)
    return m.reindex(pd.date_range(START0, HID_END - pd.Timedelta(minutes=1), freq="1min"))


def hourly_ext(hourly):
    syms = sorted(hourly.sym.unique())
    new, cov = [], {}
    for s in syms:
        m = read_1m(s, OVL_FROM, HID_END)
        if len(m):
            h = m.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna(how="all")
            h = h.rename_axis("t").reset_index().assign(sym=s)
        else:
            h = pd.DataFrame({"t": pd.DatetimeIndex([], tz="UTC"), **{c: np.array([], float) for c in ("open", "high", "low", "close")}, "sym": s})
        old = hourly[(hourly.sym == s) & (hourly.t >= OVL_FROM)].reset_index(drop=True)
        ov = h[h.t < A4].reset_index(drop=True)
        same = len(ov) == len(old) and (ov.t.to_numpy() == old.t.to_numpy()).all() and \
            all(np.array_equal(ov[c].to_numpy(), old[c].to_numpy(), equal_nan=True) for c in ("open", "high", "low", "close"))
        hid = h[h.t >= A4]
        exp = int((T_LAST + pd.Timedelta(hours=4) - A4) / pd.Timedelta(hours=1))
        cov[s] = dict(overlap_identical=bool(same), hidden_hours=int(len(hid)), hidden_hours_expected_to_1200=exp,
                      first=str(hid.t.min()) if len(hid) else None, last=str(hid.t.max()) if len(hid) else None,
                      max_gap_h=float(hid.t.diff().max() / pd.Timedelta(hours=1)) if len(hid) > 1 else None)
        assert same, (s, len(ov), len(old))
        new.append(hid)
        del m
    ext = pd.concat([hourly] + new, ignore_index=True)[["t", "open", "high", "low", "close", "sym"]]
    assert ext.t.max() < HID_END
    return ext, cov


def fit_fold4():
    d = H.load()
    keep = (pd.read_parquet(H.FILLS).t_fill < H.DEV_END).to_numpy()
    bo = pd.read_parquet(HERE.parent / "data/bar_open.parquet")[keep].reset_index(drop=True)
    assert (bo.j.to_numpy() == d.j.to_numpy()).all() and (bo.sym.to_numpy() == d.sym.to_numpy()).all() and (bo.r.to_numpy() == d.r.to_numpy()).all()
    mf = pd.read_parquet(HERE / "market_features.parquet")
    assert (mf["T"].to_numpy() == d["T"].to_numpy()).all() and (mf.sym.to_numpy() == d.sym.to_numpy()).all()
    X = pd.concat([bo[[c for c in BASE if c != "k"]], d[["k"]], mf[MKT]], axis=1)[ALL].to_numpy(float)
    y = np.clip(d["y1.0"].to_numpy(float), -0.10, 0.08)
    half = (d.j % 2).to_numpy()
    tr = (d.t_exit < TRAIN_CUT).to_numpy()
    info = dict(train_rows=int(tr.sum()), max_t_exit=str(d.t_exit[tr].max()), max_T=str(d["T"][tr].max()))
    assert d.t_exit[tr].max() < TRAIN_CUT
    mu = float(y[tr].mean())
    ms = [hgb(10 * 4 + h, MONO, ALL).fit(X[tr & (half == h)], y[tr & (half == h)]) for h in (0, 1)]
    info["mu"] = mu
    return mu, ms, info


def phase_features(raw, s, hourly, t_from):
    sh = pd.Timedelta(hours=s)
    btc = Asset(raw["BTCUSDT"][raw["BTCUSDT"].index >= START0 + sh])
    rows = []
    for sy in MAJORS:
        A = btc if sy == "BTCUSDT" else Asset(raw[sy][raw[sy].index >= START0 + sh])
        for j, T in enumerate(A.t0):
            if T < t_from + sh or T > T_LAST + sh:
                continue
            rows.append(dict(T=T, sym=sy, j=j, **bar_feats(A, btc, j)))
    f = pd.DataFrame(rows)
    return pd.concat([f, build_mkt(hourly, f[["T", "sym"]])], axis=1)


def expand(feat):
    return pd.concat([feat.assign(k=k, rung=r) for r, k in enumerate(R2)], ignore_index=True)


def causality(raw, hourly, feats, n=20, seed=23):
    rng = np.random.default_rng(seed)
    done = []
    for _ in range(n):
        s = int(rng.integers(4))
        f = feats[s]
        row = f.iloc[int(rng.integers(len(f)))]
        T, sy, sh = row["T"], row["sym"], pd.Timedelta(hours=s)
        cut = T + pd.Timedelta(minutes=1)
        tr = {q: raw[q][(raw[q].index >= START0 + sh) & (raw[q].index < cut)] for q in {sy, "BTCUSDT"}}
        btc = Asset(tr["BTCUSDT"])
        A = btc if sy == "BTCUSDT" else Asset(tr[sy])
        j = int(row["j"])
        assert A.t0[j] == T and len(A.C) == 240 * j + 1
        b = bar_feats(A, btc, j)
        mk = build_mkt(hourly[hourly.t < T], pd.DataFrame({"T": [T], "sym": [sy]})).iloc[0]
        new = np.array([b[c] for c in BO7] + [mk[c] for c in MKT], float)
        old = row[BO7 + MKT].to_numpy(float)
        assert (np.isnan(new) == np.isnan(old)).all() and np.nanmax(np.abs(new - old)) == 0.0, (s, T, sy)
        done.append(f"s{s} {T} {sy}")
    return dict(n=n, max_abs_diff=0.0, rows=done)


def main():
    t0 = time.time()
    mu, ms, info = fit_fold4()
    print("fold-4 model", info, flush=True)
    hourly, cov = hourly_ext(load_hourly())
    print("hourly extended", len(hourly), f"{time.time() - t0:.0f}s", flush=True)
    raw = {s: majors_1m(s) for s in MAJORS}
    print("majors 1m last minute", {s: str(m.dropna(how='all').index.max()) for s, m in raw.items()}, f"{time.time() - t0:.0f}s", flush=True)
    data_end = min(m.dropna(how="all").index.max() for m in raw.values()) + pd.Timedelta(minutes=1)
    check = {"fold4": info, "hourly_coverage": cov, "phases": {}, "majors_1m_data_end": str(data_end)}
    feats = {}
    for s in range(4):
        sh = pd.Timedelta(hours=s)
        feat = phase_features(raw, s, hourly, PRE_FROM)
        g = expand(feat)
        # (a) pre-cut bars with the extended data: features must equal the dev table's audit features (data extension changes nothing)
        old = pd.read_parquet(OUT / f"ctx_v2_feat_s{s}.parquet")
        pre = g[g["T"] < A4].merge(old[old["T"] >= PRE_FROM + sh], on=["T", "sym", "rung"], suffixes=("", "_old"))
        pre_diff = max(float(np.nanmax(np.abs(pre[c].to_numpy(float) - pre[c + "_old"].to_numpy(float)))) for c in BO7 + MKT)
        pre_nan = sum(int((pre[c].isna() != pre[c + "_old"].isna()).sum()) for c in BO7 + MKT)
        # hidden-year rows: fold-4 model
        h = g[g["T"] >= A4 + sh].reset_index(drop=True)
        h["size"] = rule(ms, mu, h[ALL].to_numpy(float))
        # bars whose minute 0 lies beyond the last available 1m minute cannot be computed -> neutral 1.0 (same convention as ctx_v2_s*)
        beyond = (h["T"] >= data_end).to_numpy()
        h.loc[beyond, "size"] = 1.0
        tab = h[["T", "sym", "rung", "size"]]
        tab.to_parquet(OUT / f"ctx_v2_hidden_s{s}.parquet")
        h.drop(columns=["size"]).to_parquet(OUT / f"ctx_v2_hidden_feat_s{s}.parquet")
        feats[s] = feat[feat["T"] >= A4 + sh].reset_index(drop=True)
        # (1) overlap with ctx_v2_s (T in 2025-09-24 00:00..08:00 + s h; those dev rows were neutral 1.0)
        dev = pd.read_parquet(OUT / f"ctx_v2_s{s}.parquet")
        ov = dev[dev["T"] >= A4].merge(tab, on=["T", "sym", "rung"], how="left", suffixes=("_dev", ""))
        exp_bars = len(pd.date_range(A4 + sh, T_LAST + sh, freq="4h"))
        check["phases"][s] = dict(
            rows=len(tab), bars=int(len(feats[s])), expected_bars=exp_bars * 5, T_min=str(tab["T"].min()), T_max=str(tab["T"].max()),
            hours=sorted(set(int(x) for x in tab["T"].dt.hour)), size_counts={str(k): int(v) for k, v in tab["size"].value_counts().sort_index().items()},
            feature_nan_share={c: round(float(h[c].isna().mean()), 4) for c in BO7 + MKT if h[c].isna().any()},
            pre_cut_rows_compared=len(pre), pre_cut_feature_max_abs_diff=pre_diff, pre_cut_nan_mismatch=pre_nan,
            neutral_rows_beyond_data_end=int(beyond.sum()),
            nan_feature_rows_not_neutral=int((h[BO7 + MKT].isna().any(axis=1).to_numpy() & ~beyond).sum()),
            overlap_rows=len(ov), overlap_dev_sizes={str(k): int(v) for k, v in ov["size_dev"].value_counts().items()},
            overlap_new_sizes={str(k): int(v) for k, v in ov["size"].value_counts().items()}, overlap_missing=int(ov["size"].isna().sum()),
            overlap_changed=int((ov["size"] != ov["size_dev"]).sum()))
        print("phase", s, check["phases"][s], f"{time.time() - t0:.0f}s", flush=True)
    check["causality"] = causality(raw, hourly, feats)
    print("causality", check["causality"], flush=True)
    check["seconds"] = round(time.time() - t0)
    (OUT / "check_hidden.json").write_text(json.dumps(check, indent=1, default=str))
    print("coverage", json.dumps(cov, indent=0), flush=True)


if __name__ == "__main__":
    main()
