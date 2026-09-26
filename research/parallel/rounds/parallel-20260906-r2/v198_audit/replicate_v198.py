"""v198 blind audit Part A replication.

Blind rule: does NOT read research v198 files, the v198 result json, nor
the v198 pipeline source, until replication.json is saved. Independent
implementation from OPENCODE_V198_AUDIT.md, using
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
as the gate engine base (itself a direct implementation of the AGENTS.md
2026-09-27 user goal, gate cost model and current execution assumptions).
Base: the v197 replication in v197_audit (P2 books, book m = 4, sleeve
rung size x1.5 via size_mult = 1.5, stop-risk budget X = 0.12).
Run from the repository root so every data path below stays relative.

A: TSMOM book T: for each major j and decision t on the 4h opens panel
(artifacts/research/engine_real/opens_v154.parquet, sorted): signal = mean
over L in (180, 540, 1080) of sign(open_t / open_{t-L} - 1); vol = std of
42 4h open pct changes * sqrt(2190); T = clip(signal * 0.20 / vol / 5,
-0.5, 0.5), reindexed to the books index (missing -> 0). Pipelines:
v151 = (A+B)/2, 0.75 v151 + 0.25 T, 0.5 v151 + 0.5 T, each with the v197
sleeve under engine_user (book SL/TP m = 4, 10 bps limits resting minutes
2..238, target 0.25, cap 2.0, gap 0.02, size_mult = 1.5, X = 0.12).
Report per pipeline: monthly_dev4, 5y, last year, yearly nets and 1m DDs,
gate DD, rungs, stops/TPs, liquidation count; selection = best dev4 with
DD <= 20 and no losing year in the first four years. Save replication.json.

Frozen engine_user spec (from OPENCODE_V193_AUDIT.md via v193/v197 audits,
re-stated here so the audit is self-contained):
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
     levels reset at each decision; checked from minute 0 on the position
     held (before the fill) and from the fill minute on the new position;
     SL if low <= SL (long), filled at min(SL, minute open), taker
     0.00055; TP on high > TP (strict), maker 0.0002; both in one minute ->
     SL first; after SL/TP the asset is flat for the rest of the bar and
     the pending order is cancelled if not yet filled.
  E5 Funding (gate): a long held at the end of the bar pays 0.0001 of its
     notional if T + 4h is 00/08/16 UTC; shorts 0. No carry sleeve.
  E6 Dip sleeve (v197 setting): rungs k_rung = 2.5/3/3.5/4 with sigma_4h
     (not daily), bid L = open(T) (1 - k_rung sigma_4h) live minutes
     16..238, maker fill on low < L (strict); exits after the fill minute:
     SL at L (1 - 5 sigma_4h) (low <= SL, fill min(SL, open), taker
     0.00055), TP at L (1 + sigma_4h) (high > TP strict, maker 0.0002),
     else at open(T+4h) taker paying 0.0001 if that is a settlement; rung
     notional rn = s g mult 0.25/4/1.657 via size_mult = mult = 1.5; fills
     taken in (minute, rung, asset) order iff risk_open + risk_new <= X
     where risk = rn * (5 sigma_4h(asset) + 0.02) summed over taken rungs
     still open at the fill minute (exit > f); X = 0.12.
  E7 1m-marked equity per minute = start equity * (1 + position MTM +
     sleeve MTM); gate DD = max(4h-close DD, 1m-marked DD); per anchor year
     net/monthly; monthly_dev4 = geometric mean of the first four anchor
     years (monthly % = 100 * ((1+geo) ** (1/12) - 1)).
  E8 Rows: V151 = (A+B)/2, B75 = 0.75 V151 + 0.25 T, B50 = 0.5 V151 +
     0.5 T, each with sleeve on, m = 4, sleeve SL k = 5, book limit
     (d, W) = (0.001, 239), target 0.25, cap 2.0, gap 0.02, mult 1.5,
     X = 0.12 with size_mult = 1.5; selection = best monthly_dev4 among
     rows with gate DD <= 20 and no losing year in the first four years.

Leakage notes (checked in code, reported in COMPARISON.md Part B):
  L1 Feature timing: pipeline books at t, TSMOM signal/vol use only opens
     with timestamps <= t (shift/rolling on the sorted opens panel), opens
     at t/t-1, sigma windows ending at t, s/g known at the decision; cubes
     row i = holding bar T.
  L2 No label window: no forward return is read except through fills and
     the bar-close settlement/exit prices at T/T+4h.
  L3 Fit windows: member books are pre-fit causal inputs; TSMOM has no fit
     parameters (fixed L set, fixed 42-bar vol, fixed 0.20/5 scale and
     0.5 clip); no statistic is fit on any test year inside this script
     (vol/governor are running causal filters; selection uses
     first-four-years metrics only; blends (1.0, 0.75/0.25, 0.5/0.5) were
     pre-registered, not tuned).
  L4 Fill timing: book limit minutes 2..238 strict trade-through, SL/TP
     from minute 0 (held) / fill minute (new), sleeve trigger 16..238 and
     exits strictly after the fill minute, stop-first within a minute.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2") / "v198_audit"
OUT = AUD / "replication.json"
CACHE = Path("artifacts/research/engine_real")
OPENS_FILE = CACHE / "opens_v154.parquet"
BOOKS_FILE = CACHE / "books_v154.parquet"
MEMBERS_FILE = CACHE / "members_v154.parquet"

M_SL = 4.0
M_SLEEVE_SL = 5.0
D_LIMIT = 0.001
WIN_END = 239
GAP = 0.02
TARGET = 0.25
CAP = 2.0
SIZE_MULT = 1.5
SLEEVE_X = 0.12
LOOKBACKS = (180, 540, 1080)
VOL_WIN = 42
ANN = 2190
VOL_TARGET = 0.20
N_ASSETS = 5
CLIP = 0.5


def _load_engine_user():
    spec = importlib.util.spec_from_file_location(
        "v198_audit_engine_user",
        Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def compute_tsmom(opens_sorted: pd.DataFrame) -> pd.DataFrame:
    """Causal TSMOM book T on the sorted 4h opens panel.

    signal[t,j] = mean over L of sign(open[t,j]/open[t-L,j]-1);
    vol[t,j] = std of the trailing 42 4h pct changes ending at t * sqrt(2190);
    T[t,j] = clip(signal*0.20/vol/5, -0.5, 0.5), NaN/inf -> 0.
    Every input at row t uses only opens with timestamps <= t.
    """
    tsmom = pd.DataFrame(index=opens_sorted.index, columns=opens_sorted.columns, dtype=float)
    for col in opens_sorted.columns:
        o = opens_sorted[col]
        pct = o / o.shift(1) - 1
        vol = pct.rolling(VOL_WIN, min_periods=VOL_WIN).std() * np.sqrt(ANN)
        signs = []
        for L in LOOKBACKS:
            ret = o / o.shift(L) - 1
            signs.append(np.sign(ret))
        sig = pd.concat(signs, axis=1).mean(axis=1, skipna=True)
        raw = sig * VOL_TARGET / vol / N_ASSETS
        clipped = raw.clip(lower=-CLIP, upper=CLIP)
        tsmom[col] = clipped.fillna(0.0).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    return tsmom


def main():
    eu = _load_engine_user()
    print(f"engine_user maker={eu.MAKER} taker={eu.TAKER} fund_long={eu.FUND_LONG}", flush=True)
    assert eu.MAKER == 0.0002 and eu.TAKER == 0.00055 and eu.FUND_LONG == 0.0001
    assert eu.D_LIMIT == 0.001 and eu.SIZE == 0.25 and eu.S_REF == 1.657
    assert tuple(eu.RUNGS) == (2.5, 3.0, 3.5, 4.0)

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
    V151 = ((Au + Bu) / 2).sort_index()
    assert list(V151.index) == list(books_cache.index)
    assert list(V151.columns) == cols

    opens = pd.read_parquet(OPENS_FILE).sort_index()
    print(f"pipeline V151 {V151.shape} opens {opens.shape}", flush=True)

    T_full = compute_tsmom(opens)
    T = T_full.reindex(V151.index).reindex(columns=cols).fillna(0.0)
    assert list(T.index) == list(V151.index)
    assert list(T.columns) == cols

    # TSMOM summary on the books span (for replication.json)
    t_abs_mean = float(T.abs().mean().mean())
    t_mean = float(T.mean().mean())
    t_clip_frac = float(((T.abs() >= CLIP - 1e-12) & (T.abs() > 0)).mean().mean())
    t_nonzero_frac = float((T.abs() > 0).mean().mean())
    print(f"TSMOM books-span mean={t_mean:.5f} abs_mean={t_abs_mean:.5f} "
          f"clipped_frac={t_clip_frac:.4f} nonzero_frac={t_nonzero_frac:.4f}", flush=True)

    pipelines = {
        "V151": V151,
        "BLEND75_25": 0.75 * V151 + 0.25 * T,
        "BLEND50_50": 0.50 * V151 + 0.50 * T,
    }

    prep = eu.prepare(V151, opens)
    print(f"prepared cubes O {prep['O'].shape}", flush=True)

    rows = {}
    for key, books in pipelines.items():
        # prep cubes depend only on idx/cols (same for all rows); vol/s use books arg
        print(f"simulate {key} m_sl={M_SL} d={D_LIMIT} W={WIN_END} "
              f"size_mult={SIZE_MULT} X={SLEEVE_X} ...", flush=True)
        out = eu.simulate(
            books, opens, prep,
            m_sl=M_SL, m_sleeve_sl=float(M_SLEEVE_SL),
            sleeve=True, target=float(TARGET), cap=float(CAP),
            d_limit=float(D_LIMIT), win_end=int(WIN_END),
            sleeve_risk_budget=float(SLEEVE_X), gap=float(GAP),
            size_mult=float(SIZE_MULT),
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
        blend = {"V151": [1.0, 0.0], "BLEND75_25": [0.75, 0.25], "BLEND50_50": [0.5, 0.5]}[key]
        rows[key] = {
            "pipeline": key,
            "books": "V151=(A+B)/2" if key == "V151" else f"{blend[0]}*V151+{blend[1]}*T",
            "blend_v151": blend[0],
            "blend_tsmom": blend[1],
            "sleeve": True,
            "m_sl": M_SL,
            "m_sleeve_sl": float(M_SLEEVE_SL),
            "d_limit": float(D_LIMIT),
            "win_end": int(WIN_END),
            "target": float(TARGET),
            "cap": float(CAP),
            "size_mult": float(SIZE_MULT),
            "mult": float(SIZE_MULT),
            "sleeve_risk_budget": float(SLEEVE_X),
            "gap": float(GAP),
            "rung_notional": "s * g * mult * 0.25/4/1.657",
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
            "stats": out["stats"],
        }
        print(f"{key}: dev4={out['monthly_dev4']} 5y={out['monthly_5y']} "
              f"last={out['monthly_last_year']} gateDD={out['gate_dd']} "
              f"lose={out['losing_years']} lose4={losing_first4} "
              f"nets={[y['net_pct'] for y in yearly]} "
              f"rungs={out['stats']['rungs']} rung_stops={out['stats']['rung_stops']} "
              f"rung_tps={out['stats']['rung_tps']} liq={out['stats']['liq']}", flush=True)

    eligible = {k: v for k, v in rows.items()
                if v["gate_dd"] <= 20 and v["losing_years_first4"] == 0}
    selection = max(eligible, key=lambda k: eligible[k]["monthly_dev4"]) if eligible else None
    print(f"eligible {sorted(eligible)} selection {selection}", flush=True)

    replication = {
        "version": "v198_audit_replication",
        "blind": "did_not_open_research_v198_until_this_file_saved",
        "books": "V151=(A+B)/2 from cached v154 members; T=TSMOM on opens_v154; blends 0.75/0.25 and 0.5/0.5",
        "members_check": {
            "file": "artifacts/research/engine_real/members_v154.parquet",
            "books_file": "artifacts/research/engine_real/books_v154.parquet",
            "opens_file": "artifacts/research/engine_real/opens_v154.parquet",
            "max_abs_diff_avg_vs_books": max_abs_diff,
            "union_bars": union_bars,
            "columns": cols,
        },
        "tsmom": {
            "opens_file": "artifacts/research/engine_real/opens_v154.parquet",
            "sorted": True,
            "lookbacks": list(LOOKBACKS),
            "vol_window": VOL_WIN,
            "annualization": ANN,
            "vol_target": VOL_TARGET,
            "divisor": N_ASSETS,
            "clip": CLIP,
            "causal": "shift/rolling on sorted opens; reindexed to books index missing->0",
            "books_span_mean": t_mean,
            "books_span_abs_mean": t_abs_mean,
            "books_span_clipped_frac": t_clip_frac,
            "books_span_nonzero_frac": t_nonzero_frac,
        },
        "engine": {
            "file": "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py",
            "maker": eu.MAKER,
            "taker": eu.TAKER,
            "d_limit": float(D_LIMIT),
            "win_end": int(WIN_END),
            "fund_long": eu.FUND_LONG,
            "rungs": list(eu.RUNGS),
            "size": eu.SIZE,
            "s_ref": eu.S_REF,
            "m_sl": M_SL,
            "m_sleeve_sl": float(M_SLEEVE_SL),
            "m_sleeve_tp_mult": 1.0,
            "target": float(TARGET),
            "cap": float(CAP),
            "gap": float(GAP),
            "size_mult": float(SIZE_MULT),
            "sleeve_risk_budget": float(SLEEVE_X),
            "rung_notional": "s * g * mult * 0.25/4/1.657 via size_mult = mult",
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
