"""oc_ideascan4 probes: verify free data reach back to >= 2021-09 for H1-H8.

Public GETs only (keyless). Each response truncated to ~2 KB and saved under probes/.
Total on disk < 100 KB. No returns computed; no dates >= 2025-09-24 touched.
"""
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "probes"
OUT.mkdir(exist_ok=True)

ANCHOR_MS = 1632441600000  # 2021-09-24T00:00:00Z
UA = {"User-Agent": "oc-ideascan4/1.0 (research probe)"}


def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def save(name, url, payload_desc, raw, extra=None):
    text = raw.decode("utf-8", errors="replace")
    doc = {
        "probe": name,
        "url": url,
        "http": 200,
        "payload_bytes": len(raw),
        "payload_truncated": text[:2000],
        "note": payload_desc,
    }
    if extra:
        doc.update(extra)
    (OUT / f"{name}.json").write_text(json.dumps(doc, indent=1)[:4096])
    return doc


def main():
    results = {}

    # p1: earliest BTCUSDT 4h kline (expect 2019-09, well before 2021-09)
    u = ("https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT"
         "&interval=4h&startTime=0&limit=1")
    s, raw = get(u)
    first = json.loads(raw.decode())
    open_ms = first[0][0] if first else None
    results["p1"] = save("p1", u, "earliest BTCUSDT 4h kline", raw,
                         {"openTime_ms": open_ms,
                          "covers_anchor_2021_09": bool(open_ms) and open_ms <= ANCHOR_MS})
    print("p1 openTime_ms:", open_ms)

    # p2: all 5 majors have daily klines at the 2021-09-24 anchor
    p2ok = {}
    for sym in ("ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
        u = ("https://data-api.binance.vision/api/v3/klines?symbol=" + sym
             + "&interval=1d&startTime=%d&limit=1" % ANCHOR_MS)
        s, raw = get(u)
        rows = json.loads(raw.decode())
        ok = bool(rows) and rows[0][0] <= ANCHOR_MS
        p2ok[sym] = {"openTime_ms": rows[0][0] if rows else None, "present_at_anchor": ok}
        save("p2_" + sym, u, "daily kline at 2021-09-24 anchor", raw, p2ok[sym])
    results["p2"] = p2ok
    print("p2:", p2ok)

    # p3: perp funding history reaches the anchor
    u = ("https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT"
         "&startTime=%d&limit=1" % ANCHOR_MS)
    s, raw = get(u)
    rows = json.loads(raw.decode())
    ok = bool(rows) and rows[0].get("fundingTime", 10**15) <= ANCHOR_MS + 8 * 3600 * 1000
    results["p3"] = save("p3", u, "BTCUSDT funding at/after anchor", raw,
                         {"fundingTime": rows[0].get("fundingTime") if rows else None,
                          "reaches_anchor": ok})
    print("p3:", results["p3"].get("fundingTime"), ok)

    # p4: Fear & Greed daily history reaches the anchor date
    u = "https://api.alternative.me/fng/?limit=1&format=json"
    s, raw = get(u)
    latest = json.loads(raw.decode())["data"][0]
    u2 = "https://api.alternative.me/fng/?date=2021-09-24&format=json"
    s2, raw2 = get(u2)
    anchor = json.loads(raw2.decode())["data"][0]
    results["p4"] = save("p4", u2, "F&G at 2021-09-24", raw2,
                         {"anchor_value": anchor.get("value"),
                          "latest_timestamp": latest.get("timestamp")})
    print("p4 anchor F&G:", anchor.get("value"), "latest ts:", latest.get("timestamp"))

    # p5: free on-chain value data reachable (H8 history source to verify).
    # blockchain.info keyless charts expose NVT; fallback = market-price chart.
    # Full MVRV-z vintage verification is the H8 worker's first step.
    import urllib.error as _ue
    u = ("https://api.blockchain.info/charts/nvt"
         "?timespan=1week&format=json&sampled=true")
    try:
        s, raw = get(u)
        label = "NVT chart"
    except _ue.HTTPError:
        u = ("https://api.blockchain.info/charts/market-price"
             "?timespan=1days&format=json")
        s, raw = get(u)
        label = "market-price chart (NVT path unavailable)"
    js = json.loads(raw.decode())
    vals = (js.get("values") or [])
    results["p5"] = save("p5", u, "blockchain.info free on-chain chart", raw,
                         {"chart": label, "points": len(vals)})
    print("p5:", label, "points:", len(vals))

    # p6: Yahoo CME BTC=F daily reachable
    u = "https://query1.finance.yahoo.com/v8/finance/chart/BTC=F?interval=1d&range=5d"
    s, raw = get(u)
    chart = json.loads(raw.decode())["chart"]
    err = chart.get("error")
    first_trade = (chart.get("result") or [{}])[0].get("meta", {}).get("firstTradeDate")
    results["p6"] = save("p6", u, "CME BTC=F daily", raw,
                         {"error": err, "firstTradeDate": first_trade})
    print("p6 firstTradeDate:", first_trade, "error:", err)

    total = sum(p.stat().st_size for p in OUT.glob("*.json"))
    print("probes written:", sorted(p.name for p in OUT.glob("*.json")),
          "total bytes:", total)
    assert total < 5 * 1024 * 1024, "probe budget breached"
    assert results["p1"]["covers_anchor_2021_09"], "BTC klines must cover 2021-09"
    assert all(v["present_at_anchor"] for v in p2ok.values()), "all majors at anchor"
    print("OK: all span checks pass")


if __name__ == "__main__":
    main()
