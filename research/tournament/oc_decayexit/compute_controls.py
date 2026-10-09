"""oc_decayexit compute_controls: REF books + bear + decay proxy + exposure controls.

LIGHT (4h only, no 1m). Reads cached members via forward_v205 (read-only),
writes tmp/std_books.pkl + tmp/controls.json. No outcome computed here
(controls are pre-engine exposure scalars; engine results come later).
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
from decayexit_rule import FRAC_V1, FRAC_V2, THETA, control_mult_per_year, simulate_proxy

ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR = pd.Timedelta(days=365)
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
    eu = _load("eu_dc", RD / "engine_user" / "engine_user.py")
    fw = _load("fw_dc", ROOT / "scripts" / "forward_v205.py")
    books154, opens_std = eu.er.v154_books()
    cols = list(books154.columns)
    assert set(cols) == SYMS_EXPECTED, cols
    ref = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    # Self-consistency: REF is research_books_d2 by definition.
    print(f"REF rows={len(ref)} cols={cols}", flush=True)
    btc = opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).fillna(False).to_numpy(bool)
    print(f"bear_frac={round(float(np.mean(bear)), 4)}", flush=True)
    sb_ref = apply_bear(ref, bear)
    # Decay proxy on post-bear standard-grid weights (causal, no fills).
    px1 = simulate_proxy(sb_ref.to_numpy(dtype=float), FRAC_V1, THETA)
    px2 = simulate_proxy(sb_ref.to_numpy(dtype=float), FRAC_V2, THETA)
    idx = sb_ref.index
    proxy1 = pd.DataFrame(px1, index=idx, columns=cols)
    proxy2 = pd.DataFrame(px2, index=idx, columns=cols)
    cy = {"C_V1": [], "C_V2": []}
    wcv1 = pd.DataFrame(0.0, index=idx, columns=cols)
    wcv2 = pd.DataFrame(0.0, index=idx, columns=cols)
    for y, a0 in enumerate(ANCH):
        a1 = a0 + YEAR
        m = (idx >= a0) & (idx < a1)
        g0 = float(sb_ref.loc[m].abs().to_numpy().sum())
        c1 = control_mult_per_year(sb_ref.loc[m].abs().to_numpy(), proxy1.loc[m].abs().to_numpy())
        c2 = control_mult_per_year(sb_ref.loc[m].abs().to_numpy(), proxy2.loc[m].abs().to_numpy())
        # Mean-scale diagnostics (proxy/ref where ref != 0).
        with np.errstate(divide="ignore", invalid="ignore"):
            sc1 = float((proxy1.loc[m].abs().to_numpy().sum() / g0)) if g0 else 1.0
            sc2 = float((proxy2.loc[m].abs().to_numpy().sum() / g0)) if g0 else 1.0
        cy["C_V1"].append({"anchor": str(a0.date()), "c": c1, "proxy_gross_ratio": sc1})
        cy["C_V2"].append({"anchor": str(a0.date()), "c": c2, "proxy_gross_ratio": sc2})
        # Controls scale the PRE-bear REF (bear commutes with c>=0; applied in engine).
        wcv1.loc[m] = ref.loc[m] * c1
        wcv2.loc[m] = ref.loc[m] * c2
        print(f"year {a0.date()}: c_V1={c1:.4f} c_V2={c2:.4f} gross_ref={g0:.1f}", flush=True)
    TMP.mkdir(parents=True, exist_ok=True)
    with open(TMP / "std_books.pkl", "wb") as fh:
        pickle.dump({"ref_pre": ref, "bear": bear, "cols": cols,
                     "proxy_V1": proxy1, "proxy_V2": proxy2, "cy": cy,
                     "wcv1_pre": wcv1, "wcv2_pre": wcv2}, fh)
    (TMP / "controls.json").write_text(json.dumps({"cy": cy}, indent=1))
    print("wrote tmp/std_books.pkl + tmp/controls.json", flush=True)


if __name__ == "__main__":
    main()
