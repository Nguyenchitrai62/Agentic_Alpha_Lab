"""v324: MANUAL product - POOLED TREND-REGIME overlay: predict HOW MUCH the next week trends (not where), scale the book by it (registry v324).

Why: the book earns from trends held > 4 days and loses its many small trades in chop (research/diagnostics/book_vs_bot/book_anatomy.py); the
direction signal is the limit (IC ~0.1), but the TRENDINESS of the coming week is a different, likely more predictable quantity (volatility and
regime persistence). Pooled 77-coin experience (v316 / v317, audits PASS) gives the model enough regime examples.
TARGET (per symbol, bar t): Kaufman efficiency ratio of the next 42 bars from the next open: ER = |log(o[t+1+42] / o[t+1])| / sum_{k=1..42}
|log(o[t+1+k] / o[t+k])| (0 = pure chop, 1 = straight line); the label window = the v92 label window (no new look-ahead).
MODEL: HGB (v94 hyper-parameters, seed 0) on the PT features (v92 + 17 TV + BTC cross), trained on the 5 majors + 72 U2020 alts (training only),
annual fits per anchor, cutoff = anchor - (84 + 60) bars, labels ending before the cutoff; predictions for the majors.
OVERLAY (fixed before running): multiplier m(t, asset) = clip(pred / q50, 0.5, 1.5) where q50 = the median prediction on the anchor's own MAJOR
training rows (in-sample, known at the anchor); books = M2 x m (M2 = (2 A + 2 PT + D) / 5); the portfolio vol target then re-normalises the
level, so the overlay moves risk toward predicted-trend regimes. Rules = M2 MANUAL (pullback 0.75 / 3 bars, target 0.25, cap 2).
Rows: R0 = M2 | R1 = M2 x m | R2 = M2 x m^2 (sharper tilt, clip 0.25 .. 2.25).
CHOICE: dev folds k = 2, 3 with the v310 robust MANUAL fitness on years [:k] among R0..R2; TRANSFER if the choice beats R0 in both folds. Final on
dev4; the most recent year computed once (M2 itself was shaped with knowledge of the most recent year -> contaminated; prospective log = clean).
Also reported: per-year Spearman IC of pred vs realised ER for the majors (dev years).

  python research/parallel/rounds/parallel-20260906-r2/v324/v324_pooled_trend_regime_overlay.py
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
H = 42


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v317 = _load("v317_er", RD / "v317/v317_pooled_tv_member.py")


def er_target(panel):
    out = []
    for s, g in panel.groupby("sym", sort=False):
        g = g.sort_values("t").copy()
        o = np.log(g["open"].to_numpy(float))
        n = len(o)
        y = np.full(n, np.nan)
        step = np.abs(np.diff(o))  # step[k] = |log o[k+1] - log o[k]|
        cs = np.concatenate([[0.0], np.cumsum(step)])
        m = n - 1 - H
        if m > 0:
            net = np.abs(o[1 + H:1 + H + m] - o[1:1 + m])
            path = cs[1 + H:1 + H + m] - cs[1:1 + m]
            y[:m] = np.where(path > 0, net / path, np.nan)
        gap = np.diff(g["t"].to_numpy()).astype("timedelta64[h]").astype(float)
        brk = np.concatenate([[False], gap != 4])
        cb = np.cumsum(brk.astype(int))
        bad = cb[np.minimum(np.arange(n) + 1 + H, n - 1)] - cb > 0  # a missing bar inside the forward window t+1 .. t+1+H -> NaN
        y[bad] = np.nan
        g["er"] = y
        out.append(g)
    return pd.concat(out, ignore_index=True)


def main():
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    mp = C / "v324_er_multiplier.parquet"
    out = {"version": "v324", "ic_dev": {}}
    if not mp.exists():
        panel, feats, v92, v94 = v317.build_panel(log)
        panel = er_target(panel)
        is_major = panel.sym.isin(v92.SYMS)
        log(f"ER labels {float(panel['er'].notna().mean()):.3f}, mean {float(panel['er'].mean()):.3f}")
        parts = []
        for a in v92.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            cutoff = a0 - pd.Timedelta(hours=4 * v94.EMBARGO_BARS)
            tr = panel[(panel.t < cutoff) & panel["er"].notna()]
            tr = tr[tr.t + pd.Timedelta(hours=4 * (H + 1)) < cutoff]
            m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0,
                                              random_state=0).fit(tr[feats], tr["er"])
            q50 = float(np.median(m.predict(tr.loc[tr.sym.isin(v92.SYMS), feats])))
            te = panel[is_major & (panel.t >= a0) & (panel.t < a0 + pd.Timedelta(days=365))].copy()
            te["pred"] = m.predict(te[feats])
            te["mult"] = np.clip(te["pred"] / q50, 0.5, 1.5)
            if a != v92.ANCHORS[-1]:
                ic = float(te[["pred", "er"]].corr(method="spearman").iloc[0, 1])
                out["ic_dev"][a] = round(ic, 4)
                log(f"anchor {a} rows {len(tr)} q50 {q50:.4f} IC(pred, ER) {ic:.4f}")
            parts.append(te[["t", "sym", "mult"]])
        M = pd.concat(parts).pivot_table(index="t", columns="sym", values="mult")
        M.to_parquet(mp)
    v310 = _load("v310_er", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_er", RD / "v315/v315_manual_pullback_entry.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols = W0["idx"], W0["cols"]
    rd = lambda n: pd.read_parquet(C / f"member_{n}_pooledtv.parquet").reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    PT = (rd("PT") + rd("PTq")) / 2
    M2 = (2 * W0["grp"]["wA"] + 2 * PT + W0["grp"]["wD"]) / 5
    mult = pd.read_parquet(mp).reindex(idx).ffill().fillna(1.0)[cols].to_numpy(float)  # multiplier of the decision bar (known at its close)
    mixes = {"R0": M2, "R1": M2 * mult, "R2": M2 * np.clip(mult ** 2, 0.25, 2.25)}
    base_p9 = v310._policy9

    def run(k, full=False):
        W0["grp"]["wA"] = W0["grp"]["wB"] = W0["grp"]["wD"] = mixes[k]
        v310._policy9 = v315.with_entry(0.75)
        v315.BASE_P9 = base_p9
        try:
            return v310.run_genome(v310.encode(dict(target=0.25, cap=2.0, n_valid=3)), full)
        finally:
            v310._policy9 = base_p9

    res = {k: run(k) for k in mixes}
    assert abs(v310.metrics(res["R0"], [0, 1, 2, 3])["R"] - 3.011) < 0.003
    out["rows"] = {k: dict(dev4=v310.metrics(r, [0, 1, 2, 3]), F=round(v310.fitness(r, [0, 1, 2, 3]), 4), years=[v310.metrics(r, [y]) for y in range(4)])
                   for k, r in res.items()}
    for k, v in out["rows"].items():
        log(f"{k} dev4 {v['dev4']} F {v['F']}")
    deltas, out["folds"] = [], {}
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v310.fitness(res[x], ys))
        f_ch, f_ref = v310.fitness(res[ch], [k]), v310.fitness(res["R0"], [k])
        out["folds"][k] = dict(choice=ch, test=v310.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_R0=round(f_ref, 4))
        deltas.append(f_ch - f_ref)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} vs R0 {f_ref:.4f}")
    out["transfer"] = dict(deltas=[round(x, 4) for x in deltas], holds=bool(all(x > 0 for x in deltas)))
    log(f"TRANSFER {out['transfer']}")
    ch = max(res, key=lambda x: v310.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v310.metrics(res[ch], [0, 1, 2, 3]), last_year=v310.metrics(full, [4]), five_years=v310.metrics(full, [0, 1, 2, 3, 4]),
                        full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    log(f"FINAL {ch} dev4 {out['final']['dev4']} | last year {out['final']['last_year']} | 5y {out['final']['five_years']} | full {out['final']['full']}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v324_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
