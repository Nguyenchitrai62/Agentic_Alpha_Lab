"""Dev-only diagnostic (not a registered version): the deployed pipelines v367 (M5) and v321 (R2) on 4h grids shifted by s h WITH the learned dip
agents, using the R2 decision table rebuilt on that grid (build_tables.py: same per-anchor models, state at the shifted bar open).
Everything else is research/diagnostics/phase_offset_full/phase_offset_full.py main(shift, "dev") unchanged (prep_idx, forward-filled standard
books, settle flags, pipe_setup with agents=True keyed by the shifted holding bars, metrics, book_win). At s = 0 also the deployed table
(artifacts/.../v321_r2_table_m0.parquet) as a reproduction check (must give v367 6.018 / v321 7.080).
Dev years only (2021-09-24 .. 2025-09-23 + s h). Nothing is selected or tuned.
Usage: replay_agents.py <shift>  -> runs/dev_s<shift>.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
import phase_offset_full as pof  # noqa: E402

PIPES = ("v367", "v321")


def main(shift):
    t_start = time.time()
    pod = pof._load("pod_pa", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load("history_tm_pa", ROOT / "backend/history_tm.py")
    v221 = pof._load("v221_pa", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load("forward_v205_pa", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
                                                                                 eq_max=(eq if eq_max is None else eq_max).copy(), stats=stats) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, pof.DEV1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    std_idx = books154.index[books154.index <= pof.DEV1 + pd.Timedelta(hours=4)]
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, std_idx + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    books = std_books.reindex(idx, method="ffill").fillna(0.0)
    tables = [("full_agents_rebuilt", HERE / "tables" / f"r2_table_s{shift}.parquet")]
    if shift == 0:
        tables.insert(0, ("full_agents_deployed", hist.R2_TABLE))
    # coverage: every holding bar of the replay has a row in the rebuilt table
    tab = pd.read_parquet(tables[-1][1])
    hold = pd.Index(idx + pd.Timedelta(hours=4))
    hold_live = hold[(idx >= live0) & (idx < live1)]
    cover = float(pd.Index(hold_live).isin(pd.Index(tab["T"].unique())).mean())
    runs = []
    for pipe in PIPES:
        for tag, path in tables:
            t0 = time.time()
            hist.R2_TABLE = path
            kw, trade = pof.pipe_setup(pipe, hist, v221, v216, idx, cols, True)
            events = []
            eu.simulate(books, opens, prep, trade=trade, win_start=5, events=events, **kw)
            m = pof.metrics(cap["idx"], cap["eq"], cap["eq_min"], cap["eq_max"], pof.ANCH, live0, live1, sh)
            g4 = np.prod([1 + y["net_pct"] / 100 for y in m["yearly"]]) ** (1 / 4)
            m["monthly_dev4"] = round(100 * (g4 ** (1 / 12) - 1), 3)
            m.update(pof.book_win(v221, events, live0, live1))
            m["stats"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in cap["stats"].items()}
            sz = [e for e in events if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and live0 <= pd.Timestamp(e["t"]) < live1 + pd.Timedelta(hours=8)]
            eq_end = pd.Series(cap["eq"], index=cap["idx"] + pd.Timedelta(hours=8))
            eq_end = eq_end[(cap["idx"] >= live0 - pd.Timedelta(hours=4)) & (cap["idx"] < live1)]
            runs.append(dict(pipe=pipe, tag=tag, table=str(path), shift=shift, period="dev", table_cover=cover, **m,
                             eq_end={str(k): float(v) for k, v in eq_end.items()}))
            print(pipe, tag, "s", shift, m["monthly_dev4"], [y["net_pct"] for y in m["yearly"]], "DD1m", m["dd_1m"], "bookwin", m["book_win"],
                  "allwin", m["win_all"], "rungs", len(sz), f"cover {cover:.4f}", f"{time.time() - t0:.0f}s", flush=True)
    (HERE / "runs").mkdir(exist_ok=True)
    meta = dict(shift_h=shift, live=[str(live0), str(live1)], bars=len(idx), table_cover=cover, secs=round(time.time() - t_start))
    (HERE / "runs" / f"dev_s{shift}.json").write_text(json.dumps(dict(meta=meta, runs=runs), default=str))


if __name__ == "__main__":
    main(int(sys.argv[1]))
