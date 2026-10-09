"""oc_shortmember engine: G2 replica books + 4-phase shifts + scoring.

Per PLAN.md (pre-registered). Modes:
  --build-books : LIGHT-ish. Build FULL/AS6/AS18 standard-grid books from
                  deployed caches + retrained AS members; check FULL vs
                  forward_v205.research_books_d2 (< 1e-12).
  --shift S     : HEAVY (via heavy_slot). One 4-phase-engine shift; runs all
                  three book variants sequentially on one minutes load,
                  exactly as v421 R2B1D17BFG2 (rule inv, k 1.0, kd 1.7,
                  bear, G 2.0, agents ON, win_start 5).
  --score       : LIGHT. Validate FULL vs v421_result to the digit, score all
                  rows (reset metric per year + full-path DD + trade stats)
                  into tmp/results_engine.json (internal scratch; REPORT.md
                  exposes the recent year only for the chosen row + G2).

Writes ONLY inside research/tournament/oc_shortmember/.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"
V421_RES = RD / "v421" / "v421_result.json"
TMP = HERE / "tmp"

SYMS_EXPECTED = {"BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"}
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR = pd.Timedelta(days=365)
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
VARIANTS = ("FULL", "AS6", "AS18")
MAKER, TAKER = 0.0002, 0.00055


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_standard_books(eu):
    books154, opens_std = eu.er.v154_books()
    cols = list(books154.columns)
    assert set(cols) == SYMS_EXPECTED, cols
    C = eu.er.CACHE
    M = {}
    M["A"] = pd.read_parquet(C / "member_A_O1_orders.parquet")[cols]
    M["Aq"] = pd.read_parquet(C / "member_Aq_O1_orders.parquet")[cols]
    M["B"] = pd.read_parquet(C / "member_B_tv.parquet")[cols]
    M["Bq"] = pd.read_parquet(C / "member_Bq_tv.parquet")[cols]
    M["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0)[cols]
    M["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet")[cols]
    for hnew in (6, 18):
        M[f"AS{hnew}"] = pd.read_parquet(HERE / f"member_AS{hnew}.parquet")[cols]
        M[f"AS{hnew}q"] = pd.read_parquet(HERE / f"member_AS{hnew}q.parquet")[cols]
    idx = M["A"].index
    for k in M:
        idx = idx.union(M[k].index)
    f = lambda X: X.reindex(idx).fillna(0.0)  # noqa: E731
    for k in M:
        M[k] = f(M[k])

    def d2(A, Aq):
        o1 = 0.25 * (A + M["B"] + Aq + M["Bq"])
        cb = 0.5 * (M["D"] + M["Dq"])
        return 0.8 * o1 + 0.2 * cb

    std_idx = books154.index
    books = {
        "FULL": d2(M["A"], M["Aq"]).reindex(std_idx).fillna(0.0)[cols],
        "AS6": d2(M["AS6"], M["AS6q"]).reindex(std_idx).fillna(0.0)[cols],
        "AS18": d2(M["AS18"], M["AS18q"]).reindex(std_idx).fillna(0.0)[cols],
    }
    btc = opens_std["BTCUSDT"].reindex(std_idx)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).fillna(False).to_numpy(bool)
    return books, bear, cols


def apply_bear(std, bear):
    b = np.asarray(bear, dtype=bool)
    assert b.shape == (len(std),)
    vals = std.to_numpy(dtype=float)
    vals = np.where(b[:, None] & (vals > 0.0), vals * 0.5, vals)
    return pd.DataFrame(vals, index=std.index, columns=std.columns)


def book_episodes(events):
    pos, out = {}, []
    for e in events:
        k, sym = e.get("kind"), e.get("symbol")
        if k == "book_fill":
            q = abs(e["weight"]) / e["price"]
            pos[sym] = dict(side=1 if e["side"] == "buy" else -1, qty=q,
                            cost=q * e["price"], proceeds=0.0,
                            fees=q * e["price"] * MAKER)
            continue
        o = pos.get(sym)
        if o is None:
            continue
        if k == "book_add":
            q = abs(e["weight"]) / e["price"]
            o["qty"] += q
            o["cost"] += q * e["price"]
            o["fees"] += q * e["price"] * MAKER
        elif k in ("book_reduce", "book_partial"):
            q = min(abs(e["weight"]) / e["price"], o["qty"])
            o["qty"] -= q
            o["proceeds"] += q * e["price"]
            o["fees"] += q * e["price"] * MAKER
        elif k in ("book_stop", "book_tp", "book_close"):
            o["proceeds"] += o["qty"] * e["price"]
            o["fees"] += o["qty"] * e["price"] * (TAKER if k == "book_stop" else MAKER)
            net = (o["side"] * (o["proceeds"] - o["cost"]) - o["fees"]) / o["cost"]
            out.append((pd.Timestamp(e["t"]), float(net)))
    return out


def cmd_build_books():
    eu = _load("eu_shm_books", RD / "engine_user" / "engine_user.py")
    fw = _load("fw_shm_books", ROOT / "scripts" / "forward_v205.py")
    books, bear, cols = build_standard_books(eu)
    ref = fw.research_books_d2(eu).reindex(books["FULL"].index).fillna(0.0)[cols]
    d = float((books["FULL"] - ref).abs().max().max())
    print(f"FULL vs research_books_d2 max abs diff: {d:.3e}", flush=True)
    assert d < 1e-12, d
    TMP.mkdir(exist_ok=True)
    with open(TMP / "std_books_short.pkl", "wb") as fh:
        pickle.dump({"books": books, "bear": bear, "cols": cols}, fh)
    print(f"wrote tmp/std_books_short.pkl variants={list(books)} rows={len(books['FULL'])} "
          f"bear_frac={round(float(np.mean(bear)), 4)}", flush=True)


def cmd_shift(shift):
    t0 = time.time()
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podshm_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histshm_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221shm_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    eu, v216 = v221.eu, v221.v216
    with open(TMP / "std_books_short.pkl", "rb") as fh:
        S = pickle.load(fh)
    books_std, bear, cols = S["books"], S["bear"], S["cols"]
    books154, _ = eu.er.v154_books()
    assert list(books154.columns) == cols
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    print(f"shift {shift}: loading 1m minutes ...", flush=True)
    M = pod.minutes()
    print(f"shift {shift}: minutes loaded in {time.time() - t0:.0f}s, prep ...", flush=True)
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, cols)
    del M
    idx = prep["idx"]
    assert list(prep["cols"]) == cols
    std_bear = {v: apply_bear(books_std[v].reindex(books154.index).fillna(0.0)[cols], bear)
                for v in VARIANTS}
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    out = {}
    for v in VARIANTS:
        t1 = time.time()
        books_bear = std_bear[v].reindex(idx, method="ffill").fillna(0.0)
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size = kw["sleeve_fill_size"]
        kd = 1.7

        def corr_size(i, a, r, f, base_size=base_size, kd=kd):
            m = f - 1
            n = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                    continue
                n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            return (1.0 / (1 + n)) * kd * float(base_size(i, a, r, f))

        kw["sleeve_fill_size"] = corr_size
        kw["risk_mult"] = lambda i, e, k=1.0: k
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * kd
        kw["sleeve_gross_cap"] = 2.0
        ev = []
        eu.simulate(books_bear, opens, prep, trade=trade, win_start=5, events=ev, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        rungs = [(str(e["t"]), float(e["ret"])) for e in ev
                 if e.get("kind") in ("rung_tp", "rung_sl", "rung_timeout") and "ret" in e]
        eps = [(str(t), float(n)) for t, n in book_episodes(ev)]
        kinds = {}
        for e in ev:
            kinds[str(e.get("kind"))] = kinds.get(str(e.get("kind")), 0) + 1
        out[v] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                      eq=(cap["eq"][lv] / base).tolist(),
                      eq_min=(cap["eq_min"][lv] / base).tolist(),
                      rungs=rungs, book_episodes=eps, kinds=kinds)
        print(f"shift {shift} {v}: eq_end={round(out[v]['eq'][-1], 4)} "
              f"rungs={len(rungs)} book_ep={len(eps)} in {time.time() - t1:.0f}s "
              f"(total {time.time() - t0:.0f}s)", flush=True)
    with open(TMP / f"shift_short_{shift}.pkl", "wb") as fh:
        pickle.dump(out, fh)
    print(f"shift {shift}: wrote tmp/shift_short_{shift}.pkl in {time.time() - t0:.0f}s", flush=True)


def cmd_score():
    rm = _load("rm_shm", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    v388 = _load("v388_shm", RD / "v388/v388_bot_stop_distance.py")
    runs = {}
    for s in range(4):
        with open(TMP / f"shift_short_{s}.pkl", "rb") as fh:
            d = pickle.load(fh)
        runs[s] = {v: {"t": d[v]["t"], "eq": d[v]["eq"], "eq_min": d[v]["eq_min"]} for v in VARIANTS}
        ev = {v: {"rungs": d[v]["rungs"], "book_episodes": d[v]["book_episodes"],
                   "kinds": d[v]["kinds"]} for v in VARIANTS}
        runs[s]["_ev"] = ev
    exp = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    allruns = {s: {v: runs[s][v] for v in VARIANTS} for s in range(4)}
    got_years = [rm.year_reset(allruns, "FULL", y) for y in range(5)]
    assert [(m["R"], m["DD"]) for m in got_years] == [(r, d) for r, d in exp["years"]], (got_years, exp["years"])
    R5 = round(float(np.prod([1 + m["R"] / 100 for m in got_years]) ** (1 / 5) - 1) * 100, 3)
    assert R5 == exp["R"], (R5, exp["R"])
    assert max(m["DD"] for m in got_years) == exp["DD"], got_years
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(allruns, "FULL", g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    full_dd = round(100 * float(np.max(1 - mn[seg].to_numpy() / np.maximum.accumulate(e[seg].to_numpy()))), 2)
    assert full_dd == exp["full_path_dd"], (full_dd, exp["full_path_dd"])
    print(f"FULL reproduction OK: R={R5} DD={exp['DD']} full={full_dd}", flush=True)

    rows = {}
    for v in VARIANTS:
        years = [rm.year_reset(allruns, v, y) for y in range(5)]
        e, mn = v388.mix(allruns, v, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        fdd = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        dev4 = years[:4]
        R4 = round(float(np.prod([1 + m["R"] / 100 for m in dev4]) ** (1 / 4) - 1) * 100, 3)
        R5v = round(float(np.prod([1 + m["R"] / 100 for m in years]) ** (1 / 5) - 1) * 100, 3)
        all_r = [(pd.Timestamp(t), float(r)) for s in range(4) for t, r in runs[s]["_ev"][v]["rungs"]]
        all_b = [(pd.Timestamp(t), float(r)) for s in range(4) for t, r in runs[s]["_ev"][v]["book_episodes"]]
        per_year = []
        for y, a0 in enumerate(ANCH):
            a1 = a0 + YEAR
            ry = [r for t, r in all_r if a0 <= t < a1]
            by = [r for t, r in all_b if a0 <= t < a1]
            ay = ry + by
            per_year.append({
                "anchor": str(a0.date()), "R": years[y]["R"], "DD": years[y]["DD"],
                "rungs": len(ry), "rung_win": round(sum(r > 0 for r in ry) / len(ry), 4) if ry else None,
                "book_episodes": len(by), "book_win": round(sum(r > 0 for r in by) / len(by), 4) if by else None,
                "all_trades": len(ay), "all_win": round(sum(r > 0 for r in ay) / len(ay), 4) if ay else None,
            })
        rows[v] = {
            "years": per_year,
            "dev4_R": R4, "dev4_W": min(m["R"] for m in dev4),
            "dev4_DD": max(m["DD"] for m in dev4),
            "dev4_losing": sum(m["R"] < 0 for m in dev4),
            "R5": R5v, "W5": min(m["R"] for m in years),
            "max_yearly_DD": max(m["DD"] for m in years),
            "full_path_dd": fdd,
            "rungs_total": len(all_r), "book_episodes_total": len(all_b),
        }
    with open(TMP / "results_engine.json", "w") as fh:
        json.dump({"rows": rows,
                   "full_reproduces_v421": {"R": R5, "DD": exp["DD"], "full_path_dd": full_dd}},
                  fh, indent=1)
    for v in VARIANTS:
        r = rows[v]
        print(f"{v}: dev4_R={r['dev4_R']} dev4_W={r['dev4_W']} dev4_DD={r['dev4_DD']} "
              f"losing={r['dev4_losing']} R5={r['R5']} fullDD={r['full_path_dd']} "
              f"years={[(y['anchor'], y['R'], y['DD']) for y in r['years']]}", flush=True)
    print("wrote tmp/results_engine.json (internal scratch)", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-books", action="store_true")
    ap.add_argument("--shift", type=int, default=None)
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    if a.build_books:
        cmd_build_books()
    elif a.shift is not None:
        cmd_shift(a.shift)
    elif a.score:
        cmd_score()
    else:
        raise SystemExit("pass --build-books, --shift S, or --score")


if __name__ == "__main__":
    main()
