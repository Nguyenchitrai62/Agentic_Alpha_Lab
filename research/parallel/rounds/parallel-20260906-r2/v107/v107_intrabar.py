"""v107: v103 plus intrabar features from 1h klines (registry parallel-20260906-r2 / v107).

1h series per asset = Binance SPOT 1h prefix (data/raw/spot_majors_20260925/{SYM}_spot_1h_2017.parquet, strictly before
the first USD-M 1h bar) + USD-M 1h klines. With r1 = 1h log close-to-close return and sd168 = rolling-168 std of r1:
  ih_last  = r1 of the last 1h bar / sd168
  ih_jump  = max |r1| over the last 4 1h bars / sd168
  ih_rv    = rolling-24 std r1 / sd168
  ih_ac    = rolling-72 lag-1 autocorrelation of r1
  ih_tbr   = taker buy ratio of the last 1h bar - its rolling-24 mean
  ih_up    = rolling-24 share of up 1h bars - 0.5
A 4h bar opening at T gets the values of the 1h bar opening at T+3h (closes with the 4h bar). Everything else is v103
(1d/3d targets, v92+flow features, HGB, v94 long/short daily book, 20% vol target). Primary: LS book. Secondary: 50/50
with the v96 books (as v103). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v107/v107_intrabar.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v92 = _load("v92", "v92/v92_pooled_hgb_vt.py")
v94 = _load("v94", "v94/v94_long_short_ensemble.py")
v103 = _load("v103", "v103/v103_flow_short_horizon.py")
IH = ("ih_last", "ih_jump", "ih_rv", "ih_ac", "ih_tbr", "ih_up")
PERP_1H = {"BTCUSDT": Path("data/raw/ma_ribbon_20260924/klines_1h.parquet")}
PERP_1H.update({s: Path(f"data/raw/majors_intraday_20260924/{s}_1h.parquet") for s in v92.SYMS if s != "BTCUSDT"})
SPOT_1H = Path("data/raw/spot_majors_20260925")


def load_1h(sym: str) -> pd.DataFrame:
    h = pd.read_parquet(PERP_1H[sym])
    h["open_time"] = pd.to_datetime(h["open_time"], utc=True)
    sp = SPOT_1H / f"{sym}_spot_1h_2017.parquet"
    if sp.exists():
        pre = pd.read_parquet(sp)
        pre["open_time"] = pd.to_datetime(pre["open_time"], utc=True)
        h = pd.concat([pre[pre.open_time < h.open_time.min()][h.columns.intersection(pre.columns)], h], ignore_index=True)
    return h.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)


def intrabar(h: pd.DataFrame) -> pd.DataFrame:
    c = h["close"].astype(float)
    r1 = np.log(c).diff()
    sd = r1.rolling(168, min_periods=84).std()
    tbr = (h["taker_buy_quote_volume"].astype(float) / h["quote_volume"].astype(float).clip(lower=1.0)).clip(0, 1)
    x = pd.DataFrame({"t": h["open_time"] - pd.Timedelta(hours=3)})
    x["ih_last"] = r1 / sd
    x["ih_jump"] = r1.abs().rolling(4).max() / sd
    x["ih_rv"] = r1.rolling(24).std() / sd
    x["ih_ac"] = r1.rolling(72).corr(r1.shift(1))
    x["ih_tbr"] = tbr - tbr.rolling(24).mean()
    x["ih_up"] = (r1 > 0).astype(float).where(r1.notna()).rolling(24).mean() - 0.5
    return x


def build() -> pd.DataFrame:
    panel = v103.build()
    parts = []
    for s in v92.SYMS:
        x = intrabar(load_1h(s))
        x["sym"] = s
        parts.append(x)
    ih = pd.concat(parts, ignore_index=True)
    return panel.merge(ih, on=["t", "sym"], how="left")


def main():
    panel = build()
    feats = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    assert all(f in feats for f in IH + v103.FLOW)
    cover = {s: round(float(g[list(IH)].notna().all(axis=1).mean()), 3) for s, g in panel.groupby("sym")}
    print("intrabar coverage", cover, flush=True)
    oos, ic = [], {}
    for a in v92.ANCHORS:
        te, rows = v103.train_predict(panel, a, feats)
        oos.append(te)
        ic[a] = dict(train_rows=rows, **{f"ic_y{h}": round(float(te[["pred", f"y{h}"]].corr(method="spearman").iloc[0, 1]), 4) for h in v103.HS})
        print(a, ic[a], flush=True)
    oos = pd.concat(oos, ignore_index=True)
    out = {"version": "v107", "ic": ic, "coverage": cover}
    W = v94.weights_ls(oos, True)
    out["primary_long_short"] = v103.evaluate(panel, W, "v107 LS")
    p92 = v92.build()
    v92.FEATS = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    W_lo = v92.weights_from(pd.concat([v92.train_predict(p92, a)[0] for a in v92.ANCHORS], ignore_index=True), "model")
    p94 = v94.add_targets(v92.build())
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    W94 = v94.weights_ls(pd.concat([v94.train_predict(p94, a, f94)[0] for a in v92.ANCHORS], ignore_index=True), True)
    idx = W_lo.index.union(W94.index).union(W.index)
    v96 = 0.5 * W_lo.reindex(idx).fillna(0.0).mul(v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0) \
        + 0.5 * W94.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(p94, W94).reindex(idx).fillna(1.0), axis=0)
    W107 = W.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(panel, W).reindex(idx).fillna(1.0), axis=0)
    out["secondary_blend_v96"] = v103.evaluate(p92, 0.5 * v96 + 0.5 * W107, "0.5 v96 + 0.5 v107", scale=1.0)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v107_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
