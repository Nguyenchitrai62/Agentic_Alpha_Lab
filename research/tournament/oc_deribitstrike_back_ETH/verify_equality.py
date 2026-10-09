"""Equality check: re-fetch 2025-06 into tmp/ and compare row-for-row with forward file.

Usage: python verify_equality.py [--month 2025-06]
Writes tmp/ETH_<month>.parquet (scratch only) and prints comparison.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_back_eth import CUR, FWD_DIR, fetch_month  # noqa

HERE = Path(__file__).resolve().parent
TMP = HERE / "tmp"


def compare_month(ym: str) -> dict:
    from fetch_back_eth import last_complete_day_utc

    end_cap = last_complete_day_utc()
    s = requests.Session()
    print(f"re-fetching {CUR} {ym} into tmp/ ...", flush=True)
    df = fetch_month(s, ym, end_cap)
    TMP.mkdir(parents=True, exist_ok=True)
    tmp_f = TMP / f"{CUR}_{ym}.parquet"
    tmp_f.with_suffix(".tmp.parquet").unlink(missing_ok=True)
    df.to_parquet(tmp_f.with_suffix(".tmp.parquet"), index=False)
    tmp_f.with_suffix(".tmp.parquet").rename(tmp_f)
    print(f"re-fetched rows={len(df)} -> {tmp_f}", flush=True)

    fwd_f = FWD_DIR / f"{CUR}_{ym}.parquet"
    a = pd.read_parquet(tmp_f)
    b = pd.read_parquet(fwd_f)
    out = {"month": ym, "mine_rows": int(len(a)), "fwd_rows": int(len(b)),
           "mine_file": str(tmp_f), "fwd_file": str(fwd_f)}
    out["columns_equal"] = bool(list(a.columns) == list(b.columns))
    if list(a.columns) != list(b.columns):
        out["mine_columns"] = list(a.columns)
        out["fwd_columns"] = list(b.columns)
        print(out, flush=True)
        return out
    key = ["hour", "instrument_name"]
    a2 = a.sort_values(key).reset_index(drop=True)
    b2 = b.sort_values(key).reset_index(drop=True)
    out["same_shape"] = bool(a2.shape == b2.shape)
    if a2.shape != b2.shape:
        print(out, flush=True)
        return out
    # Exact key equality
    out["keys_equal"] = bool(((a2["hour"].astype(str) == b2["hour"].astype(str)) &
                              (a2["instrument_name"] == b2["instrument_name"])).all())
    # Float columns: exact + tolerance
    float_cols = [c for c in a2.columns if pd.api.types.is_float_dtype(a2[c])]
    exact_all = True
    max_abs_diff = 0.0
    for c in float_cols:
        x, y = a2[c].to_numpy(), b2[c].to_numpy()
        both_nan = pd.isna(x) & pd.isna(y)
        eq = both_nan | (x == y)
        if not bool(eq.all()):
            exact_all = False
            d = pd.Series(x) - pd.Series(y)
            d = d[~(both_nan)].abs().max()
            max_abs_diff = max(max_abs_diff, float(d))
    out["floats_exact"] = bool(exact_all)
    out["max_abs_diff_if_not_exact"] = float(max_abs_diff)
    # Non-float, non-key columns
    other = [c for c in a2.columns if c not in key + float_cols]
    other_eq = True
    for c in other:
        x = a2[c].astype(str)
        y = b2[c].astype(str)
        if not bool((x == y).all()):
            other_eq = False
            out[f"mismatch_col_{c}"] = True
    out["other_equal"] = bool(other_eq)
    out["row_for_row_equal"] = bool(out["same_shape"] and out["keys_equal"] and exact_all and other_eq)
    print(out, flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default="2025-06")
    a = ap.parse_args()
    compare_month(a.month)


if __name__ == "__main__":
    main()
