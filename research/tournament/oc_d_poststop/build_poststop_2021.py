"""oc_d_poststop: build per-(coin, shift) post-stop mult panel on 2021-2026 perp.

Frozen (see PLAN.md): same VERBATIM kind/x recompute at mu=1.0 on the 2021-2026 perp
1m store (data/raw/btc_intraday_20260924 + data/raw/majors_intraday_20260924), O/sg from
oc_kronoshidden/bars_4h_4shift.parquet opens + verbatim compute_sigma; same (c, s) scope,
same N = 7/3, same mult 1.25.

Steps: (1) reproduction gate on the reused k2placebo ledger (n == 22312, base sums ==
(0.911273, 0.832599, 2.099814, 3.197390, 0.677229), sum5y == 7.718304 +- 0.002); STOP
unless exact. (2) perp-1m kind/x recompute, one coin at a time. (3) write
poststop_mult_2021.parquet + tmp/poststop_triggers_2021.json.

Run via heavy_slot (1m work). Heartbeat every 600 s.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
K2 = ROOT / "research/tournament/oc_k2placebo"
KH = ROOT / "research/tournament/oc_kronoshidden"
BTCD = ROOT / "data/raw/btc_intraday_20260924"
MAJD = ROOT / "data/raw/majors_intraday_20260924"
BARS = KH / "bars_4h_4shift.parquet"

sys.path.insert(0, str(HERE))
from poststop_rule import (V1_DAYS, V2_DAYS, boosted_mult, compute_sigma,
                           find_fill, outcome_kind_x, phase_mean_sums)

MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
GATE_N = 22312
GATE_BASE = (0.911273, 0.832599, 2.099814, 3.197390, 0.677229)
GATE_SUM = 7.718304
HB_S = 600


def load_ohlc(sym: str):
    if sym == "BTCUSDT":
        files = sorted(BTCD.glob("klines_1m_20*.parquet"))
    else:
        files = sorted(MAJD.glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"])
             for f in files]
    m = pd.concat(parts, ignore_index=True)
    del parts
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    idx = pd.date_range(START, END, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    out = {k: m[k].to_numpy(dtype=np.float32) for k in ("open", "high", "low", "close")}
    del m
    return idx, out


def main() -> None:
    t0 = time.time()
    last_hb = t0
    print("[oc_d_poststop] build_poststop_2021 start", flush=True)

    led = dict(np.load(K2 / "tmp/ledger.npz"))
    for k in ("phase", "coin", "year", "bar_time", "rung"):
        led[k] = led[k].astype(np.int64)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    bt_all = np.load(K2 / "tmp/bt_all.npy", allow_pickle=True)
    n = len(w)
    print(f"ledger n={n}", flush=True)

    base = phase_mean_sums(led["phase"], led["year"], w, yv, 5)
    got5 = float(sum(base))
    print(f"base={base} sum5y={got5:.6f}", flush=True)
    assert n == GATE_N, f"ledger size {n} != {GATE_N}"
    for g, b in zip(GATE_BASE, base):
        assert abs(g - b) <= 0.002, f"base {b} != {g}"
    assert abs(got5 - GATE_SUM) <= 0.002, f"sum5y {got5} != {GATE_SUM}"
    print("[oc_d_poststop] reproduction gate PASS", flush=True)

    bars = pd.read_parquet(BARS)
    bars["T"] = pd.to_datetime(bars["T"], utc=True)
    os_lut = {}
    grids = {}
    for sym in MAJORS:
        for s in (0, 1, 2, 3):
            sub = bars[(bars["sym"] == sym) & (bars["shift"] == s)].sort_values("T")
            oo = sub["open"].to_numpy(dtype=float)
            sg = compute_sigma(oo)
            tt = pd.to_datetime(sub["T"], utc=True)
            for t, o, g in zip(tt, oo, sg):
                os_lut[(sym, s, pd.Timestamp(t))] = (float(o), float(g))
            grids[(sym, s)] = (tt.reset_index(drop=True), oo, sg)
    del bars
    print("built O/sg lookup", flush=True)

    from poststop_rule import RUNGS

    kinds = np.full(n, -1, dtype=np.int64)
    KIND = {"backstop": 0, "tp": 1, "stop": 2, "time": 3}
    exit_min = np.full(n, -1, dtype=np.int64)
    n_unknown_level = 0
    n_unknown_window = 0
    for ci, sym in enumerate(MAJORS):
        idx_fill = np.where(led["coin"] == ci)[0]
        if len(idx_fill) == 0:
            continue
        print(f"loading 1m {sym} fills={len(idx_fill)}", flush=True)
        idx, d = load_ohlc(sym)
        base_t = idx[0]
        o, h, lo, c = d["open"], d["high"], d["low"], d["close"]
        del d
        for i in idx_fill:
            T = pd.Timestamp(bt_all[i])
            if T.tzinfo is None:
                T = T.tz_localize("UTC")
            s = int(led["phase"][i])
            o1, sg = os_lut.get((sym, s, T), (np.nan, np.nan))
            k = RUNGS[int(led["rung"][i])]
            if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                n_unknown_level += 1
                continue
            lv = o1 * (1 - k * sg)
            if not np.isfinite(lv) or lv <= 0:
                n_unknown_level += 1
                continue
            off = int((T - base_t).total_seconds() // 60)
            if off < 0 or off + 240 > len(idx):
                n_unknown_window += 1
                continue
            low_win = lo[off + 16:off + 238 + 1].astype(float)
            if not np.isfinite(low_win).any():
                n_unknown_window += 1
                continue
            ib = find_fill(low_win, lv)
            if ib is None:
                n_unknown_window += 1
                continue
            f = 16 + ib
            Ha = h[off:off + 240].astype(float)
            La = lo[off:off + 240].astype(float)
            Ca = c[off:off + 240].astype(float)
            Oa = o[off:off + 240].astype(float)
            kind, x = outcome_kind_x(Ha, La, Ca, Oa, f, lv, sg)
            kinds[i] = KIND[kind]
            exit_min[i] = int(x)
        del idx, o, h, lo, c
        print(f"{sym}: done elapsed {(time.time() - t0) / 60:.1f}min", flush=True)
        if time.time() - last_hb >= HB_S:
            last_hb = time.time()
            print(f"[hb] build_poststop_2021 alive elapsed {last_hb - t0:.0f}s",
                  flush=True)

    n_unknown = int((kinds == -1).sum())
    print(f"kinds unknown={n_unknown} (level={n_unknown_level} window={n_unknown_window})",
          flush=True)
    (HERE / "tmp").mkdir(exist_ok=True)
    np.savez_compressed(HERE / "tmp/stop_kinds_x_2021.npz", kind=kinds, exit_min=exit_min)

    trig = {}
    for ci, sym in enumerate(MAJORS):
        for s in (0, 1, 2, 3):
            m = (led["coin"] == ci) & (led["phase"] == s) & (kinds >= 0) & (exit_min >= 0)
            idx_m = np.where(m)[0]
            stop_m = (kinds[idx_m] == KIND["stop"]) | (kinds[idx_m] == KIND["backstop"])
            tcs = []
            for i in idx_m[stop_m]:
                T = pd.Timestamp(bt_all[i])
                if T.tzinfo is None:
                    T = T.tz_localize("UTC")
                tcs.append(int((T + pd.Timedelta(minutes=int(exit_min[i]))).value))
            tcs = np.array(sorted(set(tcs)), dtype=np.int64)
            trig[(sym, s)] = tcs
    for key, tcs in trig.items():
        print(f"triggers {key}: {len(tcs)}", flush=True)

    rows = []
    for sym in MAJORS:
        for s in (0, 1, 2, 3):
            tt, _, _ = grids[(sym, s)]
            t_ns = tt.values.astype("datetime64[ns]").astype(np.int64)
            m1 = boosted_mult(t_ns, trig[(sym, s)], V1_DAYS)
            m2 = boosted_mult(t_ns, trig[(sym, s)], V2_DAYS)
            for t, a, b in zip(tt, m1, m2):
                rows.append((s, pd.Timestamp(t), sym, float(a), float(b)))
    panel = pd.DataFrame(rows, columns=["shift", "T", "sym", "mult_V1", "mult_V2"])
    panel.to_parquet(HERE / "poststop_mult_2021.parquet", index=False)
    print(f"wrote poststop_mult_2021.parquet rows={len(panel)}", flush=True)

    trig_info = {
        "config": {"rule": "stop/backstop tc=T+xmin verbatim mu=1.0; V1 N=7 x1.25; V2 N=3 x1.25",
                   "unknown": int(n_unknown)},
        "n_triggers": {f"{sym}/s{s}": int(len(trig[(sym, s)]))
                       for sym in MAJORS for s in (0, 1, 2, 3)},
    }
    (HERE / "tmp/poststop_triggers_2021.json").write_text(json.dumps(trig_info, indent=1))
    print(f"done elapsed {(time.time() - t0) / 60:.1f}min", flush=True)


if __name__ == "__main__":
    main()
