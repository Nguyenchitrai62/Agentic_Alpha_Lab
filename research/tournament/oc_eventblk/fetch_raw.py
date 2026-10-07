"""oc_eventblk raw-page fetcher: official FOMC calendars (live Fed page +
archived Dec-2020 snapshot for the 2020 tail) + BLS CPI schedule
(archived official pages).

Direct BLS fetch returns 403 from this network and web.archive.org
replay returns 429, so BLS bytes come from arquivo.pt replays of the
same official URLs (manifest records the replay URL + archive
timestamp; pages carry the archive wrapper). No market/outcome data.

Writes research/tournament/oc_eventblk/raw/* + manifest.json
{file, url, fetched_at_utc, sha256, bytes}.

  .venv/Scripts/python.exe research/tournament/oc_eventblk/fetch_raw.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
import urllib.request
from pathlib import Path

OC = Path(__file__).resolve().parent
RAW = OC / "raw"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
SLEEP = 6

JOBS: list[tuple[str, str]] = [
    ("fed_fomccalendars.htm", "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"),
    ("fed_fomccalendars_20201224.htm",
     "https://arquivo.pt/noFrame/replay/20201224210448/https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"),
]
_BLS = "https://www.bls.gov/schedule/news_release/cpi.htm"
for _ts in ["20200224120225", "20220417220753", "20220705152805",
            "20230327012628", "20231020102602", "20240805042856",
            "20251113110217", "20260214025302"]:
    JOBS.append((f"bls_cpi_{_ts}.htm",
                 f"https://arquivo.pt/noFrame/replay/{_ts}/{_BLS}"))
for _name, _ts, _url in [
        ("bls_2021_09_sched.htm", "20210909163036", "https://www.bls.gov/schedule/2021/09_sched.htm"),
        ("bls_2021_11_sched.htm", "20211105234210", "https://www.bls.gov/schedule/2021/11_sched.htm"),
        ("bls_2021_12_sched.htm", "20211201223058", "https://www.bls.gov/schedule/2021/12_sched.htm"),
        ("bls_2021_home.htm", "20210909163700", "https://www.bls.gov/schedule/2021/home.htm")]:
    JOBS.append((_name, f"https://arquivo.pt/noFrame/replay/{_ts}/{_url}"))


def get(url: str, tries: int = 5) -> bytes:
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                if r.status != 200:
                    raise RuntimeError(f"HTTP {r.status}")
                return r.read()
        except Exception as e:  # noqa: BLE001 - retry then raise
            last = e
            time.sleep(20 * (i + 1))
    raise RuntimeError(f"fetch failed {url}: {last!r}")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for name, url in JOBS:
        blob = get(url)
        (RAW / name).write_bytes(blob)
        manifest.append({"file": f"raw/{name}", "url": url,
                         "fetched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                         "sha256": hashlib.sha256(blob).hexdigest(),
                         "bytes": len(blob)})
        print(name, len(blob), manifest[-1]["sha256"][:16], flush=True)
        time.sleep(SLEEP)
    (OC / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"saved {len(manifest)} files")


if __name__ == "__main__":
    main()
