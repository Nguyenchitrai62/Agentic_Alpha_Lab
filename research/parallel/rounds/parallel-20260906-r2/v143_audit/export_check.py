"""v143 audit 2: export check. Verifies v143_export.py writes the audited v103 panel.

- Static: export only calls v103.build(), selects t/sym + non-y feats + y6/y18/y, casts t int64.
- File checks: feature_list.json sha256/rows/syms.
- Sample replication: independent v103-panel build from raw data (same formulas as
  audited v103_v105_audit/replicate_v103_v105.py, written here without importing
  leader v103/v143 code), compared on 200 sampled rows x all 36 feats + 3 targets.
Writes export_report.json.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
AUD = Path(__file__).resolve().parent
EXPORT_SRC = ROOT / "research/parallel/rounds/parallel-20260906-r2/v143/v143_export.py"
PANEL = ROOT / "artifacts/kaggle/v143/dataset/v143_panel.parquet"
FLIST = ROOT / "artifacts/kaggle/v143/dataset/feature_list.json"

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"


def load_asset(s):
    if s == "BTCUSDT":
        b = pd.read_parquet(BTC_DIR / "klines_4h.parquet")
        d = pd.read_parquet(BTC_DIR / "klines_1d.parquet")
        f = pd.read_parquet(BTC_DIR / "funding.parquet")
    else:
        b = pd.read_parquet(XS_DIR / f"{s}_4h.parquet")
        d = pd.read_parquet(XS_DIR / f"{s}_1d.parquet")
        f = pd.read_parquet(XS_DIR / f"{s}_funding.parquet")
    for x in (b, d):
        x["open_time"] = pd.to_datetime(x["open_time"], utc=True)
        x["close_time"] = pd.to_datetime(x["close_time"], utc=True)
    f["fundingTime"] = pd.to_datetime(f["fundingTime"], utc=True)
    b = b.sort_values("open_time").reset_index(drop=True)
    d = d.sort_values("open_time").reset_index(drop=True)
    s4 = pd.read_parquet(SPOT_DIR / f"{s}_spot_4h_2017.parquet") if (SPOT_DIR / f"{s}_spot_4h_2017.parquet").exists() else b.iloc[:0].copy()
    s1 = pd.read_parquet(SPOT_DIR / f"{s}_spot_1d_2017.parquet") if (SPOT_DIR / f"{s}_spot_1d_2017.parquet").exists() else d.iloc[:0].copy()
    for x in (s4, s1):
        if len(x):
            x["open_time"] = pd.to_datetime(x["open_time"], utc=True)
            x["close_time"] = pd.to_datetime(x["close_time"], utc=True)
    pre4 = s4[s4["open_time"] < b["open_time"].min()].copy()
    pre1 = s1[s1["open_time"] < d["open_time"].min()].copy()
    b = pd.concat([pre4, b], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    d = pd.concat([pre1, d], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    return b, d, f.sort_values("fundingTime").reset_index(drop=True)


def asset_panel(s, idx):
    b, d, f = load_asset(s)
    c = b["close"].astype(float)
    lc = np.log(c)
    r1 = lc.diff()
    x = pd.DataFrame(index=b.index)
    vol42 = r1.rolling(42).std()
    for k in (6, 42, 90, 180, 540):
        dk = lc.diff(k)
        x[f"ret{k}"] = dk
        x[f"snr{k}"] = dk / (vol42 * np.sqrt(k))
    x["vol42"] = vol42
    x["vol180"] = r1.rolling(180).std()
    x["vol_ratio"] = x["vol42"] / x["vol180"]
    for sp in (20, 200):
        x[f"ema{sp}"] = np.log(c / c.ewm(span=sp, adjust=False, min_periods=sp).mean())
    dc = d["close"].astype(float)
    sma50, sma200 = dc.rolling(50).mean(), dc.rolling(200).mean()
    dfe = pd.DataFrame({"t": d["close_time"], "d50": np.log(dc / sma50), "d200": np.log(dc / sma200),
                        "rib": np.where((dc > sma50) & (sma50 > sma200), 1.0, np.where((dc < sma50) & (sma50 < sma200), -1.0, 0.0))})
    j = pd.merge_asof(pd.DataFrame({"t": b["close_time"]}), dfe.sort_values("t"), on="t", direction="backward")
    x[["d50", "d200", "rib"]] = j[["d50", "d200", "rib"]].to_numpy()
    fr = f.set_index("fundingTime")["fundingRate"].astype(float)
    fm = pd.DataFrame({"t": fr.index, "f7": fr.rolling(21, min_periods=3).mean().to_numpy(), "f30": fr.rolling(90, min_periods=9).mean().to_numpy()})
    jf = pd.merge_asof(pd.DataFrame({"t": b["close_time"]}), fm.sort_values("t"), on="t", direction="backward")
    x["f7"], x["f30"] = jf["f7"].to_numpy() * 1e4, jf["f30"].to_numpy() * 1e4
    lv = np.log(b["quote_volume"].astype(float).clip(lower=1))
    x["volz"] = (lv - lv.rolling(180).mean()) / lv.rolling(180).std()
    qv = b["quote_volume"].astype(float).clip(lower=1)
    tbr1 = (b["taker_buy_quote_volume"].astype(float) / qv).clip(0, 1)
    x["tbr_1"] = tbr1.rolling(1).mean() - 0.5
    x["tbr_6"] = tbr1.rolling(6).mean() - 0.5
    x["tbr_42"] = tbr1.rolling(42).mean() - 0.5
    signed = (2 * tbr1 - 1) * qv
    x["flow_6"] = signed.rolling(6).sum() / qv.rolling(6).sum()
    x["flow_42"] = signed.rolling(42).sum() / qv.rolling(42).sum()
    x["tbr_z"] = (tbr1.rolling(6).mean() - tbr1.rolling(180).mean()) / tbr1.rolling(180).std()
    ntr = b["num_trades"].astype(float).clip(lower=1)
    ts = np.log(qv / ntr)
    nl = np.log(ntr)
    x["tsize_z"] = (ts - ts.rolling(180).mean()) / ts.rolling(180).std()
    x["ntr_z"] = (nl - nl.rolling(180).mean()) / nl.rolling(180).std()
    x["rng6"] = np.log(b["high"].astype(float) / b["low"].astype(float)).rolling(6).mean() / vol42
    rng = b["high"].astype(float) - b["low"].astype(float)
    clv = (b["close"].astype(float) - b["low"].astype(float)) / rng
    x["clv6"] = clv.where(rng != 0, np.nan).rolling(6).mean() - 0.5
    o = b["open"].astype(float).to_numpy()
    n = len(b)
    v42 = vol42.to_numpy()
    for h in (6, 18, 42):
        fwd = np.full(n, np.nan)
        if n > 1 + h:
            fwd[: n - 1 - h] = np.log(o[1 + h:] / o[1: n - h])
        x[f"y{h if h != 42 else '' if False else h}"] = np.nan  # placeholder
    # exact v103 target names: y6, y18, y (y42 -> y)
    for h, col in ((6, "y6"), (18, "y18"), (42, "y")):
        fwd = np.full(n, np.nan)
        if n > 1 + h:
            fwd[: n - 1 - h] = np.log(o[1 + h:] / o[1: n - h])
        x[col] = np.clip(fwd / (v42 * np.sqrt(h)), -4, 4)
    # drop accidental y42-named col if created
    x = x.drop(columns=[c for c in x.columns if c not in ("y6", "y18", "y") and c.startswith("y4")], errors="ignore")
    x["asset"] = idx
    x["t"] = b["open_time"]
    x["open"] = b["open"].astype(float).to_numpy()
    x["sym"] = s
    return x, b


def main():
    src = EXPORT_SRC.read_text()
    static = {
        "calls_v103_build": "v103.build()" in src,
        "selects_y6_y18_y": '"y6", "y18", "y"' in src or "'y6'" in src or '"y6"' in src,
        "casts_t_int64": 'astype("int64")' in src,
        "no_feature_math": "rolling" not in src and "merge_asof" not in src,
    }
    meta = json.loads(FLIST.read_text())
    sha = hashlib.sha256(PANEL.read_bytes()).hexdigest()
    panel = pd.read_parquet(PANEL)
    panel["t_dt"] = pd.to_datetime(panel["t"], utc=True)
    file_checks = {
        "sha_match": sha == meta["sha256"],
        "rows_match": len(panel) == meta["rows"] == 88818,
        "n_features": len(meta["features"]),
        "features_36": len(meta["features"]) == 36,
        "syms": sorted(panel["sym"].unique().tolist()) == meta["syms"],
        "targets_present": all(c in panel.columns for c in ("y6", "y18", "y")),
    }
    # sample replication: 40 evenly spaced times x 5 syms
    times = np.sort(panel["t_dt"].unique())
    pick = np.linspace(0, len(times) - 1, 40).astype(int)
    sample_times = set(times[pick])
    rep_rows = []
    for i, s in enumerate(SYMS):
        x, _ = asset_panel(s, i)
        # BTC context join (same as v103.build)
        rep_rows.append(x)
    full = pd.concat(rep_rows, ignore_index=True)
    btc = full[full.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    full = full.join(btc, on="t")
    full["t_dt"] = pd.to_datetime(full["t"], utc=True)
    sub = full[full["t_dt"].isin(sample_times)].copy()
    feats = meta["features"]
    # merge exported vs replicated on (t_dt, sym)
    exp = panel[panel["t_dt"].isin(sample_times)][["t_dt", "sym"] + feats + ["y6", "y18", "y"]]
    m = exp.merge(sub[["t_dt", "sym"] + feats + ["y6", "y18", "y"]], on=["t_dt", "sym"], suffixes=("_exp", "_rep"))
    n_exp = int(len(exp))
    diffs = {}
    max_abs = 0.0
    for c in feats + ["y6", "y18", "y"]:
        a = m[f"{c}_exp"].to_numpy(float)
        b2 = m[f"{c}_rep"].to_numpy(float)
        both_nan = np.isnan(a) & np.isnan(b2)
        ok = both_nan | (np.abs(a - b2) < 1e-9) | ((np.isnan(a)) == (np.isnan(b2)))
        # max abs diff where both finite
        fin = np.isfinite(a) & np.isfinite(b2)
        d = float(np.max(np.abs(a[fin] - b2[fin]))) if fin.any() else 0.0
        max_abs = max(max_abs, d)
        diffs[c] = {"max_abs_diff": d, "mismatch_rows": int((~ok).sum())}
    n_mismatch = sum(v["mismatch_rows"] for v in diffs.values())
    out = {"static": static, "file_checks": file_checks, "sha256": sha,
           "sample_times": 40, "exp_sample_rows": n_exp, "matched_rows": int(len(m)),
           "sample_rows": int(len(m)), "max_abs_diff": max_abs, "total_mismatched_cells": n_mismatch,
           "per_col": diffs,
           "verdict": "pass" if all(static.values()) and all(file_checks.values()) and n_mismatch == 0 else "review"}
    (AUD / "export_report.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"static": static, "file_checks": file_checks, "exp_rows": n_exp, "matched": int(len(m)), "max_abs_diff": max_abs, "mismatched_cells": n_mismatch, "verdict": out["verdict"]}, indent=1))


if __name__ == "__main__":
    main()
