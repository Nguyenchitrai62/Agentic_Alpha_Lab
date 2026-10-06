"""Trang thai hang ngay cho nguoi van hanh (chi doc, khong network ngoai localhost, khong khoa).

Su dung:
  python scripts/daily_status.py [--md out.md] [--fast] [--json]

Mot trang owner view (tieng Viet), thu tu:
  (1) TONG: OK / WATCH / CRITICAL + ten muc xau nhat,
  (2) stop rules + bao ve (unprotected, qty mismatch tu bot_health),
  (3) runner health (bot_health + paper_report) + cycle time,
  (4) backend (http://127.0.0.1:8724/health, timeout 3s; that bai -> CRITICAL
      "backend tat: plan se cu") + do tuoi plan
      (artifacts/research/advisor_shadow/trade_plan_v376.json generated_at;
      > 1h15m = WARNING, > 4h30m = CRITICAL),
  (5) carry (artifacts/bot/paper_carry/state.json),
  (6) edge monitor (canh bao som, diagnostic-only),
  (7) market regime (scripts/regime_now.py, offline local only),
  (8) collector: liquidations + topbook theo venue
      (data/raw/liquidations_live, data/raw/topbook_live) + gap > 5 phut
      trong 24h qua.
  Cuoi trang: 1 dong KET LUAN (tuong thich cu) + tong thoi gian chay.

  --fast: khong goi network (bo qua check backend), chi doc file local.
  --json: in JSON cua status ra stdout (kem --md van duoc).
  Moi section duoc cach ly loi: section hong in dung mot dong
  'loi: <ten section> (...)' va khong bao gio lam sap trang.

Tai su dung module san co (import): scripts/bot_health.py,
scripts/paper_report.py, scripts/edge_monitor.py, scripts/stop_rules.py,
scripts/regime_now.py, research/tournament/oc_liqlive/load_liq.py
(coverage_gaps, ms_to_utc). Chi doc file; khong cham .env, khong start/stop
process, khong commit.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
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
    edge_monitor = _load("daily_status_edge_monitor", "scripts/edge_monitor.py")
except Exception:  # pragma: no cover - thieu file thi van chay
    edge_monitor = None
try:
    stop_rules = _load("daily_status_stop_rules", "scripts/stop_rules.py")
except Exception:  # pragma: no cover - thieu file thi van chay
    stop_rules = None
try:
    regime_now = _load("daily_status_regime_now", "scripts/regime_now.py")
except Exception:  # pragma: no cover - thieu file thi van chay
    regime_now = None
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
                    "health": rep.get("status"), "summary": pr,
                    "unprotected": list(rep.get("unprotected") or []),
                    "qty_mismatch": list(rep.get("qty_mismatch") or [])})
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


EDGE_RUNNERS = ("paper_d17bfg2", "paper_d17bfg2c")


def check_edge(root: Path) -> list[dict]:
    """Canh bao som edge (chi doc) cho cac runner trien khai (diagnostic-only)."""
    out = []
    if edge_monitor is None:
        return out
    for name in EDGE_RUNNERS:
        d = root / BOT_REL / name
        if not d.is_dir():
            continue
        try:
            rep = edge_monitor.summarize_dir(d)
        except Exception as e:  # pragma: no cover - phong thu
            out.append({"name": name, "severity": "warning",
                        "line": f"{name}: khong doc duoc edge ({e})",
                        "lines": []})
            continue
        worst_s = rep.get("worst", "OK")
        sev = {"OK": "ok", "CHUA DU DU LIEU": "ok",
               "WATCH": "warning", "INVESTIGATE": "warning"}.get(worst_s, "warning")
        out.append({"name": name, "severity": sev, "worst": worst_s,
                    "line": f"{name}: edge {worst_s}",
                    "lines": list(rep.get("lines", []))})
    return out


def check_stops(root: Path) -> list[dict]:
    """Nguong dung + go-live (chi doc) cho cac runner trien khai."""
    out = []
    if stop_rules is None:
        return out
    for name in getattr(stop_rules, "RUNNERS", EDGE_RUNNERS):
        if not (root / BOT_REL / name).is_dir():
            continue
        try:
            rep = stop_rules.summarize_runner(root, name)
        except Exception as e:  # pragma: no cover - phong thu
            out.append({"runner": name, "severity": "warning",
                        "lines": [f"{name}: khong doc duoc stop rules ({e})"]})
            continue
        out.append({"runner": name, "severity": rep.get("severity", "ok"),
                    "lines": list(rep.get("lines", []))})
    return out


def check_regime(root: Path) -> dict:
    """Thi truong hien tai (scripts/regime_now.py, offline local only).

    Chi doc file local, khong network (daily_status chi duoc cham localhost).
    Luon severity ok (thong tin, khong anh huong verdict/exit).
    """
    if regime_now is None:
        return {"severity": "ok", "line": "regime: n/a (thieu scripts/regime_now.py)",
                "lines": []}
    try:
        sm = regime_now.summarize(root, live=False)
        txt = regime_now.format_vi(sm)
        lines = [x for x in txt.splitlines() if x.strip()]
        head = lines[1] if len(lines) > 1 else "regime: n/a"
        return {"severity": "ok", "line": head, "lines": lines}
    except Exception as e:  # pragma: no cover - phong thu
        return {"severity": "ok", "line": f"regime: n/a ({type(e).__name__})",
                "lines": []}


def check_protection(bots: list[dict]) -> dict:
    """Bao ve moi vi the: tong hop unprotected + qty mismatch tu bot_health.

    Input la ket qua check_bots (da giu nguyen moi check cu). Severity
    critical khi co bat ky piece mo thieu stop+TP hoac lech ledger/exchange.
    """
    bad_unprot, bad_qty = [], []
    for b in bots or []:
        name = b.get("name", "-")
        for u in b.get("unprotected") or []:
            bad_unprot.append(f"{name}:{u}")
        for q in b.get("qty_mismatch") or []:
            bad_qty.append(f"{name}:{q}")
    if bad_unprot or bad_qty:
        parts = []
        if bad_unprot:
            parts.append(f"unprotected: {', '.join(bad_unprot)}")
        if bad_qty:
            parts.append(f"qty mismatch: {', '.join(bad_qty)}")
        return {"severity": "critical",
                "line": "bao ve VI PHAM: " + "; ".join(parts),
                "unprotected": bad_unprot, "qty_mismatch": bad_qty}
    if not bots:
        return {"severity": "warning", "line": "loi: bao ve (khong co runner de kiem tra)",
                "unprotected": [], "qty_mismatch": []}
    return {"severity": "ok", "line": "bao ve OK: moi piece mo co stop+TP, ledger khop exchange",
            "unprotected": [], "qty_mismatch": []}


def _section_ok_dict(line: str = "") -> dict:
    return {"severity": "ok", "line": line, "lines": []}


def _call_safe(section: str, fn, *args, **kwargs):
    """Goi mot section, hong thi tra ve placeholder warning voi 1 dong 'loi: ...'."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # moi section hong khong duoc sap trang
        return {"severity": "warning", "section_error": section,
                "line": f"loi: {section} ({type(e).__name__}: {e})",
                "lines": [f"loi: {section} ({type(e).__name__}: {e})"],
                "name": section, "runner": section,
                "venue": section, "feed": section}


def _call_safe_list(section: str, fn, *args, **kwargs) -> list:
    try:
        out = fn(*args, **kwargs)
        return out if isinstance(out, list) else [out]
    except Exception as e:  # moi section hong khong duoc sap trang
        return [{"severity": "warning", "section_error": section,
                 "line": f"loi: {section} ({type(e).__name__}: {e})",
                 "lines": [f"loi: {section} ({type(e).__name__}: {e})"],
                 "name": section, "runner": section,
                 "venue": section, "feed": section}]


def worst_item(st: dict) -> str:
    """Ten muc xau nhat cho dong TONG (uu tien section hong/critical truoc)."""
    verdict = st.get("verdict", "ok")
    if verdict == "ok":
        return "tat ca OK"
    cands: list[tuple[str, str]] = []

    def _add(sev, label):
        if sev == verdict:
            cands.append((sev, label))
    be, plan = st.get("backend") or {}, st.get("plan") or {}
    _add(be.get("severity"), f"backend ({be.get('line', '')})")
    _add(plan.get("severity"), f"plan ({plan.get('line', '')})")
    prot = st.get("protection") or {}
    _add(prot.get("severity"), f"bao ve ({prot.get('line', '')})")
    for s in st.get("stops") or []:
        _add(s.get("severity"), f"stop {s.get('runner', '-')}")
    for b in st.get("bots") or []:
        _add(b.get("severity"), f"bot {b.get('name', '-')}")
    for r in st.get("cycles") or []:
        _add(r.get("severity"), f"cycle {r.get('name', '-')}")
    carry = st.get("carry") or {}
    _add(carry.get("severity"), "carry")
    for e in st.get("edge") or []:
        _add(e.get("severity"), f"edge {e.get('name', '-')}")
    for c in st.get("collectors") or []:
        _add(c.get("severity"), f"collector {c.get('feed', '-')}/{c.get('venue', '-')}")
    if cands:
        return cands[0][1]
    return verdict


def tong_label(verdict: str) -> str:
    return {"ok": "OK", "warning": "WATCH", "critical": "CRITICAL"}.get(verdict, verdict.upper())


def build_status(root: Path = ROOT, now: datetime | None = None,
                 health_url: str = HEALTH_URL, fast: bool = False) -> dict:
    t0 = time.perf_counter()
    now = now or utcnow()
    if fast:
        be = {"ok": True, "severity": "ok",
              "line": "backend bo qua (--fast, khong network)",
              "detail": "skipped --fast"}
    else:
        be = _call_safe("backend", check_backend, health_url)
    plan = _call_safe("plan", check_plan, root, now)
    bots = _call_safe_list("bots", check_bots, root, now)
    try:
        prot = check_protection(bots)
    except Exception as e:  # pragma: no cover - phong thu
        prot = {"severity": "warning",
                "line": f"loi: bao ve ({type(e).__name__}: {e})",
                "unprotected": [], "qty_mismatch": []}
    cols = _call_safe_list("collectors", check_collectors, root, now)
    carry = _call_safe("carry", check_carry, root, now)
    cycles = _call_safe_list("cycles", check_cycles, root, now)
    edge = _call_safe_list("edge", check_edge, root)
    stops = _call_safe_list("stops", check_stops, root)
    regime = _call_safe("regime", check_regime, root)
    verdict = worst(be.get("severity", "warning"), plan.get("severity", "warning"),
                    prot.get("severity", "warning"), carry.get("severity", "warning"),
                    regime.get("severity", "ok") if regime.get("severity") == "ok" else "ok",
                    *(b.get("severity", "warning") for b in bots),
                    *(c.get("severity", "warning") for c in cols),
                    *(r.get("severity", "warning") for r in cycles),
                    *(e.get("severity", "warning") for e in edge),
                    *(s.get("severity", "warning") for s in stops))
    # regime luon severity ok theo dinh nghia (thong tin, khong anh huong verdict).
    st = {"now": now, "fast": bool(fast), "backend": be, "plan": plan, "bots": bots,
          "protection": prot, "collectors": cols, "carry": carry, "cycles": cycles,
          "edge": edge, "stops": stops, "regime": regime, "verdict": verdict,
          "exit": {"ok": 0, "warning": 1, "critical": 2}[verdict]}
    st["worst_item"] = worst_item(st)
    st["elapsed_s"] = time.perf_counter() - t0
    return st


def format_text(st: dict) -> str:
    fast_tag = " [--fast]" if st.get("fast") else ""
    L = [f"TRANG THAI HANG NGAY ({st['now'].isoformat()}){fast_tag}",
         f"TONG: {tong_label(st['verdict'])} (xau nhat: {st.get('worst_item', st['verdict'])})"]
    L.append(f"1) Stop rules + bao ve: {st.get('protection', {}).get('line', 'n/a')}")
    if st.get("stops"):
        for s in st["stops"]:
            L.append(f"   - {s.get('runner', '-')} [{str(s.get('severity', '?')).upper()}]:")
            L += [f"     . {x}" for x in s.get("lines", [])]
    else:
        L.append("   - chua co runner trien khai (paper_d17bfg2/c)")
    L.append(f"2) Runner health ({len(st['bots'])}) + cycle ({len(st['cycles'])}) "
             "[WARNING neu cycle >60s hoac state >2p]:")
    L += [f"   - {b['line']}" for b in st["bots"]]
    L += [f"   - cycle {r['line']}" for r in st["cycles"]]
    L.append(f"3) Backend & plan: {st['backend']['line']}")
    L.append(f"   Plan: {st['plan']['line']}")
    L.append(f"4) Carry: {st['carry']['line']}")
    L += [f"   - {x}" for x in st["carry"].get("lines", [])]
    L.append("5) Canh bao som edge (oc_edgedecay: 6m<1.61%/thang, TP dip<0.434; vo nguong = dieu tra):")
    if st.get("edge"):
        for e in st["edge"]:
            L.append(f"   - {e['line']}")
            L += [f"     . {x}" for x in e.get("lines", [])]
    else:
        L.append("   - chua co runner trien khai (paper_d17bfg2/c)")
    L.append("6) Thi truong hien tai (regime_now, offline local):")
    rg = st.get("regime") or {}
    for x in rg.get("lines", []) or [rg.get("line", "regime: n/a")]:
        L.append(f"   - {x}")
    L.append("7) Collector (gap >5p trong 24h):")
    L += [f"   - {c['line']}" for c in st["collectors"]]
    L.append(f"KET LUAN: {st['verdict'].upper()} "
             f"(0=OK 1=canh bao 2=nguy hiem) -> exit {st['exit']}")
    if st.get("elapsed_s") is not None:
        L.append(f"tong thoi gian: {st['elapsed_s']:.1f}s")
    return "\n".join(L)


def format_markdown(st: dict) -> str:
    fast_tag = " [--fast]" if st.get("fast") else ""
    L = [f"# Trang thai hang ngay ({st['now'].isoformat()}){fast_tag}", "",
         f"**TONG: {tong_label(st['verdict'])}** (xau nhat: {st.get('worst_item', st['verdict'])})", "",
         "## 1) Stop rules + bao ve", ""]
    L.append(f"- Bao ve: {st.get('protection', {}).get('line', 'n/a')}")
    if st.get("stops"):
        for s in st["stops"]:
            L.append(f"- {s.get('runner', '-')} ({str(s.get('severity', '?')).upper()})")
            for x in s.get("lines", []):
                L.append(f"  - {x}")
    else:
        L.append("- chua co runner trien khai (paper_d17bfg2/c)")
    L += ["", "## 2) Runner health + cycle", "",
          "| runner | trang thai | chi tiet |",
          "| --- | --- | --- |"]
    for b in st["bots"]:
        L.append(f"| {b.get('name', '-')} | {str(b.get('severity', '?')).upper()} | {b.get('line', '')} |")
    for r in st["cycles"]:
        L.append(f"| cycle {r.get('name', '-')} | {str(r.get('severity', '?')).upper()} | {r.get('line', '')} |")
    L += ["", "## 3) Backend & plan", "",
          f"- Backend: {st['backend']['line']}",
          f"- Plan: {st['plan']['line']}", ""]
    L += ["## 4) Carry", "", f"**Carry: {st['carry']['line']}**"]
    for x in st["carry"].get("lines", []):
        L.append(f"- {x}")
    L += ["", "## 5) Canh bao som edge (oc_edgedecay)",
          "Nguong: trung binh 6 thang < 1.61%/thang; TP rate dip < 0.434 "
          "(vo nguong = dieu tra, khong phai hanh dong giao dich).", ""]
    if st.get("edge"):
        for e in st["edge"]:
            L.append(f"- {e['line']} ({str(e.get('severity', '?')).upper()})")
            for x in e.get("lines", []):
                L.append(f"  - {x}")
    else:
        L.append("- chua co runner trien khai (paper_d17bfg2/c)")
    L += ["", "## 6) Thi truong hien tai (regime_now, offline local)", ""]
    rg = st.get("regime") or {}
    for x in rg.get("lines", []) or [rg.get("line", "regime: n/a")]:
        L.append(f"- {x}")
    L += ["", "## 7) Collector", "",
          "| collector | trang thai | chi tiet |",
          "| --- | --- | --- |"]
    for c in st["collectors"]:
        L.append(f"| {c.get('feed', '-')}/{c.get('venue', '-')} | "
                 f"{str(c.get('severity', '?')).upper()} | {c.get('line', '')} |")
    L += ["", f"**KET LUAN: {st['verdict'].upper()}** (exit {st['exit']})"]
    if st.get("elapsed_s") is not None:
        L.append(f"- tong thoi gian: {st['elapsed_s']:.1f}s")
    L += [""]
    return "\n".join(L)


def status_jsonable(st: dict) -> dict:
    out = dict(st)
    if isinstance(out.get("now"), datetime):
        out["now"] = out["now"].isoformat()
    return json.loads(json.dumps(out, default=str, ensure_ascii=False))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Trang thai hang ngay (chi doc).")
    ap.add_argument("--md", default=None, help="ghi ban Markdown ra PATH")
    ap.add_argument("--root", default=None, help="workspace root (mac dinh: repo)")
    ap.add_argument("--fast", action="store_true",
                    help="khong goi network, chi doc file local (bo qua check backend)")
    ap.add_argument("--json", action="store_true",
                    help="in JSON cua status ra stdout")
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else ROOT
    t0 = time.perf_counter()
    st = build_status(root, utcnow(), HEALTH_URL, fast=a.fast)
    st["elapsed_s"] = time.perf_counter() - t0
    text = format_text(st)
    if a.json:
        print(json.dumps(status_jsonable(st), ensure_ascii=False, indent=1))
    else:
        print(text)
    if a.md:
        Path(a.md).write_text(format_markdown(st) + "\n", encoding="utf-8")
        print(f"da ghi {a.md}")
    if st.get("elapsed_s") is not None and not a.json:
        pass  # da in trong format_text
    elif st.get("elapsed_s") is not None and a.json:
        print(f"tong thoi gian: {st['elapsed_s']:.1f}s", file=sys.stderr)
    return st["exit"]


if __name__ == "__main__":
    sys.exit(main())
