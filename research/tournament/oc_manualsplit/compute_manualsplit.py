"""oc_manualsplit: MANUAL split-TP bracket ladder (IDEAS_20261007c B8).

Pre-registered rows (PLAN.md, frozen before any run):
  M5_human       deployed MANUAL reference (must reproduce oc_manualcap exactly)
  H1_split75_150 M5_human with every taken dip rung split into two halves
                 rn/2 + rn/2 at TP ratios (0.75, 1.5) x deployed m0
  H2_split50_100 same with ratios (0.5, 1.0) x deployed m0

Harness = oc_manualcap copy (M5 pipe v367, human schedule win_start=15 /
sleeve_start=16, night bar skipped for books AND dips, agents ON, gate costs),
4 phases, reset_metric.year_reset per anchor + v388.mix full-path DD.

  python research/tournament/oc_manualsplit/compute_manualsplit.py --validate
  python research/tournament/oc_manualsplit/compute_manualsplit.py --heavy
"""

from __future__ import annotations

import argparse
import gc
import inspect
import json
import pickle
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"
TMP = HERE / "tmp"
CACHE = TMP / "oc_manualsplit_runs.pkl"

# ---- pre-registered constants (mirrored in tests) ----
WIN_START = 15
SLEEVE_START = 16
RATIOS_H1 = (0.75, 1.5)
RATIOS_H2 = (0.5, 1.0)
RATIOS = {"H1_split75_150": RATIOS_H1, "H2_split50_100": RATIOS_H2}
BASE_SIZE_MULT = 4.375
RISK_BUDGET = 0.26
MIN_NOTIONAL_HALF = 5.0  # Bybit linear-perp default minimum per half (USDT)
ACCOUNT = 10000.0
MAKER, TAKER, FUND_LONG = 0.0002, 0.00055, 0.0001  # gate costs
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
VOL_CAP = 2.0
ROWS = ["M5_human", "H1_split75_150", "H2_split50_100"]
ENGINE_MODE = {"M5_human": "ref", "H1_split75_150": "h1",
               "H2_split50_100": "h2"}

# ---- engine patch anchors (must each occur exactly once) ----
OLD_TP_LINE = ("                tp = lv * (1 + (m_sleeve_tp if sleeve_tp is None "
               "else float(sleeve_tp(i, a, r, f))) * sg)")
OLD_SL_LINE = "                sl = lv * (1 - _msl(a) * sg)"
OLD_HA_LINE = ("                Ha, La, Ca, Oa = "
               "(X[i, :, a].astype(float) for X in (H, L, C, O))")
BODY_START = '                x, ret, xk = end_m, None, "rung_timeout"'
BODY_END = "                path += rn * seg"


def split_tp_mult(m0: float, ratio: float) -> float:
    """Deployed TP multiplier m0 scaled by the split ratio (pure helper)."""
    return float(m0) * float(ratio)


def half_notional(rn: float, prev_eq: float,
                  account: float = ACCOUNT) -> float:
    """Notional of one half rung in USDT (pure helper)."""
    return float(rn / 2) * float(prev_eq) * float(account)


def should_merge(rn: float, prev_eq: float,
                 min_notional: float = MIN_NOTIONAL_HALF) -> bool:
    """True when a half falls below the Bybit minimum (pure helper)."""
    return half_notional(rn, prev_eq) < float(min_notional)


def rung_exit_touch(lows, highs, opens, lv: float, sg: float,
                    mult: float, sl_mult: float = 8.0):
    """Hand-checkable mirror of the engine touch-mode dip exit (pure helper).

    lows/highs/opens are 1m arrays from f+1 to end_m-1. Returns (kind, ret)
    with the same fee convention as the engine (TP: -2*MAKER, stop/timeout
    style here: stop -MAKER-TAKER). Stop-first on a same-minute tie.
    """
    tp = float(lv) * (1.0 + float(mult) * float(sg))
    sl = float(lv) * (1.0 - float(sl_mult) * float(sg))
    for k in range(len(lows)):
        hs = float(lows[k]) <= sl
        ht = float(highs[k]) > tp
        if hs:
            px = min(sl, float(opens[k]))
            return "rung_sl", px / float(lv) - 1 - MAKER - TAKER
        if ht:
            return "rung_tp", tp / float(lv) - 1 - 2 * MAKER
    return "rung_timeout", None


def make_split_simulate(eu, ratios):
    """eu.simulate with each taken dip rung split into two halves.

    Budget/gross-cap checks run ONCE on the full rn before the split; both
    halves are then processed with the same stop and their own TP
    (ratios x deployed m0). Halves below MIN_NOTIONAL_HALF merge into one
    order with the deployed TP (counted in stats split_merged).
    """
    src = inspect.getsource(eu.simulate)
    assert src.count(OLD_HA_LINE) == 1, "dip HA anchor not unique"
    assert src.count(OLD_TP_LINE) == 1, "dip TP anchor not unique"
    assert src.count(OLD_SL_LINE) == 1, "dip SL anchor not unique"
    assert src.count(BODY_START) == 1, "dip body start not unique"
    assert src.count(BODY_END) == 1, "dip body end not unique"
    i_body = src.find(BODY_START)
    i_end = src.find(BODY_END) + len(BODY_END)
    body = src[i_body:i_end]
    # indent the whole exit body one extra level (inside the halves loop)
    indented = "\n".join(("    " + ln if ln.strip() else ln)
                         for ln in body.splitlines())
    # tag each half in its events (extra kw, ignored by book stats)
    indented = indented.replace(
        'weight=float(rn), rung=float(rungs[r])))',
        'weight=float(rn), rung=float(rungs[r]), half=int(_h)))')
    indented = indented.replace(
        'weight=float(rn), ret=float(ret)))',
        'weight=float(rn), ret=float(ret), half=int(_h)))')
    head = (OLD_HA_LINE + "\n"
            "                _m0 = (m_sleeve_tp if sleeve_tp is None "
            "else float(sleeve_tp(i, a, r, f)))\n"
            "                sl = lv * (1 - _msl(a) * sg)\n"
            "                _ratios = (%r, %r)\n"
            "                _half_not = (rn / 2) * prev_eq * ACCOUNT\n"
            "                if _half_not < %r:\n"
            "                    _pairs = [(rn, _m0, 0)]\n"
            '                    stats["split_merged"] = '
            'stats.get("split_merged", 0) + 1\n'
            "                else:\n"
            "                    _pairs = [(rn / 2, _m0 * _ratios[0], 1), "
            "(rn / 2, _m0 * _ratios[1], 2)]\n"
            '                    stats["split_halves"] = '
            'stats.get("split_halves", 0) + 2\n'
            "                for _rn_save, _m_save, _h in _pairs:\n"
            "                    rn = _rn_save\n"
            "                    tp = lv * (1 + _m_save * sg)\n"
            % (float(ratios[0]), float(ratios[1]), float(MIN_NOTIONAL_HALF)))
    new_block = head + indented
    old_block = OLD_HA_LINE + "\n" + OLD_TP_LINE + "\n" + OLD_SL_LINE + "\n" + body
    assert src.count(old_block) == 1, "dip block anchor not unique"
    patched = src.replace(old_block, new_block)
    g = eu.simulate.__globals__
    ns: dict = {}
    exec(patched, g, ns)  # noqa: S102 - audited pattern (cf. oc_manualnight)
    fn = ns.get("simulate")
    if fn is None:  # pragma: no cover
        raise RuntimeError("patched simulate missing")
    fn._patched_src = patched  # test hook
    fn._ratios = tuple(float(v) for v in ratios)
    return fn


def make_simulate(eu, mode: str):
    """ref = unpatched identity; h1/h2 = split-TP patched."""
    if mode == "ref":
        return eu.simulate
    if mode == "h1":
        return make_split_simulate(eu, RATIOS_H1)
    if mode == "h2":
        return make_split_simulate(eu, RATIOS_H2)
    raise ValueError(mode)  # pragma: no cover


def _load(name: str, path: Path):
    spec = __import__("importlib.util", fromlist=["util"]).spec_from_file_location(
        name, path)
    mod = __import__("importlib.util", fromlist=["module_from_spec"]).module_from_spec(
        spec)
    spec.loader.exec_module(mod)
    return mod


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
            print("manualsplit: RAM check failed (%s), retry in 300 s" % exc,
                  flush=True)
            time.sleep(300)
            continue
        if free_kb > need_kb:
            return
        print("manualsplit: %.2f GB free, waiting for > %.0f GB"
              % (free_kb / 1048576, min_gb), flush=True)
        time.sleep(300)


def geo_mean_monthly(Rs) -> float:
    g = 1.0
    for r in Rs:
        g *= 1.0 + float(r) / 100.0
    return 100.0 * (g ** (1.0 / len(Rs)) - 1.0)


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
    import pandas as pd  # local import keeps torch-first rule out of scope
    tab = pd.read_parquet(
        ROOT / "artifacts/research/engine_real/v321_r2_table_m0.parquet")
    vals = sorted(float(v) for v in tab["tp"].unique())
    assert vals == [0.5, 1.0, 1.5], vals
    print("R2 TP table OK: deployed TP takes values %s (ratio rule applies)"
          % vals, flush=True)
    return {"m5_ref": {"R5": 3.728, "W": 0.847, "maxDD": 17.94,
                       "fullDD": 17.79}}


# --------------------------------------------------------------------------
# Stage 1: 4-phase MANUAL runs (heavy)
# --------------------------------------------------------------------------
def run_phase(shift: int):
    wait_for_ram(2.0)
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load("pod_msplit_%d" % shift,
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load("hist_msplit_%d" % shift, ROOT / "backend/history_tm.py")
    v221 = pof._load("v221_msplit_%d" % shift,
                     pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load("fw_msplit_%d" % shift, ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    sims = {"ref": eu.simulate, "h1": make_simulate(eu, "h1"),
            "h2": make_simulate(eu, "h2")}
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
        pol = trade["policy"]
        trade["policy"] = lambda i, a, st, pol=pol: (
            ("wait" if st["pos"] == 0 else "hold")
            if hours[i] == night else pol(i, a, st))
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
            years.append(dict(nb=int(nb), wb=int(wb), nr=len(rr),
                              wr=int(sum(r > 0 for r in rr))))
            yy = m["yearly"][y]
            ch.append(dict(net=yy["net_pct"] / 100, dd=yy["dd_1m_pct"]))
        out[row] = dict(run=run, wins=years, cross=ch,
                        merged=int(stats_hold.get("split_merged", 0)),
                        halves=int(stats_hold.get("split_halves", 0)))
        print(shift, row, [round(100 * v["net"], 1) for v in ch],
              [v["dd"] for v in ch],
              "merged=%d halves=%d" % (out[row]["merged"], out[row]["halves"]),
              flush=True)
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
    v388 = pof._load("v388_msplit_score", RD / "v388/v388_bot_stop_distance.py")
    rm = pof._load("reset_msplit_score",
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
        mg = sum(allres[s][row]["merged"] for s in range(4))
        hv = sum(allres[s][row]["halves"] for s in range(4))
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
            merged=int(mg), halves=int(hv),
            cross_Rmean=round(float(np.mean(r_ph)), 3),
        )
    return table


def robust_pick(table: dict) -> str:
    """H1 vs H2 on dev4 only: DD<=20, no losing dev year; prefer mean>=5;
    then highest dev4 WORST year; ties -> higher mean."""
    cands = {}
    for row in ("H1_split75_150", "H2_split50_100"):
        t = table[row]
        if t["DDdev4"] <= 20 and t["losing_dev4"] == 0:
            cands[row] = t
    if not cands:
        return "none-eligible"
    hot = {k: v for k, v in cands.items() if v["Rdev4"] >= 5}
    pool = hot or cands
    best = max(pool, key=lambda k: (pool[k]["Wdev4"], pool[k]["Rdev4"]))
    return best


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
    check_harness_identity(allres)
    table = score_all(allres)
    pick = robust_pick(table)
    out = {
        "meta": {
            "idea": "IDEAS_20261007c B8: MANUAL split-TP bracket ladder",
            "harness": ("MANUAL 4-phase (M5 pipe v367, human schedule "
                        "win_start=15 / sleeve_start=16, night bar skipped, "
                        "agents ON, gate costs maker 0.0002 / taker 0.00055 / "
                        "longs pay 0.0001 per 8h)"),
            "metric": ("reset_metric.year_reset per anchor + v388.mix "
                       "full-path DD (v421/v422 convention); selection on "
                       "dev years 2021-2024 only; last year POST-HOC"),
            "rows": {
                "M5_human": "deployed reference (reproduces oc_manualcap)",
                "H1_split75_150": "candidate 1: dip halves at 0.75x/1.5x m0",
                "H2_split50_100": "candidate 2: dip halves at 0.5x/1.0x m0",
            },
            "baseline": base,
            "pick": pick,
            "costs": {"maker": MAKER, "taker": TAKER, "fund_long_8h": FUND_LONG},
            "min_notional_half": MIN_NOTIONAL_HALF,
        },
        "rows": table,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for row, v in table.items():
        print(row, "R5", v["R5"], "W", v["W"], "maxDD", v["maxDD"],
              "fullDD", v["fullDD"], "Rdev4", v["Rdev4"], "Wdev4", v["Wdev4"],
              "DDdev4", v["DDdev4"], "Rlast", v["Rlast"],
              "book_win", v["book_win"], "rung_win", v["rung_win"],
              "merged", v["merged"], "halves", v["halves"], flush=True)
    print("PICK (dev4 only):", pick, flush=True)


if __name__ == "__main__":
    main()
