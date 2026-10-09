"""oc_presampleg2 Part A: read-only availability probes (no outcomes computed).

Reads ONLY metadata / timestamp ranges of the frozen data stores + member caches.
Writes research/tournament/oc_presampleg2/tmp/probe.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
TMP = HERE / "tmp"
TMP.mkdir(exist_ok=True)

SPAN_S = pd.Timestamp("2018-01-01", tz="UTC")
SPAN_E = pd.Timestamp("2020-09-30", tz="UTC")


def _tz(t):
    t = pd.Timestamp(t)
    return t.tz_convert("UTC") if t.tzinfo is not None else t.tz_localize("UTC")


def span_cover(first, last) -> float:
    if first is None or last is None or pd.isna(first) or pd.isna(last):
        return 0.0
    lo = max(_tz(first), SPAN_S)
    hi = min(_tz(last), SPAN_E)
    total = (SPAN_E - SPAN_S).total_seconds()
    return round(max(0.0, (hi - lo).total_seconds()) / total, 4)


def idx_range(path: Path, idx_col=None):
    """First/last timestamps of a parquet's row index (reads one column only)."""
    try:
        if idx_col:
            col = pd.read_parquet(path, columns=[idx_col])[idx_col]
            t = pd.to_datetime(col, utc=True)
        else:
            pf = pd.read_parquet(path, columns=[])
            t = pd.to_datetime(pf.index, utc=True)
        return str(t.min()), str(t.max()), int(len(t))
    except Exception as e:  # noqa: BLE001 - probe must not crash on one store
        return None, None, f"ERR {type(e).__name__}: {e}"


def main():
    out = {"span": [str(SPAN_S), str(SPAN_E)], "stores": {}}
    S = out["stores"]

    # 1. PERP order-level flow (A/Aq defining input)
    for s in ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]:
        p = ROOT / f"data/raw/aggflow_20260928_orders/{s}_flow_4h.parquet"
        first, last, n = idx_range(p) if p.exists() else (None, None, "MISSING")
        S[f"perp_orders_{s}"] = {"first": first, "last": last, "n": n,
                                 "span_cover": span_cover(first, last)}

    # 2. SPOT order-level flow (context: the allowed-like-for-like venue)
    for s in ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]:
        p = ROOT / f"data/raw/aggflow_spot_20260929_orders/{s}_flow_4h.parquet"
        first, last, n = idx_range(p) if p.exists() else (None, None, "MISSING")
        S[f"spot_orders_{s}"] = {"first": first, "last": last, "n": n,
                                 "span_cover": span_cover(first, last)}

    # 3. Deribit options (B/Bq defining input)
    for coin in ["BTC", "ETH"]:
        p = ROOT / f"data/raw/deribit_opt_20260926/{coin}_options_4h.parquet"
        if p.exists():
            bar = pd.read_parquet(p, columns=["bar"])["bar"]
            t = pd.to_datetime(bar, utc=True)
            first, last, n = str(t.min()), str(t.max()), int(len(t))
        else:
            first, last, n = None, None, "MISSING"
        S[f"deribit_opt_{coin}"] = {"first": first, "last": last, "n": n,
                                    "span_cover": span_cover(first, last)}

    # 4. Coinbase 1h (D/Dq defining input)
    for prod in ["BTC-USD", "ETH-USD"]:
        rows = []
        for suffix in ["_1h_pre2017.parquet", "_1h.parquet"]:
            p = ROOT / f"data/raw/coinbase_20260925/{prod}{suffix}"
            if p.exists():
                t = pd.to_datetime(pd.read_parquet(p, columns=["open_time"])["open_time"], utc=True)
                rows.append((str(t.min()), str(t.max()), int(len(t))))
        S[f"coinbase_{prod}"] = rows

    # 5. Perp 4h price + funding (v92 base panel)
    p = ROOT / "data/raw/ma_ribbon_20260924/klines_4h.parquet"
    first, last, n = idx_range(p, "open_time")
    S["perp_4h_BTC"] = {"first": first, "last": last, "n": n, "span_cover": span_cover(first, last)}
    p = ROOT / "data/raw/ma_ribbon_20260924/funding.parquet"
    first, last, n = idx_range(p, "fundingTime")
    S["perp_funding_BTC"] = {"first": first, "last": last, "n": n}
    for s in ["ETHUSDT", "BNBUSDT", "XRPUSDT"]:
        p = ROOT / f"data/raw/xs_universe_20260924/{s}_4h.parquet"
        first, last, n = idx_range(p, "open_time") if p.exists() else (None, None, "MISSING")
        S[f"perp_4h_{s}"] = {"first": first, "last": last, "n": n, "span_cover": span_cover(first, last)}
        p = ROOT / f"data/raw/xs_universe_20260924/{s}_funding.parquet"
        first, last, n = idx_range(p, "fundingTime") if p.exists() else (None, None, "MISSING")
        S[f"perp_funding_{s}"] = {"first": first, "last": last, "n": n}

    # 6. Spot 2017-prefix 4h (has taker-buy columns?) + reference spot_4h
    for s in ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]:
        p = ROOT / f"data/raw/spot_majors_20260925/{s}_spot_4h_2017.parquet"
        if p.exists():
            df = pd.read_parquet(p, columns=["open_time", "taker_buy_quote_volume"])
            t = pd.to_datetime(df["open_time"], utc=True)
            S[f"spot2017_4h_{s}"] = {"first": str(t.min()), "last": str(t.max()), "n": int(len(t)),
                                     "has_taker_buy": True,
                                     "span_cover": span_cover(t.min(), t.max())}
        else:
            S[f"spot2017_4h_{s}"] = {"n": "MISSING"}
    p = ROOT / "data/raw/spot_majors_20260925/BTCUSDT_spot_4h.parquet"
    first, last, n = idx_range(p, "open_time") if p.exists() else (None, None, "MISSING")
    S["spot_4h_BTC_ref"] = {"first": first, "last": last, "n": n}

    # 7. Presample spot 1m store manifest (execution data for Part B engine)
    m = ROOT / "data/raw/spot_1m_presample_20261007/manifest.json"
    S["presample_1m_manifest"] = json.loads(m.read_text()) if m.exists() else "MISSING-manifest"

    # 8. Cached deployed member predictions (do any exist pre-2021?)
    C = ROOT / "artifacts/research/engine_real"
    for f in ["members_v154.parquet", "members_quarterly.parquet", "members_quarterly_D.parquet",
              "member_A_O1_orders.parquet", "member_Aq_O1_orders.parquet",
              "member_B_tv.parquet", "member_Bq_tv.parquet"]:
        p = C / f
        first, last, n = idx_range(p) if p.exists() else (None, None, "MISSING")
        S[f"member_{f}"] = {"first": first, "last": last, "n": n}

    (TMP / "probe.json").write_text(json.dumps(out, indent=1, default=str))
    for k, v in S.items():
        print(k, json.dumps(v, default=str)[:220], flush=True)


if __name__ == "__main__":
    main()
