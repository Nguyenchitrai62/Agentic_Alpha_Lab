"""Live extension of the 4h large-order flow aggregates (research output only - public market data, no orders).

The public archive (scripts/fetch_aggtrades_flow.py) lags about one day. This collector fills the gap from the Binance REST
endpoint /fapi/v1/aggTrades (fromId pagination, resumable): every run fetches the aggTrades since the last seen id and adds them to
the same UTC 4h x notional-tier buckets (taker buy / sell notional and count). State per symbol:
data/raw/aggflow_20260928/live_state_{SYM}.json (last id + buckets after the archive end). `combined_flow(sym)` returns the archive
rows plus the live buckets after the archive's last bar - only buckets whose 4h bar has closed are returned (a partial bar never
reaches the features).

  python scripts/aggflow_live.py            # update all majors
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

OUT = Path("data/raw/aggflow_20260928")
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
TIERS = (0.0, 1e4, 1e5, 1e6, np.inf)
TNAME = ("lt10k", "10k_100k", "100k_1m", "ge1m")
COLS = [f"{a}_{b}" for a in ("buy", "sell", "n") for b in TNAME]
MAX_CALLS = 1500  # per symbol per run (weight 20 each; the one-time backlog continues on the next run)


def _base_url() -> str:
    from agentic_alpha_lab.data.binance_usdm import BASE_URL
    return BASE_URL


def _archive(sym: str) -> pd.DataFrame:
    p = OUT / f"{sym}_flow_4h.parquet"
    return pd.read_parquet(p).sort_index() if p.exists() else pd.DataFrame(columns=COLS)


def update(sym: str, session: requests.Session) -> str:
    sp = OUT / f"live_state_{sym}.json"
    arch = _archive(sym)
    arch_end = (arch.index.max() + pd.Timedelta(hours=4)) if len(arch) else pd.Timestamp.now(tz="UTC").floor("4h")
    st = json.loads(sp.read_text()) if sp.exists() else {}
    url = f"{_base_url()}/fapi/v1/aggTrades"
    if not st.get("last_id"):
        start_ms = int(arch_end.timestamp() * 1000)
        j = session.get(url, params={"symbol": sym, "startTime": start_ms, "endTime": start_ms + 3_599_999, "limit": 1}, timeout=30).json()
        if isinstance(j, dict):  # e.g. -4166: the time search only reaches back 2 days -> refresh the archive first
            raise RuntimeError(f"{sym}: cannot locate the first live trade after {arch_end}: {j} (run fetch_aggtrades_flow.py first)")
        if not j:
            return f"{sym}: no trades after {arch_end}"
        st = {"last_id": int(j[0]["a"]) - 1, "buckets": {}}
    buckets = {pd.Timestamp(k): v for k, v in st.get("buckets", {}).items()}
    calls, n_new = 0, 0
    while calls < MAX_CALLS:
        r = session.get(url, params={"symbol": sym, "fromId": st["last_id"] + 1, "limit": 1000}, timeout=30)
        calls += 1
        if r.status_code == 429 or r.status_code == 418:
            time.sleep(60)
            continue
        j = r.json()
        if not j:
            break
        d = pd.DataFrame(j)
        n = d["p"].astype(float) * d["q"].astype(float)
        sell = d["m"].astype(bool)
        t = pd.to_datetime(d["T"], unit="ms", utc=True).dt.floor("4h")
        tier = pd.cut(n, TIERS, right=False, labels=TNAME)
        g = pd.DataFrame({"t": t, "tier": tier, "buy": n.where(~sell, 0.0), "sell": n.where(sell, 0.0), "n": 1.0})
        for (bt, tr), row in g.groupby(["t", "tier"], observed=True)[["buy", "sell", "n"]].sum().iterrows():
            if bt < arch_end:
                continue  # already in the archive
            b = buckets.setdefault(bt, {c: 0.0 for c in COLS})
            for k in ("buy", "sell", "n"):
                b[f"{k}_{tr}"] += float(row[k])
        st["last_id"] = int(d["a"].iloc[-1])
        n_new += len(d)
        if len(d) < 1000:
            break
    # drop buckets the archive now covers
    buckets = {k: v for k, v in buckets.items() if k >= arch_end}
    st["buckets"] = {str(k): v for k, v in sorted(buckets.items())}
    st["updated_at"] = pd.Timestamp.now(tz="UTC").isoformat()
    sp.write_text(json.dumps(st))
    return f"{sym}: +{n_new} aggTrades in {calls} calls, live buckets {len(buckets)} from {min(buckets) if buckets else '-'}"


def combined_flow(sym: str, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Archive + closed live buckets after the archive end (same columns as the archive parquet)."""
    now = now or pd.Timestamp.now(tz="UTC")
    arch = _archive(sym)
    sp = OUT / f"live_state_{sym}.json"
    if not sp.exists():
        return arch
    st = json.loads(sp.read_text())
    live = pd.DataFrame.from_dict(st.get("buckets", {}), orient="index")
    if live.empty:
        return arch
    live.index = pd.to_datetime(live.index, utc=True)
    arch_end = (arch.index.max() + pd.Timedelta(hours=4)) if len(arch) else live.index.min()
    live = live[(live.index >= arch_end) & (live.index + pd.Timedelta(hours=4) <= now)]
    return pd.concat([arch, live[arch.columns.intersection(live.columns)]]).sort_index()


def main():
    s = requests.Session()
    for sym in SYMS:
        print(update(sym, s), flush=True)


if __name__ == "__main__":
    main()
