"""oc_weeklybook compute_books: REF books + bear + weekly slow + controls (LIGHT).

4h only, no 1m. Reads cached members via forward_v205 (read-only), writes
tmp/std_books.pkl + tmp/controls.json + tmp/proxy_diag.json. No engine outcome
computed here (exposure scalars + LIGHT proxy diagnostics only).
"""
from __future__ import annotations

import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TMP = HERE / "tmp"

sys.path.insert(0, str(HERE))
from weeklybook_rule import (F_V1, F_V2, WEDNESDAY, control_mult_per_year,
                             proxy_net_returns, sample_slow, sleeve_corr,
                             weekly_anchors)

ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR = pd.Timedelta(days=365)
DEV1 = pd.Timestamp("2025-09-24", tz="UTC")
CAP = pd.Timestamp("2026-09-23", tz="UTC")
SYMS_EXPECTED = {"BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def apply_bear(std: pd.DataFrame, bear: np.ndarray) -> pd.DataFrame:
    b = np.asarray(bear, dtype=bool)
    assert b.shape == (len(std),)
    vals = std.to_numpy(dtype=float)
    vals = np.where(b[:, None] & (vals > 0.0), vals * 0.5, vals)
    return pd.DataFrame(vals, index=std.index, columns=std.columns)


def main() -> None:
    eu = _load("eu_wb", RD / "engine_user" / "engine_user.py")
    fw = _load("fw_wb", ROOT / "scripts" / "forward_v205.py")
    books154, opens_std = eu.er.v154_books()
    cols = list(books154.columns)
    assert set(cols) == SYMS_EXPECTED, cols
    ref = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    assert np.isfinite(ref.to_numpy(float)).all()
    print(f"REF rows={len(ref)} cols={cols}", flush=True)
    btc = opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).fillna(False).to_numpy(bool)
    print(f"bear_frac={round(float(np.mean(bear)), 4)}", flush=True)
    fast = apply_bear(ref, bear)

    idx = fast.index
    wed = weekly_anchors(idx, WEDNESDAY)
    print(f"wed_anchors={int(wed.sum())} first={idx[wed][0] if wed.any() else None}", flush=True)
    slow_wed = pd.DataFrame(sample_slow(fast.to_numpy(float), wed),
                            index=idx, columns=cols)
    v1_pre = fast + F_V1 * slow_wed
    v2_pre = fast + F_V2 * slow_wed

    # Exposure-matched constants per anchor year (standard-grid gross sums).
    cy = {"C_V1": [], "C_V2": []}
    wcv1 = pd.DataFrame(0.0, index=idx, columns=cols)
    wcv2 = pd.DataFrame(0.0, index=idx, columns=cols)
    for y, a0 in enumerate(ANCH):
        a1 = a0 + YEAR
        m = (idx >= a0) & (idx < a1)
        g0 = float(fast.loc[m].abs().to_numpy().sum())
        c1 = control_mult_per_year(g0, float(v1_pre.loc[m].abs().to_numpy().sum()))
        c2 = control_mult_per_year(g0, float(v2_pre.loc[m].abs().to_numpy().sum()))
        cy["C_V1"].append({"anchor": str(a0.date()), "c": c1,
                           "gross_ratio": round(float(v1_pre.loc[m].abs().to_numpy().sum() / g0), 6) if g0 else None})
        cy["C_V2"].append({"anchor": str(a0.date()), "c": c2,
                           "gross_ratio": round(float(v2_pre.loc[m].abs().to_numpy().sum() / g0), 6) if g0 else None})
        wcv1.loc[m] = ref.loc[m] * c1
        wcv2.loc[m] = ref.loc[m] * c2
        print(f"year {a0.date()}: c_V1={c1:.6f} c_V2={c2:.6f} gross_ref={g0:.1f}", flush=True)

    # LIGHT proxy diagnostics: standard-grid open-to-open proxy (diagnostic scale).
    opens_full = pd.read_parquet(
        ROOT / "artifacts/research/engine_real/opens_v154.parquet")
    opens = opens_full.reindex(idx)[cols]
    fwd = (opens[cols].shift(-1).to_numpy(float) / opens[cols].to_numpy(float) - 1.0)
    valid = np.isfinite(fwd).all(axis=1)
    valid[-1] = False  # last bar has no forward open
    gidx = idx[valid]
    prox = {}
    legs = {"fast": fast.loc[valid].to_numpy(float),
            "slow_wed": slow_wed.loc[valid].to_numpy(float),
            "V1": v1_pre.loc[valid].to_numpy(float),
            "V2": v2_pre.loc[valid].to_numpy(float)}
    rp = {k: proxy_net_returns(v, fwd[valid]) for k, v in legs.items()}
    for k, v in rp.items():
        prox[k] = {"tot": round(float(np.sum(v)), 6), "n": int(len(v))}
    # Per-year sleeve-corr (slow standalone f=1 vs fast) + phase luck (7 phases).
    corr_rows = []
    for y, a0 in enumerate(ANCH):
        a1 = a0 + YEAR
        m = (gidx >= a0) & (gidx < a1)
        c = sleeve_corr(rp["fast"][m], rp["slow_wed"][m])
        corr_rows.append({"anchor": str(a0.date()), "n": int(m.sum()),
                          "corr_slow_fast": None if not np.isfinite(c) else round(float(c), 4),
                          "tot_fast": round(float(rp["fast"][m].sum()), 6),
                          "tot_slow": round(float(rp["slow_wed"][m].sum()), 6),
                          "tot_V1": round(float(rp["V1"][m].sum()), 6),
                          "tot_V2": round(float(rp["V2"][m].sum()), 6)})
    phases = []
    for wd in range(7):
        mk = weekly_anchors(idx, wd)
        sl = sample_slow(fast.to_numpy(float), mk)[valid]
        r = proxy_net_returns(sl, fwd[valid])
        per_y = []
        for y, a0 in enumerate(ANCH):
            a1 = a0 + YEAR
            m = (gidx >= a0) & (gidx < a1)
            c = sleeve_corr(rp["fast"][m], r[m])
            per_y.append({"anchor": str(a0.date()),
                          "corr": None if not np.isfinite(c) else round(float(c), 4),
                          "tot": round(float(r[m].sum()), 6)})
        phases.append({"weekday": wd, "n_anchors": int(mk.sum()), "years": per_y,
                       "tot": round(float(r.sum()), 6), "frozen": bool(wd == WEDNESDAY)})

    TMP.mkdir(parents=True, exist_ok=True)
    with open(TMP / "std_books.pkl", "wb") as fh:
        pickle.dump({"ref_pre": ref, "bear": bear, "cols": cols,
                     "slow_wed": slow_wed, "v1_pre": v1_pre, "v2_pre": v2_pre,
                     "wcv1_pre": wcv1, "wcv2_pre": wcv2, "cy": cy}, fh)
    (TMP / "controls.json").write_text(json.dumps({"cy": cy}, indent=1))
    (TMP / "proxy_diag.json").write_text(json.dumps(
        {"proxy": prox, "corr": corr_rows, "phases": phases,
         "note": "LIGHT standard-grid open-to-open proxy, 0.0005/unit turnover, diagnostic scale only; binding scale is the 4-phase engine"}, indent=1))
    print("wrote tmp/std_books.pkl + tmp/controls.json + tmp/proxy_diag.json", flush=True)
    print(json.dumps({"corr": corr_rows}, indent=1), flush=True)


if __name__ == "__main__":
    main()
