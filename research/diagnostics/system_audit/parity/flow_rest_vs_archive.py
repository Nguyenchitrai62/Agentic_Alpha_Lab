"""Train/serve-skew audit: live order-level flow buckets (scripts/aggflow_live.py --orders logic: REST /fapi/v1/aggTrades pages, orders =
consecutive aggTrades with the same ms transact time and side, an order cut by a page end carried to the next page) vs the research archive
(data/raw/aggflow_20260928_orders, scripts/fetch_aggtrades_flow.py --orders from data.binance.vision daily files), for archived 4h bars.
Also the fill-level tiers vs data/raw/aggflow_20260928 (same trades without order merging) as a trade-set check. Public REST only, read-only
(no state file is touched). Output: parity/flow_rest_vs_archive.json.

  .venv/Scripts/python.exe research/diagnostics/system_audit/parity/flow_rest_vs_archive.py [BAR ...]
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
os.chdir(ROOT)
sys.path.insert(0, str(HERE))
import rest_cache as rc  # noqa: E402

BARS = [pd.Timestamp(x, tz="UTC") for x in (sys.argv[1:] or ["2026-10-01 20:00"])]
URL = f"{rc.BASE}/fapi/v1/aggTrades"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


live = _load("par_aggflow_live", ROOT / "scripts/aggflow_live.py")  # only its pure helpers (_add, TIERS, COLS) are used


def first_id_at(sym, t_ms):
    try:
        j = rc.get(URL, {"symbol": sym, "startTime": t_ms, "endTime": t_ms + 3_599_999, "limit": 1})
    except Exception:  # e.g. the time search does not reach that far back
        j = None
    if isinstance(j, list) and j:
        return int(j[0]["a"]), "startTime"
    # fallback: secant / bisection on fromId
    hi = int(rc.get(URL, {"symbol": sym, "limit": 1})[-1]["a"])
    lo = hi - 50_000_000
    while hi - lo > 1:
        mid = (lo + hi) // 2
        T = int(rc.get(URL, {"symbol": sym, "fromId": mid, "limit": 1})[0]["T"])
        lo, hi = (mid, hi) if T < t_ms else (lo, mid)
    return hi, "bisection"


def rest_buckets(sym, bar):
    t0, t1 = int(bar.value // 1e6), int((bar + pd.Timedelta(hours=4)).value // 1e6)
    a0, how = first_id_at(sym, t0)
    st = {"last_id": a0 - 1}
    orders_b, fills_b = {}, {}
    arch_end = bar  # live code skips buckets < arch_end; here every bucket >= bar is kept, then only `bar` is read
    calls = 0
    while True:
        j = rc.get(URL, {"symbol": sym, "fromId": st["last_id"] + 1, "limit": 1000})
        calls += 1
        if not j:
            break
        d = pd.DataFrame(j)
        n = d["p"].astype(float) * d["q"].astype(float)
        sell = d["m"].astype(bool)
        live._add(fills_b, arch_end, pd.to_datetime(d["T"], unit="ms", utc=True).dt.floor("4h"), n, sell)
        # --- verbatim order rebuild of scripts/aggflow_live.py update(orders=True) ---
        T = d["T"].astype("int64")
        pend = st.get("pending")
        if pend:
            T = pd.concat([pd.Series([int(pend["T"])]), T], ignore_index=True)
            n = pd.concat([pd.Series([float(pend["n"])]), n], ignore_index=True)
            sell = pd.concat([pd.Series([bool(pend["m"])]), sell], ignore_index=True)
        oid = ((T != T.shift()) | (sell != sell.shift())).cumsum()
        o = pd.DataFrame({"T": T, "m": sell, "n": n}).groupby(oid, sort=False).agg(T=("T", "first"), m=("m", "first"), n=("n", "sum"))
        st["pending"] = {"T": int(o["T"].iloc[-1]), "m": bool(o["m"].iloc[-1]), "n": float(o["n"].iloc[-1])}
        o = o.iloc[:-1]
        live._add(orders_b, arch_end, pd.to_datetime(o["T"], unit="ms", utc=True).dt.floor("4h"), o["n"], o["m"].astype(bool))
        st["last_id"] = int(d["a"].iloc[-1])
        if int(d["T"].iloc[-1]) >= t1 + 60_000:  # one minute past the bar end: the bar's last order is closed
            break
    return orders_b.get(bar, {}), fills_b.get(bar, {}), {"first_id": a0, "id_search": how, "calls": calls}


def compare(rest: dict, arch: pd.Series) -> dict:
    out = {}
    for c in live.COLS:
        r, a = float(rest.get(c, 0.0)), float(arch.get(c, 0.0)) if c in arch else 0.0
        out[c] = {"rest": round(r, 2), "archive": round(a, 2), "rel_diff": round(abs(r - a) / max(abs(a), 1e-9), 6) if a else (0.0 if r == 0 else None)}
    return out


def flow_feats(sym, bar, rest_row, base):
    """The six v236 features at `bar` from the archive with the bar's row replaced by the REST row (what the live advisor would compute)."""
    flo = _load(f"par_flo_{sym}", ROOT / "research/parallel/rounds/parallel-20260906-r2/v236/flow_features.py")
    arch = pd.read_parquet(base / f"{sym}_flow_4h.parquet").sort_index()
    arch = arch[arch.index <= bar]
    alt = arch.copy()
    for c in live.COLS:
        alt.loc[bar, c] = float(rest_row.get(c, 0.0))
    idx = pd.DatetimeIndex([bar])
    fa, fr = flo.flow_features(sym, idx, arch), flo.flow_features(sym, idx, alt)
    return {c: {"archive": float(fa[c].iloc[0]), "rest": float(fr[c].iloc[0]), "abs_diff": float(abs(fa[c].iloc[0] - fr[c].iloc[0]))} for c in fa.columns}


def main():
    res = {"bars": [str(b) for b in BARS], "per_symbol": {}}
    for bar in BARS:
        for sym in rc.SYMS:
            ao = pd.read_parquet(live.OUT_ORDERS / f"{sym}_flow_4h.parquet")
            af = pd.read_parquet(live.OUT / f"{sym}_flow_4h.parquet")
            if bar not in ao.index:
                res["per_symbol"][f"{sym} {bar}"] = "bar not in the order archive"
                continue
            ro, rf, info = rest_buckets(sym, bar)
            co = compare(ro, ao.loc[bar])
            cf = compare(rf, af.loc[bar]) if bar in af.index else "bar not in the fill archive"
            n_rest, n_arch = sum(ro.get(f"n_{k}", 0) for k in live.TNAME), float(sum(ao.loc[bar].get(f"n_{k}", 0) for k in live.TNAME))
            notional_rest = sum(ro.get(f"{x}_{k}", 0) for x in ("buy", "sell") for k in live.TNAME)
            notional_arch = float(sum(ao.loc[bar].get(f"{x}_{k}", 0) for x in ("buy", "sell") for k in live.TNAME))
            res["per_symbol"][f"{sym} {bar}"] = {
                **info, "orders_rest": n_rest, "orders_archive": n_arch, "total_notional_rest": round(notional_rest, 2),
                "total_notional_archive": round(notional_arch, 2),
                "max_rel_diff_order_tiers": max((v["rel_diff"] or 0) for v in co.values()),
                "max_rel_diff_fill_tiers": max((v["rel_diff"] or 0) for v in cf.values()) if isinstance(cf, dict) else cf,
                "order_tiers": co, "fill_tiers": cf, "features_at_bar": flow_feats(sym, bar, ro, live.OUT_ORDERS)}
            print(sym, bar, info, "orders rest/arch", n_rest, n_arch, "max rel tier diff (orders, fills)",
                  res["per_symbol"][f"{sym} {bar}"]["max_rel_diff_order_tiers"], res["per_symbol"][f"{sym} {bar}"]["max_rel_diff_fill_tiers"], flush=True)
            time.sleep(5)
    (HERE / "flow_rest_vs_archive.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
