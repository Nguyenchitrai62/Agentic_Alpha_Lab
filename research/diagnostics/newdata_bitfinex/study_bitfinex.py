"""Dev-only study: Bitfinex margin features vs dip-trade outcomes + 4h returns.

Reads:
  research/diagnostics/phase_agents/fills_U.parquet  (dip-limit fills)
  data/raw/bitfinex_20261004/bitfinex_margin_1h.parquet
  data/raw/spot_majors_20260925/{SYM}USDT_spot_4h.parquet (4h-return leg)
Writes: research/diagnostics/newdata_bitfinex/ic_bitfinex.csv

LEAKAGE RULES (asserted): only fills with t_exit < 2025-09-14 (dev); features
joined strictly before the fill minute (stamp + 1h < t_fill); 4h leg uses only
decisions at closes < 2025-09-14 with labels from later opens (forward only).
Never touches dates >= 2025-09-24.

Per feature: Spearman IC with y1.0 per calendar year (2021-2025) for majors
(BTC/ETH/SOL/BNB/XRP) and all coins; partial IC = Spearman(feature, residual
of OLS y1.0 on x0..x6 fitted on the same rows), pooled, with t-stat.
Interesting <=> same sign in every year (both universes) and |t| > 3 pooled.
4h leg: Spearman IC with next-4h open-to-open return per sym per year + pooled.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from features_bitfinex import ALL_FEATURES, asof_for_bars, asof_for_fills, load_panel

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FILLS = ROOT / "research" / "diagnostics" / "phase_agents" / "fills_U.parquet"
SPOT = ROOT / "data" / "raw" / "spot_majors_20260925"
OUT_CSV = HERE / "ic_bitfinex.csv"

DEV_EXIT_END = pd.Timestamp("2025-09-14", tz="UTC")
NEVER_TOUCH = pd.Timestamp("2025-09-24", tz="UTC")
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
YEARS = [2021, 2022, 2023, 2024, 2025]
XCOLS = ["x0", "x1", "x2", "x3", "x4", "x5", "x6"]


def spearman(x: pd.Series, y: pd.Series) -> tuple[float, int]:
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(d) < 10:
        return float("nan"), int(len(d))
    return float(stats.spearmanr(d["x"], d["y"]).statistic), int(len(d))


def partial_resid(y: pd.Series, X: pd.DataFrame) -> pd.Series:
    Xf = X.copy()
    for c in Xf.columns:  # median impute (x2 has NaNs); same-row fit
        Xf[c] = Xf[c].fillna(Xf[c].median())
    Xf = Xf.fillna(0.0)
    A = np.column_stack([np.ones(len(Xf)), Xf.to_numpy(float)])
    beta, *_ = np.linalg.lstsq(A, y.to_numpy(float), rcond=None)
    return pd.Series(y.to_numpy(float) - A @ beta, index=y.index)


def main() -> None:
    panel = load_panel()
    assert panel.index.min().tz_convert("UTC") < DEV_EXIT_END

    fills = pd.read_parquet(FILLS)
    fills["t_fill"] = pd.to_datetime(fills["t_fill"], utc=True)
    fills["t_exit"] = pd.to_datetime(fills["t_exit"], utc=True)
    # dev-only: drop everything not exited before 2025-09-14 up front; the
    # rest of the script never sees later rows.
    dev = fills.loc[fills["t_exit"] < DEV_EXIT_END].copy()
    del fills
    assert (dev["t_exit"] < NEVER_TOUCH).all() and (dev["t_fill"] < NEVER_TOUCH).all()
    dev["year"] = dev["t_fill"].dt.year
    F = asof_for_fills(dev, panel=panel)
    dev = pd.concat([dev, F], axis=1)

    rows: list[dict] = []
    for feat in ALL_FEATURES:
        for uni, frame in (("majors", dev[dev["sym"].isin(MAJORS)]), ("all", dev)):
            scout = frame.dropna(subset=[feat])
            signs = []
            for yr in YEARS:
                g = scout[scout["year"] == yr]
                rho, n = spearman(g[feat], g["y1.0"])
                rows.append({"section": "dip_y1", "feature": feat, "group": uni,
                             "year": yr, "n": n, "spearman_ic": rho,
                             "t": rho * np.sqrt(max(n - 2, 0) / max(1 - rho * rho, 1e-12))
                             if np.isfinite(rho) and n > 2 else np.nan})
                signs.append(np.sign(rho))
            rho_p, n_p = spearman(scout[feat], partial_resid(scout["y1.0"], scout[XCOLS]))
            t_p = rho_p * np.sqrt(max(n_p - 2, 0) / max(1 - rho_p * rho_p, 1e-12)) \
                if np.isfinite(rho_p) and n_p > 2 else np.nan
            rows.append({"section": "dip_y1_partial", "feature": feat, "group": uni,
                         "year": "pooled", "n": n_p, "spearman_ic": rho_p, "t": t_p})
            rows.append({"section": "dip_y1_pooled", "feature": feat, "group": uni,
                         "year": "pooled", "n": int(scout[feat].notna().sum()),
                         "spearman_ic": spearman(scout[feat], scout["y1.0"])[0], "t": np.nan})

    # 4h-return leg: decision at 4h closes < DEV_EXIT_END (dev only)
    for sym in MAJORS:
        bars = pd.read_parquet(SPOT / f"{sym}_spot_4h.parquet").sort_values("open_time").reset_index(drop=True)
        bars["open_time"] = pd.to_datetime(bars["open_time"], utc=True)
        bars["close_time"] = pd.to_datetime(bars["close_time"], utc=True)
        assert (bars["open_time"] < NEVER_TOUCH).any()
        dec = bars.loc[bars["close_time"] < DEV_EXIT_END].copy().reset_index(drop=True)
        dec["fwd"] = np.log(dec["open"].shift(-2) / dec["open"].shift(-1))
        dec["year"] = dec["open_time"].dt.year
        dec = dec.dropna(subset=["fwd"])
        B = asof_for_bars(dec, sym, panel=panel).set_index(dec.index)
        for feat in ALL_FEATURES:
            xx = B[feat]
            for yr in YEARS:
                m = (dec["year"] == yr) & xx.notna()
                rho, n = spearman(xx[m], dec.loc[m, "fwd"])
                rows.append({"section": "ret4h", "feature": feat, "group": sym,
                             "year": yr, "n": n, "spearman_ic": rho, "t": np.nan})

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False)

    # interesting flags (dip leg): same sign every year in BOTH universes + |t|>3 pooled partial
    print("=== dip-leg yearly IC (majors) ===")
    piv = out[(out.section == "dip_y1") & (out.group == "majors")].pivot(
        index="feature", columns="year", values="spearman_ic")
    print(piv.round(4).to_string())
    print("=== pooled partial |t| (majors/all) ===")
    pp = out[out.section == "dip_y1_partial"].pivot(index="feature", columns="group", values="t")
    print(pp.round(2).to_string())
    print(f"wrote {OUT_CSV} ({len(out)} rows, dev fills={len(dev)})")


if __name__ == "__main__":
    main()
