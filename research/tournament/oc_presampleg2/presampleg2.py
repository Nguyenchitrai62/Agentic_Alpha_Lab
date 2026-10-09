"""oc_presampleg2 Part B: full-G2-mechanics replay on pre-sample years (replica level).

Frozen by PLAN.md (read it first). Dip leg = the oc_presample2 G2 core, used by
IMPORT (never edited, never copied); the G1 gate requires our driver's dip-only
mode (DIP0) to reproduce all 16 oc_presample2 G2 cells bit-for-bit on
CELL_FIELDS before any PB number is looked at. Book leg = the PLAN-frozen
mechanics (ONE resting limit 10 bps, live minutes 5..59, strict trade-through,
expire unfilled; SL=entry*(1-/+3*sg_d) market taker + TP=entry*(1+/-6*sg_d)
limit maker, stop-first; gate costs; adverse funding; shared within-bar gross
cap 2.0; R2 agent size = scale = governor = 1 pre-2020).

  python research/tournament/oc_presampleg2/presampleg2.py gate     # G1: DIP0 vs oc_presample2 G2
  python research/tournament/oc_presampleg2/presampleg2.py rows PB  # PB (+BOOK0/DIP0) cells
  python research/tournament/oc_presampleg2/presampleg2.py finalize # results.json

Run under heavy_slot (tag oc_presampleg2). CPU only. Progress per leg/phase.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
TMP = HERE / "tmp"

P2 = importlib.util.spec_from_file_location(
    "p2core", ROOT / "research/tournament/oc_presample2/presample2.py")
p2 = importlib.util.module_from_spec(P2)
P2.loader.exec_module(p2)

# ---- frozen G2 dip constants (imported, not restated) ----
MAKER, TAKER, FUND = p2.MAKER, p2.TAKER, p2.FUND
U, GCAP = p2.U, p2.GCAP
RUNGS = p2.RUNGS
LIVE_A, LIVE_B = p2.LIVE_A, p2.LIVE_B
M_SL = p2.M_SL
SETTLE_HOURS = p2.SETTLE_HOURS
MAJORS4 = p2.MAJORS4
LEGS = p2.LEGS
PHASES = p2.PHASES
CELL_FIELDS = p2.CELL_FIELDS

# ---- frozen book-leg constants (PLAN.md: engine_user defaults) ----
D_LIM_BPS = 0.001      # limit 10 bps better than the minute-0 price
BOOK_LIVE_A, BOOK_LIVE_B = 5, 59   # no fill in the first 5 min (user rule)
BOOK_M_SL, BOOK_M_TP = 3.0, 6.0    # engine_user defaults m_sl=3.0, TP=2*m
BOOK_CAP = 2.0         # shared within-bar gross cap (G2 cap; disclosed proxy)


def book_levels(entry: float, side: float, sgd: float):
    """Book SL/TP from the avg entry (engine_user defaults m_sl=3.0, TP=2*m):
    long SL = entry*(1-3*sg_d), TP = entry*(1+6*sg_d); short mirrored."""
    sl = entry * (1 - side * BOOK_M_SL * sgd)
    tp = entry * (1 + side * BOOK_M_TP * sgd)
    return sl, tp


def book_targets_for_phase(books: pd.DataFrame, bts: pd.DatetimeIndex):
    """Causal asof join of the standard-grid book onto a phase grid: the target
    at decision bar T is the last PB row with row_t + 4h <= T (known at its
    close; conservative one-bar lag on the aligned phase, disclosed)."""
    avail = books.index + pd.Timedelta(hours=4)
    pos = np.searchsorted(avail.values.astype("datetime64[ns]").astype(np.int64),
                          bts.values.astype("datetime64[ns]").astype(np.int64),
                          side="right") - 1
    W = np.zeros((len(bts), len(MAJORS4)))
    ok = pos >= 0
    W[ok] = books.to_numpy()[np.clip(pos[ok], 0, len(books) - 1)]
    W[~ok] = 0.0
    return {s: W[:, i] for i, s in enumerate(MAJORS4)}


def book_sig_d(opens_bar: dict) -> dict:
    """Daily sigma per coin on the phase grid: std of 4h open-to-open over 360
    bars (min 120, shift 1, same convention as the dip sigma) * sqrt(6). NaN
    (warm-up) -> no SL/TP that bar (position rides; disclosed)."""
    out = {}
    for s, oo in opens_bar.items():
        sg = pd.Series(np.asarray(oo, dtype=float)).pct_change().rolling(
            360, min_periods=120).std(ddof=1).shift(1).to_numpy() * np.sqrt(6)
        out[s] = sg
    return out


def simulate_interval_g2(idx, D, majors, bars, opens_bar, sig_bar, S, E,
                          books_w=None, sleeve=True, label=""):
    """Combined book+dip replay for bars with open in [S, E).

    books_w: dict sym -> per-bar target weight (fraction of bar-open equity),
      aligned with `bars` order; None = dip-only (must equal p2 dip exactly).
    sleeve: False = book-only (BOOK0 attribution leg).
    Returns (cell, dip_ledger, book_ledger).
    """
    EQ = 1.0
    t_all, m_all = [], []
    fills = stops = tps = timeouts = gap_stops = 0
    wins = 0
    gap_max = 0.0
    peak_gross = 0.0
    dip_pnl_sum = 0.0
    book_pnl_sum = 0.0
    dled, bled = [], []
    b_fills = b_stops = b_tps = 0
    b_wins = 0
    # book state per coin: (weight frac of CURRENT equity, avg entry)
    pos = {s: [0.0, np.nan] for s in majors}
    sigd = book_sig_d(opens_bar) if books_w is not None else {}
    for bi, j in enumerate(bars):
        T = bars[j]
        if not (S <= T < E):
            continue
        off = int((T - idx[0]).total_seconds() // 60)
        if off + 240 >= len(idx):
            continue
        settle = (T + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
        EQ_OPEN = EQ
        o1 = {s: float(D[s]["open"][off]) for s in majors}
        # ---- drift carried book weights to bar-open equity (exact weight drift:
        # q_new = q_old*(1+r)/(1+sum q_old*r), r = open-to-open per coin) ----
        q = {}
        if books_w is not None:
            rvec = {}
            for s in majors:
                prev_open = D[s]["open"][off - 240] if off - 240 >= 0 else np.nan
                if np.isfinite(prev_open) and prev_open > 0 and np.isfinite(D[s]["open"][off]):
                    rvec[s] = float(D[s]["open"][off] / prev_open - 1)
                else:
                    rvec[s] = 0.0
            den = 1.0 + sum(pos[s][0] * rvec[s] for s in majors)
            den = den if np.isfinite(den) and den > 0 else 1.0
            for s in majors:
                q[s] = pos[s][0] * (1 + rvec[s]) / den
        # ---- BOOK decision (one resting limit order per coin) ----
        book_pnl = 0.0
        fees_book = 0.0
        q_old = dict(q) if books_w is not None else {}
        q_after = dict(q)
        entries = {s: pos[s][1] for s in majors}
        fill_min = {}
        fill_lim = {}
        marks_b = np.zeros(240)
        gross_b = np.zeros(240)
        if books_w is not None:
            for s in majors:
                tgt = float(books_w[s][bi]) if np.isfinite(books_w[s][bi]) else 0.0
                if not np.isfinite(o1[s]) or o1[s] <= 0:
                    continue
                delta = tgt - q[s]
                if abs(delta) < 1e-12:
                    continue
                # shared within-bar cap: room left under BOOK_CAP by carried book
                carried = sum(abs(q[t]) for t in majors)
                room = BOOK_CAP - carried
                if room <= 1e-12:
                    continue
                if abs(delta) > room:
                    delta = np.sign(delta) * room
                side = 1.0 if delta > 0 else -1.0
                lim = o1[s] * (1 - side * D_LIM_BPS)
                H = D[s]["high"][off + BOOK_LIVE_A:off + BOOK_LIVE_B + 1].astype(float)
                L = D[s]["low"][off + BOOK_LIVE_A:off + BOOK_LIVE_B + 1].astype(float)
                if side > 0:
                    hit = np.asarray(L, dtype=float) < lim
                else:
                    hit = np.asarray(H, dtype=float) > lim
                f = None
                if hit.any():
                    f = BOOK_LIVE_A + int(np.argmax(hit))
                if f is None:
                    bled.append((label, s, str(T), "exp",
                                 round(delta, 9), 0, ""))
                    continue
                # filled all-or-nothing at the limit (maker)
                fees_book += MAKER * abs(delta)
                w0, e0 = pos[s]
                qn = w0 + delta if w0 != 0.0 else delta
                if w0 == 0.0 or np.sign(w0) != np.sign(qn):
                    en = lim
                else:
                    en = (w0 * e0 + delta * lim) / qn if qn != 0 else lim
                q_after[s] = qn
                entries[s] = en
                fill_min[s] = f
                fill_lim[s] = lim
                b_fills += 1
                bled.append((label, s, str(T),
                             "buy" if side > 0 else "sell",
                             round(delta, 9), f, round(float(lim), 6)))
            # ---- BOOK SL/TP + exact weight-accounted marks ----
            for s in majors:
                wq = q_after[s]
                w0 = q_old[s]
                if abs(wq) < 1e-12 and abs(w0) < 1e-12:
                    continue
                if not np.isfinite(o1[s]) or o1[s] <= 0:
                    continue
                H = D[s]["high"][off:off + 240].astype(float)
                L = D[s]["low"][off:off + 240].astype(float)
                O = D[s]["open"][off:off + 240].astype(float)
                C = D[s]["close"][off:off + 240].astype(float)
                base = pd.Series(
                    np.asarray(C, dtype=float) / o1[s] - 1).ffill().fillna(0.0).to_numpy()
                f = fill_min.get(s)
                dl = wq - w0
                if f is not None and np.isfinite(fill_lim[s]) and fill_lim[s] > 0:
                    limret = pd.Series(
                        np.asarray(C, dtype=float) / fill_lim[s] - 1).ffill().fillna(0.0).to_numpy()
                else:
                    limret = None
                sgd = float(sigd[s][j]) if s in sigd and np.isfinite(sigd[s][j]) else np.nan
                can_stop = (abs(wq) >= 1e-12 and np.isfinite(entries[s])
                            and np.isfinite(sgd) and sgd > 0)
                x, how, px = 240, "hold", np.nan
                if can_stop:
                    en = float(entries[s])
                    side = 1.0 if wq > 0 else -1.0
                    sl, tp = book_levels(en, side, sgd)
                    # SL/TP levels reset at each decision from the current avg
                    # entry: a position (re)filled at minute f is checked from
                    # f; an unfilled carried position is checked from minute 0.
                    m0 = f if f is not None else 0
                    La, Ha, Oa = (np.asarray(A, dtype=float)[m0:]
                                  for A in (L, H, O))
                    if side > 0:
                        ks = np.flatnonzero(La <= sl)
                        kt = np.flatnonzero(Ha > tp)
                    else:
                        ks = np.flatnonzero(Ha >= sl)
                        kt = np.flatnonzero(La < tp)
                    ks = int(ks[0]) + m0 if len(ks) else None
                    kt = int(kt[0]) + m0 if len(kt) else None
                    if ks is not None and (kt is None or ks <= kt):
                        # stop-first (both touched in one bar -> stop)
                        x, how = ks, "stop"
                        ox = float(O[ks])
                        if side > 0:
                            px = sl if ox > sl else ox
                        else:
                            px = sl if ox < sl else ox
                    elif kt is not None:
                        x, how = kt, "tp"
                        px = tp
                end = min(x, 240)
                contrib = np.zeros(240)
                # pre-fill minutes: old weight on base returns
                pre = w0 * base
                if f is None:
                    contrib[:end] = pre[:end]
                else:
                    contrib[:min(f, end)] = pre[:min(f, end)]
                    post = w0 * base[f:end] + dl * limret[f:end]
                    contrib[f:end] = post
                if x < 240:
                    if not np.isfinite(px):
                        pass  # NaN exit price: rung dropped, weight already 0 below
                    else:
                        frozen = w0 * (px / o1[s] - 1)
                        if f is not None and f <= x and limret is not None \
                                and np.isfinite(fill_lim[s]) and fill_lim[s] > 0:
                            frozen += dl * (px / fill_lim[s] - 1)
                        contrib[x:] = frozen
                        if how == "stop":
                            fees_book += TAKER * abs(wq)
                            b_stops += 1
                        else:
                            fees_book += MAKER * abs(wq)
                            b_tps += 1
                        if frozen > 0:
                            b_wins += 1
                        bled.append((label, s, str(T), how, round(wq, 9), x,
                                     round(float(px), 6)))
                    q_after[s] = 0.0
                    entries[s] = np.nan
                marks_b += contrib
                # gross weight held per minute: |w0| pre-fill, |wq| after,
                # 0 after an SL/TP exit (x >= f always: checks start at f).
                gseg = np.zeros(240)
                if f is None:
                    gseg[:end] = abs(wq)
                else:
                    gseg[:min(f, end)] = abs(w0)
                    if f < end:
                        gseg[f:end] = abs(wq)
                gross_b += gseg
            # realised book pnl = marks at bar end (exact weight accounting)
            book_pnl = float(marks_b[239]) if len(marks_b) else 0.0
            # funding on post-decision longs
            if settle:
                book_pnl -= FUND * sum(max(0.0, q_after[s]) for s in majors)
            book_pnl -= fees_book
            for s in majors:
                pos[s] = [q_after[s], entries[s]]
        # ---- DIP leg (frozen G2 mechanics; identical op order to p2) ----
        dip_pnl = 0.0
        marks = np.zeros(240)
        gross = np.zeros(240)
        taken = []
        if sleeve:
            R = p2.ROWS["G2"]
            kd, budget, cap = R["kd"], R["budget"], R["cap"]
            use_corr, stop_mode, tp_mult = R["corr"], R["stop"], R["tp"]
            opens_b = opens_bar
            cands = []
            W = LIVE_B - LIVE_A + 1
            for ai, sym in enumerate(majors):
                o1v, sg = float(opens_b[sym][j]), float(sig_bar[sym][j])
                if not (np.isfinite(o1v) and np.isfinite(sg)) or o1v <= 0 or sg <= 0:
                    continue
                low_win = D[sym]["low"][off + LIVE_A:off + LIVE_B + 1].astype(float)
                others = [s for s in majors if s != sym]
                cmat = np.stack([D[b]["close"][off + LIVE_A - 1:off + LIVE_B].astype(float)
                                 for b in others])
                oo = np.array([float(opens_b[b][j]) for b in others])
                ss = np.array([float(sig_bar[b][j]) for b in others])
                nvec = p2.n_vector(cmat, oo, ss)
                for r, k in enumerate(RUNGS):
                    lv = o1v * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = p2.find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = LIVE_A + ib
                    cands.append(dict(f=f, r=r, a=ai, sym=sym, lv=lv, sg=sg,
                                      n=int(nvec[ib])))
            cands.sort(key=lambda c: (c["f"], c["r"], c["a"]))
            taken = []
            for c in cands:
                mult = 1.0 / (1 + c["n"]) if use_corr else 1.0
                w = U * kd * mult
                risk_open = sum(t["w"] * (M_SL * t["sg"] + p2.GAP_ALLOW)
                                for t in taken if t["x"] > c["f"])
                if not p2.budget_ok_amt(risk_open, w, c["sg"], budget):
                    continue
                if cap is not None:
                    # shared within-bar cap: book gross occupies room first
                    book_g = sum(abs(q_after[t]) for t in majors) if books_w is not None else 0.0
                    open_sum = book_g + sum(t["w"] for t in taken if t["x"] > c["f"])
                    w = p2.cap_apply(open_sum, w, cap)
                    if w <= 0:
                        continue
                sym = c["sym"]
                Ha = D[sym]["high"][off:off + 240].astype(float)
                La = D[sym]["low"][off:off + 240].astype(float)
                Ca = D[sym]["close"][off:off + 240].astype(float)
                Oa = D[sym]["open"][off:off + 240].astype(float)
                o2m = D[sym]["open"][off + 240]
                o2 = float(o2m) if np.isfinite(o2m) else np.nan
                ret, x, how, gap = p2.outcome_row(Ha, La, Ca, Oa, c["f"], c["lv"],
                                                  c["sg"], o2, settle,
                                                  stop=stop_mode, tp_mult=tp_mult)
                if not np.isfinite(ret):
                    continue
                taken.append(dict(f=c["f"], r=c["r"], a=c["a"], sym=sym, lv=c["lv"],
                                  sg=c["sg"], w=w, x=x, ret=ret, how=how, gap=gap,
                                  T=T))
            for t in taken:
                Ca = D[t["sym"]]["close"][off:off + 240].astype(float)
                end = min(t["x"], 240)
                seg = np.zeros(240)
                seg[t["f"]:end] = Ca[t["f"]:end] / t["lv"] - 1
                seg = pd.Series(seg).ffill().fillna(0.0).to_numpy()
                if t["x"] < 240:
                    seg[t["x"]:] = t["ret"]
                marks += t["w"] * seg
                gseg = np.zeros(240)
                gseg[t["f"]:end] = t["w"]
                gross += gseg
                fills += 1
                if t["ret"] > 0:
                    wins += 1
                if t["how"] in ("stop", "backstop"):
                    stops += 1
                elif t["how"] == "tp":
                    tps += 1
                else:
                    timeouts += 1
                if t["gap"] is not None and t["gap"] > 1.0:
                    gap_stops += 1
                if t["gap"] is not None and np.isfinite(t["gap"]):
                    gap_max = max(gap_max, float(t["gap"]))
                dled.append((label, t["sym"], str(T), RUNGS[t["r"]], t["f"],
                             round(t["w"], 9), round(float(t["ret"]), 9),
                             t["how"]))
            dip_pnl = float(sum(t["w"] * t["ret"] for t in taken))
        EQ = EQ_OPEN * (1 + dip_pnl + book_pnl)
        dip_pnl_sum += dip_pnl
        book_pnl_sum += book_pnl
        M = EQ_OPEN * (1 + marks + (marks_b if books_w is not None else 0.0))
        for mm in range(240):
            t_all.append(T + pd.Timedelta(minutes=mm))
            m_all.append(float(M[mm]))
        t_all.append(T + pd.Timedelta(hours=4))
        m_all.append(float(EQ))
        if len(taken) or (books_w is not None and (gross_b > 0).any()):
            peak_gross = max(peak_gross, float(EQ_OPEN * np.maximum(gross, gross_b
                               if books_w is not None else 0.0).max()))
    if not m_all:
        return None, dled, bled
    marr = np.array(m_all)
    i_min = int(np.argmin(marr))
    min_m = float(marr[i_min])
    run_peak = np.maximum.accumulate(np.concatenate([[1.0], marr]))[1:]
    dd = float(np.max(1 - marr / run_peak))
    ts = pd.DatetimeIndex(t_all)
    ms = pd.Series(m_all, index=ts).sort_index()
    ms = ms[~ms.index.duplicated(keep="last")]
    days = pd.date_range(ms.index[0].floor("D"), ms.index[-1].ceil("D"), freq="D")
    bval = ms.reindex(days, method="ffill")
    drets = bval.pct_change().dropna()
    worst_day = (str(drets.idxmin().date()), round(float(drets.min()), 6)) \
        if len(drets) else (None, None)
    n_days = (E - S).total_seconds() / 86400.0
    cell = dict(equity_start=1.0, end_equity=round(EQ, 6),
                min_marked=round(min_m, 6),
                max_loss_pct=round(100 * (1 - min_m), 3),
                max_dd_pct=round(100 * dd, 3),
                pct_per_month=round(100 * (EQ ** (30.4375 / n_days) - 1), 4)
                if EQ > 0 else None,
                peak_gross=round(peak_gross, 4),
                fills=fills, stops=stops, tps=tps, timeouts=timeouts,
                wins=wins,
                win_rate=round(wins / fills, 4) if fills else None,
                gap_stops=gap_stops, gap_max=round(gap_max, 3),
                worst_minute=str(t_all[i_min]),
                worst_day=worst_day[0], worst_day_ret=worst_day[1],
                n_days=round(n_days, 2),
                dip_pnl=round(dip_pnl_sum, 6), book_pnl=round(book_pnl_sum, 6),
                book_fills=b_fills, book_stops=b_stops, book_tps=b_tps,
                book_wins=b_wins,
                book_win_rate=round(b_wins / b_fills, 4) if b_fills else None)
    return cell, dled, bled


def run_cells(row, books=None):
    """All legs x phases for one row. books: standard-grid PB (or None)."""
    cells, dled_all, bled_all = {}, [], []
    for leg in LEGS:
        idx, D, grids = p2.load_leg(leg)
        S, E = LEGS[leg]
        for s in PHASES:
            bts, ob, sg = grids[s]
            js = [j for j, T in enumerate(bts) if S <= T < E]
            jj = {j: bts[j] for j in js}
            if row in ("PB", "BOOK0"):
                tall = book_targets_for_phase(books, bts)
                bdict = {c: np.array([tall[c][j] for j in js]) for c in MAJORS4}
            else:
                bdict = None
            cell, dl, bl = simulate_interval_g2(
                idx, D, list(D.keys()), jj, ob, sg, S, E,
                books_w=bdict if row in ("PB", "BOOK0") else None,
                sleeve=(row in ("DIP0", "PB")),
                label=f"{row}_{leg}_s{s}")
            cells[f"{row}|{leg}|s{s}"] = cell
            dled_all.extend(dl)
            bled_all.extend(bl)
            print(row, leg, f"s{s}", cell, flush=True)
        del idx, D, grids
    return cells, dled_all, bled_all


def cmd_gate():
    ref = json.loads((ROOT / "research/tournament/oc_presample2"
                      / "results.json").read_text())["cells"]
    cells, ok_all, report = {}, True, {}
    got, _, _ = run_cells("DIP0")
    for key, cell in got.items():
        leg, s = key.split("|")[1], key.split("|")[2]
        r = ref[f"G2|{leg}|{s}"]
        match = all(cell[k] == r[k] for k in CELL_FIELDS)
        report[key] = {"match": bool(match),
                       "diff": {k: (cell[k], r[k]) for k in CELL_FIELDS
                                if cell[k] != r[k]}}
        ok_all &= match
        print(f"gate {key} match={report[key]['match']}", flush=True)
    out = {"pass": bool(ok_all), "cells": got, "report": report,
           "note": "DIP0 (imported G2 primitives, own driver) vs oc_presample2 G2 cells"}
    (TMP / "gate.json").write_text(json.dumps(out, indent=1, default=str))
    print("GATE", "PASS" if ok_all else "FAIL", flush=True)
    if not ok_all:
        raise SystemExit(1)


def cmd_rows(which_rows=None):
    gate = json.loads((TMP / "gate.json").read_text())
    if not gate.get("pass"):
        raise SystemExit("gate did not pass; refusing to compute outcomes")
    rows = list(which_rows) if which_rows else ["DIP0", "BOOK0", "PB"]
    books = None
    if "PB" in rows or "BOOK0" in rows:
        books = pd.read_parquet(TMP / "books_ps.parquet")
        books.index = pd.to_datetime(books.index, utc=True)
    cells, dled, bled = {}, [], []
    for row in rows:
        if row not in ("DIP0", "BOOK0", "PB"):
            raise SystemExit(f"unknown row {row}")
        c, dl, bl = run_cells(row, books=books)
        cells.update(c)
        dled.extend([(row,) + tuple(r[1:]) for r in dl])
        bled.extend([(row,) + tuple(r[1:]) for r in bl])
    chk = hashlib.sha256(repr(sorted(dled)).encode()).hexdigest()[:16]
    bchk = hashlib.sha256(repr(sorted(bled)).encode()).hexdigest()[:16]
    out = {"rows": rows, "legs": {k: (str(v[0]), str(v[1])) for k, v in LEGS.items()},
           "cells": cells, "dip_ledger_checksum": chk, "book_ledger_checksum": bchk,
           "n_dip_rows": len(dled), "n_book_rows": len(bled)}
    (TMP / "rows.json").write_text(json.dumps(out, indent=1, default=str))
    print("dip checksum", chk, len(dled), "book checksum", bchk, len(bled), flush=True)


def cmd_finalize():
    rows = json.loads((TMP / "rows.json").read_text())
    gate = json.loads((TMP / "gate.json").read_text())
    blend = json.loads((TMP / "blend.json").read_text())
    out = {
        "config": {
            "dip": "oc_presample2 G2 primitives by import (compute_sigma/n_vector/"
                   "find_fill/outcome_row/budget/cap_apply/load_leg/build_grids); "
                   "G1 gate PASS vs all 16 oc_presample2 G2 cells",
            "gate_pass": gate["pass"],
            "book_blend": blend["blend"],
            "rows": rows["rows"],
            "rungs": list(RUNGS), "live_dip": [LIVE_A, LIVE_B],
            "book": {"limit_bps": 10, "live_min": [BOOK_LIVE_A, BOOK_LIVE_B],
                     "sl_mult": BOOK_M_SL, "tp_mult": BOOK_M_TP,
                     "cap_shared": BOOK_CAP, "causal_lag": "PB row known at row_t+4h"},
            "maker": MAKER, "taker": TAKER, "fund_long_settle": FUND,
            "unit": U, "gap_allow": p2.GAP_ALLOW, "gross_cap": GCAP,
            "grid": "4h from 2020-01-01 00:00 UTC + phase h (all integer j)",
            "store": "data/raw/spot_1m_presample_20261007 (SPOT)",
            "note": "replica level, NOT the v421 stack (no R2 tables/grid/bear; "
                    "R2 agent size=scale=governor=1); spot prices, perp gate costs",
        },
        "legs": rows["legs"],
        "cells": rows["cells"],
        "dip_ledger_checksum": rows["dip_ledger_checksum"],
        "book_ledger_checksum": rows["book_ledger_checksum"],
        "n_dip_rows": rows["n_dip_rows"],
        "n_book_rows": rows["n_book_rows"],
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("results.json written", flush=True)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    which = sys.argv[1] if len(sys.argv) > 1 else "gate"
    if which == "gate":
        cmd_gate()
    elif which == "rows":
        cmd_rows(sys.argv[2:] or None)
    elif which == "finalize":
        cmd_finalize()
    else:
        raise SystemExit(f"unknown subcommand {which}")
