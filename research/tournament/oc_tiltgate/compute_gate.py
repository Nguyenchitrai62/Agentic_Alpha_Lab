"""oc_tiltgate gate decisions (CPU-only).

- 2020-fit row-count gate: total harness rows with t_exit < 2020-09-17;
  >= 1000 -> fit 2020 exactly like oc_voltilt/make_fits.py, else 2021 OFF.
- Per (anchor A, variant): exact window W(A) = [A-372d, A-7d) on replica
  fills (k2placebo ledger + tmp/ledger_ext.npz), mult from the prior-year
  live fit (anchor A-1yr fits.json entry), effect = sum((mult-1)*w*y10)/n,
  ON iff effect > 0. Output: tmp/gate.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TMP = HERE / "tmp"
K2P = ROOT / "research/tournament/oc_k2placebo"
VT = ROOT / "research/tournament/oc_voltilt"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "research/tournament"))
import harness  # noqa: E402
from gate_rule import ANCH5, decide, gate_effect, gate_window  # noqa: E402

sys.path.insert(0, str(VT))
from tilt_rule import assign_mult  # noqa: E402  (frozen rule, read-only)

MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
FEAT_COL = {"G_RV6": "risk_RV6", "G_GARCH": "risk_GARCH"}
FIT_KEY = {"G_RV6": "V_RV6", "G_GARCH": "V_GARCH"}
BASE_GATE = 7.718304
N_GATE = 22312


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)

    # ---- 2020-fit row-count gate (outcome-independent) ----
    d = harness.load()
    n2020 = int((d["t_exit"] < pd.Timestamp("2020-09-17", tz="UTC")).sum())
    print(f"harness rows with t_exit < 2020-09-17: {n2020} (need >= 1000)",
          flush=True)
    fit2020 = None
    if n2020 >= 1000:
        print("2020 sample sufficient: fitting 2020 like make_fits.py", flush=True)
        f = pd.read_parquet(VT / "vol_features_4shift.parquet",
                            columns=["sym", "shift", "T", "risk_RV6", "risk_GARCH"])
        f["T"] = pd.to_datetime(f["T"], utc=True)
        f0 = f[f["shift"] == 0][["sym", "T", "risk_RV6", "risk_GARCH"]]
        n0 = len(d)
        d = d.merge(f0, on=["sym", "T"], how="left")
        assert len(d) == n0
        maj = d["sym"].isin(harness.MAJORS).to_numpy()
        fit2020 = {}
        ok_fit = True
        for v, col in (("V_RV6", "risk_RV6"), ("V_GARCH", "risk_GARCH")):
            trm = (d["t_exit"] < pd.Timestamp("2020-09-17", tz="UTC")).to_numpy() & maj
            risk = d[col].to_numpy(dtype=float)
            ok = trm & np.isfinite(risk)
            if int(ok.sum()) < 100:
                print(f"2020 fit {v}: only {int(ok.sum())} joined rows -> no fit",
                      flush=True)
                ok_fit = False
                break
            m = np.isfinite(risk[ok]) & np.isfinite(d["y_dep"].to_numpy()[ok])
            rho = float(pd.Series(risk[ok][m]).corr(
                pd.Series(d["y_dep"].to_numpy()[ok][m]), method="spearman"))
            q20, q80 = [float(x) for x in np.quantile(risk[ok], [0.2, 0.8])]
            fit2020[v] = dict(direction=1 if rho > 0 else -1, q20=q20, q80=q80,
                              rho=round(rho, 4))
            print(f"2020 fit {v}: dir={fit2020[v]['direction']} rho={rho:.4f}",
                  flush=True)
        if not ok_fit:
            fit2020 = None
    else:
        print("2020 sample < 1000: NO 2020 fit attempted; 2021 gate = OFF",
              flush=True)

    # ---- ledgers (main read-only + extension) ----
    led = dict(np.load(K2P / "tmp/ledger.npz"))
    bt_main = np.load(K2P / "tmp/bt_all.npy", allow_pickle=True)
    n_main = len(led["w"])
    assert n_main == N_GATE, (n_main, N_GATE)
    for k in ("phase", "coin"):
        led[k] = led[k].astype(int)
    w_main = led["w"].astype(float)
    y_main = led["y10"].astype(float)
    bt_main = np.array([pd.Timestamp(t) for t in bt_main])
    print(f"main ledger n={n_main} range={bt_main.min()}..{bt_main.max()}",
          flush=True)

    ext = dict(np.load(TMP / "ledger_ext.npz"))
    bt_ext = np.load(TMP / "bt_ext.npy", allow_pickle=True)
    bt_ext = np.array([pd.Timestamp(t) for t in bt_ext])
    print(f"ext ledger n={len(ext['w'])} range={bt_ext.min()}..{bt_ext.max()}" if len(bt_ext) else "ext ledger EMPTY",
          flush=True)
    assert (bt_ext < pd.Timestamp("2021-09-24", tz="UTC")).all(), "ext must end before main start"

    ph = np.concatenate([ext["phase"].astype(int), led["phase"].astype(int)])
    co = np.concatenate([ext["coin"].astype(int), led["coin"].astype(int)])
    w = np.concatenate([ext["w"].astype(float), w_main])
    yv = np.concatenate([ext["y10"].astype(float), y_main])
    bt = np.concatenate([bt_ext, bt_main])
    order = np.argsort(bt)
    ph, co, w, yv, bt = ph[order], co[order], w[order], yv[order], bt[order]

    # ---- vol feature lookup ----
    fits = json.loads((VT / "fits.json").read_text())
    feat = pd.read_parquet(VT / "vol_features_4shift.parquet",
                           columns=["sym", "shift", "T", "risk_RV6", "risk_GARCH"])
    lut6, lutg = {}, {}
    for s, sh, t, r6, rg in zip(feat["sym"], feat["shift"], feat["T"],
                                feat["risk_RV6"], feat["risk_GARCH"]):
        key = (str(s), int(sh), pd.Timestamp(t))
        lut6[key] = float(r6)
        lutg[key] = float(rg)
    del feat
    lut = {"G_RV6": lut6, "G_GARCH": lutg}

    out = {"harness_rows_t_exit_lt_2020_09_17": n2020,
           "fit2020_attempted": bool(fit2020),
           "variants": {}}
    for variant in ("G_RV6", "G_GARCH"):
        rows = {}
        for y, a in enumerate(ANCH5):
            lo, hi = gate_window(a)
            m = (bt >= lo) & (bt < hi)
            idx = np.where(m)[0]
            n = int(m.sum())
            if y == 0:
                if fit2020 is None:
                    rows[a] = dict(on=False, effect=None, n=n,
                                   n_sized=None, fit="none (<1000 rows)",
                                   reason="no 2020 fit: harness rows "
                                          f"{n2020} < 1000 -> OFF")
                    print(f"{variant} {a}: OFF (no 2020 fit) n_window={n}",
                          flush=True)
                    continue
                f = fit2020[FIT_KEY[variant]]
                fit_name = "2020-09-24(fit t_exit<2020-09-17)"
            else:
                f = fits[FIT_KEY[variant]][ANCH5[y - 1]]
                fit_name = ANCH5[y - 1]
            L = lut[variant]
            mult = np.empty(n)
            for j, i in enumerate(idx):
                key = (MAJORS[int(co[i])], int(ph[i]), pd.Timestamp(bt[i]))
                q = L.get(key)
                r = float(q) if q is not None and np.isfinite(q) else float("nan")
                mult[j] = assign_mult(r, f["direction"], f["q20"], f["q80"],
                                      1.25, 0.75)
            g = gate_effect(mult, w[idx], yv[idx])
            on = decide(g["effect"])
            rows[a] = dict(on=bool(on), effect=round(g["effect"], 9), n=n,
                           n_sized=g["n_sized"], fit=fit_name)
            print(f"{variant} {a}: window [{lo.date()}..{hi.date()}) "
                  f"fit={fit_name} n={n} n_sized={g['n_sized']} "
                  f"effect={g['effect']:.9f} -> {'ON' if on else 'OFF'}",
                  flush=True)
        out["variants"][variant] = rows
    (TMP / "gate.json").write_text(json.dumps(out, indent=1))
    print("wrote tmp/gate.json", flush=True)


if __name__ == "__main__":
    main()
