"""v100: v92 pooled HGB trained on 4x decision rows (registry parallel-20260906-r2 / v100, track B).

Extra training rows are phase-shifted 4h bars (start hours 1/2/3 mod 4) aggregated from the perp 1h klines,
with the audited v92 feature/target definitions applied unchanged to each shifted grid (BTC context features
joined from BTC's grid with the same phase). The standard grid (phase 0, with the 2017 spot prefix) is the
v92 panel. Test rows and trading use the standard grid only, so the book, vol target and costs are exactly
v92. Deviation from the registration text: predictions are NOT averaged across phases at decision time
(trading needs no phase-shifted live bars); only training uses the extra rows.

Primary: min_samples_leaf 1200 (v92 300 x 4 rows). Sensitivity row: min_samples_leaf 300.

  python research/parallel/rounds/parallel-20260906-r2/v100/v100_offset_rows.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v92", HERE.parent / "v92" / "v92_pooled_hgb_vt.py")
v92 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v92)
H1 = {"BTCUSDT": Path("data/raw/ma_ribbon_20260924/klines_1h.parquet")}
H1.update({s: Path(f"data/raw/majors_intraday_20260924/{s}_1h.parquet") for s in v92.SYMS if s != "BTCUSDT"})
EXCL = ("y", "t", "open", "sym", "bar", "phase")


def shifted_4h(h1: pd.DataFrame, phase: int) -> pd.DataFrame:
    h = h1.copy()
    h["open_time"] = pd.to_datetime(h["open_time"], utc=True)
    h["close_time"] = pd.to_datetime(h["close_time"], utc=True)
    h = h.drop_duplicates("open_time").sort_values("open_time")
    key = (h["open_time"] - pd.Timedelta(hours=phase)).dt.floor("4h") + pd.Timedelta(hours=phase)
    g = h.groupby(key)
    b = pd.DataFrame({"open_time": g["open_time"].first(), "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                      "close": g["close"].last(), "close_time": g["close_time"].last(), "quote_volume": g["quote_volume"].sum(), "n": g.size()})
    b = b[(b["n"] == 4) & (b["open_time"] == b.index)].drop(columns="n")
    return b.reset_index(drop=True)


def build_phase(phase: int) -> pd.DataFrame:
    rows = []
    for i, s in enumerate(v92.SYMS):
        _, d, f = v92.load_asset(s)
        b = shifted_4h(pd.read_parquet(H1[s]), phase)
        x, y = v92.features(b, d, f)
        x["asset"], x["y"], x["t"], x["open"], x["sym"], x["bar"] = i, y, b["open_time"].to_numpy(), b["open"].to_numpy(), s, np.arange(len(b))
        rows.append(x)
    p = pd.concat(rows, ignore_index=True)
    btc = p[p.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    return p.join(btc, on="t").assign(phase=phase)


def train_predict(panel, extra, anchor, feats, leaf):
    a = pd.Timestamp(anchor, tz="UTC")
    cutoff = a - pd.Timedelta(hours=4 * v92.EMBARGO_BARS)
    pool = pd.concat([panel.assign(phase=0), extra], ignore_index=True)
    tr = pool[(pool.t < cutoff) & pool.y.notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (v92.H + 1)) < cutoff]
    te = panel[(panel.t >= a) & (panel.t < a + pd.Timedelta(days=365))].copy()
    m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=leaf, l2_regularization=1.0, random_state=0)
    m.fit(tr[feats], tr["y"])
    te["pred"] = m.predict(te[feats])
    return te, {int(k): int(v) for k, v in tr.phase.value_counts().sort_index().items()}


def run(panel, extra, feats, leaf):
    preds, ics = [], {}
    for a in v92.ANCHORS:
        te, rows = train_predict(panel, extra, a, feats, leaf)
        preds.append(te)
        ics[a] = dict(ic=round(float(te[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4), train_rows_by_phase=rows)
    oos = pd.concat(preds, ignore_index=True)
    W = v92.weights_from(oos, "model")
    s = v92.vol_target_scale(panel, W)
    res = {"ic": ics}
    for sc, (fee, slip) in v92.SCEN.items():
        net, turn = v92.simulate(panel, W, s, fee, slip)
        yearly = []
        for a in v92.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            mk = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
            yearly.append(dict(anchor=a, **v92.stats(net[mk], turn[mk])))
        geo = np.prod([1 + y["net_pct"] / 100 for y in yearly]) ** (1 / 5) - 1
        res[sc] = dict(yearly=yearly, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3), worst_year_dd=max(y["max_drawdown_percent"] for y in yearly))
    n = res["normal"]
    print(f"leaf {leaf} IC", [v["ic"] for v in ics.values()], "| monthly", n["monthly_pct"], "worstDD", n["worst_year_dd"],
          [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in n["yearly"]], flush=True)
    return res


def main():
    panel = v92.build()
    feats = [c for c in panel.columns if c not in EXCL]
    v92.FEATS = feats
    extra = pd.concat([build_phase(k) for k in (1, 2, 3)], ignore_index=True)
    print("extra rows by phase", extra.phase.value_counts().sort_index().to_dict(), flush=True)
    out = {"version": "v100", "primary_leaf_1200": run(panel, extra, feats, 1200), "sensitivity_leaf_300": run(panel, extra, feats, 300)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v100_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
