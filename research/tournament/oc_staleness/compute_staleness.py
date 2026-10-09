"""oc_staleness: how fast does the book's skill decay with model age?

Per PLAN.md (pre-registered): two member families (whale-flow A, Coinbase-premium D),
stale cuts C in {2021-09-17, 2022-09-17, 2023-09-17} (data before C-7d), fresh yearly
anchors {2021-09-24 .. 2024-09-24}. Pooled Spearman IC per 3-month age bin + vectorised
DIAGNOSTIC book P&L (labelled, no costs). Data before 2025-09-24 only.

  python research/tournament/oc_staleness/compute_staleness.py
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
ORDERS = Path("data/raw/aggflow_20260928_orders")

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
CUTS = [pd.Timestamp(d, tz="UTC") for d in ("2021-09-17", "2022-09-17", "2023-09-17")]
ANCHORS = [pd.Timestamp(d, tz="UTC") for d in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")]
END = pd.Timestamp("2025-09-24", tz="UTC")
Q = pd.Timedelta(days=91.3125)  # 3-month age bin
HGB = dict(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
           l2_regularization=1.0, random_state=0)


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] oc_staleness: {msg}", flush=True)


def _load(name: str, path) -> object:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_panel_A():
    """Whale-flow A panel: ext v92 base + TV(17) + order-level flow(6). Label y (H=42)."""
    log("loading v144/v240 modules for family A ...")
    v240 = _load("v240_s", RD / "v240/v240_order_level_flow.py")
    # Fresh v144 instance (annual, no quarterly wrapper) with extended history:
    v144m = _load("v144_s", RD / "v144/v144_deploy_v3.py")
    ext = v144m.v115.v114.v113
    v103m = v144m.v103
    ext.cb_bars = v144m.v115.v114.cb_bars_ext
    v144m.v115.v114.v113.cb_bars = v144m.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    base = ext.v92.build()
    log(f"family A base panel: {base.shape}")
    xf = v240.feature_frame(ext.v92.load_asset, False)
    log(f"family A extra features: {xf.shape}")
    panel = base.merge(xf, on=["t", "sym"], how="left")
    log(f"family A full panel: {panel.shape}")
    return panel, v144m.v115.v114.v113.v92 if hasattr(v144m.v115.v114.v113, "v92") else None


def build_panel_D():
    """Coinbase-premium D panel: v103.build() + v111 CB(5). Labels y6/y18."""
    log("loading v103/v111 modules for family D ...")
    v111 = _load("v111_s", RD / "v111/v111_coinbase_premium.py")
    v103m = v111.v103
    base = v103m.build()
    log(f"family D base panel: {base.shape}")
    panel = v111.add_cb(base)
    log(f"family D full panel: {panel.shape}")
    return panel


def feats_of(panel: pd.DataFrame) -> list:
    return [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]


def train_hgb(panel: pd.DataFrame, feats: list, label: str, H: int, embargo_bars: int, cut) -> object:
    cut_ts = cut if isinstance(cut, pd.Timestamp) else pd.Timestamp(cut, tz="UTC")
    cutoff = cut_ts - pd.Timedelta(hours=4 * embargo_bars)
    tr = panel[(panel.t < cutoff) & panel[label].notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (H + 1)) < cutoff]
    m = HistGradientBoostingRegressor(**HGB)
    m.fit(tr[feats], tr[label])
    return m, cutoff, len(tr)


def spearman_pooled(pred: pd.Series, label: pd.Series) -> tuple:
    both = pd.DataFrame({"p": pred, "y": label}).dropna()
    n = len(both)
    if n < 10 or both["p"].std() == 0 or both["y"].std() == 0:
        return float("nan"), int(n)
    return float(both["p"].corr(both["y"], method="spearman")), int(n)


def main() -> None:
    from sklearn import __version__ as skv
    log(f"sklearn {skv}; building panels (this is the slow part) ...")
    panelA = build_panel_A()[0]
    panelD = build_panel_D()
    panelA["t"] = pd.to_datetime(panelA["t"], utc=True)
    panelD["t"] = pd.to_datetime(panelD["t"], utc=True)
    featsA = feats_of(panelA)
    featsD = feats_of(panelD)
    log(f"featsA={len(featsA)} featsD={len(featsD)}")
    assert "y" in panelA.columns and "y6" in panelD.columns and "y18" in panelD.columns
    assert all(f in featsD for f in ("cb_btc_dev", "cb_btc_z", "cb_btc_chg", "cb_eth_z", "cb_eth_chg"))

    # Opens pivot for the diagnostic (causal next-bar returns, truncated before END).
    opens = panelA.pivot_table(index="t", columns="sym", values="open").sort_index()
    opens = opens[opens.index < END]

    EMB_A = 42 + 10 * 6  # v92 EMBARGO_BARS = H + 10*PD = 102
    EMB_D = 18 + 10 * 6  # v103 EMBARGO = max(HS) + 10*PD = 78

    # ---- train stale + fresh models ----
    staleA, freshA, info = {}, {}, {"featsA": featsA, "featsD": featsD}
    for c in CUTS:
        m, cutoff, ntr = train_hgb(panelA, featsA, "y", 42, EMB_A, c)
        staleA[str(c.date())] = m
        info[f"A_stale_{c.date()}"] = {"cutoff": str(cutoff), "train_rows": ntr}
        log(f"A stale {c.date()}: cutoff {cutoff.date()} train_rows {ntr}")
    for a in ANCHORS:
        m, cutoff, ntr = train_hgb(panelA, featsA, "y", 42, EMB_A, a)
        freshA[str(a.date())] = m
        info[f"A_fresh_{a.date()}"] = {"cutoff": str(cutoff), "train_rows": ntr}
        log(f"A fresh {a.date()}: cutoff {cutoff.date()} train_rows {ntr}")

    staleD, freshD = {}, {}
    for c in CUTS:
        ms = {}
        for h, lab in ((6, "y6"), (18, "y18")):
            m, cutoff, ntr = train_hgb(panelD, featsD, lab, h, EMB_D, c)
            ms[lab] = m
            info[f"D_stale_{c.date()}_{lab}"] = {"cutoff": str(cutoff), "train_rows": ntr}
        staleD[str(c.date())] = ms
        log(f"D stale {c.date()}: cutoff {cutoff.date()} done")
    for a in ANCHORS:
        ms = {}
        for h, lab in ((6, "y6"), (18, "y18")):
            m, cutoff, ntr = train_hgb(panelD, featsD, lab, h, EMB_D, a)
            ms[lab] = m
            info[f"D_fresh_{a.date()}_{lab}"] = {"cutoff": str(cutoff), "train_rows": ntr}
        freshD[str(a.date())] = ms
        log(f"D fresh {a.date()}: cutoff {cutoff.date()} done")

    # ---- prediction grids ----
    gridA = panelA[(panelA.t >= CUTS[0]) & (panelA.t < END)].copy()
    gridD = panelD[(panelD.t >= CUTS[0]) & (panelD.t < END)].copy()
    for cstr, m in staleA.items():
        gridA[f"stale_{cstr}"] = m.predict(gridA[featsA])
    anchor_of = {}
    for t in gridA["t"].unique():
        ts = pd.Timestamp(t)
        cand = [a for a in ANCHORS if a <= ts]
        anchor_of[str(ts)] = str(max(cand).date()) if cand else None
    gridA["fresh_anchor"] = gridA["t"].astype(str).map(anchor_of)
    gridA["pred_fresh"] = np.nan
    for astr, m in freshA.items():
        mk = gridA["fresh_anchor"] == astr
        gridA.loc[mk, "pred_fresh"] = m.predict(gridA.loc[mk, featsA])
    for cstr, ms in staleD.items():
        gridD[f"stale_{cstr}"] = (ms["y6"].predict(gridD[featsD]) + ms["y18"].predict(gridD[featsD])) / 2
    gridD["fresh_anchor"] = gridD["t"].astype(str).map(anchor_of)
    gridD["pred_fresh"] = np.nan
    for astr, ms in freshD.items():
        mk = gridD["fresh_anchor"] == astr
        gridD.loc[mk, "pred_fresh"] = (ms["y6"].predict(gridD.loc[mk, featsD]) + ms["y18"].predict(gridD.loc[mk, featsD])) / 2
    log("predictions done")

    # ---- per-bin IC + diagnostic ----
    ret1 = opens.shift(-1) / opens - 1.0  # r[t] needs open[t+1]; rows needing >= END dropped below
    rows_out = []
    for fam, grid, stale_prefix, labels in (
        ("A", gridA, "stale_", {"stale": "y", "fresh": "y"}),
        ("D", gridD, "stale_", {"stale": "y18", "fresh": "y18"}),
    ):
        for c in CUTS:
            cstr = str(c.date())
            scol = f"{stale_prefix}{cstr}"
            for k in range(8):
                lo, hi = c + k * Q, c + (k + 1) * Q
                mk = (grid.t >= lo) & (grid.t < hi) & (grid.t < END)
                # label-realised-before-END mask per label horizon
                H = 42 if fam == "A" else 18
                mk_lab = mk & (grid.t + pd.Timedelta(hours=4 * (H + 1)) < END)
                g = grid[mk_lab]
                ic_s, n_s = spearman_pooled(g[scol], g[labels["stale"]])
                gf = g[g["fresh_anchor"].notna()]
                ic_f, n_f = spearman_pooled(gf["pred_fresh"], gf[labels["fresh"]])
                # diagnostic: w=clip(pred/0.5) x next-bar return, same bars with r available
                piv = g.pivot_table(index="t", columns="sym", values=scol)
                rsub = ret1.reindex(piv.index).dropna(how="all")
                piv = piv.reindex(rsub.index)
                w = (piv / 0.5).clip(-1, 1)
                pnl = (w * rsub).sum(axis=1)
                rows_out.append({
                    "family": fam, "cut": cstr, "bin": k,
                    "age_lo_m": round(k * 3, 2), "age_hi_m": round((k + 1) * 3, 2),
                    "t_lo": str(lo.date()), "t_hi": str(min(hi, END).date()),
                    "ic_stale": round(ic_s, 4) if np.isfinite(ic_s) else None, "n_stale": n_s,
                    "ic_fresh": round(ic_f, 4) if np.isfinite(ic_f) else None, "n_fresh": n_f,
                    "ic_diff_fresh_minus_stale": (round(ic_f - ic_s, 4) if np.isfinite(ic_f) and np.isfinite(ic_s) else None),
                    "diag_pnl_sum": round(float(pnl.sum()), 6) if len(pnl) else 0.0,
                    "diag_pnl_mean_per_bar": round(float(pnl.mean()), 8) if len(pnl) else 0.0,
                    "diag_n_bars": int(len(pnl)),
                })
                log(f"{fam} cut={cstr} bin{k} [{lo.date()}..{min(hi,END).date()}]: "
                    f"IC stale {ic_s:.4f} (n={n_s}) fresh {ic_f:.4f} (n={n_f}) diag_sum {float(pnl.sum()):+.4f}")
        # D secondary label y6
        if fam == "D":
            for c in CUTS:
                cstr = str(c.date())
                scol = f"stale_{cstr}"
                for k in range(8):
                    lo, hi = c + k * Q, c + (k + 1) * Q
                    mk = (grid.t >= lo) & (grid.t < hi) & (grid.t + pd.Timedelta(hours=4 * 7) < END)
                    g = grid[mk]
                    ic_s, n_s = spearman_pooled(g[scol], g["y6"])
                    gf = g[g["fresh_anchor"].notna()]
                    ic_f, _ = spearman_pooled(gf["pred_fresh"], gf["y6"])
                    for r in rows_out:
                        if r["family"] == "D" and r["cut"] == cstr and r["bin"] == k:
                            r["ic_stale_y6"] = round(ic_s, 4) if np.isfinite(ic_s) else None
                            r["ic_fresh_y6"] = round(ic_f, 4) if np.isfinite(ic_f) else None

    # halving ages
    halv = {}
    for fam in ("A", "D"):
        for c in CUTS:
            cstr = str(c.date())
            curve = [r for r in rows_out if r["family"] == fam and r["cut"] == cstr]
            ic0 = curve[0]["ic_stale"]
            if ic0 is None or not np.isfinite(ic0) or ic0 <= 0:
                halv[f"{fam}_{cstr}"] = "no positive skill at age 0"
            else:
                hit = next((r for r in curve[1:] if r["ic_stale"] is not None and r["ic_stale"] <= 0.5 * ic0), None)
                halv[f"{fam}_{cstr}"] = (f"halves at {hit['age_lo_m']}-{hit['age_hi_m']}m"
                                         if hit else "no halving within 24m")

    out = {
        "cuts": [str(c.date()) for c in CUTS],
        "anchors_fresh": [str(a.date()) for a in ANCHORS],
        "definitions": ("stale = HGB frozen at C (native embargo cutoff); fresh = yearly walk-forward HGB, "
                        "same bars; A: pred vs y42 (7d vol-norm); D primary: pred=mean(y6,y18) vs y18 "
                        "(secondary vs y6); pooled Spearman over 5 majors per 3m age bin; "
                        "diag pnl = clip(pred/0.5,-1,1) x next-4h-bar open return, gross, labelled diagnostic; "
                        "labels only where realised < 2025-09-24; no data >= 2025-09-24 used."),
        "fit_info": info,
        "halving": halv,
        "rows": rows_out,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    pd.DataFrame(rows_out).to_csv(HERE / "staleness.csv", index=False)

    # PNG: IC vs age, one panel per family, cuts as series (stale solid, fresh dashed)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    for j, fam in enumerate(("A", "D")):
        for c in CUTS:
            cstr = str(c.date())
            curve = [r for r in rows_out if r["family"] == fam and r["cut"] == cstr]
            xs = [(r["age_lo_m"] + r["age_hi_m"]) / 2 for r in curve]
            ax[j].plot(xs, [r["ic_stale"] for r in curve], "-o", ms=3, label=f"stale {cstr}")
            ax[j].plot(xs, [r["ic_fresh"] for r in curve], "--s", ms=3, alpha=0.6, label=f"fresh {cstr}")
        ax[j].axhline(0, color="k", lw=0.5)
        ax[j].set_title(f"family {fam} pooled IC vs model age")
        ax[j].set_xlabel("model age (months)")
        ax[j].legend(fontsize=7)
    ax[0].set_ylabel("pooled Spearman IC")
    fig.suptitle("oc_staleness: stale (frozen at C) vs fresh (yearly) IC per 3m bin (data < 2025-09-24)")
    fig.tight_layout()
    fig.savefig(HERE / "staleness_ic.png", dpi=120)
    log(f"wrote results.json ({len(rows_out)} rows), staleness.csv, staleness_ic.png")
    log(f"halving: {json.dumps(halv)}")


if __name__ == "__main__":
    main()
