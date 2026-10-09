"""oc_memberagree: member-agreement confidence sizing (IDEAS8 #3).

See PLAN.md (pre-registered 2026-10-08; read it first — frozen, no outcome
computed before it). Modes:
  --build-books : LIGHT. Rebuild REF/V1/V2/C08/C_V1/C_V2 standard-grid books
                  from cached member parquets (read-only) + bear mask.
  --shift S     : HEAVY (run via heavy_slot). One 4-phase-engine shift; runs
                  all six book variants sequentially on one minutes load,
                  exactly as v421 R2B1D17BFG2 (rule inv, k 1.0, kd 1.7,
                  bear, G 2.0).
  --score       : LIGHT. Validate REF vs v421_result to the digit, then score
                  all rows (reset metric per year + full-path DD + trade
                  stats + fee split + exposure diagnostics) into
                  results.json (dev4 robust pick among REF/V1/V2 only).
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
VARIANTS = ("REF", "V1", "V2", "C08", "C_V1", "C_V2")
ELIGIBLE = ("REF", "V1", "V2")  # controls reported, NOT eligible
MAKER, TAKER = 0.0002, 0.00055


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sgn(df: pd.DataFrame) -> pd.DataFrame:
    vals = df.to_numpy(dtype=float)
    return pd.DataFrame(np.where(vals > 0.0, 1, np.where(vals < 0.0, -1, 0)),
                        index=df.index, columns=df.columns)


def agreement_and_scales(members: dict[str, pd.DataFrame],
                         w_ens: pd.DataFrame):
    """Per (T,s) agreement count + frozen V1/V2 scales (PLAN definition).

    a = # of 6 members with sgn(m) == sgn(w_ens) where w_ens != 0
    (member == 0 counts as disagree). Where w_ens == 0: a = 6, scale 1.0.
    V1: 1.0 if a>=5, 0.5 if a<=3, else 0.75.
    V2: 1.0 if a==6, 0.5 if a<=4, else 0.75 (a==5 -> 0.75).
    """
    cols = list(w_ens.columns)
    se = _sgn(w_ens)
    a = pd.DataFrame(0, index=w_ens.index, columns=cols, dtype=np.int8)
    for m in ("A", "Aq", "B", "Bq", "D", "Dq"):
        a = a + ((_sgn(members[m]) == se) & (se != 0)).astype(np.int8)
    a = a.where(se != 0, 6).astype(np.int8)
    av = a.to_numpy()
    s1 = np.where(av >= 5, 1.0, np.where(av <= 3, 0.5, 0.75))
    s2 = np.where(av == 6, 1.0, np.where(av <= 4, 0.5, 0.75))
    s1 = pd.DataFrame(s1, index=w_ens.index, columns=cols)
    s2 = pd.DataFrame(s2, index=w_ens.index, columns=cols)
    return a, s1, s2


# ---------------------------------------------------------------- books ---

def build_standard_books(eu):
    """Return (books_dict, bear, cols, agree, scales, cy). Pre-bear books on
    the books154 index; bear: boolean ndarray (v421 rule). agree: int8
    agreement counts; scales: {V1, V2} scale frames; cy: {C_V1, C_V2, per-year
    gross ratios + mean scales} diagnostics."""
    books154, opens_std = eu.er.v154_books()
    cols = list(books154.columns)
    assert set(cols) == SYMS_EXPECTED, cols
    C = eu.er.CACHE
    A = pd.read_parquet(C / "member_A_O1_orders.parquet")[cols]
    Aq = pd.read_parquet(C / "member_Aq_O1_orders.parquet")[cols]
    B = pd.read_parquet(C / "member_B_tv.parquet")[cols]
    Bq = pd.read_parquet(C / "member_Bq_tv.parquet")[cols]
    D = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0)[cols]
    Dq = pd.read_parquet(C / "members_quarterly_D.parquet")[cols]
    idx = A.index.union(Aq.index).union(B.index).union(Bq.index).union(D.index).union(Dq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)
    A, Aq, B, Bq, D, Dq = f(A), f(Aq), f(B), f(Bq), f(D), f(Dq)
    o1 = 0.25 * (A + B + Aq + Bq)
    cb = 0.5 * (D + Dq)
    w_ens = 0.8 * o1 + 0.2 * cb
    std_idx = books154.index
    re = lambda X: X.reindex(std_idx).fillna(0.0)[cols]
    Ms = {k: re(X) for k, X in
          (("A", A), ("Aq", Aq), ("B", B), ("Bq", Bq), ("D", D), ("Dq", Dq))}
    wens = re(w_ens)
    agree, sV1, sV2 = agreement_and_scales(Ms, wens)
    wV1, wV2 = wens * sV1, wens * sV2
    # exposure-matched per-year gross ratios on the standard grid
    # (bear commutes with non-negative scaling, so pre/post-bear identical)
    cy: dict[str, list] = {"C_V1": [], "C_V2": []}
    wCV1 = pd.DataFrame(0.0, index=std_idx, columns=cols)
    wCV2 = pd.DataFrame(0.0, index=std_idx, columns=cols)
    for y, a0 in enumerate(ANCH):
        a1 = a0 + YEAR
        m = (std_idx >= a0) & (std_idx < a1)
        g0 = float(wens.loc[m].abs().to_numpy().sum())
        c1 = float(wV1.loc[m].abs().to_numpy().sum() / g0) if g0 else 1.0
        c2 = float(wV2.loc[m].abs().to_numpy().sum() / g0) if g0 else 1.0
        cy["C_V1"].append({"anchor": str(a0.date()), "c": c1,
                           "mean_scale_V1": float(sV1.loc[m].to_numpy().mean())})
        cy["C_V2"].append({"anchor": str(a0.date()), "c": c2,
                           "mean_scale_V2": float(sV2.loc[m].to_numpy().mean())})
        wCV1.loc[m] = wens.loc[m] * c1
        wCV2.loc[m] = wens.loc[m] * c2
    books = {
        "REF": wens,
        "V1": wV1,
        "V2": wV2,
        "C08": wens * 0.8,
        "C_V1": wCV1,
        "C_V2": wCV2,
    }
    btc = opens_std["BTCUSDT"].reindex(std_idx)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).fillna(False).to_numpy(bool)
    scales = {"V1": sV1, "V2": sV2}
    return books, bear, cols, agree, scales, cy


def apply_bear(std, bear):
    # v421: sb.loc[bear] halve rows where w > 0 (longs only), shorts/flats kept
    b = np.asarray(bear, dtype=bool)
    assert b.shape == (len(std),)
    vals = std.to_numpy(dtype=float)
    vals = np.where(b[:, None] & (vals > 0.0), vals * 0.5, vals)
    return pd.DataFrame(vals, index=std.index, columns=std.columns)


def cmd_build_books():
    eu = _load("eu_ma_books", RD / "engine_user" / "engine_user.py")
    fw = _load("fw_ma_books", ROOT / "scripts" / "forward_v205.py")
    books, bear, cols, agree, scales, cy = build_standard_books(eu)
    ref = fw.research_books_d2(eu).reindex(books["REF"].index).fillna(0.0)[cols]
    d = float((books["REF"] - ref).abs().max().max())
    print(f"REF vs research_books_d2 max abs diff: {d:.3e}", flush=True)
    assert d < 1e-12, d
    TMP.mkdir(exist_ok=True)
    with open(TMP / "std_books.pkl", "wb") as fh:
        pickle.dump({"books": books, "bear": bear, "cols": cols,
                     "agree": agree, "scales": scales, "cy": cy}, fh)
    for v in VARIANTS:
        g = float(books[v].abs().to_numpy().sum())
        g0 = float(books["REF"].abs().to_numpy().sum())
        print(f"built {v}: rows={len(books[v])} gross_ratio={g/g0:.4f}",
              flush=True)
    print(f"bear_frac={round(float(np.mean(bear)), 4)}", flush=True)
    print("wrote tmp/std_books.pkl", flush=True)


# ---------------------------------------------------------------- engine ---

def book_episodes(events):
    """Walk book events -> list of (t, net, maker_fee, taker_fee).

    Same v213-style walk as oc_memberdrop (net identical); fees split into
    maker legs (fill/add/reduce/partial/tp/close x MAKER) and taker legs
    (stop x TAKER) for the REPORT fee split.
    """
    pos, out = {}, []
    for e in events:
        k, sym = e.get("kind"), e.get("symbol")
        if k == "book_fill":
            q = abs(e["weight"]) / e["price"]
            pos[sym] = dict(side=1 if e["side"] == "buy" else -1, qty=q,
                            cost=q * e["price"], proceeds=0.0,
                            maker=q * e["price"] * MAKER, taker=0.0)
            continue
        o = pos.get(sym)
        if o is None:
            continue
        if k == "book_add":
            q = abs(e["weight"]) / e["price"]
            o["qty"] += q
            o["cost"] += q * e["price"]
            o["maker"] += q * e["price"] * MAKER
        elif k in ("book_reduce", "book_partial"):
            q = min(abs(e["weight"]) / e["price"], o["qty"])
            o["qty"] -= q
            o["proceeds"] += q * e["price"]
            o["maker"] += q * e["price"] * MAKER
        elif k in ("book_stop", "book_tp", "book_close"):
            o["proceeds"] += o["qty"] * e["price"]
            if k == "book_stop":
                o["taker"] += o["qty"] * e["price"] * TAKER
            else:
                o["maker"] += o["qty"] * e["price"] * MAKER
            net = (o["side"] * (o["proceeds"] - o["cost"])
                   - o["maker"] - o["taker"]) / o["cost"]
            out.append((pd.Timestamp(e["t"]), float(net),
                        float(o["maker"]), float(o["taker"])))
            pos.pop(sym)
    return out


def cmd_shift(shift):
    t0 = time.time()
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podma_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histma_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221ma_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    eu, v216 = v221.eu, v221.v216
    with open(TMP / "std_books.pkl", "rb") as fh:
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
    print(f"shift {shift}: minutes loaded in {time.time()-t0:.0f}s, prep ...", flush=True)
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, cols)
    del M
    idx = prep["idx"]
    assert list(prep["cols"]) == cols
    std_bear = {v: apply_bear(books_std[v].reindex(books154.index).fillna(0.0)[cols],
                              bear) for v in VARIANTS}
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
        eps = [(str(t), float(n), float(mf), float(tf))
               for t, n, mf, tf in book_episodes(ev)]
        kinds = {}
        for e in ev:
            kinds[str(e.get("kind"))] = kinds.get(str(e.get("kind")), 0) + 1
        out[v] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                      eq=(cap["eq"][lv] / base).tolist(),
                      eq_min=(cap["eq_min"][lv] / base).tolist(),
                      rungs=rungs, book_episodes=eps, kinds=kinds)
        print(f"shift {shift} {v}: eq_end={round(out[v]['eq'][-1], 4)} "
              f"rungs={len(rungs)} book_ep={len(eps)} in {time.time()-t1:.0f}s "
              f"(total {time.time()-t0:.0f}s)", flush=True)
    with open(TMP / f"shift_{shift}.pkl", "wb") as fh:
        pickle.dump(out, fh)
    print(f"shift {shift}: wrote tmp/shift_{shift}.pkl in {time.time()-t0:.0f}s", flush=True)


# ----------------------------------------------------------------- score ---

def robust_pick(rows):
    """Dev4 robust criterion on ELIGIBLE rows only (PLAN)."""
    def ok(m):
        return m["dev4_DD"] <= 20 and m["dev4_losing"] == 0
    cands = [v for v in ELIGIBLE if ok(rows[v])]
    if not cands:
        return None, "no eligible row satisfies DD<=20 and no losing dev year"
    hi = [v for v in cands if rows[v]["dev4_R"] >= 5]
    pool = hi if hi else cands
    best = max(pool, key=lambda v: (rows[v]["dev4_W"], rows[v]["dev4_R"]))
    return best, ("dev4 mean>=5 attainable" if hi else "no row reaches mean>=5; "
                 "highest WORST among DD-ok rows")


def cmd_score():
    rm = _load("rm_ma", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    v388 = _load("v388_ma", RD / "v388/v388_bot_stop_distance.py")
    runs = {}
    for s in range(4):
        with open(TMP / f"shift_{s}.pkl", "rb") as fh:
            d = pickle.load(fh)
        runs[s] = {v: {"t": d[v]["t"], "eq": d[v]["eq"], "eq_min": d[v]["eq_min"]} for v in VARIANTS}
        ev = {v: {"rungs": d[v]["rungs"], "book_episodes": d[v]["book_episodes"],
                   "kinds": d[v]["kinds"]} for v in VARIANTS}
        runs[s]["_ev"] = ev
    # REF reproduction gate (to the digit)
    exp = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    allruns = {s: {v: runs[s][v] for v in VARIANTS} for s in range(4)}
    got_years = [rm.year_reset(allruns, "REF", y) for y in range(5)]
    assert [(m["R"], m["DD"]) for m in got_years] == [(r, d) for r, d in exp["years"]], (got_years, exp["years"])
    R5 = round(float(np.prod([1 + m["R"] / 100 for m in got_years]) ** (1 / 5) - 1) * 100, 3)
    assert R5 == exp["R"], (R5, exp["R"])
    assert max(m["DD"] for m in got_years) == exp["DD"], got_years
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(allruns, "REF", g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    full_dd = round(100 * float(np.max(1 - mn[seg].to_numpy() / np.maximum.accumulate(e[seg].to_numpy()))), 2)
    assert full_dd == exp["full_path_dd"], (full_dd, exp["full_path_dd"])
    print(f"REF reproduction OK: R={R5} DD={exp['DD']} full={full_dd}", flush=True)

    with open(TMP / "std_books.pkl", "rb") as fh:
        S = pickle.load(fh)
    agree, scales = S["agree"], S["scales"]
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
        all_b = [(pd.Timestamp(t), float(r), float(mf), float(tf))
                 for s in range(4) for t, r, mf, tf in runs[s]["_ev"][v]["book_episodes"]]
        per_year = []
        for y, a0 in enumerate(ANCH):
            a1 = a0 + YEAR
            ry = [r for t, r in all_r if a0 <= t < a1]
            by = [(r, mf, tf) for t, r, mf, tf in all_b if a0 <= t < a1]
            ay = ry + [r for r, _, _ in by]
            per_year.append({
                "anchor": str(a0.date()), "R": years[y]["R"], "DD": years[y]["DD"],
                "rungs": len(ry), "rung_win": round(sum(r > 0 for r in ry) / len(ry), 4) if ry else None,
                "book_episodes": len(by), "book_win": round(sum(r > 0 for r, _, _ in by) / len(by), 4) if by else None,
                "maker_fees": round(float(sum(mf for _, mf, _ in by)), 6),
                "taker_fees": round(float(sum(tf for _, _, tf in by)), 6),
                "all_trades": len(ay), "all_win": round(sum(r > 0 for r in ay) / len(ay), 4) if ay else None,
            })
        # exposure diagnostics on the standard grid per year
        exp_diag = []
        bks = S["books"]
        for y, a0 in enumerate(ANCH):
            a1 = a0 + YEAR
            m = (bks["REF"].index >= a0) & (bks["REF"].index < a1)
            g0 = float(bks["REF"].loc[m].abs().to_numpy().sum())
            gr = float(bks[v].loc[m].abs().to_numpy().sum() / g0) if g0 else None
            exp_diag.append({"anchor": str(a0.date()), "gross_ratio": round(gr, 4) if gr else None})
        rows[v] = {
            "years": per_year,
            "dev4_R": R4, "dev4_W": min(m["R"] for m in dev4),
            "dev4_DD": max(m["DD"] for m in dev4),
            "dev4_losing": sum(m["R"] < 0 for m in dev4),
            "R5": R5v, "W5": min(m["R"] for m in years),
            "max_yearly_DD": max(m["DD"] for m in years),
            "full_path_dd": fdd,
            "book_only_share": "not separable from stored t/eq/eq_min equity (same as v421; no sleeve-off runs, out of scope)",
            "rungs_total": len(all_r), "book_episodes_total": len(all_b),
            "maker_fees_total": round(float(sum(mf for _, _, mf, _ in all_b)), 6),
            "taker_fees_total": round(float(sum(tf for _, _, _, tf in all_b)), 6),
            "exposure_per_year": exp_diag,
        }
    # agreement distribution (standard grid, per year + full)
    ahist = {}
    for y, a0 in enumerate(ANCH):
        a1 = a0 + YEAR
        m = (agree.index >= a0) & (agree.index < a1)
        vals = agree.loc[m].to_numpy().ravel()
        hist = {str(k): int((vals == k).sum()) for k in range(7)}
        hist["mean_a"] = round(float(vals.mean()), 4)
        for tag, sc in (("V1", scales["V1"]), ("V2", scales["V2"])):
            hist[f"mean_scale_{tag}"] = round(float(sc.loc[m].to_numpy().mean()), 4)
        ahist[str(a0.date())] = hist
    pick, why = robust_pick(rows)
    res = {
        "meta": {
            "engine": "v421 R2B1D17BFG2 replica (rule inv, k 1.0, kd 1.7, bear True, G 2.0, agents ON v376 tables, win_start 5)",
            "books": ("REF=w_ens (0.8*o1+0.2*cb, o1=(A+Aq+B+Bq)/4, cb=(D+Dq)/2); "
                      "V1=w_ens x {1.0 a>=5, 0.5 a<=3, else 0.75}; V2=w_ens x {1.0 a==6, 0.5 a<=4, else 0.75}; "
                      "C08=0.8 x w_ens; C_V1/C_V2=w_ens x per-year realised gross ratio of V1/V2 "
                      "(diagnostic, in-year, not eligible); v421 x0.5 bear filter after scaling on all rows"),
            "anchors": [str(a.date()) for a in ANCH],
            "cy": {k: v for k, v in S["cy"].items()},
            "full_reproduces_v421": {"R": R5, "DD": exp["DD"], "full_path_dd": full_dd},
            "selection": ("dev4 robust pick among REF/V1/V2 only (controls reported, not eligible): "
                          "DD<=20, no losing dev year, prefer mean>=5, highest WORST, ties->mean"),
            "robust_pick": {"variant": pick, "reason": why},
            "costs": "maker 0.0002 / taker 0.00055, adverse long funding 0.0001/8h, no fill min 0-4, stop-first",
            "book_only_share": "not separable (engine stores t/eq/eq_min only)",
            "fee_split": "maker = fill/add/reduce/partial/tp/close legs x0.0002; taker = stop legs x0.00055 (book-episode walk)",
        },
        "rows": rows,
        "agreement_hist": ahist,
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1, default=str))
    for v in VARIANTS:
        r = rows[v]
        print(f"{v}: dev4_R={r['dev4_R']} dev4_W={r['dev4_W']} dev4_DD={r['dev4_DD']} "
              f"losing={r['dev4_losing']} R5={r['R5']} fullDD={r['full_path_dd']} "
              f"years={[(y['anchor'], y['R'], y['DD']) for y in r['years']]}", flush=True)
    print(f"robust_pick={pick} ({why})", flush=True)
    print("wrote results.json", flush=True)


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
