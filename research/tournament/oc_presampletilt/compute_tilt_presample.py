"""oc_presampletilt: frozen-tilt gains + timing/block placebos on the pre-sample ledger.

Frozen method (see PLAN.md): per fill join (sym, shift=phase, T) to the pre-sample
feature tables; assign_mult with the FROZEN anchor-2021 fits (hi/lo 1.25/0.75,
missing -> 1). Per pre-sample year (4-phase means, same as k2placebo
phase_mean_sums): base(y), tilt(y), realised_mean(y), norm(y) = tilt/realised_mean,
gain = norm - base. Timing placebo: 1000 uniform bar-level perms over that year's
decision-bar universe (seed 20261007+y). Block placebo: 42-bar blocks per
(sym, shift) (seed 20261008+y). Percentile = 100*(1+#{perm<=actual})/1001,
significant iff >= 95. CPU-only (numpy). Heartbeat every 600 s.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
TMP = HERE / "tmp"
sys.path.insert(0, str(HERE))
from tilt_rule import FROZEN_2021, assign_mult  # noqa: E402

LEGS = ("Y2017", "Y2018", "Y2019", "Y2020p")
LEG_BOUNDS = {
    "Y2017": (pd.Timestamp("2017-10-16", tz="UTC"), pd.Timestamp("2018-01-01", tz="UTC")),
    "Y2018": (pd.Timestamp("2018-01-01", tz="UTC"), pd.Timestamp("2019-01-01", tz="UTC")),
    "Y2019": (pd.Timestamp("2019-01-01", tz="UTC"), pd.Timestamp("2020-01-01", tz="UTC")),
    "Y2020p": (pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2020-09-01", tz="UTC")),
}
MAJORS4 = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
PHASES = (0, 1, 2, 3)
VARIANTS = ("V_RV6", "V_GARCH", "C2")
FEAT_COL = {"V_RV6": "risk_RV6", "V_GARCH": "risk_GARCH", "C2": "risk_C2"}
SEED_TIMING = 20261007
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
HB_S = 600


def phase_mean_sums(ph, yr, wv, yv, n_years=4):
    out = []
    for y in range(n_years):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


def main() -> None:
    t0 = time.time()
    last_hb = t0
    TMP.mkdir(parents=True, exist_ok=True)
    led = dict(np.load(TMP / "ledger_presample.npz"))
    for k in ("phase", "coin", "year", "t_ord", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.load(TMP / "bt_presample.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded presample ledger n={n}", flush=True)

    vol = pd.read_parquet(HERE / "vol_features_presample.parquet")
    ch = pd.read_parquet(HERE / "chronos_features_presample.parquet",
                         columns=["sym", "shift", "T", "ch_q10"])
    ch["risk_C2"] = -ch["ch_q10"].to_numpy(dtype=float)
    feat_tables = {"V_RV6": vol[["sym", "shift", "T", "risk_RV6"]],
                   "V_GARCH": vol[["sym", "shift", "T", "risk_GARCH"]],
                   "C2": ch[["sym", "shift", "T", "risk_C2"]]}
    del vol, ch

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)

    res = {"config": {
        "rule": "frozen 2021 fits (dir/q20/q80) hi/lo 1.25/0.75 missing->1; "
                "labelled fit from later data, rule frozen",
        "fits_2021": FROZEN_2021,
        "seed_timing": SEED_TIMING, "seed_block": SEED_BLOCK,
        "n_perm": N_PERM, "block": BLOCK,
        "normalisation": "norm(y)=tilt(y)/realised_mean(y); perm norms use ACTUAL denominator",
        "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95",
        "ledger": "tmp/ledger_presample.npz (D0+B1 same as k2placebo, spot store)",
    }, "legs": list(LEGS), "n_fills": int(n)}

    for variant in VARIANTS:
        f = FROZEN_2021[variant]
        col = FEAT_COL[variant]
        ft = feat_tables[variant]
        lut: dict = {}
        for s, sh, t, q in zip(ft["sym"], ft["shift"], ft["T"], ft[col]):
            lut[(str(s), int(sh), pd.Timestamp(t))] = float(q)
        del ft
        mult = np.ones(n, dtype=float)
        miss = 0
        for i in range(n):
            key = (MAJORS4[int(co[i])], int(ph[i]), pd.Timestamp(bt_all[i]))
            q = lut.get(key)
            if q is None:
                miss += 1
                mult[i] = 1.0
            else:
                mult[i] = assign_mult(q, f["direction"], f["q20"], f["q80"])
        print(f"{variant}: join n={n} missing={miss} "
              f"mult={sorted(set(np.round(mult, 6)))}", flush=True)

        base_y = phase_mean_sums(ph, yr, w, yv)
        tilt_y = phase_mean_sums(ph, yr, w * mult, yv)
        years = []
        for y in range(4):
            m = yr == y
            rm = float(mult[m].mean()) if m.any() else 1.0
            years.append({"year": LEGS[y], "n_fills": int(m.sum()),
                          "base": round(float(base_y[y]), 6),
                          "tilt": round(float(tilt_y[y]), 6),
                          "realised_mean": round(rm, 6),
                          "norm": round(float(tilt_y[y]) / rm, 6) if rm else 0.0,
                          "gain": round(float(tilt_y[y]) / rm - float(base_y[y]), 6)
                          if rm else 0.0})
        for r in years:
            print(f"  {variant} {r['year']} n={r['n_fills']} base={r['base']} "
                  f"tilt={r['tilt']} rm={r['realised_mean']} norm={r['norm']} "
                  f"gain={r['gain']}", flush=True)

        # decision-bar universes per pre-sample year from the feature table
        ft2 = (pd.read_parquet(HERE / "vol_features_presample.parquet",
                               columns=["sym", "shift", "T", "risk_RV6", "risk_GARCH"])
               if variant in ("V_RV6", "V_GARCH") else
               pd.read_parquet(HERE / "chronos_features_presample.parquet",
                               columns=["sym", "shift", "T"]))
        if variant == "C2":
            ch2 = pd.read_parquet(HERE / "chronos_features_presample.parquet",
                                  columns=["sym", "shift", "T", "ch_q10"])
            ft2 = ft2.merge(ch2, on=["sym", "shift", "T"], how="left")
            ft2["risk_C2"] = -ft2["ch_q10"].to_numpy(dtype=float)
        bar_mults, bar_keys = [], []
        for y in range(4):
            lo_a, hi_a = LEG_BOUNDS[LEGS[y]]
            sub = ft2[(ft2["T"] >= lo_a) & (ft2["T"] < hi_a)].copy()
            sub = sub.sort_values(["sym", "shift", "T"]).reset_index(drop=True)
            r = sub[col].to_numpy(dtype=float)
            mm = np.where(~np.isfinite(r), 1.0,
                          np.where(r >= f["q80"], 1.25,
                                   np.where(r <= f["q20"], 0.75, 1.0)))
            keys = list(zip(sub["sym"].astype(str), sub["shift"].astype(int),
                            pd.to_datetime(sub["T"], utc=True)))
            bar_mults.append(mm.astype(float))
            bar_keys.append(keys)
        del ft2
        # fill -> bar positions
        bar_pos = []
        for y in range(4):
            idx = {k: i for i, k in enumerate(bar_keys[y])}
            pos = np.full(int((yr == y).sum()), -1, dtype=np.int64)
            for j, i in enumerate(np.where(yr == y)[0]):
                pos[j] = idx.get((MAJORS4[int(co[i])], int(ph[i]),
                                  pd.Timestamp(bt_all[i])), -1)
            nmiss = int((pos < 0).sum())
            print(f"{variant} {LEGS[y]}: universe={len(bar_keys[y])} "
                  f"fills_missing_bar={nmiss} (missing->mult 1, excluded from perms)",
                  flush=True)
            # fills with missing bars keep mult 1; drop them from permutation
            # mapping by pointing them at a mult-1.0 bar if present, else keep -1
            if nmiss:
                ones = np.where(bar_mults[y] == 1.0)[0]
                fill = int(ones[0]) if len(ones) else -1
                pos[pos < 0] = fill
                assert (pos >= 0).all(), f"{variant} {LEGS[y]}: no mult-1 bar"
            bar_pos.append(pos)
        print(f"bar universes {variant}: {[len(b) for b in bar_mults]}", flush=True)

        timing, block = [], []
        for y in range(4):
            rng = np.random.default_rng(SEED_TIMING + y)
            mm, pos = bar_mults[y], bar_pos[y]
            denom = float(mult[yr == y].mean())
            actual = float(tilt_y[y]) / denom
            fw, fy, fp = w[yr == y], yv[yr == y], ph[yr == y]
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                fm = rng.permutation(mm)[pos]
                s = sum(float((fw[fp == p] * fm[fp == p] * fy[fp == p]).sum())
                        for p in PHASES) / 4.0
                perms[k] = s / denom
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            timing.append({"year": LEGS[y], "actual_norm": round(actual, 6),
                           "p5": round(float(np.quantile(perms, 0.05)), 6),
                           "p50": round(float(np.quantile(perms, 0.50)), 6),
                           "p95": round(float(np.quantile(perms, 0.95)), 6),
                           "percentile": round(float(pct), 2)})
            print(f"timing {variant} {LEGS[y]} actual={actual:.6f} pct={pct:.2f}",
                  flush=True)
            if time.time() - last_hb >= HB_S:
                last_hb = time.time()
                print(f"[hb] compute_tilt_presample alive elapsed {last_hb - t0:.0f}s",
                      flush=True)
        for y in range(4):
            rng = np.random.default_rng(SEED_BLOCK + y)
            keys, mm, pos = bar_keys[y], bar_mults[y], bar_pos[y]
            groups: dict = {}
            for i, k in enumerate(keys):
                groups.setdefault((k[0], k[1]), []).append(i)
            gblocks = {}
            for g, idxs in groups.items():
                idxs = sorted(idxs, key=lambda i: keys[i][2])
                gblocks[g] = [idxs[b:b + BLOCK] for b in range(0, len(idxs), BLOCK)]
            denom = float(mult[yr == y].mean())
            actual = float(tilt_y[y]) / denom
            fw, fy, fp = w[yr == y], yv[yr == y], ph[yr == y]
            perms = np.empty(N_PERM)
            cur = np.empty_like(mm)
            for k in range(N_PERM):
                for g, blks in gblocks.items():
                    order = rng.permutation(len(blks))
                    seq = []
                    for b in order:
                        seq.extend(mm[blks[b]])
                    for i, v in zip(sorted(groups[g], key=lambda i: keys[i][2]), seq):
                        cur[i] = v
                fm = cur[pos]
                s = sum(float((fw[fp == p] * fm[fp == p] * fy[fp == p]).sum())
                        for p in PHASES) / 4.0
                perms[k] = s / denom
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            block.append({"year": LEGS[y], "actual_norm": round(actual, 6),
                          "p5": round(float(np.quantile(perms, 0.05)), 6),
                          "p50": round(float(np.quantile(perms, 0.50)), 6),
                          "p95": round(float(np.quantile(perms, 0.95)), 6),
                          "percentile": round(float(pct), 2)})
            print(f"block {variant} {LEGS[y]} actual={actual:.6f} pct={pct:.2f}",
                  flush=True)
        res[variant] = {"per_year": years, "timing_placebo": timing,
                        "block_placebo": block}
    (TMP / "tilt_presample.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/tilt_presample.json", flush=True)


if __name__ == "__main__":
    main()
