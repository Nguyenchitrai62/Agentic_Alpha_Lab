"""oc_convttl: conviction-dependent order TTL (IDEAS8 #7) — 4-phase engine vs G2.

See PLAN.md (pre-registered 2026-10-08; frozen, read it first — no outcome
computed before it). Modes:
  --build-books : LIGHT. Rebuild w_ens + bear mask + pre-anchor q50/q75
                  (U < A_k - 7d, non-zero |w_base| pooled) + realised p/s
                  + C-row scaled books + research_books_d2 check.
  --shift S --stage dev|last --rows ... : HEAVY (run via heavy_slot). One
                  4-phase-engine shift; runs the requested book rows
                  sequentially on one minutes load, exactly as v421
                  R2B1D17BFG2 (rule inv, k 1.0, kd 1.7, bear, G 2.0).
                  V1/V2 use the TTL patch (flat-branch T["exp"] only);
                  REF/C rows use the unpatched G2 path bit-exact.
  --score       : LIGHT. Validate REF vs v421_result to the digit, robust
                  dev4 pick among REF/V1/V2 only, score last year ONCE for
                  REF + pick, write results.json.

Engine replica: pipe_setup("v321") + corr_size inv/kd=1.7 + risk_mult 1.0 +
sleeve_risk_budget 0.26*1.7 + sleeve_gross_cap 2.0, eu.simulate(books_bear,
opens, prep, trade=trade, win_start=5, events=ev). Gate costs are the
engine's own (maker 0.0002 / taker 0.00055 / adverse long funding 0.0001/8h,
no fill minutes 0-4, stop-first).
"""
from __future__ import annotations

import argparse
import gc
import importlib.util
import inspect
import json
import pickle
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"
V421_RES = RD / "v421" / "v421_result.json"
TMP = HERE / "tmp"
CACHE_DEV = TMP / "runs_dev.pkl"
CACHE_LAST = TMP / "runs_last.pkl"
CACHE_BOOKS = TMP / "std_books.pkl"

sys.path.insert(0, str(HERE))
import convttl as ct  # noqa: E402

SYMS_EXPECTED = {"BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"}
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
ANCH_S = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
YEAR = pd.Timedelta(days=365)
EMBARGO = pd.Timedelta(days=7)
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
DEV1 = pd.Timestamp("2025-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
VARIANTS_DEV = ("REF", "V1", "V2", "C_V1", "C_V2")
ELIGIBLE = ("REF", "V1", "V2")
MAKER, TAKER = 0.0002, 0.00055
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
HEARTBEAT_S = 600

_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print(f"[hb {datetime.now(timezone.utc):%H:%M:%S}Z] {tag} alive", flush=True)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ books ---

def apply_bear(std: pd.DataFrame, bear: np.ndarray) -> pd.DataFrame:
    b = np.asarray(bear, dtype=bool)
    assert b.shape == (len(std),)
    vals = std.to_numpy(dtype=float)
    vals = np.where(b[:, None] & (vals > 0.0), vals * 0.5, vals)
    return pd.DataFrame(vals, index=std.index, columns=std.columns)


def cmd_build_books() -> None:
    eu = _load("eu_ct_books", RD / "engine_user" / "engine_user.py")
    fw = _load("fw_ct_books", ROOT / "scripts" / "forward_v205.py")
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
    wens = re(w_ens)
    # builder check: REF must equal research_books_d2
    ref = fw.research_books_d2(eu).reindex(wens.index).fillna(0.0)[cols]
    d = float((wens - ref).abs().max().max())
    print(f"REF vs research_books_d2 max abs diff: {d:.3e}", flush=True)
    assert d < 1e-12, d
    # bear mask on the standard grid (v421 rule)
    btc = opens_std["BTCUSDT"].reindex(std_idx)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).fillna(False).to_numpy(bool)
    wbase = apply_bear(wens, bear)
    # pre-anchor quantiles: pool U < A_k - 7d, non-zero |w_base| pooled across coins
    avals = wbase.abs().to_numpy(dtype=float)
    tvals = std_idx.values.astype("datetime64[ns]").astype(np.int64)
    q50, q75 = [], []
    for k, a0 in enumerate(ANCH):
        cut = (a0 - EMBARGO).value
        pool = avals[tvals < cut]
        pool = pool[np.isfinite(pool) & (pool > 0.0)]
        if len(pool) == 0:
            # Grid starts at A_0 (books154 index 2021-09-24): Y0 has no
            # pre-anchor history. Rule INACTIVE in Y0 (all TTL=2, G2 behavior):
            # q = -1.0 so every |w_base| >= 0 exceeds it (disclosed PLAN fix,
            # no variant outcome seen). Later years have 2000+ rows/coin.
            assert k == 0, (a0, len(pool))
            q50.append(-1.0)
            q75.append(-1.0)
            continue
        assert len(pool) > 100, (a0, len(pool))
        q50.append(float(np.quantile(pool, 0.50)))
        q75.append(float(np.quantile(pool, 0.75)))
    # realised long-TTL shares + mean-TTL scales per year (standard-grid years
    # [A_y, A_y+365d); diagnostic, uses in-year data -> controls NOT eligible)
    p_V1, p_V2, s_V1, s_V2 = [], [], [], []
    wCV1 = pd.DataFrame(0.0, index=std_idx, columns=cols)
    wCV2 = pd.DataFrame(0.0, index=std_idx, columns=cols)
    for y, a0 in enumerate(ANCH):
        a1 = a0 + YEAR
        m = (std_idx >= a0) & (std_idx < a1)
        sub = wbase.loc[m].abs().to_numpy(dtype=float).ravel()
        nz = sub[np.isfinite(sub) & (sub > 0.0)]
        p1 = float((nz > q50[y]).mean()) if len(nz) else 0.0
        p2 = float((nz > q75[y]).mean()) if len(nz) else 0.0
        s1, s2 = ct.mean_ttl_scale(p1), ct.mean_ttl_scale(p2)
        p_V1.append(p1)
        p_V2.append(p2)
        s_V1.append(s1)
        s_V2.append(s2)
        wCV1.loc[m] = wens.loc[m] * s1
        wCV2.loc[m] = wens.loc[m] * s2
    books = {"REF": wens, "C_V1": wCV1, "C_V2": wCV2}
    TMP.mkdir(parents=True, exist_ok=True)
    with open(CACHE_BOOKS, "wb") as fh:
        pickle.dump({"books": books, "wbase": wbase, "bear": bear, "cols": cols,
                     "q50": q50, "q75": q75, "p_V1": p_V1, "p_V2": p_V2,
                     "s_V1": s_V1, "s_V2": s_V2}, fh)
    for y, a0 in enumerate(ANCH):
        print(f"year {str(a0.date())}: q50={q50[y]:.6f} q75={q75[y]:.6f} "
              f"pV1={p_V1[y]:.4f} sV1={s_V1[y]:.4f} pV2={p_V2[y]:.4f} sV2={s_V2[y]:.4f}",
              flush=True)
    print(f"bear_frac={round(float(np.mean(bear)), 4)}", flush=True)
    print("wrote tmp/std_books.pkl", flush=True)


# ------------------------------------------------------------- TTL patch ---

OLD_EXP = 'T["exp"][a], T["psd"][a], T["issued"][a] = i + P.get("n_valid", 2), sd_a, i'

NEW_EXP = ('_thr_q = float(_THR[i])\n'
           '                _ttl = 2 if (np.isfinite(B[i, a]) and abs(float(B[i, a])) > _thr_q) else 1\n'
           '                T["exp"][a], T["psd"][a], T["issued"][a] = i + _ttl, sd_a, i')


def make_simulate(eu, thr: np.ndarray | None):
    """G2 simulate with conviction TTL when thr is not None (V1/V2)."""
    if thr is None:
        return eu.simulate
    src = inspect.getsource(eu.simulate)
    assert src.count(OLD_EXP) == 1, "exp anchor not unique"
    patched = src.replace(OLD_EXP, NEW_EXP)
    g = eu.simulate.__globals__
    g["_THR"] = np.asarray(thr, dtype=float)
    ns: dict = {}
    exec(patched, g, ns)  # noqa: S102 - audited pattern (cf. oc_booktwo)
    fn = ns.get("simulate")
    if fn is None:  # pragma: no cover
        raise RuntimeError("patched simulate missing")
    return fn


# ------------------------------------------------------------ book walk ---

def book_episodes(events):
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


# ---------------------------------------------------------------- engine ---

def validate_g2() -> None:
    runs = pickle.loads((RD / "v421" / "v421_runs.pkl").read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    exp = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    v388 = pof._load("v388_ct_val", RD / "v388/v388_bot_stop_distance.py")
    rm = pof._load("reset_ct_val", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    strat = "R2B1D17BFG2"
    got_r = [rm.year_reset(runs, strat, y)["R"] for y in range(5)]
    got_dd = [rm.year_reset(runs, strat, y)["DD"] for y in range(5)]
    assert got_r == [r for r, _ in exp["years"]], (got_r, exp["years"])
    assert got_dd == [d for _, d in exp["years"]], (got_dd, exp["years"])
    print("G2 stored-runs validation OK (5.41 / 16.91 / 16.82 family)", flush=True)


def run_shift(shift: int, variants: list[str], stage: str):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    tag = f"{stage}_s{shift}"
    pod = pof._load(f"podct_{stage}_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histct_{stage}_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221ct_{stage}_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwct_{stage}_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    with open(CACHE_BOOKS, "rb") as fh:
        S = pickle.load(fh)
    books_std, bear, cols = S["books"], S["bear"], S["cols"]
    q50, q75 = S["q50"], S["q75"]
    cap = {}

    def _summ(idx, net, eq, eq_min, g, stats, eq_max=None):
        cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
                   stats=dict(stats))

    eu.summarize = _summ
    sh = pd.Timedelta(hours=shift)
    last = (stage == "last")
    live0 = DEV0 + sh
    live1 = (Y1 if last else DEV1) + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _opens_std = eu.er.v154_books()
    assert list(books154.columns) == cols
    std_idx = books154.index if last else books154.index[books154.index <= DEV1 + pd.Timedelta(hours=4)]
    print(f"{tag}: loading 1m minutes ...", flush=True)
    M = pod.minutes()
    print(f"{tag}: minutes loaded, prep ...", flush=True)
    opens, prep = pof.prep_idx(M, std_idx + sh, shift, cols)
    del M
    gc.collect()
    idx, cols_p = prep["idx"], list(prep["cols"])
    assert cols_p == cols
    # bear-filtered books on the shifted clock (ffill; identity at shift 0)
    base = {}
    for v in ("REF", "C_V1", "C_V2"):
        std = books_std[v].reindex(books154.index).fillna(0.0)[cols]
        std_bear = apply_bear(std, bear)
        base[v] = std_bear.reindex(idx, method="ffill").fillna(0.0)
    base["V1"] = base["REF"]
    base["V2"] = base["REF"]
    # per-bar thresholds on this shift's clock
    thr_V1 = ct.thresholds_for_bars(idx, shift, q50)
    thr_V2 = ct.thresholds_for_bars(idx, shift, q75)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"

    out = {}
    for variant in variants:
        t0 = time.time()
        thr = {"V1": thr_V1, "V2": thr_V2}.get(variant)
        sim = make_simulate(eu, thr)
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
        kw["risk_mult"] = lambda i, e: 1.0
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * kd
        kw["sleeve_gross_cap"] = 2.0
        ev: list = []
        sim(base[variant], opens, prep, trade=trade, win_start=5, events=ev, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        bq = cap["eq"][first - 1] if first > 0 else 1.0
        run = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                   eq=(cap["eq"][lv] / bq).tolist(),
                   eq_min=(cap["eq_min"][lv] / bq).tolist())
        years = []
        for y, a in enumerate(ANCH_S):
            if not last and y == 4:
                years.append(dict(nb=0, wb=0, nr=0, wr=0, nfill=0))
                continue
            a0 = pd.Timestamp(a, tz="UTC") + sh
            a1 = min(a0 + YEAR, live1)
            evy = [e for e in ev if a0 <= pd.Timestamp(e["t"]) < a1 + pd.Timedelta(hours=8)]
            ts = v216.v213.trade_stats(evy)
            nb, wb = 0, 0
            for _k, v in (ts.items() if isinstance(ts, dict) else []):
                if isinstance(v, dict) and v.get("trades"):
                    nb += int(v["trades"])
                    wb += int(round(float(v.get("win_rate") or 0.0) * int(v["trades"])))
            rr = [float(e["ret"]) for e in evy if e["kind"] in RUNG_KINDS and "ret" in e]
            nf = sum(1 for e in evy if e["kind"] == "book_fill")
            years.append(dict(nb=nb, wb=wb, nr=len(rr), wr=int(sum(r > 0 for r in rr)), nfill=int(nf)))
        rungs = [(str(e["t"]), float(e["ret"])) for e in ev
                 if e.get("kind") in RUNG_KINDS and "ret" in e]
        eps = [(str(t), float(n), float(mf), float(tf)) for t, n, mf, tf in book_episodes(ev)]
        kinds = {}
        for e in ev:
            kinds[str(e.get("kind"))] = kinds.get(str(e.get("kind")), 0) + 1
        st = cap.get("stats", {})
        out[variant] = dict(run=run, wins=years, rungs=rungs, book_episodes=eps,
                            kinds=kinds,
                            stats={k: (float(v) if isinstance(v, float) else v) for k, v in st.items()})
        print(f"{tag} {variant} eq_end={run['eq'][-1]:.4f} elapsed={(time.time() - t0) / 60:.1f}min",
              flush=True)
        del ev
        gc.collect()
    del opens, prep
    gc.collect()
    return shift, out


# ----------------------------------------------------------------- score ---

def _geo(rs) -> float:
    g = 1.0
    for r in rs:
        g *= 1.0 + float(r) / 100.0
    return 100.0 * (g ** (1.0 / len(rs)) - 1.0)


def score_variant(allres, variant: str, years: list[int], g1, v388, rm):
    runs = {s: {variant: allres[s][variant]["run"]} for s in allres}
    yr = [rm.year_reset(runs, variant, y) for y in years]
    Rs = [y["R"] for y in yr]
    DDs = [y["DD"] for y in yr]
    e, mn = v388.mix(runs, variant, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    fullDD = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    nb = sum(allres[s][variant]["wins"][y]["nb"] for s in allres for y in years)
    wb = sum(allres[s][variant]["wins"][y]["wb"] for s in allres for y in years)
    nr = sum(allres[s][variant]["wins"][y]["nr"] for s in allres for y in years)
    wr = sum(allres[s][variant]["wins"][y]["wr"] for s in allres for y in years)
    nf = sum(allres[s][variant]["wins"][y]["nfill"] for s in allres for y in years)
    fees = sum(float(allres[s][variant].get("stats", {}).get("fees", 0.0)) for s in allres)
    funding = sum(float(allres[s][variant].get("stats", {}).get("funding", 0.0)) for s in allres)
    # book-episode maker/taker split (pooled over the scored years)
    all_b = [(pd.Timestamp(t), float(n), float(mf), float(tf))
             for s in allres for t, n, mf, tf in allres[s][variant]["book_episodes"]]
    per_year, maker_y, taker_y, bepw_y, rwy = [], [], [], [], []
    for y in years:
        a0 = ANCH[y]
        a1 = a0 + YEAR
        by = [(n, mf, tf) for t, n, mf, tf in all_b if a0 <= t < a1]
        # trade_stats win counts for this year
        nby = sum(allres[s][variant]["wins"][y]["nb"] for s in allres)
        wby = sum(allres[s][variant]["wins"][y]["wb"] for s in allres)
        per_year.append(round(wby / nby, 4) if nby else None)
        bepw_y.append(sum(1 for _, _, _ in by))
        maker_y.append(round(float(sum(mf for _, mf, _ in by)), 6))
        taker_y.append(round(float(sum(tf for _, _, tf in by)), 6))
        ry = [float(e[1]) for s in allres for e in allres[s][variant]["rungs"]
              if a0 <= pd.Timestamp(e[0]) < a1]
        rwy.append(round(sum(r > 0 for r in ry) / len(ry), 4) if ry else None)
    return dict(years_R=[y["R"] for y in yr], years_DD=[y["DD"] for y in yr],
                years_book_win=per_year, years_rung_win=rwy, years_fills=[
                    sum(allres[s][variant]["wins"][y]["nfill"] for s in allres) for y in years],
                years_maker=maker_y, years_taker=taker_y,
                R5=round(_geo(Rs), 3), W=round(min(Rs), 3), maxDD=round(max(DDs), 2),
                fullDD=fullDD, losing=sum(r < 0 for r in Rs),
                book_trades=int(nb), book_win=round(wb / nb, 4) if nb else None,
                rung_trades=int(nr), rung_win=round(wr / nr, 4) if nr else None,
                win_all=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None,
                fills=int(nf), fees=round(fees, 4), funding=round(funding, 4),
                maker_tot=round(float(sum(maker_y)), 6), taker_tot=round(float(sum(taker_y)), 6))


def robust_pick(table: dict) -> str:
    cands = {k: v for k, v in table.items() if k in ELIGIBLE
             and v["DDdev4"] <= 20 and v["losing_dev4"] == 0}
    if not cands:
        return "none-eligible"
    hot = {k: v for k, v in cands.items() if v["Rdev4"] >= 5}
    pool = hot or cands
    return max(pool, key=lambda k: (pool[k]["Wdev4"], pool[k]["Rdev4"]))


def cmd_score() -> None:
    rm = _load("rm_ct", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    v388 = _load("v388_ct", RD / "v388/v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    assert CACHE_BOOKS.exists(), "std_books.pkl missing — run --build-books first"
    assert CACHE_DEV.exists(), "runs_dev.pkl missing — run the dev stage first"
    S = pickle.loads(CACHE_BOOKS.read_bytes())
    dev = pickle.loads(CACHE_DEV.read_bytes())
    assert set(dev) == {0, 1, 2, 3}, sorted(dev)
    for s in dev:
        assert set(dev[s]) >= {"REF", "V1", "V2"}, (s, sorted(dev[s]))
    exp_years = [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81), (10.677, 8.27)]
    table_dev = {}
    for v in VARIANTS_DEV:
        if v not in dev[0]:
            continue
        sc = score_variant(dev, v, [0, 1, 2, 3], g1, v388, rm)
        table_dev[v] = dict(
            years_R=sc["years_R"], years_DD=sc["years_DD"],
            years_book_win=sc["years_book_win"], years_rung_win=sc["years_rung_win"],
            years_fills=sc["years_fills"], years_maker=sc["years_maker"],
            years_taker=sc["years_taker"],
            Rdev4=sc["R5"], Wdev4=sc["W"], DDdev4=sc["maxDD"], losing_dev4=sc["losing"],
            fullDD_dev=sc["fullDD"], book_win=sc["book_win"], win_all=sc["win_all"],
            fills=sc["fills"], fees=sc["fees"], funding=sc["funding"],
            maker_tot=sc["maker_tot"], taker_tot=sc["taker_tot"],
            rung_win=sc["rung_win"])
    ref = table_dev["REF"]
    assert ref["years_R"] == [r for r, _ in exp_years], ref["years_R"]
    assert ref["years_DD"] == [d for _, d in exp_years], ref["years_DD"]
    print("REF dev identity OK vs v421 (dev years to the digit)", flush=True)
    pick = robust_pick(table_dev)
    print("DEV4 table:", json.dumps(table_dev, indent=1), flush=True)
    print("PICK (dev4 only):", pick, flush=True)

    out = {"meta": {
        "idea": "IDEAS8 #7 conviction-dependent order TTL (2 bars if |w_base|>q else 1; V1 q=median, V2 q=p75)",
        "harness": ("4-phase engine vs G2 v421 R2B1D17BFG2 (pipe v321, kd=1.7 corr-inv, "
                    "bear books, budget 0.26*1.7, G=2.0, win_start=5, gate costs "
                    "maker 0.0002/taker 0.00055/longs 0.0001 per 8h; flat-branch TTL "
                    "2/1 bars by conviction, one placement, no re-peg, stop-first; "
                    "in-position scale orders uniform n_valid=2; SL/TP unchanged)"),
        "metric": ("reset_metric.year_reset per anchor + v388.mix full-path DD; "
                   "selection on dev years 2021-2024 only; last year POST-HOC scored-once"),
        "rows": {"REF": "G2 unchanged (reproduces v421 to the digit)",
                 "V1": "TTL 2 bars if |w_base|>q50 else 1 (pre-anchor median)",
                 "V2": "TTL 2 bars if |w_base|>q75 else 1 (pre-anchor p75)",
                 "C_V1": "diagnostic uniform-TTL weight trim x s_V1,y=(1+p_V1,y)/2 (in-year realised, not eligible)",
                 "C_V2": "diagnostic uniform-TTL weight trim x s_V2,y=(1+p_V2,y)/2 (in-year realised, not eligible)"},
        "thresholds": {"q50": S["q50"], "q75": S["q75"], "p_V1": S["p_V1"],
                       "p_V2": S["p_V2"], "s_V1": S["s_V1"], "s_V2": S["s_V2"],
                       "anchors": [str(a.date()) for a in ANCH]},
        "pick": pick,
        "costs": {"maker": 0.0002, "taker": 0.00055, "fund_long_8h": 0.0001}},
        "dev": table_dev, "pick": pick}

    if CACHE_LAST.exists():
        last = pickle.loads(CACHE_LAST.read_bytes())
        assert set(last) == {0, 1, 2, 3}, sorted(last)
        have = set(next(iter(last.values())))
        assert have == {"REF", pick}, (have, pick)
        table_last = {}
        for v in ("REF", pick):
            sc = score_variant(last, v, [0, 1, 2, 3, 4], g1, v388, rm)
            table_last[v] = dict(
                years_R=sc["years_R"], years_DD=sc["years_DD"],
                years_book_win=sc["years_book_win"], years_rung_win=sc["years_rung_win"],
                years_fills=sc["years_fills"], years_maker=sc["years_maker"],
                years_taker=sc["years_taker"],
                R5=sc["R5"], W=sc["W"], maxDD=sc["maxDD"], losing=sc["losing"],
                fullDD=sc["fullDD"], book_win=sc["book_win"], win_all=sc["win_all"],
                fills=sc["fills"], fees=sc["fees"], funding=sc["funding"],
                maker_tot=sc["maker_tot"], taker_tot=sc["taker_tot"],
                rung_win=sc["rung_win"],
                Rdev4=round(_geo(sc["years_R"][:4]), 3), Wdev4=min(sc["years_R"][:4]),
                DDdev4=max(sc["years_DD"][:4]), Rlast=sc["years_R"][4])
        assert table_last["REF"]["years_R"][4] == 4.648, table_last["REF"]["years_R"]
        assert table_last["REF"]["years_DD"][4] == 12.9, table_last["REF"]["years_DD"]
        out["last_scored_once"] = table_last
        print("LAST (scored-once) table:", json.dumps(table_last, indent=1), flush=True)
    else:
        print("last stage not run yet (expected before the pick is scored once)", flush=True)
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("wrote results.json", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-books", action="store_true")
    ap.add_argument("--shift", type=int, default=None)
    ap.add_argument("--stage", choices=["dev", "last"], default="dev")
    ap.add_argument("--rows", default="REF,V1,V2,C_V1,C_V2")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()
    if args.validate:
        validate_g2()
        print("validate-only done (no engine run).", flush=True)
        return
    if args.build_books:
        cmd_build_books()
        return
    if args.score:
        cmd_score()
        return
    if args.shift is not None:
        hb = threading.Thread(target=heartbeat,
                              args=(f"run_convttl {args.stage} s{args.shift} {args.rows}",),
                              daemon=True)
        hb.start()
        variants = [r.strip() for r in args.rows.split(",") if r.strip()]
        cache_path = CACHE_LAST if args.stage == "last" else CACHE_DEV
        TMP.mkdir(parents=True, exist_ok=True)
        allres = {}
        if cache_path.exists():
            allres = pickle.loads(cache_path.read_bytes())
            print("loaded cached runs:", {s: sorted(v) for s, v in allres.items()}, flush=True)
        need = [v for v in variants if v not in allres.get(args.shift, {})]
        if not need:
            print(f"shift {args.shift}: all cached, skip", flush=True)
        else:
            s, res = run_shift(args.shift, need, args.stage)
            allres.setdefault(s, {}).update(res)
            cur = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
            cur.update(allres)
            cache_path.write_bytes(pickle.dumps(cur))
            print(f"shift {s} cached ({args.stage})", flush=True)
        _stop_hb.set()
        print("STAGE", args.stage, "DONE shifts", sorted(allres), flush=True)
        return
    raise SystemExit("pass --build-books, --shift S --stage dev|last --rows ..., --score, or --validate")


if __name__ == "__main__":
    main()
