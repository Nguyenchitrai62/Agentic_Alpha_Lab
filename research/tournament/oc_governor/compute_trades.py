"""oc_governor trade diagnostics (DISCLOSED extra, post-outcome): SAME frozen configs.

Captures events/stats for G2REF + GV3 (full window) for per-year trade counts
and win rates. Events capture has no effect on results (engine docstring); the
script asserts equity bit-identical to the already-scored tmp/engine_*.pkl and
does NOT re-score anything.

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_governor --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_governor/compute_trades.py
"""
from __future__ import annotations

import importlib.util
import json
import pickle
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parents[1] / "parallel" / "rounds" / "parallel-20260906-r2"
ROOT = HERE.parents[2]
TABLES = RD / "v376" / "tables_hidden"
ROWS = ("G2REF", "GV3")
KD = 1.7


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podgovt_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histgovt_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_govt_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwgovt_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    v388 = _load(f"v388govt_{shift}", RD / "v388/v388_bot_stop_distance.py")
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy(), stats=dict(stats)) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, v388.Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _opens_std = eu.er.v154_books()
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    sys.path.insert(0, str(ROOT / "research/tournament/oc_governor"))
    from compute_engine import pooled_g_from_stored
    pg = pooled_g_from_stored()
    out = {}
    for name in ROWS:
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
            return (1.0 / (1 + n)) * KD * base_size(i, a, r, f)

        kw["sleeve_fill_size"] = corr_size
        kw["sleeve_risk_budget"] = 0.26 * KD
        kw["sleeve_gross_cap"] = 2.0
        sim_kw = dict(kw)
        if name == "GV3":
            garr = pg[shift]
            sim_kw["gov"] = (1.0, 1e-9)
            sim_kw["risk_mult"] = lambda i, e, garr=garr: float(garr[i]) if i < len(garr) else 1.0
        else:
            sim_kw["risk_mult"] = lambda i, e: 1.0
        ev = []
        eu.simulate(books_bear, opens, prep, trade=trade, win_start=5, events=ev, **sim_kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        bw = pof.book_win(v221, ev, live0, live1)
        # per anchor-year book trades: count order-closes via events kinds per year
        years = {}
        for y, a0 in enumerate(("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")):
            a = pd.Timestamp(a0, tz="UTC")
            seg = [e for e in ev if a <= pd.Timestamp(e["t"]) < a + pd.Timedelta(days=365)]
            nb = sum(1 for e in seg if e["kind"] in ("book_stop", "book_tp", "book_close", "book_reduce", "book_partial"))
            nr = [float(e["ret"]) for e in seg if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout")]
            years[y] = dict(book_exits=nb, rungs=len(nr),
                            rung_win=round(float(np.mean(np.array(nr) > 0)), 4) if nr else None)
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                         eq=(cap["eq"][lv] / base).tolist(),
                         eq_min=(cap["eq_min"][lv] / base).tolist(),
                         stats={k: (round(float(v), 6) if isinstance(v, float) else v)
                                for k, v in cap["stats"].items()},
                         book_win=bw, per_year=years)
        print(f"shift {shift} {name}: eq_end {out[name]['eq'][-1]:.3f} "
              f"book {bw['book_trades']}@{bw['book_win']} rungs {bw['nr'] if 'nr' in bw else bw.get('rungs')}", flush=True)
    return shift, out


def main():
    t_start = time.time()
    with Pool(2) as pool:
        runs = dict(pool.map(worker, range(4)))
    print(f"done in {(time.time() - t_start) / 60:.1f} min", flush=True)
    # bit-identity vs scored runs (dev stitch + full)
    dev = pickle.loads((HERE / "tmp" / "engine_dev.pkl").read_bytes())
    full = pickle.loads((HERE / "tmp" / "engine_full.pkl").read_bytes())
    ok = True
    for s in range(4):
        # GV3: fresh full eq vs dev+full stitch of the scored runs
        d, f = dev[s]["GV3"], full[s]["GV3"]
        td = pd.to_datetime(d["t"], utc=True)
        tf = pd.to_datetime(f["t"], utc=True)
        cut = td.max()
        expect = list(d["eq"]) + [e for e, t in zip(f["eq"], tf) if t > cut]
        got = runs[s]["GV3"]["eq"]
        same = len(got) == len(expect) and np.array_equal(np.asarray(got), np.asarray(expect))
        print(f"shift {s} GV3 bit-identical to scored runs: {same}", flush=True)
        ok = ok and same
    (HERE / "tmp" / "trades.pkl").write_bytes(pickle.dumps(runs))
    (HERE / "tmp" / "trades_check.json").write_text(json.dumps(dict(bit_identical=bool(ok)), indent=1))
    print("wrote tmp/trades.pkl", flush=True)


if __name__ == "__main__":
    main()
