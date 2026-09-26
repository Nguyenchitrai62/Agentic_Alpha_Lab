"""v200 + v201 blind audit Part A replication.

Blind rule: does NOT read research v200 files, v201 files, the v200/v201
result jsons, nor the v200/v201 pipeline sources, until replication.json is
saved. Independent implementation from OPENCODE_V200_V201_AUDIT.md, using
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
as the gate engine base (itself a direct implementation of the AGENTS.md
2026-09-27 user goal, gate cost model and current execution assumptions).
Base: the v199 replication in v199_audit (v197 pipeline, v151 books,
sleeve rung size x1.5, stop-risk budget 0.12, rung stop 5 sigma_4h,
TP 1 sigma_4h, engine_user conventions after the v188 audit: intrabar
peaks, stop wins same-minute ties).
Run from the repository root so every data path below stays relative.

A1 (v200): v197 pipeline with book stop/target (SL, TP) in daily sigma =
(2, 4), (2.5, 2.5), (3, 2), plus the reference (4, 8). Report dev4, 5y,
last year, gate DD, book stops/TPs, mean and max gross book exposure
(sum |target weight|). Selection = best dev4 with DD <= 20 and no losing
year in the first four years.

A2 (v201): v197 pipeline plus an hourly ladder: per hour h of the holding
bar, base = 1m open of minute 60h, sigma_1h = std of 1h open-to-open
returns (hourly opens = minute 0/60/120/180 opens of every holding bar in
time order) over the 1440 hours ending with the last hour of the previous
holding bar (min 480); rungs 2.5/3/3.5/4 sigma_1h; bids live minutes
16..57 (h=0) else 60h+4..60h+57; TP L(1+sigma_1h), SL L(1-5 sigma_1h),
exits strictly after the fill minute and before minute 60(h+1), else
market at the open of minute 60(h+1) (h=3: next 4h open, funding if
settlement). One shared stop-risk budget over both ladders
(rn (5 sigma + 0.02) with each rung's own sigma), fills ordered (minute,
ladder 4h first, rung, asset). Variants: hourly off (must equal v197
5.562/19.72), on with budget 0.12, on with 0.18. Selection = best dev4
with DD <= 20 and no losing year in the first four years.
Save replication.json.

Updated conventions adopted from the v188 audit (verified against the
engine source in main via asserts so the audit is self-contained):
  C1 1m-marked DD uses peaks over the minute path (intrabar highs count):
     summarize peaks over maximum(e, eq_max), troughs over minimum(e,
     eq_min) -- engine_user.simulate tracks eq_max per bar and summarize
     builds peak1 from maximum(e, ex).
  C2 A stop on the held position wins a same-minute tie with a new book
     fill (the pending order is cancelled): simulate checks the held
     position over minutes [0, fill_min + 1), i.e. seg_end = fill_min + 1,
     and cancels the fill (fills - 1, unfilled + 1) when the held stop/TP
     hits at or before the fill minute.

Frozen engine_user spec (from OPENCODE_V193_AUDIT.md via v193/v197/v199
audits, re-stated here so the audit is self-contained):
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
  E4 Book SL/TP in daily sigma (this audit, A1 varies (SL, TP)): sigma_d =
     std of 360 4h open-to-open returns ending at t * sqrt(6); long SL =
     entry * (1 - SL sigma_d), TP = entry * (1 + TP sigma_d) (short
     mirrored); reference (4, 8) equals the v197 setting (m_sl = 4 with
     TP = 2 * m). Levels reset at each decision; held position checked
     from minute 0 over [0, fill_min + 1) so a held stop wins a
     same-minute tie with the new fill (C2, pending order cancelled); new
     position checked from the fill minute; SL if low <= SL (long),
     filled at min(SL, minute open), taker 0.00055; TP on high > TP
     (strict), maker 0.0002; both in one minute -> SL first; after SL/TP
     the asset is flat for the rest of the bar.
  E5 Funding (gate): a long held at the end of the bar pays 0.0001 of its
     notional if T + 4h is 00/08/16 UTC; shorts 0. No carry sleeve.
  E6 Dip sleeve (v197 setting on every row of this audit): rungs k_rung =
     (2.5, 3, 3.5, 4) with sigma_4h (not daily), bid L = open(T)
     (1 - k_rung sigma_4h) live minutes 16..238, maker fill on low < L
     (strict); exits after the fill minute: SL at L (1 - 5 sigma_4h)
     (low <= SL, fill min(SL, open), taker 0.00055), TP at L (1 + sigma_4h)
     (high > TP strict, maker 0.0002), else at open(T+4h) taker paying
     0.0001 if that is a settlement; per-rung notional fixed at
     rn = s g 1.5 0.25/4/1.657 via size_mult = 1.5 on every row (engine
     divides by the constant 4, not by the rung count); fills taken in
     (minute, rung, asset) order iff risk_open + risk_new <= X where
     risk = rn * (5 sigma_4h(asset) + 0.02) summed over taken rungs still
     open at the fill minute (exit > f); X = 0.12 on every A1 row.
  E7 Hourly ladder (A2 only, engine_user hourly=True branch): sigma_1h per
     asset from prepare (std of 1h open-to-open returns over 1440 hours
     ending with the last hour of the previous holding bar, min 480);
     per hour h of the holding bar, base = 1m open of minute 60h, rungs
     2.5/3/3.5/4 sigma_1h, bid L = base (1 - k sigma_1h) live minutes
     16..57 (h=0) else 60h+4..60h+57, maker fill on low < L (strict);
     exits strictly after the fill minute and before minute 60(h+1):
     SL at L (1 - 5 sigma_1h), TP at L (1 + sigma_1h), else market at the
     open of minute 60(h+1) (h=3: next 4h open o2, funding 0.0001 if that
     is a settlement); hourly fills share one stop-risk budget with the
     4h ladder, risk = rn (5 sigma + 0.02) with each rung's own sigma,
     fills ordered by (minute, ladder 4h first, rung, asset).
  E8 1m-marked equity per minute = start equity * (1 + position MTM +
     sleeve MTM); gate DD = max(4h-close DD, 1m-marked DD) with the 1m leg
     peaking over the minute path (C1); per anchor year net/monthly;
     monthly_dev4 = geometric mean of the first four anchor years
     (monthly % = 100 * ((1+geo) ** (1/12) - 1)).
  E9 Rows: P2 = (A+B)/2 with sleeve on, target 0.25, cap 2.0, gap 0.02,
     book limit (d, W) = (0.001, 239), size_mult 1.5, X = 0.12 (A1 all
     rows; A2 hourly-off and hourly-0.12), X = 0.18 (A2 hourly-0.18).
     A1 book (SL, TP): REF_4_8 = (4, 8), SL2_TP4 = (2, 4),
     SL2p5_TP2p5 = (2.5, 2.5), SL3_TP2 = (3, 2). A2 book fixed at (4, 8),
     hourly off / on with X = 0.12 / 0.18. Selections (first four years
     only) = best monthly_dev4 among rows with gate DD <= 20 and no
     losing year in the first four anchor years, per section.

Leakage notes (checked in code, reported in COMPARISON.md Part B):
  L1 Feature timing: pipeline books at t, opens at t/t-1, sigma windows
     (sigma_d, sigma_4h, sigma_1h) ending at or before the decision,
     s/g known at the decision; cubes row i = holding bar T.
  L2 No label window: no forward return is read except through fills and
     the bar-close settlement/exit prices at T/T+4h (hourly exits at
     intrabar opens 60(h+1) or o2).
  L3 Fit windows: member books are pre-fit causal inputs; no statistic is
     fit on any test year inside this script (vol/governor are running
     causal filters; selections use first-four-years metrics only; book
     (SL, TP) grids and hourly budgets were pre-registered, not tuned).
  L4 Fill timing: book limit minutes 2..238 strict trade-through, held
     SL/TP from minute 0 with stop-wins-tie over [0, fill_min + 1) and
     stop-first within a minute, sleeve triggers 16..238 (4h) and
     16..57 / 60h+4..60h+57 (hourly) with exits strictly after the fill
     minute.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2") / "v200_v201_audit"
OUT = AUD / "replication.json"
CACHE = Path("artifacts/research/engine_real")
OPENS_FILE = CACHE / "opens_v154.parquet"
BOOKS_FILE = CACHE / "books_v154.parquet"
MEMBERS_FILE = CACHE / "members_v154.parquet"

M_SLEEVE_SL = 5.0
M_SLEEVE_TP = 1.0
D_LIMIT = 0.001
WIN_END = 239
GAP = 0.02
TARGET = 0.25
CAP = 2.0
SIZE_MULT = 1.5
SLEEVE_X = 0.12
SLEEVE_X_HIGH = 0.18
RUNGS_4H = (2.5, 3.0, 3.5, 4.0)

A1_BOOKS = {
    "REF_4_8": (4.0, 8.0),
    "SL2_TP4": (2.0, 4.0),
    "SL2p5_TP2p5": (2.5, 2.5),
    "SL3_TP2": (3.0, 2.0),
}

A2_ROWS = {
    "HOURLY_OFF": {"hourly": False, "budget": SLEEVE_X},
    "HOURLY_012": {"hourly": True, "budget": SLEEVE_X},
    "HOURLY_018": {"hourly": True, "budget": SLEEVE_X_HIGH},
}


def _load_engine_user():
    spec = importlib.util.spec_from_file_location(
        "v200_v201_audit_engine_user",
        Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _row_record(key, out, extra):
    yearly = out["yearly"]
    first4 = yearly[:4]
    losing_first4 = sum(1 for y in first4 if y["net_pct"] < 0)
    geo4 = float(np.prod([1 + y["net_pct"] / 100 for y in first4]) ** (1 / 4) - 1)
    dev4_check = round(100 * ((1 + geo4) ** (1 / 12) - 1), 3)
    assert abs(dev4_check - out["monthly_dev4"]) < 0.002, (key, dev4_check, out["monthly_dev4"])
    assert abs(out["gate_dd"] - max(out["dd_4h"], out["dd_1m"])) < 1e-9, key
    stats = out["stats"]
    gross_mean = float(stats["gross_sum"] / stats["bars"]) if stats["bars"] else 0.0
    rec = {
        "pipeline": "P2",
        "books": "v151=(A+B)/2",
        "sleeve": True,
        "d_limit": float(D_LIMIT),
        "win_end": int(WIN_END),
        "target": float(TARGET),
        "cap": float(CAP),
        "size_mult": float(SIZE_MULT),
        "mult": float(SIZE_MULT),
        "gap": float(GAP),
        "m_sleeve_sl": float(M_SLEEVE_SL),
        "m_sleeve_tp_mult": float(M_SLEEVE_TP),
        "rungs": list(RUNGS_4H),
        "rung_notional": "s * g * 1.5 * 0.25/4/1.657 via size_mult = 1.5 (fixed regardless of rung count)",
        "monthly_dev4": out["monthly_dev4"],
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
        "book_stops": stats["stops"],
        "book_tps": stats["tps"],
        "gross_book_mean": round(gross_mean, 6),
        "gross_book_max": stats["gross_max"],
        "stats": stats,
    }
    rec.update(extra)
    return rec


def main():
    eu = _load_engine_user()
    print(f"engine_user maker={eu.MAKER} taker={eu.TAKER} fund_long={eu.FUND_LONG}", flush=True)
    assert eu.MAKER == 0.0002 and eu.TAKER == 0.00055 and eu.FUND_LONG == 0.0001
    assert eu.D_LIMIT == 0.001 and eu.SIZE == 0.25 and eu.S_REF == 1.657
    assert tuple(eu.RUNGS) == (2.5, 3.0, 3.5, 4.0)

    sim_src = inspect.getsource(eu.simulate)
    sum_src = inspect.getsource(eu.summarize)
    assert "fill_min + 1" in sim_src, "C2 stop-wins-tie (seg_end = fill_min + 1) missing"
    assert "eq_max" in sim_src, "C1 eq_max minute-peak tracking missing"
    assert "peak1" in sum_src, "C1 minute-path peak (peak1) missing in summarize"
    assert "np.maximum(e, ex)" in sum_src, "C1 minute-path peak over maximum(e, ex) missing"
    print("conventions C1 (minute-path DD peaks) and C2 (held stop wins fill tie) verified", flush=True)

    assert "sig1h" in sim_src, "hourly sigma_1h branch missing in simulate"
    assert "60 * h" in sim_src, "hourly base minute 60h branch missing in simulate"
    assert "m_tp" in sim_src, "independent book m_tp branch missing in simulate"
    prep_src = inspect.getsource(eu.prepare)
    assert "sig1h" in prep_src and "1440" in prep_src and "480" in prep_src, "sig1h 1440/min-480 window missing in prepare"
    print("hourly (sig1h 1440/min 480, base 60h) and independent m_tp branches verified", flush=True)

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
    assert "sig1h" in prep, "prepare must expose sig1h for the hourly ladder"
    assert prep["sig1h"].shape == (len(prep["idx"]), len(cols)), prep["sig1h"].shape
    assert bool(np.isnan(prep["sig1h"][0]).all()), "first-bar sig1h must be NaN (no prior hour)"

    rows_a1 = {}
    for key, (m_sl, m_tp) in A1_BOOKS.items():
        print(f"simulate A1 {key} book SL={m_sl} TP={m_tp} size_mult={SIZE_MULT} X={SLEEVE_X} ...", flush=True)
        out = eu.simulate(
            P2, opens, prep,
            m_sl=float(m_sl), m_tp=float(m_tp),
            m_sleeve_sl=float(M_SLEEVE_SL),
            sleeve=True, target=float(TARGET), cap=float(CAP),
            d_limit=float(D_LIMIT), win_end=int(WIN_END),
            sleeve_risk_budget=float(SLEEVE_X), gap=float(GAP),
            m_sleeve_tp=float(M_SLEEVE_TP),
            size_mult=float(SIZE_MULT),
            rungs=tuple(RUNGS_4H),
            hourly=False,
        )
        yearly = out["yearly"]
        assert [y["anchor"] for y in yearly] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
        rows_a1[key] = _row_record(key, out, {"m_sl": float(m_sl), "m_tp": float(m_tp), "hourly": False,
                                              "sleeve_risk_budget": float(SLEEVE_X),
                                              "hourly_rungs": list(RUNGS_4H)})
        r = rows_a1[key]
        print(f"{key}: dev4={r['monthly_dev4']} 5y={r['monthly_5y']} "
              f"last={r['monthly_last_year']} gateDD={r['gate_dd']} "
              f"lose={r['losing_years']} lose4={r['losing_years_first4']} "
              f"nets={r['yearly_net_pct']} stops={r['book_stops']} tps={r['book_tps']} "
              f"gross_mean={r['gross_book_mean']} gross_max={r['gross_book_max']} "
              f"rungs={r['stats']['rungs']} liq={r['stats']['liq']}", flush=True)

    rows_a2 = {}
    for key, cfg in A2_ROWS.items():
        print(f"simulate A2 {key} hourly={cfg['hourly']} X={cfg['budget']} book (4, 8) ...", flush=True)
        out = eu.simulate(
            P2, opens, prep,
            m_sl=4.0, m_tp=8.0,
            m_sleeve_sl=float(M_SLEEVE_SL),
            sleeve=True, target=float(TARGET), cap=float(CAP),
            d_limit=float(D_LIMIT), win_end=int(WIN_END),
            sleeve_risk_budget=float(cfg["budget"]), gap=float(GAP),
            m_sleeve_tp=float(M_SLEEVE_TP),
            size_mult=float(SIZE_MULT),
            rungs=tuple(RUNGS_4H),
            hourly=bool(cfg["hourly"]),
        )
        yearly = out["yearly"]
        assert [y["anchor"] for y in yearly] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
        rows_a2[key] = _row_record(key, out, {"m_sl": 4.0, "m_tp": 8.0, "hourly": bool(cfg["hourly"]),
                                              "sleeve_risk_budget": float(cfg["budget"]),
                                              "hourly_rungs": list(RUNGS_4H) if cfg["hourly"] else []})
        r = rows_a2[key]
        print(f"{key}: dev4={r['monthly_dev4']} 5y={r['monthly_5y']} "
              f"last={r['monthly_last_year']} gateDD={r['gate_dd']} "
              f"lose={r['losing_years']} lose4={r['losing_years_first4']} "
              f"nets={r['yearly_net_pct']} stops={r['book_stops']} tps={r['book_tps']} "
              f"rungs={r['stats']['rungs']} rung_stops={r['stats']['rung_stops']} "
              f"rung_tps={r['stats']['rung_tps']} liq={r['stats']['liq']}", flush=True)

    # Hourly-off must re-score the v197 anchor under the corrected engine.
    off = rows_a2["HOURLY_OFF"]
    assert off["monthly_dev4"] == 5.562, (off["monthly_dev4"], off["yearly_net_pct"])
    assert off["gate_dd"] == 19.72, (off["gate_dd"], off["dd_4h"], off["dd_1m"])
    assert off["yearly_net_pct"] == [40.67, 51.32, 147.63, 154.98, 38.66]
    # Same config as A1 REF_4_8, so the two rows must be bit-exact.
    ref = rows_a1["REF_4_8"]
    for k in ("monthly_dev4", "monthly_5y", "monthly_last_year", "gate_dd", "dd_4h", "dd_1m"):
        assert ref[k] == off[k], (k, ref[k], off[k])
    assert ref["yearly_net_pct"] == off["yearly_net_pct"]
    assert ref["stats"]["fills"] == off["stats"]["fills"]
    assert ref["stats"]["rungs"] == off["stats"]["rungs"]
    print("anchor checks passed: HOURLY_OFF == v197 5.562/19.72 and == A1 REF_4_8", flush=True)

    def _select(rows):
        eligible = {k: v for k, v in rows.items()
                    if v["gate_dd"] <= 20 and v["losing_years_first4"] == 0}
        selection = max(eligible, key=lambda k: eligible[k]["monthly_dev4"]) if eligible else None
        return sorted(eligible), selection

    eligible_a1, selection_a1 = _select(rows_a1)
    eligible_a2, selection_a2 = _select(rows_a2)
    print(f"A1 eligible {eligible_a1} selection {selection_a1}", flush=True)
    print(f"A2 eligible {eligible_a2} selection {selection_a2}", flush=True)

    replication = {
        "version": "v200_v201_audit_replication",
        "blind": "did_not_open_research_v200_or_v201_until_this_file_saved",
        "books": "v151=(A+B)/2 from cached v154 members; v197 pipeline with rung size x1.5",
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
            "m_sleeve_sl": float(M_SLEEVE_SL),
            "m_sleeve_tp_mult": float(M_SLEEVE_TP),
            "target": float(TARGET),
            "cap": float(CAP),
            "gap": float(GAP),
            "size_mult": float(SIZE_MULT),
            "sleeve_risk_budget": float(SLEEVE_X),
            "sleeve_risk_budget_high": float(SLEEVE_X_HIGH),
            "rung_notional": "s * g * 1.5 * 0.25/4/1.657 via size_mult = 1.5 (fixed regardless of rung count)",
            "hourly": "base = 1m open of minute 60h; sig1h = std of 1h open-to-open returns over 1440h ending last hour of previous bar (min 480); rungs 2.5/3/3.5/4; bids 16..57 (h=0) else 60h+4..60h+57; TP L(1+sig1h) SL L(1-5 sig1h); exits strictly after fill minute before 60(h+1) else market at 60(h+1) open (h=3: next 4h open, funding if settlement); shared budget rn (5 sigma + 0.02) per-rung sigma; order (minute, 4h first, rung, asset)",
            "conventions": [
                "C1 1m-marked DD peaks over the minute path (intrabar highs count)",
                "C2 held-position stop wins a same-minute tie with a new book fill (pending order cancelled)",
            ],
        },
        "a1_books": {k: list(v) for k, v in A1_BOOKS.items()},
        "rows_a1": rows_a1,
        "selection_rule_a1": "best monthly_dev4 among A1 rows with gate_dd <= 20 and no losing year in the first four anchor years",
        "eligible_a1": eligible_a1,
        "selection_a1": selection_a1,
        "a2": {k: v for k, v in A2_ROWS.items()},
        "rows_a2": rows_a2,
        "selection_rule_a2": "best monthly_dev4 among A2 rows with gate_dd <= 20 and no losing year in the first four anchor years",
        "eligible_a2": eligible_a2,
        "selection_a2": selection_a2,
        "anchor_check": {
            "hourly_off_monthly_dev4": off["monthly_dev4"],
            "hourly_off_gate_dd": off["gate_dd"],
            "hourly_off_yearly_net_pct": off["yearly_net_pct"],
            "expected_dev4": 5.562,
            "expected_gate_dd": 19.72,
            "ref_equals_off": True,
        },
    }
    AUD.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print(f"saved {OUT}", flush=True)


if __name__ == "__main__":
    main()
