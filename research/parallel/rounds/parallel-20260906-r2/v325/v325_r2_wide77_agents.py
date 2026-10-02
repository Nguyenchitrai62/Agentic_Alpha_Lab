"""v325: BOT product - R2 with dip agents trained on the WHOLE Dec-2020 perp market (77 coins) instead of 35 (registry v325).

R2 (v321, walk-forward BOT pipeline) uses dip size / take-profit agents fitted on pooled fills of all seven rung depths of 35 coins (5 majors + the
top-30 U2020 alts). v299 found that the 77-coin pool (every USDT perp listed >= 28 days in Dec-2020, delisted included; training only) raises
the dev mean of the G2 agents but not the weak year; v325 tests it once on the R2 configuration, the only change being the experience pool:
  ROW A  R2 (35-coin fit "U", v306 gene tables)
  ROW B  R2 with fit "U77": the same v296 HGB agents (cross-fitted halves, fills that exited before anchor - 7 days, state at the bar open, S1 size
         and X4 take-profit rules) trained on the fills of all seven rung depths of the 5 majors + 72 U2020_all alts.
CHOICE (fixed before running): dev folds k = 1, 2, 3 (as v306) with the v306 BOT fitness on years [:k]; TRANSFER if B is chosen and beats A on the
unseen dev year in at least 2 of the 3 folds (a fold that chooses A counts as no gain). Final choice on dev4; the most recent year computed once
for it (A's most-recent-year number 5.655 is already known from v321).

  python research/parallel/rounds/parallel-20260906-r2/v325/v325_r2_wide77_agents.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
C = Path("artifacts/research/engine_real")
U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_u77(log):
    """(size, tp) arrays [bar, asset, U-depth] of the 77-coin fit, bar-open state (v306_gene_tables recipe, universe = U2020_all)."""
    p = C / "v325_u77_tables.npz"
    if p.exists():
        z = np.load(p)
        return z["size"], z["tp"]
    v294 = _load("v294_u77", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
    v296 = _load("v296_u77", RD / "v296/v296_joint_dip_agent.py")
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py"); eu = v221.eu
    v = pd.read_csv("data/raw/um_universe_20260930/volume_2020_12.csv")
    alts = tuple(v[(v.days >= 28) & ~v.symbol.isin(v293.MAJORS)].sort_values("quote_volume_usd", ascending=False).symbol)
    v293.RUNGS = U
    assets = {s: v293.Asset(s) for s in v293.MAJORS}
    btc = assets["BTCUSDT"]
    parts = []
    for s in v293.MAJORS + alts:
        try:
            A = assets[s] if s in assets else v293.Asset(s)
        except Exception as e:  # noqa: BLE001
            log(f"skip {s}: {e}")
            continue
        d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc)
        if len(d):
            parts.append(d.assign(sym=s))
        del A
    allf = pd.concat(parts, ignore_index=True)
    log(f"U77 fills {len(allf)} from {allf.sym.nunique()} coins")
    X = allf[[f"x{q}" for q in range(7)]].to_numpy(float)
    Y = np.clip(allf[[f"y{mu}" for mu in v293.ACTIONS]].to_numpy(float), -0.10, 0.08)
    y1 = Y[:, v293.ACTIONS.index(1.0)]
    half = (allf["j"] % 2).to_numpy()
    books154, _ = eu.er.v154_books()
    idx, cols = books154.index, list(books154.columns)
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    size = np.ones((len(idx), len(cols), len(U)))
    tp = np.ones((len(idx), len(cols), len(U)))
    for jj, a0 in enumerate(anchors):
        keep = np.asarray(allf.t_exit < a0 - v293.EMBARGO)
        mu = float(y1[keep].mean())
        sm = [v296.hgb(10 * jj + h).fit(X[keep & (half == h)], y1[keep & (half == h)]) for h in (0, 1)]
        tm = [[v296.hgb(10 * jj + h + 3 * c).fit(X[keep & (half == h)], Y[keep & (half == h), c]) for c in range(3)] for h in (0, 1)]
        a1 = anchors[jj + 1] if jj + 1 < len(anchors) else a0 + pd.Timedelta(days=366)
        for a, s in enumerate(cols):
            A = assets[s]
            js = [j for j, T in enumerate(A.t0) if a0 <= T < a1 and np.isfinite(A.sig[j])]
            if not js:
                continue
            ii = idx.get_indexer(pd.DatetimeIndex([A.t0[j] for j in js]) - pd.Timedelta(hours=4))
            base = np.array([[A.sp30(j * 240), 0.0, A.volreg[j], A.trend[j], btc.sp30(j * 240),
                              np.log(A.C[j * 240] / A.hmax24[j * 240]) / A.sig[j] if A.hmax24[j * 240] > 0 else np.nan, A.t0[j].hour] for j in js])
            for q, k in enumerate(U):
                x = base.copy()
                x[:, 1] = k
                pa, pb = sm[0].predict(x), sm[1].predict(x)
                sz = np.where((pa > 2 * mu) & (pb > 2 * mu), 1.5, np.where((pa < 0) & (pb < 0), 0.5, 1.0))
                qa = np.stack([m.predict(x) for m in tm[0]], 1); qb = np.stack([m.predict(x) for m in tm[1]], 1)
                ba, bb = qa.argmax(1), qb.argmax(1)
                n = np.arange(len(x))
                ok = (ba == bb) & (ba != 1) & (qa[n, ba] - qa[:, 1] > 0.0010) & (qb[n, bb] - qb[:, 1] > 0.0010)
                t_ = np.where(ok, np.array((0.5, 1.0, 1.5))[ba], 1.0)
                good = ii >= 0
                size[ii[good], a, q], tp[ii[good], a, q] = sz[good], t_[good]
        log(f"U77 anchor {jj} rows {int(keep.sum())} mu {mu:.5f}")
    np.savez(p, size=size, tp=tp)
    return size, tp


def main():
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    size77, tp77 = build_u77(log)
    v306 = _load("v306_u77", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    g = v306.encode(v306.SEEDS["R2"])
    tables0 = v306._tables

    def run(row, full=False):
        if row == "B":
            v306._tables = lambda d: (size77, tp77)
        try:
            return v306.run_genome(g, full)
        finally:
            v306._tables = tables0

    res = {"A": run("A"), "B": run("B")}
    assert abs(v306.metrics(res["A"], [0, 1, 2, 3])["R"] - 7.079) < 0.003
    out = {"version": "v325", "rows": {k: dict(dev4=v306.metrics(r, [0, 1, 2, 3]), F=round(v306.fitness(r, [0, 1, 2, 3]), 4),
                                               years=[v306.metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        log(f"{k} dev4 {v['dev4']} F {v['F']}")
    gains = 0
    for k in (1, 2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v306.fitness(res[x], ys))
        f_ch, f_a = v306.fitness(res[ch], [k]), v306.fitness(res["A"], [k])
        out["folds"][k] = dict(choice=ch, test=v306.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_A=round(f_a, 4))
        gains += int(ch == "B" and f_ch > f_a)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} vs A {f_a:.4f}")
    out["transfer"] = dict(gain_folds=gains, holds=bool(gains >= 2))
    log(f"TRANSFER {out['transfer']}")
    ch = max(res, key=lambda x: v306.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v306.metrics(res[ch], [0, 1, 2, 3]), last_year=v306.metrics(full, [4]), five_years=v306.metrics(full, [0, 1, 2, 3, 4]),
                        full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    log(f"FINAL {ch} dev4 {out['final']['dev4']} | last year {out['final']['last_year']} | 5y {out['final']['five_years']} | full {out['final']['full']}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v325_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
