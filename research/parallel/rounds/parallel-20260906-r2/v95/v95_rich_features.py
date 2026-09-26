"""v95: audited v92 pipeline + cross-asset and market-context features (registry parallel-20260906-r2 / v95).

Added causal features (all as of the 4h bar close; NaN where a source starts later):
- cross-sectional among the five majors at the same bar: rank of ret42 / ret180 / snr42, relative strength
  ret42 - BTC ret42, share of majors with a bullish daily ribbon, mean snr42 across majors;
- per-asset funding z-score (f7 vs its trailing 180-day mean/std of f7);
- market context computed on BTC 4h bars with the previously verified modules: alt breadth
  (patterns.breadth), BTC positioning (patterns.positioning, from 2022), macro risk-on (patterns.macro),
  implied volatility (patterns.implied_vol, from 2021).
Book, vol target and execution identical to v92. Reports IC per anchor for v92-features vs v95-features.

  python research/parallel/rounds/parallel-20260906-r2/v95/v95_rich_features.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v92", HERE.parent / "v92" / "v92_pooled_hgb_vt.py")
v92 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v92)
PD = v92.PD


def market_context() -> pd.DataFrame:
    from agentic_alpha_lab.patterns import breadth, implied_vol, macro, positioning
    from agentic_alpha_lab.patterns.common import load_bars
    b = load_bars("4h", include_opened_year=True)
    parts = []
    for name, mod in (("brd", breadth), ("pos", positioning), ("mac", macro), ("dvol", implied_vol)):
        x = mod.compute(b)
        x.columns = [f"ctx_{c}" for c in x.columns]
        parts.append(x)
    ctx = pd.concat(parts, axis=1)
    ctx = ctx.loc[:, ctx.notna().mean() > 0.2]
    ctx["t"] = pd.to_datetime(b["open_time"], utc=True).to_numpy()
    return ctx.replace([np.inf, -np.inf], np.nan)


def add_cross_sectional(panel: pd.DataFrame) -> pd.DataFrame:
    p = panel.copy()
    for c in ("ret42", "ret180", "snr42"):
        p[f"xs_rank_{c}"] = p.groupby("t")[c].rank(pct=True)
    p["xs_rel_btc42"] = p["ret42"] - p["btc_ret42"]
    p["xs_bull_share"] = p.groupby("t")["rib"].transform(lambda s: float((s == 1).mean()))
    p["xs_mean_snr42"] = p.groupby("t")["snr42"].transform("mean")
    out = []
    for s, g in p.groupby("sym", sort=False):
        g = g.sort_values("t").copy()
        m, sd = g["f7"].rolling(180 * PD, min_periods=30 * PD).mean(), g["f7"].rolling(180 * PD, min_periods=30 * PD).std()
        g["f7_z"] = (g["f7"] - m) / sd
        out.append(g)
    return pd.concat(out, ignore_index=True)


def run_book(panel, feats, label):
    v92.FEATS = feats
    preds, ics = [], []
    for a in v92.ANCHORS:
        te, _ = v92.train_predict(panel, a)
        preds.append(te)
        ics.append(round(float(te[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4))
    oos = pd.concat(preds, ignore_index=True)
    W = v92.weights_from(oos, "model")
    s = v92.vol_target_scale(panel, W)
    res = {"ic_by_anchor": ics}
    for sc, (fee, slip) in v92.SCEN.items():
        net, turn = v92.simulate(panel, W, s, fee, slip)
        yearly = []
        for a in v92.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            m = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
            yearly.append(dict(anchor=a, **v92.stats(net[m], turn[m])))
        nets = [y["net_pct"] for y in yearly]
        geo = np.prod([1 + x / 100 for x in nets]) ** (1 / len(nets)) - 1
        res[sc] = dict(yearly=yearly, geometric_annual_pct=round(100 * geo, 2), monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
                       worst_year_dd=max(y["max_drawdown_percent"] for y in yearly))
    n = res["normal"]
    print(label, "IC", ics, "| monthly", n["monthly_pct"], "worstDD", n["worst_year_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in n["yearly"]], flush=True)
    return res


def main():
    base = v92.build()
    base_feats = [c for c in base.columns if c not in ("y", "t", "open", "sym", "bar")]
    panel = add_cross_sectional(base)
    ctx = market_context()
    panel = panel.merge(ctx, on="t", how="left")
    rich_feats = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar")]
    out = {"version": "v95", "n_base_features": len(base_feats), "n_rich_features": len(rich_feats),
           "added_features": [c for c in rich_feats if c not in base_feats]}
    out["v92_features_reference"] = run_book(panel, base_feats, "v92-features")
    out["v95_rich_features"] = run_book(panel, rich_feats, "v95-rich")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v95_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
