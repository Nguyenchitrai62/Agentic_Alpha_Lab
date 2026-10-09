"""oc_d_poststop: 2021-2026 replica join + gains + placebos (CPU-only).

Frozen (see PLAN.md): join k2placebo fills to poststop_mult_2021.parquet (exact +
causal ffill, missing -> 1.0); per-year base/boosted/realised/norm/gain (4-phase means,
y = 0..4); dSum5y + sum-half; timing + block-42 placebos per (year, shift, coin), 1000
perms (seeds 20261007+y / 20261008+y). SECONDARY pass: dSum5y >= +0.273 AND >= 4/5 years
with gain > 0. Output: tmp/poststop_2021.json. Heartbeat every 600 s.
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

sys.path.insert(0, str(HERE))
from poststop_rule import phase_mean_sums

MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
SEED_TIMING = 20261007
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
HB_S = 600


def main() -> None:
    t0 = time.time()
    last_hb = t0
    print("[oc_d_poststop] compute_poststop_2021 start", flush=True)

    led = dict(np.load(K2 / "tmp/ledger.npz"))
    for k in ("phase", "coin", "year", "bar_time", "rung"):
        led[k] = led[k].astype(np.int64)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    bt_all = np.load(K2 / "tmp/bt_all.npy", allow_pickle=True)
    n = len(w)
    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)

    panel = pd.read_parquet(HERE / "poststop_mult_2021.parquet")
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    lut = {}
    grid = {}
    for sym in MAJORS:
        for s in (0, 1, 2, 3):
            sub = panel[(panel["sym"] == sym) & (panel["shift"] == s)].sort_values("T")
            t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
            grid[(s, sym)] = (t_ns, sub["mult_V1"].to_numpy(dtype=float),
                              sub["mult_V2"].to_numpy(dtype=float))
            for t, a, b in zip(pd.to_datetime(sub["T"], utc=True),
                               sub["mult_V1"], sub["mult_V2"]):
                lut[(s, sym, pd.Timestamp(t))] = (float(a), float(b))
    del panel

    n_exact = 0
    mult = {}
    for variant in ("V1", "V2"):
        mm = np.empty(n)
        for i in range(n):
            T = pd.Timestamp(bt_all[i])
            if T.tzinfo is None:
                T = T.tz_localize("UTC")
            key = (int(ph[i]), MAJORS[int(co[i])], T)
            hit = lut.get(key)
            if hit is not None:
                n_exact += (1 if variant == "V1" else 0)
                mm[i] = hit[0] if variant == "V1" else hit[1]
            else:
                t_ns, m1, m2 = grid[(int(ph[i]), MAJORS[int(co[i])])]
                q = pd.Timestamp(T)
                if q.tzinfo is None:
                    q = q.tz_localize("UTC")
                pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
                mm[i] = float((m1 if variant == "V1" else m2)[pos]) if pos >= 0 else 1.0
        mult[variant] = mm
    print(f"join: n={n} exact={n_exact} (V1 count)", flush=True)

    base_y = phase_mean_sums(ph, yr, w, yv, 5)
    out = {"config": {
        "rule": "post-stop x1.25 per (coin,shift): V1 N=7d, V2 N=3d",
        "seed_timing": SEED_TIMING, "seed_block": SEED_BLOCK, "n_perm": N_PERM,
        "block": BLOCK,
        "gate": "SECONDARY pass iff dSum5y >= +0.273 AND >= 4/5 years gain>0"},
        "join": {"n": int(n), "exact": int(n_exact)}}

    bar_mults = {}
    bar_pos = {}
    fill_idx_by_ysc = {}
    for y in range(5):
        for s in (0, 1, 2, 3):
            for ci, sym in enumerate(MAJORS):
                idx = np.where((yr == y) & (ph == s) & (co == ci))[0]
                if len(idx) == 0:
                    continue
                t_ns, m1, m2 = grid[(s, sym)]
                Ts = pd.to_datetime([bt_all[i] for i in idx], utc=True)
                lo_a, hi_a = Ts.min(), Ts.max() + pd.Timedelta(hours=4)
                keep = (t_ns >= np.int64(lo_a.value)) & (t_ns < np.int64(hi_a.value))
                bar_mults[(y, s, ci)] = (t_ns[keep], m1[keep], m2[keep])
                pos = np.empty(len(idx), dtype=np.int64)
                for j, i in enumerate(idx):
                    T = pd.Timestamp(bt_all[i])
                    if T.tzinfo is None:
                        T = T.tz_localize("UTC")
                    q = np.int64(T.value)
                    e = int(np.searchsorted(t_ns[keep], q, side="left"))
                    if e < int(keep.sum()) and t_ns[keep][e] == q:
                        pos[j] = e
                    else:
                        pos[j] = int(np.searchsorted(t_ns[keep], q, side="right")) - 1
                bar_pos[(y, s, ci)] = pos
                fill_idx_by_ysc[(y, s, ci)] = idx

    for variant in ("V1", "V2"):
        mm = mult[variant]
        boost_y = phase_mean_sums(ph, yr, w * mm, yv, 5)
        per_year = []
        for y in range(5):
            m = yr == y
            rm = float(mm[m].mean()) if m.any() else 1.0
            per_year.append({
                "year": ANCH5[y], "n_fills": int(m.sum()),
                "base": round(float(base_y[y]), 6),
                "boosted": round(float(boost_y[y]), 6),
                "realised_mean": round(rm, 6),
                "norm": round(float(boost_y[y]) / rm, 6) if rm else 0.0,
                "gain": round(float(boost_y[y]) / rm - float(base_y[y]), 6) if rm else 0.0,
                "boosted_share_fills": round(float((mm[m] == 1.25).mean()), 4)
                if m.any() else 0.0})
        gains = [r["gain"] for r in per_year]
        dsum = round(float(sum(gains)), 6)
        half = int(sum(1 for g in gains if g > 0))
        out[variant] = {"per_year": per_year, "dSum5y": dsum,
                        "sum_half": f"{half}/5",
                        "secondary_pass": bool(dsum >= 0.273 and half >= 4)}
        print(f"{variant}: dSum5y={dsum} half={half}/5 pass={dsum >= 0.273 and half >= 4}",
              flush=True)
        for r in per_year:
            print(f"  {r['year']} gain={r['gain']} share={r['boosted_share_fills']}", flush=True)

        for tag, seed in (("timing_placebo", SEED_TIMING), ("block_placebo", SEED_BLOCK)):
            rows = []
            for y in range(5):
                rng = np.random.default_rng(seed + y)
                actual = float(boost_y[y]) / float(mm[yr == y].mean())
                denom = float(mm[yr == y].mean())
                fill_w = w[yr == y]
                fill_y = yv[yr == y]
                fill_ph = ph[yr == y]
                gidx = np.where(yr == y)[0]
                if tag == "timing_placebo":
                    grp = {}
                    for key in [k for k in bar_mults if k[0] == y]:
                        _, m1k, m2k = bar_mults[key]
                        grp[key] = (m1k if variant == "V1" else m2k)
                    perms = np.empty(N_PERM)
                    for k in range(N_PERM):
                        fm = np.empty(len(gidx))
                        for key, idx in fill_idx_by_ysc.items():
                            if key[0] != y:
                                continue
                            pm = rng.permutation(grp[key])
                            fm[np.searchsorted(gidx, idx)] = pm[bar_pos[key]]
                        s = 0.0
                        for p in (0, 1, 2, 3):
                            mp = fill_ph == p
                            s += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
                        perms[k] = (s / 4.0) / denom
                else:
                    grp = {}
                    for key in [k for k in bar_mults if k[0] == y]:
                        _, m1k, m2k = bar_mults[key]
                        base_m = (m1k if variant == "V1" else m2k)
                        grp[key] = [base_m[b:b + BLOCK] for b in range(0, len(base_m), BLOCK)]
                    perms = np.empty(N_PERM)
                    for k in range(N_PERM):
                        fm = np.empty(len(gidx))
                        for key, idx in fill_idx_by_ysc.items():
                            if key[0] != y:
                                continue
                            blks = grp[key]
                            order = rng.permutation(len(blks))
                            seq = np.concatenate([blks[b] for b in order]) if blks else np.array([])
                            fm[np.searchsorted(gidx, idx)] = seq[bar_pos[key]]
                        s = 0.0
                        for p in (0, 1, 2, 3):
                            mp = fill_ph == p
                            s += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
                        perms[k] = (s / 4.0) / denom
                pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
                rows.append({"year": ANCH5[y], "actual_norm": round(actual, 6),
                             "p5": round(float(np.quantile(perms, 0.05)), 6),
                             "p50": round(float(np.quantile(perms, 0.50)), 6),
                             "p95": round(float(np.quantile(perms, 0.95)), 6),
                             "percentile": round(float(pct), 2)})
                print(f"{variant} {tag} y={y} pct={pct:.2f}", flush=True)
                if time.time() - last_hb >= HB_S:
                    last_hb = time.time()
                    print(f"[hb] compute_poststop_2021 alive elapsed {last_hb - t0:.0f}s",
                          flush=True)
            out[variant][tag] = rows

    (HERE / "tmp/poststop_2021.json").write_text(json.dumps(out, indent=1))
    print("wrote tmp/poststop_2021.json", flush=True)


if __name__ == "__main__":
    main()
