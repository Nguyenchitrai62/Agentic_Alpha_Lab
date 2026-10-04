"""Dev-only study: do Binance book-depth features predict dip-limit fill outcomes (y1.0) or next 4h returns?

Study window: 2023-01 .. 2025-09-13 (bookDepth history starts 2023-01-01; dev = t_exit < 2025-09-14,
features joined strictly before the fill minute). No data at/after 2025-09-14 is ever touched.
Coverage is majors-only (alts lack full-window bookDepth history), so "all coins" = majors rows.

  python research/diagnostics/newdata_bookdepth/study.py
writes ic_dip.csv, ic_4h.csv, SUMMARY.md in this folder.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from features import FEATURES, attach_features, load_depth

HERE = Path(__file__).resolve().parent
FILLS = HERE.parent / "phase_agents" / "fills_U.parquet"
DEV_END = pd.Timestamp("2025-09-14", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
XCOLS = [f"x{i}" for i in range(7)]


def spearman_t(rho: float, n: int) -> float:
    if n < 3 or not np.isfinite(rho) or abs(rho) >= 1:
        return float("nan")
    return float(rho * np.sqrt((n - 2) / (1 - rho * rho)))


def ic_block(df: pd.DataFrame, feat: str, target: str) -> dict:
    """Spearman IC per year (2023/2024/2025) + pooled, on rows where both are finite."""
    out = {}
    sub = df[["year", feat, target]].dropna()
    for y in (2023, 2024, 2025):
        w = sub[sub["year"] == y]
        rho, _ = (stats.spearmanr(w[feat], w[target]) if len(w) >= 10 else (np.nan, np.nan))
        out[f"ic_{y}"] = float(rho) if np.isfinite(rho) else np.nan
        out[f"n_{y}"] = len(w)
    rho, _ = (stats.spearmanr(sub[feat], sub[target]) if len(sub) >= 10 else (np.nan, np.nan))
    out["ic_pool"] = float(rho) if np.isfinite(rho) else np.nan
    out["n_pool"] = len(sub)
    out["t_pool"] = spearman_t(out["ic_pool"], out["n_pool"])
    return out


def partial_ic(df: pd.DataFrame, feat: str) -> dict:
    """IC of feat with y1.0 residualized on x0..x6 (OLS fitted on the same complete-case rows)."""
    cc = df[[feat, "y1.0", *XCOLS]].dropna()
    out = {"n_partial": len(cc)}
    if len(cc) < 50:
        return out | {"ic_partial_pool": np.nan, "t_partial_pool": np.nan,
                      "ic_partial_2023": np.nan, "ic_partial_2024": np.nan, "ic_partial_2025": np.nan}
    X = np.column_stack([np.ones(len(cc)), cc[XCOLS].to_numpy(float)])
    resid = cc["y1.0"].to_numpy(float) - X @ np.linalg.lstsq(X, cc["y1.0"].to_numpy(float), rcond=None)[0]
    cc = cc.assign(resid=resid, year=cc.index.map(df["year"]))
    rho, _ = stats.spearmanr(cc[feat], cc["resid"])
    out["ic_partial_pool"] = float(rho)
    out["t_partial_pool"] = spearman_t(float(rho), len(cc))
    for y in (2023, 2024, 2025):
        w = cc[cc["year"] == y]
        r, _ = (stats.spearmanr(w[feat], w["resid"]) if len(w) >= 10 else (np.nan, np.nan))
        out[f"ic_partial_{y}"] = float(r) if np.isfinite(r) else np.nan
    return out


def load_4h(sym: str) -> pd.DataFrame:
    root = HERE.parents[2] / "data" / "raw"
    parts = []
    if sym == "BTCUSDT":
        for y in (2023, 2024, 2025):
            p = root / "btc_intraday_20260924" / f"klines_1m_{y}.parquet"
            if p.exists():
                parts.append(pd.read_parquet(p, columns=["open_time", "open", "close"]))
    else:
        src = root / "majors_intraday_20260924"
        for y in (2023, 2024, 2025):
            p = src / f"{sym}_1m_{y}.parquet"
            if p.exists():
                parts.append(pd.read_parquet(p, columns=["open_time", "open", "close"]))
    assert parts, f"no 1m klines for {sym}"
    m = pd.concat(parts, ignore_index=True).sort_values("open_time").reset_index(drop=True)
    m["grid"] = m["open_time"].dt.floor("4h")
    g = m.groupby("grid")
    bars = pd.DataFrame({"open_time": g["open_time"].first().index, "open": g["open"].first().to_numpy(),
                         "close": g["close"].last().to_numpy()}).sort_values("open_time").reset_index(drop=True)
    bars["close_time"] = bars["open_time"] + pd.Timedelta(hours=4)
    return bars


def main() -> None:
    fills = pd.read_parquet(FILLS)
    fills["t_fill"] = pd.to_datetime(fills["t_fill"], utc=True)
    fills["t_exit"] = pd.to_datetime(fills["t_exit"], utc=True)
    dev = fills[(fills["t_exit"] < DEV_END) & (fills["t_fill"] >= pd.Timestamp("2023-01-01", tz="UTC"))
                & (fills["sym"].isin(MAJORS))].copy()  # majors only: alts lack full-window bookDepth history
    assert (dev["t_exit"] < DEV_END).all() and (dev["sym"].isin(MAJORS)).all(), "dev/majors window violated"
    dev["year"] = dev["t_fill"].dt.year
    depth = {s: load_depth(s) for s in MAJORS}
    dec = pd.DataFrame({"sym": dev["sym"].to_numpy(), "T": dev["t_fill"].to_numpy()}, index=dev.index)
    feats = attach_features(dec, depth)
    dev = pd.concat([dev, feats], axis=1)
    assert (feats.notna().any(axis=1)).any()

    rows = []
    for feat in FEATURES:
        for cov in ("majors", "all"):
            d = dev  # majors-only coverage: majors == all; kept as separate rows for the contract
            b = ic_block(d, feat, "y1.0") | partial_ic(d, feat)
            signs = [np.sign(b[f"ic_{y}"]) for y in (2023, 2024, 2025)]
            b["same_sign"] = len(set(signs)) == 1 and signs[0] != 0
            b["interesting"] = bool(b["same_sign"] and abs(b.get("t_partial_pool", 0) or 0) > 3)
            rows.append({"feature": feat, "coverage": cov, **b})
    ic_dip = pd.DataFrame(rows)
    ic_dip.to_csv(HERE / "ic_dip.csv", index=False)
    sym_lines = []
    for feat in FEATURES:
        per = {}
        for s, g in dev.groupby("sym"):
            w = g[[feat, "y1.0"]].dropna()
            rho, _ = stats.spearmanr(w[feat], w["y1.0"]) if len(w) >= 10 else (np.nan, np.nan)
            per[s] = float(rho)
        pd.DataFrame([{"feature": feat, **per}]).to_csv(HERE / "ic_dip_persym.csv", mode="a",
                                                        header=not (HERE / "ic_dip_persym.csv").exists(), index=False)
        sgn = np.sign(list(per.values()))
        sym_lines.append(f"{feat} persym: " + " ".join(f"{s[:3]}={v:+.3f}" for s, v in per.items())
                         + f" all5_same_sign={bool((sgn != 0).all() and (sgn == sgn[0]).all())}")

    # 4h next-return IC: feature as-of bar close T, target = open[i+1] -> open[i+2] (bar open -> next bar open)
    h4 = []
    for sym in MAJORS:
        bars = load_4h(sym)
        bars = bars[bars["close_time"] < DEV_END].reset_index(drop=True)
        bars["fwd"] = bars["open"].shift(-2) / bars["open"].shift(-1) - 1.0
        use = bars.dropna(subset=["fwd"]).reset_index(drop=True)
        dec4 = pd.DataFrame({"sym": sym, "T": use["close_time"]})
        f4 = attach_features(dec4, depth)
        use = pd.concat([use.reset_index(drop=True), f4.reset_index(drop=True)], axis=1)
        use["year"] = use["close_time"].dt.year
        for feat in FEATURES:
            b = ic_block(use, feat, "fwd")
            h4.append({"feature": feat, "sym": sym, **b})
    pooled = []
    for feat in FEATURES:
        all4 = []
        for sym in MAJORS:
            bars = load_4h(sym)
            bars = bars[bars["close_time"] < DEV_END].reset_index(drop=True)
            bars["fwd"] = bars["open"].shift(-2) / bars["open"].shift(-1) - 1.0
            use = bars.dropna(subset=["fwd"]).reset_index(drop=True)
            f4 = attach_features(pd.DataFrame({"sym": sym, "T": use["close_time"]}), depth)
            use = pd.concat([use.reset_index(drop=True), f4.reset_index(drop=True)], axis=1)
            use["year"] = use["close_time"].dt.year
            all4.append(use[["year", feat, "fwd"]].rename(columns={"fwd": "tgt"}))
        cat = pd.concat(all4, ignore_index=True).rename(columns={feat: "f"})
        b = ic_block(cat.rename(columns={"f": feat, "tgt": "fwd"}), feat, "fwd")
        pooled.append({"feature": feat, "sym": "POOLED", **b})
    ic_4h = pd.DataFrame(h4 + pooled)
    ic_4h.to_csv(HERE / "ic_4h.csv", index=False)

    n_feat = len(dev)
    lines = [f"# bookdepth study (dev only, 2023-01..2025-09-13, n={n_feat} majors fills; majors == all-coins coverage)",
             f"as-of: last snapshot ts < t_fill asserted; depth_rel_7d trailing median, lags 15/60 min",
             f"x2 NaN: partial IC on complete-case rows (n_partial per feature)"]
    for _, r in ic_dip[ic_dip["coverage"] == "majors"].iterrows():
        lines.append(f"{r['feature']}: ic23={r['ic_2023']:+.3f} ic24={r['ic_2024']:+.3f} ic25={r['ic_2025']:+.3f} "
                     f"pool={r['ic_pool']:+.4f} t={r['t_pool']:+.1f} partial={r['ic_partial_pool']:+.4f} "
                     f"t_p={r['t_partial_pool']:+.1f} same_sign={r['same_sign']} interesting={r['interesting']}")
    p4 = ic_4h[ic_4h["sym"] == "POOLED"]
    for _, r in p4.iterrows():
        lines.append(f"4h {r['feature']}: pooled ic23={r['ic_2023']:+.3f} ic24={r['ic_2024']:+.3f} ic25={r['ic_2025']:+.3f} "
                     f"pool={r['ic_pool']:+.4f} t={r['t_pool']:+.1f}")
    verdict = "interesting: " + (", ".join(ic_dip[ic_dip['interesting'] & (ic_dip['coverage'] == 'majors')]['feature'].unique())
                                 or "NONE")
    lines.append(verdict)
    lines.extend(sym_lines)
    assert len(lines) <= 20, f"SUMMARY.md {len(lines)} lines > 20"
    (HERE / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
