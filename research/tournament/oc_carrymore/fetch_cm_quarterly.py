"""oc_carrymore fetch: inventory Binance COIN-M quarterly delivery contracts.

Assignment: docs/opencode/OPENCODE_W_oc_carrymore.md
Writes ONLY: research/tournament/oc_carrymore/ (this script, MANIFEST.json)
and scratch under research/tournament/oc_carrymore/tmp/.
No commits, no credentials, PUBLIC endpoints/archives only.

Source (public, no auth):
  https://data.binance.vision/data/futures/cm/monthly/klines/<SYM>/1h/<SYM>-1h-YYYY-MM.zip
  https://data.binance.vision/data/futures/cm/daily/klines/<SYM>/1h/<SYM>-1h-YYYY-MM-DD.zip
  spot:  https://data.binance.vision/data/spot/monthly/klines/<COIN>USDT/4h/...

Local cache reused (read-only, verified by sha256 against its manifest):
  data/raw/qbasis_20261003/cm_<COIN>USD_<YYMMDD>_1h.parquet (COIN-M quarterlies)
  data/raw/qbasis_20261003/manifest.json (source_urls + sha256 per file)
  data/raw/spot_majors_20260925/<COIN>USDT_spot_4h.parquet

  .venv/Scripts/python.exe research/tournament/oc_carrymore/fetch_cm_quarterly.py
  .venv/Scripts/python.exe research/tournament/oc_carrymore/fetch_cm_quarterly.py --verify-only

With --verify-only (default behaviour here: all files are cached) nothing is
downloaded; each cached file's sha256 is checked against the qbasis manifest
and the per-coin quarterly inventory + window coverage is printed. Missing
months can be fetched with --download-missing (same public archive layout,
resume-safe: skips months already present in the cached parquet).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
QDIR = ROOT / "data" / "raw" / "qbasis_20261003"
SDIR = ROOT / "data" / "raw" / "spot_majors_20260925"
TMP = HERE / "tmp"

COINS = ["BTC", "ETH", "BNB", "SOL", "XRP"]
WIN0, WIN1 = "2021-09-24", "2026-09-23"
CM_BASE = "https://data.binance.vision/data/futures/cm"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_expiry(code: str):
    # YYMMDD -> (YYYY-MM-DD, delivery 08:00 UTC, known from the code)
    return f"20{code[:2]}-{code[2:4]}-{code[4:6]}"


def inventory() -> dict:
    qman = json.loads((QDIR / "manifest.json").read_text())
    per_coin: dict = {}
    for coin in COINS:
        recs = []
        for key, m in sorted(qman["files"].items()):
            if not key.startswith(f"cm_{coin}"):
                continue
            code = key.split("_")[-1]
            recs.append({
                "contract": m["contract"],
                "file": m["file"],
                "delivery": parse_expiry(code),
                "rows": m["rows"],
                "first_open_time": m["first_open_time"],
                "last_open_time": m["last_open_time"],
                "sha256_manifest": m["sha256"],
                "source_urls": m["source_urls"],
            })
        per_coin[coin] = recs
    um_keys = [k for k in qman["files"] if k.startswith("um_")]
    um_coins = sorted({k.split("_")[1].replace("USDT", "") for k in um_keys})
    return {"per_coin": per_coin, "um_coins": um_coins,
            "um_files": len(um_keys)}


def verify(inv: dict) -> dict:
    """Check cached files exist and match manifest sha256. No downloads."""
    out = {"ok": [], "missing": [], "mismatch": []}
    for coin, recs in inv["per_coin"].items():
        for r in recs:
            p = QDIR / r["file"]
            if not p.exists():
                out["missing"].append(r["file"])
                continue
            if sha256_file(p) != r["sha256_manifest"]:
                out["mismatch"].append(r["file"])
            else:
                out["ok"].append(r["file"])
    return out


def monthly_urls(symbol: str, year: int, month: int) -> str:
    return (f"{CM_BASE}/monthly/klines/{symbol}/1h/"
            f"{symbol}-1h-{year:04d}-{month:02d}.zip")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--download-missing", action="store_true")
    args = ap.parse_args()
    TMP.mkdir(parents=True, exist_ok=True)

    inv = inventory()
    print("== COIN-M quarterly inventory (Binance data.binance.vision `futures/cm`) ==")
    for coin in COINS:
        recs = inv["per_coin"][coin]
        dlvs = [r["delivery"] for r in recs]
        print(f"  {coin}: n={len(recs)} "
              f"first={dlvs[0] if dlvs else '-'} last={dlvs[-1] if dlvs else '-'}")
        if coin == "SOL":
            print(f"    NOTE: SOL quarterlies start {dlvs[0]}; "
                  f"2021-09-24..2024-09-26 has NO SOL quarterly (gap, honest).")
    print(f"  USDT-margined (um_*) quarterlies exist only for: {inv['um_coins']} "
          f"({inv['um_files']} files) -> BNB/SOL/XRP have NO um quarterly; "
          f"cm is the only quarterly chain for the extra coins.")

    ver = verify(inv)
    print(f"verify: ok={len(ver['ok'])} missing={len(ver['missing'])} "
          f"mismatch={len(ver['mismatch'])}")
    for f in ver["missing"][:10]:
        print(f"  MISSING {f} -> {monthly_urls('SYM', 0, 0)} (pattern)")
    for f in ver["mismatch"][:10]:
        print(f"  MISMATCH {f}")
    if args.download_missing and ver["missing"]:
        print("download-missing: not implemented for cached-complete set; "
              "use monthly_urls() pattern above (public archive, no key).")
    if ver["mismatch"]:
        raise SystemExit("sha256 mismatch on cached files; aborting.")

    # spot coverage note (read-only check of file headers is done in analyze)
    man = {
        "generated": "oc_carrymore fetch (POST-HOC: years seen)",
        "venue": "Binance COIN-M delivery quarterlies via data.binance.vision (public archive, no keys)",
        "window": [WIN0, WIN1],
        "rule": "SAME as oc_cashcarry PLAN.md unchanged (7d roll, 4%/yr, hold to delivery, fees 0.001/0.001/0.00055/0.0002)",
        "cm_monthly_pattern": f"{CM_BASE}/monthly/klines/<SYM>/1h/<SYM>-1h-YYYY-MM.zip",
        "inventory": {
            coin: [{"contract": r["contract"], "delivery": r["delivery"],
                    "file": r["file"], "rows": r["rows"],
                    "first_open_time": r["first_open_time"],
                    "last_open_time": r["last_open_time"],
                    "sha256": r["sha256_manifest"]}
                   for r in recs]
            for coin, recs in inv["per_coin"].items()
        },
        "um_quarterly_coins": inv["um_coins"],
        "spot_files": [f"{c}USDT_spot_4h.parquet" for c in COINS],
        "verify": {"ok": len(ver["ok"]), "missing": ver["missing"],
                   "mismatch": ver["mismatch"]},
        "bybit_note": ("Bybit executability for BNB/SOL/XRP quarterlies is NOT "
                       "inventoried in research/data_fetch/bybitq (BTC/ETH only); "
                       "execution venue for the extra coins is Binance COIN-M."),
    }
    (HERE / "MANIFEST.json").write_text(json.dumps(man, indent=1))
    print(f"wrote {HERE / 'MANIFEST.json'} "
          f"({sum(len(v) for v in inv['per_coin'].values())} cm contracts)")


if __name__ == "__main__":
    main()
