"""v204 blind audit Part A replication.

Blind rule: does NOT read research v204 files, the v204 result json, nor
the v204 pipeline source, until replication.json is saved. Independent
implementation from OPENCODE_V204_AUDIT.md, using
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
as the gate engine base (itself a direct implementation of the AGENTS.md
2026-09-27 user goal, gate cost model and current execution assumptions).
Base: the v199 replication in v199_audit (v151 books, sleeve rung size
x1.5, stop-risk budget 0.12, rung stop 5 sigma_4h, TP 1 sigma_4h, ladder
2.5/3/3.5/4). Run from the repository root so every data path below stays
relative.

A: v197 pipeline (v151 books, sleeve rung size x1.5, stop-risk budget
0.12, rung stop 5 sigma_4h, TP 1 sigma_4h, ladder 2.5/3/3.5/4) with
directional rung sizing: the rung notional per filled rung = rn * m where
m = m_long if the asset book target weight at the decision is > 0 else
m_other; (m_long, m_other) in ((1, 1), (1.5, 0.5), (2, 0)) (m = 0 -> the
rung is not taken); the stop-risk budget sums each open rung own notional
* (5 sigma_4h + 0.02), i.e. risk_open + risk_new <= X with X = 0.12 on
every row. Report dev4, worst first-four-year monthly return, 5y, last
year, gate DD, rungs; selection = robust criterion in AGENTS.md (among
rows with gate DD <= 20 and no losing year in the first four years,
prefer rows with first-four-year mean >= 5 pct/month if any, among them
pick the highest worst-year monthly return of the first four years, ties
-> higher mean). Save replication.json.

Updated conventions adopted from the v188 audit (verified against the
engine source in main via asserts so the audit is self-contained):
  C1 1m-marked DD uses peaks over the minute path (intrabar highs count):
     summarize peaks over maximum(e, eq_max), troughs over minimum(e,
     eq_min) — engine_user.simulate tracks eq_max per bar and summarize
     builds peak1 from maximum(e, ex).
  C2 A stop on the held position wins a same-minute tie with a new book
     fill (the pending order is cancelled): simulate checks the held
     position over minutes [0, fill_min + 1), i.e. seg_end = fill_min + 1,
     and cancels the fill (fills - 1, unfilled + 1) when the held stop/TP
     hits at or before the fill minute.

Frozen engine_user spec (from OPENCODE_V193_AUDIT.md via v193/v197/v198/
v199 audits, re-stated here so the audit is self-contained):
  E1 Inputs: books (pipeline weights), opens (4h opens), 1m klines of the
     majors. Decision bar t is the books index; holding bar T = t + 4h.
  E2 Vol target: realized[t] = 0.8 * sum_j books[t-2,j] *
     (open[t,j]/open[t-1,j] - 1); vol = rolling std 360 (min 120) *
     sqrt(2190); s = min(0.25/vol, 2) (1 if NaN); governor g[t] =
     clip((0.20 - (1 - eq[t-2]/max eq over the 540 bars ending t-2))/0.10,
     0, 1). Live span 2021-09-24 .. +1825 d. Target weight =
     0.8 * s * books[t] * g.
  E3 Quantities q = w / open(T) at bar start (w drifted from previous bar
     end). Order dw = target - w (skip if |dw|*equity*10000 < min notional:
     BTC 100, ETH 20, others 5, unless target is 0 and position is not).
     Limit at open_1m(T, minute 0) * (1 -/+ 0.001), filled at the limit if
     a 1m low (buy) / high (sell) in minutes 2..238 trades through it
     (strict), maker 0.0002; otherwise expires (no fallback).
  E4 Book SL/TP with m = 4 (this audit): sigma_d = std of 360 4h
     open-to-open returns ending at t * sqrt(6); long SL = entry *
     (1 - m sigma_d), TP = entry * (1 + 2 m sigma_d) (short mirrored);
     levels reset at each decision; held position checked from minute 0
     over [0, fill_min + 1) so a held stop wins a same-minute tie with the
     new fill (C2, pending order cancelled); new position checked from the
     fill minute; SL if low <= SL (long), filled at min(SL, minute open),
     taker 0.00055; TP on high > TP (strict), maker 0.0002; both in one
     minute -> SL first; after SL/TP the asset is flat for the rest of the
     bar.
  E5 Funding (gate): a long held at the end of the bar pays 0.0001 of its
     notional if T + 4h is 00/08/16 UTC; shorts 0. No carry sleeve.
  E6 Dip sleeve (v197 setting, directional size per row): rungs k_rung =
     (2.5, 3, 3.5, 4) with sigma_4h (not daily), bid L = open(T)
     (1 - k_rung sigma_4h) live minutes 16..238, maker fill on low < L
     (strict); exits after the fill minute: SL at L (1 - 5 sigma_4h)
     (low <= SL, fill min(SL, open), taker 0.00055), TP at L (1 + sigma_4h)
     (high > TP strict, maker 0.0002), else at open(T+4h) taker paying
     0.0001 if that is a settlement; base per-rung notional
     rn_base = s g 1.5 0.25/4/1.657 via size_mult = 1.5 on every row
     (engine divides by the constant 4, not by the rung count); per filled
     rung rn = rn_base * m with m = m_long if tgt[a] > 0 else m_other
     (engine align branch, tgt = 0.8 s B g at the decision, decision-known;
     m = 0 -> rung skipped); fills taken in (ladder, rung, asset) order
     iff risk_open + risk_new <= X where risk = own rn *
     (5 sigma_4h(asset) + 0.02) summed over taken rungs still open at the
     fill minute (exit > f); X = 0.12 on every row.
  E7 1m-marked equity per minute = start equity * (1 + position MTM +
     sleeve MTM); gate DD = max(4h-close DD, 1m-marked DD) with the 1m leg
     peaking over the minute path (C1); per anchor year net/monthly;
     monthly_dev4 = geometric mean of the first four anchor years
     (monthly % = 100 * ((1+geo) ** (1/12) - 1)); worst_first4 = min of the
     first-four yearly monthly_pct.
  E8 Rows: P2 = (A+B)/2 with sleeve on, m = 4, sleeve SL k = 5, book limit
     (d, W) = (0.001, 239), target 0.25, cap 2.0, gap 0.02, size_mult 1.5,
     X = 0.12, ladder (2.5, 3, 3.5, 4) on every row, align in
     ((1, 1), (1.5, 0.5), (2, 0)); selection = robust criterion (AGENTS.md
     2026-09-27, v204 on): among rows with gate DD <= 20 and no losing
     year in the first four anchor years, prefer rows with monthly_dev4
     >= 5 if any, among them pick the highest worst_first4, ties -> higher
     monthly_dev4.

Leakage notes (checked in code, reported in COMPARISON.md Part B):
  L1 Feature timing: pipeline books at t, opens at t/t-1, sigma windows
     ending at t, s/g known at the decision; cubes row i = holding bar T;
     the align multiplier uses tgt[a] = 0.8 s B[t] g at the decision only
     (engine_user.py align branch reads tgt[a] computed at i), so the book
     direction used is known at the decision.
  L2 No label window: no forward return is read except through fills and
     the bar-close settlement/exit prices at T/T+4h.
  L3 Fit windows: member books are pre-fit causal inputs; no statistic is
     fit on any test year inside this script (vol/governor are running
     causal filters; selection uses first-four-years metrics only; aligns
     ((1,1), (1.5,0.5), (2,0)) with fixed per-rung base and X = 0.12 were
     pre-registered, not tuned).
  L4 Fill timing: book limit minutes 2..238 strict trade-through, held
     SL/TP from minute 0 with stop-wins-tie over [0, fill_min + 1) and
     stop-first within a minute, sleeve trigger 16..238 and exits strictly
     after the fill minute.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2") / "v204_audit"
OUT = AUD / "replication.json"
CACHE = Path("artifacts/research/engine_real")
OPENS_FILE = CACHE / "opens_v154.parquet"
BOOKS_FILE = CACHE / "books_v154.parquet"
MEMBERS_FILE = CACHE / "members_v154.parquet"

M_SL = 4.0
M_SLEEVE_SL = 5.0
M_SLEEVE_TP = 1.0
D_LIMIT = 0.001
WIN_END = 239
GAP = 0.02
TARGET = 0.25
CAP = 2.0
SIZE_MULT = 1.5
SLEEVE_X = 0.12
RUNGS = (2.5, 3.0, 3.5, 4.0)
ALIGNS = {
    "ALIGN_11": (1.0, 1.0),
    "ALIGN_150_05": (1.5, 0.5),
    "ALIGN_20": (2.0, 0.0),
}


def _load_engine_user():
    spec = importlib.util.spec_from_file_location(
        "v204_audit_engine_user",
        Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def robust_selection(rows):
    eligible = {k: v for k, v in rows.items()
                if v["gate_dd"] <= 20 and v["losing_years_first4"] == 0}
    pool = [k for k in eligible if eligible[k]["monthly_dev4"] >= 5]
    if not pool:
        pool = list(eligible)
    if not pool:
        return None
    return max(pool, key=lambda k: (eligible[k]["worst_first4"], eligible[k]["monthly_dev4"]))


def main():
    eu = _load_engine_user()
    print(f"engine_user maker={eu.MAKER} taker={eu.TAKER} fund_long={eu.FUND_LONG}", flush=True)
    assert eu.MAKER == 0.0002 and eu.TAKER == 0.00055 and eu.FUND_LONG == 0.0001
    assert eu.D_LIMIT == 0.001 and eu.SIZE == 0.25 and eu.S_REF == 1.657
    assert tuple(eu.RUNGS) == (2.5, 3.0, 3.5, 4.0)

    # C1/C2: verify the two v188 conventions are present in this engine.
    sim_src = inspect.getsource(eu.simulate)
    sum_src = inspect.getsource(eu.summarize)
    assert "fill_min + 1" in sim_src, "C2 stop-wins-tie (seg_end = fill_min + 1) missing"
    assert "eq_max" in sim_src, "C1 eq_max minute-peak tracking missing"
    assert "peak1" in sum_src, "C1 minute-path peak (peak1) missing in summarize"
    assert "np.maximum(e, ex)" in sum_src, "C1 minute-path peak over maximum(e, ex) missing"
    # Align branch: directional rung sizing uses decision-known tgt[a].
    assert "align" in sim_src, "align directional sizing branch missing"
    assert "tgt[a] > 0" in sim_src, "align book-direction check (tgt[a] > 0) missing"
    print("conventions C1 (minute-path DD peaks) and C2 (held stop wins fill tie) verified; align branch verified", flush=True)

    mem = pd.read_parquet(MEMBERS_FILE)
    books_cache = pd.read_parquet(BOOKS_FILE)
    assert set(mem.columns.get_level_values(0).unique()) >= {"A", "B", "D"}
    A_m = mem["A"]
    B_m = mem["B"]
    D_m = mem["D"]
    avg = (A_m + B_m + D_m) / 3
    max_abs_diff = float((avg - books_cache).abs().max().max())
    print(f"members check max abs diff (A+B+D)/3 vs books_v154 = {max_abs_diff}", flush=True)
    assert max_abs_diff == 0.0, f"members average mismatch {max_abs_diff}"
    union_bars = int(len(A_m.index.union(B_m.index).union(D_m.index)))
    print(f"members union bars = {union_bars}", flush=True)

    idx_union = A_m.index.union(B_m.index).union(D_m.index).sort_values()
    cols = list(books_cache.columns)
    Au = A_m.reindex(idx_union).reindex(columns=cols).fillna(0.0)
    Bu = B_m.reindex(idx_union).reindex(columns=cols).fillna(0.0)
    P2 = ((Au + Bu) / 2).sort_index()
    assert list(P2.index) == list(books_cache.index)
    assert list(P2.columns) == cols

    opens = pd.read_parquet(OPENS_FILE).sort_index()
    print(f"pipeline P2 {P2.shape} opens {opens.shape}", flush=True)

    prep = eu.prepare(P2, opens)
    print(f"prepared cubes O {prep['O'].shape}", flush=True)

    rows = {}
    for key, align in ALIGNS.items():
        print(f"simulate {key} align={align} size_mult={SIZE_MULT} X={SLEEVE_X} rungs={RUNGS} ...", flush=True)
        out = eu.simulate(
            P2, opens, prep,
            m_sl=M_SL, m_sleeve_sl=float(M_SLEEVE_SL),
            sleeve=True, target=float(TARGET), cap=float(CAP),
            d_limit=float(D_LIMIT), win_end=int(WIN_END),
            sleeve_risk_budget=float(SLEEVE_X), gap=float(GAP),
            m_sleeve_tp=float(M_SLEEVE_TP),
            size_mult=float(SIZE_MULT),
            rungs=tuple(RUNGS),
            align=tuple(align),
        )
        yearly = out["yearly"]
        assert [y["anchor"] for y in yearly] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
        first4 = yearly[:4]
        losing_first4 = sum(1 for y in first4 if y["net_pct"] < 0)
        geo4 = float(np.prod([1 + y["net_pct"] / 100 for y in first4]) ** (1 / 4) - 1)
        dev4_check = round(100 * ((1 + geo4) ** (1 / 12) - 1), 3)
        assert abs(dev4_check - out["monthly_dev4"]) < 0.002, (key, dev4_check, out["monthly_dev4"])
        assert abs(out["gate_dd"] - max(out["dd_4h"], out["dd_1m"])) < 1e-9, key
        worst_first4 = round(min(y["monthly_pct"] for y in first4), 3)
        rows[key] = {
            "pipeline": "P2",
            "books": "v151=(A+B)/2",
            "sleeve": True,
            "m_sl": M_SL,
            "m_sleeve_sl": float(M_SLEEVE_SL),
            "m_sleeve_tp_mult": float(M_SLEEVE_TP),
            "d_limit": float(D_LIMIT),
            "win_end": int(WIN_END),
            "target": float(TARGET),
            "cap": float(CAP),
            "size_mult": float(SIZE_MULT),
            "mult": float(SIZE_MULT),
            "sleeve_risk_budget": float(SLEEVE_X),
            "gap": float(GAP),
            "rungs": list(RUNGS),
            "align": list(align),
            "m_long": float(align[0]),
            "m_other": float(align[1]),
            "rung_notional": "rn_base * m via size_mult = 1.5 then align m (m_long if tgt>0 else m_other); risk per open rung = own rn * (5 sigma_4h + 0.02)",
            "monthly_dev4": out["monthly_dev4"],
            "worst_first4": worst_first4,
            "monthly_5y": out["monthly_5y"],
            "monthly_last_year": out["monthly_last_year"],
            "yearly": yearly,
            "yearly_net_pct": [y["net_pct"] for y in yearly],
            "yearly_monthly_pct": [y["monthly_pct"] for y in yearly],
            "yearly_dd_1m_pct": [y["dd_1m_pct"] for y in yearly],
            "losing_years": out["losing_years"],
            "losing_years_first4": losing_first4,
            "dd_4h": out["dd_4h"],
            "dd_1m": out["dd_1m"],
            "gate_dd": out["gate_dd"],
            "gate_pass": out["gate_pass"],
            "stats": out["stats"],
        }
        print(f"{key}: dev4={out['monthly_dev4']} worst4={worst_first4} 5y={out['monthly_5y']} "
              f"last={out['monthly_last_year']} gateDD={out['gate_dd']} "
              f"lose={out['losing_years']} lose4={losing_first4} "
              f"nets={[y['net_pct'] for y in yearly]} "
              f"rungs={out['stats']['rungs']} rung_stops={out['stats']['rung_stops']} "
              f"rung_tps={out['stats']['rung_tps']} liq={out['stats']['liq']}", flush=True)

    eligible = {k: v for k, v in rows.items()
                if v["gate_dd"] <= 20 and v["losing_years_first4"] == 0}
    selection = robust_selection(rows)
    print(f"eligible {sorted(eligible)} selection {selection}", flush=True)

    replication = {
        "version": "v204_audit_replication",
        "blind": "did_not_open_research_v204_until_this_file_saved",
        "books": "v151=(A+B)/2 from cached v154 members; v197 pipeline with directional rung size (align)",
        "members_check": {
            "file": "artifacts/research/engine_real/members_v154.parquet",
            "books_file": "artifacts/research/engine_real/books_v154.parquet",
            "opens_file": "artifacts/research/engine_real/opens_v154.parquet",
            "max_abs_diff_avg_vs_books": max_abs_diff,
            "union_bars": union_bars,
            "columns": cols,
        },
        "engine": {
            "file": "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py",
            "maker": eu.MAKER,
            "taker": eu.TAKER,
            "d_limit": float(D_LIMIT),
            "win_end": int(WIN_END),
            "fund_long": eu.FUND_LONG,
            "default_rungs": list(eu.RUNGS),
            "size": eu.SIZE,
            "s_ref": eu.S_REF,
            "m_sl": M_SL,
            "m_sleeve_sl": float(M_SLEEVE_SL),
            "m_sleeve_tp_mult": float(M_SLEEVE_TP),
            "target": float(TARGET),
            "cap": float(CAP),
            "gap": float(GAP),
            "size_mult": float(SIZE_MULT),
            "sleeve_risk_budget": float(SLEEVE_X),
            "rungs": list(RUNGS),
            "rung_notional": "rn_base = s * g * 1.5 * 0.25/4/1.657 via size_mult = 1.5; per filled rung rn = rn_base * m (align)",
            "conventions": [
                "C1 1m-marked DD peaks over the minute path (intrabar highs count)",
                "C2 held-position stop wins a same-minute tie with a new book fill (pending order cancelled)",
            ],
        },
        "rows": rows,
        "aligns": {k: list(v) for k, v in ALIGNS.items()},
        "selection_rule": "robust criterion (AGENTS.md 2026-09-27, v204 on): among rows with gate_dd <= 20 and no losing year in the first four years, prefer rows with monthly_dev4 >= 5 if any, among them pick the highest worst_first4, ties -> higher monthly_dev4",
        "eligible": sorted(eligible),
        "selection": selection,
    }
    AUD.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print(f"saved {OUT}", flush=True)


if __name__ == "__main__":
    main()
