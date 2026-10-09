"""oc_tiltgate ledger extension: replay the SAME D0+B1 replica core for bars
open in [2020-09-17, 2021-09-24) so gate windows [A-372d, A-7d) are exact.

Same code: imports compute_placebo_dip read-only and calls its replica
primitives (n_vector, size_mult, find_fill, outcome_mu,
exit_day_ordinal) with identical constants (RUNGS, LIVE_A/B, M_SL,
BACKSTOP, DETECT_K, MAKER/TAKER/FUND, SETTLE_HOURS) and the identical
4h grid anchored at START=2020-08-01 00:00 UTC + 0/1/2/3h. Only the
traded-bar selection differs (pre-sample window instead of
[2021-09-24, 2026-09-24)); year is stored as -1 and the gate filters by
bar-open time directly. Kept-fill rule identical (fill on lv AND all
three TP legs finite).

Outputs: tmp/ledger_ext.npz (phase/coin/bar_time/rung/w/y10) +
tmp/bt_ext.npy (bar-open datetimes). bar_time ordinals use the same
START epoch, directly comparable with oc_k2placebo/tmp/ledger.npz.

Usage (via heavy_slot):
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_tiltgate_ext
    --min-free-gb 2.0 -- .venv/Scripts/python.exe
    research/tournament/oc_tiltgate/extend_ledger.py
"""
from __future__ import annotations

import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TMP = HERE / "tmp"
PDIP = ROOT / "research/tournament/oc_placebo_dip"

sys.path.insert(0, str(PDIP))
import compute_placebo_dip as cpd  # noqa: E402  (read-only import)

EXT_START = pd.Timestamp("2020-09-17 00:00", tz="UTC")
EXT_END = pd.Timestamp("2021-09-24 00:00", tz="UTC")
DATA_END = pd.Timestamp("2021-09-25 00:00", tz="UTC")  # +1d tail for exits
HEARTBEAT_S = 600

_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print(f"[hb {datetime.now(timezone.utc):%H:%M:%S}Z] {tag} alive",
              flush=True)


def load_oc_range(sym: str, start, end):
    """Identical logic to cpd.load_oc but with an explicit date range."""
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "close"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= start) & (m["open_time"] <= end)]
    idx = pd.date_range(start, end, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    O = m["open"].to_numpy(dtype=np.float32)
    C = m["close"].to_numpy(dtype=np.float32)
    del m, parts
    return idx, O, C


def load_hl_range(sym: str, idx):
    """Identical logic to cpd.load_hl but on an already-built index."""
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "high", "low"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= idx[0]) & (m["open_time"] <= idx[-1])]
    m = m.set_index("open_time").reindex(idx)
    H = m["high"].to_numpy(dtype=np.float32)
    L = m["low"].to_numpy(dtype=np.float32)
    del m, parts
    return H, L


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    out_npz, out_bt = TMP / "ledger_ext.npz", TMP / "bt_ext.npy"
    if out_npz.exists() and out_bt.exists():
        print("extension cached, skip", flush=True)
        return
    hb = threading.Thread(target=heartbeat, args=("extend_ledger",), daemon=True)
    hb.start()
    t0 = time.time()

    assert cpd.START == pd.Timestamp("2020-08-01", tz="UTC"), cpd.START
    coins = cpd.MAJORS
    phases = cpd.PHASES
    O, C, base_idx = {}, {}, None
    for sym in coins:
        ii, o, c = load_oc_range(sym, cpd.START, DATA_END)
        base_idx = ii if base_idx is None else base_idx
        O[sym], C[sym] = o, c
        print(f"loaded OC {sym} n={len(ii)}", flush=True)
    n_all = len(base_idx)

    grids = {}
    for p in phases:
        off = p * 60
        nb = (n_all - off) // 240
        t0a = base_idx[off:off + nb * 240:240]
        opens_bar, sig_bar = {}, {}
        for sym in coins:
            ob = O[sym][off:off + nb * 240:240].astype(float)
            sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            opens_bar[sym], sig_bar[sym] = ob, sg
        js = [j for j in range(nb)
              if EXT_START <= t0a[j] < EXT_END and (off + j * 240 + 240) < n_all]
        grids[p] = dict(off=off, nb=nb, t0=t0a, opens=opens_bar, sig=sig_bar, js=js)
        print(f"shift {p}: nb={nb} traded={len(js)}", flush=True)
    del opens_bar, sig_bar

    F = {k: [] for k in ("phase", "coin", "bar_time", "rung", "w", "y10")}
    bt_list = []
    coin_ix = {s: i for i, s in enumerate(coins)}
    for sym in coins:
        H, L = load_hl_range(sym, base_idx)
        La, Ha = L, H
        others = [b for b in coins if b != sym]
        Oa, Ca = O[sym], C[sym]
        for p in phases:
            g = grids[p]
            off, t0a = g["off"], g["t0"]
            opens_bar, sig_bar = g["opens"], g["sig"]
            n_fill = 0
            for j in g["js"]:
                bt = t0a[j]
                o1, sg = float(opens_bar[sym][j]), float(sig_bar[sym][j])
                if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                    continue
                base = off + j * 240
                o2m = Oa[base + 240]
                o2 = float(o2m) if np.isfinite(o2m) else np.nan
                settle = (bt + pd.Timedelta(hours=4)).hour in cpd.SETTLE_HOURS
                low_win = La[base + cpd.LIVE_A:base + cpd.LIVE_B + 1].astype(float)
                cmat = np.stack([C[b][base + cpd.LIVE_A - 1:base + cpd.LIVE_B].astype(float)
                                 for b in others])
                oo = np.array([opens_bar[b][j] for b in others], dtype=float)
                ss = np.array([sig_bar[b][j] for b in others], dtype=float)
                nvec = cpd.n_vector(cmat, oo, ss)
                Ha_b = Ha[base:base + 240].astype(float)
                La_b = La[base:base + 240].astype(float)
                Ca_b = Ca[base:base + 240].astype(float)
                Oa_b = Oa[base:base + 240].astype(float)
                for ri, k in enumerate(cpd.RUNGS):
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = cpd.find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = cpd.LIVE_A + ib
                    nf = int(nvec[ib])
                    r09, _, _ = cpd.outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 0.9, o2, settle)
                    r10, _, _ = cpd.outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 1.0, o2, settle)
                    r11, _, _ = cpd.outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 1.1, o2, settle)
                    if not (np.isfinite(r09) and np.isfinite(r10) and np.isfinite(r11)):
                        continue
                    n_fill += 1
                    F["phase"].append(p)
                    F["coin"].append(coin_ix[sym])
                    F["bar_time"].append(off + j * 240)
                    F["rung"].append(ri)
                    F["w"].append(cpd.size_mult(nf))
                    F["y10"].append(r10)
                    bt_list.append(bt)
            print(f"{sym} p{p}: fills={n_fill}", flush=True)
        del H, L, La, Ha
    led = {k: np.array(v) for k, v in F.items()}
    for k in ("phase", "coin", "bar_time", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.array(bt_list, dtype=object)
    np.savez_compressed(out_npz, **led)
    np.save(out_bt, bt_all)
    _stop_hb.set()
    print(f"extension fills={len(led['w'])} range={bt_all.min()}..{bt_all.max()} "
          f"elapsed={(time.time() - t0) / 60:.1f}min", flush=True)


if __name__ == "__main__":
    main()
