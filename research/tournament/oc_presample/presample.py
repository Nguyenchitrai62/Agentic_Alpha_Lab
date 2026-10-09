"""oc_presample: fixed-rule G2 dip-sleeve replay on pre-sample spot data.

Frozen by PLAN.md (read it first). Core functions below are vendored
VERBATIM from research/tournament/oc_crash2020/crash.py (pure-numpy core:
compute_sigma / n_vector / find_fill / outcome_d0 / budget_ok / cap_apply
+ constants). The fidelity gate (`gate` subcommand) replays oc_crash2020
window W1 from the OLD perp store and requires bit-for-bit agreement with
oc_crash2020/results.json before any pre-sample number is computed.

Subcommands (run under heavy_slot; one process):
  gate       fidelity replay of W1_covid0312 -> tmp/gate.json (PASS/FAIL)
  presample  Y2017/Y2018/Y2019/Y2020p year legs on the new spot store
             (requires gate PASS) -> tmp/presample.json
  reference  R1..R5 year legs on the old perp store (requires gate PASS)
             -> tmp/reference.json
  finalize   combine into results.json (no computation)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Silence the pandas pct_change fill_method FutureWarning: compute_sigma is
# vendored VERBATIM from oc_crash2020/crash.py (gate-proven bit-identical);
# the warning changes nothing computationally.
import warnings
warnings.simplefilter("ignore", FutureWarning)

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
TMP = HERE / "tmp"

# ============================================================ vendored core
# VERBATIM from oc_crash2020/crash.py (only MAJORS/loader differ per leg).
MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0
DETECT_K = 2.5
KD = 1.7
U = 0.25 * 1.75 / 4 / 1.657  # engine fixed per-rung unit (SIZE/size_mult/S_REF)
BUDGET = 0.26 * 1.7  # G2 risk budget (k=1, kd=1.7)
GAP_ALLOW = 0.02
GCAP = 2.0
SETTLE_HOURS = (0, 8, 16)
MAJORS5 = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
MAJORS4 = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
ORIGIN = pd.Timestamp("2020-01-01", tz="UTC")
PHASES = (0, 1, 2, 3)


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


def outcome_d0(Ha, La, Ca, Oa, f: int, lv: float, sg: float,
               o2: float, settle: bool):
    """D0 replica from lv. Returns (ret, x, how, gap_sigma)."""
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + 1.0 * sg)
    post = np.arange(f + 1, 240)
    trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
    ks = int(np.argmax(trig)) if trig.any() else None
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


def budget_ok(risk_open: float, w: float, sg: float) -> bool:
    """Engine risk-budget check for one candidate rung."""
    return risk_open + w * (M_SL * sg + GAP_ALLOW) <= BUDGET + 1e-12


def cap_apply(open_sum: float, w: float, cap: float | None) -> float:
    """Gross-cap room cut (engine hook). Returns kept weight (0 = skip)."""
    if cap is None:
        return w
    room = cap - open_sum
    if room <= 1e-12:
        return 0.0
    return min(w, room)


# ============================================================ data loaders
PERP_BTC = ROOT / "data/raw/btc_intraday_20260924"
PERP_MAJ = ROOT / "data/raw/majors_intraday_20260924"
SPOT = ROOT / "data/raw/spot_1m_presample_20261007"


def load_1m_perp(sym: str, start, end):
    """Vendored read pattern from crash.load_1m (perp store)."""
    if sym == "BTCUSDT":
        files = sorted(PERP_BTC.glob("klines_1m_20*.parquet"))
    else:
        files = sorted(PERP_MAJ.glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "high", "low",
                                         "close"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= start) & (m["open_time"] <= end)]
    idx = pd.date_range(start, end, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    out = {k: m[k].to_numpy(dtype=np.float32) for k in ("open", "high",
                                                       "low", "close")}
    del m, parts
    return idx, out


def load_1m_spot(sym: str, start, end):
    """Read the new spot presample store (o,h,l,c,volume)."""
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
                       arm="G2", label=""):
    """Dip-only replay for bars with open in [S, EQ). G2 arm.

    Mirrors crash.simulate_window (same accounting/marks), generalised to an
    arbitrary interval with per-coin eligibility masks (warm-up).
    bars: dict j -> Timestamp; opens_bar/sig_bar: dict sym -> array aligned
    with the phase grid positions used for js (NaN where ineligible).
    Returns (cell, ledger_rows).
    """
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
            w = U * KD / (1 + c["n"])
            risk_open = sum(t["w"] * (M_SL * t["sg"] + GAP_ALLOW)
                            for t in taken if t["x"] > c["f"])
            if not budget_ok(risk_open, w, c["sg"]):
                continue
            if arm == "G2":
                open_sum = sum(t["w"] for t in taken if t["x"] > c["f"])
                w = cap_apply(open_sum, w, GCAP)
                if w <= 0:
                    continue
            sym = c["sym"]
            Ha = D[sym]["high"][off:off + 240].astype(float)
            La = D[sym]["low"][off:off + 240].astype(float)
            Ca = D[sym]["close"][off:off + 240].astype(float)
            Oa = D[sym]["open"][off:off + 240].astype(float)
            o2m = D[sym]["open"][off + 240]
            o2 = float(o2m) if np.isfinite(o2m) else np.nan
            ret, x, how, gap = outcome_d0(Ha, La, Ca, Oa, c["f"], c["lv"],
                                          c["sg"], o2, settle)
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
            # MARK FIX (disclosed in REPORT): runner-up NaN closes (outage
            # gaps) hold the last marked value instead of poisoning the DD
            # series. Realised equity E is untouched (NaN-exit rungs are
            # dropped before booking). Leading NaN (no print yet) = 0.
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
    # worst UTC calendar day (boundary-to-boundary marked returns)
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
        # anchor to the ORIGIN + s h lattice:
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


# ============================================================ subcommands
GATE_S = pd.Timestamp("2020-03-12", tz="UTC")
GATE_DAYS = 10


def cmd_gate():
    print("gate: loading perp 1m ...", flush=True)
    start = pd.Timestamp("2019-12-31", tz="UTC")
    end = pd.Timestamp("2021-07-03", tz="UTC")
    idx = None
    D = {}
    for sym in MAJORS5:
        ii, d = load_1m_perp(sym, start, end)
        if idx is None:
            idx = ii
        D[sym] = d
        print(f"  {sym} n={len(ii)}", flush=True)
    grids = build_grids(idx, list(MAJORS5), D)
    ref = json.loads((ROOT / "research/tournament/oc_crash2020"
                      / "results.json").read_text())["cells"]
    cells, ok_all, report = {}, True, {}
    for s in PHASES:
        bts, ob, sg = grids[s]
        js = [j for j, T in enumerate(bts)
              if GATE_S <= T < GATE_S + pd.Timedelta(days=GATE_DAYS)]
        jj = {j: bts[j] for j in js}
        cell, _ = simulate_interval(idx, D, list(MAJORS5), jj, ob, sg,
                                    GATE_S,
                                    GATE_S + pd.Timedelta(days=GATE_DAYS),
                                    label=f"gate_s{s}")
        cells[f"s{s}"] = cell
        r = ref[f"W1_covid0312|s{s}|G2"]
        # recovery_days_7d is derived in crash.main, not in simulate_window;
        # compare the simulate-level fields:
        fields = ("end_equity", "min_marked", "max_loss_pct", "max_dd_pct",
                  "peak_gross", "fills", "stops", "tps", "timeouts",
                  "gap_stops", "gap_max", "worst_minute")
        match = all(cell[k] == r[k] for k in fields)
        report[f"s{s}"] = {"match": bool(match),
                           "diff": {k: (cell[k], r[k]) for k in fields
                                    if cell[k] != r[k]}}
        ok_all &= match
        print(f"s{s} match={match} {cell}", flush=True)
    out = {"pass": bool(ok_all), "cells": cells, "report": report,
           "note": "vendored core vs oc_crash2020 W1 G2 cells"}
    (TMP / "gate.json").write_text(json.dumps(out, indent=1, default=str))
    print("GATE", "PASS" if ok_all else "FAIL", flush=True)
    if not ok_all:
        raise SystemExit(1)


def cmd_years(which):
    gate = json.loads((TMP / "gate.json").read_text())
    if not gate.get("pass"):
        raise SystemExit("gate did not pass; refusing to compute outcomes")
    if which == "presample":
        majors = list(MAJORS4)
        legs = {
            "Y2017": (pd.Timestamp("2017-10-16", tz="UTC"),
                      pd.Timestamp("2018-01-01", tz="UTC")),
            "Y2018": (pd.Timestamp("2018-01-01", tz="UTC"),
                      pd.Timestamp("2019-01-01", tz="UTC")),
            "Y2019": (pd.Timestamp("2019-01-01", tz="UTC"),
                      pd.Timestamp("2020-01-01", tz="UTC")),
            "Y2020p": (pd.Timestamp("2020-01-01", tz="UTC"),
                       pd.Timestamp("2020-09-01", tz="UTC")),
        }
        loader, lname = load_1m_spot, "spot"
        out_name = "presample.json"
        # store-wide first bars (manifest) for the 60-day warm-up rule
        man = json.loads((SPOT / "manifest.json").read_text())["symbols"]
        store_warmup = {s: pd.Timestamp(man[s]["first_bar"])
                        + pd.Timedelta(days=60) for s in majors}
    else:
        majors = list(MAJORS5)
        # exact spans: R3 2023-09-24..2024-09-24 crosses leap day (366d)
        legs = {
            "R1": (pd.Timestamp("2021-09-24", tz="UTC"),
                   pd.Timestamp("2022-09-24", tz="UTC")),
            "R2": (pd.Timestamp("2022-09-24", tz="UTC"),
                   pd.Timestamp("2023-09-24", tz="UTC")),
            "R3": (pd.Timestamp("2023-09-24", tz="UTC"),
                   pd.Timestamp("2024-09-24", tz="UTC")),
            "R4": (pd.Timestamp("2024-09-24", tz="UTC"),
                   pd.Timestamp("2025-09-24", tz="UTC")),
            "R5": (pd.Timestamp("2025-09-24", tz="UTC"),
                   pd.Timestamp("2026-09-24", tz="UTC")),
        }
        loader, lname = load_1m_perp, "perp"
        out_name = "reference.json"
        store_warmup = {}
    cells, ledgers = {}, []
    coins_per_leg = {}
    for leg, (S, E) in legs.items():
        # load window: 100d warm-up for sigma + 1d tail for timeouts
        LS = S - pd.Timedelta(days=100)
        LE = E + pd.Timedelta(days=1)
        idx = None
        D = {}
        warmup_from = {}
        for sym in majors:
            ii, d = loader(sym, LS, LE)
            if idx is None:
                idx = ii
            if which == "presample":
                dd = {"open": d["o"], "high": d["h"], "low": d["l"],
                      "close": d["c"]}
            else:
                dd = d
            present = np.flatnonzero(np.isfinite(dd["close"]))
            if len(present) == 0:
                print(f"{leg} {sym}: no data in window; absent", flush=True)
                continue
            if sym in store_warmup:
                warmup_from[sym] = store_warmup[sym]
            D[sym] = dd
            t_first = idx[int(present[0])]
            print(f"{leg} {sym}: window n={len(ii)} first_in_window={t_first} "
                  f"warm={warmup_from.get(sym)}", flush=True)
        if idx is None:
            raise SystemExit(f"{leg}: no data at all")
        # coins missing from this leg (e.g. XRP in 2017): absent
        coins_per_leg[leg] = sorted(D.keys())
        grids = build_grids(idx, list(D.keys()), D, warmup_from=warmup_from)
        for s in PHASES:
            bts, ob, sg = grids[s]
            js = [j for j, T in enumerate(bts) if S <= T < E]
            jj = {j: bts[j] for j in js}
            if not jj:
                cells[f"{leg}|s{s}"] = None
                continue
            cell, led = simulate_interval(idx, D, list(D.keys()), jj, ob,
                                          sg, S, E, label=f"{leg}_s{s}")
            cells[f"{leg}|s{s}"] = cell
            ledgers.extend(led)
            print(leg, f"s{s}", cell, flush=True)
    import hashlib
    chk = hashlib.sha256(repr(sorted(ledgers)).encode()).hexdigest()[:16]
    out = {"store": lname, "coins_per_leg": coins_per_leg,
           "legs": {k: (str(v[0]), str(v[1])) for k, v in legs.items()},
           "cells": cells, "ledger_checksum": chk,
           "n_ledger_rows": len(ledgers)}
    (TMP / out_name).write_text(json.dumps(out, indent=1, default=str))
    print("checksum", chk, "rows", len(ledgers), flush=True)


def cmd_finalize():
    pre = json.loads((TMP / "presample.json").read_text())
    ref = json.loads((TMP / "reference.json").read_text())
    gate = json.loads((TMP / "gate.json").read_text())
    out = {
        "config": {
            "core": "vendored verbatim from oc_crash2020/crash.py "
                    "(compute_sigma/n_vector/find_fill/outcome_d0/"
                    "budget_ok/cap_apply); gate PASS vs W1 cells",
            "gate_pass": gate["pass"],
            "rungs": list(RUNGS), "live": [LIVE_A, LIVE_B],
            "maker": MAKER, "taker": TAKER, "fund_long_settle": FUND,
            "kd": KD, "unit": U, "budget": BUDGET, "gap_allow": GAP_ALLOW,
            "gross_cap_G2": GCAP, "arm": "G2",
            "grid": "4h from 2020-01-01 00:00 UTC + phase h (all integer j)",
            "presample_store": "data/raw/spot_1m_presample_20261007 (SPOT)",
            "reference_store": "perp intraday ( btc/majors_intraday_20260924)",
            "note": "dip-only; R2 agent size=1, scale=governor=1; "
                    "spot prices with perp gate costs (labelled caveat)",
        },
        "presample": pre, "reference": ref,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("results.json written", flush=True)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    which = sys.argv[1] if len(sys.argv) > 1 else "gate"
    if which == "gate":
        cmd_gate()
    elif which in ("presample", "reference"):
        cmd_years(which)
    elif which == "finalize":
        cmd_finalize()
    else:
        raise SystemExit(f"unknown subcommand {which}")
