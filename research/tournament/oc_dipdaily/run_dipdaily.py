"""oc_dipdaily run: daily-grid dip sleeve replay + G2 overlay (PLAN.md frozen 2026-10-08).

Usage:
  python research/tournament/oc_dipdaily/run_dipdaily.py --step g2
  python research/tournament/oc_dipdaily/run_dipdaily.py --step pass1 --coin BTCUSDT
  python research/tournament/oc_dipdaily/run_dipdaily.py --step pass1 --coin BTCUSDT --pre
  python research/tournament/oc_dipdaily/run_dipdaily.py --step pass2   # accounting+report
  (full: --step all runs g2 + all coins (+pre) + pass2; heavy 1m work belongs under
   heavy_slot --tag oc_dipdaily --min-free-gb 2.0)

One process, one coin's 1m H/L in RAM at a time (float32). Progress every 10 min.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import dipdaily_core as C

RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"
TMP = HERE / "tmp"
PRE_DIR = ROOT / "data/raw/spot_1m_presample_20261007"

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
PRE_COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]  # SOL absent pre-sample
STRAT = "R2B1D17BFG2"
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
G1 = pd.Timestamp("2026-09-23 12:00", tz="UTC")
TRADE0 = pd.Timestamp("2021-09-24 00:00", tz="UTC")
LAST_OPEN = pd.Timestamp("2026-09-22 00:00", tz="UTC")  # last day with next open in-sample
M1_START = pd.Timestamp("2021-01-01 00:00", tz="UTC")
M1_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
ANCH = [pd.Timestamp(a, tz="UTC") for a in
        ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR = pd.Timedelta(days=365)
DAYNS = 86_400_000_000_000
VARIANTS = ["D05", "D025"]
# pre-sample legs (oc_presample2-exact) + per-coin warm-up (data-start + 60d)
PRE_LEGS = [
    ("Y2017", pd.Timestamp("2017-10-16", tz="UTC"), pd.Timestamp("2018-01-01", tz="UTC"), 77),
    ("Y2018", pd.Timestamp("2018-01-01", tz="UTC"), pd.Timestamp("2019-01-01", tz="UTC"), 365),
    ("Y2019", pd.Timestamp("2019-01-01", tz="UTC"), pd.Timestamp("2020-01-01", tz="UTC"), 365),
    ("Y2020p", pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2020-09-01", tz="UTC"), 244),
]
PRE_WARM = {"BTCUSDT": pd.Timestamp("2017-10-16", tz="UTC"),
            "ETHUSDT": pd.Timestamp("2017-10-16", tz="UTC"),
            "BNBUSDT": pd.Timestamp("2018-01-05", tz="UTC"),
            "XRPUSDT": pd.Timestamp("2018-07-03", tz="UTC")}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def files_1m(sym: str):
    if sym == "BTCUSDT":
        return sorted((ROOT / "data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    return sorted((ROOT / "data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))


# ---------------- step g2: baseline hourly equity + validation ----------------
def step_g2() -> None:
    v388 = _load("v388_for_dipdaily", RD / "v388/v388_bot_stop_distance.py")
    runs = pickle.loads(V421.read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    grid = pd.date_range(GRID0, G1, freq="1h")
    Es, Ms = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s][STRAT], GRID0, G1)
        assert (e1.index == grid).all()
        Es.append(e1.to_numpy(dtype=float))
        Ms.append(m1.to_numpy(dtype=float))
    Es, Ms = np.stack(Es), np.stack(Ms)
    E, M = Es.mean(axis=0), Ms.mean(axis=0)
    exp = json.loads(V421_RES.read_text())["rows"][STRAT]
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    gotR, gotD = [], []
    for y, a0 in enumerate(ANCH):
        a1 = a0 + YEAR
        seg = (grid > a0) & (grid <= a1)
        idx = np.where(np.asarray(seg))[0]
        le = gn <= a0.value
        b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
        es = np.mean([Es[s][idx] / b[s] for s in range(4)], axis=0)
        ms = np.mean([Ms[s][idx] / b[s] for s in range(4)], axis=0)
        pk = np.maximum.accumulate(es)
        gotR.append(round(100 * float(es[-1] ** (1 / 12) - 1), 3))
        gotD.append(round(100 * float(np.max(1 - ms / pk)), 2))
    assert gotR == [r for r, _ in exp["years"]], (gotR, exp["years"])
    assert gotD == [d for _, d in exp["years"]], (gotD, exp["years"])
    segf = np.asarray(grid > pd.Timestamp("2021-09-24", tz="UTC"))
    esf, msf = E[segf], M[segf]
    dd_m = round(100 * float(np.max(1 - msf / np.maximum.accumulate(esf))), 2)
    dd_c = round(100 * float(np.max(1 - esf / np.maximum.accumulate(esf))), 2)
    full = max(dd_m, dd_c)
    assert full == exp["full_path_dd"], (full, exp)
    geo5 = round(float(np.prod([1 + r / 100 for r in gotR]) ** (1 / 5) - 1) * 100, 3)
    assert geo5 == exp["R"] and min(gotR) == exp["W"] and max(gotD) == exp["DD"]
    print(f"g2 validation OK: reproduces v421_result {STRAT} to the digit", flush=True)
    TMP.mkdir(exist_ok=True)
    np.savez_compressed(TMP / "g2_hourly.npz",
                        grid=gn, Es=Es, Ms=Ms, E=E, M=M,
                        anchors=np.array([a.value for a in ANCH]))


def _to_minutes(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise 1m column names (perp open/high/low/close vs spot o/h/l/c)."""
    ren = {"o": "open", "h": "high", "l": "low", "c": "close"}
    return df.rename(columns={k: v for k, v in ren.items() if k in df.columns})


# ---------------- step pass1: per-coin 1m -> daily rung records ----------------
def step_pass1(coin: str, pre: bool = False) -> None:
    t0 = time.time()
    last_print = t0
    if pre:
        assert coin in PRE_COINS, coin
        m = pd.read_parquet(PRE_DIR / f"{coin}.parquet")
        m = _to_minutes(m)
        cols = ["open_time", "open", "high", "low", "close"]
        m = m[cols]
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        lo, hi = PRE_LEGS[0][1] - pd.Timedelta(days=130), PRE_LEGS[-1][2] + pd.Timedelta(days=2)
        m = m.drop_duplicates("open_time").sort_values("open_time")
        m = m[(m["open_time"] >= lo) & (m["open_time"] < hi)]
        full_idx = pd.date_range(lo.floor("D"), hi.ceil("D"), freq="1min")[:-1]
        warm = PRE_WARM[coin]
        tag = f"pre_{coin}"
        leg_lo, leg_hi = PRE_LEGS[0][1], PRE_LEGS[-1][2]
    else:
        parts = [pd.read_parquet(f) for f in files_1m(coin)]
        m = pd.concat(parts, ignore_index=True)
        del parts
        m = _to_minutes(m)
        cols = ["open_time", "open", "high", "low", "close"]
        m = m[cols]
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        m = m.drop_duplicates("open_time").sort_values("open_time")
        m = m[(m["open_time"] >= M1_START) & (m["open_time"] < M1_END)]
        full_idx = pd.date_range(M1_START, M1_END - pd.Timedelta(minutes=1), freq="1min")
        warm, tag = None, coin
        leg_lo, leg_hi = TRADE0, LAST_OPEN + pd.Timedelta(days=1)
    m = m.set_index("open_time").reindex(full_idx)
    O = m["open"].to_numpy(dtype=np.float32)
    H = m["high"].to_numpy(dtype=np.float32)
    Lw = m["low"].to_numpy(dtype=np.float32)
    del m
    n_min = len(full_idx)
    assert n_min % 1440 == 0, n_min
    nb = n_min // 1440
    T = full_idx[:n_min:1440]  # daily opens
    O1 = O[::1440].astype(float)
    sg = C.sigma1d_causal(O1)
    Ob = O.reshape(nb, 1440)
    Hb = H.reshape(nb, 1440)
    Lb = Lw.reshape(nb, 1440)
    del O, H, Lw
    recs, n_traded, n_skip = [], 0, 0
    for j in range(nb):
        tj = T[j]
        if not (leg_lo <= tj < leg_hi):
            continue
        if pre and tj < warm:
            continue
        if not pre and not (TRADE0 <= tj <= LAST_OPEN):
            continue
        s = float(sg[j])
        if not (np.isfinite(s) and s > 0):
            n_skip += 1
            continue
        o0 = float(O1[j])
        o_next = float(O1[j + 1]) if j + 1 < nb else np.nan
        blk = (Ob[j], Hb[j], Lb[j])
        if not (np.isfinite(o0) and o0 > 0 and np.isfinite(o_next) and o_next > 0
                and np.isfinite(np.asarray(blk[0])).all()
                and np.isfinite(np.asarray(blk[1])).all()
                and np.isfinite(np.asarray(blk[2])).all()):
            n_skip += 1
            continue
        n_traded += 1
        for r in C.day_outcomes(o0, Ob[j], Hb[j], Lb[j], s, o_next):
            exit_day = tj if r["x"] < 1440 else tj + pd.Timedelta(days=1)
            recs.append((int(tj.value), int(exit_day.value), r["k"], r["f"],
                         r["x"], r["fill"], r["exit"], r["ret"], r["how"], r["nst"]))
        now = time.time()
        if now - last_print >= 600:
            print(f"pass1 {tag}: day {tj.date()} ({n_traded} traded) "
                  f"{now - t0:.0f}s", flush=True)
            last_print = now
    df = pd.DataFrame(recs, columns=["day_ns", "exit_ns", "k", "f", "x",
                                     "fill", "exit", "ret", "how", "nst"])
    df["coin"] = coin
    TMP.mkdir(exist_ok=True)
    df.to_parquet(TMP / f"rec_{tag}.parquet", index=False)
    print(f"pass1 {tag}: DONE {n_traded} days, {n_skip} skipped, {len(df)} rungs, "
          f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=["g2", "pass1", "pass2", "all"], required=True)
    ap.add_argument("--coin", default=None)
    ap.add_argument("--pre", action="store_true")
    a = ap.parse_args()
    if a.step in ("g2", "all"):
        step_g2()
    if a.step == "pass1":
        assert a.coin in (PRE_COINS if a.pre else MAJORS), a.coin
        step_pass1(a.coin, pre=a.pre)
    if a.step == "all":
        for c in MAJORS:
            step_pass1(c)
        for c in PRE_COINS:
            step_pass1(c, pre=True)
    if a.step in ("pass2", "all"):
        from run_dipdaily_pass2 import step_pass2
        step_pass2()
