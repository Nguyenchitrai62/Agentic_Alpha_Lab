"""Trang thai hang ngay cho nguoi van hanh (chi doc, khong network ngoai localhost, khong khoa).

Su dung:
  python scripts/daily_status.py [--md out.md]

Noi dung (tieng Viet, 1 trang):
  (1) backend con song? (http://127.0.0.1:8724/health, timeout 3s;
       that bai -> CRITICAL "backend tat: plan se cu", ke ca khi plan con tuoi) + do tuoi plan
       (artifacts/research/advisor_shadow/trade_plan_v376.json generated_at;
       > 1h15m = WARNING, > 4h30m = CRITICAL),
  (2) moi thu muc artifacts/bot/paper*: dong trang thai bot_health +
      equity/return/max DD/fills tu paper_report,
  (3) collector: thoi diem liquidation va top-of-book cuoi cung theo venue
      (data/raw/liquidations_live, data/raw/topbook_live) + gap > 5 phut
      trong 24h qua,
  (4) 1 dong ket luan (OK / WARNING / CRITICAL) + exit code 0/1/2.

Tai su dung module san co (import): scripts/bot_health.py,
scripts/paper_report.py, research/tournament/oc_liqlive/load_liq.py
(coverage_gaps, ms_to_utc). Chi doc file; khong cham .env, khong start/stop
process, khong commit.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEALTH_URL = "http://127.0.0.1:8724/health"
HEALTH_TIMEOUT = 3.0
PLAN_REL = Path("artifacts/research/advisor_shadow/trade_plan_v376.json")
BOT_REL = Path("artifacts/bot")
LIQ_REL = Path("data/raw/liquidations_live")
TOP_REL = Path("data/raw/topbook_live")
PLAN_WARN_H = 1.25
PLAN_STALE_H = 4.5
GAP_MS = 5 * 60 * 1000
STALE_S = 5 * 60.0
WINDOW_H = 24.0
VENUES = ("binance", "bybit")
CARRY_REL = Path("artifacts/bot/paper_carry/state.json")
CARRY_STALE_S = 2 * 3600.0
RUNNER_STALE_S = 2 * 60.0
CYCLE_WARN_MS = 60_000.0


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bot_health = _load("daily_status_bot_health", "scripts/bot_health.py")
paper_report = _load("daily_status_paper_report", "scripts/paper_report.py")
try:
    liq_mod = _load("daily_status_load_liq", "research/tournament/oc_liqlive/load_liq.py")
except Exception:  # pragma: no cover - pandas/pyarrow thieu thi van chay
    liq_mod = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def fmt_ts_ms(ms) -> str:
    try:
        if liq_mod is not None:
            return liq_mod.ms_to_utc(int(ms))
    except Exception:
        pass
    return datetime.fromtimestamp(float(ms) / 1000, tz=timezone.utc).isoformat()


def fmt_age_s(age_s) -> str:
    if age_s is None:
        return "n/a"
    if age_s < 0:
        return "tuong lai?"
    if age_s < 600:
        return f"{age_s:.0f}s"
    if age_s < 3600:
        return f"{age_s / 60:.1f} phut"
    return f"{age_s / 3600:.1f}h"


def check_backend(url: str = HEALTH_URL, timeout: float = HEALTH_TIMEOUT) -> dict:
    """GET /health voi timeout 3s. That bai -> critical."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            code = getattr(r, "status", 200)
            body = r.read(4096).decode("utf-8", "replace") if code == 200 else ""
    except Exception as e:
        return {"ok": False, "severity": "critical",
                "line": f"backend tắt: plan sẽ cũ (khong noi duoc {url}: {type(e).__name__})",
                "detail": f"{type(e).__name__}: {e}"}
    if code != 200:
        return {"ok": False, "severity": "critical",
                "line": f"backend tắt: plan sẽ cũ (HTTP {code})", "detail": f"HTTP {code}"}
    try:
        st = (json.loads(body) or {}).get("status") if body else None
    except ValueError:
        st = None
    if st is not None and st != "ok":
        return {"ok": True, "severity": "warning",
                "line": f"backend song nhung scheduler stale (status={st})",
                "detail": body[:200]}
    return {"ok": True, "severity": "ok",
            "line": "backend song (GET /health OK)", "detail": body[:200]}


def check_plan(root: Path, now: datetime) -> dict:
    p = root / PLAN_REL
    plan = bot_health.load_json(p)
    if plan is None:
        return {"severity": "critical", "age_h": None,
                "line": f"plan KHONG DOC DUOC ({PLAN_REL.as_posix()}): coi nhu plan cu"}
    gen = bot_health.parse_ts(plan.get("generated_at"))
    if gen is None:
        return {"severity": "critical", "age_h": None,
                "line": "plan generated_at khong ro: coi nhu plan cu"}
    age_h = (now - gen).total_seconds() / 3600
    if age_h > PLAN_STALE_H:
        return {"severity": "critical", "age_h": age_h,
                "line": f"plan CU {age_h:.1f}h (>4h30m, gen {gen.isoformat()})"}
    if age_h > PLAN_WARN_H:
        return {"severity": "warning", "age_h": age_h,
                "line": f"plan cu {age_h:.1f}h (>1h15m, gen {gen.isoformat()})"}
    return {"severity": "ok", "age_h": age_h,
            "line": f"plan tuoi {age_h:.1f}h (gen {gen.isoformat()})"}


def list_paper_dirs(root: Path) -> list[Path]:
    base = root / BOT_REL
    try:
        dirs = [d for d in base.glob("paper*") if d.is_dir() and d.name != "paper_carry"]  # carry ledger is not a bot runner (own section)
    except OSError:
        return []
    return sorted(dirs)


def check_bots(root: Path, now: datetime) -> list[dict]:
    plan = bot_health.load_json(root / PLAN_REL)
    out = []
    for d in list_paper_dirs(root):
        try:
            rep = bot_health.check_dir(d, plan, now, 20.0)
        except Exception as e:  # pragma: no cover - phong thu
            out.append({"name": d.name, "severity": "warning",
                        "line": f"[WARNING] {d.name}: khong doc duoc ({e})"})
            continue
        try:
            pr = paper_report.summarize_dir(d)
        except Exception:  # pragma: no cover
            pr = None
        sev = {"ok": "ok", "warning": "warning", "critical": "critical"}.get(
            rep.get("status"), "warning")
        age = rep.get("cycle_age_s")
        if pr is not None:
            eq, ret, dd = pr.get("equity_now"), pr.get("return_pct"), pr.get("max_dd_pct")
            eq_s = f"{eq:,.2f}" if eq is not None else "n/a"
            ret_s = f"{ret:.2f}%" if ret is not None else "n/a"
            dd_s = f"{dd:.2f}%" if dd is not None else "n/a"
            fills = f"dip={pr.get('dip_fills', 0)}/book={pr.get('book_fills', 0)}"
            extra = f"equity {eq_s} return {ret_s} maxDD {dd_s} fills({fills})"
        else:
            extra = "paper_report n/a"
        probs = "; ".join(rep.get("problems", []) + rep.get("warnings", []))
        line = (f"[{sev.upper()}] {d.name}: chu ky cuoi {fmt_age_s(age)} truoc; "
                f"{extra}" + (f" | {probs}" if probs else ""))
        out.append({"name": d.name, "severity": sev, "line": line,
                    "health": rep.get("status"), "summary": pr})
    if not out:
        out.append({"name": "-", "severity": "warning",
                    "line": "khong thay thu muc artifacts/bot/paper* nao"})
    return out


def _read_ms_column(files: list[Path], column: str, since_ms: int) -> list[int]:
    """Doc 1 cot ms tu cac file parquet gan nhat (2 file/symbol de chan tren I/O)."""
    import pyarrow.parquet as pq
    by_sym: dict[str, list[Path]] = {}
    for f in files:
        by_sym.setdefault(str(f.parent), []).append(f)
    picked = [f for fs in by_sym.values() for f in sorted(fs)[-2:]]
    vals: list[int] = []
    for f in sorted(picked):  # chan tren I/O: file ngay + theo symbol
        try:
            col = pq.read_table(str(f), columns=[column]).column(column).to_pylist()
        except Exception:
            continue
        for v in col:
            try:
                m = int(v)
            except (TypeError, ValueError):
                continue
            if m >= since_ms:
                vals.append(m)
    return sorted(vals)


def _venue_files(base: Path, venue: str) -> list[Path]:
    try:
        return sorted((base / venue).rglob("*.parquet"))
    except OSError:
        return []


def check_collectors(root: Path, now: datetime) -> list[dict]:
    now_ms = int(now.timestamp() * 1000)
    since_ms = now_ms - int(WINDOW_H * 3600 * 1000)
    out: list[dict] = []
    for venue in VENUES:
        # --- liquidations: heartbeat = coverage end; event cuoi chi de tham khao ---
        cov_files = [f for f in _venue_files(root / LIQ_REL / "_coverage", venue)
                     if f.suffix == ".parquet"]
        cov_rows: list[tuple[int, int]] = []
        cov_end = None
        if cov_files:
            try:
                import pyarrow.parquet as pq
                for f in sorted(cov_files):
                    try:
                        t = pq.read_table(str(f), columns=["venue", "start_ms", "end_ms"])
                    except Exception:
                        continue
                    for r in t.to_pylist():
                        if str(r.get("venue")) != venue:
                            continue
                        try:
                            s, e = int(r["start_ms"]), int(r["end_ms"])
                        except (TypeError, ValueError):
                            continue
                        cov_rows.append((s, e))
            except Exception:
                cov_rows = []
            if cov_rows:
                cov_end = max(e for _, e in cov_rows)
        gaps_n, gap_note = 0, "khong tinh duoc coverage"
        if cov_rows:
            recent = [(s, e) for s, e in cov_rows if e >= since_ms]
            if liq_mod is not None and recent:
                try:
                    import pandas as pd
                    df = pd.DataFrame([{"venue": venue, "start_ms": s, "end_ms": e}
                                       for s, e in sorted(recent)])
                    g = liq_mod.coverage_gaps(df, gap_ms=GAP_MS)
                    g = g[g["end_ms"] >= since_ms]
                    gaps_n = int(len(g))
                    gap_note = (f"{gaps_n} gap >5p/24h" + (f" (gap lon nhat {float(g['gap_ms'].max()) / 1000:.0f}s)" if gaps_n else ""))
                except Exception:
                    gaps_n, gap_note = _manual_gaps(sorted(recent), since_ms)
            else:
                gaps_n, gap_note = _manual_gaps(sorted(recent), since_ms)
        liq_files = [f for f in _venue_files(root / LIQ_REL, venue)
                     if "_coverage" not in f.parts and f.suffix == ".parquet"]
        last_ev = None
        if liq_files:
            try:
                vals = _read_ms_column(liq_files, "event_time", since_ms)
                last_ev = vals[-1] if vals else None
            except Exception:
                last_ev = None
        if cov_end is None:
            sev, hb = "warning", "khong co coverage"
        else:
            age_s = (now_ms - cov_end) / 1000
            sev = "critical" if age_s > STALE_S else ("warning" if gaps_n else "ok")
            hb = f"heartbeat {fmt_ts_ms(cov_end)} ({fmt_age_s(age_s)} truoc)"
        ev_s = fmt_ts_ms(last_ev) if last_ev else "khong co event/24h (binh thuong)"
        out.append({"venue": venue, "feed": "liquidations", "severity": sev,
                    "line": f"liquidations/{venue}: event cuoi {ev_s}; {hb}; {gap_note}"})
        # --- topbook: heartbeat = row cuoi; gap tu sample_time ---
        tb_files = [f for f in _venue_files(root / TOP_REL, venue) if f.suffix == ".parquet"]
        last_tb, tb_gaps = None, None
        if tb_files:
            try:
                vals = _read_ms_column(tb_files, "sample_time", since_ms)
                if vals:
                    last_tb = vals[-1]
                    tb_gaps = sum(1 for a, b in zip(vals, vals[1:]) if b - a > GAP_MS)
            except Exception:
                last_tb, tb_gaps = None, None
        if last_tb is None:
            sev2, gap2 = "warning", "khong co du lieu/24h"
        else:
            age_s = (now_ms - last_tb) / 1000
            gap2 = f"{tb_gaps} gap >5p/24h" if tb_gaps is not None else "khong tinh duoc gap"
            sev2 = "critical" if age_s > STALE_S else ("warning" if (tb_gaps or 0) else "ok")
        tb_s = fmt_ts_ms(last_tb) if last_tb else "n/a"
        out.append({"venue": venue, "feed": "topbook", "severity": sev2,
                    "line": f"topbook/{venue}: row cuoi {tb_s}; {gap2}"})
    return out


def _manual_gaps(intervals: list[tuple[int, int]], since_ms: int) -> tuple[int, str]:
    n = 0
    biggest = 0
    for (_, e), (s2, _) in zip(intervals, intervals[1:]):
        if s2 - e > GAP_MS and s2 >= since_ms:
            n += 1
            biggest = max(biggest, s2 - e)
    note = f"{n} gap >5p/24h" + (f" (gap lon nhat {biggest / 1000:.0f}s)" if n else "")
    return n, note


def _state_mtime(p: Path):
    try:
        return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def check_carry(root: Path, now: datetime) -> dict:
    """Carry sleeve (chi doc artifacts/bot/paper_carry/state.json)."""
    p = root / CARRY_REL
    st = bot_health.load_json(p)
    if not isinstance(st, dict) or not isinstance(st.get("positions"), dict):
        return {"severity": "ok",
                "line": "carry: chua co ledger (chua chay carry_paper)",
                "lines": []}
    mt = _state_mtime(p)
    if mt is None:
        mt = bot_health.parse_ts((st or {}).get("updated_at"))
    age_s = (now - mt).total_seconds() if mt is not None and mt <= now else 0.0
    now_ms = int(now.timestamp() * 1000)
    lines = []
    positions = st.get("positions") or {}
    soonest = None
    for coin in sorted(positions):
        pos = positions[coin] or {}
        try:
            dlv_ms = int(pos.get("delivery_ms", 0))
        except (TypeError, ValueError):
            dlv_ms = 0
        dte_d = (dlv_ms - now_ms) / 86_400_000 if dlv_ms else None
        try:
            basis = float(pos.get("ann_basis", 0.0)) * 100
        except (TypeError, ValueError):
            basis = None
        try:
            mtm = float(pos.get("mtm_alloc", 0.0)) * 100
        except (TypeError, ValueError):
            mtm = None
        try:
            fees = float(pos.get("entry_fees", 0.0))
        except (TypeError, ValueError):
            fees = None
        dlv_s = datetime.fromtimestamp(dlv_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d") if dlv_ms else "n/a"
        lines.append(
            f"mo {coin} {pos.get('symbol', '?')}: basis "
            f"{basis:+.2f}%/nam" if basis is not None else f"mo {coin} {pos.get('symbol', '?')}: basis n/a")
        lines[-1] += (f", den han {dte_d:.1f} ngay ({dlv_s})" if dte_d is not None else ", han n/a")
        lines[-1] += (f", MtM {mtm:+.2f}% von phan bo" if mtm is not None else ", MtM n/a")
        lines[-1] += (f", phi {fees:.2f}" if fees is not None else ", phi n/a")
        if dlv_ms and (soonest is None or dlv_ms < soonest[0]):
            soonest = (dlv_ms, coin)
    if not lines:
        lines.append("khong co cap mo (flat)")
    hist = st.get("history") or []
    n_set = len(hist) if isinstance(hist, list) else 0
    tot = st.get("totals") or {}
    try:
        rpnl = float(tot.get("realised_pnl", 0.0))
    except (TypeError, ValueError):
        rpnl = 0.0
    try:
        tfees = float(tot.get("fees_paid", 0.0))
    except (TypeError, ValueError):
        tfees = 0.0
    lines.append(f"da quyet toan: {n_set} cap, P&L {rpnl:+.2f} USDT (phi tich luy {tfees:.2f})")
    if mt is None:
        run_s, sev = "khong ro lan chay cuoi", "warning"
    else:
        run_s = f"ledger chay lan cuoi {mt.isoformat()} ({fmt_age_s(age_s)} truoc)"
        sev = "warning" if age_s is not None and age_s > CARRY_STALE_S else "ok"
        if sev == "warning":
            run_s += " WARNING: >2h (vong hourly chet?)"
    lines.append(run_s)
    if soonest is not None:
        d = datetime.fromtimestamp(soonest[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        left = (soonest[0] - now_ms) / 86_400_000
        lines.append(f"roll tiep theo: {d} ({soonest[1]}, con {left:.1f} ngay)")
    else:
        lines.append("roll tiep theo: n/a (khong co vi the mo)")
    head = f"carry: {len(positions)} cap mo, P&L {rpnl:+.2f}"
    if sev == "warning":
        head += " [WARNING ledger >2h]"
    return {"severity": sev, "line": head, "lines": lines}


def check_cycles(root: Path, now: datetime) -> list[dict]:
    """Moi paper runner: last_cycle_ms + stage cham nhat + tuoi state.json."""
    out = []
    for d in list_paper_dirs(root):
        sp = d / "state.json"
        st = bot_health.load_json(sp)
        if not isinstance(st, dict):
            out.append({"name": d.name, "severity": "warning",
                        "line": f"{d.name}: khong doc duoc state.json WARNING"})
            continue
        try:
            cyc = st.get("last_cycle_ms")
            cyc = float(cyc) if cyc is not None else None
        except (TypeError, ValueError):
            cyc = None
        stages = st.get("last_cycle_stages_ms")
        slow = None
        if isinstance(stages, dict) and stages:
            try:
                k = max(stages, key=lambda x: float(stages[x]))
                slow = (k, float(stages[k]))
            except (TypeError, ValueError):
                slow = None
        mt = _state_mtime(sp)
        age_s = (now - mt).total_seconds() if mt is not None and mt <= now else 0.0
        cyc_s = "n/a" if cyc is None else f"{cyc / 1000:.1f}s"
        slow_s = "n/a" if slow is None else f"{slow[0]}={slow[1] / 1000:.1f}s"
        warn = (cyc is not None and cyc > CYCLE_WARN_MS) or age_s > RUNNER_STALE_S
        sev = "warning" if warn else "ok"
        line = f"{d.name}: cycle {cyc_s} (cham nhat {slow_s}); state tuoi {fmt_age_s(age_s)}"
        if cyc is not None and cyc > CYCLE_WARN_MS:
            line += " WARNING: cycle >60s"
        if age_s > RUNNER_STALE_S:
            line += " WARNING: state >2p (runner dung?)"
        out.append({"name": d.name, "severity": sev, "line": line,
                    "cycle_ms": cyc, "slowest": slow, "state_age_s": age_s})
    if not out:
        out.append({"name": "-", "severity": "warning",
                    "line": "khong thay thu muc artifacts/bot/paper* nao"})
    return out


def worst(*sevs: str) -> str:
    order = {"ok": 0, "warning": 1, "critical": 2}
    return max(sevs, key=lambda s: order.get(s, 1))


def build_status(root: Path = ROOT, now: datetime | None = None,
                 health_url: str = HEALTH_URL) -> dict:
    now = now or utcnow()
    be = check_backend(health_url)
    plan = check_plan(root, now)
    bots = check_bots(root, now)
    cols = check_collectors(root, now)
    carry = check_carry(root, now)
    cycles = check_cycles(root, now)
    verdict = worst(be["severity"], plan["severity"], carry["severity"],
                    *(b["severity"] for b in bots), *(c["severity"] for c in cols),
                    *(r["severity"] for r in cycles))
    return {"now": now, "backend": be, "plan": plan, "bots": bots,
            "collectors": cols, "carry": carry, "cycles": cycles,
            "verdict": verdict,
            "exit": {"ok": 0, "warning": 1, "critical": 2}[verdict]}


def format_text(st: dict) -> str:
    L = [f"TRANG THAI HANG NGAY ({st['now'].isoformat()})",
         f"1) Backend & plan: {st['backend']['line']}",
         f"   Plan: {st['plan']['line']}"]
    L.append(f"2) Bot paper ({len(st['bots'])}) :")
    L += [f"   - {b['line']}" for b in st["bots"]]
    L.append("3) Collector (gap >5p trong 24h):")
    L += [f"   - {c['line']}" for c in st["collectors"]]
    L.append(f"4) Carry: {st['carry']['line']}")
    L += [f"   - {x}" for x in st["carry"].get("lines", [])]
    L.append(f"5) Chu ky runner ({len(st['cycles'])}) [WARNING neu cycle >60s hoac state >2p]:")
    L += [f"   - {r['line']}" for r in st["cycles"]]
    L.append(f"KET LUAN: {st['verdict'].upper()} "
             f"(0=OK 1=canh bao 2=nguy hiem) -> exit {st['exit']}")
    return "\n".join(L)


def format_markdown(st: dict) -> str:
    L = [f"# Trang thai hang ngay ({st['now'].isoformat()})", "",
         f"- Backend: {st['backend']['line']}",
         f"- Plan: {st['plan']['line']}", "",
         "| bot | trang thai | chi tiet |",
         "| --- | --- | --- |"]
    for b in st["bots"]:
        L.append(f"| {b.get('name', '-')} | {b['severity'].upper()} | {b['line']} |")
    L += ["", "| collector | trang thai | chi tiet |",
          "| --- | --- | --- |"]
    for c in st["collectors"]:
        L.append(f"| {c['feed']}/{c['venue']} | {c['severity'].upper()} | {c['line']} |")
    L += ["", f"**Carry: {st['carry']['line']}**"]
    for x in st["carry"].get("lines", []):
        L.append(f"- {x}")
    L += ["", "| runner | trang thai | chi tiet |",
          "| --- | --- | --- |"]
    for r in st["cycles"]:
        L.append(f"| {r.get('name', '-')} | {r['severity'].upper()} | {r['line']} |")
    L += ["", f"**KET LUAN: {st['verdict'].upper()}** (exit {st['exit']})", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Trang thai hang ngay (chi doc).")
    ap.add_argument("--md", default=None, help="ghi ban Markdown ra PATH")
    ap.add_argument("--root", default=None, help="workspace root (mac dinh: repo)")
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else ROOT
    st = build_status(root, utcnow(), HEALTH_URL)
    text = format_text(st)
    print(text)
    if a.md:
        Path(a.md).write_text(format_markdown(st) + "\n", encoding="utf-8")
        print(f"da ghi {a.md}")
    return st["exit"]


if __name__ == "__main__":
    sys.exit(main())
