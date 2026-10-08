"""Prospective D1 (downside-share) feature log (4 clocks x 5 majors, hourly) for a paper runner to test D1.

Settings IDENTICAL to research/tournament/oc_downshare (model-free, like
chronos_shadow in structure): D1 = trailing-6d downside-RV share over
close-to-close 4h log returns, i.e. share(r[E-36 .. E-1]) with
share(rs) = sum(min(r,0)^2) / sum(r^2); NaN unless all finite and total > 0.
Causal by construction: only closes of bars closing <= T[E]. Data granularity:
the research build aggregates Binance USD-M 1m klines to 4h bars; here Binance
USD-M public 1h klines are aggregated to the same 4h bars (same OHLCV +
quote-volume convention as oc_kronoshidden/build_bars_4shift.py aggregated
from 1m; venue = Binance USD-M there too, so NO venue difference). A 4h close
is the last 1h close of its block = the last 1m close, so 1h aggregation gives
the same closes (proven by the parity backfill, exact or explained).

Each --once run (hourly; idempotent): for every shift s whose 4h bar opened in
the last hour (opens at s, s+4, ... UTC), build the trailing closed 4h bars of
that shift for BTC/ETH/SOL/BNB/XRP from public 1h klines, compute risk_D1 + C0
for bar open T, and the D1 multiplier from the frozen anchor-2026 fit
(fit_2026.json: direction +1, q20/q80 below; hi/lo 1.25/0.75). Appends to
artifacts/research/d1_shadow/d1_features_live.parquet
(sym, shift, T, risk_D1, C0, d1_mult + k2_mult copy, model_sha, logged_at,
mode, is_prospective). The k2_mult column is an exact copy of d1_mult so the
existing bot flag --k2-tilt reads it with no code change. A row is PROSPECTIVE
when logged_at - T <= 30 min; --backfill-hours rows are labelled backfill and
never prospective.

Public market-data GETs only (fapi.binance.com/fapi/v1/klines + /fapi/v1/time).
Robust to API errors (retry, log, exit 0). Never places orders. CPU only
(no model).

  python scripts/d1_shadow.py --once --dry-run
  python scripts/d1_shadow.py --once
  python scripts/d1_shadow.py --once --backfill-hours 48
Hourly loop (leader only, every 10 min is fine - idempotent per bar): see
docs/opencode/D1SHADOW_20261008.md. CPU-light: no heavy_slot needed.
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
OC = ROOT / "research/tournament/oc_downshare"
FITS_PATH = ROOT / "research/tournament/bot_d1shadow/fit_2026.json"
DEFAULT_OUT = ROOT / "artifacts/research/d1_shadow/d1_features_live.parquet"

# D1 definition (frozen, = oc_downshare PLAN/build_downshare/tilt_rule):
#   r[i] = log(C[i]) - log(C[i-1]); D1[E] = share(r[E-36 .. E-1]) needs the 37
#   closes C[E-37 .. E-1], i.e. 37 COMPLETE 4h bars with open < T[E].
WIN_D1 = 36
NEED_BARS = WIN_D1 + 1  # 37
HIST_4H = 60  # 37 needed + margin (tiny; each 4h bar = 4x 1h klines)
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
# Frozen anchor-2026 D1 fit (fit_2026.json; asserted at runtime against that file).
FROZEN = {"direction": 1, "q20": 0.2902893279268819, "q80": 0.7411885300667425}
D1_HI, D1_LO = 1.25, 0.75
PROSPECTIVE_MAX_LAG = pd.Timedelta(minutes=30)

BASE_URL = "https://fapi.binance.com"
MAX_RETRIES = 6
BACKOFF_BASE_S = 2.0
MIN_INTERVAL_S = 0.21
HOUR_MS = 3_600_000


# ---------------------------------------------------------------- pure helpers

def share_of(rs) -> float:
    """Downside-RV share of a return window (verbatim rule as tilt_rule.share_of)."""
    a = np.asarray(list(rs), dtype=float)
    if a.size == 0:
        return float("nan")
    if not np.all(np.isfinite(a)):
        return float("nan")
    total = float(np.sum(a * a))
    if not np.isfinite(total) or total <= 0:
        return float("nan")
    down = float(np.sum(np.minimum(a, 0.0) ** 2))
    return float(down / total)


def assign_d1(risk: float, direction: int = 1, q20: float = FROZEN["q20"],
              q80: float = FROZEN["q80"], hi: float = D1_HI, lo: float = D1_LO) -> float:
    """D1 multiplier from risk_D1 (same rule as oc_downshare/tilt_rule.assign_mult)."""
    r = float(risk) if risk is not None else float("nan")
    if not np.isfinite(r):
        return 1.0
    if direction > 0:
        if r >= q80:
            return hi
        if r <= q20:
            return lo
        return 1.0
    if r >= q80:
        return lo
    if r <= q20:
        return hi
    return 1.0


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
    Uses ONLY rows with closed == True (bars closing <= T enforced by caller).
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


def select_context(bars: pd.DataFrame, T, p: int = NEED_BARS):
    """Last p COMPLETE (n_h == 4) bars with open < T. Empty when insufficient."""
    b = bars[(bars["T"] < pd.Timestamp(T)) & (bars["n_h"] == 4)].sort_values("T")
    if len(b) < p:
        return b.iloc[0:0]
    return b.tail(p).reset_index(drop=True)


def compute_d1(ctx: pd.DataFrame):
    """D1 downside-share from exactly NEED_BARS trailing closes (as in build_downshare).

    Returns (risk_D1, C0); NaN risk unless all 36 returns finite and total > 0.
    C0 = close of the bar closing at T (last complete close, known at T).
    """
    if len(ctx) < NEED_BARS:
        return float("nan"), float("nan")
    C = ctx["close"].to_numpy(dtype=float)[-NEED_BARS:]
    lc = np.log(np.clip(C, 1e-12, None))
    r = lc[1:] - lc[:-1]  # 36 returns = r[E-36 .. E-1]
    return share_of(r), float(C[-1])


def model_sha() -> str:
    return f"model-free:D1-trailing-6d-downside-RV-share:WIN_D1={WIN_D1}"


def check_source_def():
    """Confirm WIN_D1 matches oc_downshare/tilt_rule.py (assignment: read the exact definition there)."""
    try:
        txt = (OC / "tilt_rule.py").read_text()
    except OSError:
        return
    import re
    m = re.search(r"WIN_D1\s*=\s*(\d+)", txt)
    if m and int(m.group(1)) != WIN_D1:
        print(f"WARNING D1 window drift: script WIN_D1={WIN_D1} vs research {m.group(1)}", flush=True)


def frozen_fit() -> dict:
    try:
        fits = json.loads(FITS_PATH.read_text())
        f = fits["2026-09-24"]
        assert f["direction"] == 1 and abs(f["q20"] - FROZEN["q20"]) < 1e-12 \
            and abs(f["q80"] - FROZEN["q80"]) < 1e-12, "fit_2026.json anchor-2026 changed"
        return {"direction": int(f["direction"]), "q20": float(f["q20"]), "q80": float(f["q80"])}
    except Exception as exc:
        print(f"fit_2026.json unreadable ({exc!r}); using frozen constants", flush=True)
        return dict(direction=1, q20=FROZEN["q20"], q80=FROZEN["q80"])


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                    help="single hourly pass (the leader loops externally)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backfill-hours", type=int, default=0)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--now", default=None, help="override UTC now (ISO, tests/backfill)")
    a = ap.parse_args()
    t0 = time.time()
    if not a.once:
        print("REFUSED: --once is required (hourly single pass; the leader loops externally)")
        return 2
    out_path = Path(a.out)
    now = pd.Timestamp(a.now) if a.now else pd.Timestamp(datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    n_hours = int(a.backfill_hours) if int(a.backfill_hours) > 0 else 1
    targets = targets_for_window(now, n_hours)
    check_source_def()
    print(f"d1_shadow: device=cpu (model-free) targets={[(s, str(T)) for s, T in targets][:3]}"
          f"{'...' if len(targets) > 3 else ''} n={len(targets)} "
          f"out={out_path} backfill={int(a.backfill_hours)}", flush=True)
    if a.dry_run:
        lo = min(T for _, T in targets) - pd.Timedelta(hours=4 * HIST_4H)
        hi = max(T for _, T in targets) + pd.Timedelta(hours=1)
        print(f"dry-run: would fetch Binance USD-M 1h for {SYMS} "
              f"{lo.isoformat()}..{hi.isoformat()} (~{(hi - lo).total_seconds() / 3600:.0f}h each), "
              f"compute D1 trailing-6d downside-RV share on {len(targets) * len(SYMS)} (sym,shift,T), "
              f"append idempotently to {out_path}. No network touched.", flush=True)
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
    fit = frozen_fit()
    sha = model_sha()
    done = done_keys(out_path)
    rows = []
    logged_at = pd.Timestamp(datetime.now(timezone.utc))
    last_hb = time.time()
    for s, T in targets:
        for sym in SYMS:
            key = (sym, int(s), pd.Timestamp(T).isoformat())
            if key in done:
                print(f"skip {sym} s{s} {T} (already logged)", flush=True)
                continue
            bars = build_shift_bars(h1_by_sym[sym], s)
            ctx = select_context(bars, T)
            if len(ctx) < NEED_BARS:
                print(f"skip {sym} s{s} {T}: only {len(ctx)} complete bars (<{NEED_BARS})", flush=True)
                continue
            risk, C0 = compute_d1(ctx)
            backfill = int(a.backfill_hours) > 0
            mode = "backfill" if backfill else ("prospective" if is_prospective(logged_at, T) else "late")
            mult = assign_d1(risk, fit["direction"], fit["q20"], fit["q80"])
            rows.append({"sym": sym, "shift": int(s), "T": pd.Timestamp(T),
                         "risk_D1": float(risk), "C0": float(C0),
                         "d1_mult": mult, "k2_mult": mult,
                         "model_sha": sha, "logged_at": logged_at, "mode": mode,
                         "is_prospective": bool(mode == "prospective")})
            now_t = time.time()
            if now_t - last_hb >= 600:
                last_hb = now_t
                print(f"[hb] d1_shadow alive rows={len(rows)} elapsed {(now_t - t0) / 60:.1f}min",
                      flush=True)
    if not rows:
        print(f"done: no new rows (elapsed {(time.time() - t0) / 60:.1f}min, device=cpu)",
              flush=True)
        return 0
    new = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        prev = pd.read_parquet(out_path)
        prev["T"] = pd.to_datetime(prev["T"], utc=True)
        prev["logged_at"] = pd.to_datetime(prev["logged_at"], utc=True)
        new = pd.concat([prev, new], ignore_index=True)
        new = new.drop_duplicates(subset=["sym", "shift", "T"], keep="first")
    new.sort_values(["T", "shift", "sym"]).reset_index(drop=True).to_parquet(out_path, index=False)
    el = time.time() - t0
    print(f"saved {out_path} +{len(rows)} rows total={len(new)} "
          f"elapsed={el:.0f}s (cpu model-free)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
