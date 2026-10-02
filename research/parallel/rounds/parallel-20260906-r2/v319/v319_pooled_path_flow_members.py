"""v319: two more POOLED-EXPERIENCE members for the MANUAL book (registry v319).

v316 / v317 (audit v316 PASS): training on the 5 majors + 72 survivorship-free U2020 alts raises the book IC (TV member PT: 2023 0.169 vs 0.078 control)
and the MANUAL book (pullback M2 = (2A + 2PT + D)/5: 5y 3.16). Two pre-registered extensions, both annual + quarterly fits exactly as v317 (v94
horizons 18 / 42 / 84, HGB v94 hyper-parameters seed 0, cutoff = (quarter) start - (84 + 60) bars, labels ending before the cutoff, majors predicted):
  PP  PATH-label TV member: features = PT's (v92 + 17 TV + BTC cross); every return target y18 / y42 / y84 replaced by the v287 first-touch label
      (entry next open, barrier vol42 x sqrt(h), +1 / -1 first touch, stop-first, else clipped return / barrier; same window) - aimed at the
      win rate of the SL / TP trade structure.
  PF  FLOW-augmented pooled member: PT features + the six O1 order-level flow features (fl_*; majors only, NaN for every alt row) - the alts teach the
      price / TV part, the majors the flow part.
ROWS (MANUAL, pullback rules 0.75 sigma_4h / 3 bars, cap 2, target 0.25; base = v317 M2):
  X0 base (2A + 2PT + D)/5 | X1 (2A + 2PT + D + PP)/6 | X2 (2PF + 2PT + D)/5 | X3 (2PF + 2PT + D + PP)/6
CHOICE (fixed before running; dev only): at fold k = 2, 3 the row with the highest v310 robust fitness on years [:k] among X0..X3 is scored on year k;
TRANSFER if it beats X0 there in both folds (a fold that picks X0 counts as no gain). Final choice on dev4; the most recent year computed once for it
(contaminated by design: the family was shaped with knowledge of the most recent year - prospective log = clean evidence).

  python research/parallel/rounds/parallel-20260906-r2/v319/v319_pooled_path_flow_members.py
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


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v317 = _load("v317_p", RD / "v317/v317_pooled_tv_member.py")
v287 = _load("v287_p", RD / "v287/v287_path_label_member.py")


def main():
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    need = [n for n in ("PP", "PPq", "PF", "PFq") if not (C / f"member_{n}_pooled.parquet").exists()]
    if need:
        panel, feats, v92, v94 = v317.build_panel(log)
        # OHLC per symbol for the path labels (majors: the extended loader; alts: the v316 4h cache)
        v144 = _load("v144_p", RD / "v144/v144_deploy_v3.py")
        ext = v144.v115.v114.v113
        ext.cb_bars = v144.v115.v114.cb_bars_ext
        ext.v92.load_asset = ext.load_asset_ext
        ohlc = {s: ext.load_asset_ext(s)[0][["open_time", "high", "low"]].drop_duplicates("open_time") for s in v92.SYMS}
        for s in panel.sym.unique():
            if s not in ohlc:
                ohlc[s] = v317.v316.alt_bars(s)[["open_time", "high", "low"]].drop_duplicates("open_time")
        pp = v287.relabel(panel, [(f"y{h}", h) for h in v94.HORIZONS], ohlc)
        log(f"path labels: {float(pp['y42'].notna().mean()):.3f} of rows labelled; mean |y42| {float(pp['y42'].abs().mean()):.3f}")
        v240 = _load("v240_p", RD / "v240/v240_order_level_flow.py")
        xf = v240.feature_frame(ext.v92.load_asset, False)
        flow = [c for c in xf.columns if c.startswith("fl_")]
        pf = panel.merge(xf[["t", "sym"] + flow], on=["t", "sym"], how="left")
        log(f"flow features {flow}; alt rows with flow {float(pf.loc[~pf.sym.isin(v92.SYMS), flow[0]].notna().mean()):.3f}")
        for n, (pan, fs, q) in {"PP": (pp, feats, False), "PPq": (pp, feats, True), "PF": (pf, feats + flow, False), "PFq": (pf, feats + flow, True)}.items():
            if n not in need:
                continue
            W, ic = v317.fit_books(pan, fs, v92, v94, True, q, log, n)
            W.to_parquet(C / f"member_{n}_pooled.parquet")
            log(f"member {n} IC dev (vs its own label) {ic}")
    v310 = _load("v310_p", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_p", RD / "v315/v315_manual_pullback_entry.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols = W0["idx"], W0["cols"]
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    PT = (rd("member_PT_pooledtv.parquet") + rd("member_PTq_pooledtv.parquet")) / 2
    PP = (rd("member_PP_pooled.parquet") + rd("member_PPq_pooled.parquet")) / 2
    PF = (rd("member_PF_pooled.parquet") + rd("member_PFq_pooled.parquet")) / 2
    A, D = W0["grp"]["wA"].copy(), W0["grp"]["wD"].copy()
    mixes = {"X0": (2 * A + 2 * PT + D) / 5, "X1": (2 * A + 2 * PT + D + PP) / 6, "X2": (2 * PF + 2 * PT + D) / 5, "X3": (2 * PF + 2 * PT + D + PP) / 6}
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
    assert abs(v310.metrics(res["X0"], [0, 1, 2, 3])["R"] - 3.011) < 0.003
    out = {"version": "v319", "rows": {k: dict(dev4=v310.metrics(r, [0, 1, 2, 3]), F=round(v310.fitness(r, [0, 1, 2, 3]), 4)) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        log(f"{k} {v}")
    deltas = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v310.fitness(res[x], ys))
        f_ch, f_ref = v310.fitness(res[ch], [k]), v310.fitness(res["X0"], [k])
        out["folds"][k] = dict(choice=ch, test=v310.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_X0=round(f_ref, 4))
        deltas.append(f_ch - f_ref)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} vs X0 {f_ref:.4f}")
    out["transfer"] = dict(deltas=[round(x, 4) for x in deltas], holds=bool(all(x > 0 for x in deltas)))
    log(f"TRANSFER {out['transfer']}")
    ch = max(res, key=lambda x: v310.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v310.metrics(res[ch], [0, 1, 2, 3]), last_year=v310.metrics(full, [4]), five_years=v310.metrics(full, [0, 1, 2, 3, 4]),
                        full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    log(f"FINAL {ch} dev4 {out['final']['dev4']} | last year {out['final']['last_year']} | 5y {out['final']['five_years']} | full {out['final']['full']}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v319_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
