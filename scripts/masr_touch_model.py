"""Can a model tell which MA-Ribbon touches hold? (HGB on touch-time features, hidden-year test.)

Uses the MA tests from `masr_reaction.py` (events.parquet) and rebuilds causal features at the
touch bar from the same 1m-derived bars: MA slope, the other MA's distance, approach speed,
volume z-score, ATR%, number of recent tests, higher-timeframe trend, time of day. Label: the
±1 ATR race outcome (hold=1). Train on events before 2025-09-14, test on 2025-09-24 onwards.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).parent))
from masr_reaction import TFS, bars_from_1m, load_1m  # noqa: E402

EV = Path("artifacts/research/masr/reaction/events.parquet")


def features(b: pd.DataFrame) -> pd.DataFrame:
    c = b["close"]
    atr = b["atr"].shift(1)
    f = pd.DataFrame(index=b.index)
    s50, s200 = c.rolling(50).mean(), c.rolling(200).mean()
    for name, s in (("s50", s50), ("s200", s200)):
        f[f"{name}_slope"] = ((s - s.shift(5)) / atr).shift(1)
        f[f"{name}_dist_prev"] = ((c.shift(1) - s.shift(1)) / atr)
        touch = (b["low"] <= s.shift(1)) & (b["high"] >= s.shift(1))
        f[f"{name}_touches20"] = touch.astype(float).shift(1).rolling(20).sum()
    f["s50_s200"] = ((s50 - s200) / atr).shift(1)
    f["approach4"] = ((c.shift(1) - c.shift(5)) / atr)
    f["atr_pct"] = atr / c.shift(1)
    f["range_prev"] = ((b["high"] - b["low"]).shift(1) / atr)
    f["hour"] = b.index.hour
    f["dow"] = b.index.dayofweek
    d = c.resample("1D").last().dropna()
    dtrend = np.sign(d.rolling(50).mean() - d.rolling(200).mean()).shift(1)
    f["daily_trend"] = dtrend.reindex(b.index, method="ffill")
    return f


def main():
    ev = pd.read_parquet(EV)
    ev = ev[(ev.kind == "ma") & ~ev["amb_1.0"]].copy()
    parts = []
    for sym in ev.sym.unique():
        m = load_1m(sym)
        for tf, rule in TFS.items():
            b = bars_from_1m(m, rule)
            f = features(b)
            e = ev[(ev.sym == sym) & (ev.tf == tf)]
            x = f.reindex(pd.DatetimeIndex(e.t)).reset_index(drop=True)
            parts.append(pd.concat([e.reset_index(drop=True), x], axis=1))
    df = pd.concat(parts, ignore_index=True)
    df["tf_code"] = df.tf.map({"15m": 0, "1h": 1, "4h": 2, "1d": 3})
    df["ma_code"] = (df.ma == 200).astype(int)
    df["side_code"] = (df.side == "support").astype(int)
    df["sym_code"] = df.sym.map({"BTCUSDT": 0, "ETHUSDT": 1, "SOLUSDT": 2})
    cols = [c for c in df.columns if c.startswith(("s50_", "s200_", "approach", "atr_pct", "range_prev", "hour", "dow", "daily_trend"))] + ["tf_code", "ma_code", "side_code", "sym_code", "s50_s200"]
    cols = list(dict.fromkeys(cols))
    y = df["hold_1.0"].astype(int).to_numpy()
    tr = df.t < pd.Timestamp("2025-09-14", tz="UTC")
    te = df.t >= pd.Timestamp("2025-09-24", tz="UTC")
    model = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300, min_samples_leaf=200, l2_regularization=1.0, random_state=0)
    # inner validation on the last 20% of training time to report an honest train-side AUC too
    cut = df.t[tr].quantile(0.8)
    fit_idx, val_idx = tr & (df.t < cut), tr & (df.t >= cut)
    model.fit(df.loc[fit_idx, cols], y[fit_idx])
    auc_val = roc_auc_score(y[val_idx], model.predict_proba(df.loc[val_idx, cols])[:, 1])
    model.fit(df.loc[tr, cols], y[tr])
    p = model.predict_proba(df.loc[te, cols])[:, 1]
    auc_hid = roc_auc_score(y[te], p)
    print(f"events train {int(tr.sum())}, hidden {int(te.sum())}; base hold rate train {y[tr].mean():.3f}, hidden {y[te].mean():.3f}")
    print(f"AUC validation (last 20% of train) {auc_val:.3f} | AUC hidden year {auc_hid:.3f}")
    q = pd.qcut(p, 5, labels=False)
    print("hidden-year hold rate by predicted quintile (1=lowest .. 5=highest):",
          [round(float(y[te][q == i].mean()), 3) for i in range(5)], "n per quintile", int(len(p) / 5))
    top = p >= np.quantile(p, 0.9)
    print(f"top-decile predicted holds in hidden year: hold rate {y[te][top].mean():.3f} (n={int(top.sum())})")


if __name__ == "__main__":
    main()
