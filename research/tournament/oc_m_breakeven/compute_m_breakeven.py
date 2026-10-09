"""oc_m_breakeven: IDEAS9 #2 one-move break-even on the MANUAL product.

Pre-registered rows (PLAN.md, frozen before any run):
  M5_human  deployed MANUAL reference (must reproduce oc_manualcap exactly)
  V1_BE075  M5_human + one-move BE at +0.75sg to exactly entry (book + dip)
  V2_BE050  M5_human + one-move BE at +0.50sg to exactly entry (book + dip)

Book leg uses the engine-native trade be_k/be_off (no engine file edit).
Dip leg uses a patched simulate (audited inspect.getsource pattern cf.
oc_manualsplit): touch-mode exit with BE trigger/arm/search, all else
identical. M5_human uses the unpatched eu.simulate (identity).

  python research/tournament/oc_m_breakeven/compute_m_breakeven.py --validate
  python research/tournament/oc_m_breakeven/compute_m_breakeven.py --heavy
"""

from __future__ import annotations

import argparse
import gc
import inspect
import json
import pickle
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"
TMP = HERE / "tmp"
CACHE = TMP / "oc_m_breakeven_runs.pkl"

# ---- pre-registered constants (mirrored in tests) ----
WIN_START = 15
SLEEVE_START = 16
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
BE_K = {"V1_BE075": 0.75, "V2_BE050": 0.50}
BE_OFF = 0.0  # SL to exactly entry (both legs)
MAKER, TAKER, FUND_LONG = 0.0002, 0.00055, 0.0001  # gate costs
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
ROWS = ["M5_human", "V1_BE075", "V2_BE050"]
ENGINE_MODE = {"M5_human": "ref", "V1_BE075": "v1", "V2_BE050": "v2"}
HEARTBEAT_S = 600

# ---- engine patch anchors (must each occur exactly once) ----
OLD_HA_LINE = ("                Ha, La, Ca, Oa = "
               "(X[i, :, a].astype(float) for X in (H, L, C, O))")
OLD_TP_LINE = ("                tp = lv * (1 + (m_sleeve_tp if sleeve_tp is None "
               "else float(sleeve_tp(i, a, r, f))) * sg)")
OLD_SL_LINE = "                sl = lv * (1 - _msl(a) * sg)"
BODY_START = '                x, ret, xk = end_m, None, "rung_timeout"'
BODY_END = "                path += rn * seg"

_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print("[hb %sZ] %s alive"
              % (datetime.now(timezone.utc).strftime("%H:%M:%S"), tag),
              flush=True)


# --------------------------------------------------------------------------
# Pure helpers (unit-tested; no data access)
# --------------------------------------------------------------------------
def anchor_of(t: pd.Timestamp, shift: int) -> int:
    """Dev/most-recent year index 0..4 of holding-bar open T on phase shift."""
    sh = pd.Timedelta(hours=shift)
    live1 = Y1 + sh
    tt = pd.Timestamp(t)
    if tt.tzinfo is None:
        tt = tt.tz_localize("UTC")
    if tt < pd.Timestamp(ANCH5[0], tz="UTC") + sh:
        return 0
    for y, a in enumerate(ANCH5):
        a0 = pd.Timestamp(a, tz="UTC") + sh
        a1 = min(a0 + pd.Timedelta(days=365), live1)
        if a0 <= tt < a1:
            return y
    return 4


def geo_mean_monthly(Rs) -> float:
    g = 1.0
    for r in Rs:
        g *= 1.0 + float(r) / 100.0
    return 100.0 * (g ** (1.0 / len(Rs)) - 1.0)


def be_trigger_price(entry: float, side: int, be_k: float, sigma: float) -> float:
    """BE trigger mark: entry * (1 + side * be_k * sigma)."""
    return float(entry) * (1.0 + float(side) * float(be_k) * float(sigma))


def be_stop_price(entry: float, side: int, be_off: float = BE_OFF) -> float:
    """Amended SL: entry * (1 + side * be_off); frozen be_off=0.0 = entry."""
    return float(entry) * (1.0 + float(side) * float(be_off))


def dip_be_arm(tb, ks, kt) -> bool:
    """True iff the BE trigger strictly precedes every base trigger.

    tb/ks/kt are absolute minute indices or None. A same-minute tie goes
    to the base exit (BE never arms), as pre-registered.
    """
    if tb is None:
        return False
    if ks is not None and not tb < ks:
        return False
    if kt is not None and not tb < kt:
        return False
    return True


def dip_be_exit(lows, highs, opens, lv: float, sg: float, m0: float,
                be_k: float, sl_mult: float = 8.0, be_off: float = BE_OFF):
    """Hand-checkable mirror of the patched touch-mode dip exit.

    lows/highs/opens are 1m arrays from f+1 to end_m-1. Returns
    (kind, ret, armed, tb_rel). Stop-first on ties; trigger minute uses sl;
    BE-stop search starts at tb+1. Fee convention matches the engine
    (TP: -2*MAKER; stop/BE-stop: -MAKER-TAKER).
    """
    lv = float(lv)
    sg = float(sg)
    tp = lv * (1.0 + float(m0) * sg)
    sl = lv * (1.0 - float(sl_mult) * sg)
    be_trig = lv * (1.0 + float(be_k) * sg)
    be_stop = lv * (1.0 + float(be_off))
    n = len(lows)
    tb = ks = kt = None
    for k in range(n):
        if tb is None and float(highs[k]) >= be_trig:
            tb = k
        if ks is None and float(lows[k]) <= sl:
            ks = k
        if kt is None and float(highs[k]) > tp:
            kt = k
    tba = tb
    armed = dip_be_arm(tba, ks, kt)
    if armed:
        for k in range(tb + 1, n):
            hs = float(lows[k]) <= be_stop
            ht = float(highs[k]) > tp
            if hs:
                px = min(be_stop, float(opens[k]))
                return "rung_sl", px / lv - 1 - MAKER - TAKER, True, tb
            if ht:
                return "rung_tp", tp / lv - 1 - 2 * MAKER, True, tb
        return "rung_timeout", None, True, tb
    for k in range(n):
        hs = float(lows[k]) <= sl
        ht = float(highs[k]) > tp
        if hs:
            px = min(sl, float(opens[k]))
            return "rung_sl", px / lv - 1 - MAKER - TAKER, False, tb
        if ht:
            return "rung_tp", tp / lv - 1 - 2 * MAKER, False, tb
    return "rung_timeout", None, False, tb


def make_be_simulate(eu, be_k: float, be_off: float = BE_OFF):
    """eu.simulate with the dip touch-mode exit replaced by the BE version.

    Book BE is NOT patched here (it comes from the trade dict be_k/be_off).
    Budget/gross-cap checks, sizes, TP table, night skip, costs, settlement,
    timeout and hedge blocks are unchanged. BE-stop exits emit rung_sl with
    be=True; all other events keep be=False.
    """
    src = inspect.getsource(eu.simulate)
    assert src.count(OLD_HA_LINE) == 1, "dip HA anchor not unique"
    assert src.count(OLD_TP_LINE) == 1, "dip TP anchor not unique"
    assert src.count(OLD_SL_LINE) == 1, "dip SL anchor not unique"
    assert src.count(BODY_START) == 1, "dip body start not unique"
    assert src.count(BODY_END) == 1, "dip body end not unique"
    i_body = src.find(BODY_START)
    i_end = src.find(BODY_END) + len(BODY_END)
    head = src[:i_body]
    tail = src[i_end:]
    # head: replace the tp/sl lines to also define BE levels (literals)
    old_head_block = OLD_HA_LINE + "\n" + OLD_TP_LINE + "\n" + OLD_SL_LINE
    assert src.count(old_head_block) == 1, "dip head block not unique"
    new_head_block = (
        OLD_HA_LINE + "\n"
        + OLD_TP_LINE + "\n"
        + OLD_SL_LINE + "\n"
        + "                _be_trig = lv * (1 + " + repr(float(be_k)) + " * sg)\n"
        + "                _be_stop = lv * (1 + " + repr(float(be_off)) + ")\n"
        + "                _be_flag = False\n"
    )
    head = head.replace(old_head_block, new_head_block)
    body = src[i_body:i_end]
    # replace the touch-mode branch with the BE version
    old_touch = (
        "                elif f + 1 < end_m:\n"
        "                    hs = La[f + 1:end_m] <= sl\n"
        "                    ht = Ha[f + 1:end_m] > tp * (1 + ft)\n"
        "                    hit = hs | ht\n"
        "                    if hit.any():\n"
        "                        k = int(np.argmax(hit))\n"
        "                        x = f + 1 + k\n"
        "                        if hs[k]:\n"
        "                            ret = _slip(min(sl, Oa[x]), 1, La[x], np.nan) / lv - 1 - MAKER - TAKER\n"
        '                            stats["rung_stops"] += 1\n'
        '                            xk = "rung_sl"\n'
        "                        else:\n"
        "                            ret = tp / lv - 1 - 2 * MAKER\n"
        '                            stats["rung_tps"] += 1\n'
        '                            xk = "rung_tp"\n'
    )
    assert body.count(old_touch) == 1, "dip touch block not unique"
    new_touch = (
        "                elif f + 1 < end_m:\n"
        "                    _hb = Ha[f + 1:end_m] >= _be_trig\n"
        "                    _hs0 = La[f + 1:end_m] <= sl\n"
        "                    _ht0 = Ha[f + 1:end_m] > tp * (1 + ft)\n"
        "                    _tb = int(np.argmax(_hb)) if _hb.any() else None\n"
        "                    _ks = int(np.argmax(_hs0)) if _hs0.any() else None\n"
        "                    _kt = int(np.argmax(_ht0)) if _ht0.any() else None\n"
        "                    _tba = (f + 1 + _tb) if _tb is not None else None\n"
        "                    _ksa = (f + 1 + _ks) if _ks is not None else None\n"
        "                    _kta = (f + 1 + _kt) if _kt is not None else None\n"
        "                    _armed = (_tba is not None and (_ksa is None or _tba < _ksa) and (_kta is None or _tba < _kta))\n"
        "                    if _armed:\n"
        '                        stats["be_armed"] = stats.get("be_armed", 0) + 1\n'
        "                    if _armed:\n"
        "                        _s0 = _tba + 1\n"
        "                        if _s0 < end_m:\n"
        "                            _hs2 = La[_s0:end_m] <= _be_stop\n"
        "                            _ht2 = Ha[_s0:end_m] > tp * (1 + ft)\n"
        "                            _hit2 = _hs2 | _ht2\n"
        "                            if _hit2.any():\n"
        "                                _k2 = int(np.argmax(_hit2))\n"
        "                                x = _s0 + _k2\n"
        "                                if _hs2[_k2]:\n"
        "                                    ret = _slip(min(_be_stop, Oa[x]), 1, La[x], np.nan) / lv - 1 - MAKER - TAKER\n"
        '                                    stats["rung_stops"] += 1\n'
        '                                    stats["be_exits"] = stats.get("be_exits", 0) + 1\n'
        '                                    xk = "rung_sl"\n'
        "                                    _be_flag = True\n"
        "                                else:\n"
        "                                    ret = tp / lv - 1 - 2 * MAKER\n"
        '                                    stats["rung_tps"] += 1\n'
        '                                    xk = "rung_tp"\n'
        "                    if ret is None and not _armed:\n"
        "                        _hit = _hs0 | _ht0\n"
        "                        if _hit.any():\n"
        "                            k = int(np.argmax(_hit))\n"
        "                            x = f + 1 + k\n"
        "                            if _hs0[k]:\n"
        "                                ret = _slip(min(sl, Oa[x]), 1, La[x], np.nan) / lv - 1 - MAKER - TAKER\n"
        '                                stats["rung_stops"] += 1\n'
        '                                xk = "rung_sl"\n'
        "                            else:\n"
        "                                ret = tp / lv - 1 - 2 * MAKER\n"
        '                                stats["rung_tps"] += 1\n'
        '                                xk = "rung_tp"\n'
    )
    body = body.replace(old_touch, new_touch)
    # label BE-stop exits in events (second append); base exits keep be=False
    old_ev = (
        '                    events.append(dict(t=t0 + pd.Timedelta(minutes=int(min(x, 240)) + late), symbol=cols[a], kind=xk, side="sell",\n'
        '                                       price=float(lv * (1 + ret)), weight=float(rn), ret=float(ret)))\n'
    )
    assert body.count(old_ev) == 1, "dip events block not unique"
    new_ev = (
        '                    events.append(dict(t=t0 + pd.Timedelta(minutes=int(min(x, 240)) + late), symbol=cols[a], kind=xk, side="sell",\n'
        '                                       price=float(lv * (1 + ret)), weight=float(rn), ret=float(ret), be=bool(_be_flag)))\n'
    )
    body = body.replace(old_ev, new_ev)
    # reset the per-rung flag at the top of the rung body (after x, ret, xk)
    body = body.replace(
        BODY_START,
        BODY_START + "\n                _be_flag = False",
        1,
    )
    patched = head + body + tail
    g = eu.simulate.__globals__
    ns: dict = {}
    exec(patched, g, ns)  # noqa: S102 - audited pattern (cf. oc_manualsplit)
    fn = ns.get("simulate")
    if fn is None:  # pragma: no cover
        raise RuntimeError("patched simulate missing")
    fn._patched_src = patched  # test hook
    fn._be_k = float(be_k)
    fn._be_off = float(be_off)
    return fn


def make_simulate(eu, mode: str):
    """ref = unpatched identity; v1/v2 = dip-BE patched."""
    if mode == "ref":
        return eu.simulate
    if mode == "v1":
        return make_be_simulate(eu, BE_K["V1_BE075"], BE_OFF)
    if mode == "v2":
        return make_be_simulate(eu, BE_K["V2_BE050"], BE_OFF)
    raise ValueError(mode)  # pragma: no cover


def wait_for_ram(min_gb: float = 2.0) -> None:
    need_kb = min_gb * 1048576
    while True:
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"],
                text=True, timeout=120)
            free_kb = float(out.strip().split()[0])
        except Exception as exc:
            print("m_breakeven: RAM check failed (%s), retry in 300 s" % exc,
                  flush=True)
            time.sleep(300)
            continue
        if free_kb > need_kb:
            return
        print("m_breakeven: %.2f GB free, waiting for > %.0f GB"
              % (free_kb / 1048576, min_gb), flush=True)
        time.sleep(300)


# --------------------------------------------------------------------------
# Stage 0: reproduce the M5_human baseline (read-only) or STOP
# --------------------------------------------------------------------------
def validate_baselines() -> dict:
    man = json.loads(
        (ROOT / "research/diagnostics/oc_manualcap/results.json").read_text())
    m5 = man["rows"]["M5_human"]
    assert (m5["R5"], m5["W"], m5["maxDD"], m5["fullDD"], m5["book_win"]) == \
        (3.728, 0.847, 17.94, 17.79, 0.6482), m5
    print("M5_human reference OK: R5 3.728 / W 0.847 / maxDD 17.94 / "
          "fullDD 17.79 / win .6482", flush=True)
    assert set(BE_K) == {"V1_BE075", "V2_BE050"}, BE_K
    assert BE_K["V1_BE075"] == 0.75 and BE_K["V2_BE050"] == 0.50
    assert BE_OFF == 0.0
    print("BE fractions frozen: V1 0.75sg / V2 0.50sg -> entry (off 0.0)",
          flush=True)
    return {"m5_ref": {"R5": 3.728, "W": 0.847, "maxDD": 17.94,
                       "fullDD": 17.79}}


# --------------------------------------------------------------------------
# Stage 1: 4-phase MANUAL runs (heavy)
# --------------------------------------------------------------------------
def run_phase(shift: int):
    wait_for_ram(2.0)
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load("pod_mbe_%d" % shift,
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load("hist_mbe_%d" % shift, ROOT / "backend/history_tm.py")
    v221 = pof._load("v221_mbe_%d" % shift,
                     pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load("fw_mbe_%d" % shift, ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    sims = {"ref": eu.simulate, "v1": make_simulate(eu, "v1"),
            "v2": make_simulate(eu, "v2")}
    cap = {}
    stats_hold = {}

    def _summ(idx, net, eq, eq_min, g, stats, eq_max=None):
        cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
                   eq_max=(eq if eq_max is None else eq_max).copy())
        stats_hold.update(stats)
        return {}

    eu.summarize = _summ
    sh = pd.Timedelta(hours=shift)
    live0, live1 = DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    cols = list(books154.columns)
    assert set(cols) == set(MAJORS), cols
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, cols)
    del M
    gc.collect()
    idx = prep["idx"]
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    books = std_books.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / ("r2_table_s%d.parquet" % shift)
    hours = np.asarray((idx + pd.Timedelta(hours=4)).hour)
    night = (20 + shift) % 24
    out = {}
    for row in ROWS:
        mode = ENGINE_MODE[row]
        kw, trade = pof.pipe_setup("v367", hist, v221, v216, idx, cols, True)
        base_pol = trade["policy"]

        def _pol(i, a, st, base_pol=base_pol):
            if hours[i] == night:
                return ("wait" if st["pos"] == 0 else "hold")
            return base_pol(i, a, st)

        trade["policy"] = _pol
        if mode in ("v1", "v2"):
            trade["be_k"] = BE_K[row]
            trade["be_off"] = BE_OFF
        kw["sleeve_start"] = SLEEVE_START
        kw["sleeve_filter"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0
        events: list = []
        stats_hold.clear()
        sims[mode](books, opens, prep, trade=trade, win_start=WIN_START,
                   events=events, **kw)
        m = pof.metrics(cap["idx"], cap["eq"], cap["eq_min"], cap["eq_max"],
                        ANCH5, live0, live1, sh)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        run = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                   eq=(cap["eq"][lv] / base).tolist(),
                   eq_min=(cap["eq_min"][lv] / base).tolist())
        years = []
        ch = []
        for y, a in enumerate(ANCH5):
            a0 = pd.Timestamp(a, tz="UTC") + sh
            a1 = min(a0 + pd.Timedelta(days=365), live1)
            ev = [e for e in events
                  if a0 <= pd.Timestamp(e["t"]) < a1 + pd.Timedelta(hours=8)]
            ts = v216.v213.trade_stats(ev)
            nb = sum((ts.get(k) or {}).get("trades", 0) for k in ("dev", "_hidden"))
            wb = sum(round((ts.get(k) or {}).get("win_rate", 0)
                           * (ts.get(k) or {}).get("trades", 0))
                     for k in ("dev", "_hidden"))
            rr = [float(e["ret"]) for e in ev if e["kind"] in RUNG_KINDS
                  and "ret" in e]
            be_r = sum(1 for e in ev if e["kind"] in RUNG_KINDS
                       and bool(e.get("be", False)))
            be_mv = sum(1 for e in ev if e["kind"] == "sl_move"
                        and str(e.get("why", "")).startswith("break-even"))
            years.append(dict(nb=int(nb), wb=int(wb), nr=len(rr),
                              wr=int(sum(r > 0 for r in rr)),
                              be_rung=int(be_r), be_moves=int(be_mv)))
            yy = m["yearly"][y]
            ch.append(dict(net=yy["net_pct"] / 100, dd=yy["dd_1m_pct"]))
        out[row] = dict(run=run, wins=years, cross=ch,
                        be_armed=int(stats_hold.get("be_armed", 0)),
                        be_exits=int(stats_hold.get("be_exits", 0)),
                        be_moves=int(stats_hold.get("be_moves", 0)))
        print(shift, row, [round(100 * v["net"], 1) for v in ch],
              [v["dd"] for v in ch],
              "be_armed=%d be_exits=%d be_moves=%d"
              % (out[row]["be_armed"], out[row]["be_exits"],
                 out[row]["be_moves"]), flush=True)
        del events
        gc.collect()
    del opens, prep, books
    gc.collect()
    return shift, out


def check_harness_identity(allres) -> None:
    """My M5_human rerun must equal the stored oc_manualcap run bit-exact."""
    stored = pickle.loads(
        (ROOT / "research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl").read_bytes())
    maxd = 0.0
    for s in range(4):
        for k in ("eq", "eq_min"):
            a = np.asarray(allres[s]["M5_human"]["run"][k], dtype=float)
            b = np.asarray(stored[s]["M5_human"]["run"][k], dtype=float)
            assert a.shape == b.shape, (s, k, a.shape, b.shape)
            maxd = max(maxd, float(np.max(np.abs(a - b))))
    print("M5_human harness identity: max abs d(eq) = %.3e" % maxd, flush=True)
    assert maxd <= 1e-12, "harness drift %.3e -- STOP" % maxd


def runs_for_reset(allres, row):
    return {s: {row: allres[s][row]["run"]} for s in allres}


def score_all(allres) -> dict:
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    v388 = pof._load("v388_mbe_score", RD / "v388/v388_bot_stop_distance.py")
    rm = pof._load("reset_mbe_score",
                   ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    table = {}
    for row in ROWS:
        runs = runs_for_reset(allres, row)
        yr = [rm.year_reset(runs, row, y) for y in range(5)]
        Rs = [y["R"] for y in yr]
        DDs = [y["DD"] for y in yr]
        e, mn = v388.mix(runs, row, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        fullDD = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        nb = sum(allres[s][row]["wins"][y]["nb"] for s in range(4) for y in range(5))
        wb = sum(allres[s][row]["wins"][y]["wb"] for s in range(4) for y in range(5))
        nr = sum(allres[s][row]["wins"][y]["nr"] for s in range(4) for y in range(5))
        wr = sum(allres[s][row]["wins"][y]["wr"] for s in range(4) for y in range(5))
        be_r = sum(allres[s][row]["wins"][y]["be_rung"] for s in range(4) for y in range(5))
        be_mv = sum(allres[s][row]["wins"][y]["be_moves"] for s in range(4) for y in range(5))
        be_ar = sum(allres[s][row]["be_armed"] for s in range(4))
        be_ex = sum(allres[s][row]["be_exits"] for s in range(4))
        be_mo = sum(allres[s][row]["be_moves"] for s in range(4))
        r_ph = []
        for s in range(4):
            yy = allres[s][row]["cross"]
            r_ph.append(100 * (np.prod([1 + v["net"] for v in yy]) ** (1 / 60) - 1))
        table[row] = dict(
            years_R=[y["R"] for y in yr], years_DD=[y["DD"] for y in yr],
            years_book_win=[
                round(sum(allres[s][row]["wins"][y]["wb"] for s in range(4))
                      / max(sum(allres[s][row]["wins"][y]["nb"] for s in range(4)), 1), 4)
                for y in range(5)],
            years_rung_win=[
                round(sum(allres[s][row]["wins"][y]["wr"] for s in range(4))
                      / max(sum(allres[s][row]["wins"][y]["nr"] for s in range(4)), 1), 4)
                for y in range(5)],
            R5=round(geo_mean_monthly(Rs), 3), W=round(min(Rs), 3),
            maxDD=round(max(DDs), 2), fullDD=fullDD,
            Rdev4=round(geo_mean_monthly(Rs[:4]), 3),
            Wdev4=round(min(Rs[:4]), 3),
            DDdev4=round(max(DDs[:4]), 2),
            losing_dev4=sum(r < 0 for r in Rs[:4]),
            Rlast=round(Rs[4], 3),
            book_trades=int(nb), book_win=round(wb / nb, 4) if nb else None,
            rung_trades=int(nr), rung_win=round(wr / nr, 4) if nr else None,
            win_all=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None,
            cross_Rmean=round(float(np.mean(r_ph)), 3),
            be_armed=int(be_ar), be_exits=int(be_ex), be_moves=int(be_mo),
            be_rung_exits=int(be_r), be_book_moves=int(be_mv),
            be_k=(BE_K[row] if row in BE_K else None), be_off=BE_OFF,
        )
    return table


def robust_pick(table: dict) -> str:
    """AGENTS.md robust criterion on dev4 ONLY: eligible = DD<=20, no losing
    year; prefer dev4 mean >= 5; then highest dev4 WORST; ties -> higher mean."""
    cand = [r for r in ("V1_BE075", "V2_BE050")
            if table[r]["DDdev4"] <= 20 and table[r]["losing_dev4"] == 0]
    if not cand:
        return "none-eligible"
    hi = [r for r in cand if table[r]["Rdev4"] >= 5.0]
    pool = hi if hi else cand
    best = max(pool, key=lambda r: (table[r]["Wdev4"], table[r]["Rdev4"]))
    return best


def eligibility(table: dict) -> dict:
    out = {}
    for row in ROWS:
        t = table[row]
        out[row] = bool(t["DDdev4"] <= 20 and t["losing_dev4"] == 0)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--heavy", action="store_true")
    args = ap.parse_args()
    base = validate_baselines()
    if not args.heavy:
        print("validate-only done (no engine run). Use --heavy for the "
              "4-phase runs.", flush=True)
        return
    hb = threading.Thread(target=heartbeat, args=("oc_m_breakeven",),
                           daemon=True)
    hb.start()
    TMP.mkdir(parents=True, exist_ok=True)
    if CACHE.exists():
        allres = pickle.loads(CACHE.read_bytes())
        missing = [s for s in range(4) if s not in allres]
        print("loaded cached phase runs (%d/4)" % len(allres), flush=True)
    else:
        allres, missing = {}, list(range(4))
    for shift in missing:
        s, out = run_phase(shift)
        allres[s] = out
        CACHE.write_bytes(pickle.dumps(allres))
        print("phase %d cached" % s, flush=True)
    _stop_hb.set()
    check_harness_identity(allres)
    table = score_all(allres)
    elig = eligibility(table)
    pick = robust_pick(table)
    out = {
        "meta": {
            "idea": "oc_m_breakeven: IDEAS9 #2 one-move break-even (MANUAL)",
            "harness": ("MANUAL 4-phase (M5 pipe v367, human schedule "
                        "win_start=15 / sleeve_start=16, night bar skipped, "
                        "agents ON, gate costs maker 0.0002 / taker 0.00055 / "
                        "longs pay 0.0001 per 8h); book BE via trade "
                        "be_k/be_off, dip BE via patched touch exit"),
            "metric": ("reset_metric.year_reset per anchor + v388.mix "
                       "full-path DD (v421/v422 convention); V1 vs V2 judged "
                       "on dev years 2021-2024 only; last year POST-RELEASE, "
                       "scored once for the pick + M5_human"),
            "rows": {
                "M5_human": "deployed reference (reproduces oc_manualcap)",
                "V1_BE075": "one-move BE at +0.75sg to entry (book+dip)",
                "V2_BE050": "one-move BE at +0.50sg to entry (book+dip)",
            },
            "baseline": base,
            "be": {r: {"be_k": BE_K[r], "be_off": BE_OFF}
                   for r in ("V1_BE075", "V2_BE050")},
            "eligibility_dev4": elig,
            "pick_dev4": pick,
            "costs": {"maker": MAKER, "taker": TAKER, "fund_long_8h": FUND_LONG},
            "caveat": ("BE fractions frozen ex-ante (no fit, no per-year pick); "
                       "dev years are research data; most recent year is "
                       "POST-RELEASE context, scored once, never used "
                       "to choose"),
        },
        "rows": table,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for row, v in table.items():
        print(row, "R5", v["R5"], "W", v["W"], "maxDD", v["maxDD"],
              "fullDD", v["fullDD"], "Rdev4", v["Rdev4"], "Wdev4", v["Wdev4"],
              "DDdev4", v["DDdev4"], "Rlast", v["Rlast"],
              "book_win", v["book_win"], "rung_win", v["rung_win"],
              "be_armed", v["be_armed"], "be_exits", v["be_exits"],
              "be_moves", v["be_moves"],
              "eligible", elig[row], flush=True)
    print("ELIGIBILITY (dev4 only):", elig, "PICK:", pick, flush=True)


if __name__ == "__main__":
    main()
