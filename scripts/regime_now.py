"""Thi truong hien tai (chi doc, khong dat lenh).

Doc tieng Viet cho chu so huu:
  (1) bear-book filter now (BTC vs mean 1200 bar 4h, % distance) - book long co bi halved?
  (2) BTC + moi coin: 30-day realised vol hien tai + percentile vs lich su 2021-2026 (causal).
      Vol hien tai uu tien 1h live (720 return 1h, annual hoa) khi co live 1h;
      khong thi dung 4h mo rong. Phan phoi lich su = 1 diem vol / thang lich
      (bar cuoi thang, causal), percentile = 100 * mean(dist <= hien tai).
  (3) so flush 2.5-sigma 4h moi coin trong 30 ngay qua vs phan phoi thang lich su (p10/p50/p90).
  (4) 1 dong: dip activity thang nay (thap / binh thuong / cao) + P&L ky vong
      (thang yen tinh = it trade, khong phai edge hong - xem oc_edgedecay REPORT.md).

Nguon du lieu:
  - Local (offline-first): data/raw/ma_ribbon_20260924/klines_4h.parquet (BTC),
    data/raw/xasset_20260924/{SYM}_4h.parquet (ETH/SOL/BNB/XRP).
  - Live (public only, khong bao gio dat lenh): 45 ngay gan nhat cua 5 coin -
    klines 4h (~270 bar, lay 300 bar tru hao) cho flush/activity/bear-nen va
    klines 1h (~1080 bar, lay 1100 bar tru hao) cho vol - qua
    bot.bybit_v5.cached_call (shared kline cache, TTL 10 phut). Chi append cac
    bar live co open_time > local max (khong ghi de lich su), loai bar dang
    hinh thanh (chua dong). API chet -> dung local va ghi 'du lieu cu' kem
    timestamp.
  - daily_status.py goi summarize(root, live=False) nen van offline (localhost only).

Dinh nghia (khan truoc khi nhin ket qua, khop oc_edgedecay + bot/mirror):
  - Bear (giong bot/mirror.is_bear): open 4h moi nhat < mean don cua 1200
    open 4h gan nhat (toi thieu 600 bar). Book long bi halved khi bear.
  - Vol 30d (4h): std cua 180 log-return 4h gan nhat (ddof=1, toi thieu 90) *
    sqrt(6*365) * 100 (%/nam). Vol 30d (1h live): std cua 720 log-return 1h
    gan nhat (ddof=1, toi thieu 600) * sqrt(24*365) * 100 (%/nam).
  - Flush: lr = log(close/close.shift(1)); sig = std trailing 180 bar (min 90)
    STRICTLY truoc bar hien tai; flush <=> sig > 0 va lr <= -2.5*sig
    (giong oc_edgedecay run_edgedecay.py). Dem theo thang lich (open_time).
  - Activity: TOTAL = tong flush 5 coin trong 180 bar 4h gan nhat (~30 ngay);
    lich su = tong flush / thang lich. THAP neu < p25, CAO neu > p75,
    con lai BINH THUONG (p25/p75 tu cung lich su thang do).
"""
from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
BEAR_WINDOW = 1200
BEAR_MIN = 600
VOL_WINDOW = 180  # ~30 ngay bar 4h
VOL_MIN = 90
VOL1H_WINDOW = 720  # ~30 ngay bar 1h
VOL1H_MIN = 600  # toi thieu ~25 ngay 1h, thieu hon thi fallback 4h
FLUSH_K = 2.5
FLUSH_WIN = 180
FLUSH_MIN = 90
HIST_START = pd.Timestamp("2021-01-01", tz="UTC")
PER_YEAR_4H = 6 * 365
PER_YEAR_1H = 24 * 365
# Live extension: 45 ngay gan nhat (public Bybit, cached).
LIVE_DAYS = 45
LIVE_4H_BARS = 300  # 45d * 6 + tru hao overlap
LIVE_1H_BARS = 1100  # 45d * 24 + tru hao overlap
LIVE_TTL = 600.0  # 10 phut: readout che do doc, khong can TTL 20s nhu bot
MS_1H = 3_600_000
MS_4H = 4 * MS_1H


def _btc_path(root: Path) -> Path:
    return root / "data" / "raw" / "ma_ribbon_20260924" / "klines_4h.parquet"


def _alt_path(root: Path, sym: str) -> Path:
    return root / "data" / "raw" / "xasset_20260924" / f"{sym}_4h.parquet"


def load_local_4h(root: Path, sym: str) -> pd.DataFrame | None:
    """1 DataFrame local (open_time/open/high/low/close, sort, tz UTC) hoac None."""
    p = _btc_path(root) if sym == "BTCUSDT" else _alt_path(root, sym)
    try:
        if not p.exists():
            return None
        df = pd.read_parquet(p, columns=["open_time", "open", "high", "low", "close"])
    except Exception:
        return None
    try:
        df = df.copy()
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
        for c in ("open", "high", "low", "close"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["open_time", "open", "close"])
        df = df.sort_values("open_time").reset_index(drop=True)
    except Exception:
        return None
    return df if len(df) else None


def bear_state(opens) -> dict:
    """Bear-book filter tu chuoi open 4h (khop bot/mirror.is_bear)."""
    try:
        seq = [float(x) for x in list(opens or []) if x is not None]
        seq = [x for x in seq if math.isfinite(x)]
    except (TypeError, ValueError):
        return {"ok": False, "is_bear": False, "price": None, "mean": None,
                "dist_pct": None, "n": 0, "note": "khong co du lieu open"}
    n = len(seq)
    if n < BEAR_MIN:
        return {"ok": False, "is_bear": False, "price": float(seq[-1]) if n else None,
                "mean": None, "dist_pct": None, "n": n,
                "note": f"chua du du lieu ({n}<{BEAR_MIN})"}
    win = seq[-BEAR_WINDOW:]
    mean = float(sum(win) / len(win))
    price = float(win[-1])
    dist = (price / mean - 1.0) * 100.0 if mean else None
    return {"ok": True, "is_bear": bool(price < mean), "price": price,
            "mean": mean, "dist_pct": dist, "n": n, "note": ""}


def trailing_vol_30d(closes) -> float:
    """Vol nam hoa tu 180 log-return 4h gan nhat; nan khi thieu du lieu."""
    try:
        c = pd.Series(np.asarray(list(closes), dtype=float))
    except (TypeError, ValueError):
        return float("nan")
    c = c[np.isfinite(c.to_numpy())]
    if len(c) < VOL_MIN + 1:
        return float("nan")
    lr = np.log(c.to_numpy()[1:] / c.to_numpy()[:-1])
    lr = lr[np.isfinite(lr)][-VOL_WINDOW:]
    if len(lr) < VOL_MIN:
        return float("nan")
    sd = float(np.std(lr, ddof=1))
    return sd * math.sqrt(PER_YEAR_4H) * 100.0 if sd > 0 else 0.0


def trailing_vol_from_1h(closes) -> float:
    """Vol nam hoa tu 720 log-return 1h gan nhat; nan khi thieu du lieu."""
    try:
        c = pd.Series(np.asarray(list(closes), dtype=float))
    except (TypeError, ValueError):
        return float("nan")
    c = c[np.isfinite(c.to_numpy())]
    if len(c) < VOL1H_MIN + 1:
        return float("nan")
    lr = np.log(c.to_numpy()[1:] / c.to_numpy()[:-1])
    lr = lr[np.isfinite(lr)][-VOL1H_WINDOW:]
    if len(lr) < VOL1H_MIN:
        return float("nan")
    sd = float(np.std(lr, ddof=1))
    return sd * math.sqrt(PER_YEAR_1H) * 100.0 if sd > 0 else 0.0


def monthly_vol_dist(df: pd.DataFrame) -> list[float]:
    """1 diem vol / thang lich (bar cuoi thang), causal, tu 2021."""
    if df is None or not len(df):
        return []
    d = df[pd.to_datetime(df["open_time"], utc=True) >= HIST_START].copy()
    if not len(d):
        return []
    closes = d["close"].to_numpy(float)
    lr = np.full(len(d), np.nan)
    lr[1:] = np.log(closes[1:] / closes[:-1])
    s = pd.Series(lr).shift(1).rolling(VOL_WINDOW, min_periods=VOL_MIN).std(ddof=1)
    vol = s.to_numpy(float) * math.sqrt(PER_YEAR_4H) * 100.0
    d = d.assign(_vol=vol).dropna(subset=["_vol"])
    if not len(d):
        return []
    d = d.assign(_m=pd.to_datetime(d["open_time"], utc=True).dt.strftime("%Y-%m"))
    return [float(g["_vol"].iloc[-1]) for _, g in d.groupby("_m", sort=True)]


def flush_series(df: pd.DataFrame) -> pd.Series:
    """Boolean flush moi bar 4h (causal, khop oc_edgedecay)."""
    if df is None or not len(df):
        return pd.Series([], dtype=bool)
    closes = pd.to_numeric(df["close"], errors="coerce").to_numpy(float)
    lr = np.full(len(df), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        lr[1:] = np.log(closes[1:] / closes[:-1])
    sig = pd.Series(lr).shift(1).rolling(FLUSH_WIN, min_periods=FLUSH_MIN).std(ddof=1).to_numpy(float)
    fl = (sig > 0) & np.isfinite(lr) & (lr <= -FLUSH_K * sig)
    return pd.Series(np.where(np.isfinite(lr) & np.isfinite(sig), fl, False), index=df.index)


def monthly_flush_dist(df: pd.DataFrame, fl: pd.Series) -> list[int]:
    """So flush / thang lich tu 2021 (causal)."""
    if df is None or not len(df) or fl is None or not len(fl):
        return []
    d = df.assign(_fl=np.asarray(fl, dtype=int))
    d = d[pd.to_datetime(d["open_time"], utc=True) >= HIST_START]
    if not len(d):
        return []
    d = d.assign(_m=pd.to_datetime(d["open_time"], utc=True).dt.strftime("%Y-%m"))
    return [int(g["_fl"].sum()) for _, g in d.groupby("_m", sort=True)]


def pct_le(dist, val) -> float | None:
    try:
        d = np.asarray(list(dist), dtype=float)
        v = float(val)
    except (TypeError, ValueError):
        return None
    d = d[np.isfinite(d)]
    if not len(d) or not math.isfinite(v):
        return None
    return float(100.0 * np.mean(d <= v))


def p10_p50_p90(dist) -> tuple[float | None, ...]:
    try:
        d = np.asarray(list(dist), dtype=float)
        d = d[np.isfinite(d)]
        if not len(d):
            return (None, None, None)
        return (float(np.percentile(d, 10)), float(np.percentile(d, 50)), float(np.percentile(d, 90)))
    except (TypeError, ValueError):
        return (None, None, None)


def p25_p75(dist) -> tuple[float | None, float | None]:
    """p25/p75 tu cung lich su thang (cho activity thap/binh thuong/cao)."""
    try:
        d = np.asarray(list(dist), dtype=float)
        d = d[np.isfinite(d)]
        if not len(d):
            return (None, None)
        return (float(np.percentile(d, 25)), float(np.percentile(d, 75)))
    except (TypeError, ValueError):
        return (None, None)


def classify_activity(total_cur, total_hist) -> tuple[str, float | None, float | None]:
    """THAP neu < p25, CAO neu > p75, con lai BINH THUONG; thieu lich su -> khong ro.

    Tra ve (activity, p25, p75). Bien giua [p25, p75] la BINH THUONG (bao gom bang).
    """
    try:
        cur = int(total_cur)
    except (TypeError, ValueError):
        return ("khong ro", None, None)
    p25, p75 = p25_p75(total_hist or [])
    if p25 is None or p75 is None:
        return ("khong ro", p25, p75)
    if cur < p25:
        return ("thap", p25, p75)
    if cur > p75:
        return ("cao", p25, p75)
    return ("binh thuong", p25, p75)


def get_live_btc_opens():
    """BTC 4h opens live qua shared kline cache; raise khi API chet."""
    from bot.bybit_v5 import MAINNET, Bybit, cached_call  # noqa: import-outside-toplevel

    pub = Bybit(base=MAINNET)  # public only, khong can key
    opens, _hit = cached_call("BTCUSDT", "opens_4h", lambda: pub.klines_4h_opens("BTCUSDT"))
    return list(opens)


def _rows_to_df(rows) -> pd.DataFrame | None:
    """Bybit kline rows (newest-first) -> DataFrame open_time/open/high/low/close, sort UTC."""
    try:
        rows = list(rows or [])
    except TypeError:
        return None
    if not rows:
        return None
    recs = []
    for r in rows:
        try:
            ms = int(r[0])
            recs.append((ms, float(r[1]), float(r[2]), float(r[3]), float(r[4])))
        except (TypeError, ValueError, IndexError):
            continue
    if not recs:
        return None
    df = pd.DataFrame(recs, columns=["_ms", "open", "high", "low", "close"])
    df["open_time"] = pd.to_datetime(df["_ms"], unit="ms", utc=True)
    df = df.dropna(subset=["open_time", "open", "close"])
    df = df.sort_values("open_time").drop_duplicates("open_time", keep="last")
    return df[["open_time", "open", "high", "low", "close"]].reset_index(drop=True)


def _drop_incomplete(df: pd.DataFrame | None, interval_ms: int, now_ms: int | None = None) -> pd.DataFrame | None:
    """Loai bar dang hinh thanh (open + interval > now); giu cac bar da dong."""
    if df is None or not len(df):
        return df
    try:
        now = int(now_ms) if now_ms is not None else int(time.time() * 1000)
        ms = pd.to_datetime(df["open_time"], utc=True).astype("int64") // 1_000_000
        keep = (ms.to_numpy() + int(interval_ms)) <= int(now)
        out = df[np.asarray(keep)].reset_index(drop=True)
        return out if len(out) else None
    except Exception:
        return df


def _fetch_recent_rows(pub, symbol: str, interval: str, want_n: int) -> list:
    """Nhung kline rows moi nhat (newest-first, kem bar dang hinh thanh) qua public endpoint.

    Phan trang bang con tro `end` (giong klines_4h_opens): moi batch limit<=1000.
    """
    rows: list = []
    end = None
    want = max(1, int(want_n))
    while len(rows) < want:
        batch_limit = min(1000, want - len(rows))
        kw: dict = dict(category="linear", symbol=symbol, interval=interval, limit=batch_limit)
        if end is not None:
            kw["end"] = end
        batch = pub.public("/v5/market/kline", **kw)["list"]
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < batch_limit:
            break
        oldest = min(int(r[0]) for r in batch)
        nxt = oldest - 1
        if end is not None and nxt >= int(end):
            break
        end = nxt
    return rows


def fetch_live_4h_df(sym: str, cache_dir=None, ttl: float = LIVE_TTL) -> pd.DataFrame | None:
    """45 ngay 4h live (public, cached); None khi API chet. Khong bao gio raise ngoai fetch."""
    from bot.bybit_v5 import MAINNET, Bybit, cached_call  # noqa: import-outside-toplevel

    pub = Bybit(base=MAINNET)  # public only, khong can key

    def _fetch():
        return _fetch_recent_rows(pub, sym, "240", LIVE_4H_BARS)

    rows, _hit = cached_call(sym, "live_4h_45d", _fetch, cache_dir=cache_dir, ttl=float(ttl))
    df = _rows_to_df(rows)
    return _drop_incomplete(df, MS_4H)


def fetch_live_1h_df(sym: str, cache_dir=None, ttl: float = LIVE_TTL) -> pd.DataFrame | None:
    """45 ngay 1h live (public, cached) cho vol; None khi API chet."""
    from bot.bybit_v5 import MAINNET, Bybit, cached_call  # noqa: import-outside-toplevel

    pub = Bybit(base=MAINNET)  # public only, khong can key

    def _fetch():
        return _fetch_recent_rows(pub, sym, "60", LIVE_1H_BARS)

    rows, _hit = cached_call(sym, "live_1h_45d", _fetch, cache_dir=cache_dir, ttl=float(ttl))
    df = _rows_to_df(rows)
    return _drop_incomplete(df, MS_1H)


def _as_live_df(obj) -> pd.DataFrame | None:
    """Chuan hoa fetcher output (test fake): DataFrame giu nguyen, rows -> DataFrame."""
    if obj is None:
        return None
    if isinstance(obj, pd.DataFrame):
        try:
            df = obj.copy()
            if "open_time" not in df.columns or "close" not in df.columns:
                return None
            df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
            for c in ("open", "high", "low", "close"):
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            if "open" not in df.columns:
                df["open"] = df["close"]
            if "high" not in df.columns:
                df["high"] = df["close"]
            if "low" not in df.columns:
                df["low"] = df["close"]
            df = df.dropna(subset=["open_time", "close"]).sort_values("open_time").reset_index(drop=True)
            return df if len(df) else None
        except Exception:
            return None
    try:
        return _rows_to_df(obj)
    except Exception:
        return None


def extend_with_live(local: pd.DataFrame | None, live: pd.DataFrame | None) -> pd.DataFrame | None:
    """Noi live vao sau local (chi cac bar live > local max); khong ghi de lich su."""
    live = _as_live_df(live)
    if live is None or not len(live):
        return local
    if local is None or not len(local):
        return live
    try:
        lmax = pd.to_datetime(local["open_time"], utc=True).max()
        lv = live[pd.to_datetime(live["open_time"], utc=True) > lmax].copy()
        if not len(lv):
            return local
        out = pd.concat([local, lv], ignore_index=True)
        out = out.sort_values("open_time").drop_duplicates("open_time", keep="last").reset_index(drop=True)
        return out
    except Exception:
        return local


def summarize(root: Path = ROOT, live: bool = True, fetch_4h=None, fetch_1h=None,
              cache_dir=None) -> dict:
    """Doc dia phuong + live 45 ngay (optional). Khong bao gio raise.

    fetch_4h(sym)/fetch_1h(sym): injectable cho tests (fake fetcher) - tra ve
    DataFrame (open_time/open/high/low/close) hoac Bybit rows; None = that bai.
    Mac dinh (None) dung fetch_live_*_df qua cached public helpers.
    live=False: offline hoan toan (daily_status).
    """
    root = Path(root)
    local = {}
    for s in SYMS:
        try:
            local[s] = load_local_4h(root, s)
        except Exception:
            local[s] = None
    # --- (1) bear: live truoc, local fallback ---
    live_ok, opens, stale_note = False, None, ""
    if live:
        try:
            opens = get_live_btc_opens()
            live_ok = bool(opens)
        except Exception:
            opens, live_ok = None, False
    local_asof = None
    try:
        btc = local.get("BTCUSDT")
        if btc is not None and len(btc):
            local_asof = pd.to_datetime(btc["open_time"], utc=True).max()
    except Exception:
        local_asof = None
    if not live_ok:
        btc = local.get("BTCUSDT")
        if btc is not None and len(btc):
            opens = btc["open"].tolist()
        if live:
            stale_note = f"du lieu cu (local {local_asof.isoformat() if local_asof is not None else 'n/a'})"
    bear = bear_state(opens or [])
    # --- live 4h/1h mo rong 45 ngay ---
    eff, live1h, hist_live_any = {}, {}, False
    for s in SYMS:
        df = local.get(s)
        live4 = None
        if live:
            try:
                if fetch_4h is not None:
                    live4 = _as_live_df(fetch_4h(s))
                else:
                    live4 = fetch_live_4h_df(s, cache_dir=cache_dir)
            except Exception:
                live4 = None
        ext = extend_with_live(df, live4) if live4 is not None else df
        if live4 is not None and ext is not df and df is not None:
            try:
                if len(ext) > len(df):
                    hist_live_any = True
            except TypeError:
                pass
        elif live4 is not None and df is None and ext is not None and len(ext):
            hist_live_any = True
        eff[s] = ext
        if live:
            try:
                if fetch_1h is not None:
                    l1 = _as_live_df(fetch_1h(s))
                else:
                    l1 = fetch_live_1h_df(s, cache_dir=cache_dir)
                live1h[s] = l1
            except Exception:
                live1h[s] = None
        else:
            live1h[s] = None
    try:
        mx = None
        for s in SYMS:
            df = eff.get(s)
            if df is not None and len(df):
                m = pd.to_datetime(df["open_time"], utc=True).max()
                if mx is None or m > mx:
                    mx = m
        asof = mx
    except Exception:
        asof = local_asof
    hist_note = ""
    if live and not hist_live_any:
        hist_note = f"du lieu cu (local {local_asof.isoformat() if local_asof is not None else 'n/a'})"
    # --- (2)(3) vol + flush tu series mo rong (live neu co, local fallback) ---
    vols, flushes = {}, {}
    for s in SYMS:
        df = eff.get(s)
        if df is None or not len(df):
            vols[s] = {"ok": False, "cur": None, "pct": None, "hist_n": 0,
                       "p10": None, "p50": None, "p90": None}
            flushes[s] = {"ok": False, "cur30d": None, "hist_n": 0,
                          "p10": None, "p25": None, "p50": None, "p75": None, "p90": None}
            continue
        cur_vol, vol_src = None, "4h"
        l1 = live1h.get(s)
        if l1 is not None and len(l1):
            try:
                v1 = trailing_vol_from_1h(l1["close"].tolist())
                if math.isfinite(v1):
                    cur_vol, vol_src = float(v1), "1h-live"
            except Exception:
                cur_vol, vol_src = None, "4h"
        if cur_vol is None:
            try:
                cur_vol = trailing_vol_30d(df["close"].tolist())
            except Exception:
                cur_vol = float("nan")
        hv = monthly_vol_dist(df)
        p10, p50, p90 = p10_p50_p90(hv)
        vols[s] = {"ok": bool(cur_vol is not None and math.isfinite(cur_vol)) and bool(len(hv)),
                   "cur": float(cur_vol) if cur_vol is not None and math.isfinite(cur_vol) else None,
                   "pct": pct_le(hv, cur_vol), "hist_n": len(hv),
                   "p10": p10, "p50": p50, "p90": p90, "src": vol_src}
        fl = flush_series(df)
        cur30 = int(np.asarray(fl, dtype=int)[-VOL_WINDOW:].sum()) if len(fl) else None
        hm = monthly_flush_dist(df, fl)
        f10, f50, f90 = p10_p50_p90(hm)
        f25, f75 = p25_p75(hm)
        flushes[s] = {"ok": cur30 is not None and bool(len(hm)),
                      "cur30d": cur30, "hist_n": len(hm),
                      "p10": f10, "p25": f25, "p50": f50, "p75": f75, "p90": f90}
    # --- (4) activity tu TOTAL (p25/p75) ---
    total_hist = None
    try:
        per_sym = {}
        for s in SYMS:
            df = eff.get(s)
            if df is None or not len(df):
                continue
            fl = flush_series(df)
            d = df.assign(_fl=np.asarray(fl, dtype=int))
            d = d[pd.to_datetime(d["open_time"], utc=True) >= HIST_START]
            d = d.assign(_m=pd.to_datetime(d["open_time"], utc=True).dt.strftime("%Y-%m"))
            per_sym[s] = d.groupby("_m")["_fl"].sum()
        if per_sym:
            tot = pd.concat(per_sym.values(), axis=1).fillna(0).sum(axis=1)
            total_hist = [int(x) for x in tot.tolist()]
    except Exception:
        total_hist = None
    total_cur = sum((flushes[s].get("cur30d") or 0) for s in SYMS
                    if flushes[s].get("cur30d") is not None)
    t10, t50, t90 = p10_p50_p90(total_hist or [])
    t25, t75 = p25_p75(total_hist or [])
    activity, _a25, _a75 = classify_activity(total_cur, total_hist or [])
    if activity == "thap":
        pnl = ("thang yen tinh: it flush -> it dip trade (vd H7 oc_edgedecay: 315 trade/thang, "
               "edge con nguyen) nen P&L thang co the thap, khong phai edge hong")
    elif activity == "cao":
        pnl = ("thang nhieu flush: nhieu co hoi dip (vd H8: 582 trade/thang) nhung chat luong "
               "moi trade kem (rung -9bp) nen cho nhieu trade, giu ky luat TP/SL")
    elif activity == "binh thuong":
        pnl = ("thang binh thuong: so co hoi dip gan muc lich su (vd H9 tro lai binh thuong), "
               "P&L ky vong quanh muc trung binh, thang yen tinh van khong phai edge hong")
    else:
        pnl = "chua du du lieu de danh gia P&L thang"
    return {"bear": bear, "bear_live": bool(live_ok), "bear_note": stale_note,
            "hist_live": bool(hist_live_any), "hist_note": hist_note,
            "local_asof": local_asof.isoformat() if local_asof is not None else None,
            "asof": asof.isoformat() if asof is not None else None,
            "vols": vols, "flushes": flushes,
            "total_cur30d": int(total_cur), "total_hist_n": len(total_hist or []),
            "total_p10": t10, "total_p25": t25, "total_p50": t50,
            "total_p75": t75, "total_p90": t90,
            "activity": activity, "pnl_line": pnl}


def format_vi(sm: dict) -> str:
    """Readout tieng Viet 1 trang."""
    L = ["THI TRUONG HIEN TAI (chi doc, khong dat lenh)"]
    b = sm.get("bear", {})
    src = "live" if sm.get("bear_live") else (sm.get("bear_note") or "du lieu cu")
    if b.get("ok"):
        state = ("BEAR: book long bi halved (gia < mean 1200 bar)" if b["is_bear"]
                 else "khong bear: book long full size (gia >= mean 1200 bar)")
        L.append(f"1) Bear-book filter [{src}]: BTC {b['price']:,.1f} vs mean1200 {b['mean']:,.1f} "
                 f"({b['dist_pct']:+.2f}%, n={b['n']}) -> {state}.")
    else:
        L.append(f"1) Bear-book filter [{src}]: {b.get('note', 'n/a')} (giua nguyen size).")
    L.append("2) Vol 30d hien tai (nam hoa, %/nam; uu tien 1h-live, fallback 4h mo rong) + percentile vs thang lich 2021-2026:")
    for s in SYMS:
        v = sm.get("vols", {}).get(s, {})
        if v.get("ok"):
            L.append(f"   - {s}: {v['cur']:.1f}% [{v.get('src', '4h')}] (pct {v['pct']:.0f}/100, lich su p10/p50/p90 "
                     f"{v['p10']:.1f}/{v['p50']:.1f}/{v['p90']:.1f}, n={v['hist_n']} thang)")
        else:
            L.append(f"   - {s}: n/a (thieu du lieu local)")
    L.append("3) Flush 2.5-sigma 4h trong 30 ngay qua vs phan phoi thang lich su (so flush/thang):")
    for s in SYMS:
        f = sm.get("flushes", {}).get(s, {})
        if f.get("ok") and f.get("p25") is not None:
            L.append(f"   - {s}: {f['cur30d']} flush/30d (lich su p10/p25/p50/p75/p90 "
                     f"{f['p10']:.0f}/{f['p25']:.0f}/{f['p50']:.0f}/{f['p75']:.0f}/{f['p90']:.0f}, n={f['hist_n']} thang)")
        elif f.get("ok"):
            L.append(f"   - {s}: {f['cur30d']} flush/30d (lich su p10/p50/p90 "
                     f"{f['p10']:.0f}/{f['p50']:.0f}/{f['p90']:.0f}, n={f['hist_n']} thang)")
        else:
            L.append(f"   - {s}: n/a (thieu du lieu local)")
    t10, t25, t50, t75, t90 = (sm.get("total_p10"), sm.get("total_p25"), sm.get("total_p50"),
                               sm.get("total_p75"), sm.get("total_p90"))
    if t10 is not None and t25 is not None:
        L.append(f"   TOTAL 5 coin: {sm['total_cur30d']} flush/30d (lich su p10/p25/p50/p75/p90 "
                 f"{t10:.0f}/{t25:.0f}/{t50:.0f}/{t75:.0f}/{t90:.0f}, n={sm['total_hist_n']} thang)")
    elif t10 is not None:
        L.append(f"   TOTAL 5 coin: {sm['total_cur30d']} flush/30d (lich su p10/p50/p90 "
                 f"{t10:.0f}/{t50:.0f}/{t90:.0f}, n={sm['total_hist_n']} thang)")
    else:
        L.append("   TOTAL 5 coin: n/a")
    L.append(f"4) Dip activity thang nay: {sm.get('activity', 'khong ro').upper()} - {sm.get('pnl_line', '')}")
    L.append("   (nguong: THAP < p25, BINH THUONG p25-p75, CAO > p75 cua cung lich su thang; "
             "oc_edgedecay REPORT.md: H7 tram lang it co hoi nhung edge con nguyen; "
             "H8 nhieu flush nhung moi trade yeu; H9 tro lai binh thuong. "
             "Thang yen tinh = it trade, khong phai edge hong.)")
    if sm.get("hist_live"):
        if sm.get("asof"):
            L.append(f"   Du lieu moi nhat (live, mo rong 45 ngay): {sm['asof']}.")
    else:
        if sm.get("asof"):
            L.append(f"   Du lieu local moi nhat: {sm['asof']}.")
        if sm.get("hist_note") or sm.get("bear_note"):
            L.append(f"   ({sm.get('hist_note') or sm.get('bear_note')})")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Thi truong hien tai (chi doc).")
    ap.add_argument("--root", default=None, help="workspace root (mac dinh: repo)")
    ap.add_argument("--no-live", action="store_true", help="chi dung local (offline)")
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else ROOT
    print(format_vi(summarize(root, live=not a.no_live)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
