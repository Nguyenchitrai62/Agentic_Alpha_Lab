"""v205 blind audit Part A replication.

Blind rule: does NOT read research v205 files, the v205 result json, nor
the v205 pipeline source, until replication.json is saved. Independent
implementation from OPENCODE_V205_AUDIT.md, using
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
as the gate engine base (itself a direct implementation of the AGENTS.md
2026-09-27 user goal, gate cost model and current execution assumptions).
Base: the v203 replication (books 50/50 annual+quarterly blend, caches,
reindex to books_v154 missing -> 0) and the v204 replication (directional
rung sizing align m_long 1.5 / m_other 0.5 on top of the x1.5 rung size).
Run from the repository root so every data path below stays relative.

A: books = 0.5 (A+B)/2 annual
(artifacts/research/engine_real/members_v154.parquet) + 0.5 (Aq+Bq)/2
quarterly (members_quarterly.parquet), reindexed to books_v154
(missing -> 0); sleeve aligned with the book direction (m_long 1.5,
m_other 0.5 on top of the x1.5 rung size, as v204); everything else v204
(engine_user, corrected conventions). Reference = v204 selection (annual
books with the same align). Report dev4, worst first-four-year monthly
return, 5y, last year, yearly nets and 1m DDs, gate DD; selection =
robust criterion. Save replication.json.

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

Frozen engine_user spec (from OPENCODE_V193_AUDIT.md via v193/v197/v199/
v203/v204 audits, re-stated here so the audit is self-contained):
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
  E6 Dip sleeve (v197 setting + v204 align, both rows): rungs k_rung =
     (2.5, 3, 3.5, 4) with sigma_4h, bid L = open(T)
     (1 - k_rung sigma_4h) live minutes 16..238, maker fill on low < L
     (strict); exits after the fill minute: SL at L (1 - 5 sigma_4h)
     (low <= SL, fill min(SL, open), taker 0.00055), TP at L (1 + sigma_4h)
     (high > TP strict, maker 0.0002), else at open(T+4h) taker paying
     0.0001 if that is a settlement; base per-rung notional
     rn_base = s g 1.5 0.25/4/1.657 via size_mult = 1.5 on every row
     (engine divides by the constant 4, not by the rung count); per filled
     rung rn = rn_base * m with m = m_long (1.5) if tgt[a] > 0 else
     m_other (0.5) (engine align branch, tgt = 0.8 s B g at the decision,
     decision-known; m = 0 -> rung skipped, not used here); fills taken in
     (ladder, rung, asset) order iff risk_open + risk_new <= X where
     risk = own rn * (5 sigma_4h(asset) + 0.02) summed over taken rungs
     still open at the fill minute (exit > f); X = 0.12 on every row.
  E7 1m-marked equity per minute = start equity * (1 + position MTM +
     sleeve MTM); gate DD = max(4h-close DD, 1m-marked DD) with the 1m leg
     peaking over the minute path (C1); per anchor year net/monthly;
     monthly_dev4 = geometric mean of the first four anchor years
     (monthly % = 100 * ((1+geo) ** (1/12) - 1)); worst_first4 = min of the
     first-four yearly monthly_pct.
  E8 Rows: REF_ANNUAL = (A+B)/2 annual with align (1.5, 0.5) (= v204
     selection on annual books); BLEND_50_50 = 0.5 * REF_ANNUAL + 0.5 *
     (Aq+Bq)/2 quarterly (both legs reindexed to books_v154, missing ->
     0) with the same align (1.5, 0.5); both rows under the same v204
     rules (sleeve on, m = 4, sleeve SL k = 5, book limit (d, W) =
     (0.001, 239), target 0.25, cap 2.0, gap 0.02, size_mult 1.5, X =
     0.12, rungs (2.5, 3, 3.5, 4)); selection = robust criterion
     (AGENTS.md 2026-09-27, v204 on).

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
     causal filters; selection uses first-four-years metrics only; the
     50/50 blend weight and the (1.5, 0.5) align were pre-registered, not
     tuned).
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

AUD = Path("research/parallel/rounds/parallel-20260906-r2") / "v205_audit"
OUT = AUD / "replication.json"
CACHE = Path("artifacts/research/engine_real")
OPENS_FILE = CACHE / "opens_v154.parquet"
BOOKS_FILE = CACHE / "books_v154.parquet"
MEMBERS_FILE = CACHE / "members_v154.parquet"
QMEMBERS_FILE = CACHE / "members_quarterly.parquet"

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
ALIGN = (1.5, 0.5)


def _load_engine_user():
    spec = importlib.util.spec_from_file_location(
        "v205_audit_engine_user",
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

    books154 = pd.read_parquet(BOOKS_FILE).sort_index()
    cols = list(books154.columns)
    mem = pd.read_parquet(MEMBERS_FILE).sort_index()
    assert set(mem.columns.get_level_values(0).unique()) >= {"A", "B"}
    A = mem.xs("A", axis=1, level=0).reindex(books154.index).reindex(columns=cols).fillna(0.0)
    B = mem.xs("B", axis=1, level=0).reindex(books154.index).reindex(columns=cols).fillna(0.0)
    annual = ((A + B) / 2).sort_index()
    assert list(annual.index) == list(books154.index)
    assert list(annual.columns) == cols

    qmem = pd.read_parquet(QMEMBERS_FILE).sort_index()
    assert set(qmem.columns.get_level_values(0).unique()) >= {"A", "B"}
    Aq = qmem.xs("A", axis=1, level=0).reindex(books154.index).reindex(columns=cols).fillna(0.0)
    Bq = qmem.xs("B", axis=1, level=0).reindex(books154.index).reindex(columns=cols).fillna(0.0)
    quarterly = ((Aq + Bq) / 2).sort_index()
    assert list(quarterly.index) == list(books154.index)
    assert list(quarterly.columns) == cols
    n_q_extra = int(len(set(qmem.index) - set(books154.index)))
    n_q_missing = int(len(set(books154.index) - set(qmem.index)))
    print(f"quarterly reindex: extra dropped={n_q_extra} missing filled 0={n_q_missing}", flush=True)
    assert n_q_missing == 0

    blend = (0.5 * annual + 0.5 * quarterly).sort_index()
    assert list(blend.index) == list(books154.index)
    assert list(blend.columns) == cols
    max_abs_blend = float((blend - (annual + quarterly) / 2).abs().max().max())
    assert max_abs_blend == 0.0

    opens = pd.read_parquet(OPENS_FILE).sort_index()
    print(f"annual {annual.shape} quarterly {quarterly.shape} blend {blend.shape} opens {opens.shape}", flush=True)

    prep = eu.prepare(books154, opens)
    print(f"prepared cubes O {prep['O'].shape}", flush=True)

    books_map = {"REF_ANNUAL": annual, "BLEND_50_50": blend}
    rows = {}
    for key in ("REF_ANNUAL", "BLEND_50_50"):
        bk = books_map[key]
        print(f"simulate {key} align={list(ALIGN)} size_mult={SIZE_MULT} X={SLEEVE_X} rungs={list(RUNGS)} ...", flush=True)
        out = eu.simulate(
            bk, opens, prep,
            m_sl=M_SL, m_sleeve_sl=float(M_SLEEVE_SL),
            sleeve=True, target=float(TARGET), cap=float(CAP),
            d_limit=float(D_LIMIT), win_end=int(WIN_END),
            sleeve_risk_budget=float(SLEEVE_X), gap=float(GAP),
            m_sleeve_tp=float(M_SLEEVE_TP),
            size_mult=float(SIZE_MULT),
            rungs=tuple(RUNGS),
            align=tuple(ALIGN),
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
            "pipeline": "v204_rules",
            "books": "annual_(A+B)/2" if key == "REF_ANNUAL" else "0.5_annual_(A+B)/2_+_0.5_quarterly_(Aq+Bq)/2",
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
            "align": list(ALIGN),
            "m_long": float(ALIGN[0]),
            "m_other": float(ALIGN[1]),
            "rung_notional": "rn_base * m via size_mult = 1.5 then align m (m_long 1.5 if tgt>0 else m_other 0.5); risk per open rung = own rn * (5 sigma_4h + 0.02)",
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
              f"fills={out['stats']['fills']} rungs={out['stats']['rungs']} "
              f"liq={out['stats']['liq']}", flush=True)

    eligible = {k: v for k, v in rows.items()
                if v["gate_dd"] <= 20 and v["losing_years_first4"] == 0}
    selection = robust_selection(rows)
    print(f"eligible {sorted(eligible)} selection {selection}", flush=True)

    replication = {
        "version": "v205_audit_replication",
        "blind": "did_not_open_research_v205_until_this_file_saved",
        "books": "0.5_annual_(A+B)/2_from_members_v154_+_0.5_quarterly_(Aq+Bq)/2_from_members_quarterly_reindexed_to_books_v154_missing_0_with_align_(1.5,0.5)",
        "books_detail": {
            "annual_file": "artifacts/research/engine_real/members_v154.parquet",
            "quarterly_file": "artifacts/research/engine_real/members_quarterly.parquet",
            "books_file": "artifacts/research/engine_real/books_v154.parquet",
            "opens_file": "artifacts/research/engine_real/opens_v154.parquet",
            "books_index_len": int(len(books154.index)),
            "columns": cols,
            "quarterly_extra_dropped": n_q_extra,
            "quarterly_missing_filled_0": n_q_missing,
            "blend_weight_annual": 0.5,
            "blend_weight_quarterly": 0.5,
            "blend_check_max_abs_diff": max_abs_blend,
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
            "align": list(ALIGN),
            "m_long": float(ALIGN[0]),
            "m_other": float(ALIGN[1]),
            "rung_notional": "rn_base = s * g * 1.5 * 0.25/4/1.657 via size_mult = 1.5; per filled rung rn = rn_base * m (m_long 1.5 if tgt>0 else m_other 0.5)",
            "conventions": [
                "C1 1m-marked DD peaks over the minute path (intrabar highs count)",
                "C2 held-position stop wins a same-minute tie with a new book fill (pending order cancelled)",
            ],
        },
        "rows": rows,
        "reference": "REF_ANNUAL = v204 selection (annual books with align 1.5/0.5)",
        "selection_rule": "robust criterion (AGENTS.md 2026-09-27, v204 on): among rows with gate_dd <= 20 and no losing year in the first four years, prefer rows with monthly_dev4 >= 5 if any, among them pick the highest worst_first4, ties -> higher monthly_dev4",
        "eligible": sorted(eligible),
        "selection": selection,
    }
    AUD.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print(f"saved {OUT}", flush=True)


if __name__ == "__main__":
    main()
