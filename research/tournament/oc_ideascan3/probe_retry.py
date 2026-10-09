"""oc_ideascan3 retry pass: corrected endpoints for the first-pass failures + 3 extra candidates."""
import json
import os
import time
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
            rec = {"name": name, "url": url, "method": method, "http": r.status,
                   "bytes_total": len(raw), "head": raw[:keep].decode("utf-8", "replace")}
    except Exception as e:  # noqa: BLE001
        rec = {"name": name, "url": url, "method": method, "http": None,
               "error": f"{type(e).__name__}: {e}", "head": ""}
    with open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    print(f"{name}: http={rec.get('http')} err={rec.get('error', '')[:120]} bytes={rec.get('bytes_total', 0)}")
    return rec


if __name__ == "__main__":
    # Deribit: per-instrument public trade history (works for any listed strike) + block-trade retry
    fetch("d2b_deribit_trades_by_instr",
          "https://www.deribit.com/api/v2/public/get_last_trades_by_instrument?instrument_name=BTC-PERPETUAL&count=3")
    fetch("d2c_deribit_blocktrades_nocount",
          "https://www.deribit.com/api/v2/public/get_last_block_trades_by_currency?currency=BTC")
    # Bybit option recent trades with a live symbol harvested from the verified D3 probe
    fetch("d4b_bybit_opt_trades_live",
          "https://api.bybit.com/v5/market/recent-trade?category=option&symbol=BTC-25JUN27-106000-C-USDT&limit=3")
    # Bybit option delivery / settlement prices (for carry-style settlement verification)
    fetch("d18_bybit_delivery_price",
          "https://api.bybit.com/v5/market/delivery-price?category=option&baseCoin=BTC&limit=3")
    # OKX: instrument list (baseline) + liquidation-orders with alternate uly format
    fetch("d13b_okx_instruments",
          "https://www.okx.com/api/v5/public/instruments?instType=SWAP&uly=BTC-USDT")
    fetch("d13c_okx_liquidations_alt",
          "https://www.okx.com/api/v5/public/liquidation-orders?instType=SWAP&uly=BTC-USDT-SWAP&limit=1")
    # Bitfinex: ticker baseline (proves venue reachability) + liquidation retry with spot symbol
    fetch("d14b_bitfinex_ticker",
          "https://api-pub.bitfinex.com/v2/ticker/tBTCUSD")
    fetch("d14c_bitfinex_liq_spot",
          "https://api-pub.bitfinex.com/v2/liquidations/hist/tBTCUSD?limit=2&sort=-1")
    # GDELT retry once after a short backoff (first pass: HTTP 429)
    time.sleep(5)
    fetch("d15b_gdelt_retry",
          "https://api.gdeltproject.org/api/v2/doc/doc?query=bitcoin&mode=timelinevol&timespan=1week&format=json")
    # CME BTC front-month via Yahoo Finance chart API (free, no key) — Stooq is JS-blocked from this host
    fetch("d20_yahoo_cme_btc",
          "https://query1.finance.yahoo.com/v8/finance/chart/BTC=F?interval=1d&range=5d")
    # Hyperliquid venue-wide mids + funding + OI snapshot (one POST, all coins incl. majors)
    fetch("d17_hl_assetctxs", "https://api.hyperliquid.xyz/info",
          method="POST", payload={"type": "metaAndAssetCtxs"})
    # Binance insurance-fund: try the documented USDM endpoint path (may not exist — record honestly)
    fetch("d19a_binance_insurance_usdm",
          "https://fapi.binance.com/fapi/v1/insuranceFund?symbol=BTCUSDT")
    print("retry done ->", OUT)
