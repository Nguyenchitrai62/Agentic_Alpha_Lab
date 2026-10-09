"""oc_costlabel: retrain the whale-flow book member on a COST-THRESHOLDED binary label.

Per PLAN.md (pre-registered 2026-10-08, read it first). Steps:
  --check : rebuild deployed A/Aq exactly (v240 logic) and require
            Spearman(repro, cache) >= 0.999 per anchor year for both.
  --train <thr_bps> : retrain annual+quarterly members with EVERY return target
            replaced by the single binary cost label
              y_cost = 1{ log(open[t+1+6]/open[t+1]) > thr }
            (thr = 8bps CV1 / 5bps CV2, h=6, raw, o[T+1]-based, horizonfix rule).
            One HGB Classifier per original sub-model slot
            (v92:1, v94:3 with filters 19/43/85 bars, v103:2 with filters 7/19
            bars; same features/hyperparams/filters/anchors/embargoes as deployed),
            mean proba per sub-model, then per-anchor per-sub-model
            IsotonicRegression (pre-anchor in-sample proba -> pre-anchor
            in-sample deployed-regressor pred) mapping back to the existing
            weight scale; downstream raw/phased/vol_target_scale unchanged.
  --iso-report : print isotonic fit diagnostics from training logs.

HEAVY (HGB training): run via
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_costlabel --min-free-gb 2.0 -- <this> ...
CPU only. Writes ONLY inside research/tournament/oc_costlabel/.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
CACHE = ROOT / "artifacts/research/engine_real"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR = pd.Timedelta(days=365)
YLABELS = [f"{y}-09-24" for y in (2021, 2022, 2023, 2024, 2025)]
H_COST = 6
THR = {8: 0.0008, 5: 0.0005}

_uid = [0]


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] oc_costlabel: {msg}", flush=True)


def _load(name: str, path) -> object:
    _uid[0] += 1
    modname = f"{name}_{_uid[0]}"
    spec = importlib.util.spec_from_file_location(modname, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


def add_y_cost(panel: pd.DataFrame, thr: float, h: int = H_COST) -> pd.DataFrame:
    """Add binary cost label y_cost = 1{log(open[t+1+h]/open[t+1]) > thr}.

    Per symbol on time-sorted rows from the panel's own `open`
    (raw log return, NOT vol-normalised; o[T+1]-based horizonfix forward).
    Tail rows without a realised forward get NaN. Original y* columns kept.
    """
    out = []
    for s, g in panel.groupby("sym", sort=False):
        g = g.sort_values("t").copy()
        o = g["open"].to_numpy(dtype=float)
        n = len(g)
        fwd = np.full(n, np.nan)
        if n - 1 - h > 0:
            with np.errstate(divide="ignore", invalid="ignore"):
                fwd[: n - 1 - h] = np.log(o[1 + h:] / o[1: n - h])
        yc = np.where(np.isfinite(fwd), (fwd > thr).astype(float), np.nan)
        g["y_cost"] = yc
        out.append(g)
    return pd.concat(out, ignore_index=True)


def build_member_orig(quarterly: bool):
    """Reproduce v240.build_member(quarterly, keep_fills=False) exactly."""
    tag = f"{'q' if quarterly else 'a'}_orig"
    v202 = _load(f"v202_cl_{tag}", RD / "v202/v202_quarterly_retrain.py")
    v144 = _load(f"v144_cl_{tag}", RD / "v144/v144_deploy_v3.py")
    if quarterly:
        v202.quarterly(v144)
    ext, v103 = v144.v115.v114.v113, v144.v103
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    v240 = _load(f"v240_cl_{tag}", RD / "v240/v240_order_level_flow.py")
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    log(f"building base92 panel ({tag}) ...")
    base92 = b92()
    log(f"base92 ({tag}): {base92.shape}")
    xf = v240.feature_frame(ext.v92.load_asset, False)
    log(f"order-flow xf ({tag}): {xf.shape}")
    drop = {c for c in xf.columns if c not in ("t", "sym")}
    v144.v129.vol_predict = (
        lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in drop], anchors, emb)
    )
    ext.v92.build = lambda: base92.merge(xf, on=["t", "sym"], how="left")
    v103.build = lambda: b103().merge(xf, on=["t", "sym"], how="left")
    log(f"training books_v142 ({tag}; quarterly={quarterly}) ...")
    t0 = time.time()
    books = v144.books_v142()[1]
    log(f"books ({tag}) done: {books.shape} in {time.time() - t0:.0f}s")
    return books


def _cost_predictors(thr: float):
    """Factory for cost-aware train_predict wrappers (classifier + isotonic).

    Mirrors the deployed structure: v92 1 slot (filter H=42), v94 3 slots
    (filters H=18/42/84), v103 2 slots (filters H=6/18); each slot trains one
    HGB Classifier on y_cost with its OWN original filter, proba averaged per
    sub-model, then mapped via per-anchor per-sub-model IsotonicRegression
    fitted on pre-anchor in-sample (proba -> deployed-regressor pred) rows.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    from sklearn.isotonic import IsotonicRegression

    HGB_KW = dict(max_depth=4, learning_rate=0.03, max_iter=400,
                  min_samples_leaf=300, l2_regularization=1.0, random_state=0)

    def _ycost_tr(panel: pd.DataFrame, cutoff: pd.Timestamp, h_filt: int):
        p = add_y_cost(panel, thr)
        tr = p[(p.t < cutoff) & p["y_cost"].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h_filt + 1)) < cutoff]
        return tr

    def _fit_iso(proba_tr: np.ndarray, pred_tr: np.ndarray) -> IsotonicRegression:
        iso = IsotonicRegression(out_of_bounds="clip")
        order = np.argsort(proba_tr, kind="mergesort")
        iso.fit(proba_tr[order], pred_tr[order])
        return iso

    def tp92_cost(panel, anchor, _orig_tp, feats_holder):
        from pandas import Timestamp
        a = Timestamp(anchor, tz="UTC")
        cutoff = a - pd.Timedelta(hours=4 * 102)
        te = panel[(panel.t >= a) & (panel.t < a + YEAR)].copy()
        feats = feats_holder["feats"]
        # deployed regressor (iso target) on original y, same filter
        tr_d = panel[(panel.t < cutoff) & panel["y"].notna()]
        tr_d = tr_d[tr_d.t + pd.Timedelta(hours=4 * (42 + 1)) < cutoff]
        tr_c = _ycost_tr(panel, cutoff, 42)
        assert len(tr_d) > 100 and len(tr_c) > 100, (len(tr_d), len(tr_c))
        mr = HistGradientBoostingRegressor(**HGB_KW)
        mr.fit(tr_d[feats], tr_d["y"])
        mc = HistGradientBoostingClassifier(**HGB_KW)
        mc.fit(tr_c[feats], tr_c["y_cost"].astype(int))
        inter = tr_c.merge(tr_d[["t", "sym"]], on=["t", "sym"], how="inner")
        p_tr = mc.predict_proba(inter[feats])[:, 1]
        y_tr = mr.predict(inter[feats])
        iso = _fit_iso(p_tr, y_tr)
        p_te = mc.predict_proba(te[feats])[:, 1]
        te["pred"] = iso.predict(p_te)
        sp = float(pd.Series(p_tr).corr(pd.Series(y_tr), method="spearman"))
        log(f"tp92 thr={thr} anchor={str(a.date())} ntr_c={len(tr_c)} posrate={tr_c['y_cost'].mean():.4f} iso_tr_spearman={sp:.4f}")
        return te, {"n_c": len(tr_c), "posrate": round(float(tr_c["y_cost"].mean()), 4)}

    def tp94_cost(panel, anchor, feats, _orig_tp):
        from pandas import Timestamp
        a = Timestamp(anchor, tz="UTC")
        cutoff = a - pd.Timedelta(hours=4 * 144)
        te = panel[(panel.t >= a) & (panel.t < a + YEAR)].copy()
        proba_te, proba_tr_list, pred_tr_list, inter0 = [], [], [], None
        n_c = {}
        for h in (18, 42, 84):
            col = f"y{h}"
            tr_d = panel[(panel.t < cutoff) & panel[col].notna()]
            tr_d = tr_d[tr_d.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
            tr_c = _ycost_tr(panel, cutoff, h)
            assert len(tr_d) > 100 and len(tr_c) > 100, (h, len(tr_d), len(tr_c))
            mr = HistGradientBoostingRegressor(**HGB_KW)
            mr.fit(tr_d[feats], tr_d[col])
            mc = HistGradientBoostingClassifier(**HGB_KW)
            mc.fit(tr_c[feats], tr_c["y_cost"].astype(int))
            proba_te.append(mc.predict_proba(te[feats])[:, 1])
            n_c[h] = len(tr_c)
            if h == 84:
                inter0 = tr_c.merge(tr_d[["t", "sym"]], on=["t", "sym"], how="inner")
                p84 = mc.predict_proba(inter0[feats])[:, 1]
                y84 = mr.predict(inter0[feats])
                proba_tr_list.append(p84)
                pred_tr_list.append(y84)
        # iso on the strictest (h=84) intersection rows only (conservative subset)
        iso = _fit_iso(proba_tr_list[0], pred_tr_list[0])
        p_te = np.mean(proba_te, axis=0)
        te["pred"] = iso.predict(p_te)
        te["y"] = te["y42"]
        sp = float(pd.Series(proba_tr_list[0]).corr(pd.Series(pred_tr_list[0]), method="spearman"))
        log(f"tp94 thr={thr} anchor={str(a.date())} ntr={n_c} iso_tr_spearman={sp:.4f}")
        return te, n_c

    def tp103_cost(panel, anchor, feats, _orig_tp):
        from pandas import Timestamp
        a = Timestamp(anchor, tz="UTC")
        cutoff = a - pd.Timedelta(hours=4 * 78)
        te = panel[(panel.t >= a) & (panel.t < a + YEAR)].copy()
        proba_te = []
        n_c = {}
        iso_ref = {}
        for h in (6, 18):
            col = f"y{h}"
            tr_d = panel[(panel.t < cutoff) & panel[col].notna()]
            tr_d = tr_d[tr_d.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
            tr_c = _ycost_tr(panel, cutoff, h)
            assert len(tr_d) > 100 and len(tr_c) > 100, (h, len(tr_d), len(tr_c))
            mr = HistGradientBoostingRegressor(**HGB_KW)
            mr.fit(tr_d[feats], tr_d[col])
            mc = HistGradientBoostingClassifier(**HGB_KW)
            mc.fit(tr_c[feats], tr_c["y_cost"].astype(int))
            proba_te.append(mc.predict_proba(te[feats])[:, 1])
            n_c[h] = len(tr_c)
            if h == 18:
                inter = tr_c.merge(tr_d[["t", "sym"]], on=["t", "sym"], how="inner")
                iso_ref["p"] = mc.predict_proba(inter[feats])[:, 1]
                iso_ref["y"] = mr.predict(inter[feats])
        iso = _fit_iso(iso_ref["p"], iso_ref["y"])
        p_te = np.mean(proba_te, axis=0)
        te["pred"] = iso.predict(p_te)
        sp = float(pd.Series(iso_ref["p"]).corr(pd.Series(iso_ref["y"]), method="spearman"))
        log(f"tp103 thr={thr} anchor={str(a.date())} ntr={n_c} iso_tr_spearman={sp:.4f}")
        return te, n_c

    return tp92_cost, tp94_cost, tp103_cost


def build_member_cost(quarterly: bool, thr: float):
    """Retrain A/Aq with the binary cost label (thr) + isotonic mapping."""
    tag = f"{'q' if quarterly else 'a'}_c{int(thr * 10000)}"
    v202 = _load(f"v202_clc_{tag}", RD / "v202/v202_quarterly_retrain.py")
    v144 = _load(f"v144_clc_{tag}", RD / "v144/v144_deploy_v3.py")
    if quarterly:
        v202.quarterly(v144)
    ext, v103 = v144.v115.v114.v113, v144.v103
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    v240 = _load(f"v240_clc_{tag}", RD / "v240/v240_order_level_flow.py")
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    log(f"building base92 panel ({tag}) ...")
    base92 = b92()
    log(f"base92 ({tag}): {base92.shape}")
    xf = v240.feature_frame(ext.v92.load_asset, False)
    log(f"order-flow xf ({tag}): {xf.shape}")
    drop = {c for c in xf.columns if c not in ("t", "sym")}
    v144.v129.vol_predict = (
        lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in drop], anchors, emb)
    )
    ext.v92.build = lambda: base92.merge(xf, on=["t", "sym"], how="left")
    v103.build = lambda: b103().merge(xf, on=["t", "sym"], how="left")

    tp92_cost, tp94_cost, tp103_cost = _cost_predictors(thr)
    o92, o94, o103 = ext.v92.train_predict, ext.v94.train_predict, v103.train_predict
    feats92 = {}
    # NOTE (quarterly cut): v202.quarterly() wrapped the ORIGINAL train_predict
    # fns with _cut to [anchor, next_anchor). This cost path calls the cost
    # predictors directly, so the same cut must be applied here explicitly
    # (else the 20 quarterly year-long predictions overlap -> duplicate index).
    _v202 = v202
    _is_q = bool(quarterly)

    def _cut_q(df, a):
        if not _is_q:
            return df
        return _v202._cut(df, str(pd.Timestamp(a, tz="UTC").date()))

    # Patch train_predict to cost versions, then call the real books_v142 body
    # via a local re-implementation identical to v144.books_v142 except routing
    # through the cost predictors (features/blend/vol-target code untouched).
    v142mod = v144.v142 if hasattr(v144, "v142") else None
    ext_v92, v103mod, v129mod, v125mod = ext.v92, v103, v144.v129, v144.v125

    def books_v142_cost():
        p92 = ext_v92.build()
        f92_base = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
        p92x = v144.v142.add_xs(p92, v144.v142.BASE)
        ext_v92.FEATS = [c for c in p92x.columns if c not in ("y", "t", "open", "sym", "bar")]
        feats92["feats"] = list(ext_v92.FEATS)
        lo = pd.concat(
            [_cut_q(tp92_cost(p92x, a, o92, feats92)[0], a) for a in ext_v92.ANCHORS], ignore_index=True
        )
        p94 = ext.v94.add_targets(p92x)
        f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
        ls = pd.concat(
            [_cut_q(tp94_cost(p94, a, f94, o94)[0], a) for a in ext_v92.ANCHORS], ignore_index=True
        )
        p103 = v103mod.build()
        f103_base = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
        p103x = v144.v142.add_xs(p103, v144.v142.BASE + v144.v142.FLOWX)
        f103 = [c for c in p103x.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
        fl = pd.concat(
            [_cut_q(tp103_cost(p103x, a, f103, o103)[0], a) for a in ext_v92.ANCHORS], ignore_index=True
        )
        pv92, _ = v129mod.vol_predict(p92, f92_base, ext_v92.ANCHORS, ext_v92.EMBARGO_BARS)
        pv103, _ = v129mod.vol_predict(p103, f103_base, ext_v92.ANCHORS, ext_v92.EMBARGO_BARS)

        def swap(df, pv):
            d = df.merge(pv, on=["t", "sym"], how="left")
            d["vol42"] = d["pvol"].fillna(d["vol42"])
            return d.drop(columns="pvol")

        ph = list(range(v144.PD))
        W_lo = v144.v125.phased(v144.v125.raw_lo(swap(lo, pv92)), ph)
        W94 = v144.v125.phased(v144.v125.raw_ls(swap(ls, pv92)), ph)
        W103 = v144.v125.phased(v144.v125.raw_ls(swap(fl, pv103)), ph)
        idx = W_lo.index.union(W94.index).union(W103.index)
        idx = idx[idx >= p103.t.min()]
        books = 0.25 * W_lo.reindex(idx).fillna(0.0).mul(
            ext.v94.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0
        ) + 0.25 * W94.reindex(idx).fillna(0.0).mul(
            ext.v94.vol_target_scale(p92, W94).reindex(idx).fillna(1.0), axis=0
        ) + 0.5 * W103.reindex(idx).fillna(0.0).mul(
            ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0
        )
        return p103, books

    log(f"training cost books ({tag}; quarterly={quarterly}, thr={thr}) ...")
    t0 = time.time()
    books = books_v142_cost()[1]
    log(f"cost books ({tag}) done: {books.shape} in {time.time() - t0:.0f}s")
    return books


def spearman_per_year(repro: pd.DataFrame, ref: pd.DataFrame, grid: pd.DatetimeIndex) -> dict:
    a = repro.reindex(grid).fillna(0.0)
    b = ref.reindex(grid).fillna(0.0)
    out = {}
    for ylab, a0 in zip(YLABELS, ANCHORS):
        m = (grid >= a0) & (grid < a0 + YEAR)
        x = a.loc[m].stack()
        yy = b.loc[m].stack()
        c = float(pd.DataFrame({"x": x, "y": yy}).corr(method="spearman").iloc[0, 1])
        out[ylab] = round(c, 6)
    return out


def cmd_check() -> None:
    eu = _load("eu_cl_check", RD / "engine_user/engine_user.py")
    books154, _ = eu.er.v154_books()
    grid = books154.index
    ok = True
    for name, q, cache_f in (("A", False, "member_A_O1_orders.parquet"),
                             ("Aq", True, "member_Aq_O1_orders.parquet")):
        repro = build_member_orig(q)
        ref = pd.read_parquet(CACHE / cache_f)
        per = spearman_per_year(repro, ref, grid)
        for ylab, c in per.items():
            flag = "OK" if c >= 0.999 else "FAIL"
            if c < 0.999:
                ok = False
            log(f"builder check {name} year {ylab}: Spearman={c:.6f} [{flag}]")
    res = {"builder_check": "pass" if ok else "FAIL"}
    (HERE / "tmp" / "builder_check.json").write_text(json.dumps(res, indent=1))
    if not ok:
        log("BUILDER CHECK FAILED: stop and report (no training, no engine).")
        raise SystemExit(1)
    log("builder check PASS (>= 0.999 every anchor year for A and Aq).")


def cmd_train(thr_bps: int) -> None:
    assert thr_bps in (5, 8)
    chk = json.loads((HERE / "tmp" / "builder_check.json").read_text())
    assert chk.get("builder_check") == "pass", "run --check (pass) before --train"
    thr = THR[thr_bps]
    for name, q in ((f"C{thr_bps}", False), (f"C{thr_bps}q", True)):
        out = HERE / f"member_{name}.parquet"
        if out.exists():
            log(f"{name} exists, skip ({out})")
            continue
        books = build_member_cost(q, thr)
        books.index.name = "t"
        books.to_parquet(out)
        log(f"wrote {out} {books.shape}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--train", type=int, default=None)
    a = ap.parse_args()
    (HERE / "tmp").mkdir(exist_ok=True)
    if a.check:
        cmd_check()
    elif a.train is not None:
        assert a.train in (5, 8)
        cmd_train(a.train)
    else:
        raise SystemExit("pass --check or --train 5|8")


if __name__ == "__main__":
    main()
