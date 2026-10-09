"""oc_d_poststop: build per-(coin, shift) post-stop mult panel on pre-sample spot.

Frozen (see PLAN.md): VERBATIM ledger exit branch at mu=1.0 -> per-fill kind + exit
minute x -> stop tc = T + x min (kinds {stop, backstop} only) -> per (coin, shift)
boosted iff exists tc with 0 < T' - tc <= N days (V1 N=7, V2 N=3, mult 1.25 else 1.0).

Steps: (1) reproduction gate on the reused presample ledger (n==9731, per-leg
909/2986/3115/2721, base 4-phase-mean sums == (2.313362, 2.678870, 0.577643, 0.297538)
+- 1e-6); STOP unless exact. (2) spot-1m kind/x recompute, one coin at a time.
(3) write poststop_mult_presample.parquet + tmp/poststop_triggers.json.

Run via heavy_slot (1m work). Heartbeat every 600 s. Progress prints throughout.
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
PST = ROOT / "research/tournament/oc_presampletilt"
SPOT = ROOT / "data/raw/spot_1m_presample_20261007"
BARS = PST / "bars_4h_presample.parquet"

sys.path.insert(0, str(HERE))
from poststop_rule import (V1_DAYS, V2_DAYS, boosted_mult, compute_sigma,
                           find_fill, outcome_kind_x, phase_mean_sums)

MAJORS4 = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
LEG_ORDER = ("Y2017", "Y2018", "Y2019", "Y2020p")
GATE_N = 9731
GATE_LEG = (909, 2986, 3115, 2721)
GATE_BASE = (2.313362, 2.678870, 0.577643, 0.297538)
HB_S = 600
STOP_KINDS = {"stop", "backstop"}


def main() -> None:
    t0 = time.time()
    last_hb = t0
    print("[oc_d_poststop] build_poststop_presample start", flush=True)

    led = dict(np.load(PST / "tmp/ledger_presample.npz"))
    for k in ("phase", "coin", "year", "t_ord", "rung"):
        led[k] = led[k].astype(np.int64)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    bt_all = np.load(PST / "tmp/bt_presample.npy", allow_pickle=True)
    n = len(w)
    print(f"ledger n={n}", flush=True)

    # ---- reproduction gate (base 4-phase-mean sums, n_years=4) ----
    base = phase_mean_sums(led["phase"], led["year"], w, yv, 4)
    per_leg = [int((led["year"] == i).sum()) for i in range(4)]
    print(f"base={base} per_leg={per_leg}", flush=True)
    assert n == GATE_N, f"ledger size {n} != {GATE_N}"
    assert tuple(per_leg) == GATE_LEG, f"per_leg {per_leg} != {GATE_LEG}"
    for g, b in zip(GATE_BASE, base):
        assert abs(g - b) <= 1e-6, f"base {b} != {g}"
    print("[oc_d_poststop] reproduction gate PASS", flush=True)

    # ---- O/sg lookup from frozen bars opens (verbatim compute_sigma) ----
    bars = pd.read_parquet(BARS)
    bars["T"] = pd.to_datetime(bars["T"], utc=True)
    os_lut = {}
    grids = {}
    for sym in MAJORS4:
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

    # ---- per-fill kind + exit time (one coin's 1m in RAM at a time) ----
    from poststop_rule import RUNGS

    kinds = np.full(n, -1, dtype=np.int64)  # 0 backstop 1 tp 2 stop 3 time -1 unknown
    KIND = {"backstop": 0, "tp": 1, "stop": 2, "time": 3}
    exit_min = np.full(n, -1, dtype=np.int64)
    n_unknown_level = 0
    n_unknown_window = 0
    for ci, sym in enumerate(MAJORS4):
        idx_fill = np.where(led["coin"] == ci)[0]
        if len(idx_fill) == 0:
            continue
        print(f"loading 1m {sym} fills={len(idx_fill)}", flush=True)
        m = pd.read_parquet(SPOT / f"{sym}.parquet")
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        m = m.sort_values("open_time")
        t_min = pd.to_datetime([bt_all[i] for i in idx_fill], utc=True).min() - pd.Timedelta(days=2)
        t_max = pd.to_datetime([bt_all[i] for i in idx_fill], utc=True).max() + pd.Timedelta(days=2)
        m = m[(m["open_time"] >= t_min) & (m["open_time"] <= t_max)]
        full_idx = pd.date_range(m["open_time"].min().floor("min"),
                                 m["open_time"].max().ceil("min"), freq="1min")
        m = m.set_index("open_time").reindex(full_idx)
        o = m["o"].to_numpy(dtype=np.float32)
        h = m["h"].to_numpy(dtype=np.float32)
        lo = m["l"].to_numpy(dtype=np.float32)
        c = m["c"].to_numpy(dtype=np.float32)
        base_t = full_idx[0]
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
            if off < 0 or off + 240 > len(full_idx):
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
        del m, o, h, lo, c
        print(f"{sym}: done elapsed {(time.time() - t0) / 60:.1f}min", flush=True)
        if time.time() - last_hb >= HB_S:
            last_hb = time.time()
            print(f"[hb] build_poststop_presample alive elapsed {last_hb - t0:.0f}s",
                  flush=True)

    n_unknown = int((kinds == -1).sum())
    print(f"kinds unknown={n_unknown} (level={n_unknown_level} window={n_unknown_window})",
          flush=True)
    (HERE / "tmp").mkdir(exist_ok=True)
    np.savez_compressed(HERE / "tmp/stop_kinds_x.npz", kind=kinds, exit_min=exit_min,
                        t_ord=led["t_ord"])

    # ---- stop trigger tables per (coin, shift): tc = T + x min ----
    trig = {}
    for ci, sym in enumerate(MAJORS4):
        for s in (0, 1, 2, 3):
            m = (led["coin"] == ci) & (led["phase"] == s) & (kinds >= 0) & (exit_min >= 0)
            kk = kinds[m]
            is_stop = (kk == KIND["stop"]) | (kk == KIND["backstop"])
            tcs = []
            # vectorised over the masked fills:
            idx_m = np.where(m)[0]
            stop_m = (kinds[idx_m] == KIND["stop"]) | (kinds[idx_m] == KIND["backstop"])
            for i in idx_m[stop_m]:
                T = pd.Timestamp(bt_all[i])
                if T.tzinfo is None:
                    T = T.tz_localize("UTC")
                tcs.append(int((T + pd.Timedelta(minutes=int(exit_min[i]))).value))
            tcs = np.array(sorted(set(tcs)), dtype=np.int64)
            trig[(sym, s)] = tcs
    for key, tcs in trig.items():
        print(f"triggers {key}: {len(tcs)}", flush=True)

    # ---- mult panel per (sym, shift) grid ----
    rows = []
    for sym in MAJORS4:
        for s in (0, 1, 2, 3):
            tt, _, _ = grids[(sym, s)]
            t_ns = tt.values.astype("datetime64[ns]").astype(np.int64)
            m1 = boosted_mult(t_ns, trig[(sym, s)], V1_DAYS)
            m2 = boosted_mult(t_ns, trig[(sym, s)], V2_DAYS)
            for t, a, b in zip(tt, m1, m2):
                rows.append((s, pd.Timestamp(t), sym, float(a), float(b)))
    panel = pd.DataFrame(rows, columns=["shift", "T", "sym", "mult_V1", "mult_V2"])
    panel.to_parquet(HERE / "poststop_mult_presample.parquet", index=False)
    print(f"wrote poststop_mult_presample.parquet rows={len(panel)}", flush=True)

    trig_info = {
        "config": {"rule": "stop/backstop tc=T+xmin verbatim mu=1.0; V1 N=7 x1.25; V2 N=3 x1.25",
                   "unknown": int(n_unknown),
                   "unknown_level": int(n_unknown_level),
                   "unknown_window": int(n_unknown_window)},
        "n_triggers": {f"{sym}/s{s}": int(len(trig[(sym, s)]))
                       for sym in MAJORS4 for s in (0, 1, 2, 3)},
        "boosted_timebar_share": {},
    }
    for sym in MAJORS4:
        for s in (0, 1, 2, 3):
            sub = panel[(panel["sym"] == sym) & (panel["shift"] == s)]
            trig_info["boosted_timebar_share"][f"{sym}/s{s}"] = {
                "V1": round(float((sub["mult_V1"] == 1.25).mean()), 4),
                "V2": round(float((sub["mult_V2"] == 1.25).mean()), 4),
                "n_bars": int(len(sub))}
    (HERE / "tmp/poststop_triggers.json").write_text(json.dumps(trig_info, indent=1))
    print(f"done elapsed {(time.time() - t0) / 60:.1f}min", flush=True)


if __name__ == "__main__":
    main()
