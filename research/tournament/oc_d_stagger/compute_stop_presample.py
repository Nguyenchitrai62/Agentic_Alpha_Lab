"""oc_d_stagger: heavy base-kind recompute (pre-sample REF fills).

VERBATIM build_ledger_presample outcome branch at mu=1.0 (sl/bl/tp, close5+backstop,
stop-first). Levels lv = O(T)*(1-k*sg(T)) with O/sg from bars_4h_presample
(open + compute_sigma pct_change rolling-360/min_periods-120/shift-1).
Fill f re-found via VERBATIM find_fill on live 16..238 (should match the ledger fill;
mismatches counted, kind=unknown). NaN windows -> unknown.

Output: tmp/basekind_presample.npz (kind per REF fill order) + summary json.
Via heavy_slot, one coin in RAM at a time, float32. Heartbeat 600 s.
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
TMP = HERE / "tmp"
PRE = HERE.parent / "oc_presampletilt"
SPOT = ROOT / "data" / "raw" / "spot_1m_presample_20261007"
sys.path.insert(0, str(HERE))
import stagger_rule as sr  # noqa: E402

MAJORS4 = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
EPOCH = pd.Timestamp("2017-08-01", tz="UTC")
SETTLE = (0, 8, 16)
HB_S = 600
KIND = {"tp": 0, "time": 1, "stop": 2, "backstop": 3}


def main() -> None:
    t0 = time.time()
    last_hb = t0
    TMP.mkdir(parents=True, exist_ok=True)
    led = dict(np.load(PRE / "tmp" / "ledger_presample.npz"))
    for k in ("phase", "coin", "year", "t_ord", "rung"):
        led[k] = led[k].astype(np.int64)
    bt = np.load(PRE / "tmp" / "bt_presample.npy", allow_pickle=True)
    n = len(led["w"])
    bars = pd.read_parquet(PRE / "bars_4h_presample.parquet")
    # per (sym, shift) open/sigma series indexed by T
    grids = {}
    for (sym, sh), g in bars.groupby(["sym", "shift"]):
        g = g.sort_values("T")
        Ts = pd.to_datetime(g["T"], utc=True).to_numpy()
        oo = g["open"].to_numpy(dtype=float)
        sg = sr.compute_sigma(oo)
        grids[(str(sym), int(sh))] = (Ts, oo, sg)
    del bars
    # 1m per coin cached one at a time
    man = json.loads((SPOT / "manifest.json").read_text())
    tmin = min(pd.Timestamp(t) for t in bt) - pd.Timedelta(hours=5)
    tmax = max(pd.Timestamp(t) for t in bt) + pd.Timedelta(hours=5)
    kinds = np.full(n, -2, dtype=np.int64)
    nmismatch = 0
    order = np.argsort(led["coin"], kind="stable")
    for sym_i, sym in enumerate(MAJORS4):
        sel = order[led["coin"][order] == sym_i]
        if len(sel) == 0:
            continue
        m = pd.read_parquet(SPOT / f"{sym}.parquet")
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        m = m[(m["open_time"] >= tmin) & (m["open_time"] <= tmax)]
        idx = pd.date_range(tmin, tmax, freq="1min")
        m = m.set_index("open_time").reindex(idx)
        m1 = {k: m[k].to_numpy(dtype=np.float32) for k in ("o", "h", "l", "c")}
        del m
        print(f"basekind: loaded {sym} fills={len(sel)}", flush=True)
        for ii, i in enumerate(sel):
            T = pd.Timestamp(bt[i])
            s = int(led["phase"][i])
            Ts, oo, sg = grids[(sym, s)]
            pos = int(np.searchsorted(Ts.astype("datetime64[ns]").astype("int64"), T.value))
            if pos >= len(Ts) or pd.Timestamp(Ts[pos]) != T:
                kinds[i] = -2
                continue
            o1, sgv = float(oo[pos]), float(sg[pos])
            k = RUNGS[int(led["rung"][i])]
            lv = o1 * (1 - k * sgv)
            off = int((T - tmin).total_seconds() // 60)
            if off + 240 >= len(idx):
                kinds[i] = -2
                continue
            La = np.asarray(m1["l"][off:off + 240], dtype=float)
            Ha = np.asarray(m1["h"][off:off + 240], dtype=float)
            Ca = np.asarray(m1["c"][off:off + 240], dtype=float)
            Oa = np.asarray(m1["o"][off:off + 240], dtype=float)
            o2m = m1["o"][off + 240]
            o2 = float(o2m) if np.isfinite(o2m) else np.nan
            f = sr.find_fill_in(La, lv, 16, 238)
            if f is None:
                nmismatch += 1
                kinds[i] = -2
                continue
            settle = (T + pd.Timedelta(hours=4)).hour in SETTLE
            _, _, how = sr.outcome_mu(Ha, La, Ca, Oa, f, lv, sgv, 1.0, o2, settle)
            kinds[i] = KIND[how]
            if (ii + 1) % 2000 == 0:
                print(f"basekind: {sym} {ii+1}/{len(sel)}", flush=True)
            if time.time() - last_hb >= HB_S:
                last_hb = time.time()
                print(f"[hb] basekind alive elapsed {last_hb-t0:.0f}s", flush=True)
        del m1
    np.savez_compressed(TMP / "basekind_presample.npz", kind=kinds)
    out = {"n": n, "unknown_or_mismatch": int((kinds < 0).sum()),
           "mismatch_note": "find_fill miss or grid miss -> -2 (excluded from rates)"}
    (TMP / "basekind_presample.json").write_text(json.dumps(out, indent=1))
    print(f"basekind done unknown={out['unknown_or_mismatch']} mism={nmismatch}", flush=True)


if __name__ == "__main__":
    main()
