"""Append the frozen trend-advisor state for each new closed 4h bar (prospective paper log).

Public Binance USD-M REST only; advisory, no orders. Rows logged more than 6h
after their bar closed are marked backfill and are not forward evidence.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from agentic_alpha_lab.data.binance_usdm import fetch_klines
import numpy as np
import pandas as pd

from agentic_alpha_lab.research_vf import Context
from agentic_alpha_lab.signals.trend_advisor import advice
from agentic_alpha_lab.vf_families import combo

COMBO_ID = "vf_combo_fast20_don55_10_w0.5_k0.65"
COMBO_PARAMS = dict(fast=20, entry=55, exit=10, gate="none", w=0.5)
COMBO_SCALE = 0.65


def combo_advice(bars4h: pd.DataFrame, daily: pd.DataFrame) -> dict:
    from agentic_alpha_lab.signals.combo_advisor import report
    return report(bars4h, daily)

LOG = Path("artifacts/research/advisor_shadow/shadow.jsonl")
PROSPECTIVE_MAX_LAG = timedelta(hours=6)


def _retry(fn, wait=45):
    """One retry after a pause when Binance rate-limits the IP (HTTP 429/418), so a busy minute does not lose a prospective row."""
    try:
        return fn()
    except Exception as exc:
        if "429" not in repr(exc) and "418" not in repr(exc):
            raise
        import time as _t
        _t.sleep(wait)
        return fn()


FAST = (("v240_advisor", "v240_O1"), ("v285_cb_advisor", "v285_CB"))  # the member advisors all five site pipelines read
BACKFILL_DAYS = 14


def backfill() -> int:
    """Gap check + backfill of the advisors the trade plans read: every 4h decision bar of the last BACKFILL_DAYS (from each candidate's
    first row) that has no valid row gets one, computed AS OF that bar (ADVISOR_ASOF: only bars closed by then, funding up to then;
    the other inputs are joined on the bar time, so nothing after the bar reaches the features). Rows carry asof=True; rows logged more
    than 6h after the bar are mode 'backfill' (not forward evidence, but the trade plans may replay them). The latest closed bar is
    left to the regular fast run."""
    import importlib.util as _u
    rows = [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()] if LOG.exists() else []
    good = {f'{r.get("candidate")}|{r["decision_bar_close"]}' for r in rows if "perp_weight" in r}
    now = datetime.now(timezone.utc)
    latest = pd.Timestamp(now).floor("4h") - pd.Timedelta(milliseconds=1)          # close of the last closed 4h bar
    n_new, n_err = 0, 0
    for mod, cand in FAST:
        mine = [pd.Timestamp(r["decision_bar_close"]) for r in rows if r.get("candidate") == cand and "perp_weight" in r]
        if not mine:
            continue
        first = max(min(mine), latest - pd.Timedelta(days=BACKFILL_DAYS))
        bars = pd.date_range(first, latest - pd.Timedelta(hours=4), freq="4h")
        missing = [t for t in bars if f"{cand}|{t}" not in good]
        if not missing:
            continue
        spec = _u.spec_from_file_location(f"{mod}_bf", Path(__file__).parent / f"{mod}.py")
        m = _u.module_from_spec(spec)
        spec.loader.exec_module(m)
        for t in missing:
            os.environ["ADVISOR_ASOF"] = str(t)
            try:
                rec = _retry(m.advise)
                if str(pd.Timestamp(rec["decision_bar_close"])) != str(t):
                    raise RuntimeError(f"as-of bar mismatch: got {rec['decision_bar_close']}, wanted {t}")
                rec["decision_bar_close"] = str(t)
                rec["asof"] = True
            except Exception as exc:
                rec = dict(candidate=cand, decision_bar_close=str(t), error="backfill: " + repr(exc)[:300], asof=True)
                n_err += 1
            finally:
                os.environ.pop("ADVISOR_ASOF", None)
            lag = now - pd.Timestamp(t).to_pydatetime()
            rec["logged_at"] = now.isoformat()
            rec["mode"] = "prospective" if lag <= PROSPECTIVE_MAX_LAG else "backfill"
            with LOG.open("a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
            n_new += "perp_weight" in rec
            print("backfilled", cand, t, "ok" if "perp_weight" in rec else rec.get("error"), flush=True)
    print(f"backfill: {n_new} rows added, {n_err} errors")
    return 0


def main() -> int:
    now = datetime.now(timezone.utc)
    s = requests.Session()
    bars4h = fetch_klines("BTCUSDT", "4h", now - timedelta(days=500), session=s)
    daily = fetch_klines("BTCUSDT", "1d", now - timedelta(days=800), session=s)
    logged = set()
    if LOG.exists():
        logged = {f'{r.get("candidate")}|{r["decision_bar_close"]}' for r in map(json.loads, filter(str.strip, LOG.read_text().splitlines()))}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if os.environ.get("ADVISOR_SHADOW_BACKFILL") == "1":  # gap check + as-of backfill of missed decision bars (backend cycle, first)
        return backfill()
    if os.environ.get("ADVISOR_SHADOW_FAST") == "1":  # only the advisors the trade plans read (backend cycle, before its plans)
        import importlib.util as _u
        rows = []
        for mod, cand in FAST:
            try:
                _spec = _u.spec_from_file_location(mod, Path(__file__).parent / f"{mod}.py")
                _m = _u.module_from_spec(_spec); _spec.loader.exec_module(_m)
                rows.append(_retry(_m.advise))
            except Exception as exc:  # logged, never silently skipped
                rows.append(dict(candidate=cand, decision_bar_close=str(bars4h["close_time"].iloc[-1]), error=repr(exc)[:300]))
        _append(rows, logged, now)
        return 0
    funding = pd.DataFrame(s.get("https://fapi.binance.com/fapi/v1/fundingRate", params={"symbol": "BTCUSDT", "limit": 1000}, timeout=60).json())
    funding["fundingRate"] = funding["fundingRate"].astype(float)
    funding["fundingTime"] = pd.to_datetime(funding["fundingTime"], unit="ms", utc=True)
    try:
        refresh_alts(s)
    except Exception as exc:  # stale alt data would bias the breadth family; record it in its row instead
        print("alt refresh failed", repr(exc)[:200])
    extra = []
    try:
        import importlib.util as _u
        _spec = _u.spec_from_file_location("v99_advisor", Path(__file__).parent / "v99_advisor.py")
        _m = _u.module_from_spec(_spec); _spec.loader.exec_module(_m)
        extra.append(_m.advise())
    except Exception as exc:  # logged, never silently skipped
        extra.append(dict(candidate="v99_models_portfolio", decision_bar_close=str(bars4h["close_time"].iloc[-1]), error=repr(exc)[:300]))
    try:
        _spec = _u.spec_from_file_location("v104_advisor", Path(__file__).parent / "v104_advisor.py")
        _m = _u.module_from_spec(_spec); _spec.loader.exec_module(_m)
        extra.append(_m.advise())
    except Exception as exc:  # logged, never silently skipped
        extra.append(dict(candidate="v104_models_portfolio", decision_bar_close=str(bars4h["close_time"].iloc[-1]), error=repr(exc)[:300]))
    try:
        _spec = _u.spec_from_file_location("v115_advisor", Path(__file__).parent / "v115_advisor.py")
        _m = _u.module_from_spec(_spec); _spec.loader.exec_module(_m)
        extra.append(_m.advise())
    except Exception as exc:  # logged, never silently skipped
        extra.append(dict(candidate="v115_models_portfolio", decision_bar_close=str(bars4h["close_time"].iloc[-1]), error=repr(exc)[:300]))
    try:
        _spec = _u.spec_from_file_location("v127_advisor", Path(__file__).parent / "v127_advisor.py")
        _m = _u.module_from_spec(_spec); _spec.loader.exec_module(_m)
        extra.append(_m.advise())
    except Exception as exc:  # logged, never silently skipped
        extra.append(dict(candidate="v127_tranched_portfolio", decision_bar_close=str(bars4h["close_time"].iloc[-1]), error=repr(exc)[:300]))
    try:
        _spec = _u.spec_from_file_location("v133_advisor", Path(__file__).parent / "v133_advisor.py")
        _m = _u.module_from_spec(_spec); _spec.loader.exec_module(_m)
        extra.append(_m.advise())
    except Exception as exc:  # logged, never silently skipped
        extra.append(dict(candidate="v133_deploy_v2", decision_bar_close=str(bars4h["close_time"].iloc[-1]), error=repr(exc)[:300]))
    try:
        _spec = _u.spec_from_file_location("v144_advisor", Path(__file__).parent / "v144_advisor.py")
        _m = _u.module_from_spec(_spec); _spec.loader.exec_module(_m)
        extra.append(_m.advise())
    except Exception as exc:  # logged, never silently skipped
        extra.append(dict(candidate="v144_deploy_v3", decision_bar_close=str(bars4h["close_time"].iloc[-1]), error=repr(exc)[:300]))
    try:
        _spec = _u.spec_from_file_location("v151_advisor", Path(__file__).parent / "v151_advisor.py")
        _m = _u.module_from_spec(_spec); _spec.loader.exec_module(_m)
        extra.append(_retry(_m.advise))
    except Exception as exc:  # logged, never silently skipped
        extra.append(dict(candidate="v151_deploy_v4", decision_bar_close=str(bars4h["close_time"].iloc[-1]), error=repr(exc)[:300]))
    try:
        _spec = _u.spec_from_file_location("v154_advisor", Path(__file__).parent / "v154_advisor.py")
        _m = _u.module_from_spec(_spec); _spec.loader.exec_module(_m)
        extra.append(_m.advise())
    except Exception as exc:  # logged, never silently skipped
        extra.append(dict(candidate="v154_deploy_v5", decision_bar_close=str(bars4h["close_time"].iloc[-1]), error=repr(exc)[:300]))
    try:
        _spec = _u.spec_from_file_location("v233_advisor", Path(__file__).parent / "v233_advisor.py")
        _m = _u.module_from_spec(_spec); _spec.loader.exec_module(_m)
        extra.append(_retry(_m.advise))
    except Exception as exc:  # logged, never silently skipped
        extra.append(dict(candidate="v233_T3", decision_bar_close=str(bars4h["close_time"].iloc[-1]), error=repr(exc)[:300]))
    try:
        _spec = _u.spec_from_file_location("v236_advisor", Path(__file__).parent / "v236_advisor.py")
        _m = _u.module_from_spec(_spec); _spec.loader.exec_module(_m)
        extra.append(_retry(_m.advise))
    except Exception as exc:  # logged, never silently skipped
        extra.append(dict(candidate="v236_W2", decision_bar_close=str(bars4h["close_time"].iloc[-1]), error=repr(exc)[:300]))
    try:
        _spec = _u.spec_from_file_location("v240_advisor", Path(__file__).parent / "v240_advisor.py")
        _m = _u.module_from_spec(_spec); _spec.loader.exec_module(_m)
        extra.append(_retry(_m.advise))
    except Exception as exc:  # logged, never silently skipped
        extra.append(dict(candidate="v240_O1", decision_bar_close=str(bars4h["close_time"].iloc[-1]), error=repr(exc)[:300]))
    try:
        extra.append(portfolio_row(s, now))
    except Exception as exc:  # logged, never silently skipped
        extra.append(dict(candidate="portfolio_v1_3book", decision_bar_close=str(bars4h["close_time"].iloc[-1]), error=repr(exc)[:300]))
    _append((advice(bars4h, daily), combo_advice(bars4h, daily), *tournament_rows(bars4h, daily, funding), *extra), logged, now)
    return 0


def _append(recs, logged, now) -> None:
    for rec in recs:
        key = f'{rec["candidate"]}|{rec["decision_bar_close"]}'
        if key in logged:
            print("already logged", key)
            continue
        lag = now - datetime.fromisoformat(rec["decision_bar_close"])
        rec["logged_at"] = now.isoformat()
        rec["mode"] = "prospective" if lag <= PROSPECTIVE_MAX_LAG else "backfill"
        with LOG.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        logged.add(key)
        print(json.dumps(rec, indent=1))



ALT_DIR = Path("data/raw/xasset_20260924")


def refresh_alts(session: requests.Session) -> None:
    """Append newly closed alt bars/funding so the breadth family sees live data (append-only merge)."""
    from agentic_alpha_lab.data.binance_usdm import BASE_URL
    for f in sorted(ALT_DIR.glob("*_4h.parquet")) + sorted(ALT_DIR.glob("*_1d.parquet")):
        sym, iv = f.stem.split("_")
        old = pd.read_parquet(f)
        new = fetch_klines(sym, iv, old["open_time"].iloc[-1].to_pydatetime(), session=session)
        merged = pd.concat([old, new]).drop_duplicates("open_time", keep="first").sort_values("open_time").reset_index(drop=True)
        merged.to_parquet(f, index=False)
    for f in sorted(ALT_DIR.glob("*_funding.parquet")):
        sym = f.stem.split("_")[0]
        old = pd.read_parquet(f)
        start = int(old["fundingTime"].iloc[-1].timestamp() * 1000) + 1
        rows = session.get(f"{BASE_URL}/fapi/v1/fundingRate", params={"symbol": sym, "startTime": start, "limit": 1000}, timeout=60).json()
        if rows:
            new = pd.DataFrame(rows)[["fundingTime", "fundingRate"]]
            new["fundingRate"] = new["fundingRate"].astype(float)
            new["fundingTime"] = pd.to_datetime(new["fundingTime"], unit="ms", utc=True)
            pd.concat([old, new]).drop_duplicates("fundingTime").sort_values("fundingTime").to_parquet(f, index=False)


def tournament_rows(bars4h: pd.DataFrame, daily: pd.DataFrame, funding: pd.DataFrame) -> list[dict]:
    """Targets of all frozen tournament families at the last closed 4h bar."""
    from agentic_alpha_lab.backtest.ma_ribbon import funding_per_bar
    from agentic_alpha_lab.vf_families import FAMILIES
    cfg = json.loads(Path("artifacts/research/advisor_shadow/tournament.json").read_text())
    b = bars4h.reset_index(drop=True)
    fr, fc = funding_per_bar(b, funding)
    ctx = Context("4h", b, daily, funding, fr, fc)
    rows = []
    for fam, sel in cfg["families"].items():
        fn, _ = FAMILIES[sel.get("family", fam)]
        params = {k: tuple(v) if isinstance(v, list) else v for k, v in sel["params"].items()}
        try:
            tgt = fn(ctx, params) * sel["scale"]
            rows.append(dict(candidate=f"tournament:{fam}", decision_bar_close=str(b["close_time"].iloc[-1]),
                             target_fraction=round(float(tgt[-1]), 4), previous_target_fraction=round(float(tgt[-2]), 4),
                             close_4h=float(b["close"].iloc[-1])))
        except Exception as exc:  # a family needing unavailable live data is logged as an error row, never silently skipped
            rows.append(dict(candidate=f"tournament:{fam}", decision_bar_close=str(b["close_time"].iloc[-1]), error=repr(exc)[:300]))
    return rows



def portfolio_row(session: requests.Session, now: datetime) -> dict:
    from agentic_alpha_lab.data.binance_usdm import BASE_URL
    from agentic_alpha_lab.signals.portfolio_advisor import MAJORS, targets
    data = {}
    for s in MAJORS:
        b4 = fetch_klines(s, "4h", now - timedelta(days=500), session=session)
        d1 = fetch_klines(s, "1d", now - timedelta(days=800), session=session)
        f = pd.DataFrame(session.get(f"{BASE_URL}/fapi/v1/fundingRate", params={"symbol": s, "limit": 1000}, timeout=60).json())
        f["fundingRate"] = f["fundingRate"].astype(float)
        f["fundingTime"] = pd.to_datetime(f["fundingTime"], unit="ms", utc=True)
        data[s] = dict(bars4h=b4, daily=d1, funding=f)
    t = targets(data)
    return dict(candidate="portfolio_v1_3book", decision_bar_close=str(data["BTCUSDT"]["bars4h"]["close_time"].iloc[-1]), **t)


def _locked_main() -> int:
    """Run main() under an exclusive lock file so concurrent loop copies cannot write duplicate rows."""
    import os
    import time
    lock = Path(__file__).resolve().parents[1] / "artifacts/research/advisor_shadow/run.lock"
    if lock.exists() and time.time() - lock.stat().st_mtime > 3600:
        lock.unlink(missing_ok=True)  # stale lock from a crashed run
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print("another advisor_shadow run holds", lock, "- skipping")
        return 0
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return main()
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(_locked_main())
