"""Prospective Chronos-Bolt-small C2 feature log (4 clocks x 5 majors, hourly) for a paper runner to test C2.

Settings IDENTICAL to research/tournament/oc_chronos/run_chronos_4shift.py
(amazon/chronos-bolt-small, context 512x4h log closes, pred_len 1,
deterministic quantile heads 0.1..0.9; ch_q10/ch_q50/ch_q90 = (q - log C0)/sigma,
sigma = std of last 360 4h log-open diffs incl. diff to open_T, SAME formula
as Kronos' sigma; C0 = close of the bar closing at T). Imports chronos from
oc_chronos/pylib exactly as the research script does (same package versions).
Model pinned at the exact HF snapshot revision used by the research run
(loaded from the local HF cache via revision=...; fails loudly when missing).
Deterministic: Chronos-Bolt quantile heads need no sampling seed.

Each --once run (hourly; idempotent): for every shift s whose 4h bar opened in
the last hour (opens at s, s+4, ... UTC), build the 512 closed 4h bars of that
shift for BTC/ETH/SOL/BNB/XRP from Binance USD-M public 1h klines (same OHLCV +
quote-volume convention as oc_kronoshidden/build_bars_4shift.py aggregated from
1m; venue = Binance USD-M there too, so NO venue difference), compute
ch_q10/ch_q50/ch_q90 + sigma + C0 for bar open T, and the C2 multiplier from the
frozen anchor-2026 fit (fit_2026.json: direction +1, q20/q80 below; hi/lo
1.25/0.75). Appends to artifacts/research/chronos_shadow/chronos_features_live.parquet
(sym, shift, T, features, c2_mult + k2_mult copy, model_sha, logged_at, mode).
The k2_mult column is an exact copy of c2_mult so the existing bot flag
--k2-tilt reads it with no code change. A row is PROSPECTIVE when
logged_at - T <= 30 min; --backfill-hours rows are labelled backfill and never
prospective.

Public market-data GETs only (fapi.binance.com/fapi/v1/klines + /fapi/v1/time).
Robust to API errors (retry, log, exit 0). Never places orders.

  python scripts/chronos_shadow.py --once --dry-run
  python scripts/chronos_shadow.py --once
  python scripts/chronos_shadow.py --once --backfill-hours 48
Hourly loop (leader only, every 10 min is fine - idempotent per bar): see
docs/opencode/CHRONOSSHADOW_20261008.md. Heavy/GPU step: wrap in heavy_slot.
"""

import torch  # before pandas (Windows DLL load order)

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
OC = ROOT / "research/tournament/oc_chronos"
PYLIB = OC / "pylib"
FITS_PATH = ROOT / "research/tournament/bot_c2shadow/fit_2026.json"
DEFAULT_OUT = ROOT / "artifacts/research/chronos_shadow/chronos_features_live.parquet"

MODEL = "amazon/chronos-bolt-small"
MODEL_REVISION = "772f3d25d38aec6d914c8949dab4462e2d46f5d8"
P, H = 512, 1
SIG_WIN = 360
HIST_4H = 932  # 512 context + 360 sigma + margin
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
# Frozen anchor-2026 C2 fit (fit_2026.json; asserted at runtime against that file).
FROZEN = {"direction": 1, "q20": 1.0765874389863197, "q80": 2.5955569463614445}
C2_HI, C2_LO = 1.25, 0.75
PROSPECTIVE_MAX_LAG = pd.Timedelta(minutes=30)

BASE_URL = "https://fapi.binance.com"
MAX_RETRIES = 6
BACKOFF_BASE_S = 2.0
MIN_INTERVAL_S = 0.21
HOUR_MS = 3_600_000


# ---------------------------------------------------------------- pure helpers

def assign_c2(risk: float, direction: int = 1, q20: float = FROZEN["q20"],
              q80: float = FROZEN["q80"], hi: float = C2_HI, lo: float = C2_LO) -> float:
    """C2 multiplier from risk = -ch_q10 (same rule as oc_chronos/tilt_rule.py)."""
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


def select_context(bars: pd.DataFrame, T, p: int = P):
    """Last p COMPLETE (n_h == 4) bars with open < T. Empty when insufficient."""
    b = bars[(bars["T"] < pd.Timestamp(T)) & (bars["n_h"] == 4)].sort_values("T")
    if len(b) < p:
        return b.iloc[0:0]
    return b.tail(p).reset_index(drop=True)


def compute_sigma(ctx: pd.DataFrame, open_T: float) -> float:
    """Rolling-360 sample std of log-open diffs incl. diff to open_T (as in run_chronos_4shift)."""
    opens = np.r_[ctx["open"].to_numpy(dtype=float), [float(open_T)]]
    lo = np.log(np.maximum(opens, 1e-12))
    sig = pd.Series(np.r_[np.nan, np.diff(lo)]).rolling(SIG_WIN).std().to_numpy()
    return float(sig[-1])


def model_sha() -> str:
    return f"{MODEL}@{MODEL_REVISION}"


def check_model_id():
    """Confirm MODEL matches run_chronos_4shift.py (assignment: read MODEL from that script)."""
    try:
        txt = (OC / "run_chronos_4shift.py").read_text()
    except OSError:
        return
    import re
    m = re.search(r'MODEL\s*=\s*"([^"]+)"', txt)
    if m and m.group(1) != MODEL:
        print(f"WARNING model id drift: script MODEL={MODEL} vs research {m.group(1)}", flush=True)


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


# ---------------------------------------------------------------- inference (torch, lazy)

def load_chronos(device: str):
    sys.path.insert(0, str(PYLIB))
    from chronos import ChronosBoltPipeline  # noqa: E402
    check_model_id()
    try:
        import transformers
        print(f"transformers={transformers.__version__}", flush=True)
    except Exception as e:
        print(f"transformers version unknown: {e}", flush=True)
    import importlib.metadata as md
    try:
        print(f"chronos-forecasting={md.version('chronos-forecasting')}", flush=True)
    except Exception as e:
        print(f"chronos-forecasting version unknown: {e}", flush=True)
    try:
        pipe = ChronosBoltPipeline.from_pretrained(MODEL, revision=MODEL_REVISION)
    except Exception as exc:
        print(f"FATAL: cannot load {MODEL} at revision {MODEL_REVISION}: {exc!r}", flush=True)
        print("The pinned HF snapshot revision is missing from the local cache; "
              "refusing to run with unpinned weights.", flush=True)
        raise SystemExit(f"missing pinned model revision {MODEL_REVISION}: {exc!r}")
    try:
        pipe.model.to(device).eval()
    except Exception as exc:
        print(f"FATAL: cannot move Chronos model to {device}: {exc!r}", flush=True)
        raise
    try:
        rev = pipe.model.config.revision if hasattr(pipe.model.config, "revision") else None
    except Exception:
        rev = None
    print(f"model={MODEL} pinned_revision={MODEL_REVISION} config_revision={rev} "
          f"quantiles={pipe.quantiles}", flush=True)
    return pipe


@torch.no_grad()
def infer_one(pipe, device: str, ctx: pd.DataFrame, open_T: float) -> dict:
    """Identical feature math to run_chronos_4shift.py for one (sym, shift, T)."""
    closes = ctx["close"].to_numpy(dtype=np.float64)
    sigma = compute_sigma(ctx, open_T)
    C0 = float(ctx["close"].iloc[-1])
    logc = np.log(np.clip(closes, 1e-12, None)).astype(np.float32)
    context = torch.from_numpy(np.ascontiguousarray(logc[None, :])).to(device)
    pred = pipe.predict(context, prediction_length=H)  # (1, 9, 1), q = 0.1..0.9
    q = pred[:, :, 0].float().cpu().numpy()
    lc0 = float(np.log(max(C0, 1e-12)))
    sg = float(sigma)
    return {"sigma": sg, "C0": C0,
            "ch_q10": float((float(q[0, 0]) - lc0) / sg),
            "ch_q50": float((float(q[0, 4]) - lc0) / sg),
            "ch_q90": float((float(q[0, 8]) - lc0) / sg)}


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
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"chronos_shadow: device={device} targets={[(s, str(T)) for s, T in targets][:3]}"
          f"{'...' if len(targets) > 3 else ''} n={len(targets)} "
          f"out={out_path} backfill={int(a.backfill_hours)}", flush=True)
    if a.dry_run:
        lo = min(T for _, T in targets) - pd.Timedelta(hours=4 * HIST_4H)
        hi = max(T for _, T in targets) + pd.Timedelta(hours=1)
        print(f"dry-run: would fetch Binance USD-M 1h for {SYMS} "
              f"{lo.isoformat()}..{hi.isoformat()} (~{(hi - lo).total_seconds() / 3600:.0f}h each), "
              f"infer H={H} on {len(targets) * len(SYMS)} (sym,shift,T) with {MODEL}@{MODEL_REVISION}, "
              f"append idempotently to {out_path}. No network/model touched.", flush=True)
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
    rows, pipe = [], None
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
            if len(ctx) < P:
                print(f"skip {sym} s{s} {T}: only {len(ctx)} complete bars (<{P})", flush=True)
                continue
            m1 = h1_by_sym[sym]
            hit = m1[m1["open_time"] == pd.Timestamp(T)]
            open_T = float(hit["open"].iloc[0]) if len(hit) else float(ctx["close"].iloc[-1])
            sigma = compute_sigma(ctx, open_T)
            if not np.isfinite(sigma) or sigma <= 0:
                print(f"skip {sym} s{s} {T}: nonfinite sigma", flush=True)
                continue
            try:
                if pipe is None:
                    torch.manual_seed(20261007)
                    print(f"loading {MODEL}@{MODEL_REVISION} on {device} ...", flush=True)
                    pipe = load_chronos(device)
                    print("model loaded", flush=True)
                r0 = time.time()
                feats = infer_one(pipe, device, ctx, open_T)
                dt = time.time() - r0
                print(f"inferred {sym} s{s} {T} ch_q10={feats['ch_q10']:.4f} in {dt:.1f}s ({device})",
                      flush=True)
            except SystemExit:
                raise
            except Exception as exc:
                print(f"inference error {sym} s{s} {T} (logged, continue): {exc!r}"[:500], flush=True)
                continue
            backfill = int(a.backfill_hours) > 0
            mode = "backfill" if backfill else ("prospective" if is_prospective(logged_at, T) else "late")
            mult = assign_c2(-feats["ch_q10"], fit["direction"], fit["q20"], fit["q80"])
            rows.append({"sym": sym, "shift": int(s), "T": pd.Timestamp(T),
                         "ch_q10": feats["ch_q10"], "ch_q50": feats["ch_q50"],
                         "ch_q90": feats["ch_q90"], "sigma": feats["sigma"], "C0": feats["C0"],
                         "c2_mult": mult, "k2_mult": mult,
                         "model_sha": sha, "logged_at": logged_at, "mode": mode,
                         "is_prospective": bool(mode == "prospective")})
            now_t = time.time()
            if now_t - last_hb >= 600:
                last_hb = now_t
                print(f"[hb] chronos_shadow alive rows={len(rows)} elapsed {(now_t - t0) / 60:.1f}min",
                      flush=True)
    if not rows:
        print(f"done: no new rows (elapsed {(time.time() - t0) / 60:.1f}min, device={device})",
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
          f"elapsed={el:.0f}s ({el / max(len(rows), 1):.0f}s/row on {device})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
