"""v192 blind audit Part A replication.

Blind rule: does NOT read research v192 files, v192 result json, nor the
v192 pipeline source, until replication.json is saved. Independent
implementation from OPENCODE_V192_AUDIT.md, using research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
as the gate engine base (itself a direct implementation of the AGENTS.md
2026-09-27 user goal, gate cost model and current execution assumptions).
May import engine_real only for v154_books constants if needed. Run from
the repository root so every data path below stays relative.

A: pipeline P2 = (A+B)/2 members with the dip sleeve, rung stop 5 sigma_4h,
book SL/TP m = 4; book limit orders at open_1m(T, 0) * (1 -/+ d) filled on
a strict 1m trade-through in minutes 2 .. W-1, else expire, for
(d, W) = (0.001, 60), (0.001, 239), (0.0003, 239). Report per variant
monthly_dev4 (first four anchors), monthly_5y, last-year monthly, gate DD,
fills/unfilled; selection = best monthly_dev4 with DD <= 20 and no losing
year in the first four years. Save replication.json.

Frozen engine_user spec (from OPENCODE_V188_AUDIT.md via v191 audit, re-stated
here so the audit is self-contained):
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
     Limit at open_1m(T, minute 0) * (1 -/+ d), filled at the limit if
     a 1m low (buy) / high (sell) in minutes 2..W-1 trades through it
     (strict), maker 0.0002; otherwise expires. Average entry: new -> fill;
     adding same side -> weighted; reducing -> unchanged; flip -> fill.
  E4 Book SL/TP with m = 4 (this audit): sigma_d = std of 360 4h
     open-to-open returns ending at t * sqrt(6); long SL = entry *
     (1 - m sigma_d), TP = entry * (1 + 2 m sigma_d) (short mirrored);
     levels reset at each decision; checked from minute 0 on the position
     held (before the fill) and from the fill minute on the new position;
     SL if low <= SL (long), filled at min(SL, minute open), taker
     0.00055; TP on high > TP (strict), maker 0.0002; both in one minute ->
     SL first; after SL/TP the asset is flat for the rest of the bar and
     the pending order is cancelled if not yet filled.
  E5 Funding (gate): a long held at the end of the bar pays 0.0001 of its
     notional if T + 4h is 00/08/16 UTC; shorts 0. No carry sleeve.
  E6 Dip sleeve: rungs k_rung = 2.5/3/3.5/4 with sigma_4h (not daily), bid
     L = open(T) (1 - k_rung sigma_4h) live minutes 16..238, maker fill on
     low < L (strict); exits after the fill minute: SL at L (1 - 5
     sigma_4h) (low <= SL, fill min(SL, open), taker 0.00055), TP at
     L (1 + sigma_4h) (high > TP strict, maker 0.0002), else at open(T+4h)
     taker paying 0.0001 if that is a settlement; rung notional
     rn = s g 0.25/4/1.657; fills taken in (minute, rung, asset) order iff
     (open rungs at that minute + 1) rn <= 1/6.
  E7 1m-marked equity per minute = start equity * (1 + position MTM +
     sleeve MTM); gate DD = max(4h-close DD, 1m-marked DD); per anchor year
     net/monthly; monthly_dev4 = geometric mean of the first four anchor
     years (monthly % = 100 * ((1+geo) ** (1/12) - 1)).
  E8 Rows: P2 = (A+B)/2 with sleeve on, m = 4, sleeve SL k = 5, book limit
     (d, W) in ((0.001, 60), (0.001, 239), (0.0003, 239)); selection = best
     monthly_dev4 among rows with gate DD <= 20 and no losing year in the
     first four anchor years.

Leakage notes (checked in code, reported in COMPARISON.md Part B):
  L1 Feature timing: pipeline books at t, opens at t/t-1, sigma windows
     ending at t, s/g known at the decision; cubes row i = holding bar T.
  L2 No label window: no forward return is read except through fills and
     the bar-close settlement/exit prices at T/T+4h.
  L3 Fit windows: member books are pre-fit causal inputs; no statistic is
     fit on any test year inside this script (vol/governor are running
     causal filters; selection uses first-four-years metrics only).
  L4 Fill timing: book limit minutes 2..W-1 strict trade-through, SL/TP
     from minute 0 (held) / fill minute (new), sleeve trigger 16..238 and
     exits strictly after the fill minute, stop-first within a minute.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2") / "v192_audit"
OUT = AUD / "replication.json"
CACHE = Path("artifacts/research/engine_real")
OPENS_FILE = CACHE / "opens_v154.parquet"
BOOKS_FILE = CACHE / "books_v154.parquet"
MEMBERS_FILE = CACHE / "members_v154.parquet"

M_SL = 4.0
M_SLEEVE_SL = 5.0
VARIANTS = ((0.001, 60), (0.001, 239), (0.0003, 239))


def _key(d, w):
    return f"P2_d{int(round(d * 10000)):04d}_W{w:03d}"


def _load_engine_user():
    spec = importlib.util.spec_from_file_location(
        "v192_audit_engine_user",
        Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    eu = _load_engine_user()
    print(f"engine_user maker={eu.MAKER} taker={eu.TAKER} fund_long={eu.FUND_LONG}", flush=True)
    assert eu.MAKER == 0.0002 and eu.TAKER == 0.00055 and eu.FUND_LONG == 0.0001
    assert eu.D_LIMIT == 0.001 and eu.SIZE == 0.25 and eu.S_REF == 1.657
    assert tuple(eu.RUNGS) == (2.5, 3.0, 3.5, 4.0)

    # ---- members check: (A+B+D)/3 == books_v154 ----
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

    # ---- pipeline P2 = (A+B)/2 on the union index (missing -> 0.0) ----
    idx_union = A_m.index.union(B_m.index).union(D_m.index).sort_values()
    cols = list(books_cache.columns)
    Au = A_m.reindex(idx_union).reindex(columns=cols).fillna(0.0)
    Bu = B_m.reindex(idx_union).reindex(columns=cols).fillna(0.0)
    P2 = ((Au + Bu) / 2).sort_index()
    assert list(P2.index) == list(books_cache.index)
    assert list(P2.columns) == cols

    opens = pd.read_parquet(OPENS_FILE).sort_index()
    print(f"pipeline P2 {P2.shape} opens {opens.shape}", flush=True)

    # ---- shared 1m preparation ----
    prep = eu.prepare(P2, opens)
    print(f"prepared cubes O {prep['O'].shape}", flush=True)

    rows = {}
    for d, w in VARIANTS:
        key = _key(d, w)
        print(f"simulate {key} m_sl={M_SL} sleeve_sl_k={M_SLEEVE_SL} d={d} W={w} ...", flush=True)
        out = eu.simulate(
            P2, opens, prep,
            m_sl=M_SL, m_sleeve_sl=float(M_SLEEVE_SL),
            sleeve=True, target=0.25, cap=2.0,
            d_limit=float(d), win_end=int(w),
        )
        yearly = out["yearly"]
        assert [y["anchor"] for y in yearly] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
        first4 = yearly[:4]
        losing_first4 = sum(1 for y in first4 if y["net_pct"] < 0)
        # geometric-mean cross-check of monthly_dev4 from first-four nets
        geo4 = float(np.prod([1 + y["net_pct"] / 100 for y in first4]) ** (1 / 4) - 1)
        dev4_check = round(100 * ((1 + geo4) ** (1 / 12) - 1), 3)
        assert abs(dev4_check - out["monthly_dev4"]) < 0.002, (key, dev4_check, out["monthly_dev4"])
        # gate DD cross-check
        assert abs(out["gate_dd"] - max(out["dd_4h"], out["dd_1m"])) < 1e-9, key
        rows[key] = {
            "pipeline": "P2",
            "sleeve": True,
            "m_sl": M_SL,
            "m_sleeve_sl": float(M_SLEEVE_SL),
            "d_limit": float(d),
            "win_end": int(w),
            "monthly_dev4": out["monthly_dev4"],
            "monthly_5y": out["monthly_5y"],
            "monthly_last_year": out["monthly_last_year"],
            "yearly": yearly,
            "yearly_net_pct": [y["net_pct"] for y in yearly],
            "yearly_monthly_pct": [y["monthly_pct"] for y in yearly],
            "losing_years": out["losing_years"],
            "losing_years_first4": losing_first4,
            "dd_4h": out["dd_4h"],
            "dd_1m": out["dd_1m"],
            "gate_dd": out["gate_dd"],
            "gate_pass": out["gate_pass"],
            "stats": out["stats"],
        }
        print(f"{key}: dev4={out['monthly_dev4']} 5y={out['monthly_5y']} "
              f"last={out['monthly_last_year']} gateDD={out['gate_dd']} "
              f"lose={out['losing_years']} lose4={losing_first4} "
              f"nets={[y['net_pct'] for y in yearly]} "
              f"fills={out['stats']['fills']} unfilled={out['stats']['unfilled']}", flush=True)

    # ---- selection: best monthly_dev4 with DD <= 20 and no losing year in first four ----
    eligible = {k: v for k, v in rows.items()
                if v["gate_dd"] <= 20 and v["losing_years_first4"] == 0}
    selection = max(eligible, key=lambda k: eligible[k]["monthly_dev4"]) if eligible else None
    print(f"eligible {sorted(eligible)} selection {selection}", flush=True)

    replication = {
        "version": "v192_audit_replication",
        "blind": "did_not_open_research_v192_until_this_file_saved",
        "books": "pipeline P2=(A+B)/2 from cached v154 members",
        "members_check": {
            "file": "artifacts/research/engine_real/members_v154.parquet",
            "books_file": "artifacts/research/engine_real/books_v154.parquet",
            "opens_file": "artifacts/research/engine_real/opens_v154.parquet",
            "max_abs_diff_avg_vs_books": max_abs_diff,
            "p3_vs_books_max_abs_diff": 0.0,
            "union_bars": union_bars,
            "columns": cols,
        },
        "engine": {
            "file": "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py",
            "maker": eu.MAKER,
            "taker": eu.TAKER,
            "d_limit_variants": [[float(d), int(w)] for d, w in VARIANTS],
            "fund_long": eu.FUND_LONG,
            "rungs": list(eu.RUNGS),
            "size": eu.SIZE,
            "s_ref": eu.S_REF,
            "m_sl": M_SL,
            "m_sleeve_sl": float(M_SLEEVE_SL),
            "m_sleeve_tp_mult": 1.0,
            "target": 0.25,
            "cap": 2.0,
        },
        "rows": rows,
        "selection_rule": "best monthly_dev4 among rows with gate_dd <= 20 and no losing year in the first four anchor years",
        "eligible": sorted(eligible),
        "selection": selection,
    }
    AUD.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print(f"saved {OUT}", flush=True)


if __name__ == "__main__":
    main()
