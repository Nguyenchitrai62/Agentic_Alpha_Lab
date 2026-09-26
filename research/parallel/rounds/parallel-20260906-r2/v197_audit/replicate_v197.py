"""v197 blind audit Part A replication.

Blind rule: does NOT read research v197 files, the v197 result json, nor
the v197 pipeline source, until replication.json is saved. Independent
implementation from OPENCODE_V197_AUDIT.md, using
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
as the gate engine base (itself a direct implementation of the AGENTS.md
2026-09-27 user goal, gate cost model and current execution assumptions).
Base: the v193 replication in v193_audit (P2 books, book m = 4, sleeve
rung SL 5 sigma, TP L(1 + sigma), limit 10 bps resting minutes 2..238).
Run from the repository root so every data path below stays relative.

A: v193 pipeline (books vol target 0.25) with rung notional
rn = s g mult 0.25/4/1.657 and stop-risk budget X = 0.08 * mult,
mult = 1, 1.5, 2. The books vol target changes s = min(0.25/vol, 2) on
the books leg; the sleeve rung notional scales with the same s and g
times size_mult = mult (engine_user size_mult branch); the budget scales
as X = 0.08 * mult. Report per mult: monthly_dev4, 5y, last year, yearly
nets and 1m DDs, gate DD, rungs, stops/TPs, liquidation count; selection
= best dev4 with DD <= 20 and no losing year in the first four years.
Also report for the selected mult: the 10 worst 1m-marked bars (dates,
book vs sleeve), stop gaps (book/sleeve counts, max gap, equity drag),
and the liquidation-check margin at the worst minute. Save
replication.json.

Frozen engine_user spec (from OPENCODE_V193_AUDIT.md via v193/v194/v195
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
     rn = s g mult 0.25/4/1.657 via size_mult = mult; fills taken in
     (minute, rung, asset) order iff risk_open + risk_new <= X where
     risk = rn * (5 sigma_4h(asset) + 0.02) summed over taken rungs still
     open at the fill minute (exit > f); X = 0.08 * mult.
  E7 1m-marked equity per minute = start equity * (1 + position MTM +
     sleeve MTM); gate DD = max(4h-close DD, 1m-marked DD); per anchor year
     net/monthly; monthly_dev4 = geometric mean of the first four anchor
     years (monthly % = 100 * ((1+geo) ** (1/12) - 1)).
  E8 Rows: P2 = (A+B)/2 with sleeve on, m = 4, sleeve SL k = 5, book limit
     (d, W) = (0.001, 239), target 0.25, cap 2.0, gap 0.02,
     (mult, X) in ((1, 0.08), (1.5, 0.12), (2, 0.16)) with
     size_mult = mult; selection = best monthly_dev4 among rows with gate
     DD <= 20 and no losing year in the first four anchor years.

Leakage notes (checked in code, reported in COMPARISON.md Part B):
  L1 Feature timing: pipeline books at t, opens at t/t-1, sigma windows
     ending at t, s/g known at the decision; cubes row i = holding bar T.
  L2 No label window: no forward return is read except through fills and
     the bar-close settlement/exit prices at T/T+4h.
  L3 Fit windows: member books are pre-fit causal inputs; no statistic is
     fit on any test year inside this script (vol/governor are running
     causal filters; selection uses first-four-years metrics only; mult
     in (1, 1.5, 2) with X = 0.08 * mult was pre-registered, not tuned).
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

AUD = Path("research/parallel/rounds/parallel-20260906-r2") / "v197_audit"
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
MULTS = (1.0, 1.5, 2.0)


def _key(mult):
    return f"P2_M{int(round(mult * 100)):03d}"


def _load_engine_user():
    spec = importlib.util.spec_from_file_location(
        "v197_audit_engine_user",
        Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def instrumented_run(eu, P2, opens, prep, mult, X):
    """Line-exact copy of engine_user.simulate with diagnostics (no behavior change).

    Collects per-live-bar 1m paths split book/sleeve, stop gap fills, and
    the liquidation-check margin at each bar (threshold MMR * gross).
    """
    from copy import deepcopy

    idx, cols = prep["idx"], prep["cols"]
    O, H, L, C = prep["O"], prep["H"], prep["L"], prep["C"]
    sig4, o1, o2, settle = prep["sig4"], prep["o1"], prep["o2"], prep["settle"]
    B = P2.to_numpy()
    na, n = len(cols), len(idx)
    o = opens.reindex(idx)[cols]
    v99, v110 = eu.er.v99, eu.er.v110
    realized = v99.W_BOOKS * (P2.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
    vol = (realized.rolling(60 * eu.PD, min_periods=20 * eu.PD).std() * np.sqrt(eu.PD * 365)).to_numpy()
    s = np.where(np.isnan(vol), 1.0, np.minimum(TARGET / np.where(np.isnan(vol), 1.0, vol), CAP))
    live = np.asarray((idx >= v110.START) & (idx < v110.END))
    mins = np.array([eu.MIN_NOTIONAL.get(c, 5.0) for c in cols])
    net = np.zeros(n)
    g = np.ones(n)
    eq = np.ones(n)
    eq_min = np.ones(n)
    w = np.zeros(na)
    entry = np.full(na, np.nan)
    stats = dict(fills=0, unfilled=0, stops=0, tps=0, rungs=0, rung_stops=0, rung_tps=0, liq=0, fees=0.0, funding=0.0)

    book_gap_events = []
    sleeve_gap_events = []
    per_bar = []

    for i in range(n):
        if i >= 2:
            j = i - 2
            peak = eq[max(0, j - 90 * eu.PD + 1): j + 1].max()
            g[i] = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0.0, 1.0))
        prev_eq = eq[i - 1] if i else 1.0
        if not live[i] or not np.all(np.isfinite(o1[i])) or not np.all(np.isfinite(o2[i])):
            eq[i] = prev_eq
            eq_min[i] = prev_eq
            continue
        tgt = v99.W_BOOKS * s[i] * B[i] * g[i]
        sd = sig4[i] * np.sqrt(6)
        cash = 0.0
        q = w / o1[i]
        path = np.zeros(240)
        book_path = np.zeros(240)
        sleeve_path = np.zeros(240)
        for a in range(na):
            Oa, Ha, La, Ca = (X_[i, :, a].astype(float) for X_ in (O, H, L, C))
            if not np.isfinite(Oa[0]):
                continue
            qa, ea = q[a], entry[a]
            dw = tgt[a] - w[a]
            fill_min, fill_px = 999, np.nan
            if abs(dw) * prev_eq * eu.ACCOUNT >= mins[a] or (tgt[a] == 0 and w[a] != 0):
                lim = Oa[0] * (1 - D_LIMIT) if dw > 0 else Oa[0] * (1 + D_LIMIT)
                win = La[2:WIN_END] < lim if dw > 0 else Ha[2:WIN_END] > lim
                if win.any():
                    fill_min, fill_px = 2 + int(np.argmax(win)), lim
                    stats["fills"] += 1
                else:
                    stats["unfilled"] += 1
            dq = dw / o1[i][a] if fill_min < 999 else 0.0
            qarr = np.full(240, qa)
            carr = np.zeros(240)
            cur_q, cur_e = qa, ea

            def levels(qq, ee):
                if qq == 0 or not np.isfinite(ee) or not np.isfinite(sd[a]):
                    return None, None
                if qq > 0:
                    return ee * (1 - M_SL * sd[a]), ee * (1 + 2 * M_SL * sd[a])
                return ee * (1 + M_SL * sd[a]), ee * (1 - 2 * M_SL * sd[a])

            def first_exit(qq, lo_m, hi_m):
                sl, tp = levels(qq, cur_e)
                if sl is None or hi_m <= lo_m:
                    return None
                Ls, Hs = La[lo_m:hi_m], Ha[lo_m:hi_m]
                hs = Ls <= sl if qq > 0 else Hs >= sl
                ht = Hs > tp if qq > 0 else Ls < tp
                hit = hs | ht
                if not hit.any():
                    return None
                k = int(np.argmax(hit))
                mm = lo_m + k
                if hs[k]:
                    px = min(sl, Oa[mm]) if qq > 0 else max(sl, Oa[mm])
                    return mm, px, eu.TAKER, "stops"
                return mm, tp, eu.MAKER, "tps"

            def apply_exit(ev):
                nonlocal cur_q, cur_e
                mm, px, fee, kind = ev
                if kind == "stops":
                    sl, _ = levels(cur_q, cur_e)
                    if cur_q > 0 and px < sl - 1e-12:
                        book_gap_events.append((i, cols[a], "long", float(sl), float(px),
                                                float((sl - px) / cur_e), float(abs(cur_q) * (sl - px))))
                    elif cur_q < 0 and px > sl + 1e-12:
                        book_gap_events.append((i, cols[a], "short", float(sl), float(px),
                                                float((px - sl) / cur_e), float(abs(cur_q) * (px - sl))))
                carr[mm:] += cur_q * px - abs(cur_q) * px * fee
                stats["fees"] += abs(cur_q) * px * fee
                stats[kind] += 1
                qarr[mm:] = 0.0
                cur_q, cur_e = 0.0, np.nan

            seg_end = fill_min if fill_min < 240 else 240
            ev = first_exit(cur_q, 0, seg_end)
            if ev is not None:
                apply_exit(ev)
            elif fill_min < 240:
                new_q = cur_q + dq
                if cur_q == 0 or np.sign(new_q) != np.sign(cur_q):
                    cur_e = fill_px if new_q != 0 else np.nan
                elif abs(new_q) > abs(cur_q):
                    cur_e = (abs(cur_q) * cur_e + abs(dq) * fill_px) / abs(new_q)
                carr[fill_min:] -= dq * fill_px + abs(dq) * fill_px * eu.MAKER
                stats["fees"] += abs(dq) * fill_px * eu.MAKER
                qarr[fill_min:] = new_q
                cur_q = new_q
                ev = first_exit(cur_q, fill_min, 240)
                if ev is not None:
                    apply_exit(ev)
            val_path = carr + qarr * Ca - qa * o1[i][a]
            pnl_cash = carr[-1]
            end_val = pnl_cash + cur_q * o2[i][a]
            fund = eu.FUND_LONG * max(cur_q, 0.0) * o2[i][a] if settle[i] else 0.0
            stats["funding"] += fund
            path += val_path
            book_path += val_path
            cash += end_val - qa * o1[i][a] - fund
            q[a], entry[a] = cur_q, cur_e
        sleeve_pnl = 0.0
        rn = s[i] * g[i] * float(mult) * eu.SIZE / len(eu.RUNGS) / eu.S_REF
        fills = []
        for r, k in enumerate(eu.RUNGS):
            for a in range(na):
                if not np.isfinite(sig4[i][a]):
                    continue
                lv = o1[i][a] * (1 - k * sig4[i][a])
                hit = L[i, 16:239, a].astype(float) < lv
                if hit.any():
                    fills.append((16 + int(np.argmax(hit)), r, a, lv))
        fills.sort()
        taken = []
        for f, r, a, lv in fills:
            risk_open = sum(rn * (M_SLEEVE_SL * sig4[i][t[2]] + GAP) for t in taken if t[4] > f)
            if risk_open + rn * (M_SLEEVE_SL * sig4[i][a] + GAP) > X + 1e-12:
                continue
            Ha, La, Ca, Oa = (X_[i, :, a].astype(float) for X_ in (H, L, C, O))
            tp = lv * (1 + sig4[i][a])
            sl = lv * (1 - M_SLEEVE_SL * sig4[i][a])
            x, ret = 240, None
            if f + 1 < 240:
                hs = La[f + 1:240] <= sl
                ht = Ha[f + 1:240] > tp
                hit = hs | ht
                if hit.any():
                    k = int(np.argmax(hit))
                    x = f + 1 + k
                    if hs[k]:
                        ret = min(sl, Oa[x]) / lv - 1 - eu.MAKER - eu.TAKER
                        stats["rung_stops"] += 1
                        if Oa[x] < sl - 1e-12:
                            sleeve_gap_events.append((i, cols[a], r, float(sl), float(Oa[x]),
                                                      float((sl - Oa[x]) / lv),
                                                      float(rn * (sl - Oa[x]) / lv)))
                    else:
                        ret = tp / lv - 1 - 2 * eu.MAKER
                        stats["rung_tps"] += 1
            if ret is None:
                ret = o2[i][a] / lv - 1 - eu.MAKER - eu.TAKER - (eu.FUND_LONG if settle[i] else 0.0)
            taken.append((f, r, a, lv, x, ret))
            sleeve_pnl += rn * ret
            seg = np.zeros(240)
            end = min(x, 240)
            seg[f:end] = Ca[f:end] / lv - 1
            if x < 240:
                seg[x:] = ret
            path += rn * seg
            sleeve_path += rn * seg
        stats["rungs"] += len(taken)
        pnl = cash + sleeve_pnl
        eq[i] = prev_eq * (1 + pnl)
        eq_min[i] = prev_eq * (1 + min(0.0, float(path.min())))
        gross = float(np.abs(q * o2[i]).sum()) + eu.N_MAX
        liq_thr = eu.MMR * max(gross, 1e-9)
        liq_margin = float(1 + float(path.min())) - float(liq_thr)
        liq_flag = bool(1 + float(path.min()) < liq_thr)
        if liq_flag:
            stats["liq"] += 1
        end_eq_rel = 1 + pnl
        w = np.where(np.isfinite(o2[i]), q * o2[i] / end_eq_rel, 0.0)
        net[i] = pnl
        if live[i]:
            m = int(np.argmin(path))
            per_bar.append(dict(pos=i, date=str(idx[i]), net=float(pnl), book=float(cash),
                                sleeve=float(sleeve_pnl), path_min=float(path.min()),
                                path_min_minute=m, book_at_min=float(book_path[m]),
                                sleeve_at_min=float(sleeve_path[m]),
                                gross=float(gross), liq_threshold=float(liq_thr),
                                liq_margin=float(liq_margin), liq_flag=bool(liq_flag)))
    return dict(net=net, eq=eq, eq_min=eq_min, g=g, stats=deepcopy(stats), per_bar=per_bar,
                book_gaps=list(book_gap_events), sleeve_gaps=list(sleeve_gap_events))


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
    P2 = ((Au + Bu) / 2).sort_index()
    assert list(P2.index) == list(books_cache.index)
    assert list(P2.columns) == cols

    opens = pd.read_parquet(OPENS_FILE).sort_index()
    print(f"pipeline P2 {P2.shape} opens {opens.shape}", flush=True)

    prep = eu.prepare(P2, opens)
    print(f"prepared cubes O {prep['O'].shape}", flush=True)

    rows = {}
    for mult in MULTS:
        x = 0.08 * mult
        key = _key(mult)
        print(f"simulate {key} mult={mult} X={x} m_sl={M_SL} d={D_LIMIT} W={WIN_END} ...", flush=True)
        out = eu.simulate(
            P2, opens, prep,
            m_sl=M_SL, m_sleeve_sl=float(M_SLEEVE_SL),
            sleeve=True, target=float(TARGET), cap=float(CAP),
            d_limit=float(D_LIMIT), win_end=int(WIN_END),
            sleeve_risk_budget=float(x), gap=float(GAP),
            size_mult=float(mult),
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
        rows[key] = {
            "pipeline": "P2",
            "sleeve": True,
            "m_sl": M_SL,
            "m_sleeve_sl": float(M_SLEEVE_SL),
            "d_limit": float(D_LIMIT),
            "win_end": int(WIN_END),
            "target": float(TARGET),
            "cap": float(CAP),
            "size_mult": float(mult),
            "mult": float(mult),
            "sleeve_risk_budget": float(x),
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

    # ---- selected-mult diagnostics: worst 1m-marked bars, stop gaps, liq margin ----
    sel_mult = rows[selection]["mult"] if selection else None
    sel_x = rows[selection]["sleeve_risk_budget"] if selection else None
    diag = instrumented_run(eu, P2, opens, prep, float(sel_mult), float(sel_x))
    rep_stats = rows[selection]["stats"]
    for k in ("fills", "unfilled", "stops", "tps", "rungs", "rung_stops", "rung_tps", "liq"):
        assert diag["stats"][k] == rep_stats[k], (k, diag["stats"][k], rep_stats[k])
    assert abs(round(float(diag["stats"]["fees"]), 4) - float(rep_stats["fees"])) < 1e-9
    assert abs(round(float(diag["stats"]["funding"]), 4) - float(rep_stats["funding"])) < 1e-9
    worst = sorted(diag["per_bar"], key=lambda b: b["path_min"])[:10]
    worst_out = [dict(date=w["date"], path_min=round(w["path_min"], 5), minute=w["path_min_minute"],
                      book_at_min=round(w["book_at_min"], 5), sleeve_at_min=round(w["sleeve_at_min"], 5),
                      net=round(w["net"], 5), book=round(w["book"], 5), sleeve=round(w["sleeve"], 5),
                      gross=round(w["gross"], 5), liq_threshold=round(w["liq_threshold"], 6),
                      liq_margin=round(w["liq_margin"], 5), liq_flag=w["liq_flag"]) for w in worst]

    def gap_stats(events):
        gaps = [e[-2] for e in events]
        drags = [e[-1] for e in events]
        return dict(n=len(events), total_gap_rel=float(sum(gaps)) if gaps else 0.0,
                    max_gap_rel=float(max(gaps)) if gaps else 0.0,
                    mean_gap_rel=float(sum(gaps) / len(gaps)) if gaps else 0.0,
                    total_equity_drag=float(sum(drags)) if drags else 0.0,
                    max_equity_drag=float(max(drags)) if drags else 0.0)

    book_gaps = gap_stats(diag["book_gaps"])
    sleeve_gaps = gap_stats(diag["sleeve_gaps"])
    worst_bar = worst[0]
    print(f"selected {selection} worst bar {worst_bar['date']} path_min={worst_bar['path_min']} "
          f"book={worst_bar['book_at_min']} sleeve={worst_bar['sleeve_at_min']} "
          f"liq_margin={worst_bar['liq_margin']} liq_flag={worst_bar['liq_flag']}", flush=True)
    print(f"book gaps {book_gaps} sleeve gaps {sleeve_gaps}", flush=True)

    replication = {
        "version": "v197_audit_replication",
        "blind": "did_not_open_research_v197_until_this_file_saved",
        "books": "pipeline P2=(A+B)/2 from cached v154 members",
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
            "rungs": list(eu.RUNGS),
            "size": eu.SIZE,
            "s_ref": eu.S_REF,
            "m_sl": M_SL,
            "m_sleeve_sl": float(M_SLEEVE_SL),
            "m_sleeve_tp_mult": 1.0,
            "target": float(TARGET),
            "cap": float(CAP),
            "gap": float(GAP),
            "mults": list(MULTS),
            "sleeve_risk_budgets": [0.08 * m for m in MULTS],
            "rung_notional": "s * g * mult * 0.25/4/1.657 via size_mult = mult",
        },
        "rows": rows,
        "selection_rule": "best monthly_dev4 among rows with gate_dd <= 20 and no losing year in the first four anchor years",
        "eligible": sorted(eligible),
        "selection": selection,
        "selected_diagnostics": {
            "key": selection,
            "mult": sel_mult,
            "sleeve_risk_budget": sel_x,
            "stats_match_simulate": True,
            "worst_10_1m_marked_bars": worst_out,
            "worst_minute_liquidation_check": dict(
                date=worst_bar["date"], minute=worst_bar["path_min_minute"],
                path_min=round(worst_bar["path_min"], 5),
                gross=round(worst_bar["gross"], 5),
                liq_threshold=round(worst_bar["liq_threshold"], 6),
                liq_margin=round(worst_bar["liq_margin"], 5),
                liq_flag=worst_bar["liq_flag"],
                mmr=eu.MMR, n_max=eu.N_MAX,
                rule="liq if 1 + path_min < MMR * gross with gross = |q*o2|.sum() + N_MAX"),
            "book_stop_gaps": book_gaps,
            "sleeve_stop_gaps": sleeve_gaps,
        },
    }
    AUD.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print(f"saved {OUT}", flush=True)


if __name__ == "__main__":
    main()
