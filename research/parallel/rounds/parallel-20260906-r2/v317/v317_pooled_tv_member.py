"""v317: POOLED-EXPERIENCE TV member PT for both products (registry v317).

v316 (registered, dev only): the v94 horizon ensemble trained on majors + the survivorship-free U2020 alts beat the majors-only control in IC in 3 of
4 dev years (2023: 0.186 vs 0.089) and as a 20% blend (MANUAL dev4 2.75 vs 2.50) -> pooled experience is a candidate. v317 applies it to the
stronger feature set and produces walk-forward books for all five anchors.
MEMBER PT = v94 horizon ensemble (y18 / y42 / y84, HGB v94 hyper-parameters, seed 0) on v92 features + the 17 TradingView indicators
(v231 tv_features, computed per symbol from its own 4h OHLCV, alts included) + BTC cross features, trained on the 5 majors + 72 U2020 alts (asset id 5
for every alt), predicting the majors; annual fits per anchor (cutoff = anchor - v94 embargo, labels ending before the cutoff) and the quarterly
twin PTq (refit at each quarter start of the anchor year with cutoff = quarter start - embargo). Control CT / CTq = the same on the majors rows only.
Books = v94.weights_ls(shorts=True) of the mean horizon prediction. Group = (annual + quarterly) / 2, as every audited member.
ROWS (fixed before running; base = (2 A + 2 B + D) / 5, the G2 / CB books):
  MANUAL (sleeve off; G2 manual rules target 0.25 cap 2; and the v315 pullback-entry rules entry 0.75 sigma_4h / 3 bars):
    M0 base | M1 0.8 base + 0.2 PT | M2 (2 A + 2 PT + D) / 5 (PT replaces the TV member B) | M3 0.8 base + 0.2 CT (control)
  BOT (G2 bar-open: dip size / TP agents fit G2, budget 0.26, C4 rules, v306 machinery):
    B0 base | B1 0.8 base + 0.2 PT | B2 (2 A + 2 PT + D) / 5
SELECTION per product and rule set (dev years only): among {M1, M2} (resp. {B1, B2}) the highest v310 robust fitness on dev4 (MANUAL fitness for the
manual rows; for BOT the v306 BOT fitness); it replaces the base only if its fitness beats the base's AND beats the control-member row (MANUAL M3).
The most recent year is scored ONCE for each selected row (and reported next to the already-known base rows).

  python research/parallel/rounds/parallel-20260906-r2/v317/v317_pooled_tv_member.py
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
RD = HERE.parent
C = Path("artifacts/research/engine_real")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v316 = _load("v316_t", RD / "v316/v316_pooled_universe_book_member.py")


def build_panel(log):
    v144 = _load("v144_t", RD / "v144/v144_deploy_v3.py")
    ext = v144.v115.v114.v113
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    v92, v94 = ext.v92, ext.v94
    v240 = _load("v240_t", RD / "v240/v240_order_level_flow.py")
    tvm = v240.tvm
    majors = v92.build()
    tvs = []
    for s in v92.SYMS:
        b, _, _ = ext.load_asset_ext(s)
        tvs.append(pd.concat([pd.DataFrame({"t": pd.DatetimeIndex(b["open_time"]), "sym": s}), tvm.tv_features(b).reset_index(drop=True)], axis=1))
    majors = majors.merge(pd.concat(tvs, ignore_index=True), on=["t", "sym"], how="left")
    btc = majors[majors.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    v = pd.read_csv("data/raw/um_universe_20260930/volume_2020_12.csv")
    uni = list(v[(v.days >= 28) & ~v.symbol.isin(v92.SYMS)].sort_values("quote_volume_usd", ascending=False).symbol)
    rows = []
    for s in uni:
        try:
            b, d, f = v316.alt_asset(s)
        except Exception as e:  # noqa: BLE001
            log(f"alt {s} skipped: {e}")
            continue
        if len(b) < 600:
            continue
        x, y = v92.features(b, d, f)
        x["asset"], x["y"], x["t"], x["open"], x["sym"], x["bar"] = 5, y, pd.DatetimeIndex(b["open_time"]), b["open"].to_numpy(), s, np.arange(len(b))
        tv = tvm.tv_features(b.reset_index(drop=True)).reset_index(drop=True)
        x = pd.concat([x.reset_index(drop=True), tv], axis=1)
        rows.append(x.join(btc, on="t"))
    panel = v94.add_targets(pd.concat([majors] + rows, ignore_index=True))
    feats = [c for c in majors.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    alt = ~panel.sym.isin(v92.SYMS)
    log(f"panel {len(panel)} rows, {panel.sym.nunique()} symbols, {len(feats)} features; alt rows with BTC cross features "
        f"{float(panel.loc[alt, 'btc_ret42'].notna().mean()):.3f}, with TV {float(panel.loc[alt, 'tv_st_dir'].notna().mean()):.3f}")
    return panel, feats, v92, v94


def fit_books(panel, feats, v92, v94, pooled, quarterly, log, tag):
    is_major = panel.sym.isin(v92.SYMS)
    train_mask = pd.Series(True, index=panel.index) if pooled else is_major
    oos = []
    for a in v92.ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        starts = [a0 + pd.Timedelta(days=91 * q) for q in range(4)] if quarterly else [a0]
        for qi, q0 in enumerate(starts):
            q1 = starts[qi + 1] if qi + 1 < len(starts) else a0 + pd.Timedelta(days=365)
            cutoff = q0 - pd.Timedelta(hours=4 * v94.EMBARGO_BARS)
            te = panel[is_major & (panel.t >= q0) & (panel.t < q1)].copy()
            preds = []
            for h in v94.HORIZONS:
                tr = panel[train_mask & (panel.t < cutoff) & panel[f"y{h}"].notna()]
                tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
                m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0,
                                                  random_state=0)
                m.fit(tr[feats], tr[f"y{h}"])
                preds.append(m.predict(te[feats]))
            te["pred"] = np.mean(preds, axis=0)
            oos.append(te)
        log(f"{tag} anchor {a} done")
    oos = pd.concat(oos, ignore_index=True)
    ic = {a: round(float(oos[(oos.t >= pd.Timestamp(a, tz="UTC")) & (oos.t < pd.Timestamp(a, tz="UTC") + pd.Timedelta(days=365))][["pred", "y42"]]
                         .corr(method="spearman").iloc[0, 1]), 4) for a in v92.ANCHORS[:4]}
    return v94.weights_ls(oos, True), ic


def main():
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    names = {"PT": (True, False), "PTq": (True, True), "CT": (False, False), "CTq": (False, True)}
    out = {"version": "v317", "ic_dev": {}, "manual": {}, "bot": {}}
    if not all((C / f"member_{n}_pooledtv.parquet").exists() for n in names):
        panel, feats, v92, v94 = build_panel(log)
        for n, (pooled, quarterly) in names.items():
            W, ic = fit_books(panel, feats, v92, v94, pooled, quarterly, log, n)
            W.to_parquet(C / f"member_{n}_pooledtv.parquet")
            out["ic_dev"][n] = ic
            log(f"member {n} IC dev {ic}")
    # ---------------- MANUAL rows
    v310 = _load("v310_t", RD / "v310/v310_manual_book_robust_evolution.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols = W0["idx"], W0["cols"]
    rd = lambda n: pd.read_parquet(C / f"member_{n}_pooledtv.parquet").reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    PT, CT = (rd("PT") + rd("PTq")) / 2, (rd("CT") + rd("CTq")) / 2
    A, B, D = W0["grp"]["wA"].copy(), W0["grp"]["wB"].copy(), W0["grp"]["wD"].copy()
    base = (2 * A + 2 * B + D) / 5
    mixes = {"M0": base, "M1": 0.8 * base + 0.2 * PT, "M2": (2 * A + 2 * PT + D) / 5, "M3": 0.8 * base + 0.2 * CT}
    v315 = _load("v315_t", RD / "v315/v315_manual_pullback_entry.py")
    v315.v310 = v310
    v315.BASE_P9 = v310._policy9
    res_m = {}
    for rules in ("g2", "pullback"):
        for k, mix in mixes.items():
            W0["grp"]["wA"] = W0["grp"]["wB"] = W0["grp"]["wD"] = mix  # weights (2, 2, 1) normalise to exactly the mix
            if rules == "g2":
                r = v310.run_genome(v310.encode(dict(target=0.25, cap=2.0)))
            else:
                r = v315.run(0.75, 3)
            res_m[(rules, k)] = r
            out["manual"][f"{rules}:{k}"] = dict(dev4=v310.metrics(r, [0, 1, 2, 3]), F=round(v310.fitness(r, [0, 1, 2, 3]), 4))
            log(f"MANUAL {rules} {k} {out['manual'][f'{rules}:{k}']}")
    W0["grp"]["wA"], W0["grp"]["wB"], W0["grp"]["wD"] = A, B, D
    assert abs(out["manual"]["g2:M0"]["dev4"]["R"] - 2.502) < 0.003
    sel_m = {}
    for rules in ("g2", "pullback"):
        F = lambda k: v310.fitness(res_m[(rules, k)], [0, 1, 2, 3])
        best = max(("M1", "M2"), key=F)
        ok = F(best) > F("M0") and F(best) > F("M3")
        sel_m[rules] = best if ok else None
        log(f"MANUAL {rules}: selected {sel_m[rules]} (F {F(best):.4f} vs base {F('M0'):.4f} vs control {F('M3'):.4f})")
    # ---------------- BOT rows (v306 machinery, G2 genome)
    v306 = _load("v306_t", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    W6 = v306.W
    A6, B6, D6 = W6["grp"]["wA"].copy(), W6["grp"]["wB"].copy(), W6["grp"]["wD"].copy()
    base6 = (2 * A6 + 2 * B6 + D6) / 5
    bmix = {"B0": base6, "B1": 0.8 * base6 + 0.2 * PT, "B2": (2 * A6 + 2 * PT + D6) / 5}
    res_b = {}
    for k, mix in bmix.items():
        W6["grp"]["wA"] = W6["grp"]["wB"] = W6["grp"]["wD"] = mix
        r = v306.run_genome(v306.encode({}))
        res_b[k] = r
        out["bot"][k] = dict(dev4=v306.metrics(r, [0, 1, 2, 3]), F=round(v306.fitness(r, [0, 1, 2, 3]), 4))
        log(f"BOT {k} {out['bot'][k]}")
    assert abs(out["bot"]["B0"]["dev4"]["R"] - 6.504) < 0.003
    Fb = lambda k: v306.fitness(res_b[k], [0, 1, 2, 3])
    bb = max(("B1", "B2"), key=Fb)
    sel_b = bb if Fb(bb) > Fb("B0") else None
    log(f"BOT: selected {sel_b} (F {Fb(bb):.4f} vs base {Fb('B0'):.4f})")
    out["selected"] = dict(manual=sel_m, bot=sel_b)
    # ---------------- the most recent year, once, for the selected rows
    final = {}
    for rules, k in sel_m.items():
        if k is None:
            continue
        W0["grp"]["wA"] = W0["grp"]["wB"] = W0["grp"]["wD"] = mixes[k]
        r = v310.run_genome(v310.encode(dict(target=0.25, cap=2.0)), True) if rules == "g2" else v315.run(0.75, 3, True)
        final[f"manual:{rules}:{k}"] = dict(last_year=v310.metrics(r, [4]), five_years=v310.metrics(r, [0, 1, 2, 3, 4]),
                                            full={q: r[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
        log(f"FINAL manual {rules} {k} {final[f'manual:{rules}:{k}']}")
    W0["grp"]["wA"], W0["grp"]["wB"], W0["grp"]["wD"] = A, B, D
    if sel_b:
        W6["grp"]["wA"] = W6["grp"]["wB"] = W6["grp"]["wD"] = bmix[sel_b]
        r = v306.run_genome(v306.encode({}), True)
        final[f"bot:{sel_b}"] = dict(last_year=v306.metrics(r, [4]), five_years=v306.metrics(r, [0, 1, 2, 3, 4]),
                                     full={q: r[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
        log(f"FINAL bot {sel_b} {final[f'bot:{sel_b}']}")
    out["final"] = final
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v317_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
