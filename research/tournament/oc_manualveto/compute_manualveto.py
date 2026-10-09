"""oc_manualveto: MANUAL volatility veto of new bracket placement (IDEAS5 #8).

Pre-registered rows (PLAN.md, frozen before any run):
  M5_human  deployed MANUAL reference (must reproduce oc_manualcap exactly)
  VETO_V1   skip new bracket placement when per-coin 4h sigma360 >
            trailing-90d p80 (skip-only, holds/exits unchanged)
  VETO_V2   V1 OR global BTC 24h range > 2x trailing-30d median

Veto signals are causal past-bar aggregates from existing 1m klines
(one coin in RAM at a time, float32); veto[i,a] uses only bars closing
<= decision-bar close idx[i]. Human schedule win_start=15 /
sleeve_start=16, night bar skipped, agents ON, gate costs. 4 phases,
reset_metric.year_reset per anchor + v388.mix full-path DD. Dev years
2021-2024 choose (robust criterion); most recent year POST-HOC, scored
once, never used to choose.

  python research/tournament/oc_manualveto/compute_manualveto.py --validate
  python research/tournament/oc_manualveto/compute_manualveto.py --heavy
"""

from __future__ import annotations

import argparse
import gc
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
CACHE = TMP / "oc_manualveto_runs.pkl"
VETO_CACHE = TMP / "oc_manualveto_veto.pkl"

# ---- pre-registered constants (mirrored in tests) ----
WIN_START = 15
SLEEVE_START = 16
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
SIG_WIN = 360
SIG_MIN = 120
P80_WIN = 540  # trailing 90d of 4h bars
P80_Q = 0.80
P80_MIN = 120  # warmup: fewer finite sigmas -> no veto
RANGE_BARS = 6  # 24h = 6 x 4h bars
RANGE_MULT = 2.0
MED_WIN = 180  # trailing 30d of 4h bars
MED_MIN = 60  # warmup: fewer finite ranges -> no veto
HIST_START = pd.Timestamp("2020-08-01", tz="UTC")
MAKER, TAKER, FUND_LONG = 0.0002, 0.00055, 0.0001  # gate costs
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
ROWS = ["M5_human", "VETO_V1", "VETO_V2"]
ENGINE_MODE = {"M5_human": "ref", "VETO_V1": "v1", "VETO_V2": "v2"}
HEARTBEAT_S = 600

_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print("[hb %sZ] %s alive"
              % (datetime.now(timezone.utc).strftime("%H:%M:%S"), tag),
              flush=True)


# --------------------------------------------------------------------------
# Pure helpers (unit-tested; no data access)
# --------------------------------------------------------------------------
def sigma360_from_opens(opens: pd.Series) -> pd.Series:
    """Program sigma360: pct_change of 4h opens, rolling 360 std, shift 1.

    Value at i uses returns ending at bar i-1 only (strictly past).
    """
    r = opens.pct_change()
    return r.rolling(SIG_WIN, min_periods=SIG_MIN).std(ddof=1).shift(1)


def trailing_p80(sig: pd.Series) -> pd.Series:
    """Trailing-90d p80 of sigma360 using bars < i only (strictly past)."""
    return sig.shift(1).rolling(P80_WIN, min_periods=P80_MIN).quantile(P80_Q)


def veto_v1_from_sigma(sig: pd.Series, p80: pd.Series) -> pd.Series:
    """Per-coin sigma veto: sigma > trailing p80 (False on warmup/NaN)."""
    v = (sig > p80)
    return v.fillna(False).astype(bool)


def range24_from_bars(high: pd.Series, low: pd.Series,
                      close: pd.Series) -> pd.Series:
    """24h BTC range at bar i from bars i-5..i (all closing <= i)."""
    hh = high.rolling(RANGE_BARS, min_periods=RANGE_BARS).max()
    ll = low.rolling(RANGE_BARS, min_periods=RANGE_BARS).min()
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (hh - ll) / close
    out = out.where(np.isfinite(out), np.nan)
    out = out.where((close > 0) & np.isfinite(close), np.nan)
    return out


def trailing_median(rng: pd.Series) -> pd.Series:
    """Trailing-30d median of the 24h range using bars < i only."""
    return rng.shift(1).rolling(MED_WIN, min_periods=MED_MIN).median()


def veto_expansion_from_range(rng: pd.Series, med: pd.Series) -> pd.Series:
    """Global BTC expansion veto: range > 2x trailing median."""
    v = (rng > RANGE_MULT * med) & np.isfinite(rng) & np.isfinite(med) \
        & (med > 0)
    return v.fillna(False).astype(bool)


def anchor_of(t: pd.Timestamp, shift: int) -> int:
    """Dev/most-recent year index 0..4 of holding-bar open T on phase shift.

    Year y covers [a0, min(a0+365d, live1)) with a0 = ANCH5[y]+sh.
    Bars at/after live1 use the last anchor's stats (beyond scoring).
    """
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


# --------------------------------------------------------------------------
# Veto precomputation (one coin in RAM at a time, float32 1m arrays)
# --------------------------------------------------------------------------
def _files_for(sym: str):
    if sym == "BTCUSDT":
        base = ROOT / "data/raw/btc_intraday_20260924"
        return sorted(base.glob("klines_1m_20*.parquet"))
    base = ROOT / "data/raw/majors_intraday_20260924"
    return sorted(base.glob(f"{sym}_1m_20*.parquet"))


def load_1m(sym: str):
    """1m O/H/L/C as float32, indexed by open_time (one coin at a time)."""
    files = _files_for(sym)
    assert len(files) > 0, f"no 1m files for {sym}"
    parts = [pd.read_parquet(f, columns=["open_time", "open", "high",
                                         "low", "close"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    del parts
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m.set_index("open_time")
    for c in ("open", "high", "low", "close"):
        m[c] = m[c].to_numpy(dtype=np.float32)
    return m


def bars_4h_from_1m(m: pd.DataFrame, shift: int) -> pd.DataFrame:
    """4h bars closing at shifted-grid closes in [HIST_START, Y1+sh+8h].

    Bar i covers minutes [close-4h, close). Causal: bar close == right edge.
    """
    sh = pd.Timedelta(hours=shift)
    lo = HIST_START
    hi = Y1 + sh + pd.Timedelta(hours=8)
    m = m[(m.index >= lo - pd.Timedelta(hours=4)) & (m.index < hi)]
    start = ((m.index - sh).floor("4h") + sh).tz_convert("UTC")
    close = start + pd.Timedelta(hours=4)
    m = m.assign(_close=close)
    g = m.groupby("_close")
    bars = pd.DataFrame({
        "open": g["open"].first(),
        "high": g["high"].max(),
        "low": g["low"].min(),
        "close": g["close"].last(),
        "n": g.size(),
    })
    bars.index = pd.DatetimeIndex(bars.index, tz="UTC")
    bars = bars.sort_index()
    # keep near-full bars only (4h = 240 minutes; allow small gaps)
    bars = bars[bars["n"] >= 200]
    return bars[["open", "high", "low", "close"]]


def veto_series_for_coin(bars: pd.DataFrame):
    """Per-bar sigma veto (+ intermediates) for one coin's 4h bars."""
    o = bars["open"].astype(float)
    sig = sigma360_from_opens(o)
    p80 = trailing_p80(sig)
    v1 = veto_v1_from_sigma(sig, p80)
    return sig, p80, v1


def expansion_series_for_btc(bars: pd.DataFrame):
    """Global BTC expansion veto series (indexed by BTC bar close)."""
    rng = range24_from_bars(bars["high"].astype(float),
                            bars["low"].astype(float),
                            bars["close"].astype(float))
    med = trailing_median(rng)
    vexp = veto_expansion_from_range(rng, med)
    return rng, med, vexp


def build_veto_for_phase(shift: int, idx: pd.DatetimeIndex,
                         cols) -> dict:
    """Veto boolean arrays aligned with engine idx (n x na) for V1/V2.

    Uses merge_asof backward (bars closing <= decision close only).
    Returns dict with veto_v1, veto_v2 (bool ndarrays), veto_rate info,
    and per-coin coverage disclosure.
    """
    n, na = len(idx), len(cols)
    v1 = np.zeros((n, na), dtype=bool)
    vexp_on_idx = np.zeros(n, dtype=bool)
    coverage = {}
    btc_vexp = None
    for j, sym in enumerate(cols):
        m = load_1m(sym)
        files = [f.name for f in _files_for(sym)]
        bars = bars_4h_from_1m(m, shift)
        del m
        gc.collect()
        coverage[sym] = dict(n_bars=int(len(bars)),
                             first=str(bars.index[0]) if len(bars) else None,
                             last=str(bars.index[-1]) if len(bars) else None,
                             files=len(files))
        sig, p80, vv = veto_series_for_coin(bars)
        df = pd.DataFrame({"close_t": bars.index, "v": vv.to_numpy()})
        df = df.sort_values("close_t")
        q = pd.DataFrame({"idx": pd.DatetimeIndex(idx)})
        q = q.sort_values("idx")
        mal = pd.merge_asof(q, df, left_on="idx", right_on="close_t",
                             direction="backward")
        v1[:, j] = mal["v"].fillna(False).to_numpy(dtype=bool)
        del bars, sig, p80, vv, df, q, mal
        gc.collect()
        if sym == "BTCUSDT":
            m2 = load_1m(sym)
            bbars = bars_4h_from_1m(m2, shift)
            del m2
            gc.collect()
            rng, med, vexp = expansion_series_for_btc(bbars)
            df2 = pd.DataFrame({"close_t": bbars.index,
                                "v": vexp.to_numpy()})
            df2 = df2.sort_values("close_t")
            q2 = pd.DataFrame({"idx": pd.DatetimeIndex(idx)})
            q2 = q2.sort_values("idx")
            mal2 = pd.merge_asof(q2, df2, left_on="idx", right_on="close_t",
                                 direction="backward")
            vexp_on_idx = mal2["v"].fillna(False).to_numpy(dtype=bool)
            btc_vexp = dict(
                veto_rate=float(np.mean(vexp_on_idx)),
                n_expansion=int(np.sum(vexp_on_idx)))
            del bbars, rng, med, vexp, df2, q2, mal2
            gc.collect()
    v2 = v1 | vexp_on_idx[:, None]
    info = dict(
        v1_rate=[round(float(v1[:, j].mean()), 6) for j in range(na)],
        v2_rate=[round(float(v2[:, j].mean()), 6) for j in range(na)],
        v1_n=[int(v1[:, j].sum()) for j in range(na)],
        v2_n=[int(v2[:, j].sum()) for j in range(na)],
        btc_expansion=btc_vexp,
        coverage=coverage,
    )
    return {"v1": v1, "v2": v2, "info": info}


def build_veto_filter(hours, night, veto_arr):
    """sleeve_filter: 0 on night bar or veto, else 1 (bar-open only)."""
    def filt(i, a, r):
        if hours[i] == night:
            return 0.0
        if bool(veto_arr[i, a]):
            return 0.0
        return 1.0
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
            print("manualveto: RAM check failed (%s), retry in 300 s" % exc,
                  flush=True)
            time.sleep(300)
            continue
        if free_kb > need_kb:
            return
        print("manualveto: %.2f GB free, waiting for > %.0f GB"
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
    for sym in MAJORS:
        files = _files_for(sym)
        assert len(files) > 0, sym
        print(f"1m coverage {sym}: {len(files)} files "
              f"({files[0].name}..{files[-1].name})", flush=True)
    return {"m5_ref": {"R5": 3.728, "W": 0.847, "maxDD": 17.94,
                       "fullDD": 17.79}}


# --------------------------------------------------------------------------
# Stage 1: 4-phase MANUAL runs (heavy)
# --------------------------------------------------------------------------
def run_phase(shift: int, veto: dict | None):
    wait_for_ram(2.0)
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load("pod_mv_%d" % shift,
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load("hist_mv_%d" % shift, ROOT / "backend/history_tm.py")
    v221 = pof._load("v221_mv_%d" % shift,
                     pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load("fw_mv_%d" % shift, ROOT / "scripts/forward_v205.py")
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
    if veto is None:
        veto = build_veto_for_phase(shift, idx, cols)
    v1arr = veto["v1"]
    v2arr = veto["v2"]
    assert v1arr.shape == (len(idx), len(cols)), v1arr.shape
    assert v2arr.shape == (len(idx), len(cols)), v2arr.shape
    out = {}
    for row in ROWS:
        mode = ENGINE_MODE[row]
        kw, trade = pof.pipe_setup("v367", hist, v221, v216, idx, cols, True)
        pol = trade["policy"]
        if mode == "ref":
            trade["policy"] = lambda i, a, st, pol=pol: (
                ("wait" if st["pos"] == 0 else "hold")
                if hours[i] == night else pol(i, a, st))
            kw["sleeve_filter"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0
        else:
            varr = v1arr if mode == "v1" else v2arr
            trade["policy"] = lambda i, a, st, pol=pol, varr=varr: (
                ("wait" if st["pos"] == 0 else "hold")
                if (hours[i] == night or bool(varr[i, a])) else pol(i, a, st))
            kw["sleeve_filter"] = build_veto_filter(hours, night, varr)
        kw["sleeve_start"] = SLEEVE_START
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
        if mode == "ref":
            vr = [0.0] * 5
        else:
            varr = v1arr if mode == "v1" else v2arr
            vr = []
            for y, a in enumerate(ANCH5):
                a0 = pd.Timestamp(a, tz="UTC") + sh
                a1 = min(a0 + pd.Timedelta(days=365), live1)
                msk = (idx >= a0 - pd.Timedelta(hours=4)) & \
                      (idx < a1 - pd.Timedelta(hours=4))
                msk = np.asarray(msk)
                vr.append(round(float(varr[msk].mean()) if msk.sum() else 0.0, 6))
        out[row] = dict(run=run, wins=years, cross=ch, veto_rate=vr)
        print(shift, row, [round(100 * v["net"], 1) for v in ch],
              [v["dd"] for v in ch], "veto=%s" % (vr,), flush=True)
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


def score_all(allres, veto_info) -> dict:
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    v388 = pof._load("v388_mv_score", RD / "v388/v388_bot_stop_distance.py")
    rm = pof._load("reset_mv_score",
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
        vr_y = []
        for y in range(5):
            vals = [allres[s][row]["veto_rate"][y] for s in range(4)]
            vr_y.append(round(float(np.mean(vals)), 6))
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
            veto_rate=vr_y,
        )
    return table


def robust_pick(table: dict) -> str:
    """AGENTS.md robust criterion on dev4 only: eligible, prefer mean>=5,
    then highest WORST year, ties -> higher mean."""
    cands = [r for r in ("VETO_V1", "VETO_V2")
             if table[r]["DDdev4"] <= 20 and table[r]["losing_dev4"] == 0]
    pool = cands if cands else ["VETO_V1", "VETO_V2"]
    hi = [r for r in pool if table[r]["Rdev4"] >= 5.0]
    pool2 = hi if hi else pool
    pool2 = sorted(pool2, key=lambda r: (table[r]["Wdev4"],
                                         table[r]["Rdev4"]), reverse=True)
    return pool2[0]


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
    hb = threading.Thread(target=heartbeat, args=("oc_manualveto",),
                           daemon=True)
    hb.start()
    TMP.mkdir(parents=True, exist_ok=True)
    if CACHE.exists():
        allres = pickle.loads(CACHE.read_bytes())
        missing = [s for s in range(4) if s not in allres]
        print("loaded cached phase runs (%d/4)" % len(allres), flush=True)
    else:
        allres, missing = {}, list(range(4))
    veto_info = {}
    if VETO_CACHE.exists():
        veto_info = pickle.loads(VETO_CACHE.read_bytes())
        print("loaded cached veto arrays (%d/4)" % len(veto_info), flush=True)
    for shift in missing:
        s, out = run_phase(shift, veto_info.get(shift))
        allres[s] = out
        CACHE.write_bytes(pickle.dumps(allres))
        print("phase %d cached" % s, flush=True)
    _stop_hb.set()
    check_harness_identity(allres)
    table = score_all(allres, veto_info)
    elig = eligibility(table)
    pick = robust_pick(table)
    out = {
        "meta": {
            "idea": "oc_manualveto: MANUAL volatility veto of new bracket "
                    "placement (V1 sigma360>p80-90d; V2 V1 or BTC24h>2xmed30d)",
            "harness": ("MANUAL 4-phase (M5 pipe v367, human schedule "
                        "win_start=15 / sleeve_start=16, night bar skipped, "
                        "agents ON, gate costs maker 0.0002 / taker 0.00055 / "
                        "longs pay 0.0001 per 8h)"),
            "metric": ("reset_metric.year_reset per anchor + v388.mix "
                       "full-path DD (v421/v422 convention); VETO_V1 vs "
                       "VETO_V2 judged on dev years 2021-2024 only; last "
                       "year POST-HOC, scored once for the pick + ref"),
            "rows": {
                "M5_human": "deployed reference (reproduces oc_manualcap)",
                "VETO_V1": "per-coin sigma360 > trailing-90d p80 veto",
                "VETO_V2": "V1 OR BTC 24h range > 2x trailing-30d median",
            },
            "baseline": base,
            "frozen": {
                "sigma": f"pct_change of 4h opens rolling {SIG_WIN} "
                         f"min {SIG_MIN} shift 1",
                "p80": f"q{P80_Q} trailing {P80_WIN}b min {P80_MIN}",
                "range": f"24h ({RANGE_BARS}x4h) range/mult {RANGE_MULT} "
                         f"median trailing {MED_WIN}b min {MED_MIN}",
            },
            "eligibility_dev4": elig,
            "robust_pick_dev4": pick,
            "costs": {"maker": MAKER, "taker": TAKER,
                      "fund_long_8h": FUND_LONG},
            "caveat": ("veto thresholds frozen round numbers, nothing "
                       "fitted; rolling windows use only past bars; most "
                       "recent year POST-HOC, never used to choose"),
        },
        "rows": table,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for row, v in table.items():
        print(row, "R5", v["R5"], "W", v["W"], "maxDD", v["maxDD"],
              "fullDD", v["fullDD"], "Rdev4", v["Rdev4"], "Wdev4", v["Wdev4"],
              "DDdev4", v["DDdev4"], "Rlast", v["Rlast"],
              "book_win", v["book_win"], "rung_win", v["rung_win"],
              "veto", v["veto_rate"], "eligible", elig[row], flush=True)
    print("ROBUST PICK (dev4 only):", pick, flush=True)
    print("ELIGIBILITY (dev4 only):", elig, flush=True)


if __name__ == "__main__":
    main()
