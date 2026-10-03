"""v336: MANUAL product - BREADTH: the pooled TV book traded on the 5 majors + the 10 largest Dec-2020 alts (registry v336; RESEARCH ONLY -
trading coins other than the majors needs the user's explicit OK before any deployment).

Why: the fundamental law IR ~ IC x sqrt(breadth): with IC ~0.12 on 5 majors the MANUAL book sits at IR ~2 (5y ~3.2 %/month at DD ~20); the floor
(5 %/month, DD < 20) needs IR ~3.5 - either a doubled IC (100+ versions found no such information) or more independent bets. The pooled member PT
is trained on 77 coins and can forecast any of them.
UNIVERSE (causal, fixed at 2020-12): majors + the top-10 non-major USDT perps by Dec-2020 quote volume (um_universe_20260930/volume_2020_12.csv):
LTC, LINK, BCH, YFI, SUSHI, XLM, ADA, EOS (delisted 2025-05: no position after its last bar), DOT, UNI. 1m data from the kept alt stores.
MEMBER PTX = v317 PT exactly (v92 + 17 TV + BTC cross, v94 horizons, pooled 77-coin training, annual + quarterly fits, cutoff = (quarter) start -
(84 + 60) bars, labels ending before the cutoff) with predictions for the 15 traded coins; books = v94.weights_ls(shorts=True) over the 15.
ROWS (MANUAL rules = M2: pullback entry 0.75 sigma_4h / 3 bars, G2 grid trader, SL 4 / TP 8 sigma_d, target 0.25, cap 2, engine_user costs):
  M2   (2A + 2PT + D)/5 on the majors (reference, dev4 3.011)
  B0   PT alone on the majors (control for B1)
  B1   PTX alone on the 15 coins
  M2X  majors: the M2 mix; alts: PTX
CHOICE: dev folds k = 2, 3 with the v310 robust MANUAL fitness on years [:k]; TRANSFER if a 15-coin row is chosen and beats M2 on the unseen dev year in
both folds. Final on dev4; the most recent year computed once for the final choice. Reported per row: share of PnL and trades from the alts.

  python research/parallel/rounds/parallel-20260906-r2/v336/v336_manual_breadth.py
"""
from __future__ import annotations

import glob
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
ALTS = ("LTCUSDT", "LINKUSDT", "BCHUSDT", "YFIUSDT", "SUSHIUSDT", "XLMUSDT", "ADAUSDT", "EOSUSDT", "DOTUSDT", "UNIUSDT")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v317 = _load("v317_br", RD / "v317/v317_pooled_tv_member.py")


def fit_books_ext(panel, feats, v92, v94, quarterly, syms, log, tag):
    """= v317.fit_books (pooled) with predictions for `syms`."""
    pred_mask = panel.sym.isin(syms)
    oos = []
    for a in v92.ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        starts = [a0 + pd.Timedelta(days=91 * q) for q in range(4)] if quarterly else [a0]
        for qi, q0 in enumerate(starts):
            q1 = starts[qi + 1] if qi + 1 < len(starts) else a0 + pd.Timedelta(days=365)
            cutoff = q0 - pd.Timedelta(hours=4 * v94.EMBARGO_BARS)
            te = panel[pred_mask & (panel.t >= q0) & (panel.t < q1)].copy()
            preds = []
            for h in v94.HORIZONS:
                tr = panel[(panel.t < cutoff) & panel[f"y{h}"].notna()]
                tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
                m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0,
                                                  random_state=0)
                m.fit(tr[feats], tr[f"y{h}"])
                preds.append(m.predict(te[feats]))
            te["pred"] = np.mean(preds, axis=0)
            oos.append(te)
        log(f"{tag} anchor {a} done")
    return v94.weights_ls(pd.concat(oos, ignore_index=True), True)


def alt_cube(G, cols, base_cube):
    """v172.cube_ohlc for the majors + the alts' 1m stores (same layout)."""
    majors = [c for c in cols if not c in ALTS]
    A0 = base_cube(G, majors)
    starts = G + pd.Timedelta(hours=4)
    n = len(G)
    A = {k: np.full((n, 240, len(cols)), np.nan, dtype=np.float32) for k in ("open", "high", "low", "close")}
    for j, s in enumerate(cols):
        if s in majors:
            for k in A:
                A[k][:, :, j] = A0[k][:, :, majors.index(s)]
            continue
        files = sorted(glob.glob(f"data/raw/alts2020_intraday_20260930/{s}_1m_*.parquet")) or sorted(glob.glob(f"data/raw/alts_intraday_20260926/{s}_1m_*.parquet"))
        m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in files])
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        m = m.drop_duplicates("open_time")
        T = m["open_time"].dt.floor("4h")
        pos = pd.Series(np.arange(n), index=starts)
        i = pos.reindex(T).to_numpy()
        ok = ~np.isnan(i)
        off = ((m["open_time"] - T).dt.total_seconds() // 60).astype(int).to_numpy()
        for k in A:
            A[k][i[ok].astype(int), off[ok], j] = m[k].to_numpy(float)[ok]
        for k in A:
            X = A[k][:, :, j]
            for mm in range(1, 240):
                miss = np.isnan(X[:, mm])
                X[:, mm][miss] = X[:, mm - 1][miss]
    return A


def main():
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    v310 = _load("v310_br", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_br", RD / "v315/v315_manual_pullback_entry.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols5 = W0["idx"], list(W0["cols"])
    cols15 = cols5 + list(ALTS)
    if not all((C / f"member_{n}_ext15.parquet").exists() for n in ("PTX", "PTXq")):
        panel, feats, v92, v94 = v317.build_panel(log)
        for n, q in (("PTX", False), ("PTXq", True)):
            W = fit_books_ext(panel, feats, v92, v94, q, cols15, log, n)
            W.to_parquet(C / f"member_{n}_ext15.parquet")
    rd = lambda f, cs: pd.read_parquet(C / f).reindex(idx).ffill().fillna(0.0).reindex(columns=cs).fillna(0.0).to_numpy(float)
    PT5 = (rd("member_PT_pooledtv.parquet", cols5) + rd("member_PTq_pooledtv.parquet", cols5)) / 2
    PTX = (rd("member_PTX_ext15.parquet", cols15) + rd("member_PTXq_ext15.parquet", cols15)) / 2
    A5, D5 = W0["grp"]["wA"].copy(), W0["grp"]["wD"].copy()
    M2_5 = (2 * A5 + 2 * PT5 + D5) / 5
    # extended opens / prep (15 coins); no position where an alt has no price (before listing / after delisting)
    opens5 = W0["opens"]
    alt_open = {s: pd.read_parquet(f"artifacts/research/engine_real/v316_alt4h/{s}.parquet").assign(
        t=lambda d: pd.to_datetime(d["open_time"], utc=True)).set_index("t")["open"] for s in ALTS}
    opens15 = pd.concat([opens5[cols5], pd.DataFrame(alt_open).reindex(opens5.index)], axis=1)[cols15]
    v172 = W0["eu"].v172
    base_cube = v172.cube_ohlc
    v172.cube_ohlc = lambda G, cs: alt_cube(G, cs, base_cube)
    books_ref = pd.DataFrame(0.0, index=idx, columns=cols15)
    prep15 = W0["eu"].prepare(books_ref, opens15)
    v172.cube_ohlc = base_cube
    live = opens15.reindex(idx).notna().to_numpy() & opens15.reindex(idx).shift(-2).notna().to_numpy()
    pad = lambda X5: np.concatenate([X5, np.zeros((len(idx), len(ALTS)))], axis=1)
    mixes = {"M2": ("5", M2_5), "B0": ("5", PT5), "B1": ("15", PTX * live), "M2X": ("15", np.where(np.arange(15) < 5, pad(M2_5), PTX) * live)}
    keep = dict(opens=W0["opens"], prep=W0["prep"], cols=W0["cols"])
    grp_keep = {n: v.copy() for n, v in W0["grp"].items()}
    base_p9 = v310._policy9

    def run(k, full=False):
        u, X = mixes[k]
        if u == "15":
            W0.update(opens=opens15, prep=prep15, cols=cols15)
        for n in W0["grp"]:  # every member group must have the run's width (the zero-weight groups included)
            W0["grp"][n] = np.zeros_like(X)
        W0["grp"]["wA"] = W0["grp"]["wB"] = W0["grp"]["wD"] = X
        v310._policy9 = v315.with_entry(0.75)
        v315.BASE_P9 = base_p9
        try:
            return v310.run_genome(v310.encode(dict(target=0.25, cap=2.0, n_valid=3)), full)
        finally:
            v310._policy9 = base_p9
            W0.update(**keep)
            W0["grp"].update({n: v.copy() for n, v in grp_keep.items()})

    res = {k: run(k) for k in mixes}
    assert abs(v310.metrics(res["M2"], [0, 1, 2, 3])["R"] - 3.011) < 0.003
    out = {"version": "v336", "universe": cols15, "rows": {k: dict(dev4=v310.metrics(r, [0, 1, 2, 3]), F=round(v310.fitness(r, [0, 1, 2, 3]), 4),
                                                                    years=[v310.metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        log(f"{k} dev4 {v['dev4']} F {v['F']}")
    gains = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v310.fitness(res[x], ys))
        f_ch, f0 = v310.fitness(res[ch], [k]), v310.fitness(res["M2"], [k])
        out["folds"][k] = dict(choice=ch, test=v310.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_M2=round(f0, 4))
        gains.append(ch in ("B1", "M2X") and f_ch > f0)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} vs M2 {f0:.4f}")
    out["transfer"] = dict(holds=bool(all(gains)))
    log(f"TRANSFER {out['transfer']}")
    ch = max(res, key=lambda x: v310.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v310.metrics(res[ch], [0, 1, 2, 3]), last_year=v310.metrics(full, [4]), five_years=v310.metrics(full, [0, 1, 2, 3, 4]),
                        full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")},
                        deployment_note="research only: trading the 10 alts needs the user's explicit OK")
    log(f"FINAL {ch} dev4 {out['final']['dev4']} | last year {out['final']['last_year']} | 5y {out['final']['five_years']} | full {out['final']['full']}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v336_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
