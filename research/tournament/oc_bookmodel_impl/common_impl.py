"""Shared helpers for oc_bookmodel_impl C1/C2 (no pre-registration here; see c1/c2 docstrings)."""
from __future__ import annotations

import glob
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

IMPL = Path(__file__).parent
RD = Path("research/parallel/rounds/parallel-20260906-r2")
CACHE = Path("artifacts/research/engine_real")

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
OUT_COLS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
DEV_ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")
FINAL_ANCHOR = "2025-09-24"
EMBARGO_DAYS = 7
HGB = dict(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
           l2_regularization=1.0, random_state=0)
H_C1 = (3, 18, 42)  # 12h, 3d, 7d in 4h bars
H_MAX = 42
ALT4H = Path("artifacts/research/engine_real/v316_alt4h")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_stack():
    v92 = _load("ocbm_v92", RD / "v92/v92_pooled_hgb_vt.py")
    v94 = _load("ocbm_v94", RD / "v94/v94_long_short_ensemble.py")
    v103 = _load("ocbm_v103", RD / "v103/v103_flow_short_horizon.py")
    v142 = _load("ocbm_v142", RD / "v142/v142_cross_sectional_features.py")
    tvm = _load("ocbm_tv", RD / "v231/tv_indicators.py")
    flo = _load("ocbm_flow", RD / "v236/flow_features.py")
    flo_orders = _load("ocbm_flow_o", RD / "v236/flow_features.py")
    flo_orders.D = Path("data/raw/aggflow_20260928_orders")
    return v92, v94, v103, v142, tvm, flo, flo_orders


def cutoff_for(anchor: str) -> pd.Timestamp:
    return pd.Timestamp(anchor, tz="UTC") - pd.Timedelta(days=EMBARGO_DAYS)


def quarter_starts(anchor: str):
    a0 = pd.Timestamp(anchor, tz="UTC")
    return [a0 + pd.Timedelta(days=91 * q) for q in range(4)]


def quarter_end(anchor: str) -> pd.Timestamp:
    return pd.Timestamp(anchor, tz="UTC") + pd.Timedelta(days=365)


def alt_universe() -> list:
    v = pd.read_csv("data/raw/um_universe_20260930/volume_2020_12.csv")
    majors = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    v = v[(v.days >= 28) & ~v.symbol.isin(majors)].sort_values("quote_volume_usd", ascending=False)
    return list(v.symbol)


def alt_bars(sym: str) -> pd.DataFrame:
    p = ALT4H / f"{sym}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    files = sorted(glob.glob(f"data/raw/alts2020_intraday_20260930/{sym}_1m_*.parquet")) or \
        sorted(glob.glob(f"data/raw/alts_intraday_20260926/{sym}_1m_*.parquet"))
    parts = []
    for f in files:
        m = pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close", "volume",
                                         "quote_volume", "num_trades", "taker_buy_volume",
                                         "taker_buy_quote_volume"])
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        g = m.groupby(m["open_time"].dt.floor("4h"))
        parts.append(pd.DataFrame({
            "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
            "close": g["close"].last(), "volume": g["volume"].sum(),
            "quote_volume": g["quote_volume"].sum(), "num_trades": g["num_trades"].sum(),
            "taker_buy_volume": g["taker_buy_volume"].sum(),
            "taker_buy_quote_volume": g["taker_buy_quote_volume"].sum(),
            "n_min": g["open"].count()}))
    b = pd.concat(parts).sort_index()
    b = b[~b.index.duplicated()]
    b = b[b["n_min"] >= 200].drop(columns="n_min")
    b.index.name = "open_time"
    b = b.reset_index()
    b["close_time"] = b["open_time"] + pd.Timedelta(hours=4) - pd.Timedelta(milliseconds=1)
    ALT4H.mkdir(parents=True, exist_ok=True)
    b.to_parquet(p)
    return b


def add_targets_multi(panel: pd.DataFrame, horizons) -> pd.DataFrame:
    """Vol-normalised forward open-to-open targets, same formula as v92/v103.

    y_h(t) = clip(log(open[t+1+h]/open[t+1]) / (vol42(t)*sqrt(h)), +-4).
    Uses only opens at t+1..t+1+h and vol42 known at t (causal).
    """
    panel = panel.copy()
    for h in horizons:
        out = np.full(len(panel), np.nan)
        for _s, g in panel.groupby("sym", sort=False):
            idx = g.index.to_numpy()
            o = g["open"].to_numpy()
            v = g["vol42"].to_numpy()
            n = len(g)
            fwd = np.full(n, np.nan)
            if n > h + 1:
                with np.errstate(divide="ignore", invalid="ignore"):
                    fwd[: n - 1 - h] = np.log(o[1 + h:] / o[1: n - h]) / (v[: n - 1 - h] * np.sqrt(h))
            panel.loc[g.index, f"y{h}"] = np.clip(fwd, -4, 4)
            _ = idx
        _ = out
    return panel


def train_mask(panel: pd.DataFrame, cutoff: pd.Timestamp, horizons) -> pd.Series:
    """Rows with t < cutoff and every label realised before cutoff: t+(h+1)*4h < cutoff."""
    m = panel["t"] < cutoff
    for h in horizons:
        m &= panel["t"] + pd.Timedelta(hours=4 * (h + 1)) < cutoff
    for h in horizons:
        m &= panel[f"y{h}"].notna()
    return m


def build_majors_panel(stack, with_flow_kline=True) -> pd.DataFrame:
    """Majors panel: v92.features + v103 kline-flow + BTC cross (audited code paths)."""
    v92, _v94, v103, _v142, _tvm, _flo, _flo_o = stack
    rows = []
    for i, s in enumerate(v92.SYMS):
        b, d, f = v92.load_asset(s)
        x, y = v92.features(b, d, f)
        if with_flow_kline:
            x = pd.concat([x, v103.flow_features(b, x["vol42"])], axis=1)
        x["asset"] = i
        x["y"] = y
        x["t"] = pd.DatetimeIndex(b["open_time"])
        x["open"] = b["open"].to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    return panel.join(btc, on="t")


def add_tv_and_flow(stack, panel: pd.DataFrame, load_asset_fn, order_flow=True) -> pd.DataFrame:
    """Merge audited TV(17) (+ order-level whale flow(6) for majors) on (t, sym)."""
    _v92, _v94, _v103, _v142, tvm, _flo, flo_o = stack
    tv_rows, fl_rows = [], []
    for s in SYMS:
        b, _, _ = load_asset_fn(s)
        t = pd.DatetimeIndex(b["open_time"])
        tv = tvm.tv_features(b.reset_index(drop=True)).reset_index(drop=True)
        tv_rows.append(pd.concat([pd.DataFrame({"t": t, "sym": s}), tv], axis=1))
        if order_flow:
            try:
                fl = flo_o.flow_features(s, t).reset_index(drop=True)
            except Exception:
                fl = pd.DataFrame({c: np.nan for c in
                                   ("fl_big_imb6", "fl_big_imb42", "fl_ret_imb6", "fl_div6",
                                    "fl_big_share_z", "fl_whale_n_z")}, index=range(len(t)))
                fl["t"] = t
                fl["sym"] = s
                fl = fl.drop(columns=["t", "sym"])
            fl_rows.append(pd.concat([pd.DataFrame({"t": t, "sym": s}), fl], axis=1))
    xf = pd.concat(tv_rows, ignore_index=True)
    panel = panel.merge(xf, on=["t", "sym"], how="left")
    if order_flow:
        xff = pd.concat(fl_rows, ignore_index=True)
        panel = panel.merge(xff, on=["t", "sym"], how="left")
    return panel


def add_alt_rows(stack, panel: pd.DataFrame, load_asset_fn, uni: list, max_alts=None,
                 log=None) -> pd.DataFrame:
    """Append pooled alt rows: v92.features + kline-flow + TV on alt 4h bars.

    Alt rows only where the coin was listed before the bar (n_min>=200 filter in
    alt_bars); universe fixed Dec-2020 so no survivorship pick-up. Alt flow(6) =
    NaN (majors-only archive); alt asset id = 5 (v316 convention).
    """
    v92, _v94, v103, _v142, tvm, _flo, _flo_o = stack
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    rows = []
    for s in (uni[: max_alts] if max_alts else uni):
        try:
            b, d, f = alt_asset_df(s)
        except Exception as e:
            if log:
                log(f"alt {s} skipped: {e}")
            continue
        if len(b) < 600:
            continue
        x, y = v92.features(b, d, f)
        try:
            x = pd.concat([x, v103.flow_features(b, x["vol42"])], axis=1)
        except Exception:
            pass
        x["asset"] = 5
        x["y"] = y
        x["t"] = pd.DatetimeIndex(b["open_time"])
        x["open"] = b["open"].to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        try:
            tv = tvm.tv_features(b.reset_index(drop=True)).reset_index(drop=True)
            x = pd.concat([x.reset_index(drop=True), tv.reset_index(drop=True)], axis=1)
        except Exception:
            pass
        x = x.join(btc, on="t")
        rows.append(x)
    if rows:
        panel = pd.concat([panel] + rows, ignore_index=True)
    _ = load_asset_fn
    return panel


def alt_asset_df(sym: str):
    b = alt_bars(sym)
    d = b.set_index("open_time").resample("1D").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()
    d["close_time"] = d["open_time"] + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
    fp = Path(f"data/raw/xs_universe_20260924/{sym}_funding.parquet")
    if fp.exists():
        f = pd.read_parquet(fp)
        f["fundingTime"] = pd.to_datetime(f["fundingTime"], utc=True)
        f = f.sort_values("fundingTime")
    else:
        f = pd.DataFrame({"fundingTime": pd.to_datetime([], utc=True), "fundingRate": []})
    return b, d, f


def add_xs(stack, panel: pd.DataFrame) -> pd.DataFrame:
    """v142 cross-sectional features on the v92 BASE set (+ v103 FLOWX where present)."""
    _v92, _v94, _v103, v142, _tvm, _flo, _flo_o = stack
    cols = [c for c in v142.BASE if c in panel.columns]
    panel = v142.add_xs(panel, cols)
    flowx = [c for c in v142.FLOWX if c in panel.columns]
    if flowx:
        panel = v142.add_xs(panel, flowx)
    return panel


def feature_list(panel: pd.DataFrame, exclude_flow_for_B=False) -> list:
    feats = [c for c in panel.columns
             if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    if exclude_flow_for_B:
        feats = [c for c in feats if not c.startswith("fl_")]
    return feats


def weights_frame(oos: pd.DataFrame, v94, shorts=True) -> pd.DataFrame:
    """v94.weights_ls on the OOS prediction frame (needs pred, rib, vol42, t, sym)."""
    W = v94.weights_ls(oos, shorts)
    return W.reindex(columns=OUT_COLS).sort_index()


def format_member(W: pd.DataFrame) -> pd.DataFrame:
    W = W.reindex(columns=OUT_COLS).sort_index()
    W.index.name = "t"
    return W.fillna(0.0).astype(float)


def truncation_check(feature_fn, bars: pd.DataFrame, n_check=3) -> dict:
    """Causality proof: features on truncated bars equal the head of full-bar features.

    feature_fn(bars) -> DataFrame aligned to bars.index. Truncate the last
    `n_check` raw bars; the first len-n_check rows must be bit-identical
    (NaN-aware). Returns {max_abs_diff, pass}.
    """
    full = feature_fn(bars)
    trunc = feature_fn(bars.iloc[: len(bars) - n_check].copy())
    a = full.iloc[: len(trunc)].to_numpy(float)
    b = trunc.to_numpy(float)
    both_nan = np.isnan(a) & np.isnan(b)
    diff = np.abs(a - b)
    diff[both_nan] = 0.0
    diff[np.isnan(diff)] = np.inf
    mad = float(np.max(diff)) if diff.size else 0.0
    return {"max_abs_diff": mad, "pass": bool(mad == 0.0), "rows": int(len(trunc))}


def write_kpack_template(out_dir: Path, candidate: str, kernel_name: str, inputs: list,
                         runtime_note: str):
    """Kaggle bundle builder (kpack-style): inputs + kernel script + metadata template.

    Writes <out_dir>/ with kernel_run.py (imported from the candidate script),
    kernel-metadata.json.template (is_private true; do NOT push), MANIFEST.txt and
    INPUTS.json listing the local input files the leader must attach. Never pushes.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": f"private/{kernel_name}",
        "title": kernel_name,
        "code_file": "kernel_run.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": False,
        "enable_internet": False,
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
    }
    (out_dir / "kernel-metadata.json.template").write_text(json.dumps(meta, indent=1))
    (out_dir / "INPUTS.json").write_text(json.dumps(
        {"candidate": candidate, "inputs": inputs, "runtime_note": runtime_note}, indent=1))
    (out_dir / "MANIFEST.txt").write_text(
        f"candidate={candidate}\nkernel={kernel_name}\nprivate=true\ndo not push: leader uploads\n")
