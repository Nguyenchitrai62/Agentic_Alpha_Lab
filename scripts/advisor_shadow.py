"""Append the frozen trend-advisor state for each new closed 4h bar (prospective paper log).

Public Binance USD-M REST only; advisory, no orders. Rows logged more than 6h
after their bar closed are marked backfill and are not forward evidence.
"""

from __future__ import annotations

import json
import math
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
# First decision closes needed by the deployed paper windows. Fresh logs must fill these too.
PAPER_STARTS = {"v240_O1": "2026-09-28T07:59:59.999Z", "v285_CB": "2026-09-29T23:59:59.999Z"}


def _row_key(rec):
    return f'{rec.get("candidate")}|{pd.Timestamp(rec["decision_bar_close"]).isoformat()}'


def _valid_row(rec):
    if rec.get("error") or (rec.get("mode") == "backfill" and not rec.get("asof")):
        return False
    for key in ("perp_weight", "spot_weight"):
        values = rec.get(key)
        if not isinstance(values, dict):
            return False
        try:
            if any(isinstance(v, bool) or not math.isfinite(v) for v in values.values()):
                return False
        except TypeError:
            return False
    return True


def _read_rows():
    rows = []
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    continue
                _row_key(row)
                rows.append(row)
            except (ValueError, TypeError, KeyError):
                print("shadow log: ignoring an incomplete row; its decision will be repaired", flush=True)
    return rows


def _write_row(rec):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    # A killed writer can leave a partial last line. Separate it from the next complete record.
    separator = ""
    if LOG.exists() and LOG.stat().st_size:
        with LOG.open("rb") as f:
            f.seek(-1, 2)
            if f.read(1) != b"\n":
                separator = "\n"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(separator + json.dumps(rec, default=str) + "\n")


def _member(mod, suffix=""):
    import importlib.util as util
    spec = util.spec_from_file_location(mod + suffix, Path(__file__).parent / f"{mod}.py")
    member = util.module_from_spec(spec)
    spec.loader.exec_module(member)
    return member


def backfill() -> int:
    """Gap check + backfill of the advisors the trade plans read: every required 4h decision bar (from each candidate's paper start or
    first row) that has no valid row gets one, computed AS OF that bar (ADVISOR_ASOF: only bars closed by then, funding up to then;
    the other inputs are joined on the bar time, so nothing after the bar reaches the features). Rows carry asof=True; rows logged more
    than 6h after the bar are mode 'backfill' (not forward evidence, but the trade plans may replay them). Include the latest closed bar."""
    rows = _read_rows()
    good = {_row_key(r) for r in rows if _valid_row(r)}
    now = datetime.now(timezone.utc)
    latest = pd.Timestamp(now).floor("4h") - pd.Timedelta(milliseconds=1)          # close of the last closed 4h bar
    n_new, n_err = 0, 0
    for mod, cand in FAST:
        mine = [pd.Timestamp(r["decision_bar_close"]) for r in rows if r.get("candidate") == cand and _valid_row(r)]
        first = min([pd.Timestamp(PAPER_STARTS[cand]), *mine])
        bars = pd.date_range(first, latest, freq="4h")
        missing = [t for t in bars if _row_key(dict(candidate=cand, decision_bar_close=t)) not in good]
        if not missing:
            continue
        m = _member(mod, "_bf")
        for t in missing:
            previous_asof = os.environ.get("ADVISOR_ASOF")
            os.environ["ADVISOR_ASOF"] = str(t)
            try:
                rec = _retry(m.advise)
                if rec.get("candidate") != cand or not _valid_row(rec):
                    raise RuntimeError("Advisor returned an invalid member row")
                if str(pd.Timestamp(rec["decision_bar_close"])) != str(t):
                    raise RuntimeError(f"as-of bar mismatch: got {rec['decision_bar_close']}, wanted {t}")
                rec["decision_bar_close"] = str(t)
                rec["asof"] = True
            except Exception as exc:
                rec = dict(candidate=cand, decision_bar_close=str(t), error="backfill: " + repr(exc)[:300], asof=True)
                n_err += 1
            finally:
                if previous_asof is None:
                    os.environ.pop("ADVISOR_ASOF", None)
                else:
                    os.environ["ADVISOR_ASOF"] = previous_asof
            lag = now - pd.Timestamp(t).to_pydatetime()
            rec["logged_at"] = now.isoformat()
            rec["mode"] = "prospective" if lag <= PROSPECTIVE_MAX_LAG else "backfill"
            _write_row(rec)
            n_new += _valid_row(rec)
            print("backfilled", cand, t, "ok" if "perp_weight" in rec else rec.get("error"), flush=True)
    print(f"backfill: {n_new} rows added, {n_err} errors")
    return 1 if n_err else 0


def main() -> int:
    now = datetime.now(timezone.utc)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if os.environ.get("ADVISOR_SHADOW_BACKFILL") == "1":
        return backfill()
    records = _read_rows()
    fast_candidates = {cand for _, cand in FAST}
    logged = {_row_key(r) for r in records if r.get("candidate") not in fast_candidates or _valid_row(r)}
    s = requests.Session()
    if os.environ.get("ADVISOR_SHADOW_FAST") == "1":  # only the advisors the trade plans read (backend cycle, before its plans)
        rows = []
        latest = pd.Timestamp(now).floor("4h") - pd.Timedelta(milliseconds=1)
        for mod, cand in FAST:
            if _row_key(dict(candidate=cand, decision_bar_close=latest)) in logged:
                continue
            try:
                _m = _member(mod)
                rec = _retry(_m.advise)
                if not _valid_row(rec) or rec.get("candidate") != cand or pd.Timestamp(rec["decision_bar_close"]) != latest:
                    raise RuntimeError("Advisor did not produce the latest closed decision")
                rows.append(rec)
            except Exception as exc:  # logged, never silently skipped
                rows.append(dict(candidate=cand, decision_bar_close=str(latest), error=repr(exc)[:300]))
        _append(rows, logged, now)
        return 1 if any(not _valid_row(r) for r in rows) else 0
    bars4h = fetch_klines("BTCUSDT", "4h", now - timedelta(days=500), session=s)
    daily = fetch_klines("BTCUSDT", "1d", now - timedelta(days=800), session=s)
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
        key = _row_key(rec)
        if key in logged:
            print("already logged", key)
            continue
        lag = now - datetime.fromisoformat(rec["decision_bar_close"])
        rec["logged_at"] = now.isoformat()
        rec["mode"] = "prospective" if lag <= PROSPECTIVE_MAX_LAG else "backfill"
        _write_row(rec)
        if _valid_row(rec) or rec["candidate"] not in PAPER_STARTS:
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


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    # On Windows os.kill(pid, 0) can terminate a process: query its status through WinAPI instead.
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return ctypes.get_last_error() == 5  # access denied: conservatively assume alive
    try:
        code = wintypes.DWORD()
        return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
    finally:
        kernel.CloseHandle(handle)


def _locked_main() -> int:
    """Run main() under an exclusive lock file so concurrent loop copies cannot write duplicate rows."""
    import os
    import time
    lock = LOG.resolve().with_name("run.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        try:
            owner = lock.read_text().strip()
            alive = _pid_alive(int(owner))
        except (ValueError, OSError):
            alive = time.time() - lock.stat().st_mtime <= 3600
        if not alive:
            lock.unlink(missing_ok=True)  # recover immediately after a crashed/killed writer
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print("another advisor_shadow run holds", lock, "- skipping")
        return 3  # Busy is incomplete, never a successful gap repair.
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return main()
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(_locked_main())
