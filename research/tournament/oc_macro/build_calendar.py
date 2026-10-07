"""oc_macro calendar builder: hard-coded official release dates -> UTC windows.

Reads NOTHING except the date lists below (fixed in PLAN.md). Writes
research/tournament/oc_macro/macro_calendar.csv with one row per release:
date, series, release_local_et, release_utc, window_start_utc,
window_end_utc (= start + 5h), source.

UTC rule (PLAN.md): 08:30 ET (CPI/NFP) / 14:00 ET (FOMC); EDT (UTC-4) iff
the date is in [2nd-Sunday-March, 1st-Sunday-November), else EST (UTC-5).
DST starts: 2021-03-14, 2022-03-13, 2023-03-12, 2024-03-10, 2025-03-09,
2026-03-08; ends: 2021-11-07, 2022-11-06, 2023-11-05, 2024-11-03,
2025-11-02, 2026-11-01.

  .venv/Scripts/python.exe research/tournament/oc_macro/build_calendar.py
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

OC = Path(__file__).resolve().parent

FOMC = [
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16",
    "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15",
    "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14",
    "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16",
]
CPI = [
    "2021-01-13", "2021-02-10", "2021-03-10", "2021-04-13",
    "2021-05-12", "2021-06-10", "2021-07-13", "2021-08-11",
    "2021-09-14", "2021-10-13", "2021-11-10", "2021-12-10",
    "2022-01-12", "2022-02-10", "2022-03-10", "2022-04-12",
    "2022-05-11", "2022-06-10", "2022-07-13", "2022-08-10",
    "2022-09-13", "2022-10-13", "2022-11-10", "2022-12-13",
    "2023-01-12", "2023-02-14", "2023-03-14", "2023-04-12",
    "2023-05-10", "2023-06-13", "2023-07-12", "2023-08-10",
    "2023-09-13", "2023-10-12", "2023-11-14", "2023-12-12",
    "2024-01-11", "2024-02-13", "2024-03-12", "2024-04-10",
    "2024-05-15", "2024-06-12", "2024-07-11", "2024-08-14",
    "2024-09-11", "2024-10-10", "2024-11-13", "2024-12-11",
    "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10",
    "2025-05-13", "2025-06-11", "2025-07-15", "2025-08-12",
    "2025-09-11", "2025-10-24", "2025-12-18",
    "2026-01-13", "2026-02-13", "2026-03-11", "2026-04-10",
    "2026-05-12", "2026-06-10", "2026-07-14", "2026-08-12",
    "2026-09-11",
]
NFP = [
    "2021-01-08", "2021-02-05", "2021-03-05", "2021-04-02",
    "2021-05-07", "2021-06-04", "2021-07-02", "2021-08-06",
    "2021-09-03", "2021-10-08", "2021-11-05", "2021-12-03",
    "2022-01-07", "2022-02-04", "2022-03-04", "2022-04-01",
    "2022-05-06", "2022-06-03", "2022-07-08", "2022-08-05",
    "2022-09-02", "2022-10-07", "2022-11-04", "2022-12-02",
    "2023-01-06", "2023-02-03", "2023-03-10", "2023-04-07",
    "2023-05-05", "2023-06-02", "2023-07-07", "2023-08-04",
    "2023-09-01", "2023-10-06", "2023-11-03", "2023-12-08",
    "2024-01-05", "2024-02-02", "2024-03-08", "2024-04-05",
    "2024-05-03", "2024-06-07", "2024-07-05", "2024-08-02",
    "2024-09-06", "2024-10-04", "2024-11-01", "2024-12-06",
    "2025-01-10", "2025-02-07", "2025-03-07", "2025-04-04",
    "2025-05-02", "2025-06-06", "2025-07-03", "2025-08-01",
    "2025-09-05", "2025-11-20", "2025-12-16",
    "2026-01-09", "2026-02-11", "2026-03-06", "2026-04-03",
    "2026-05-08", "2026-06-05", "2026-07-02", "2026-08-07",
    "2026-09-04",
]

DST_START = {2021: "2021-03-14", 2022: "2022-03-13", 2023: "2023-03-12",
             2024: "2024-03-10", 2025: "2025-03-09", 2026: "2026-03-08"}
DST_END = {2021: "2021-11-07", 2022: "2022-11-06", 2023: "2023-11-05",
           2024: "2024-11-03", 2025: "2025-11-02", 2026: "2026-11-01"}

SOURCES = {
    "FOMC": "federalreserve.gov/monetarypolicy/fomccalendars.htm (2nd meeting day; 14:00 ET)",
    "CPI": "bls.gov/schedule (CPI release schedule + yearly Selected Releases); Oct-2025 ref missing (shutdown)",
    "NFP": "bls.gov/schedule (Employment Situation schedule); Oct-2025 ref missing (shutdown); ALFRED rid 50 x-check",
}


def is_edt(d: str) -> bool:
    y = int(d[:4])
    return DST_START[y] <= d < DST_END[y]


def main() -> None:
    rows = []
    for d in FOMC:
        utc_h = 18 if is_edt(d) else 19
        r = pd.Timestamp(f"{d} {utc_h:02d}:00", tz="UTC")
        rows.append(("FOMC", d, "14:00", r))
    for d in CPI:
        utc_h, utc_m = (12, 30) if is_edt(d) else (13, 30)
        r = pd.Timestamp(f"{d} {utc_h:02d}:{utc_m:02d}", tz="UTC")
        rows.append(("CPI", d, "08:30", r))
    for d in NFP:
        utc_h, utc_m = (12, 30) if is_edt(d) else (13, 30)
        r = pd.Timestamp(f"{d} {utc_h:02d}:{utc_m:02d}", tz="UTC")
        rows.append(("NFP", d, "08:30", r))
    df = pd.DataFrame(rows, columns=["series", "date", "release_local_et", "release_utc"])
    df["window_start_utc"] = df["release_utc"]
    df["window_end_utc"] = df["release_utc"] + pd.Timedelta(hours=5)
    df["source"] = df["series"].map(SOURCES)
    df = df.sort_values(["release_utc", "series"]).reset_index(drop=True)
    cutoff = pd.Timestamp("2026-09-24", tz="UTC")
    assert (df["window_start_utc"] < cutoff).all(), "calendar must end before cutoff"
    assert len(df) == len(FOMC) + len(CPI) + len(NFP), "row count"
    assert len(df) == 46 + 68 + 68, f"expected 182 rows, got {len(df)}"
    df.to_csv(OC / "macro_calendar.csv", index=False)
    print(f"rows={len(df)} FOMC={len(FOMC)} CPI={len(CPI)} NFP={len(NFP)}")
    print(df.head(3).to_string(index=False))
    print(df.tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
