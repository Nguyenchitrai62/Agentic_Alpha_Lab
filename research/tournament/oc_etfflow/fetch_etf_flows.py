"""oc_etfflow: fetch daily US spot BTC/ETH ETF net flows (Farside, one GET per page).

Source: https://farside.co.uk/btc/ and /eth/ were verified reachable (HTTP 200,
single GET each, probe d10 + PLAN checks). Those landing pages carry only the
recent ~15-row window, so the full 2024-01+ history is taken from the same
publisher's linked all-data pages (one GET each, same terms, no heavy scraping):
  BTC: https://farside.co.uk/bitcoin-etf-flow-all-data/
  ETH: https://farside.co.uk/ethereum-etf-flow-all-data/
Robots (2026-10-07): /robots.txt mentions only Twitterbot (Disallow: empty);
no crawl-delay; single GET per page with an identifying UA is respectful use.
Outputs (per assignment): data/raw/etf_flows_20261007/btc_etf_flows_daily.csv,
eth_etf_flows_daily.csv (date,total_net_flow_usd_m) + manifest.json.

  .venv/Scripts/python.exe research/tournament/oc_etfflow/fetch_etf_flows.py
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
OUT = ROOT / "data/raw/etf_flows_20261007"
TMP = HERE / "tmp"

BTC_URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
ETH_URL = "https://farside.co.uk/ethereum-etf-flow-all-data/"
LANDING = ["https://farside.co.uk/btc/", "https://farside.co.uk/eth/"]
UA = {"User-Agent": "AgenticAlphaLab-oc_etfflow/1.0 (research, single GET per page)"}

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def one_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        assert r.status == 200, (url, r.status)
        return r.read()


def parse_num(s: str) -> float:
    s = s.strip().replace(",", "").replace("*", "").replace("$", "")
    if s in ("", "-", "--", "–", "n/a", "N/A"):
        return 0.0
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1].strip()
    if s in ("", "-"):
        return 0.0
    v = float(s)
    return -v if neg else v


def parse_date(s: str) -> str:
    m = re.match(r"\s*(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s*", s)
    assert m, s
    d, mon, y = int(m.group(1)), MONTHS[m.group(2).title()], int(m.group(3))
    return f"{y:04d}-{mon:02d}-{d:02d}"


def parse_table(html: str) -> list[tuple[str, float]]:
    trs = re.findall(r"<tr.*?</tr>", html, flags=re.S | re.I)
    rows: list[tuple[str, float]] = []
    for t in trs:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", t, flags=re.S | re.I)
        clean = [re.sub(r"<[^>]+>", "", c).replace("&nbsp;", " ").strip()
                 for c in cells]
        if not clean:
            continue
        if not re.match(r"\d{1,2} \w{3} \d{4}", clean[0].strip()):
            continue  # header / Fee / Seed rows
        date = parse_date(clean[0])
        total = parse_num(clean[-1])
        rows.append((date, total))
    # dedupe + sort (publisher table is newest-first or oldest-first; normalize)
    seen: dict[str, float] = {}
    for d, v in rows:
        seen[d] = v  # last wins on duplicate day
    return sorted(seen.items())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    fetch_time = datetime.now(timezone.utc).isoformat()
    # Reachability check of the landing pages (header only, no parse/store).
    landing_status = {}
    for u in LANDING:
        try:
            raw = one_get(u)
            landing_status[u] = {"http": 200, "bytes": len(raw)}
        except Exception as e:  # noqa: BLE001 - record, fall through to all-data
            landing_status[u] = {"http": None, "error": f"{type(e).__name__}: {e}"}
    pages = {}
    for name, url in (("btc", BTC_URL), ("eth", ETH_URL)):
        raw = one_get(url)
        (TMP / f"{name}_alldata.html").write_bytes(raw)
        html = raw.decode("utf-8", "replace")
        rows = parse_table(html)
        assert len(rows) > 500, (name, len(rows))
        pages[name] = (url, raw, rows)
    manifest = {"fetch_time_utc": fetch_time, "sources": {}, "landing_check": landing_status,
                "availability_rule": "flows for US trading day D known from D+1 08:00 UTC (conservative)",
                "robots_note": "farside.co.uk/robots.txt 2026-10-07: only Twitterbot listed (Disallow empty); one GET per page, identifying UA, no heavy scraping",
                "parser": "Total column (last cell) per dated row; (x)=negative; '-'=0; commas/* stripped; Fee/Seed/non-date rows excluded; dedupe by date, sorted ascending"}
    for name, (url, raw, rows) in pages.items():
        path = OUT / f"{name}_etf_flows_daily.csv"
        lines = ["date,total_net_flow_usd_m"] + [f"{d},{v:.1f}" for d, v in rows]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest["sources"][name] = {"url": url, "csv": path.name,
                                     "sha256": sha, "n_rows": len(rows),
                                     "span": [rows[0][0], rows[-1][0]],
                                     "page_bytes": len(raw),
                                     "page_sha256": hashlib.sha256(raw).hexdigest()}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps({k: {"n": v["n_rows"], "span": v["span"]} for k, v in manifest["sources"].items()}, indent=1))


if __name__ == "__main__":
    main()
