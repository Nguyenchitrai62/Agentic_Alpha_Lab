"""Prospective cascade-boost B7 / B7xC2 feature log (4 clocks x 5 majors, hourly).

B7 definition VERBATIM from research/tournament/oc_cascadeboost (itself verbatim
from oc_cascadedelay): per (sym, shift), r[i] = ln(C[i]/C[i-1]); SIG[i] = std
(ddof=1) of r[i-540..i-1], min_periods 120, tested bar EXCLUDED; trigger iff
|r[i]| > 4.0*SIG[i] (strict); tc = T[i]+4h. Per shift: union tc over the 5
majors -> B7 boosted iff exists tc with 0 < T-tc <= 7 days (market-wide per
shift, same b7_mult for all coins at (shift, T)). b7_mult = 1.5 in window else
1.0. b7c2_mult = b7_mult * c2_mult where c2_mult comes from the live Chronos
feed (read-only); 1.0 where the C2 row is missing (stack_mult with
non-finite leg -> 1.0, as in oc_b7c2/stack_rule.py).

Each --once run (hourly; idempotent): for every shift s whose 4h bar opened in
the last hour, build the trailing closed 4h bars of that shift for
BTC/ETH/SOL/BNB/XRP from Binance USD-M public 1h klines (same OHLCV +
quote-volume convention as oc_kronoshidden/build_bars_4shift.py aggregated from
1m; venue = Binance USD-M there too, so NO venue difference), compute the B7
window for bar open T, join the C2 multiplier, and append to BOTH:
  artifacts/research/cascade_shadow/b7_live.parquet   (k2_mult = b7_mult)
  artifacts/research/cascade_shadow/b7c2_live.parquet (k2_mult = b7c2_mult)
Both files keep the bot-facing columns of the chronos feed
(sym, shift, T, k2_mult, mode, logged_at, is_prospective) so the existing bot
flag --k2-tilt reads them with no code change, plus audit columns
(b7_mult / c2_mult / b7c2_mult, C0, sigma, model_sha). A row is PROSPECTIVE
when logged_at - T <= 30 min; --backfill-hours rows are labelled backfill and
never prospective.

Public market-data GETs only (fapi.binance.com/fapi/v1/klines + /fapi/v1/time).
Robust to API errors (retry, log, exit 0). Never places orders. CPU only
(no model).

  python scripts/cascade_shadow.py --once --dry-run
  python scripts/cascade_shadow.py --once
  python scripts/cascade_shadow.py --once --backfill-hours 48
  python scripts/cascade_shadow.py --once --backfill-hours 552 --now 2026-09-24T00:00:00Z --out research/tournament/bot_b7shadow/tmp/b7_live.parquet
Hourly loop (leader only, every 10 min is fine - idempotent per bar): see
docs/opencode/B7SHADOW_20261008.md. CPU-light: no heavy_slot needed.
"""

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
BOOST_RULE = ROOT / "research/tournament/oc_cascadeboost/boost_rule.py"
C2_FEED = ROOT / "artifacts/research/chronos_shadow/chronos_features_live.parquet"
DEFAULT_OUT_B7 = ROOT / "artifacts/research/cascade_shadow/b7_live.parquet"
DEFAULT_OUT_B7C2 = ROOT / "artifacts/research/cascade_shadow/b7c2_live.parquet"

# Frozen cascade definition (verbatim oc_cascadeboost/boost_rule.py).
THRESH = 4.0
WINDOW = 540  # 90d x 6 bars/day
MIN_PERIODS = 120
BOOST = 1.5
B7_DAYS = 7
NS_DAY = 86_400_000_000_000
HIST_4H = 650  # 540 sigma window + 7d B7 lookback (42 bars) + margin
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
PROSPECTIVE_MAX_LAG = pd.Timedelta(minutes=30)

BASE_URL = "https://fapi.binance.com"
MAX_RETRIES = 6
BACKOFF_BASE_S = 2.0
MIN_INTERVAL_S = 0.21
HOUR_MS = 3_600_000


# ---------------------------------------------------------------- pure helpers
# Arithmetic verbatim from oc_cascadeboost/boost_rule.py (no data access).

def close_returns(closes) -> np.ndarray:
    """Close-to-close log returns; r[0] = NaN. Pure."""
    c = np.asarray(closes, dtype=float)
    r = np.full_like(c, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        r[1:] = np.log(c[1:] / c[:-1])
    r[~np.isfinite(r)] = np.nan
    return r


def trailing_sigma(r, window: int = WINDOW,
                   min_periods: int = MIN_PERIODS) -> np.ndarray:
    """SIG[i] = std(ddof=1) of r[i-window .. i-1] (tested bar EXCLUDED). Pure."""
    r = np.asarray(r, dtype=float)
    n = r.size
    out = np.full(n, np.nan)
    if n == 0:
        return out
    finite = np.isfinite(r)
    cs = np.cumsum(np.where(finite, r, 0.0))
    cs2 = np.cumsum(np.where(finite, r * r, 0.0))
    cn = np.cumsum(finite.astype(float))
    for i in range(n):
        lo = max(0, i - window)
        cnt = cn[i - 1] - (cn[lo - 1] if lo > 0 else 0.0) if i > 0 else 0.0
        if cnt < min_periods:
            continue
        s = cs[i - 1] - (cs[lo - 1] if lo > 0 else 0.0)
        s2 = cs2[i - 1] - (cs2[lo - 1] if lo > 0 else 0.0)
        var = (s2 - s * s / cnt) / (cnt - 1)
        if np.isfinite(var) and var > 0:
            out[i] = float(np.sqrt(var))
    return out


def triggers_of(closes, thresh: float = THRESH, window: int = WINDOW,
                min_periods: int = MIN_PERIODS) -> np.ndarray:
    """Bool array: bar i fires iff |r[i]| > thresh * SIG[i] (strict). Pure."""
    r = close_returns(closes)
    sig = trailing_sigma(r, window, min_periods)
    fire = np.zeros(len(r), dtype=bool)
    ok = np.isfinite(r) & np.isfinite(sig) & (sig > 0)
    fire[ok] = np.abs(r[ok]) > float(thresh) * sig[ok]
    return fire


def boosted_mask(grid_ns: np.ndarray, trig_ns: np.ndarray,
                 n_days: int = B7_DAYS) -> np.ndarray:
    """For each grid time T: True iff exists tc with 0 < T - tc <= n_days. Pure."""
    grid_ns = np.asarray(grid_ns, dtype=np.int64)
    trig_ns = np.asarray(trig_ns, dtype=np.int64)
    out = np.zeros(len(grid_ns), dtype=bool)
    if trig_ns.size == 0:
        return out
    span = int(n_days) * NS_DAY
    pos = np.searchsorted(trig_ns, grid_ns, side="left") - 1
    valid = pos >= 0
    out[valid] = (grid_ns[valid] - trig_ns[pos[valid]] <= span)
    return out


def stack_mult(m_b7: float, m_c2: float) -> float:
    """B7C2 product; non-finite leg counts as 1.0 (as in oc_b7c2/stack_rule.py)."""
    a = float(m_b7) if m_b7 is not None else float("nan")
    b = float(m_c2) if m_c2 is not None else float("nan")
    if not np.isfinite(a):
        a = 1.0
    if not np.isfinite(b):
        b = 1.0
    return float(a * b)


def targets_for_window(now, n_hours: int = 1):
    """Hourly 4h-bar opens: T_k = hour_floor - k*1h, shift = T.hour % 4. Ascending."""
    now = pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    base = now.floor("h")
    out = []
    for k in range(int(n_hours) - 1, -1, -1):
        T = base - pd.Timedelta(hours=k)
        out.append((int(T.hour) % 4, T))
    return out


def is_prospective(logged_at, T) -> bool:
    return (pd.Timestamp(logged_at) - pd.Timestamp(T)) <= PROSPECTIVE_MAX_LAG


def build_shift_bars(h1: pd.DataFrame, shift: int) -> pd.DataFrame:
    """Aggregate CLOSED 1h klines to shift-s 4h bars (same convention as build_bars_4shift.py).

    h1 cols: open_time, open, high, low, close, volume, quote_volume, closed.
    Returns T (bar open), open, high, low, close, volume, amount, n_h.
    Uses ONLY rows with closed == True.
    """
    c = h1[h1["closed"]].copy() if "closed" in h1.columns else h1.copy()
    c = c.sort_values("open_time").reset_index(drop=True)
    if len(c) == 0:
        return pd.DataFrame(columns=["T", "open", "high", "low", "close", "volume", "amount", "n_h"])
    sh = pd.Timedelta(hours=int(shift))
    c["T"] = ((c["open_time"] - sh).dt.floor("4h") + sh)
    g = c.groupby("T", sort=True)
    b = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close": g["close"].last(), "volume": g["volume"].sum(),
        "amount": g["quote_volume"].sum(), "n_h": g.size()})
    return b.reset_index().sort_values("T").reset_index(drop=True)


def complete_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Only COMPLETE (n_h == 4) bars, sorted by T."""
    if len(bars) == 0:
        return bars
    return bars[bars["n_h"] == 4].sort_values("T").reset_index(drop=True)


def context_stats(bars: pd.DataFrame, T):
    """(C0, sigma_at_T) for holding-bar open T, causal: only bars with open < T.

    C0 = close of the last complete bar (known at T). sigma = trailing SIG at
    the position of T in the complete series (NaN when T not on the grid or
    window unfilled). Diagnostic only; the B7 window does not use it.
    """
    cb = complete_bars(bars)
    cb = cb[cb["T"] < pd.Timestamp(T)].sort_values("T").reset_index(drop=True)
    if len(cb) == 0:
        return float("nan"), float("nan")
    c0 = float(cb["close"].iloc[-1])
    try:
        sig = trailing_sigma(close_returns(cb["close"].to_numpy(dtype=float)))
        # SIG of the bar that would sit at T = next index after cb: uses the
        # same window the trigger test would use for a bar closing at T+4h
        # evaluated on history only; report last computable SIG as diagnostic.
        s = float(sig[-1]) if len(sig) else float("nan")
    except Exception:
        s = float("nan")
    return c0, s


def union_triggers_ns(bars_by_sym: dict, shift: int) -> np.ndarray:
    """Union tc (ns, sorted unique) over the 5 majors for one shift.

    bars_by_sym: sym -> shift-s 4h bars DataFrame (any n_h; only complete used).
    tc = T[i]+4h for each firing bar i (verbatim build_boost.py).
    """
    all_tc = []
    for sym in SYMS:
        bars = complete_bars(bars_by_sym.get(sym, pd.DataFrame()))
        if len(bars) == 0:
            continue
        t = pd.to_datetime(bars["T"], utc=True)
        c = bars["close"].to_numpy(dtype=float)
        fire = triggers_of(c)
        tc = (t[fire] + pd.Timedelta(hours=4)).tolist()
        all_tc.extend(tc)
    if not all_tc:
        return np.array([], dtype=np.int64)
    tc = sorted(set(pd.to_datetime(all_tc, utc=True)))
    return np.array([x.value for x in tc], dtype=np.int64)


def b7_mult_for(T, trig_ns: np.ndarray) -> float:
    """1.5 inside (tc, tc+7d] else 1.0 for a single holding-bar open T. Pure."""
    g = np.array([pd.Timestamp(T).value], dtype=np.int64)
    m = boosted_mask(g, np.asarray(trig_ns, dtype=np.int64), B7_DAYS)
    return float(BOOST if bool(m[0]) else 1.0)


def model_sha() -> str:
    return (f"model-free:cascade-B7-THRESH={THRESH}-WINDOW={WINDOW}"
            f"-MIN{MIN_PERIODS}-N={B7_DAYS}-BOOST={BOOST}")


def check_source_def():
    """Confirm constants match oc_cascadeboost/boost_rule.py (fail-open warning)."""
    try:
        txt = BOOST_RULE.read_text()
    except OSError:
        return
    import re
    pairs = [("THRESH", THRESH, float), ("WINDOW", WINDOW, int),
             ("MIN_PERIODS", MIN_PERIODS, int), ("BOOST", BOOST, float),
             ("B7_DAYS", B7_DAYS, int)]
    for name, val, cast in pairs:
        m = re.search(rf"{name}\s*=\s*([0-9.]+)", txt)
        if m and abs(cast(m.group(1)) - val) > 1e-12:
            print(f"WARNING cascade def drift: script {name}={val} vs research {m.group(1)}",
                  flush=True)


def load_c2_map() -> dict:
    """Read-only {(sym, shift, T_ns): c2_mult} from the live Chronos feed.

    Missing / unreadable file -> {} (every b7c2 leg falls back to b7*1.0).
    Row-level problems map that row to 1.0 (never raise).
    """
    try:
        df = pd.read_parquet(C2_FEED, columns=["sym", "shift", "T", "c2_mult"])
    except Exception as exc:
        print(f"c2 feed unreadable ({exc!r}); b7c2 falls back to b7*1.0", flush=True)
        return {}
    out = {}
    try:
        rows = zip(df["sym"], df["shift"], df["T"], df["c2_mult"])
    except (KeyError, TypeError):
        return {}
    for s, sh, t, m in rows:
        try:
            sym = str(s).strip().upper()
            shift = int(sh)
            tn = pd.Timestamp(t)
            if tn.tzinfo is None:
                tn = tn.tz_localize("UTC")
            key = (sym, shift, int(tn.value))
        except Exception:
            continue
        try:
            mf = float(m)
        except (TypeError, ValueError):
            mf = 1.0
        if not np.isfinite(mf):
            mf = 1.0
        out[key] = mf
    return out


# ---------------------------------------------------------------- fetching

def fetch_1h(session: requests.Session, symbol: str, start_ms: int, end_ms: int,
             server_ms: int) -> pd.DataFrame:
    """Closed + forming 1h klines in [start_ms, end_ms); retry/backoff. Public GET only."""
    out, cursor, last_req = [], int(start_ms), [0.0]
    while cursor < int(end_ms):
        params = {"symbol": symbol, "interval": "1h", "startTime": cursor,
                  "endTime": int(end_ms), "limit": 1500}
        for attempt in range(MAX_RETRIES):
            try:
                dt = time.monotonic() - last_req[0]
                if dt < MIN_INTERVAL_S:
                    time.sleep(MIN_INTERVAL_S - dt)
                r = session.get(f"{BASE_URL}/fapi/v1/klines", params=params, timeout=60)
                r.raise_for_status()
                batch = r.json()
                last_req[0] = time.monotonic()
                break
            except Exception as exc:
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError(f"klines failed {symbol}: {exc!r}"[:300])
                time.sleep(BACKOFF_BASE_S * (2 ** attempt))
        if not batch:
            break
        out.extend(batch)
        cursor = int(batch[-1][0]) + HOUR_MS
        if len(batch) < 1500:
            break
    cols = ["ot", "o", "h", "l", "c", "v", "ct", "qv", "nt", "tbv", "tbqv", "ig"]
    df = pd.DataFrame(out, columns=cols) if out else pd.DataFrame(columns=cols)
    if len(df) == 0:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close",
                                     "volume", "quote_volume", "close_time", "closed"])
    df["open_time"] = pd.to_datetime(df["ot"].astype("int64"), unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["ct"].astype("int64"), unit="ms", utc=True)
    for src, dst in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"),
                     ("v", "volume"), ("qv", "quote_volume")):
        df[dst] = df[src].astype(float)
    server_ts = pd.to_datetime(int(server_ms), unit="ms", utc=True)
    df["closed"] = df["close_time"] < server_ts
    df = df[(df["open_time"] >= pd.to_datetime(int(start_ms), unit="ms", utc=True))
            & (df["open_time"] < pd.to_datetime(int(end_ms), unit="ms", utc=True))]
    return df[["open_time", "open", "high", "low", "close", "volume",
               "quote_volume", "close_time", "closed"]].sort_values("open_time").reset_index(drop=True)


# ---------------------------------------------------------------- main

def resolve_outputs(out_arg: str):
    """Primary B7 path from --out; B7C2 path alongside it.

    Default --out (= b7_live.parquet) -> b7c2_live.parquet in the same dir.
    Custom --out named b7_live.parquet -> same rule; any other name -> sibling
    <stem>_b7c2.parquet next to it (documented in B7SHADOW_20261008.md).
    """
    b7 = Path(out_arg)
    if b7.name == "b7_live.parquet":
        return b7, b7.parent / "b7c2_live.parquet"
    if b7.parent / "b7c2_live.parquet" == Path(str(DEFAULT_OUT_B7C2)):
        pass
    return b7, b7.parent / (b7.stem + "_b7c2.parquet")


def done_keys(out_path: Path) -> set:
    if not out_path.exists():
        return set()
    try:
        prev = pd.read_parquet(out_path, columns=["sym", "shift", "T"])
    except Exception as exc:
        print(f"existing parquet unreadable ({exc!r}); starting fresh", flush=True)
        return set()
    return {(str(s), int(sh), pd.Timestamp(t).isoformat()) for s, sh, t in
            zip(prev["sym"], prev["shift"], prev["T"])}


def append_idempotent(out_path: Path, new: pd.DataFrame) -> int:
    """Append rows idempotently on (sym, shift, T); returns total rows."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        try:
            prev = pd.read_parquet(out_path)
        except Exception as exc:
            print(f"existing parquet unreadable ({exc!r}); overwriting", flush=True)
            prev = pd.DataFrame()
        if len(prev):
            prev["T"] = pd.to_datetime(prev["T"], utc=True)
            if "logged_at" in prev.columns:
                prev["logged_at"] = pd.to_datetime(prev["logged_at"], utc=True)
            new = pd.concat([prev, new], ignore_index=True)
        new = new.drop_duplicates(subset=["sym", "shift", "T"], keep="first")
    new.sort_values(["T", "shift", "sym"]).reset_index(drop=True).to_parquet(out_path, index=False)
    return len(new)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                    help="single hourly pass (the leader loops externally)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backfill-hours", type=int, default=0)
    ap.add_argument("--out", default=str(DEFAULT_OUT_B7))
    ap.add_argument("--now", default=None, help="override UTC now (ISO, tests/backfill)")
    a = ap.parse_args()
    t0 = time.time()
    if not a.once:
        print("REFUSED: --once is required (hourly single pass; the leader loops externally)")
        return 2
    b7_path, b7c2_path = resolve_outputs(a.out)
    now = pd.Timestamp(a.now) if a.now else pd.Timestamp(datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    n_hours = int(a.backfill_hours) if int(a.backfill_hours) > 0 else 1
    targets = targets_for_window(now, n_hours)
    check_source_def()
    print(f"cascade_shadow: device=cpu (model-free) targets={[(s, str(T)) for s, T in targets][:3]}"
          f"{'...' if len(targets) > 3 else ''} n={len(targets)} "
          f"out_b7={b7_path} out_b7c2={b7c2_path} backfill={int(a.backfill_hours)}", flush=True)
    if a.dry_run:
        lo = min(T for _, T in targets) - pd.Timedelta(hours=4 * HIST_4H)
        hi = max(T for _, T in targets) + pd.Timedelta(hours=1)
        print(f"dry-run: would fetch Binance USD-M 1h for {SYMS} "
              f"{lo.isoformat()}..{hi.isoformat()} (~{(hi - lo).total_seconds() / 3600:.0f}h each), "
              f"flag cascade bars EXACTLY as oc_cascadedelay/oc_cascadeboost "
              f"(|r|>4*SIG(540,min120), tc=T+4h, union over 5 majors per shift, "
              f"window (tc,tc+7d]) on {len(targets) * len(SYMS)} (sym,shift,T), "
              f"join C2 read-only from {C2_FEED}, append idempotently to {b7_path} + {b7c2_path}. "
              f"No network touched.", flush=True)
        return 0
    try:
        session = requests.Session()
        server_ms = session.get(f"{BASE_URL}/fapi/v1/time", timeout=30).json()["serverTime"]
        lo = min(T for _, T in targets) - pd.Timedelta(hours=4 * HIST_4H)
        hi = max(T for _, T in targets) + pd.Timedelta(hours=1)
        s_ms, e_ms = int(lo.timestamp() * 1000), int(hi.timestamp() * 1000)
        h1_by_sym = {}
        for sym in SYMS:
            h1_by_sym[sym] = fetch_1h(session, sym, s_ms, e_ms, server_ms)
            print(f"fetched {sym}: rows={len(h1_by_sym[sym])} "
                  f"closed={int(h1_by_sym[sym]['closed'].sum())}", flush=True)
    except Exception as exc:
        print(f"API error (logged, exit 0): {exc!r}"[:500], flush=True)
        return 0
    # Per-shift 4h bars + union triggers (causal: only closed 1h -> complete 4h).
    bars_by_shift_sym: dict = {}
    trig_ns_by_shift: dict = {}
    for s, _T in targets:
        if s in bars_by_shift_sym:
            continue
        per_sym = {}
        for sym in SYMS:
            per_sym[sym] = build_shift_bars(h1_by_sym[sym], s)
        bars_by_shift_sym[s] = per_sym
        trig_ns_by_shift[s] = union_triggers_ns(per_sym, s)
        print(f"shift{s}: union triggers={len(trig_ns_by_shift[s])}", flush=True)
    c2map = load_c2_map()
    sha = model_sha()
    done_b7 = done_keys(b7_path)
    done_b7c2 = done_keys(b7c2_path)
    rows_b7, rows_b7c2 = [], []
    logged_at = pd.Timestamp(datetime.now(timezone.utc))
    last_hb = time.time()
    for s, T in targets:
        trig_ns = trig_ns_by_shift[s]
        per_sym = bars_by_shift_sym[s]
        for sym in SYMS:
            key = (sym, int(s), pd.Timestamp(T).isoformat())
            if key in done_b7 and key in done_b7c2:
                print(f"skip {sym} s{s} {T} (already logged)", flush=True)
                continue
            b7 = b7_mult_for(T, trig_ns)
            c0, sig = context_stats(per_sym[sym], T)
            backfill = int(a.backfill_hours) > 0
            mode = "backfill" if backfill else ("prospective" if is_prospective(logged_at, T) else "late")
            c2_key = (sym, int(s), int(pd.Timestamp(T).value))
            c2 = float(c2map.get(c2_key, 1.0))
            if not np.isfinite(c2):
                c2 = 1.0
            b7c2 = stack_mult(b7, c2)
            base = {"sym": sym, "shift": int(s), "T": pd.Timestamp(T),
                    "C0": float(c0), "sigma": float(sig),
                    "model_sha": sha, "logged_at": logged_at, "mode": mode,
                    "is_prospective": bool(mode == "prospective")}
            if key not in done_b7:
                rows_b7.append({**base, "b7_mult": float(b7), "k2_mult": float(b7)})
            if key not in done_b7c2:
                rows_b7c2.append({**base, "b7_mult": float(b7), "c2_mult": float(c2),
                                   "b7c2_mult": float(b7c2), "k2_mult": float(b7c2)})
            now_t = time.time()
            if now_t - last_hb >= 600:
                last_hb = now_t
                print(f"[hb] cascade_shadow alive b7={len(rows_b7)} b7c2={len(rows_b7c2)} "
                      f"elapsed {(now_t - t0) / 60:.1f}min", flush=True)
    if not rows_b7 and not rows_b7c2:
        print(f"done: no new rows (elapsed {(time.time() - t0) / 60:.1f}min, device=cpu)",
              flush=True)
        return 0
    if rows_b7:
        total = append_idempotent(b7_path, pd.DataFrame(rows_b7))
        print(f"saved {b7_path} +{len(rows_b7)} rows total={total}", flush=True)
    if rows_b7c2:
        total = append_idempotent(b7c2_path, pd.DataFrame(rows_b7c2))
        print(f"saved {b7c2_path} +{len(rows_b7c2)} rows total={total}", flush=True)
    el = time.time() - t0
    print(f"done: b7 +{len(rows_b7)} b7c2 +{len(rows_b7c2)} elapsed={el:.0f}s (cpu model-free)",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
