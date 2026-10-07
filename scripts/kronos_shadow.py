"""Prospective Kronos-small feature log (4 clocks x 5 majors, hourly) for a later counterfactual of the K2 dip tilt.

Settings IDENTICAL to research/tournament/oc_kronoshidden/run_inference_4shift.py
(Kronos-small + Tokenizer-base, context 400x4h, pred_len 6, S=64, T=1.0,
top_p=0.9, top_k=0, fp32, per-window z-norm + clip 5). Reuses that folder's
model/ and kronos_fast.py by import. Seed per (sym, shift, T) = hash-based so
reruns are reproducible. GPU if available else CPU (elapsed per run printed).

Each --once run (hourly; idempotent): for every shift s whose 4h bar opened in
the last hour (opens at s, s+4, ... UTC), build the 400 closed 4h bars of that
shift for BTC/ETH/SOL/BNB/XRP from Binance USD-M public 1h klines (same OHLCV +
quote-volume convention as oc_kronoshidden/build_bars_4shift.py aggregated from
1m; venue = Binance USD-M there too, so NO venue difference), compute the 8
features + sigma + C0 for bar open T, and the K2 multiplier from the frozen
anchor-2025 fit (fits.json: direction +1, q20 0.5872, q80 2.1828; hi/lo
1.25/0.75). Appends to artifacts/research/kronos_shadow/kronos_features_live.parquet
(sym, shift, T, features, k2_mult, model_sha, logged_at, mode). A row is
PROSPECTIVE when logged_at - T <= 30 min; --backfill-hours rows are labelled
backfill and never prospective.

Public market-data GETs only (fapi.binance.com/fapi/v1/klines + /fapi/v1/time).
Robust to API errors (retry, log, exit 0). Never places orders.

  python scripts/kronos_shadow.py --once --dry-run
  python scripts/kronos_shadow.py --once
  python scripts/kronos_shadow.py --once --backfill-hours 48
Hourly loop (leader only, every 10 min is fine - idempotent per bar): see
docs/opencode/KRONOSSHADOW_20261007.md. Heavy/GPU step: wrap in heavy_slot.
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
OC = ROOT / "research/tournament/oc_kronoshidden"
FITS_PATH = OC / "fits.json"
DEFAULT_OUT = ROOT / "artifacts/research/kronos_shadow/kronos_features_live.parquet"

MODEL = "NeoQuasar/Kronos-small"
TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"
P, H, S = 400, 6, 64
TEMP, TOP_P, TOP_K = 1.0, 0.9, 0
SIG_WIN = 360
HIST_4H = 820  # 400 context + 360 sigma + margin
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
# Frozen anchor-2025 K2 fit (fits.json; asserted at runtime against that file).
FROZEN = {"direction": 1, "q20": 0.5872428352509342, "q80": 2.182801599162049}
K2_HI, K2_LO = 1.25, 0.75
PROSPECTIVE_MAX_LAG = pd.Timedelta(minutes=30)

BASE_URL = "https://fapi.binance.com"
MAX_RETRIES = 6
BACKOFF_BASE_S = 2.0
MIN_INTERVAL_S = 0.21
HOUR_MS = 3_600_000


# ---------------------------------------------------------------- pure helpers

def seed_for(sym: str, shift: int, T) -> int:
    t = pd.Timestamp(T)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    key = f"{sym}|{int(shift)}|{t.isoformat()}|{MODEL}|S{S}|T{TEMP}|p{TOP_P}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def assign_k2(low1: float, direction: int = 1, q20: float = FROZEN["q20"],
              q80: float = FROZEN["q80"], hi: float = K2_HI, lo: float = K2_LO) -> float:
    """K2 multiplier from risk = -low1 (same rule as oc_kronoshidden/tilt_rule.py)."""
    r = float(low1) if low1 is not None else float("nan")
    if not np.isfinite(r):
        return 1.0
    risk = -r
    if direction > 0:
        if risk >= q80:
            return hi
        if risk <= q20:
            return lo
        return 1.0
    if risk >= q80:
        return lo
    if risk <= q20:
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
    """Rolling-360 sample std of log-open diffs incl. diff to open_T (as in run_inference_4shift)."""
    opens = np.r_[ctx["open"].to_numpy(dtype=float), [float(open_T)]]
    lo = np.log(np.maximum(opens, 1e-12))
    sig = pd.Series(np.r_[np.nan, np.diff(lo)]).rolling(SIG_WIN).std().to_numpy()
    return float(sig[-1])


def stamps(ts) -> np.ndarray:
    ts = pd.DatetimeIndex(ts)
    return np.stack([ts.minute, ts.hour, ts.weekday, ts.day, ts.month], -1).astype(np.float32)


def model_sha() -> str:
    h = hashlib.sha256()
    h.update(MODEL.encode())
    for f in (OC / "kronos_fast.py", OC / "model/kronos.py", OC / "run_inference_4shift.py"):
        try:
            h.update(Path(f).read_bytes())
        except OSError:
            h.update(b"missing:" + str(f).encode())
    return f"{MODEL}#{h.hexdigest()[:12]}"


def check_model_id():
    """Confirm MODEL matches run_inference_4shift.py (assignment: read MODEL from that script)."""
    try:
        txt = (OC / "run_inference_4shift.py").read_text()
    except OSError:
        return
    import re
    m = re.search(r'MODEL\s*=\s*"([^"]+)"', txt)
    if m and m.group(1) != MODEL:
        print(f"WARNING model id drift: script MODEL={MODEL} vs inference {m.group(1)}", flush=True)


def frozen_fit() -> dict:
    try:
        fits = json.loads(FITS_PATH.read_text())
        f = fits["2025-09-24"]
        assert f["direction"] == 1 and abs(f["q20"] - FROZEN["q20"]) < 1e-12 \
            and abs(f["q80"] - FROZEN["q80"]) < 1e-12, "fits.json anchor-2025 changed"
        return {"direction": int(f["direction"]), "q20": float(f["q20"]), "q80": float(f["q80"])}
    except Exception as exc:
        print(f"fits.json unreadable ({exc!r}); using frozen constants", flush=True)
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

def load_kronos(device: str):
    sys.path.insert(0, str(OC))
    import kronos_fast as kf  # noqa: E402
    from model import Kronos, KronosTokenizer  # noqa: E402
    check_model_id()
    tok = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base").to(device).eval()
    mdl = Kronos.from_pretrained(MODEL).to(device).eval()
    return kf, tok, mdl


@torch.no_grad()
def infer_one(kf, tok, mdl, device: str, ctx: pd.DataFrame, open_T: float,
              T, seed: int) -> dict:
    """Identical sampling/feature math to run_inference_4shift.py for one (sym, shift, T)."""
    X = ctx[["open", "high", "low", "close", "volume", "amount"]].to_numpy(np.float32)
    st = stamps(ctx["T"])
    lo = np.log(np.maximum(ctx["open"].to_numpy(dtype=float), 1e-12))
    sig_full = pd.Series(np.r_[np.nan, np.diff(np.r_[lo, [np.log(max(float(open_T), 1e-12))]])]) \
        .rolling(SIG_WIN).std().to_numpy()
    sigma = float(sig_full[-1])
    xn = X[None, :, :]
    m, s = xn.mean(1, keepdims=True), xn.std(1, keepdims=True)
    xnn = (xn - m) / (s + 1e-5)
    xs = st[None, :, :]
    hoff = pd.to_timedelta(4 * np.arange(H), unit="h")
    ys = np.stack([stamps(pd.DatetimeIndex([pd.Timestamp(T) + o]))[0] for o in hoff])[None, :, :]
    f = lambda a: torch.from_numpy(np.ascontiguousarray(a, dtype=np.float32)).to(device)
    torch.manual_seed(seed)
    if device.startswith("cuda"):
        torch.cuda.manual_seed_all(seed)
    out = kf.sample_paths(tok, mdl, f(xnn), f(xs), f(ys), H, S, T=TEMP, top_k=TOP_K, top_p=TOP_P)
    out = out.double() * (f(s)[:, None, :, :].double() + 1e-5) + f(m)[:, None, :, :].double()
    O, Hh, L, C = out[..., 0], out[..., 1], out[..., 2], out[..., 3]
    Leff = torch.minimum(torch.minimum(L, O), C).clamp_min(1e-12)
    Heff = torch.maximum(torch.maximum(Hh, O), C)
    C0 = float(ctx["close"].iloc[-1])
    sg = float(sigma)
    C0t = torch.tensor([[C0]], dtype=torch.float64, device=device)
    r1 = torch.log(C[..., 0].clamp_min(1e-12) / C0t) / sg
    r6 = torch.log(C[..., 5].clamp_min(1e-12) / C0t) / (sg * np.sqrt(6))
    l1 = torch.log(Leff[..., 0] / C0t) / sg
    feats = dict(er1=float(r1.mean(1).cpu()),
                 er6=float(r6.mean(1).cpu()),
                 vol1=float(r1.std(1).cpu()),
                 vol6=float(r6.std(1).cpu()),
                 rng1=float((torch.log(Heff[..., 0] / Leff[..., 0]) / sg).mean(1).cpu()),
                 low1=float(l1.mean(1).cpu()),
                 pdrop2=float((l1 < -2).double().mean(1).cpu()),
                 pdrop3=float((l1 < -3).double().mean(1).cpu()))
    return {"sigma": sg, "C0": C0, **feats}


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
    print(f"kronos_shadow: device={device} targets={[(s, str(T)) for s, T in targets]} "
          f"out={out_path} backfill={int(a.backfill_hours)}", flush=True)
    if a.dry_run:
        lo = min(T for _, T in targets) - pd.Timedelta(hours=4 * HIST_4H)
        hi = max(T for _, T in targets) + pd.Timedelta(hours=1)
        print(f"dry-run: would fetch Binance USD-M 1h for {SYMS} "
              f"{lo.isoformat()}..{hi.isoformat()} (~{(hi - lo).total_seconds() / 3600:.0f}h each), "
              f"infer S={S} on {len(targets) * len(SYMS)} (sym,shift,T), "
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
    rows, kf_tok_mdl = [], None
    logged_at = pd.Timestamp(datetime.now(timezone.utc))
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
                if kf_tok_mdl is None:
                    print(f"loading {MODEL} on {device} ...", flush=True)
                    kf_tok_mdl = load_kronos(device)
                    print("model loaded", flush=True)
                kf, tok, mdl = kf_tok_mdl
                r0 = time.time()
                feats = infer_one(kf, tok, mdl, device, ctx, open_T, T, seed_for(sym, s, T))
                dt = time.time() - r0
                print(f"inferred {sym} s{s} {T} low1={feats['low1']:.4f} in {dt:.0f}s ({device})",
                      flush=True)
            except Exception as exc:
                print(f"inference error {sym} s{s} {T} (logged, continue): {exc!r}"[:500], flush=True)
                continue
            backfill = int(a.backfill_hours) > 0
            mode = "backfill" if backfill else ("prospective" if is_prospective(logged_at, T) else "late")
            rows.append({"sym": sym, "shift": int(s), "T": pd.Timestamp(T),
                         **feats, "k2_mult": assign_k2(feats["low1"], fit["direction"],
                                                      fit["q20"], fit["q80"]),
                         "model_sha": sha, "logged_at": logged_at, "mode": mode,
                         "is_prospective": bool(mode == "prospective")})
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
