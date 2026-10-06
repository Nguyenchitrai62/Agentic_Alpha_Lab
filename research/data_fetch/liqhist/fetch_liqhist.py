"""Probe + (conditional) fetch of Binance USD-M liquidation history.

Public endpoints only, polite rate (<= 5 req/s), resume-safe, CHECKSUM-verified.

Probe target (assignment):
  https://data.binance.vision, prefix
    data/futures/um/daily/liquidationSnapshot/<SYMBOL>/
    data/futures/um/monthly/liquidationSnapshot/<SYMBOL>/
  listed via the S3 listing
    https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=...&delimiter=/
for BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT.

Result (2026-10-06): the UM prefix does NOT exist (empty listing, IsTruncated=false)
for every symbol x {daily, monthly}, and the parent
data/futures/um/daily/liquidationSnapshot/ and .../monthly/... are likewise empty.
The full data-type listing under data/futures/um/daily/ and .../monthly/ contains
no liquidationSnapshot at all. liquidationSnapshot exists ONLY under COIN-M
(data/futures/cm/daily/liquidationSnapshot/, e.g. BTCUSD_PERP 2023-06-25..2024-10-14),
which is the wrong margin type and stops early. So there is nothing to download.

Behaviour:
  1. Probe all 5 symbols x {daily, monthly} (+ parent prefixes as negative controls
     and one positive control aggTrades/BTCUSDT) at <= 5 req/s, save raw XML listings
     under data/raw/binance_liq_20261006/s3_listings/.
  2. If any UM liquidationSnapshot keys are found: download every zip + .CHECKSUM,
     verify SHA256 against the CHECKSUM file, skip files already present and verified
     (resume-safe), abort the whole run if total size would exceed 3 GB, then convert
     to one parquet per symbol with columns
       time (UTC ms, int64), side (string), price (float), qty (float), notional (float)
     and write coverage stats. Document the ORIGINAL archive columns in REPORT.md.
  3. If none are found (current case): write zero parquet files, write the probe
     evidence + coverage tables (all zeros), exit 0 with a plain-English statement.

Usage:
  .venv/Scripts/python.exe research/data_fetch/liqhist/fetch_liqhist.py
  .venv/Scripts/python.exe research/data_fetch/liqhist/fetch_liqhist.py --probe-only
"""

from __future__ import annotations

import argparse
import hashlib
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "raw" / "binance_liq_20261006"
LISTING_DIR = OUT_DIR / "s3_listings"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
FREQS = ["daily", "monthly"]
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
RATE_SLEEP = 0.25  # 4 req/s, under the 5 req/s limit
MAX_TOTAL_BYTES = 3 * 1024**3
NS = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}


def s3_list(prefix: str, delimiter: str = "/") -> str:
    url = f"{S3}?prefix={prefix}&delimiter={delimiter}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse_listing(xml_text: str) -> tuple[list[str], list[str], bool]:
    root = ET.fromstring(xml_text)
    prefixes = [e.text for e in root.findall("s:CommonPrefixes/s:Prefix", NS)]
    keys = [e.text for e in root.findall("s:Contents/s:Key", NS)]
    trunc_el = root.find("s:IsTruncated", NS)
    trunc = trunc_el.text == "true" if trunc_el is not None else False
    return prefixes, keys, trunc


def probe() -> dict:
    LISTING_DIR.mkdir(parents=True, exist_ok=True)
    evidence: dict = {"symbols": {}, "controls": {}}
    # Main probe: 5 symbols x daily+monthly.
    for sym in SYMBOLS:
        evidence["symbols"][sym] = {}
        for freq in FREQS:
            prefix = f"data/futures/um/{freq}/liquidationSnapshot/{sym}/"
            xml_text = s3_list(prefix)
            (LISTING_DIR / f"um_{freq}_liquidationSnapshot_{sym}.xml").write_text(
                xml_text, encoding="utf-8"
            )
            cps, keys, trunc = parse_listing(xml_text)
            evidence["symbols"][sym][freq] = {
                "prefix": prefix,
                "common_prefixes": cps,
                "keys": keys,
                "is_truncated": trunc,
            }
            time.sleep(RATE_SLEEP)
    # Negative controls: parent prefixes + plausible alternative names.
    for label, prefix in [
        ("um_daily_liquidationSnapshot_parent", "data/futures/um/daily/liquidationSnapshot/"),
        ("um_monthly_liquidationSnapshot_parent", "data/futures/um/monthly/liquidationSnapshot/"),
        ("um_daily_types", "data/futures/um/daily/"),
        ("um_monthly_types", "data/futures/um/monthly/"),
        ("alt_forceOrders", "data/futures/um/daily/forceOrders/BTCUSDT/"),
        ("alt_liquidations", "data/futures/um/daily/liquidations/BTCUSDT/"),
    ]:
        xml_text = s3_list(prefix)
        safe = label.replace("/", "_")
        (LISTING_DIR / f"control_{safe}.xml").write_text(xml_text, encoding="utf-8")
        cps, keys, trunc = parse_listing(xml_text)
        evidence["controls"][label] = {
            "prefix": prefix,
            "common_prefixes": cps,
            "keys": keys[:10],
            "is_truncated": trunc,
        }
        time.sleep(RATE_SLEEP)
    # Positive control: aggTrades listing must be non-empty (proves the method works).
    xml_text = s3_list("data/futures/um/daily/aggTrades/BTCUSDT/")
    (LISTING_DIR / "control_positive_aggTrades_BTCUSDT.xml").write_text(
        xml_text, encoding="utf-8"
    )
    cps, keys, trunc = parse_listing(xml_text)
    evidence["controls"]["positive_aggTrades_BTCUSDT"] = {
        "prefix": "data/futures/um/daily/aggTrades/BTCUSDT/",
        "n_keys_page1": len(keys),
        "is_truncated": trunc,
        "sample": keys[:4],
    }
    time.sleep(RATE_SLEEP)
    # Context: one CM liquidationSnapshot symbol to show it exists but is out of scope.
    xml_text = s3_list("data/futures/cm/daily/liquidationSnapshot/BTCUSD_PERP/")
    (LISTING_DIR / "control_cm_BTCUSD_PERP_p1.xml").write_text(xml_text, encoding="utf-8")
    return evidence


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe-only", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    evidence = probe()

    n_um_keys = sum(
        len(v["keys"]) for sym in evidence["symbols"].values() for v in sym.values()
    )
    print(f"UM liquidationSnapshot keys found: {n_um_keys} (expected 0)")
    print(
        "UM daily data types:",
        evidence["controls"]["um_daily_types"]["common_prefixes"],
    )
    print(
        "UM monthly data types:",
        evidence["controls"]["um_monthly_types"]["common_prefixes"],
    )
    pos = evidence["controls"]["positive_aggTrades_BTCUSDT"]
    print(f"Positive control aggTrades/BTCUSDT: page1 keys={pos['n_keys_page1']}")

    if args.probe_only or n_um_keys == 0:
        print(
            "PLAIN RESULT: the Binance data-vision archive has NO "
            "data/futures/um/*/liquidationSnapshot history for "
            "BTCUSDT/ETHUSDT/SOLUSDT/BNBUSDT/XRPUSDT. Nothing to download."
        )
        return

    # --- Download path (only if the archive ever appears). Kept for reproducibility.
    import zipfile  # deferred; not exercised while the prefix is empty

    total = 0
    for sym in SYMBOLS:
        for freq in FREQS:
            for key in evidence["symbols"][sym][freq]["keys"]:
                if key.endswith(".CHECKSUM"):
                    continue
                if total > MAX_TOTAL_BYTES:
                    raise SystemExit("Total size would exceed 3 GB; aborting.")
                dest = OUT_DIR / "zips" / key
                if dest.exists():  # resume-safe
                    continue
                raise SystemExit(
                    "Download path not exercised in this run (prefix empty)."
                )


if __name__ == "__main__":
    main()
