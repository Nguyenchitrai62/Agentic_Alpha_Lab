"""oc_kronosmanual: ex-ante (bar-open) corr-aware dip sizing from Kronos drop forecasts.

Pre-registered rows (PLAN.md, frozen before any run):
  M5_human  deployed MANUAL reference (must reproduce oc_manualcap exactly)
  KM1       every dip bracket rung x 1/(1+E_n), rescaled x s1_A
  KM2       every bracket rung x 1/(1+2*E_n), rescaled x s2_A
  CTRL      every bracket rung x 1/(1+c_A), constant (no second rescaling)

E_n(coin c, bar open T, clock shift s) = sum of pdrop2 of the four OTHER
majors at (T, s) from
research/tournament/oc_kronoshidden/kronos_features_4shift.parquet
(missing-data rule in PLAN.md: <3 of 4 others finite -> mult 1.0, else
sum_avail * 4 / n_avail). Training rows for anchor A: feature rows with
T < A - 7d (pooled 5 coins x 4 shifts); c_A = mean E_n, s1_A/s2_A =
1/mean(w1/w2). Book orders unchanged; dip scaling via sleeve_filter
(bar-open only). Human schedule win_start=15 / sleeve_start=16, night bar
skipped, agents ON, gate costs. 4 phases, reset_metric.year_reset per
anchor + v388.mix full-path DD.

  python research/tournament/oc_kronosmanual/compute_kronosmanual.py --validate
  python research/tournament/oc_kronosmanual/compute_kronosmanual.py --heavy
"""

from __future__ import annotations

import argparse
import gc
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
CACHE = TMP / "oc_kronosmanual_runs.pkl"
KRONOS_PATH = (ROOT / "research/tournament/oc_kronoshidden"
               / "kronos_features_4shift.parquet")

# ---- pre-registered constants (mirrored in tests) ----
WIN_START = 15
SLEEVE_START = 16
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
KM1_K = 1.0
KM2_K = 2.0
EMBARGO_DAYS = 7
ACCOUNT = 10000.0
MAKER, TAKER, FUND_LONG = 0.0002, 0.00055, 0.0001  # gate costs
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
ROWS = ["M5_human", "KM1", "KM2", "CTRL"]
ENGINE_MODE = {"M5_human": "ref", "KM1": "km1", "KM2": "km2", "CTRL": "ctrl"}


# --------------------------------------------------------------------------
# Pure helpers (unit-tested; no data access)
# --------------------------------------------------------------------------
def raw_mult(e_n: float, variant: str, c: float = 0.0) -> float:
    """Raw bar-open Kronos multiplier before training-anchored rescaling."""
    e = float(e_n)
    if variant == "km1":
        return 1.0 / (1.0 + e)
    if variant == "km2":
        return 1.0 / (1.0 + KM2_K * e)
    if variant == "ctrl":
        return 1.0 / (1.0 + float(c))
    raise ValueError(variant)  # pragma: no cover


def expected_n(others: list) -> float | None:
    """E_n from the four other majors' pdrop2 (missing-data rule, PLAN.md).

    others: list of 4 pdrop2 values (float or NaN/None). Returns None when
    fewer than 3 are finite (caller maps to mult 1.0); else
    sum_avail * 4 / n_avail.
    """
    vals = [float(v) for v in others
            if v is not None and np.isfinite(float(v))]
    if len(vals) < 3:
        return None
    return float(sum(vals)) * 4.0 / float(len(vals))


def final_mult(variant: str, e_n: float | None, scale: float,
               c: float = 0.0) -> float:
    """Final rung multiplier: raw x training scale (neutral 1.0 if no E_n)."""
    if e_n is None:
        return 1.0
    if variant == "ctrl":
        return raw_mult(e_n, "ctrl", c)
    return raw_mult(e_n, variant) * float(scale)


def anchor_of(t: pd.Timestamp, shift: int) -> int:
    """Dev/most-recent year index 0..4 holding bar open T on phase shift.

    Year y covers [a0, min(a0+365d, live1)) with a0 = ANCH5[y]+sh.
    Bars at/after live1 use the last anchor's stats (beyond scoring).
    """
    sh = pd.Timedelta(hours=shift)
    live1 = Y1 + sh
    tt = pd.Timestamp(t)
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


# --------------------------------------------------------------------------
# Kronos feature loading + per-anchor training stats (fits only, no outcomes)
# --------------------------------------------------------------------------
def load_kronos() -> dict:
    """Load (sym, shift, T) -> pdrop2. Asserts all 20 (shift, sym) groups."""
    df = pd.read_parquet(KRONOS_PATH, columns=["sym", "shift", "T", "pdrop2"])
    groups = df.groupby(["shift", "sym"]).size()
    assert len(groups) == 20, "kronos groups %d != 20: %s" % (len(groups), groups)
    assert set(df["sym"].unique()) == set(MAJORS), df["sym"].unique()
    out: dict = {}
    for sym, shift, t, p in zip(df["sym"], df["shift"],
                                df["T"], df["pdrop2"]):
        out[(str(sym), int(shift), pd.Timestamp(t))] = float(p)
    return out


def training_stats(kronos: dict) -> dict:
    """Per-anchor c_A / s1_A / s2_A from rows with T < A - 7d (pooled)."""
    by_t: dict = {}
    for (sym, shift, t), p in kronos.items():
        by_t.setdefault((shift, t), {})[sym] = p
    fits: dict = {}
    for y, a in enumerate(ANCH5):
        cutoff = pd.Timestamp(a, tz="UTC") - pd.Timedelta(days=EMBARGO_DAYS)
        ens, w1s, w2s = [], [], []
        for (shift, t), mp in by_t.items():
            if pd.Timestamp(t) >= cutoff:
                continue
            for coin in MAJORS:
                others = [mp.get(o) for o in MAJORS if o != coin]
                e = expected_n(others)
                if e is None:
                    continue
                ens.append(e)
                w1s.append(raw_mult(e, "km1"))
                w2s.append(raw_mult(e, "km2"))
        assert len(ens) > 0, "no training rows for anchor %s" % a
        c_a = float(np.mean(ens))
        m1 = float(np.mean(w1s))
        m2 = float(np.mean(w2s))
        fits[a] = dict(c=c_a, m1=m1, m2=m2, s1=1.0 / m1, s2=1.0 / m2,
                       n_train=int(len(ens)))
    return fits


def kronos_mult_for(coin: str, t: pd.Timestamp, shift: int, variant: str,
                    kronos: dict, fits: dict) -> float:
    """Final bar-open multiplier for one (coin, bar, shift) and variant."""
    a = ANCH5[anchor_of(t, shift)]
    others = [kronos.get((o, shift, pd.Timestamp(t))) for o in MAJORS
              if o != coin]
    e = expected_n(others)
    if variant == "km1":
        return final_mult("km1", e, fits[a]["s1"])
    if variant == "km2":
        return final_mult("km2", e, fits[a]["s2"])
    if variant == "ctrl":
        return final_mult("ctrl", e, 1.0, fits[a]["c"])
    raise ValueError(variant)  # pragma: no cover


def build_kronos_filter(hours, night, idx, cols, shift, variant, kronos,
                        fits):
    """sleeve_filter: 0 on the night bar else the Kronos mult (bar-open only).

    Mult depends only on (coin, holding-bar T, shift) via the feature table
    and pre-anchor fits; never on minute or fill data.
    """
    cache: dict = {}

    def filt(i, a, r):
        if hours[i] == night:
            return 0.0
        key = (i, a)
        m = cache.get(key)
        if m is None:
            t = idx[i] + pd.Timedelta(hours=4)
            m = kronos_mult_for(cols[a], t, shift, variant, kronos, fits)
            cache[key] = m
        return m

    filt.cache = cache
    return filt


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
            print("kronosmanual: RAM check failed (%s), retry in 300 s" % exc,
                  flush=True)
            time.sleep(300)
            continue
        if free_kb > need_kb:
            return
        print("kronosmanual: %.2f GB free, waiting for > %.0f GB"
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
    df = pd.read_parquet(KRONOS_PATH, columns=["sym", "shift"])
    groups = df.groupby(["shift", "sym"]).size()
    assert len(groups) == 20, "kronos groups %d != 20" % len(groups)
    assert set(df["sym"].unique()) == set(MAJORS), df["sym"].unique()
    print("kronos 4shift OK: 20 (shift, sym) groups, syms %s"
          % sorted(df["sym"].unique()), flush=True)
    return {"m5_ref": {"R5": 3.728, "W": 0.847, "maxDD": 17.94,
                       "fullDD": 17.79}}


# --------------------------------------------------------------------------
# Stage 1: 4-phase MANUAL runs (heavy)
# --------------------------------------------------------------------------
def run_phase(shift: int, kronos: dict, fits: dict):
    wait_for_ram(2.0)
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load("pod_kman_%d" % shift,
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load("hist_kman_%d" % shift, ROOT / "backend/history_tm.py")
    v221 = pof._load("v221_kman_%d" % shift,
                     pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load("fw_kman_%d" % shift, ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
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
        pol = trade["policy"]
        trade["policy"] = lambda i, a, st, pol=pol: (
            ("wait" if st["pos"] == 0 else "hold")
            if hours[i] == night else pol(i, a, st))
        kw["sleeve_start"] = SLEEVE_START
        if mode == "ref":
            kw["sleeve_filter"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0
        else:
            kw["sleeve_filter"] = build_kronos_filter(
                hours, night, idx, cols, shift, mode, kronos, fits)
        events: list = []
        stats_hold.clear()
        eu.simulate(books, opens, prep, trade=trade, win_start=WIN_START,
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
        out[row] = dict(run=run, wins=years, cross=ch)
        print(shift, row, [round(100 * v["net"], 1) for v in ch],
              [v["dd"] for v in ch], flush=True)
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
    v388 = pof._load("v388_kman_score", RD / "v388/v388_bot_stop_distance.py")
    rm = pof._load("reset_kman_score",
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
        )
    return table


def robust_pick(table: dict) -> str:
    """KM1 vs KM2 on dev4 only: DD<=20, no losing dev year; prefer mean>=5;
    then highest dev4 WORST year; ties -> higher mean."""
    cands = {}
    for row in ("KM1", "KM2"):
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
    kronos = load_kronos()
    fits = training_stats(kronos)
    for a, f in fits.items():
        print("fit %s: c=%.4f s1=%.4f s2=%.4f n=%d"
              % (a, f["c"], f["s1"], f["s2"], f["n_train"]), flush=True)
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
        s, out = run_phase(shift, kronos, fits)
        allres[s] = out
        CACHE.write_bytes(pickle.dumps(allres))
        print("phase %d cached" % s, flush=True)
    check_harness_identity(allres)
    table = score_all(allres)
    pick = robust_pick(table)
    out = {
        "meta": {
            "idea": "oc_kronosmanual: ex-ante Kronos pdrop2 corr-aware dip sizing",
            "harness": ("MANUAL 4-phase (M5 pipe v367, human schedule "
                        "win_start=15 / sleeve_start=16, night bar skipped, "
                        "agents ON, gate costs maker 0.0002 / taker 0.00055 / "
                        "longs pay 0.0001 per 8h)"),
            "metric": ("reset_metric.year_reset per anchor + v388.mix "
                       "full-path DD (v421/v422 convention); selection KM1 "
                       "vs KM2 on dev years 2021-2024 only; last year "
                       "POST-HOC"),
            "rows": {
                "M5_human": "deployed reference (reproduces oc_manualcap)",
                "KM1": "dip rungs x 1/(1+E_n), rescaled to training mean 1",
                "KM2": "dip rungs x 1/(1+2*E_n), rescaled to training mean 1",
                "CTRL": "dip rungs x 1/(1+c_A), constant exposure control",
            },
            "baseline": base,
            "fits": fits,
            "pick": pick,
            "costs": {"maker": MAKER, "taker": TAKER, "fund_long_8h": FUND_LONG},
            "caveat": ("Kronos released 2025-08: dev years likely in "
                       "pretraining -> dev = UPPER BOUND; most recent year "
                       "is the clean test"),
        },
        "rows": table,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for row, v in table.items():
        print(row, "R5", v["R5"], "W", v["W"], "maxDD", v["maxDD"],
              "fullDD", v["fullDD"], "Rdev4", v["Rdev4"], "Wdev4", v["Wdev4"],
              "DDdev4", v["DDdev4"], "Rlast", v["Rlast"],
              "book_win", v["book_win"], "rung_win", v["rung_win"], flush=True)
    print("PICK (dev4 only):", pick, flush=True)


if __name__ == "__main__":
    main()
