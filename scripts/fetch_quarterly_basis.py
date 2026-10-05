"""Quarterly-futures basis fetcher (public Binance archive only, no keys).

Downloads 1h klines of Binance USD-M delivery contracts (BTC/ETH quarterly,
e.g. BTCUSDT_210326) and COIN-M delivery contracts (BTC/ETH/BNB/XRP/SOL
quarterly, e.g. BTCUSD_210326) from https://data.binance.vision, then builds a
causal quarterly-basis feature table on the engine's 4h grid.

Contract calendar: the expiry of a YYMMDD suffix is 08:00 UTC on 20YY-MM-DD.
At each hour close C the FRONT contract is the nearest expiry with
E > C + 7 days (roll 7 days before expiry); NEXT is the following expiry.
Features use only bars that closed at or before C (merge_asof backward):

    qb_front = ln(F_front / perp) * 365 / days_to_expiry   (UM if available else CM)
    qb_slope = annualised next basis - annualised front basis (same venue)
    qb_chg24 = qb_front(C) - qb_front(C - 24h exact lag)

The 4h value is the last hourly value inside the bar (hourly C == 4h close).
NaN where no contract (or no NEXT leg for the slope) exists.

Perp reference is NOT re-downloaded: hourly closes come from the existing
local perp 1m stores (data/raw/majors_intraday_20260924,
data/raw/btc_intraday_20260924): the close of the last 1m bar of each hour.

Outputs (write scope only):
  data/raw/qbasis_20261003/<venue>_<contract>_1h.parquet  (open_time,open,high,low,close,volume)
  data/raw/qbasis_20261003/manifest.json                 (urls, sha256, rows, first/last + summary)
  artifacts/research/engine_real/qbasis_features_4h.parquet
    (open_time, close_time, sym, qb_front, qb_slope, qb_chg24, source)

  python scripts/fetch_quarterly_basis.py
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/qbasis_20261003"
FEAT_PATH = ROOT / "artifacts/research/engine_real/qbasis_features_4h.parquet"
BTC_1M_DIR = ROOT / "data/raw/btc_intraday_20260924"
MAJORS_1M_DIR = ROOT / "data/raw/majors_intraday_20260924"

BASE = "https://data.binance.vision/"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"

ROLL_DAYS = 7
EXPIRY_HOUR_UTC = 8

# coin -> perp symbol used as the spot/perp reference
PERP = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "BNB": "BNBUSDT",
        "XRP": "XRPUSDT", "SOL": "SOLUSDT"}
COINS = ("BTC", "ETH", "BNB", "XRP", "SOL")

KCOLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
         "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


# ---------------------------------------------------------------- calendar

def expiry_from_contract(contract: str) -> pd.Timestamp:
    """Expiry = 08:00 UTC on the 20YY-MM-DD date in the _YYMMDD suffix."""
    m = re.search(r"_(\d{6})$", contract)
    if not m:
        raise ValueError(f"no YYMMDD suffix in {contract!r}")
    yy, mm, dd = int(m.group(1)[:2]), int(m.group(1)[2:4]), int(m.group(1)[4:6])
    return pd.Timestamp(datetime(2000 + yy, mm, dd, EXPIRY_HOUR_UTC), tz="UTC")


def select_front_next(expiries, close_time, roll_days: float = ROLL_DAYS):
    """FRONT = nearest expiry with E > close_time + roll_days; NEXT = following.

    expiries: sorted iterable of tz-aware Timestamps. Returns (front, next)
    where each is a Timestamp or None.
    """
    exp = sorted(expiries)
    cutoff = pd.Timestamp(close_time) + pd.Timedelta(days=roll_days)
    front = next((e for e in exp if e > cutoff), None)
    nxt = None
    if front is not None:
        i = exp.index(front)
        nxt = exp[i + 1] if i + 1 < len(exp) else None
    return front, nxt


def annualised_basis(f_close: float, perp_close: float, close_time, expiry) -> float:
    """ln(F/P) * 365 / days_to_expiry; NaN on missing/non-positive input."""
    try:
        f = float(f_close)
        p = float(perp_close)
    except (TypeError, ValueError):
        return float("nan")
    if not (f > 0 and p > 0):
        return float("nan")
    dte = (pd.Timestamp(expiry) - pd.Timestamp(close_time)).total_seconds() / 86400.0
    if not dte > 0:
        return float("nan")
    import math
    return math.log(f / p) * 365.0 / dte


# ---------------------------------------------------------------- features (pure; network-free, used by tests)

def build_hourly_features(perp_hourly: pd.DataFrame, contract_closes: dict,
                          expiries, roll_days: float = ROLL_DAYS) -> pd.DataFrame:
    """Causal hourly basis features for one venue chain.

    perp_hourly: DataFrame with close_time (UTC), perp_close, sorted.
    contract_closes: {expiry Timestamp -> DataFrame with close_time, close}.
    Returns DataFrame(close_time, qb_front, qb_slope, qb_chg24, front, next)
    where front/next are ISO strings (or None). Every row uses only bars with
    close_time <= its own close_time (merge_asof backward + exact 24h lag).
    """
    exp = sorted(expiries)
    ph = perp_hourly.sort_values("close_time").reset_index(drop=True).copy()
    ph["close_time"] = pd.to_datetime(ph["close_time"], utc=True)
    out = pd.DataFrame({"close_time": ph["close_time"]})
    if not exp:
        out[["qb_front", "qb_slope", "qb_chg24"]] = float("nan")
        out["front"] = None
        out["next"] = None
        return out
    series = {}
    for e in exp:
        d = contract_closes.get(e)
        if d is None or len(d) == 0:
            series[e] = None
            continue
        dd = d.sort_values("close_time")
        series[e] = (dd[["close_time", "close"]]
                     .assign(close_time=pd.to_datetime(dd["close_time"], utc=True))
                     .reset_index(drop=True))
    fronts, nexts, ffront, fnext = [], [], [], []
    for c in out["close_time"]:
        fe, ne = select_front_next(exp, c, roll_days)
        fronts.append(fe)
        nexts.append(ne)
        ff = float("nan")
        if fe is not None and series.get(fe) is not None:
            m = pd.merge_asof(pd.DataFrame({"close_time": [c]}), series[fe],
                              on="close_time", direction="backward")
            if len(m) and pd.notna(m["close"].iloc[0]):
                ff = float(m["close"].iloc[0])
        nn = float("nan")
        if ne is not None and series.get(ne) is not None:
            m = pd.merge_asof(pd.DataFrame({"close_time": [c]}), series[ne],
                              on="close_time", direction="backward")
            if len(m) and pd.notna(m["close"].iloc[0]):
                nn = float(m["close"].iloc[0])
        ffront.append(ff)
        fnext.append(nn)
    out["front"] = [e.isoformat() if e is not None else None for e in fronts]
    out["next"] = [e.isoformat() if e is not None else None for e in nexts]
    qb_f, qb_n = [], []
    for c, fe, ne, ff, nn, p in zip(out["close_time"], fronts, nexts,
                                    ffront, fnext, ph["perp_close"].tolist()):
        qb_f.append(annualised_basis(ff, p, c, fe) if fe is not None else float("nan"))
        qb_n.append(annualised_basis(nn, p, c, ne) if ne is not None else float("nan"))
    out["qb_front"] = qb_f
    import pandas as _pd
    qn = _pd.Series(qb_n, index=out["close_time"])
    qf = _pd.Series(qb_f, index=out["close_time"])
    out["qb_slope"] = [qn[c] - qf[c] if _pd.notna(qn[c]) and _pd.notna(qf[c])
                       else float("nan") for c in out["close_time"]]
    lag = {c: c - _pd.Timedelta(hours=24) for c in out["close_time"]}
    out["qb_chg24"] = [qf[c] - qf[lag[c]] if lag[c] in qf.index
                       and _pd.notna(qf[c]) and _pd.notna(qf[lag[c]])
                       else float("nan") for c in out["close_time"]]
    return out[["close_time", "qb_front", "qb_slope", "qb_chg24", "front", "next"]]


def combine_venues(hourly_um: pd.DataFrame | None,
                   hourly_cm: pd.DataFrame) -> pd.DataFrame:
    """Prefer the USD-M row where its qb_front is available, else COIN-M."""
    if hourly_um is None:
        h = hourly_cm.copy()
        h["source"] = ["cm" if pd.notna(v) else "none" for v in h["qb_front"]]
        return h
    m = hourly_um.set_index("close_time")
    c = hourly_cm.set_index("close_time")
    idx = m.index.union(c.index).sort_values()
    rows = []
    for t in idx:
        use_um = t in m.index and pd.notna(m.loc[t, "qb_front"])
        src = m.loc[t] if use_um else (c.loc[t] if t in c.index else None)
        if src is None:
            rows.append((t, float("nan"), float("nan"), float("nan"),
                         None, None, "none"))
        else:
            s = "um" if use_um else ("cm" if pd.notna(src["qb_front"]) else "none")
            rows.append((t, src["qb_front"], src["qb_slope"], src["qb_chg24"],
                         src["front"], src["next"], s))
    return pd.DataFrame(rows, columns=["close_time", "qb_front", "qb_slope",
                                       "qb_chg24", "front", "next", "source"])


def aggregate_to_4h(hourly: pd.DataFrame) -> pd.DataFrame:
    """4h bars (00/04/08/12/16/20 UTC): value = hourly row with C == 4h close."""
    h = hourly.sort_values("close_time").reset_index(drop=True)
    h["close_time"] = pd.to_datetime(h["close_time"], utc=True)
    if len(h) == 0:
        return pd.DataFrame(columns=["open_time", "close_time", "qb_front",
                                     "qb_slope", "qb_chg24", "source",
                                     "front", "next"])
    start = h["close_time"].iloc[0].floor("D")
    end = h["close_time"].iloc[-1]
    closes = pd.date_range(start=start + pd.Timedelta(hours=4), end=end,
                           freq="4h", tz="UTC")
    # 4h grid anchored at 00 UTC: date_range from midnight keeps 00/04/... phase.
    by_close = h.set_index("close_time")
    rows = []
    for c in closes:
        o = c - pd.Timedelta(hours=4)
        if c in by_close.index:
            r = by_close.loc[c]
            if isinstance(r, pd.DataFrame):
                r = r.iloc[-1]
            src = r["source"] if "source" in by_close.columns else "none"
            if not isinstance(src, str):
                src = "none"
            fr = r["front"] if "front" in by_close.columns else None
            nx = r["next"] if "next" in by_close.columns else None
            rows.append((o, c, r["qb_front"], r["qb_slope"], r["qb_chg24"],
                         src, fr, nx))
        else:
            rows.append((o, c, float("nan"), float("nan"), float("nan"),
                         "none", None, None))
    return pd.DataFrame(rows, columns=["open_time", "close_time", "qb_front",
                                       "qb_slope", "qb_chg24", "source",
                                       "front", "next"])


# ---------------------------------------------------------------- archive I/O

def urlopen_retry(url: str, timeout: int = 60, retries: int = 6) -> bytes:
    """GET with exponential backoff on transient network errors."""
    err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            err = e
            time.sleep(min(2 ** attempt, 30) + 0.5 * attempt)
    raise RuntimeError(f"GET failed after {retries}x: {url}: {err}")


def s3_keys(prefix: str) -> list[str]:
    out, marker = [], ""
    while True:
        txt = urlopen_retry(f"{S3}?prefix={prefix}&marker={marker}").decode()
        chunk = re.findall(r"<Key>([^<]+)</Key>", txt)
        out += chunk
        if "<IsTruncated>true" not in txt:
            return out
        marker = chunk[-1]


def s3_prefixes(prefix: str) -> list[str]:
    out, marker = [], ""
    while True:
        txt = urlopen_retry(
            f"{S3}?delimiter=/&prefix={prefix}&marker={marker}").decode()
        out += re.findall(r"<Prefix>[^<]*?/klines/([^<]+)/</Prefix>", txt)
        if "<IsTruncated>true" not in txt:
            return sorted(set(out))
        m = re.findall(r"<NextMarker>([^<]+)</NextMarker>", txt)
        marker = m[0] if m else out[-1]


def list_delivery_contracts() -> dict:
    """{venue: [contracts]} for UM (BTC/ETH) and CM (BTC/ETH/BNB/XRP/SOL)."""
    um = [s for s in s3_prefixes("data/futures/um/monthly/klines/")
          if re.fullmatch(r"(BTCUSDT|ETHUSDT)_\d{6}", s)]
    cm = [s for s in s3_prefixes("data/futures/cm/monthly/klines/")
          if re.fullmatch(r"(BTCUSD|ETHUSD|BNBUSD|XRPUSD|SOLUSD)_\d{6}", s)]
    return {"um": sorted(um), "cm": sorted(cm)}


def month_of_monthly_key(key: str) -> str:
    m = re.search(r"(\d{4}-\d{2})\.zip$", key)
    return m.group(1) if m else ""


def day_of_daily_key(key: str) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})\.zip$", key)
    return m.group(1) if m else ""


def contract_zip_keys(venue: str, contract: str) -> tuple[list[str], list[str]]:
    """(monthly_keys, daily_keys_after_last_month) for the contract's 1h klines."""
    kind = "um" if venue == "um" else "cm"
    monthly = sorted(k for k in s3_keys(
        f"data/futures/{kind}/monthly/klines/{contract}/1h/")
        if k.endswith(".zip") and "CHECKSUM" not in k)
    last_month = max(([month_of_monthly_key(k) for k in monthly] or [""]))
    daily_all = sorted(k for k in s3_keys(
        f"data/futures/{kind}/daily/klines/{contract}/1h/")
        if k.endswith(".zip") and "CHECKSUM" not in k)
    daily = [k for k in daily_all if day_of_daily_key(k)[:7] > last_month]
    return monthly, daily


def fetch_bytes(url: str, retries: int = 6) -> bytes:
    return urlopen_retry(url, timeout=120, retries=retries)


def parse_kline_zip(raw: bytes) -> pd.DataFrame:
    """Raw 1h kline zip -> DataFrame(open_time, open, high, low, close, volume)."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        if not names:
            raise ValueError("empty zip")
        txt = z.open(names[0]).read().decode()
    first = txt.split("\n", 1)[0]
    has_header = not first[:1].isdigit()
    d = pd.read_csv(io.StringIO(txt), header=0 if has_header else None)
    d = d.iloc[:, :len(KCOLS)]
    d.columns = KCOLS[:d.shape[1]]
    d["open_time"] = pd.to_datetime(pd.to_numeric(d["open_time"]), unit="ms", utc=True)
    d = d.drop_duplicates("open_time").sort_values("open_time")
    for c in ("open", "high", "low", "close", "volume"):
        d[c] = d[c].astype(float)
    return d[["open_time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def ensure_contract_parquet(venue: str, contract: str,
                            prior: dict | None = None) -> tuple[dict, bool]:
    """Download (skip if present) + parse one contract; returns (manifest_entry, downloaded)."""
    kind = "um" if venue == "um" else "cm"
    path = OUT / f"{kind}_{contract}_1h.parquet"
    if path.exists() and prior and isinstance(prior.get("source_urls"), list):
        d = pd.read_parquet(path)
        return ({"contract": contract, "venue": kind, "file": path.name,
                 "rows": int(len(d)), "first_open_time": str(d["open_time"].iloc[0]),
                 "last_open_time": str(d["open_time"].iloc[-1]),
                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                 "source_urls": prior["source_urls"]}, False)
    monthly, daily = contract_zip_keys(venue, contract)
    urls = [BASE + k for k in monthly + daily]
    if path.exists():  # cached but URL provenance missing -> re-list only, no download
        d = pd.read_parquet(path)
        return ({"contract": contract, "venue": kind, "file": path.name,
                 "rows": int(len(d)), "first_open_time": str(d["open_time"].iloc[0]),
                 "last_open_time": str(d["open_time"].iloc[-1]),
                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                 "source_urls": urls}, False)
    parts, missing = [], []
    for key, url in zip(monthly + daily, urls):
        try:
            got = parse_kline_zip(fetch_bytes(url))
            parts.append(got)
            print(f"{contract} {key.rsplit('/', 1)[-1]} rows={len(got)}", flush=True)
        except urllib.error.HTTPError as e:
            if e.code == 404:  # genuinely absent month/day: record, continue
                missing.append(f"{key} (404)")
                print(f"{contract} {key.rsplit('/', 1)[-1]} MISSING 404", flush=True)
            else:
                raise  # persistent server error: abort, resume later (never cache partial)
    if not parts:
        entry = {"contract": contract, "venue": kind, "file": None, "rows": 0,
                 "first_open_time": None, "last_open_time": None, "sha256": None,
                 "source_urls": urls, "missing": missing, "note": "no klines found"}
        return entry, True
    d = (pd.concat(parts, ignore_index=True).drop_duplicates("open_time")
         .sort_values("open_time").reset_index(drop=True))
    d.to_parquet(path)
    entry = {"contract": contract, "venue": kind, "file": path.name,
             "rows": int(len(d)), "first_open_time": str(d["open_time"].iloc[0]),
             "last_open_time": str(d["open_time"].iloc[-1]),
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
             "source_urls": urls}
    if missing:
        entry["missing"] = missing
    return entry, True


# ---------------------------------------------------------------- perp reference (local only)

def load_perp_hourly(perp_sym: str) -> pd.DataFrame:
    """Hourly perp closes from local 1m: close of the last 1m bar of each hour."""
    if perp_sym == "BTCUSDT":
        files = sorted(BTC_1M_DIR.glob("klines_1m_*.parquet"))
    else:
        files = sorted(MAJORS_1M_DIR.glob(f"{perp_sym}_1m_*.parquet"))
    if not files:
        raise FileNotFoundError(f"no local 1m files for {perp_sym}")
    parts = [pd.read_parquet(f, columns=["open_time", "close"]) for f in files]
    d = pd.concat(parts, ignore_index=True)
    d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
    d = d.drop_duplicates("open_time").sort_values("open_time")
    d["hour"] = d["open_time"].dt.floor("h")
    last = d.loc[d.groupby("hour")["open_time"].idxmax()].sort_values("hour")
    return pd.DataFrame({"close_time": last["hour"] + pd.Timedelta(hours=1),
                         "perp_close": last["close"].astype(float).tolist()})


def delivery_hourly(contract: str, venue: str) -> pd.DataFrame:
    """Contract 1h bars as close-time closes (NaN if the contract file is missing)."""
    kind = "um" if venue == "um" else "cm"
    path = OUT / f"{kind}_{contract}_1h.parquet"
    if not path.exists():
        return pd.DataFrame(columns=["close_time", "close"])
    d = pd.read_parquet(path, columns=["open_time", "close"])
    d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
    return pd.DataFrame({"close_time": d["open_time"] + pd.Timedelta(hours=1),
                         "close": d["close"].astype(float)}).sort_values("close_time")


def contract_coin(contract: str) -> str:
    base = contract.split("_")[0]
    return {"BTCUSDT": "BTC", "BTCUSD": "BTC", "ETHUSDT": "ETH", "ETHUSD": "ETH",
            "BNBUSD": "BNB", "XRPUSD": "XRP", "SOLUSD": "SOL"}[base]


# ---------------------------------------------------------------- main

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    FEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    contracts = list_delivery_contracts()
    print(f"delivery contracts: UM={len(contracts['um'])} CM={len(contracts['cm'])}",
          flush=True)
    prior_files: dict = {}
    if (OUT / "manifest.json").exists():
        try:
            prior_files = json.loads((OUT / "manifest.json").read_text()).get("files", {})
        except (json.JSONDecodeError, OSError):
            prior_files = {}
    files: dict[str, dict] = {}
    for venue in ("um", "cm"):
        for contract in contracts[venue]:
            entry, _ = ensure_contract_parquet(
                venue, contract, prior_files.get(f"{venue}_{contract}"))
            files[f"{venue}_{contract}"] = entry
            (OUT / "manifest.json").write_text(json.dumps(
                {"source": BASE, "files": files}, indent=1))

    # ---- causal features per coin on the 4h grid
    by_coin_venue: dict[str, dict[str, list]] = {c: {"um": [], "cm": []} for c in COINS}
    for venue in ("um", "cm"):
        for contract in contracts[venue]:
            coin = contract_coin(contract)
            by_coin_venue[coin][venue].append(contract)
    long_rows = []
    coin_stats = {}
    for coin in COINS:
        perp = load_perp_hourly(PERP[coin])
        venue_hourly = {}
        for venue in ("um", "cm"):
            clist = sorted(by_coin_venue[coin][venue],
                           key=lambda c: expiry_from_contract(c))
            exps = [expiry_from_contract(c) for c in clist]
            closes = {e: delivery_hourly(c, venue) for e, c in zip(exps, clist)}
            venue_hourly[venue] = build_hourly_features(perp, closes, exps)
        combined = (combine_venues(venue_hourly["um"], venue_hourly["cm"])
                    if by_coin_venue[coin]["um"] else combine_venues(None, venue_hourly["cm"]))
        b4 = aggregate_to_4h(combined)
        b4["sym"] = PERP[coin]
        # rolls = front changes between consecutive 4h bars (leading none excluded)
        fr = b4["front"].tolist()
        rolls = sum(1 for a, b in zip(fr, fr[1:]) if b != a and a is not None)
        first_with = next((str(c) for c, v in zip(b4["close_time"], b4["qb_front"])
                           if pd.notna(v)), None)
        n = len(b4)
        nn = int(b4["qb_front"].isna().sum())
        coin_stats[coin] = {
            "rows_4h": n,
            "first_4h_close": str(b4["close_time"].iloc[0]) if n else None,
            "last_4h_close": str(b4["close_time"].iloc[-1]) if n else None,
            "first_contract": first_with,
            "rolls": rolls,
            "nan_share_qb_front": round(nn / n, 4) if n else None,
        }
        keep = b4[["open_time", "close_time", "sym", "qb_front", "qb_slope",
                   "qb_chg24", "source"]]
        long_rows.append(keep)
    feat = (pd.concat(long_rows, ignore_index=True).sort_values(["sym", "close_time"])
            .reset_index(drop=True))
    feat.to_parquet(FEAT_PATH)
    total = len(feat)
    nan_all = int(feat["qb_front"].isna().sum())
    um_share = round(float((feat["source"] == "um").mean()), 4)
    summary = {
        "BTCUSDT": f"rows={coin_stats['BTC']['rows_4h']} first={coin_stats['BTC']['first_contract']} rolls={coin_stats['BTC']['rolls']} nan={coin_stats['BTC']['nan_share_qb_front']}",
        "ETHUSDT": f"rows={coin_stats['ETH']['rows_4h']} first={coin_stats['ETH']['first_contract']} rolls={coin_stats['ETH']['rolls']} nan={coin_stats['ETH']['nan_share_qb_front']}",
        "BNBUSDT": f"rows={coin_stats['BNB']['rows_4h']} first={coin_stats['BNB']['first_contract']} rolls={coin_stats['BNB']['rolls']} nan={coin_stats['BNB']['nan_share_qb_front']}",
        "XRPUSDT": f"rows={coin_stats['XRP']['rows_4h']} first={coin_stats['XRP']['first_contract']} rolls={coin_stats['XRP']['rolls']} nan={coin_stats['XRP']['nan_share_qb_front']}",
        "SOLUSDT": f"rows={coin_stats['SOL']['rows_4h']} first={coin_stats['SOL']['first_contract']} rolls={coin_stats['SOL']['rolls']} nan={coin_stats['SOL']['nan_share_qb_front']}",
        "rows_nan": f"total={total} nan_share={round(nan_all / total, 4) if total else None}",
        "um_range": f"um_share={um_share} range={feat['close_time'].min()}..{feat['close_time'].max()}",
        "note": "rolls=front changes excl leading none; nan=pre-listing/no-contract hours",
    }
    man = {"source": BASE, "files": files, "coins": coin_stats,
           "feature_table": str(FEAT_PATH.relative_to(ROOT)),
           "feature_rows": total, "summary": summary}
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    print(f"saved {FEAT_PATH} rows={total}", flush=True)
    print(json.dumps(summary, indent=1), flush=True)


if __name__ == "__main__":
    main()
