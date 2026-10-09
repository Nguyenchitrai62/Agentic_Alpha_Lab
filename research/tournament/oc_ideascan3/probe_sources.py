"""oc_ideascan3: verify free public endpoints for NEW data candidates (scan only, no backtests).

Each probe = one small public GET (Hyperliquid: POST, its API is POST-only),
no auth, no paid APIs, responses truncated to ~3 KB and saved under probes/.
Total output << 5 MB. Run: .venv/Scripts/python.exe research/tournament/oc_ideascan3/probe_sources.py
"""
import json
import os
import urllib.request

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probes")
os.makedirs(OUT, exist_ok=True)

UA = {"User-Agent": "AgenticAlphaLab-research-probe/1.0 (public-endpoint check, single small GET)"}


def fetch(name, url, method="GET", payload=None, timeout=25, keep=3000):
    req = urllib.request.Request(url, method=method, headers=UA)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
            raw = r.read(6000)
            body = raw[:keep].decode("utf-8", "replace")
            rec = {"name": name, "url": url, "method": method,
                   "http": r.status, "bytes_total": len(raw),
                   "head": body}
    except Exception as e:  # noqa: BLE001 - probe must record failures, not crash
        rec = {"name": name, "url": url, "method": method,
               "http": None, "error": f"{type(e).__name__}: {e}", "head": ""}
    with open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    print(f"{name}: http={rec.get('http')} err={rec.get('error', '')[:100]} bytes={rec.get('bytes_total', 0)}")
    return rec


if __name__ == "__main__":
    # D1 Deribit per-strike instrument universe (options history starts here)
    fetch("d1_deribit_instruments",
          "https://www.deribit.com/api/v2/public/get_instruments?currency=BTC&kind=option&expired=true")
    # D2 Deribit block (RFQ) trades — institutional prints, not in deribit_opt_20260926 aggregates
    fetch("d2_deribit_blocktrades",
          "https://www.deribit.com/api/v2/public/get_last_block_trades_by_currency?currency=BTC&count=5")
    # D3 Bybit options instrument list (bybit_20260925 holds perp funding only)
    fetch("d3_bybit_opt_instruments",
          "https://api.bybit.com/v5/market/instruments-info?category=option&baseCoin=BTC&limit=10")
    # D4 Bybit options public recent trades (symbol harvested from D3 at runtime; fallback BTC-31OCT25-110000-C)
    sym = "BTC-31OCT25-110000-C"
    try:
        with open(os.path.join(OUT, "d3_bybit_opt_instruments.json"), encoding="utf-8") as f:
            d3 = json.load(f)
        lst = d3.get("head", "")
        # crude symbol harvest from truncated head
        import re
        m = re.search(r'"symbol"\s*:\s*"([A-Z]+-[0-9A-Z]+-[0-9]+\-[CP])"', lst)
        if m:
            sym = m.group(1)
    except Exception:  # noqa: BLE001
        pass
    fetch("d4_bybit_opt_trades",
          f"https://api.bybit.com/v5/market/recent-trade?category=option&symbol={sym}&limit=5")
    # D5 Binance options (EAPI) universe — no EAPI data in data/raw
    fetch("d5_binance_eapi_exchangeinfo",
          "https://eapi.binance.com/eapi/v1/exchangeInfo")
    # D6/D7 Hyperliquid public archive (POST-only API): venue meta + BTC funding history sample
    fetch("d6_hyperliquid_meta", "https://api.hyperliquid.xyz/info",
          method="POST", payload={"type": "meta"})
    fetch("d7_hyperliquid_funding", "https://api.hyperliquid.xyz/info",
          method="POST", payload={"type": "fundingHistory", "coin": "BTC",
                                  "startTime": 1727740800000, "endTime": 1727827200000})
    # D8 Coinbase International perps (coinbase_20260925 = spot; this venue is absent)
    fetch("d8_coinbase_intl_instruments",
          "https://api.international.coinbase.com/api/v1/instruments")
    # D9 CME BTC futures daily settlements via Stooq free CSV (cftc_20260926 = positioning, not prices)
    fetch("d9_stooq_cme_btc", "https://stooq.com/q/d/l/?s=btc.f&i=d")
    # D10 Spot BTC ETF daily flows (Farside public page; no flow data in data/raw)
    fetch("d10_farside_etf_btc", "https://farside.co.uk/btc/")
    # D11 Stablecoin market caps via CoinGecko free tier (onchain has daily USDT/USDC cap;
    # this checks a live free API for supply + a mint/burn-event alternative path)
    fetch("d11_coingecko_stablecoins",
          "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=tether,usd-coin&per_page=2&page=1")
    # D12 Exchange status / maintenance calendar (Binance public system status)
    fetch("d12_binance_sysstatus", "https://api.binance.com/sapi/v1/system/status")
    # D13 OKX public liquidation orders (okxflow_* holds taker flow, not liquidations)
    fetch("d13_okx_liquidations",
          "https://www.okx.com/api/v5/public/liquidation-orders?instType=SWAP&uly=BTC-USDT&limit=1")
    # D14 Bitfinex liquidation history (bitfinex_20261004 holds margin 1h, not liquidations)
    fetch("d14_bitfinex_liquidations",
          "https://api-pub.bitfinex.com/v2/liquidations/hist/tBTCF0:USTF0?limit=2&sort=-1")
    # D15 GDELT news tone for bitcoin (newinfo_* holds Wikipedia only)
    fetch("d15_gdelt_btc",
          "https://api.gdeltproject.org/api/v2/doc/doc?query=bitcoin&mode=artlist&maxrecords=5&format=json")
    # D16 Google Trends explore (expected to need cookies/429 — documents non-viability)
    fetch("d16_gtrends_explore",
          "https://trends.google.com/trends/api/explore?hl=en-US&tz=0&req=%7B%22comparisonItem%22%3A%5B%7B%22keyword%22%3A%22bitcoin%22%2C%22geo%22%3A%22%22%2C%22time%22%3A%22today+12-m%22%7D%5D%2C%22category%22%3A0%2C%22property%22%3A%22%22%7D")
    print("done ->", OUT)
