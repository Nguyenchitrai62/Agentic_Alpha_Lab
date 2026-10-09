"""oc_booktwo engine: 4-phase G2 (v421 R2B1D17BFG2) with a two-rung book entry ladder.

Frozen definitions in PLAN.md (IDEAS6 #7). REF = G2 bit-exact; V1/V2 replace
ONLY the flat-branch new-order single limit with two fixed rungs
(10bps + 25bps; V1 50/50, V2 70/30), fill window [5,65) strict trade-through,
minute-5 ban, unfilled expire, SL/TP from the average entry with the same
sd/multiples, then G2 in-position management unchanged.

Usage (all heavy via the shared semaphore, one job at a time):
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_booktwo --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_booktwo/run_engine.py --validate
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_booktwo --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_booktwo/run_engine.py --stage dev --shifts 0,1,2,3 --rows REF,V1,V2
  (then, after the dev4 pick in analyze.py, scored-once last stage for REF + pick only)

Resume-safe caches: tmp/runs_dev.pkl, tmp/runs_last.pkl. Heartbeat every 600 s.
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
V421 = RD / "v421"
TMP = HERE / "tmp"
CACHE_DEV = TMP / "runs_dev.pkl"
CACHE_LAST = TMP / "runs_last.pkl"

sys.path.insert(0, str(HERE))
import booktwo as bt  # noqa: E402

DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
DEV1 = pd.Timestamp("2025-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
HEARTBEAT_S = 600
W0, W1 = 5, 65

_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print(f"[hb {datetime.now(timezone.utc):%H:%M:%S}Z] {tag} alive", flush=True)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# Ladder patch (flat-branch new-order single limit -> two fixed rungs)
# --------------------------------------------------------------------------
OLD_ISSUE = '            if ps == 0 and sgn != 0 and size > 0 and size * prev_eq * ACCOUNT >= mins[a] and np.isfinite(sd_a) and np.isfinite(s4_a):'

LADDER_SRC = '''
            if ps == 0 and sgn != 0 and size > 0 and size * prev_eq * ACCOUNT >= mins[a] and np.isfinite(sd_a) and np.isfinite(s4_a):
                _w1, _w2 = bt.split_weights(size, __VARIANT__)
                _px1 = Oa[0] * (1 - sgn * 0.001)
                _px2 = Oa[0] * (1 - sgn * 0.0025)
                T["risk"][a] = r_new
                T["psd"][a], T["issued"][a] = sd_a, i
                T["exp"][a] = i + 1
                stats["issued"] += 2
                _ev(i, a, 0, "order_issue", "buy" if sgn > 0 else "sell", _px1, sgn * _w1, offset=0.001, rung="ladder10")
                _ev(i, a, 0, "order_issue", "buy" if sgn > 0 else "sell", _px2, sgn * _w2, offset=0.0025, rung="ladder25")
                ps = sgn
                _f1 = _f2 = False
                _e = float("nan")
                _sl = _tp = float("nan")
                _q = 0.0
                _mexit = None
                _mkind = None
                for _m in range(5, min(65, 240)):
                    if _mexit is not None:
                        break
                    if not _f1 and np.isfinite(_px1):
                        _hit1 = La[_m] < _px1 * (1 - ft) if sgn > 0 else Ha[_m] > _px1 * (1 + ft)
                        if bool(_hit1):
                            _f1 = True
                            _dq1 = sgn * _w1 / _px1
                            carr[_m:] -= _dq1 * _px1 + abs(_dq1) * _px1 * MAKER
                            stats["fees"] += abs(_dq1) * _px1 * MAKER
                            stats["fills"] += 1
                            _q += _dq1
                            qarr[_m:] = _q
                            _ev(i, a, _m, "book_fill", "buy" if sgn > 0 else "sell", _px1, sgn * _w1, entry_type="limit ladder10", issued_bars_ago=0)
                    if not _f2 and np.isfinite(_px2):
                        _hit2 = La[_m] < _px2 * (1 - ft) if sgn > 0 else Ha[_m] > _px2 * (1 + ft)
                        if bool(_hit2):
                            _f2 = True
                            _dq2 = sgn * _w2 / _px2
                            carr[_m:] -= _dq2 * _px2 + abs(_dq2) * _px2 * MAKER
                            stats["fees"] += abs(_dq2) * _px2 * MAKER
                            stats["fills"] += 1
                            _q += _dq2
                            qarr[_m:] = _q
                            _ev(i, a, _m, "book_fill", "buy" if sgn > 0 else "sell", _px2, sgn * _w2, entry_type="limit ladder25", issued_bars_ago=0)
                    if _f1 or _f2:
                        _ws = (_w1 if _f1 else 0.0) + (_w2 if _f2 else 0.0)
                        _qq = (_w1 / _px1 if _f1 else 0.0) + (_w2 / _px2 if _f2 else 0.0)
                        _e = float(_ws / _qq) if _qq else float("nan")
                        _mt = 2 * m_sl if m_tp is None else m_tp
                        _sl, _tp = _e * (1 - sgn * m_sl * sd_a), _e * (1 + sgn * _mt * sd_a)
                        _hit_s = (La[_m] <= _sl) if sgn > 0 else (Ha[_m] >= _sl)
                        _hit_t = (Ha[_m] > _tp * (1 + ft)) if sgn > 0 else (La[_m] < _tp * (1 - ft))
                        if bool(_hit_s):
                            _pxx = min(_sl, Oa[_m]) if sgn > 0 else max(_sl, Oa[_m])
                            carr[_m:] += _q * _pxx - abs(_q) * _pxx * TAKER
                            stats["fees"] += abs(_q) * _pxx * TAKER
                            stats["stops"] += 1
                            _ev(i, a, _m, "book_stop", "sell" if sgn > 0 else "buy", _pxx, -_q * _pxx / (prev_eq if prev_eq else 1.0))
                            qarr[_m:] = 0.0
                            _q = 0.0
                            _mexit, _mkind = _m, "stop"
                        elif bool(_hit_t):
                            carr[_m:] += _q * _tp - abs(_q) * _tp * MAKER
                            stats["fees"] += abs(_q) * _tp * MAKER
                            stats["tps"] += 1
                            _ev(i, a, _m, "book_tp", "sell" if sgn > 0 else "buy", _tp, -_q * _tp / (prev_eq if prev_eq else 1.0))
                            qarr[_m:] = 0.0
                            _q = 0.0
                            _mexit, _mkind = _m, "tp"
                if _mexit is not None:
                    T["sl"][a] = T["tp"][a] = np.nan
                    T["risk"][a] = 0.0
                    T["side"][a] = 0
                    T["ak"][a] = 0
                    stats["expired"] += int(not _f1) + int(not _f2)
                    return carr, qarr, 0.0, np.nan
                if not _f1 and not _f2:
                    T["side"][a] = 0
                    T["risk"][a] = 0.0
                    stats["unfilled"] += 1
                    stats["expired"] += 2
                    _ev(i, a, 65, "order_expire", "buy" if sgn > 0 else "sell", _px1, 0.0, rung="ladder10")
                    _ev(i, a, 65, "order_expire", "buy" if sgn > 0 else "sell", _px2, 0.0, rung="ladder25")
                    return carr, qarr, 0.0, np.nan
                if not _f1 or not _f2:
                    stats["expired"] += int(not _f1) + int(not _f2)
                    _ev(i, a, 65, "order_expire", "buy" if sgn > 0 else "sell", _px1 if not _f1 else _px2, 0.0, rung=("ladder10" if not _f1 else "ladder25"))
                cur_q, cur_e = _q, _e
                sdv = sd_a
                mt = 2 * m_sl if m_tp is None else m_tp
                T["sl"][a], T["tp"][a], T["sd"][a] = _sl, _tp, sdv
                T["be"][a] = T["part"][a] = False
                T["side"][a] = 0
                T["w"][a] = (_w1 if _f1 else 0.0) + (_w2 if _f2 else 0.0)
                T["ak"][a], T["nadd"][a], T["nred"][a] = 0, 0, 0
                T["open_i"][a] = T["last_adj"][a] = i
                m0 = 65
'''

OLD_FILL_TAIL = '''            if ps == 0:
                return carr, qarr, 0.0, np.nan
            px = T["px"][a]
            hit = La[start:240] < px * (1 - ft) if ps > 0 else Ha[start:240] > px * (1 + ft)
            if not hit.any():
                return carr, qarr, 0.0, np.nan
            m0 = start + int(np.argmax(hit))
            dq = ps * T["w"][a] / px
            carr[m0:] -= dq * px + abs(dq) * px * MAKER
            stats["fees"] += abs(dq) * px * MAKER
            stats["fills"] += 1
            qarr[m0:] = dq
            cur_q, cur_e = dq, px
            sdv = T["psd"][a]
            mt = 2 * m_sl if m_tp is None else m_tp
            T["sl"][a], T["tp"][a], T["sd"][a] = px * (1 - ps * m_sl * sdv), px * (1 + ps * mt * sdv), sdv
            T["be"][a] = T["part"][a] = False
            T["side"][a] = 0
            T["ak"][a], T["nadd"][a], T["nred"][a] = 0, 0, 0
            T["open_i"][a] = T["last_adj"][a] = i
            _ev(i, a, m0, "book_fill", "buy" if ps > 0 else "sell", px, ps * T["w"][a], entry_type="limit", sl=float(T["sl"][a]),
                tp=float(T["tp"][a]), issued_bars_ago=int(i - T["issued"][a]))
'''


def make_simulate(eu, variant: str):
    """eu.simulate with the ladder entry for V1/V2 (REF = unpatched, bit-exact)."""
    if variant == "REF":
        return eu.simulate
    src = inspect.getsource(eu.simulate)
    assert src.count(OLD_ISSUE) == 1, "entry anchor not unique"
    assert src.count(OLD_FILL_TAIL) == 1, "fill-tail anchor not found"
    patched = src.replace(OLD_ISSUE, LADDER_SRC.replace("__VARIANT__", repr(variant)))
    # remove the now-dead single-fill tail (ps==0 return + px/hit/m0 block)
    patched = patched.replace(OLD_FILL_TAIL, '            m0 = 65\n')
    g = eu.simulate.__globals__  # live dict (audited oc_idea5_manualrest pattern): sees eu.summarize override
    g["bt"] = bt
    ns: dict = {}
    exec(patched, g, ns)  # noqa: S102 - audited pattern (cf. oc_idea5_manualrest)
    fn = ns.get("simulate")
    if fn is None:  # pragma: no cover
        raise RuntimeError("patched simulate missing")
    fn._patched_src = patched
    return fn


def validate_g2() -> None:
    runs = pickle.loads((V421 / "v421_runs.pkl").read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    exp = json.loads((V421 / "v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    v388 = pof._load("v388_bt_val", RD / "v388/v388_bot_stop_distance.py")
    rm = pof._load("reset_bt_val", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    strat = "R2B1D17BFG2"
    got_r, got_dd = [], []
    for y in range(5):
        m = rm.year_reset(runs, strat, y)
        got_r.append(m["R"])
        got_dd.append(m["DD"])
    assert got_r == [r for r, _ in exp["years"]], (got_r, exp["years"])
    assert got_dd == [d for _, d in exp["years"]], (got_dd, exp["years"])
    R5 = round(float(np.prod([1 + r / 100 for r in got_r]) ** (1 / 5) - 1) * 100, 3)
    assert R5 == exp["R"] and min(got_r) == exp["W"] and max(got_dd) == exp["DD"], (R5, exp)
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(runs, strat, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    assert full == exp["full_path_dd"], (full, exp["full_path_dd"])
    print(f"G2 validation OK: R {R5} / W {min(got_r)} / DD {max(got_dd)} / full {full}", flush=True)


def run_shift(shift: int, variants: list[str], stage: str):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    tag = f"{stage}_s{shift}"
    pod = pof._load(f"pod_bt_{stage}_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_bt_{stage}_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_bt_{stage}_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_bt_{stage}_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}

    def _summ(idx, net, eq, eq_min, g, stats, eq_max=None):
        cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
                   eq_max=(eq if eq_max is None else eq_max).copy(), stats=dict(stats))

    eu.summarize = _summ
    sh = pd.Timedelta(hours=shift)
    last = (stage == "last")
    live0 = DEV0 + sh
    live1 = (Y1 if last else DEV1) + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _opens_std = eu.er.v154_books()
    std_idx = books154.index if last else books154.index[books154.index <= DEV1 + pd.Timedelta(hours=4)]
    cols = list(books154.columns)
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, std_idx + sh, shift, cols)
    del M
    gc.collect()
    idx, cols = prep["idx"], list(prep["cols"])
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    books = std_books.reindex(idx, method="ffill").fillna(0.0)
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"

    out = {}
    for variant in variants:
        t0 = time.time()
        sim = make_simulate(eu, variant)
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size = kw["sleeve_fill_size"]

        def corr_size(i, a, r, f, base_size=base_size):
            m = f - 1
            n = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                    continue
                n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            return (1.0 / (1 + n)) * 1.7 * base_size(i, a, r, f)

        kw["sleeve_fill_size"] = corr_size
        kw["risk_mult"] = lambda i, e: 1.0
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * 1.7
        kw["sleeve_gross_cap"] = 2.0
        ev: list = []
        sim(books_bear, opens, prep, trade=trade, win_start=5, events=ev, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        run = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                   eq=(cap["eq"][lv] / base).tolist(),
                   eq_min=(cap["eq_min"][lv] / base).tolist())
        years = []
        for y, a in enumerate(ANCH5):
            if not last and y == 4:
                years.append(dict(nb=0, wb=0, nr=0, wr=0, nfill=0))
                continue
            a0 = pd.Timestamp(a, tz="UTC") + sh
            a1 = min(a0 + pd.Timedelta(days=365), live1)
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
        st = cap.get("stats", {})
        out[variant] = dict(run=run, wins=years,
                            stats={k: (float(v) if isinstance(v, float) else v) for k, v in st.items()})
        print(f"{tag} {variant} eq_end={run['eq'][-1]:.4f} elapsed={(time.time() - t0) / 60:.1f}min", flush=True)
        del ev
        gc.collect()
    del opens, prep, books
    gc.collect()
    return shift, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--stage", choices=["dev", "last"], default="dev")
    ap.add_argument("--shifts", default="0,1,2,3")
    ap.add_argument("--rows", default="REF,V1,V2")
    args = ap.parse_args()
    validate_g2()
    if args.validate:
        print("validate-only done (no engine run).", flush=True)
        return
    shifts = [int(s) for s in args.shifts.split(",")]
    variants = [r.strip() for r in args.rows.split(",") if r.strip()]
    hb = threading.Thread(target=heartbeat, args=(f"run_engine {args.stage} {args.rows}",), daemon=True)
    hb.start()
    cache_path = CACHE_LAST if args.stage == "last" else CACHE_DEV
    TMP.mkdir(parents=True, exist_ok=True)
    allres = {}
    if cache_path.exists():
        allres = pickle.loads(cache_path.read_bytes())
        print("loaded cached runs:", {s: sorted(v) for s, v in allres.items()}, flush=True)
    # REF identity: must reproduce v421 stored runs on every shift (checked in analyze.py too)
    for shift in shifts:
        need = [v for v in variants if v not in allres.get(shift, {})]
        if not need:
            print(f"shift {shift}: all cached, skip", flush=True)
            continue
        s, res = run_shift(shift, need, args.stage)
        allres.setdefault(s, {}).update(res)
        cur = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
        cur.update(allres)
        cache_path.write_bytes(pickle.dumps(cur))
        print(f"shift {s} cached ({args.stage})", flush=True)
    _stop_hb.set()
    print("STAGE", args.stage, "DONE shifts", sorted(allres), flush=True)


if __name__ == "__main__":
    main()
