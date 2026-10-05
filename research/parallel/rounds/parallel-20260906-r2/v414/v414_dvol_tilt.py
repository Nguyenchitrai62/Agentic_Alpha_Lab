"""v414: implied-volatility (DVOL) tilt of the correlation-aware dip sizes (registry v414).

Why: research/tournament/oc_dvol (OpenCode, 2026-10-05): the BTC / ETH Deribit DVOL level vs its trailing 90 days (z90) and the DVOL - realised
vol premium have a POSITIVE rank IC with dip-rung outcomes in 5 of 5 years and a leave-one-year-out tercile spread of the same sign in 4 of 5
(dips pay more when implied fear is high) - the first new information source to pass a pre-registered consistency rule in this program.
Rule (no fitted parameters): z90 = (BTC DVOL hourly close at the last hour strictly before the holding bar start T - mean of the trailing 2160
hourly closes) / their std (min 720), from data/raw/deribit_dvol_20261005 (research/tournament/oc_dvol/dvol_hourly.parquet). BTC DVOL is the
market fear gauge for every major.
Rows (fixed before running): R2B1D17BF (reference = v411 cache), R2B1D17BFV1 (dip size x1.3 if z90 > +0.5, x0.7 if z90 < -0.5, else 1),
R2B1D17BFV2 (x clip(1 + 0.3 z90, 0.6, 1.4)); z90 NaN -> 1. The multiplier applies on top of the B1 / dip x1.7 sizes; budget unchanged
(0.26 x 1.7). Pool(1). Harness, reset metric, full-path DD, selection and folds exactly as v411. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v414/v414_dvol_tilt.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import pickle
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
ROOT = RD.parents[3]
TABLES = RD / "v376" / "tables_hidden"
RUNS = {"R2B1D17BF": dict(rule="inv", k=1.0, kd=1.7, bear=True), "R2B1D17BFV1": dict(rule="inv", k=1.0, kd=1.7, bear=True, dv="step"), "R2B1D17BFV2": dict(rule="inv", k=1.0, kd=1.7, bear=True, dv="lin")}
REF = "R2B1D17BF"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_414", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_414", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod414_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist414_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_414_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw414_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _opens_std = eu.er.v154_books()
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    dv = pd.read_parquet(ROOT / "research/tournament/oc_dvol/dvol_hourly.parquet")
    dv = dv[dv.sym == "BTCDVOL"].set_index("t")["close"].sort_index()
    dv.index = pd.to_datetime(dv.index, utc=True)
    z = (dv - dv.rolling(2160, min_periods=720).mean()) / dv.rolling(2160, min_periods=720).std()
    T = idx + pd.Timedelta(hours=4)  # holding bar start; use the last hourly close strictly before T (hour starting at T - 2h closes at T - 1h)
    zT = z.reindex(T - pd.Timedelta(hours=2), method="ffill").to_numpy()
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    books = std_books.reindex(idx, method="ffill").fillna(0.0)
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    out = {}
    for name, cfg in RUNS.items():
        if name == REF:
            continue  # reference = v406 cached R2B1D16 runs (identical settings)
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size, rule = kw["sleeve_fill_size"], cfg["rule"]

        kd = cfg.get("kd", 1.0)

        dvm = cfg.get("dv")

        def corr_size(i, a, r, f, base_size=base_size, rule=rule, kd=kd, dvm=dvm):
            m = f - 1
            n = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                    continue
                n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            mult = 1.0 / (1 + n) if rule == "inv" else (0.5 if n >= 2 else 1.0)
            zz = zT[i]
            if dvm == "step":
                tilt = 1.3 if zz > 0.5 else (0.7 if zz < -0.5 else 1.0)
            elif dvm == "lin":
                tilt = float(np.clip(1 + 0.3 * zz, 0.6, 1.4)) if np.isfinite(zz) else 1.0
            else:
                tilt = 1.0
            if not np.isfinite(zz):
                tilt = 1.0
            return mult * kd * tilt * base_size(i, a, r, f)
        kw["sleeve_fill_size"] = corr_size
        k = cfg["k"]
        kw["risk_mult"] = lambda i, e, k=k: k
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * k * kd
        if "bm" in cfg:
            trade["book_mult"] = cfg["bm"]

        eu.simulate(books_bear if cfg.get("bear") else books, opens, prep, trade=trade, win_start=5, events=[], **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)], eq=(cap["eq"][lv] / base).tolist(), eq_min=(cap["eq_min"][lv] / base).tolist())
        print(shift, name, round(out[name]["eq"][-1], 3), flush=True)
    return shift, out


def stats(runs, row, ys):
    yy = [rm.year_reset(runs, row, y) for y in ys]
    geo = 100 * (np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / len(yy)) - 1)
    return dict(R=round(float(geo), 3), W=min(y["R"] for y in yy), DD=max(y["DD"] for y in yy), losing=sum(y["R"] < 0 for y in yy),
                years=[(y["R"], y["DD"]) for y in yy])


def rank_key(m):
    ok = m["DD"] <= 20 and m["losing"] == 0
    if ok:
        return (2, int(m["R"] >= 5), m["W"], m["R"])
    g = np.minimum([m["R"] / 8, m["W"] / 5, 15 / max(m["DD"], 1e-6)], 1.2)
    return (1 if m["losing"] == 0 else 0, 0, float(0.5 * g.min() + 0.5 * g.mean()), m["R"])


def main():
    cache = HERE / "v414_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
    else:
        with Pool(1) as pool:
            runs = dict(pool.map(worker, range(4)))
        ref = pickle.loads((RD / "v411" / "v411_runs.pkl").read_bytes())
        for s in range(4):
            runs[s][REF] = ref[s][REF]
        cache.write_bytes(pickle.dumps(runs))
    out = {"version": "v414", "rows": {r: stats(runs, r, list(range(5))) for r in RUNS}, "folds": {}}
    for r, m in out["rows"].items():
        print(r, m, flush=True)
    wins = 0
    for k in (2, 3, 4):
        ch = max(RUNS, key=lambda r: rank_key(stats(runs, r, list(range(k)))))
        t, t0 = rm.year_reset(runs, ch, k), rm.year_reset(runs, REF, k)
        good = ch != REF and t["R"] > t0["R"] and t["DD"] <= t0["DD"]
        wins += good
        out["folds"][k] = dict(choice=ch, test=t, ref=t0, good=good)
        print("FOLD", k, ch, t, "vs", t0, good, flush=True)
    out["transfer"] = wins >= 2
    out["final"] = max(RUNS, key=lambda r: rank_key(out["rows"][r]))
    g1 = Y1 + pd.Timedelta(hours=12)
    for r in RUNS:
        e, mn = v388.mix(runs, r, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        out["rows"][r]["full_path_dd"] = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        print(r, "full-path DD", out["rows"][r]["full_path_dd"], flush=True)
    print("TRANSFER", out["transfer"], "FINAL", out["final"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v414_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
