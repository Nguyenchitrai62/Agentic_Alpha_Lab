"""oc_presample2: do the dip-sleeve DESIGN CHOICES made on 2021-2026 hold on 2017-2020?

Frozen by PLAN.md (read it first). Core functions below are copied from
research/tournament/oc_presample/presample.py (itself vendored VERBATIM from
research/tournament/oc_crash2020/crash.py: compute_sigma / n_vector /
find_fill / outcome_d0 / budget_ok / cap_apply + constants), extended with
ONE knob per design-choice row (corr / kd+budget / cap / stop_mode /
tp_mult). The fidelity gate (`gate` subcommand) replays the oc_presample
pre-sample legs with G2 knobs and requires bit-for-bit agreement with
oc_presample/results.json presample cells before any other row is computed.

Subcommands (run under heavy_slot; one process):
  gate       G2-knob replay of Y2017/Y2018/Y2019/Y2020p -> tmp/gate2.json
             (PASS/FAIL vs oc_presample results.json)
  rows       all 7 rows x 4 legs x 4 phases (requires gate PASS)
             -> tmp/rows.json
  finalize   combine into results.json (no computation)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import warnings
warnings.simplefilter("ignore", FutureWarning)

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
TMP = HERE / "tmp"

# ============================================================ copied core
# Copied from oc_presample/presample.py (copy, do not edit the original).
MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0
DETECT_K = 2.5
U = 0.25 * 1.75 / 4 / 1.657  # engine fixed per-rung unit (SIZE/size_mult/S_REF)
GAP_ALLOW = 0.02
GCAP = 2.0
SETTLE_HOURS = (0, 8, 16)
MAJORS4 = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
ORIGIN = pd.Timestamp("2020-01-01", tz="UTC")
PHASES = (0, 1, 2, 3)

# Row table (ONE knob each vs G2; see PLAN.md).
#   corr: False -> mult=1 (NOB1); True -> mult=1/(1+n)
#   kd/budget: KD13 1.3/0.338, KD20 2.0/0.52, else 1.7/0.442
#   cap: None (NOCAP) or 2.0
#   stop: "close5" or "touch" (TOUCH)
#   tp: 1.0 or 1.5 (TP15)
ROWS = {
    "G2":    dict(corr=True, kd=1.7, budget=0.26 * 1.7, cap=2.0,
                  stop="close5", tp=1.0),
    "NOB1":  dict(corr=False, kd=1.7, budget=0.26 * 1.7, cap=2.0,
                  stop="close5", tp=1.0),
    "KD13":  dict(corr=True, kd=1.3, budget=0.26 * 1.3, cap=2.0,
                  stop="close5", tp=1.0),
    "KD20":  dict(corr=True, kd=2.0, budget=0.26 * 2.0, cap=2.0,
                  stop="close5", tp=1.0),
    "NOCAP": dict(corr=True, kd=1.7, budget=0.26 * 1.7, cap=None,
                  stop="close5", tp=1.0),
    "TOUCH": dict(corr=True, kd=1.7, budget=0.26 * 1.7, cap=2.0,
                  stop="touch", tp=1.0),
    "TP15":  dict(corr=True, kd=1.7, budget=0.26 * 1.7, cap=2.0,
                  stop="close5", tp=1.5),
}


def compute_sigma(opens: np.ndarray) -> np.ndarray:
    """4h sigma known at each bar open: rolling(360, min_periods=120).std.shift(1)."""
    return pd.Series(np.asarray(opens, dtype=float)).pct_change().rolling(
        360, min_periods=120).std(ddof=1).shift(1).to_numpy()


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """B1 correlation count per live minute (v399-exact). NaN -> not flushing."""
    W = close_others.shape[1]
    n = np.zeros(W, dtype=np.int64)
    for i in range(close_others.shape[0]):
        o, sg = float(open_others[i]), float(sigma_others[i])
        if not (np.isfinite(o) and np.isfinite(sg)) or o <= 0 or sg <= 0:
            continue
        thr = o * (1 - DETECT_K * sg)
        if not np.isfinite(thr):
            continue
        c = close_others[i]
        n += (np.isfinite(c) & (c <= thr)).astype(np.int64)
    return n


def find_fill(low_win: np.ndarray, level: float):
    """First live-window index with low < level (STRICT). None if no fill."""
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_row(Ha, La, Ca, Oa, f: int, lv: float, sg: float,
                o2: float, settle: bool, stop: str = "close5",
                tp_mult: float = 1.0):
    """D0 replica from lv with row knobs. Returns (ret, x, how, gap_sigma).

    stop="close5": first clock minute m with (m+1)%5==0 and close(m) <= sl
      -> exit at open(m+1) (or o2 if m==239), taker.
    stop="touch": first t with low(t) <= sl -> exit at min(sl, open(t)),
      taker (same pricing as the backstop; NaN open -> NaN ret).
    tp_mult scales the TP level: tp = lv*(1+tp_mult*sg), maker exit.
    Priority stop-first (backstop wins ties; else TP only if strictly
    earlier; else stop; same-minute stop+TP -> stop).
    """
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + tp_mult * sg)
    if stop == "touch":
        hs = np.asarray(La[f + 1:240], dtype=float) <= sl
        ks = int(np.argmax(hs)) if hs.any() else None
        ks_is_touch = True
    else:
        post = np.arange(f + 1, 240)
        trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
        ks = int(np.argmax(trig)) if trig.any() else None
        ks_is_touch = False
    hb = np.asarray(La[f + 1:240], dtype=float) <= bl
    kb = int(np.argmax(hb)) if hb.any() else None
    ht = np.asarray(Ha[f + 1:240], dtype=float) > tp
    kt = int(np.argmax(ht)) if ht.any() else None
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = float(Oa[x])
        if not np.isfinite(ox):
            return (np.nan, x, "backstop", None)
        px = bl if ox > bl else ox  # min(bl, open): gap pays the open
        return (px / lv - 1 - MAKER - TAKER, x, "backstop", (bl - px) / (lv * sg))
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / lv - 1 - 2 * MAKER, x, "tp", None)
    if ks is not None:
        if ks_is_touch:
            x = f + 1 + ks
            ox = float(Oa[x])
            if not np.isfinite(ox):
                return (np.nan, x, "stop", None)
            px = sl if ox > sl else ox  # min(sl, open): gap pays the open
            ret = px / lv - 1 - MAKER - TAKER
            if x == 240 and settle:
                ret -= FUND
            return (ret, x, "stop", (sl - px) / (lv * sg))
        km = f + 1 + ks
        if km + 1 < 240:
            px, x = float(Oa[km + 1]), km + 1
        else:
            px, x = float(o2), 240
        if not np.isfinite(px):
            return (np.nan, x, "stop", None)
        ret = px / lv - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop", (sl - px) / (lv * sg))
    x = 240
    if not np.isfinite(float(o2)):
        return (np.nan, x, "time", None)
    return (float(o2) / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0),
            x, "time", None)


# Back-compat alias with G2 knobs (= oc_presample outcome_d0 verbatim).
def outcome_d0(Ha, La, Ca, Oa, f: int, lv: float, sg: float,
               o2: float, settle: bool):
    return outcome_row(Ha, La, Ca, Oa, f, lv, sg, o2, settle,
                       stop="close5", tp_mult=1.0)


def budget_ok_amt(risk_open: float, w: float, sg: float, budget: float) -> bool:
    """Engine risk-budget check for one candidate rung (parameterised)."""
    return risk_open + w * (M_SL * sg + GAP_ALLOW) <= budget + 1e-12


def budget_ok(risk_open: float, w: float, sg: float) -> bool:
    """G2 budget check (oc_presample verbatim)."""
    return budget_ok_amt(risk_open, w, sg, 0.26 * 1.7)


def cap_apply(open_sum: float, w: float, cap: float | None) -> float:
    """Gross-cap room cut (engine hook). Returns kept weight (0 = skip)."""
    if cap is None:
        return w
    room = cap - open_sum
    if room <= 1e-12:
        return 0.0
    return min(w, room)


# ============================================================ data loaders
SPOT = ROOT / "data/raw/spot_1m_presample_20261007"


def load_1m_spot(sym: str, start, end):
    """Read the presample spot store (o,h,l,c,volume)."""
    m = pd.read_parquet(SPOT / f"{sym}.parquet")
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m[(m["open_time"] >= start) & (m["open_time"] <= end)]
    idx = pd.date_range(start, end, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    out = {k: m[k].to_numpy(dtype=np.float32) for k in ("o", "h", "l", "c")}
    del m
    return idx, out


# ============================================================ simulation
def simulate_interval(idx, D, majors, bars, opens_bar, sig_bar, S, E,
                       arm="G2", label="", row=None):
    """Dip-only replay for bars with open in [S, E). Parameterised row.

    row: key of ROWS (default arm G2 settings). Mirrors
    oc_presample.simulate_interval exactly when row="G2".
    Returns (cell, ledger_rows).
    """
    if row is None:
        row = "G2"
    R = ROWS[row]
    kd, budget, cap = R["kd"], R["budget"], R["cap"]
    use_corr, stop_mode, tp_mult = R["corr"], R["stop"], R["tp"]
    EQ = 1.0
    t_all, m_all = [], []
    fills = stops = tps = timeouts = gap_stops = 0
    wins = 0
    gap_max = 0.0
    peak_gross = 0.0
    ledger = []
    for j in bars:
        T = bars[j]
        if not (S <= T < E):
            continue
        off = int((T - idx[0]).total_seconds() // 60)
        if off + 240 >= len(idx):
            continue
        settle = (T + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
        EQ_OPEN = EQ
        cands = []
        W = LIVE_B - LIVE_A + 1
        for ai, sym in enumerate(majors):
            o1, sg = float(opens_bar[sym][j]), float(sig_bar[sym][j])
            if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                continue
            low_win = D[sym]["low"][off + LIVE_A:off + LIVE_B + 1].astype(float)
            others = [s for s in majors if s != sym]
            cmat = np.stack([D[b]["close"][off + LIVE_A - 1:off + LIVE_B].astype(float)
                             for b in others])
            oo = np.array([float(opens_bar[b][j]) for b in others])
            ss = np.array([float(sig_bar[b][j]) for b in others])
            nvec = n_vector(cmat, oo, ss)
            for r, k in enumerate(RUNGS):
                lv = o1 * (1 - k * sg)
                if not np.isfinite(lv) or lv <= 0:
                    continue
                ib = find_fill(low_win, lv)
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
            risk_open = sum(t["w"] * (M_SL * t["sg"] + GAP_ALLOW)
                            for t in taken if t["x"] > c["f"])
            if not budget_ok_amt(risk_open, w, c["sg"], budget):
                continue
            if cap is not None:
                open_sum = sum(t["w"] for t in taken if t["x"] > c["f"])
                w = cap_apply(open_sum, w, cap)
                if w <= 0:
                    continue
            sym = c["sym"]
            Ha = D[sym]["high"][off:off + 240].astype(float)
            La = D[sym]["low"][off:off + 240].astype(float)
            Ca = D[sym]["close"][off:off + 240].astype(float)
            Oa = D[sym]["open"][off:off + 240].astype(float)
            o2m = D[sym]["open"][off + 240]
            o2 = float(o2m) if np.isfinite(o2m) else np.nan
            ret, x, how, gap = outcome_row(Ha, La, Ca, Oa, c["f"], c["lv"],
                                           c["sg"], o2, settle,
                                           stop=stop_mode, tp_mult=tp_mult)
            if not np.isfinite(ret):
                continue
            taken.append(dict(f=c["f"], r=c["r"], a=c["a"], sym=sym, lv=c["lv"],
                              sg=c["sg"], w=w, x=x, ret=ret, how=how, gap=gap,
                              T=T))
        marks = np.zeros(240)
        gross = np.zeros(240)
        for t in taken:
            Ca = D[t["sym"]]["close"][off:off + 240].astype(float)
            end = min(t["x"], 240)
            seg = np.zeros(240)
            seg[t["f"]:end] = Ca[t["f"]:end] / t["lv"] - 1
            # MARK FIX (copied from oc_presample): runner-up NaN closes
            # (outage gaps) hold the last marked value instead of poisoning
            # the DD series. Realised equity E is untouched (NaN-exit rungs
            # are dropped before booking). Leading NaN (no print yet) = 0.
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
            ledger.append((label, t["sym"], str(T), RUNGS[t["r"]], t["f"],
                           round(t["w"], 9), round(float(t["ret"]), 9),
                           t["how"]))
        pnl = float(sum(t["w"] * t["ret"] for t in taken))
        EQ = EQ_OPEN * (1 + pnl)
        M = EQ_OPEN * (1 + marks)
        for mm in range(240):
            t_all.append(T + pd.Timedelta(minutes=mm))
            m_all.append(float(M[mm]))
        t_all.append(T + pd.Timedelta(hours=4))
        m_all.append(float(EQ))
        if len(taken):
            peak_gross = max(peak_gross, float(EQ_OPEN * gross.max()))
    if not m_all:
        return None, ledger
    marr = np.array(m_all)
    i_min = int(np.argmin(marr))
    min_m = float(marr[i_min])
    run_peak = np.maximum.accumulate(np.concatenate([[1.0], marr]))[1:]
    dd = float(np.max(1 - marr / run_peak))
    ts = pd.DatetimeIndex(t_all)
    ms = pd.Series(m_all, index=ts).sort_index()
    ms = ms[~ms.index.duplicated(keep="last")]
    days = pd.date_range(ms.index[0].floor("D"), ms.index[-1].ceil("D"),
                         freq="D")
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
                n_days=round(n_days, 2))
    return cell, ledger


def build_grids(idx, majors, D, warmup_from=None):
    """Per-phase 4h grids from ORIGIN (negative j extends back) + sigma.

    warmup_from: dict sym -> Timestamp; bars before it get NaN open/sigma
    (coin absent: skipped and excluded from n-counts).
    Returns {phase: (bts, {sym: opens}, {sym: sigs})}.
    """
    grids = {}
    for s in PHASES:
        base = ORIGIN + pd.Timedelta(hours=s)
        span0 = idx[0] - pd.Timedelta(hours=4)
        span1 = idx[-1] + pd.Timedelta(hours=4)
        j0 = int(np.floor((span0 - base).total_seconds() / 14400))
        j1 = int(np.ceil((span1 - base).total_seconds() / 14400))
        bts = base + pd.to_timedelta(np.arange(j0, j1 + 1) * 4, unit="h")
        bts = bts[(bts >= idx[0]) & (bts + pd.Timedelta(hours=4) <= idx[-1])]
        offs = ((bts - idx[0]).total_seconds() // 60).astype(int)
        ob, sg = {}, {}
        for sym in majors:
            oo = D[sym]["open"][offs].astype(float)
            ob[sym] = oo
            sg[sym] = compute_sigma(oo)
            if warmup_from is not None and sym in warmup_from:
                mask = np.asarray(bts < warmup_from[sym])
                ob[sym] = np.where(mask, np.nan, ob[sym])
                sg[sym] = np.where(mask, np.nan, sg[sym])
        grids[s] = (bts, ob, sg)
    return grids


LEGS = {
    "Y2017": (pd.Timestamp("2017-10-16", tz="UTC"),
              pd.Timestamp("2018-01-01", tz="UTC")),
    "Y2018": (pd.Timestamp("2018-01-01", tz="UTC"),
              pd.Timestamp("2019-01-01", tz="UTC")),
    "Y2019": (pd.Timestamp("2019-01-01", tz="UTC"),
              pd.Timestamp("2020-01-01", tz="UTC")),
    "Y2020p": (pd.Timestamp("2020-01-01", tz="UTC"),
               pd.Timestamp("2020-09-01", tz="UTC")),
}
ROW_ORDER = ("G2", "NOB1", "KD13", "KD20", "NOCAP", "TOUCH", "TP15")
CELL_FIELDS = ("end_equity", "min_marked", "max_loss_pct", "max_dd_pct",
               "pct_per_month", "peak_gross", "fills", "stops", "tps",
               "timeouts", "wins", "win_rate", "gap_stops", "gap_max",
               "worst_minute", "worst_day", "worst_day_ret", "n_days")


def load_leg(leg):
    """Load one leg's spot 1m window (+100d warm-up, +1d tail)."""
    S, E = LEGS[leg]
    LS = S - pd.Timedelta(days=100)
    LE = E + pd.Timedelta(days=1)
    man = json.loads((SPOT / "manifest.json").read_text())["symbols"]
    store_warmup = {s: pd.Timestamp(man[s]["first_bar"])
                    + pd.Timedelta(days=60) for s in MAJORS4}
    idx = None
    D = {}
    warmup_from = {}
    for sym in MAJORS4:
        ii, d = load_1m_spot(sym, LS, LE)
        if idx is None:
            idx = ii
        dd = {"open": d["o"], "high": d["h"], "low": d["l"],
              "close": d["c"]}
        present = np.flatnonzero(np.isfinite(dd["close"]))
        if len(present) == 0:
            print(f"{leg} {sym}: no data in window; absent", flush=True)
            continue
        warmup_from[sym] = store_warmup[sym]
        D[sym] = dd
        t_first = idx[int(present[0])]
        print(f"{leg} {sym}: window n={len(ii)} first_in_window={t_first} "
              f"warm={warmup_from.get(sym)}", flush=True)
    grids = build_grids(idx, list(D.keys()), D, warmup_from=warmup_from)
    return idx, D, grids


def cmd_gate():
    ref = json.loads((ROOT / "research/tournament/oc_presample"
                      / "results.json").read_text())["presample"]["cells"]
    cells, ok_all, report = {}, True, {}
    for leg in LEGS:
        idx, D, grids = load_leg(leg)
        for s in PHASES:
            bts, ob, sg = grids[s]
            S, E = LEGS[leg]
            js = [j for j, T in enumerate(bts) if S <= T < E]
            jj = {j: bts[j] for j in js}
            cell, _ = simulate_interval(idx, D, list(D.keys()), jj, ob,
                                        sg, S, E, row="G2",
                                        label=f"{leg}_s{s}")
            key = f"{leg}|s{s}"
            cells[key] = cell
            r = ref[key]
            match = all(cell[k] == r[k] for k in CELL_FIELDS)
            report[key] = {"match": bool(match),
                           "diff": {k: (cell[k], r[k]) for k in CELL_FIELDS
                                    if cell[k] != r[k]}}
            ok_all &= match
            print(f"gate {key} match={match} {cell}", flush=True)
        del idx, D, grids
    out = {"pass": bool(ok_all), "cells": cells, "report": report,
           "note": "G2 knobs vs oc_presample presample cells"}
    (TMP / "gate2.json").write_text(json.dumps(out, indent=1, default=str))
    print("GATE2", "PASS" if ok_all else "FAIL", flush=True)
    if not ok_all:
        raise SystemExit(1)


def cmd_rows(which_rows=None):
    gate = json.loads((TMP / "gate2.json").read_text())
    if not gate.get("pass"):
        raise SystemExit("gate2 did not pass; refusing to compute outcomes")
    rows = list(which_rows) if which_rows else list(ROW_ORDER)
    for r in rows:
        if r not in ROWS:
            raise SystemExit(f"unknown row {r}")
    cells, ledgers = {}, []
    import hashlib
    for leg in LEGS:
        idx, D, grids = load_leg(leg)
        S, E = LEGS[leg]
        for row in rows:
            for s in PHASES:
                bts, ob, sg = grids[s]
                js = [j for j, T in enumerate(bts) if S <= T < E]
                jj = {j: bts[j] for j in js}
                if not jj:
                    cells[f"{row}|{leg}|s{s}"] = None
                    continue
                cell, led = simulate_interval(idx, D, list(D.keys()), jj,
                                              ob, sg, S, E, row=row,
                                              label=f"{row}_{leg}_s{s}")
                cells[f"{row}|{leg}|s{s}"] = cell
                ledgers.extend(led)
                print(row, leg, f"s{s}", cell, flush=True)
        del idx, D, grids
    chk = hashlib.sha256(repr(sorted(ledgers)).encode()).hexdigest()[:16]
    out = {"rows": {r: ROWS[r] for r in rows},
           "legs": {k: (str(v[0]), str(v[1])) for k, v in LEGS.items()},
           "cells": cells, "ledger_checksum": chk,
           "n_ledger_rows": len(ledgers)}
    (TMP / "rows.json").write_text(json.dumps(out, indent=1, default=str))
    print("checksum", chk, "rows", len(ledgers), flush=True)


def cmd_finalize():
    rows = json.loads((TMP / "rows.json").read_text())
    gate = json.loads((TMP / "gate2.json").read_text())
    out = {
        "config": {
            "core": "copied from oc_presample/presample.py "
                    "(compute_sigma/n_vector/find_fill/outcome/budget/cap); "
                    "gate2 PASS vs oc_presample presample cells",
            "gate2_pass": gate["pass"],
            "rows": rows["rows"],
            "rungs": list(RUNGS), "live": [LIVE_A, LIVE_B],
            "maker": MAKER, "taker": TAKER, "fund_long_settle": FUND,
            "unit": U, "gap_allow": GAP_ALLOW, "gross_cap_G2": GCAP,
            "grid": "4h from 2020-01-01 00:00 UTC + phase h (all integer j)",
            "store": "data/raw/spot_1m_presample_20261007 (SPOT)",
            "note": "dip-only; R2 agent size=1, scale=governor=1; "
                    "spot prices with perp gate costs (labelled caveat)",
        },
        "legs": rows["legs"],
        "cells": rows["cells"],
        "ledger_checksum": rows["ledger_checksum"],
        "n_ledger_rows": rows["n_ledger_rows"],
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
