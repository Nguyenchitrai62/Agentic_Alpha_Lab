"""oc_etfflow: 4-phase engine judgement of the ETF-outflow throttle (PLAN-pinned).

Mirrors research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py
exactly, except the gate comes from research/tournament/oc_etfflow/panel.parquet
(T1_on = S5 < trailing p5; T2_on = S5 < trailing p10; global across syms) and a
constant exposure control C0 (book longs x0.95 every bar).

Per (T,sym) long-weight multiplier on STANDARD rows, after the bear filter,
before the shifted-clock forward fill. G2 config: rule inv, k 1.0, kd 1.7,
bear True, G 2.0. G2 itself is loaded from the v421 cache (reproduced to the
digit before any overlay). Gate costs / fills / funding = gate model in PLAN.

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_etfflow --min-free-gb 2.0 -- .venv/Scripts/python.exe research/tournament/oc_etfflow/run_etf_throttle.py
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
RD = HERE.parents[1] / "parallel/rounds/parallel-20260906-r2"
ROOT = HERE.parents[2]
TABLES = RD / "v376" / "tables_hidden"
RUNS = {"R2B1D17BFG2": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0),
        "G2_T1": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="T1"),
        "G2_T2": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="T2"),
        "G2_C0": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="C0")}
CACHED = {"R2B1D17BFG2": ("research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl", "R2B1D17BFG2")}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_etf", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_etf", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podetf_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histetf_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_etf_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwetf_{shift}", ROOT / "scripts/forward_v205.py")
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
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    books = std_books.reindex(idx, method="ffill").fillna(0.0)
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    # ETF gate (global): map panel T1_on/T2_on onto sb.index (standard rows).
    pan = pd.read_parquet(HERE / "panel.parquet", columns=["T", "T1_on", "T2_on"])
    pan["T"] = pd.to_datetime(pan["T"], utc=True)
    t1set = set(pan["T"][pan["T1_on"].to_numpy(bool)].tolist())
    t2set = set(pan["T"][pan["T2_on"].to_numpy(bool)].tolist())
    g1 = pd.DataFrame(False, index=sb.index, columns=sb.columns)
    g2 = pd.DataFrame(False, index=sb.index, columns=sb.columns)
    ix = sb.index
    m1 = np.array([t in t1set for t in ix])
    m2 = np.array([t in t2set for t in ix])
    g1.iloc[m1, :] = True
    g2.iloc[m2, :] = True
    # Rows before 2021-09-24 never gated (none in sb.index anyway; assert).
    assert bool((ix >= pd.Timestamp("2021-09-24", tz="UTC")).all())
    sb_t1 = sb.where(~(g1 & (sb > 0)), sb * 0.5)
    sb_t2 = sb.where(~(g2 & (sb > 0)), sb * 0.5)
    sb_c0 = sb.where(~(sb > 0), sb * 0.95)
    print(shift, "T1 long rows", int((g1 & (sb > 0)).to_numpy().sum()),
          "T2 long rows", int((g2 & (sb > 0)).to_numpy().sum()), flush=True)
    books_t1 = sb_t1.reindex(idx, method="ffill").fillna(0.0)
    books_t2 = sb_t2.reindex(idx, method="ffill").fillna(0.0)
    books_c0 = sb_c0.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    out = {}
    for name, cfg in RUNS.items():
        if name in CACHED:
            continue
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size, rule = kw["sleeve_fill_size"], cfg["rule"]
        kd = cfg.get("kd", 1.0)
        ev, stops, ptr = [], {}, [0]
        cool = cfg.get("cool", False)
        COOL = pd.Timedelta(hours=24)

        def cooled(i, a):
            while ptr[0] < len(ev):
                e = ev[ptr[0]]
                ptr[0] += 1
                if e["kind"] == "rung_sl":
                    stops.setdefault(e["symbol"], []).append(e["t"])
            B = idx[i] + pd.Timedelta(hours=4)
            return any(s_ < B <= s_ + COOL for s_ in stops.get(cols[a], [])[-20:])

        def corr_size(i, a, r, f, base_size=base_size, rule=rule, kd=kd, cool=cool):
            if cool and cooled(i, a):
                return 0.0
            m = f - 1
            n = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                    continue
                n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            mult = 1.0 / (1 + n) if rule == "inv" else (0.5 if n >= 2 else 1.0)
            return mult * kd * base_size(i, a, r, f)
        kw["sleeve_fill_size"] = corr_size
        k = cfg["k"]
        kw["risk_mult"] = lambda i, e, k=k: k
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * k * kd
        if "G" in cfg:
            kw["sleeve_gross_cap"] = cfg["G"]
        if "xrp" in cfg:
            base_sl = kw.get("m_sleeve_sl", 4.0)
            xa = cols.index("XRPUSDT")
            kw["sleeve_sl_coin"] = lambda i, a, xa=xa, x=cfg["xrp"], b=base_sl: x if a == xa else b
        if "bm" in cfg:
            trade["book_mult"] = cfg["bm"]
        gate = cfg.get("gate")
        bsel = {"T1": books_t1, "T2": books_t2, "C0": books_c0}[gate]
        eu.simulate(bsel, opens, prep, trade=trade, win_start=5, events=ev, **kw)
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


def main():
    cache = HERE / "tmp" / "etf_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        for row, (pth, key) in CACHED.items():
            cr = pickle.loads((ROOT / pth).read_bytes())
            for s in range(4):
                runs[s][row] = cr[s][key]
        cache.write_bytes(pickle.dumps(runs))
    # G2 reproduction check (to the digit vs v421_result.json).
    exp = json.loads((RD / "v421" / "v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    got = stats(runs, "R2B1D17BFG2", list(range(5)))
    assert [a for a, _ in got["years"]] == [r for r, _ in exp["years"]], (got, exp)
    assert [d for _, d in got["years"]] == [d for _, d in exp["years"]], (got, exp)
    assert got["R"] == exp["R"] and got["W"] == exp["W"] and got["DD"] == exp["DD"], (got, exp)
    print("G2 reproduction OK:", got, flush=True)
    out = {"version": "oc_etfflow", "rows": {r: stats(runs, r, list(range(5))) for r in RUNS}}
    for r, m in out["rows"].items():
        print(r, m, flush=True)
    g1 = Y1 + pd.Timedelta(hours=12)
    for r in RUNS:
        e, mn = v388.mix(runs, r, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        out["rows"][r]["full_path_dd"] = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        print(r, "full-path DD", out["rows"][r]["full_path_dd"], flush=True)
    assert out["rows"]["R2B1D17BFG2"]["full_path_dd"] == exp["full_path_dd"], out["rows"]["R2B1D17BFG2"]
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "tmp" / "etf_engine.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
