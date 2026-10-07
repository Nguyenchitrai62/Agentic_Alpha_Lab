"""oc_eventblk calendar builder: raw official pages -> event_calendar.csv.

Parses FOMC meeting ranges from the Fed pages (statement = 2nd meeting
day, 14:00 ET) and CPI release dates from the archived BLS schedule
pages (08:30 ET). Applies the PLAN.md DST rule (-> UTC), drops events
at/after 2026-09-24, cross-checks against the PLAN.md expected lists
(officials win; deviations logged to calendar_check.json).

Reads ONLY research/tournament/oc_eventblk/raw/* + manifest.json.
Writes event_calendar.csv + calendar_check.json. No market/outcome data.

  .venv/Scripts/python.exe research/tournament/oc_eventblk/build_calendar.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

OC = Path(__file__).resolve().parent
RAW = OC / "raw"
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")

FOMC_EXPECTED = [
    "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
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
CPI_EXPECTED = [
    "2020-08-12", "2020-09-11", "2020-10-13", "2020-11-12", "2020-12-10",
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

DST_START = {2020: "2020-03-08", 2021: "2021-03-14", 2022: "2022-03-13",
             2023: "2023-03-12", 2024: "2024-03-10", 2025: "2025-03-09",
             2026: "2026-03-08"}
DST_END = {2020: "2020-11-01", 2021: "2021-11-07", 2022: "2022-11-06",
           2023: "2023-11-05", 2024: "2024-11-03", 2025: "2025-11-02",
           2026: "2026-11-01"}

MONTHS = {"jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
          "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 6 + 1,
          "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
          "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12,
          "december": 12}


def is_edt(d: str) -> bool:
    y = int(d[:4])
    return DST_START[y] <= d < DST_END[y]


def clean(path: Path) -> str:
    b = path.read_bytes().decode("utf-8", "replace")
    txt = re.sub(r"<[^>]+>", " ", b)
    return re.sub(r"\s+", " ", txt)


def parse_fed(path: Path) -> set[str]:
    """Meeting ranges in 'YYYY FOMC Meetings' sections -> 2nd-day dates."""
    txt = clean(path)
    out: set[str] = set()
    for m in re.finditer(r"(20\d\d) FOMC Meetings", txt):
        year, start = m.group(1), m.end()
        nxt = txt.find("FOMC Meetings", start)
        seg = txt[start:] if nxt < 0 else txt[start:nxt]
        # ranges: 'January 27-28', 'March 17-18*', 'Apr/May 30-1', 'Jan/Feb 31-1';
        # the 2nd day is in month m2 when present ('Jan/Feb 31-1' -> Feb 1).
        # An explicit ', YYYY' (the archived page notes the Jan 2022 meeting
        # inside the 2021 section) overrides the section year.
        for r in re.finditer(
                r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
                r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
                r"Nov(?:ember)?|Dec(?:ember)?)"
                r"(?:/(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
                r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
                r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?))?"
                r"\s+(\d{1,2})-(\d{1,2})\*?(?:,\s*(20\d\d))?", seg):
            m1, m2, d1, d2, yexp = r.group(1), r.group(2), int(r.group(3)), int(r.group(4)), r.group(5)
            yy = int(yexp) if yexp else int(year)
            if m2:
                mm = MONTHS[m2.lower().rstrip(".")]
                if mm < MONTHS[m1.lower().rstrip(".")] and not yexp:
                    yy += 1  # Dec/Jan wrap with no explicit year
            else:
                mm = MONTHS[m1.lower().rstrip(".")]
            out.add(f"{yy:04d}-{mm:02d}-{d2:02d}")
    return out


def parse_cpi_schedule(path: Path) -> set[str]:
    """BLS 'Reference Month / Release Date' tables: 'Sep. 11, 2020'."""
    txt = clean(path)
    out: set[str] = set()
    for m in re.finditer(
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+"
            r"(\d{1,2}),\s+(20[12]\d)", txt):
        mon = MONTHS[m.group(1).lower().rstrip(".")]
        out.add(f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}")
    return out


def parse_selected(path: Path) -> set[str]:
    """BLS 'Schedule of Selected Releases': 'Consumer Price Index for
    November 2021 Friday, December 10, 2021'."""
    txt = clean(path)
    out: set[str] = set()
    for m in re.finditer(
            r"Consumer Price Index for [A-Z][a-z]+ 20\d\d\s+"
            r"[A-Z][a-z]+,?\s+([A-Z][a-z]+)\s+(\d{1,2}),\s+(20\d\d)", txt):
        mon = MONTHS[m.group(1).lower()]
        out.add(f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}")
    return out


def main() -> None:
    fomc: set[str] = set()
    for p in ["fed_fomccalendars.htm", "fed_fomccalendars_20201224.htm"]:
        fomc |= parse_fed(RAW / p)
    fomc = {d for d in fomc if "2020-01-01" <= d < "2027-01-01"}  # PLAN scope tail (pages list older/newer years too)
    cpi: set[str] = set()
    for p in sorted(RAW.glob("bls_cpi_*.htm")):
        cpi |= parse_cpi_schedule(p)
    for p in ["bls_2021_09_sched.htm", "bls_2021_11_sched.htm",
              "bls_2021_12_sched.htm", "bls_2021_home.htm"]:
        cpi |= parse_selected(RAW / p)

    check = {
        "fomc_extracted": sorted(fomc),
        "cpi_extracted": sorted(cpi),
        "fomc_missing_vs_plan": sorted(set(FOMC_EXPECTED) - fomc),
        "fomc_extra_vs_plan": sorted(fomc - set(FOMC_EXPECTED)),
        "cpi_missing_vs_plan": sorted(set(CPI_EXPECTED) - cpi),
        "cpi_extra_vs_plan": sorted(cpi - set(CPI_EXPECTED)),
    }
    # Officials win: union, then scope filter.
    fomc_u = sorted(d for d in (set(FOMC_EXPECTED) | fomc) if "2020-01-01" <= d < "2027-01-01")
    cpi_u = sorted(d for d in (set(CPI_EXPECTED) | cpi) if "2020-01-01" <= d < "2027-01-01")

    rows = []
    for d in fomc_u:
        hh = 18 if is_edt(d) else 19
        rows.append(("FOMC", d, "14:00", pd.Timestamp(f"{d} {hh:02d}:00", tz="UTC")))
    for d in cpi_u:
        hm = "12:30" if is_edt(d) else "13:30"
        rows.append(("CPI", d, "08:30", pd.Timestamp(f"{d} {hm}", tz="UTC")))
    df = pd.DataFrame(rows, columns=["series", "date", "release_local_et", "release_utc"])
    df = df.sort_values(["release_utc", "series"]).reset_index(drop=True)
    over = df[df["release_utc"] >= CUTOFF]
    check["dropped_at_after_cutoff"] = over[["series", "date"]].values.tolist()
    df = df[df["release_utc"] < CUTOFF].reset_index(drop=True)
    df["source"] = df["series"].map({
        "FOMC": "federalreserve.gov fomccalendars (live 2026-10-05 + archived 2020-12-24)",
        "CPI": "BLS CPI release schedule (archived snapshots 2020-02..2026-02 + 2021 selected-releases pages)",
    })
    df.to_csv(OC / "event_calendar.csv", index=False)
    check["n_fomc"] = int((df["series"] == "FOMC").sum())
    check["n_cpi"] = int((df["series"] == "CPI").sum())
    (OC / "calendar_check.json").write_text(json.dumps(check, indent=1))
    print(f"FOMC={check['n_fomc']} CPI={check['n_cpi']} rows={len(df)}")
    print("missing vs plan:", check["fomc_missing_vs_plan"], check["cpi_missing_vs_plan"])
    print("extra vs plan:", check["fomc_extra_vs_plan"], check["cpi_extra_vs_plan"])
    print("dropped:", check["dropped_at_after_cutoff"])


if __name__ == "__main__":
    main()
