"""oc_bookoos: clean OOS scorer for the FULL deployed G2 book (book + dip) on genuinely-new data.

Window: 2026-09-30 00:00 UTC (first midnight after all member rows the deployed
book needs exist - verified below) to the last complete UTC day at runtime
(expected 2026-10-06 00:00 exclusive = 6 days, genuinely new; research ends 2026-09-23).
Label: clean OOS, tiny sample.

Books (honest, prospective-only): the deployed G2 book is 0.8 x O1 + 0.2 x CB
(scripts/forward_trade.py v321_R2 / forward_trade_phase.py: live_books("v240_O1")
and live_books("v285_CB") on their common index), where each member row is
converted to research units as (perp_weight + spot_weight) / (0.8 * portfolio_scale)
(scripts/forward_v205.live_books, scripts/v285_cb_advisor.py). ONLY rows with
mode == "prospective", no error, valid perp/spot weights, logged <= 6 h after
their decision_bar_close (scripts/advisor_shadow.PROSPECTIVE_MAX_LAG) are used.
No backfill rows (mode == "backfill", even as-of), no refit, no parameter change.
Gaps where no common prospective row exists (missed cycles later backfilled) are
forward-filled from the last common prospective book (hold last target, as
forward_trade's reindex+ffill does); the gaps are listed in results.json.

First-bar verification (see load_prospective_books): v240_O1 prospective rows start
2026-09-28 16:00 (t index), v285_CB prospective rows start 2026-09-29 16:00 (t index);
first common prospective t is 2026-09-29 16:00. The first traded HOLDING bar
2026-09-30 00:00 needs the book at t = 2026-09-29 20:00, which exists for both
members (prospective, lag <= 6 h). Scoring starts at the first midnight
2026-09-30 00:00 for clean daily equity (earlier common bars 09-29 16:00/20:00 exist
but would give a partial day).

Engine: research/diagnostics/oc_expiry4p/oc_expiry4p.py 4-phase G2 harness
(phase_offset_full prep + pipe_setup("v321", agents OFF) + kd = 1.7 corr-size +
gross cap G = 2.0 + win_start = 5; gate fees maker 0.0002 / taker 0.00055;
adverse long funding 0.0001 per settlement / shorts 0; stop-first; 1m-marked DD),
BUT with two stated omissions vs the historical v421 row: (1) no R2/G2 agent tables
(size 1.0, default TP - the walk-forward tables end 2026-09-23 with no OOS rows,
so there is nothing honest to look up); (2) no bear-book halving (live paper
forward_trade v285/v321_R2 trades the raw 0.8 O1 + 0.2 CB blend; the bear filter
is research-only and needs a 1200-bar BTC baseline). Books are the prospective
blend above, forward-filled to each shifted clock.

Data: fresh public 1m ONLY under data/raw/majors_1m_oos_20261006/ (Binance vision
daily zips, CHECKSUM-verified). Reuses the oc_oos12d fetcher to EXTEND the same
directory weekly (new days appended, manifest rewritten). 4h opens derived from 1m
in-memory. Warmup: 75 days of local intraday archive (read-only) for sig4/vol.

Expectation band: 10000 random N-day windows from v421_runs.pkl R2B1D17BFG2 mixed
daily (same convention as oc_oos12d; the band is the historical full-G2 with
bear+agents, so it is an approximation for this no-agent/no-bear OOS leg).
OOS is ONE tiny sample -> no gate claim.

Usage (weekly rerun, one command):
  .venv/Scripts/python.exe research/diagnostics/oc_bookoos/score_oos.py --fetch --run
(fetch extends the 1m dir; without --fetch a stale manifest fails loudly with the
exact re-fetch command). Tests: .venv/Scripts/python.exe -m pytest tests/test_oc_bookoos.py -q
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import math
import time
import zipfile
from datetime import timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OOS_DIR = ROOT / "data/raw/majors_1m_oos_20261006"
SHADOW = ROOT / "artifacts/research/advisor_shadow/shadow.jsonl"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
OOS_START = pd.Timestamp("2026-09-30 00:00", tz="UTC")
VISION = "https://data.binance.vision/data/futures/um"
KLINE_COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
                 "quote_volume", "num_trades", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
WARM_DAYS = 75
N_BOOT = 10000
SEED = 12
MAKER = 0.0002
TAKER = 0.00055
MAX_LAG_H = 6.0


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def oos_end() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC").floor("1D")


def day_list(a: pd.Timestamp, b_excl: pd.Timestamp) -> list[str]:
    out, t = [], a.floor("1D")
    while t < b_excl:
        out.append(t.strftime("%Y-%m-%d"))
        t += pd.Timedelta(days=1)
    return out


def parse_vision_csv(payload: bytes) -> pd.DataFrame:
    text = payload.decode("utf-8", errors="strict")
    first = text.split("\n", 1)[0]
    has_header = first.split(",", 1)[0].strip() == "open_time"
    frame = pd.read_csv(io.StringIO(text), header=None, skiprows=1 if has_header else 0)
    if frame.shape[1] != len(KLINE_COLUMNS):
        raise ValueError(f"unexpected column count {frame.shape[1]}")
    frame.columns = KLINE_COLUMNS
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    for c in ("open", "high", "low", "close", "volume"):
        frame[c] = pd.to_numeric(frame[c], errors="raise")
    return frame[["open_time", "open", "high", "low", "close", "volume"]]


def fetch_oos_1m(end: pd.Timestamp) -> dict:
    """Extend the shared OOS 1m dir (same layout/fetcher as oc_oos12d) to cover 2026-09-24 .. end."""
    OOS_START_ALL = pd.Timestamp("2026-09-24 00:00", tz="UTC")
    OOS_DIR.mkdir(parents=True, exist_ok=True)
    sess, manifest, days = requests.Session(), {"symbols": {}}, day_list(OOS_START_ALL, end)
    for sym in SYMS:
        frames = []
        files = []
        for d in days:
            url = f"{VISION}/daily/klines/{sym}/1m/{sym}-1m-{d}.zip"
            for attempt in (0, 1, 2):
                r = sess.get(url, timeout=120)
                if r.status_code == 404:
                    raise RuntimeError(f"{url}: 404 (day not yet archived?)")
                if r.status_code in (429, 418):
                    time.sleep(10 + 20 * attempt)
                    continue
                r.raise_for_status()
                break
            c = sess.get(url + ".CHECKSUM", timeout=60)
            c.raise_for_status()
            expect = c.text.split()[0].strip().lower()
            got = hashlib.sha256(r.content).hexdigest()
            if got != expect:
                raise RuntimeError(f"{sym} {d}: CHECKSUM mismatch {got} != {expect}")
            with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                names = [n for n in zf.namelist() if n.endswith(".csv")]
                if len(names) != 1:
                    raise ValueError(f"{url}: expected 1 csv, got {names}")
                with zf.open(names[0]) as f:
                    frames.append(parse_vision_csv(f.read()))
            files.append({"day": d, "zip_sha256": got, "url": url})
            time.sleep(0.5)
        m = pd.concat(frames, ignore_index=True).drop_duplicates("open_time").sort_values("open_time")
        m = m[(m["open_time"] >= OOS_START_ALL) & (m["open_time"] < end)].reset_index(drop=True)
        exp = pd.date_range(OOS_START_ALL, end - pd.Timedelta(minutes=1), freq="1min", tz="UTC")
        missing = exp.difference(pd.DatetimeIndex(m["open_time"]))
        if len(missing):
            raise RuntimeError(f"{sym}: {len(missing)} missing 1m bars e.g. {missing[:3].tolist()}")
        if ((m["high"] < m["low"]) | (m["close"] <= 0)).any():
            raise RuntimeError(f"{sym}: OHLC sanity failed")
        p = OOS_DIR / f"{sym}_1m_oos.parquet"
        m.to_parquet(p, index=False)
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        manifest["symbols"][sym] = {"rows": int(len(m)), "first": str(m["open_time"].iloc[0]),
                                    "last": str(m["open_time"].iloc[-1]), "parquet": p.name,
                                    "parquet_sha256": h, "days": days, "files": files}
    manifest.update({"source": "Binance data.binance.vision futures/um daily 1m zips, CHECKSUM-verified",
                     "window": [str(OOS_START_ALL), str(end)], "fetched_at": pd.Timestamp.now(tz="UTC").isoformat()})
    (OOS_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"fetched/extended OOS 1m 2026-09-24..{(end - pd.Timedelta(days=1)).date()} -> {OOS_DIR}", flush=True)
    return manifest


def load_minutes(end: pd.Timestamp) -> dict:
    warm0 = OOS_START - pd.Timedelta(days=WARM_DAYS)
    out = {}
    for sym in SYMS:
        hist_frames = []
        if sym == "BTCUSDT":
            d = ROOT / "data/raw/btc_intraday_20260924"
            pats = sorted(d.glob("klines_1m_20*.parquet"))
        else:
            d = ROOT / "data/raw/majors_intraday_20260924"
            pats = sorted(d.glob(f"{sym}_1m_20*.parquet"))
        for f in pats:
            w = pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"])
            w["open_time"] = pd.to_datetime(w["open_time"], utc=True)
            w = w[(w["open_time"] >= warm0) & (w["open_time"] < OOS_START)]
            if len(w):
                hist_frames.append(w)
        oos = pd.read_parquet(OOS_DIR / f"{sym}_1m_oos.parquet")
        oos["open_time"] = pd.to_datetime(oos["open_time"], utc=True)
        full = pd.concat(hist_frames + [oos], ignore_index=True).drop_duplicates("open_time").sort_values("open_time")
        full = full.set_index("open_time").sort_index()
        out[sym] = full[["open", "high", "low", "close"]].astype(float)
    return out


def _valid_weights(rec: dict) -> bool:
    for key in ("perp_weight", "spot_weight"):
        v = rec.get(key)
        if not isinstance(v, dict):
            return False
        try:
            if any(isinstance(x, bool) or not math.isfinite(float(x)) for x in v.values()):
                return False
        except (TypeError, ValueError):
            return False
    return True


def load_prospective_books() -> tuple[pd.DataFrame, dict]:
    """Deployed G2 blend from prospective-only member rows. Returns (std_books, info)."""
    rows = []
    for line in SHADOW.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            if isinstance(r, dict):
                rows.append(r)
        except ValueError:
            continue
    per_member: dict[str, dict] = {}
    lag_max: dict[str, float] = {}
    counts: dict[str, int] = {}
    for cand in ("v240_O1", "v285_CB"):
        out = {}
        worst = 0.0
        for r in rows:
            if r.get("candidate") != cand or r.get("error"):
                continue
            if "perp_weight" not in r or not _valid_weights(r):
                continue
            if r.get("mode") != "prospective":
                continue
            try:
                dec = pd.Timestamp(r["decision_bar_close"])
                log = pd.Timestamp(r["logged_at"])
            except (ValueError, TypeError):
                continue
            lag_h = (log - dec).total_seconds() / 3600.0
            if not np.isfinite(lag_h) or lag_h < -0.1 or lag_h > MAX_LAG_H + 1e-9:
                continue
            worst = max(worst, float(lag_h))
            t = dec + pd.Timedelta(milliseconds=1) - pd.Timedelta(hours=4)
            sc = float(r.get("portfolio_scale") or 1.0)
            if not np.isfinite(sc) or sc <= 0:
                continue
            out[t] = {s: (float(r["perp_weight"].get(s, 0.0)) + float(r["spot_weight"].get(s, 0.0))) / (0.8 * sc)
                      for s in SYMS}
        per_member[cand] = out
        lag_max[cand] = round(worst, 3)
        counts[cand] = len(out)
    lo1 = pd.DataFrame.from_dict(per_member["v240_O1"], orient="index").sort_index() if per_member["v240_O1"] else pd.DataFrame(columns=SYMS)
    lcb = pd.DataFrame.from_dict(per_member["v285_CB"], orient="index").sort_index() if per_member["v285_CB"] else pd.DataFrame(columns=SYMS)
    if len(lo1) == 0 or len(lcb) == 0:
        raise RuntimeError("no prospective member rows for v240_O1 and/or v285_CB (shadow.jsonl empty?)")
    common = lo1.index.intersection(lcb.index).sort_values()
    lb = (0.8 * lo1.loc[common] + 0.2 * lcb.loc[common]).sort_index()
    # expected standard 4h grid over the overlap; gaps = backfill-only/missed cycles (forward-filled at score time)
    exp = pd.date_range(common.min(), common.max(), freq="4h", tz="UTC")
    gaps = [str(t) for t in exp if t not in set(common)]
    need_t = OOS_START - pd.Timedelta(hours=4)
    if need_t not in set(lb.index):
        raise RuntimeError(f"OOS_START book t={need_t} has no common prospective row; first common={common.min()}")
    o1_first = lo1.index.min()
    cb_first = lcb.index.min()
    info = {
        "o1_first_t": str(o1_first), "cb_first_t": str(cb_first),
        "first_common_t": str(common.min()), "last_common_t": str(common.max()),
        "n_o1": int(len(lo1)), "n_cb": int(len(lcb)), "n_common": int(len(common)),
        "n_gaps_ffilled": int(len(gaps)), "gaps_ffilled": gaps,
        "lag_max_h": lag_max, "counts": counts,
        "oos_start_holding": str(OOS_START),
        "oos_start_book_t": str(need_t),
        "formula": "0.8 * (perp+spot)/(0.8*scale) [v240_O1] + 0.2 * (perp+spot)/(0.8*scale) [v285_CB], prospective-only, lag<=6h",
    }
    return lb[SYMS], info


def book_episodes(events) -> list:
    """Discrete book position episodes -> [(exit_t, net)] (net>0 = win, after fees; mirrors v213.trade_stats)."""
    pos, out = {}, []
    for e in events:
        k, sym = e.get("kind"), e.get("symbol")
        if k == "book_fill":
            q = abs(e["weight"]) / e["price"]
            pos[sym] = dict(side=1 if e["side"] == "buy" else -1, qty=q,
                            cost=q * e["price"], proceeds=0.0,
                            fees=q * e["price"] * MAKER)
            continue
        o = pos.get(sym)
        if o is None:
            continue
        if k == "book_add":
            q = abs(e["weight"]) / e["price"]
            o["qty"] += q
            o["cost"] += q * e["price"]
            o["fees"] += q * e["price"] * MAKER
        elif k in ("book_reduce", "book_partial"):
            q = min(abs(e["weight"]) / e["price"], o["qty"])
            o["qty"] -= q
            o["proceeds"] += q * e["price"]
            o["fees"] += q * e["price"] * MAKER
        elif k in ("book_stop", "book_tp", "book_close"):
            o["proceeds"] += o["qty"] * e["price"]
            o["fees"] += o["qty"] * e["price"] * (TAKER if k == "book_stop" else MAKER)
            net = (o["side"] * (o["proceeds"] - o["cost"]) - o["fees"]) / o["cost"]
            out.append((pd.Timestamp(e["t"]), float(net)))
            pos.pop(sym)
    return out


def run_phase(shift: int, M: dict, live0: pd.Timestamp, live1: pd.Timestamp, std_books: pd.DataFrame) -> dict:
    import sys
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod_name, hist_name = f"pod_bookoos_{shift}", f"hist_bookoos_{shift}"
    v221_name = f"v221_bookoos_{shift}"
    pod = pof._load(pod_name, ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(hist_name, ROOT / "backend/history_tm.py")
    v221 = pof._load(v221_name, pof.RD / "v221/v221_grid_hysteresis.py")
    eu, v216 = v221.eu, v221.v216
    cap: dict = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
        eq_max=(eq if eq_max is None else eq_max).copy(), stats=stats) or {}
    eu.v110.START, eu.v110.END = live0, live1
    warm0 = OOS_START - pd.Timedelta(days=WARM_DAYS)
    std_idx = pd.date_range(warm0.floor("4h") + pd.Timedelta(hours=shift),
                            live1 + pd.Timedelta(hours=4), freq="4h", tz="UTC")
    opens, prep = pof.prep_idx(M, std_idx, shift, SYMS)
    idx = prep["idx"]
    # prospective G2 blend (no bear halving: live-paper form) forward-filled to this shifted clock
    books = std_books.reindex(idx, method="ffill").fillna(0.0)[list(prep["cols"])]
    kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, list(prep["cols"]), False)
    O, C, sg = prep["O"], prep["C"], prep["sig4"]
    base = kw.pop("sleeve_fill_size", None)
    base_fn = base if callable(base) else (lambda i, a, r, f: 1.0)
    rule, kd = "inv", 1.7
    kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * kd
    kw["risk_mult"] = lambda i, e: 1.0
    kw["sleeve_gross_cap"] = 2.0

    def corr_size(i, a, r, f, base_fn=base_fn, kd=kd):
        m = f - 1
        n = 0
        for b in range(len(prep["cols"])):
            if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                continue
            n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
        return (1.0 / (1 + n)) * kd * float(base_fn(i, a, r, f))

    kw["sleeve_fill_size"] = corr_size
    ev = []
    eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, **kw)
    lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
    first = int(np.argmax(lv))
    base_eq = cap["eq"][first - 1] if first > 0 else 1.0
    rungs = [(pd.Timestamp(e["t"]), float(e["ret"])) for e in ev
             if e.get("kind") in ("rung_tp", "rung_sl", "rung_timeout") and "ret" in e]
    eps = book_episodes(ev)
    n_book_ev = sum(1 for e in ev if str(e.get("kind", "")).startswith("book_"))
    return {"t": [str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
            "eq": (cap["eq"][lv] / base_eq).tolist(), "eq_min": (cap["eq_min"][lv] / base_eq).tolist(),
            "eq_max": (cap["eq_max"][lv] / base_eq).tolist(), "stats": cap.get("stats", {}),
            "rungs": [[str(t), r] for t, r in rungs],
            "book_exits": [[str(t), r] for t, r in eps],
            "n_book_events": int(n_book_ev)}


def hourly_mix(phases: dict, g0: pd.Timestamp, g1: pd.Timestamp):
    grid = pd.date_range(g0, g1, freq="1h")
    es, mns = [], []
    for s in range(4):
        d = phases[str(s)]
        t = pd.to_datetime(pd.Series(d["t"]), utc=True)
        e = pd.Series(d["eq"], index=t).reindex(grid, method="ffill").fillna(1.0)
        lo = (pd.Series(d["eq_min"], index=t - pd.Timedelta(hours=4)).reindex(grid, method="ffill").fillna(1.0))
        hi = (pd.Series(d["eq_max"], index=t - pd.Timedelta(hours=4)).reindex(grid, method="ffill").fillna(1.0))
        es.append(e)
        mns.append(np.minimum(np.minimum(lo, e), hi))
    return sum(es) / 4, sum(mns) / 4


def bootstrap_band(n_days: int) -> dict:
    import pickle
    runs = pickle.loads((RD / "v421/v421_runs.pkl").read_bytes())
    v388 = _load("v388_bookoos", RD / "v388/v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, _mn = v388.mix(runs, "R2B1D17BFG2", g1)
    daily = e.resample("1D").last()
    rets = daily.pct_change().dropna().to_numpy()
    rng = np.random.default_rng(SEED)
    outs, dds = [], []
    for _ in range(N_BOOT):
        i = int(rng.integers(0, len(rets) - n_days + 1))
        w = rets[i:i + n_days]
        outs.append(float(np.prod(1 + w) - 1))
        curve = np.cumprod(np.concatenate([[1.0], 1 + w]))
        dds.append(float(np.max(1 - curve / np.maximum.accumulate(curve))))
    outs = np.array(outs)
    return {"n": N_BOOT, "window_days": int(n_days), "source": "v421_runs.pkl R2B1D17BFG2 mixed hourly->daily",
            "total_pct": {"p5": round(100 * float(np.quantile(outs, 0.05)), 3),
                          "p50": round(100 * float(np.quantile(outs, 0.50)), 3),
                          "p95": round(100 * float(np.quantile(outs, 0.95)), 3)},
            "dd_pct": {"p50": round(100 * float(np.median(dds)), 3),
                       "p95": round(100 * float(np.quantile(dds, 0.95)), 3)}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--bootstrap-only", action="store_true")
    a = ap.parse_args()
    if not (a.fetch or a.run or a.bootstrap_only):
        a.run = True
    end = oos_end()
    assert end > OOS_START, f"no complete OOS day yet (now={end})"
    n_days = int((end - OOS_START).days)
    if a.bootstrap_only:
        print(json.dumps(bootstrap_band(n_days), indent=1))
        return
    if a.fetch or not (OOS_DIR / "manifest.json").exists():
        fetch_oos_1m(end)
    man = json.loads((OOS_DIR / "manifest.json").read_text())
    if str(man["window"][1]) != str(end):
        raise RuntimeError(f"manifest for {man['window'][1]} != needed {end}; re-run with --fetch to extend")
    std_books, book_info = load_prospective_books()
    M = load_minutes(end)
    phases = {}
    for shift in range(4):
        live0, live1 = OOS_START + pd.Timedelta(hours=shift), end + pd.Timedelta(hours=shift)
        d = run_phase(shift, M, live0, live1, std_books)
        phases[str(shift)] = d
        print(f"shift {shift}: eq_end={round(d['eq'][-1], 4)} rungs={len(d['rungs'])} book_exits={len(d['book_exits'])}", flush=True)
    g0 = OOS_START + pd.Timedelta(hours=4)
    e, mn = hourly_mix(phases, g0, end + pd.Timedelta(hours=3))
    daily_eq = e.resample("1D").last()
    daily_min = mn.resample("1D").min()
    peak = np.maximum.accumulate(np.concatenate([[1.0], daily_eq.to_numpy()]))[1:]
    dd_close = float(np.max(1 - daily_eq.to_numpy() / peak)) if len(daily_eq) else 0.0
    dd_mark = float(np.max(1 - np.minimum(daily_eq.to_numpy(), daily_min.to_numpy()) / peak)) if len(daily_eq) else 0.0
    total = float(daily_eq.iloc[-1] - 1) if len(daily_eq) else 0.0
    all_rungs = [(pd.Timestamp(t), float(r)) for s in phases.values() for t, r in s["rungs"]]
    all_rungs.sort()
    all_book = [(pd.Timestamp(t), float(r)) for s in phases.values() for t, r in s["book_exits"]]
    all_book.sort()
    all_tr = all_rungs + all_book
    wr = sum(1 for _, r in all_rungs if r > 0)
    wb = sum(1 for _, r in all_book if r > 0)
    wa = sum(1 for _, r in all_tr if r > 0)
    band = bootstrap_band(n_days)
    import pickle
    runs = pickle.loads((RD / "v421/v421_runs.pkl").read_bytes())
    v388 = _load("v388_bookoos_b", RD / "v388/v388_bot_stop_distance.py")
    g1b = v388.Y1 + pd.Timedelta(hours=12)
    ee, _ = v388.mix(runs, "R2B1D17BFG2", g1b)
    drets = ee.resample("1D").last().pct_change().dropna().to_numpy()
    rng = np.random.default_rng(SEED)
    draws = []
    for _ in range(N_BOOT):
        i = int(rng.integers(0, len(drets) - n_days + 1))
        draws.append(float(np.prod(1 + drets[i:i + n_days]) - 1))
    pctile = round(100 * float(np.mean(np.array(draws) <= total)), 1)
    res = {
        "version": "oc_bookoos",
        "label": "clean OOS, tiny sample",
        "window": {"start": str(OOS_START), "end_exclusive": str(end), "days": n_days},
        "mode": "full G2 book+dip rule-based (prospective 0.8 O1 + 0.2 CB books; no agents size 1.0 default TP; no bear halving; 4 phases)",
        "honesty": {"books": "prospective-only v240_O1 + v285_CB rows (mode=prospective, lag<=6h); no backfill rows used",
                    "backfill_used": False, "refit": False,
                    "agent_tables": "not used (walk-forward R2/G2 tables end 2026-09-23, no OOS rows)",
                    "bear_filter": "not applied (live-paper form, as forward_trade v285/v321_R2)"},
        "books_coverage": book_info,
        "costs": {"maker": MAKER, "taker": TAKER, "funding_long_per_settlement": 0.0001, "funding_short": 0.0,
                  "win_start_minute": 5, "stop_first": True},
        "daily_equity": [[str(k), round(float(v), 6)] for k, v in daily_eq.items()],
        "total_pct": round(100 * total, 3),
        "max_dd_close_pct": round(100 * dd_close, 3),
        "max_dd_1m_pct": round(100 * dd_mark, 3),
        "gate_dd_pct": round(100 * max(dd_close, dd_mark), 3),
        "trades": {"rungs": len(all_rungs), "rung_wins": wr,
                   "rung_win_rate": round(wr / len(all_rungs), 4) if all_rungs else None,
                   "book_episodes": len(all_book), "book_wins": wb,
                   "book_win_rate": round(wb / len(all_book), 4) if all_book else None,
                   "all": len(all_tr), "all_wins": wa,
                   "all_win_rate": round(wa / len(all_tr), 4) if all_tr else None,
                   "book_events": sum(s["n_book_events"] for s in phases.values())},
        "rung_exits": [[str(t), float(r)] for t, r in all_rungs],
        "book_exits": [[str(t), float(r)] for t, r in all_book],
        "expectation_band": band,
        "oos_percentile_vs_band": pctile,
        "phases": phases,
        "data": {"oos_dir": "data/raw/majors_1m_oos_20261006", "manifest": man},
    }
    raw = json.dumps(res, indent=1, default=str)
    (HERE / "results.json").write_text(raw)
    print(f"OOS {n_days}d total {res['total_pct']}% DD {res['gate_dd_pct']}% "
          f"rungs {len(all_rungs)} win {res['trades']['rung_win_rate']} "
          f"books {len(all_book)} win {res['trades']['book_win_rate']} "
          f"all {len(all_tr)} win {res['trades']['all_win_rate']} pctile {pctile} vs band {band['total_pct']}", flush=True)


if __name__ == "__main__":
    main()
