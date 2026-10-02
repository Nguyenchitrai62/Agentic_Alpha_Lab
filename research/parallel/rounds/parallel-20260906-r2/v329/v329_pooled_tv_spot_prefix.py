"""v329: pooled TV member with the alts' SPOT history prefix (PT2) - more pooled experience for the early anchors (registry v329).

v317 PT (5 majors + 72 U2020 alts, training only) lifted the MANUAL book (M2), but the alts' perp histories start mostly in 2019-2020, so the first
anchors (2021-09, 2022-09) learn from few alt rows (v316: 197k pooled rows at the first anchor vs 680k at the fourth). The majors already use spot /
Bitstamp / Coinbase prefixes before their perps (v113). PT2 = PT with each alt's Binance SPOT 4h bars (data/raw/alt_spot_4h_20261003, 71 of 72 alts,
public REST; fetched up to the alt's first perp bar) prepended to its perp history - training rows only, the traded universe is unchanged.
Everything else = v317 PT exactly (v92 + 17 TV + BTC cross features, v94 horizons, annual + quarterly fits, cutoff = anchor - (84 + 60) bars,
labels ending before the cutoff, majors predicted, v94.weights_ls books); funding features are NaN on the spot prefix rows (as for the majors' prefixes).
ROWS (MANUAL M2 setting: pullback 0.75 sigma_4h / 3 bars, target 0.25, cap 2): S0 M2 = (2A + 2PT + D)/5 | S1 (2A + 2PT2 + D)/5.
CHOICE: dev folds k = 2, 3 with the v310 robust MANUAL fitness on years [:k]; TRANSFER if S1 is chosen and beats S0 on the unseen year in both folds.
Final on dev4; the most recent year once (M2 was shaped with knowledge of it - contaminated; prospective log = clean evidence). IC per dev year reported.

  python research/parallel/rounds/parallel-20260906-r2/v329/v329_pooled_tv_spot_prefix.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
C = Path("artifacts/research/engine_real")
SPOT = Path("data/raw/alt_spot_4h_20261003")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v317 = _load("v317_sp", RD / "v317/v317_pooled_tv_member.py")
_alt_bars = v317.v316.alt_bars


def alt_bars_with_prefix(sym):
    b = _alt_bars(sym)
    f = SPOT / f"{sym}_spot_4h.parquet"
    if not f.exists():
        return b
    s = pd.read_parquet(f)
    s = s[s["open_time"] < b["open_time"].min()][[c for c in b.columns if c in s.columns]]
    return pd.concat([s, b], ignore_index=True).sort_values("open_time").reset_index(drop=True)


def main():
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    out = {"version": "v329", "ic_dev": {}}
    if not all((C / f"member_{n}_pooledtv_spot.parquet").exists() for n in ("PT2", "PT2q")):
        v317.v316.alt_bars = alt_bars_with_prefix
        panel, feats, v92, v94 = v317.build_panel(log)
        alt = ~panel.sym.isin(v92.SYMS)
        log(f"alt rows {int(alt.sum())} (v317: 916693); first alt row {panel.loc[alt, 't'].min()}")
        for n, q in (("PT2", False), ("PT2q", True)):
            W, ic = v317.fit_books(panel, feats, v92, v94, True, q, log, n)
            W.to_parquet(C / f"member_{n}_pooledtv_spot.parquet")
            out["ic_dev"][n] = ic
            log(f"member {n} IC dev {ic}")
    v310 = _load("v310_sp", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_sp", RD / "v315/v315_manual_pullback_entry.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols = W0["idx"], W0["cols"]
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    PT = (rd("member_PT_pooledtv.parquet") + rd("member_PTq_pooledtv.parquet")) / 2
    PT2 = (rd("member_PT2_pooledtv_spot.parquet") + rd("member_PT2q_pooledtv_spot.parquet")) / 2
    A, D = W0["grp"]["wA"].copy(), W0["grp"]["wD"].copy()
    mixes = {"S0": (2 * A + 2 * PT + D) / 5, "S1": (2 * A + 2 * PT2 + D) / 5}
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
    assert abs(v310.metrics(res["S0"], [0, 1, 2, 3])["R"] - 3.011) < 0.003
    out["rows"] = {k: dict(dev4=v310.metrics(r, [0, 1, 2, 3]), F=round(v310.fitness(r, [0, 1, 2, 3]), 4), years=[v310.metrics(r, [y]) for y in range(4)])
                   for k, r in res.items()}
    for k, v in out["rows"].items():
        log(f"{k} dev4 {v['dev4']} F {v['F']}")
    gains, out["folds"] = [], {}
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v310.fitness(res[x], ys))
        f_ch, f0 = v310.fitness(res[ch], [k]), v310.fitness(res["S0"], [k])
        out["folds"][k] = dict(choice=ch, test=v310.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_S0=round(f0, 4))
        gains.append(ch == "S1" and f_ch > f0)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} vs S0 {f0:.4f}")
    out["transfer"] = dict(holds=bool(all(gains)))
    log(f"TRANSFER {out['transfer']}")
    ch = max(res, key=lambda x: v310.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v310.metrics(res[ch], [0, 1, 2, 3]), last_year=v310.metrics(full, [4]), five_years=v310.metrics(full, [0, 1, 2, 3, 4]),
                        full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    log(f"FINAL {ch} dev4 {out['final']['dev4']} | last year {out['final']['last_year']} | 5y {out['final']['five_years']} | full {out['final']['full']}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v329_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
