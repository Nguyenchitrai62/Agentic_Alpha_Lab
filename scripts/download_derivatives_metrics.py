"""Checksum-verified public BTC metrics archive; does not imply point-in-time availability."""
import torch
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import time
import zipfile
import numpy as np
import pandas as pd
import requests
from agentic_alpha_lab.data.training import sha256

FIELDS = ["sum_open_interest", "sum_open_interest_value", "count_toptrader_long_short_ratio",
          "sum_toptrader_long_short_ratio", "count_long_short_ratio", "sum_taker_long_short_vol_ratio"]


def parse_archive(payload, day):
    expected = f"BTCUSDT-metrics-{day}.csv"
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if archive.namelist() != [expected] or archive.getinfo(expected).file_size > 10_000_000:
            raise ValueError("Unexpected/oversized archive member")
        frame = pd.read_csv(io.BytesIO(archive.read(expected)))
    if list(frame.columns) != ["create_time", "symbol", *FIELDS] or len(frame) > 5000:
        raise ValueError("Unexpected metrics schema/size")
    if not frame.symbol.eq("BTCUSDT").all():
        raise ValueError("Wrong symbol")
    frame["create_time"] = pd.to_datetime(frame.create_time, utc=True, errors="raise")
    start = pd.Timestamp(day, tz="UTC")
    if frame.empty or not frame.create_time.between(start, start+pd.Timedelta(days=1), inclusive="left").all():
        raise ValueError("Event times outside named day")
    for field in FIELDS:
        frame[field] = pd.to_numeric(frame[field], errors="raise")
        nonmissing = frame[field].dropna().to_numpy()
        if not np.isfinite(nonmissing).all() or (nonmissing < 0).any():
            raise ValueError(f"Invalid metric: {field}")
    return frame


def get(url):
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=25)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            if len(response.content) > 10_000_000:
                raise ValueError("Oversized archive response")
            return response
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def fetch_day(day, output, source):
    name = f"BTCUSDT-metrics-{day}.zip"
    path = output / "raw" / name
    checksum = path.with_suffix(".zip.CHECKSUM")
    url = source + name
    if path.exists() and checksum.exists():
        payload, expected = path.read_bytes(), checksum.read_text().split()[0]
    else:
        response = get(url)
        if response is None:
            return {"day": day, "status": "missing_404", "url": url}, None
        check = get(url + ".CHECKSUM")
        if check is None:
            raise ValueError(f"Missing checksum: {day}")
        payload, expected = response.content, check.text.split()[0]
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError(f"Checksum mismatch: {day}")
        # Partial pairs are never trusted on resume; fresh verified responses replace them.
        path.write_bytes(payload)
        checksum.write_text(check.text)
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError(f"Stored checksum mismatch: {day}")
    frame = parse_archive(payload, day)
    return {"day": day, "status": "verified", "url": url, "sha256": expected, "rows": len(frame)}, frame


def run(a):
    plan = json.loads(a.plan.read_text())
    if plan["symbol"] != "BTCUSDT" or not plan["source"].startswith("https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/"):
        raise ValueError("Only the planned public BTC archive is supported")
    saved = a.output / "plan.json"
    if a.output.exists() and (not saved.exists() or json.loads(saved.read_text()) != plan):
        raise ValueError("Existing download has a different/missing plan")
    if (a.output / "manifest.json").exists():
        raise FileExistsError("Completed audit is immutable; use a new version")
    (a.output / "raw").mkdir(parents=True, exist_ok=True)
    saved.write_text(json.dumps(plan, indent=2))
    days = pd.date_range(plan["start"], plan["end_exclusive"], inclusive="left", freq="D").strftime("%Y-%m-%d").tolist()
    records, frames = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch_day, day, a.output, plan["source"]): day for day in days}
        for job in as_completed(jobs):
            record, frame = job.result()
            records.append(record)
            if frame is not None:
                frames.append(frame)
            if len(records) % 100 == 0 or len(records) == len(days):
                (a.output / "progress.json").write_text(json.dumps({"completed":len(records),"total":len(days),"missing":sum(r["status"]!="verified" for r in records)}))
                print((a.output / "progress.json").read_text(), flush=True)
    if not frames:
        raise ValueError("No data found")
    frame = pd.concat(frames, ignore_index=True).sort_values("create_time").reset_index(drop=True)
    frame.to_parquet(a.output / "metrics.parquet", index=False)
    (a.output / "files.json").write_text(json.dumps(sorted(records,key=lambda r:r["day"]),indent=2))
    delta = frame.create_time.diff().dropna()
    quality = {"rows":len(frame),"first":str(frame.create_time.min()),"last":str(frame.create_time.max()),
               "duplicate_timestamps":int(frame.create_time.duplicated().sum()),"gaps_over5m":int((delta>pd.Timedelta(minutes=5)).sum()),
               "max_gap_seconds":float(delta.max().total_seconds()),
               "nonnull_fraction_by_year":{str(year):part[FIELDS].notna().mean().to_dict() for year,part in frame.groupby(frame.create_time.dt.year)}}
    manifest = {"state":"complete_audit_only","plan_sha256":sha256(a.plan),"created_at":datetime.now(timezone.utc).isoformat(),
                "script_sha256":sha256(Path(__file__)),"expected_days":len(days),"missing_days":[r["day"] for r in records if r["status"]!="verified"],
                "quality":quality,"point_in_time_availability_verified":False,"feature_ready":False,
                "files":{name:sha256(a.output/name) for name in ("plan.json","files.json","metrics.parquet")}}
    (a.output / "manifest.json").write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2),flush=True)


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--plan",type=Path,default=Path("configs/btc_derivatives_data_plan.json"))
    p.add_argument("--output",type=Path,required=True)
    run(p.parse_args())
