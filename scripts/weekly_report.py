"""Bao cao tuan cho nguoi van hanh (chi doc, khong network, khong keys, khong commit).

Su dung:
  python scripts/weekly_report.py [--root PATH] [--out PATH] [--now ISO]

Doc DUY NHAT file local trong cac thu muc runner trien khai
(artifacts/bot/paper_d17bfg2, artifacts/bot/paper_d17bfg2c), ledger carry
(artifacts/bot/paper_carry/state.json) va plan paper
(artifacts/research/advisor_shadow/trade_plan_v376.json).
Tai su dung module san co: scripts/paper_report.py, scripts/edge_monitor.py,
scripts/paper_divergence.py, scripts/stop_rules.py (import, chi doc file).

Xuat mot trang tieng Viet (markdown ra stdout + ghi file
artifacts/reports/weekly_<ISO-week>.md): moi runner + ledger carry gom
tuan / tu-dau return, DD, trades va win rate theo loai (book / dip / carry),
win/loss lon nhat, divergence vs plan, trang thai edge-monitor va stop-rule,
so ngay bang chung so voi muc toi thieu 56 ngay go-live, va tom tat 3 dong.
Thieu du lieu -> ghi 'n/a (chua co du lieu)', khong bao gio crash.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT_REL = Path("artifacts/bot")
PLAN_REL = Path("artifacts/research/advisor_shadow/trade_plan_v376.json")
CARRY_REL = Path("artifacts/bot/paper_carry/state.json")
REPORTS_REL = Path("artifacts/reports")
OOS_REL = Path("research/diagnostics/oc_bookoos/results.json")
OOS_REFRESH_CMD = (".venv/Scripts/python.exe research/diagnostics/oc_bookoos/score_oos.py"
                   " --fetch --run")
OOS_MAX_AGE_DAYS = 8.0

RUNNERS = ("paper_d17bfg2", "paper_d17bfg2c")
GO_LIVE_MIN_DAYS = 56.0
WEEK_DAYS = 7.0


def _load(name: str, rel: str):
    try:
        spec = importlib.util.spec_from_file_location(name, ROOT / rel)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


paper_report = _load("weekly_paper_report", "scripts/paper_report.py")
edge_monitor = _load("weekly_edge_monitor", "scripts/edge_monitor.py")
paper_divergence = _load("weekly_paper_divergence", "scripts/paper_divergence.py")
stop_rules = _load("weekly_stop_rules", "scripts/stop_rules.py")


def parse_ts(x):
    if x is None:
        return None
    try:
        t = datetime.fromisoformat(str(x))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t


def parse_ms(x):
    try:
        return datetime.fromtimestamp(int(x) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def load_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_curve(exchange: dict) -> list:
    pts = []
    for row in (exchange or {}).get("equity_curve") or []:
        try:
            t, v = parse_ts(row[0]), float(row[1])
        except (TypeError, ValueError, IndexError):
            continue
        if t is not None:
            pts.append((t, v))
    pts.sort(key=lambda r: r[0])
    return pts


def pct_return(pts: list) -> float | None:
    if len(pts) < 2 or not pts[0][1]:
        return None
    return 100.0 * (pts[-1][1] / pts[0][1] - 1.0)


def max_dd_pct(equities: list) -> float | None:
    if len(equities) < 2:
        return None
    peak, worst = equities[0], 0.0
    for v in equities:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return 100.0 * worst


def week_slice(pts: list, week_start) -> list:
    """Diem equity trong tuan: anchor ffill tai/sau week_start + moi diem sau."""
    if len(pts) < 1:
        return []
    anchor = None
    for t, v in pts:
        if t <= week_start:
            anchor = (t, v)
    if anchor is None:
        for t, v in pts:
            if t >= week_start:
                anchor = (t, v)
                break
    out = [anchor] if anchor is not None else []
    for t, v in pts:
        if anchor is not None and t <= anchor[0]:
            continue
        if t >= week_start:
            out.append((t, v))
    return out


def _f2(v):
    return "n/a" if v is None else f"{v:,.2f}"


def _fp(v):
    return "n/a" if v is None else f"{v:+.2f}%"


def closed_pnls(state: dict, exchange: dict) -> list:
    """Cac piece da dong: [(pid, pnl, kind, last_exit_time)]. Chi doc."""
    if paper_report is None:
        return []
    try:
        state_links = paper_report.load_state_links(state)
    except Exception:
        return []
    ledger = (state or {}).get("ledger") or {}
    piece_sym = {}
    try:
        for link, rec in ((state or {}).get("links") or {}).items():
            o = (rec or {}).get("order") or {}
            if o.get("piece") and o.get("symbol"):
                piece_sym.setdefault(o["piece"], o["symbol"])
    except AttributeError:
        pass
    entry_qty, entry_cost, exit_qty, exit_px, exit_t = {}, {}, {}, {}, {}
    for e in ((exchange or {}).get("execs") or []):
        if not isinstance(e, dict):
            continue
        link = e.get("orderLinkId", "")
        try:
            is_entry, _kb, piece = paper_report.classify_exec(link, state_links)
        except Exception:
            continue
        try:
            qty, px = float(e["execQty"]), float(e["execPrice"])
        except (TypeError, ValueError, KeyError):
            continue
        if qty <= 0 or not piece:
            continue
        t = parse_ms(e.get("execTime"))
        if is_entry:
            entry_qty[piece] = entry_qty.get(piece, 0.0) + qty
            entry_cost[piece] = entry_cost.get(piece, 0.0) + qty * px
        else:
            exit_qty[piece] = exit_qty.get(piece, 0.0) + qty
            exit_px[piece] = exit_px.get(piece, 0.0) + qty * px
            if t is not None and (piece not in exit_t or t > exit_t[piece]):
                exit_t[piece] = t
    out = []
    for piece in set(list(entry_qty) + list(exit_qty)):
        if entry_qty.get(piece, 0.0) <= 0 or exit_qty.get(piece, 0.0) <= 0:
            continue
        pc = ledger.get(piece) or {}
        if not (pc.get("qty", 0) == 0 or exit_qty[piece] >= entry_qty[piece] > 0):
            continue
        avg = entry_cost[piece] / entry_qty[piece]
        side = int(pc["side"]) if pc.get("side") in (1, -1) else 1
        pnl = side * (exit_px[piece] - avg * exit_qty[piece])
        try:
            kind = paper_report.piece_kind_of(piece, state_links, ledger)
        except Exception:
            kind = None
        out.append((piece, pnl, kind, exit_t.get(piece)))
    return out


def wr_line(rows: list) -> str:
    n = len(rows)
    if not n:
        return "n/a (0 dong)"
    w = sum(1 for _, p, _, *_ in rows if p > 0)
    return f"{100.0 * w / n:.1f}% ({w}/{n})"


def extremes(rows: list) -> tuple:
    if not rows:
        return None, None
    ps = sorted((p for _, p, _, *_ in rows))
    return ps[-1], ps[0]


def ref_now(root: Path, runners=RUNNERS, override=None):
    if override is not None:
        return override
    cands = []
    for name in runners:
        ex = load_json(root / BOT_REL / name / "exchange.json") or {}
        for row in ex.get("equity_curve") or []:
            try:
                t = parse_ts(row[0])
            except (TypeError, IndexError):
                t = None
            if t is not None:
                cands.append(t)
    st = load_json(root / CARRY_REL)
    if isinstance(st, dict):
        t = parse_ts(st.get("updated_at"))
        if t is not None:
            cands.append(t)
    if cands:
        return max(cands)
    return datetime.now(timezone.utc)


def summarize_runner(root: Path, name: str, now: datetime) -> dict:
    d = root / BOT_REL / name
    res = {"runner": name, "exists": d.is_dir()}
    if not d.is_dir():
        return res
    state = load_json(d / "state.json") or {}
    exchange = load_json(d / "exchange.json") or {}
    pts = load_curve(exchange)
    res["n_points"] = len(pts)
    if len(pts) >= 2:
        res["t0"], res["t1"] = pts[0][0], pts[-1][0]
        days = (pts[-1][0] - pts[0][0]).total_seconds() / 86400.0
        res["days"] = days
        res["ret_all"] = pct_return(pts)
        res["dd_all"] = max_dd_pct([v for _, v in pts])
    else:
        res["t0"] = res["t1"] = None
        res["days"] = 0.0 if len(pts) == 1 else None
        res["ret_all"] = None
        res["dd_all"] = max_dd_pct([v for _, v in pts])
    ws = now - timedelta(days=WEEK_DAYS)
    wpts = week_slice(pts, ws) if pts else []
    res["ret_week"] = pct_return(wpts)
    res["dd_week"] = max_dd_pct([v for _, v in wpts])
    try:
        fills = paper_report.summarize_dir(d) if paper_report is not None else None
    except Exception:
        fills = None
    res["dip_fills"] = (fills or {}).get("dip_fills")
    res["book_fills"] = (fills or {}).get("book_fills")
    res["fees"] = (fills or {}).get("fees")
    if not isinstance(exchange, dict) or not exchange:
        res["fees"] = None
    closed = closed_pnls(state, exchange)
    res["closed"] = [(p, r, k) for p, r, k, _ in closed]
    book = [r for r in closed if r[2] == "book"]
    dip = [r for r in closed if r[2] == "dip"]
    res["wr_all"], res["wr_book"], res["wr_dip"] = wr_line(closed), wr_line(book), wr_line(dip)
    res["n_book"], res["n_dip"] = len(book), len(dip)
    bw, bl = extremes(closed)
    res["biggest_win"], res["biggest_loss"] = bw, bl
    wclosed = [r for r in closed if r[3] is not None and r[3] >= ws]
    res["n_closed_week"] = len(wclosed)
    res["wr_week"] = wr_line(wclosed)
    # divergence vs plan
    if paper_divergence is not None and (root / PLAN_REL).exists():
        try:
            plan = paper_divergence.load_plan(str(root / PLAN_REL))
            dv = paper_divergence.summarize(str(d), plan)
            res["divergence"] = dv
        except Exception as e:
            res["divergence"] = {"verdict": "n/a", "note": f"khong tinh duoc ({e})"}
    else:
        res["divergence"] = {"verdict": "n/a", "note": "chua co plan trade_plan_v376.json"}
    # edge monitor
    if edge_monitor is not None:
        try:
            res["edge"] = edge_monitor.summarize_dir(d)
        except Exception as e:
            res["edge"] = {"worst": "n/a", "lines": [f"khong doc duoc edge ({e})"]}
    else:
        res["edge"] = {"worst": "n/a", "lines": ["thieu scripts/edge_monitor.py"]}
    # stop rules + go-live
    if stop_rules is not None:
        try:
            res["stops"] = stop_rules.summarize_runner(root, name)
        except Exception as e:
            res["stops"] = {"severity": "n/a", "lines": [f"khong doc duoc stop rules ({e})"]}
    else:
        res["stops"] = {"severity": "n/a", "lines": ["thieu scripts/stop_rules.py"]}
    return res


def summarize_carry(root: Path, now: datetime) -> dict:
    p = root / CARRY_REL
    res = {"exists": p.exists()}
    st = load_json(p)
    if not isinstance(st, dict) or not isinstance(st.get("positions"), dict):
        res["note"] = "chua co ledger (chua chay carry_paper)"
        res.update({"open": [], "history": [], "realised": 0.0,
                    "unrealised": 0.0, "wr": "n/a (0 dong)",
                    "biggest_win": None, "biggest_loss": None,
                    "n_entered_week": 0, "n_settled_week": 0})
        return res
    ws = now - timedelta(days=WEEK_DAYS)
    positions = st.get("positions") or {}
    open_rows = []
    unreal = 0.0
    n_entered_week = 0
    for coin in sorted(positions):
        pos = positions[coin] or {}
        try:
            u = float(pos.get("unrealised", 0.0) or 0.0)
        except (TypeError, ValueError):
            u = 0.0
        unreal += u
        try:
            basis = float(pos.get("ann_basis", 0.0)) * 100
            basis_s = f"{basis:+.2f}%/nam"
        except (TypeError, ValueError):
            basis_s = "n/a"
        et = parse_ts(pos.get("entry_time"))
        if et is not None and et >= ws:
            n_entered_week += 1
        open_rows.append(f"{coin} {pos.get('symbol', '?')}: basis {basis_s}, "
                         f"unrealised {u:+.2f} USDT")
    hist = st.get("history") if isinstance(st.get("history"), list) else []
    pnls = []
    n_settled_week = 0
    for h in hist:
        if not isinstance(h, dict):
            continue
        try:
            pnl = float(h.get("realised_pnl", 0.0))
        except (TypeError, ValueError):
            continue
        pnls.append(pnl)
        stt = parse_ts(h.get("settled_at"))
        if stt is not None and stt >= ws:
            n_settled_week += 1
    tot = st.get("totals") or {}
    try:
        realised = float(tot.get("realised_pnl", 0.0) or 0.0)
    except (TypeError, ValueError):
        realised = sum(pnls)
    nw = sum(1 for x in pnls if x > 0)
    res.update({"open": open_rows, "history": hist, "realised": realised,
                "unrealised": unreal, "n_settled": len(pnls),
                "wr": f"{100.0 * nw / len(pnls):.1f}% ({nw}/{len(pnls)})" if pnls else "n/a (0 dong)",
                "biggest_win": max(pnls) if pnls else None,
                "biggest_loss": min(pnls) if pnls else None,
                "n_entered_week": n_entered_week, "n_settled_week": n_settled_week,
                "equity_arg": st.get("equity_arg"), "f": st.get("f"),
                "updated_at": st.get("updated_at")})
    return res


def summarize_oos(root: Path, now: datetime) -> dict:
    """Doc LATEST oc_bookoos results.json (chi doc, khong chay scorer nang).

    Tra ve dict luon co: exists, path, refresh_cmd, age_days, stale.
    Neu doc duoc: window_start/end/days, total_pct, gate_dd_pct,
    max_dd_close_pct, max_dd_1m_pct, trades, band (p5/p50/p95),
    oos_percentile, reading (trong bien / duoi p5 -> dieu tra / tren p95).
    """
    path = root / OOS_REL
    base: dict = {"path": OOS_REL.as_posix(), "refresh_cmd": OOS_REFRESH_CMD,
                  "max_age_days": OOS_MAX_AGE_DAYS}
    if not path.exists():
        base.update({"exists": False, "ok": False, "age_days": None, "stale": True,
                     "note": "chua co results.json (chua chay scorer OOS)"})
        return base
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        age_days = (now - mtime).total_seconds() / 86400.0
    except (OSError, OverflowError):
        age_days = None
    res = load_json(path)
    if not isinstance(res, dict):
        base.update({"exists": True, "ok": False, "age_days": age_days,
                     "stale": True, "note": "khong doc duoc results.json (JSON loi)"})
        return base
    stale = age_days is None or age_days > OOS_MAX_AGE_DAYS
    w = res.get("window") if isinstance(res.get("window"), dict) else {}
    tr = res.get("trades") if isinstance(res.get("trades"), dict) else {}
    band_all = res.get("expectation_band") if isinstance(res.get("expectation_band"), dict) else {}
    band = band_all.get("total_pct") if isinstance(band_all.get("total_pct"), dict) else {}

    def _num(x):
        try:
            v = float(x)
        except (TypeError, ValueError):
            return None
        return v if v == v else None  # NaN -> None

    total = _num(res.get("total_pct"))
    p5, p50, p95 = _num(band.get("p5")), _num(band.get("p50")), _num(band.get("p95"))
    pctile = _num(res.get("oos_percentile_vs_band"))
    if total is None or p5 is None or p95 is None:
        reading = "n/a (chua du du lieu)"
    elif total < p5:
        reading = "duoi p5 -> dieu tra"
    elif total > p95:
        reading = "tren p95 (vuot ky vong)"
    else:
        reading = "trong bien (binh thuong)"
    base.update({
        "exists": True, "ok": True, "age_days": age_days, "stale": bool(stale),
        "window_start": w.get("start"), "window_end": w.get("end_exclusive"),
        "window_days": w.get("days"),
        "total_pct": total,
        "gate_dd_pct": _num(res.get("gate_dd_pct")),
        "max_dd_close_pct": _num(res.get("max_dd_close_pct")),
        "max_dd_1m_pct": _num(res.get("max_dd_1m_pct")),
        "trades": tr,
        "band": {"p5": p5, "p50": p50, "p95": p95,
                 "n": band_all.get("n"), "window_days": band_all.get("window_days")},
        "oos_percentile": pctile,
        "reading": reading,
        "label": res.get("label"),
        "mode": res.get("mode"),
    })
    return base


def _oos_trades_text(tr: dict) -> str:
    if not isinstance(tr, dict) or not tr:
        return "n/a"
    try:
        r, rw = int(tr.get("rungs") or 0), int(tr.get("rung_wins") or 0)
        b, bw = int(tr.get("book_episodes") or 0), int(tr.get("book_wins") or 0)
        a, aw = int(tr.get("all") if tr.get("all") is not None else r + b), \
            int(tr.get("all_wins") if tr.get("all_wins") is not None else rw + bw)
    except (TypeError, ValueError):
        return "n/a"
    def _wr(w, n):
        return f"{100.0 * w / n:.1f}% ({w}/{n})" if n else "n/a (0)"
    return (f"{r} rung (win {_wr(rw, r)}), {b} book episodes (win {_wr(bw, b)}), "
            f"tong {a} (win {_wr(aw, a)})")


def format_oos_lines(oos: dict) -> list:
    L = ["## OOS sach (du lieu moi)"]
    cmd = oos.get("refresh_cmd", OOS_REFRESH_CMD)
    age = oos.get("age_days")
    age_s = "n/a" if age is None else f"{max(0.0, age):.1f} ngay"
    if not oos.get("exists"):
        L.append(f"- chua co {oos.get('path', OOS_REL)} (du lieu moi) — "
                 f"lam moi: `{cmd}`")
        L.append("")
        return L
    if not oos.get("ok"):
        L.append(f"- {oos.get('note', 'khong doc duoc results.json')} — "
                 f"lam moi: `{cmd}` (tuoi ket qua: {age_s})")
        L.append("")
        return L
    if oos.get("stale"):
        L.append(f"- Ket qua CU {age_s} (> {OOS_MAX_AGE_DAYS:.0f} ngay) — "
                 f"can lam moi: `{cmd}` (so lieu duoi day la so cu)")
    else:
        L.append(f"- Nguon: `{oos.get('path')}` (tuoi {age_s}; lam moi: `{cmd}`)")
    L.append(f"- Cua so: {oos.get('window_start', 'n/a')} .. {oos.get('window_end', 'n/a')} "
             f"({oos.get('window_days', 'n/a')} ngay; {oos.get('label', '')})")
    dd = oos.get("gate_dd_pct")
    L.append(f"- Tong: {_fp(oos.get('total_pct'))}; DD gate "
             + (f"{dd:.2f}%" if isinstance(dd, (int, float)) else "n/a")
             + f" (close {_f2(oos.get('max_dd_close_pct'))}% / 1m {_f2(oos.get('max_dd_1m_pct'))}%)")
    L.append(f"- Trades: {_oos_trades_text(oos.get('trades') or {})}")
    b = oos.get("band") or {}
    n = b.get("n")
    L.append(f"- Band ky vong ({b.get('window_days', '?')}d, n={n if n is not None else '?'}): "
             f"p5 {_fp(b.get('p5'))} / p50 {_fp(b.get('p50'))} / p95 {_fp(b.get('p95'))}; "
             f"OOS percentile {oos.get('oos_percentile', 'n/a') if oos.get('oos_percentile') is not None else 'n/a'}")
    L.append(f"- Nhan dinh: {oos.get('reading', 'n/a')}")
    L.append("")
    return L


def build_report(root: Path = ROOT, now: datetime | None = None) -> dict:
    now = ref_now(root, override=now)
    runners = [summarize_runner(root, n, now) for n in RUNNERS]
    carry = summarize_carry(root, now)
    oos = summarize_oos(root, now)
    iso_y, iso_w, _ = now.isocalendar()
    return {"now": now, "iso_week": f"{iso_y}-W{iso_w:02d}",
            "runners": runners, "carry": carry, "oos": oos}


def _dv_text(dv: dict) -> str:
    if not isinstance(dv, dict):
        return "n/a (chua co du lieu)"
    if dv.get("status"):
        return f"{dv.get('status')} (verdict={dv.get('verdict')})"
    if dv.get("verdict") == "n/a":
        return f"n/a ({dv.get('note', 'chua co du lieu')})"
    return (f"bot {dv.get('bot_return_pct')}% vs plan {dv.get('plan_return_pct')}% = "
            f"{dv.get('div_pp_per_month')}pp/thang => {dv.get('verdict')}")


def format_markdown(rep: dict) -> str:
    now = rep["now"]
    L = [f"# Bao cao tuan {rep['iso_week']} (ref {now.isoformat()})", "",
         f"Tu thieu du lieu ghi 'n/a'. Muc go-live can toi thieu {GO_LIVE_MIN_DAYS:.0f} ngay "
         f"(8 tuan); tuan = {WEEK_DAYS:.0f} ngay truoc ref.", ""]
    for r in rep["runners"]:
        L.append(f"## {r['runner']}")
        if not r.get("exists"):
            L.append("- khong thay thu muc (bo qua)")
            L.append("")
            continue
        t0 = r.get("t0").isoformat() if r.get("t0") else "n/a"
        days = r.get("days")
        days_s = "n/a" if days is None else f"{days:.1f}/{GO_LIVE_MIN_DAYS:.0f} ngay"
        dd_all = r.get("dd_all")
        dd_all_s = f"{dd_all:.2f}%" if isinstance(dd_all, (int, float)) else "n/a"
        L.append(f"- Tu dau ({t0}): return {_fp(r.get('ret_all') if isinstance(r.get('ret_all'), (int, float)) else None)}, "
                 f"DD {dd_all_s}, bang chung {days_s}")
        L.append(f"- Tuan: return {_fp(r.get('ret_week') if isinstance(r.get('ret_week'), (int, float)) else None)}, "
                 f"DD " + (f"{r.get('dd_week'):.2f}%" if isinstance(r.get("dd_week"), (int, float)) else "n/a") +
                 f", dong {r.get('n_closed_week', 0)} piece (win rate {r.get('wr_week')})")
        L.append(f"- Fills: dip={r.get('dip_fills', 'n/a')}/book={r.get('book_fills', 'n/a')}, phi {_f2(r.get('fees'))}")
        L.append(f"- Book: {r.get('n_book', 0)} dong, win rate {r.get('wr_book')}; "
                 f"dip: {r.get('n_dip', 0)} dong, win rate {r.get('wr_dip')}; "
                 f"tat ca: {r.get('wr_all')}")
        bw, bl = r.get("biggest_win"), r.get("biggest_loss")
        L.append(f"- Win/loss lon nhat (dong): {_f2(bw)} / {_f2(bl)} USDT")
        L.append(f"- Divergence vs plan: {_dv_text(r.get('divergence'))}")
        edge = r.get("edge") or {}
        L.append(f"- Edge: {edge.get('worst', 'n/a')}")
        for x in list(edge.get("lines", []))[:2]:
            L.append(f"  - {x}")
        st = r.get("stops") or {}
        L.append(f"- Stop/go-live [{st.get('severity', 'n/a')}]:")
        for x in list(st.get("lines", []))[:4]:
            L.append(f"  - {x}")
        L.append("")
    c = rep["carry"]
    L.append("## Carry (paper_carry)")
    if not c.get("exists"):
        L.append(f"- {c.get('note', 'chua co ledger (chua chay carry_paper)')}")
    else:
        L.append(f"- Mo: {len(c.get('open', []))} cap; unrealised {c.get('unrealised', 0.0):+.2f} USDT; "
                 f"realised {c.get('realised', 0.0):+.2f} USDT (von {c.get('equity_arg')}, f={c.get('f')})")
        for x in c.get("open", []) or ["flat"]:
            L.append(f"  - {x}")
        L.append(f"- Quyet toan: {c.get('n_settled', 0)} cap, win rate {c.get('wr')}; "
                 f"lon nhat {_f2(c.get('biggest_win'))} / {_f2(c.get('biggest_loss'))} USDT")
        L.append(f"- Tuan: vao {c.get('n_entered_week', 0)} / quyet toan {c.get('n_settled_week', 0)}")
        L.append(f"- Cap nhat: {c.get('updated_at', 'n/a')}")
    L += [""] + format_oos_lines(rep.get("oos") or {"exists": False})
    L += ["## Tom tat 3 dong"]
    L += ["- " + x for x in plain_summary(rep)]
    L.append("")
    return "\n".join(L)


def plain_summary(rep: dict) -> list:
    """3 dong tom tat don gian: tuan, trang thai dung, duong toi go-live."""
    parts = []
    for r in rep["runners"]:
        if not r.get("exists"):
            parts.append(f"{r['runner']} chua chay")
        else:
            parts.append(f"{r['runner']} tuan {_fp(r.get('ret_week') if isinstance(r.get('ret_week'), (int, float)) else None)}"
                         f" / tu dau {_fp(r.get('ret_all') if isinstance(r.get('ret_all'), (int, float)) else None)}"
                         f" (dong {r.get('n_closed_week', 0)}, win {r.get('wr_week')})")
    l1 = "Tuan: " + "; ".join(parts) + "."
    stops = []
    for r in rep["runners"]:
        st = (r.get("stops") or {})
        if r.get("exists"):
            stops.append(f"{r['runner']} {st.get('severity', 'n/a')}")
    edges = []
    for r in rep["runners"]:
        eg = (r.get("edge") or {})
        if r.get("exists"):
            edges.append(f"{r['runner']} {eg.get('worst', 'n/a')}")
    l2 = ("Trang thai: stop [" + (", ".join(stops) if stops else "chua co du lieu") +
          "]; edge [" + (", ".join(edges) if edges else "chua co du lieu") + "].")
    days = [r.get("days") for r in rep["runners"] if r.get("exists") and r.get("days") is not None]
    dmax = max(days) if days else 0.0
    left = max(0.0, GO_LIVE_MIN_DAYS - dmax)
    l3 = (f"Go-live: {dmax:.0f}/{GO_LIVE_MIN_DAYS:.0f} ngay bang chung, con ~{left:.0f} ngay nua; "
          f"chua ket luan gi truoc 14 ngay (divergence) / 8 tuan (go-live).")
    return [l1, l2, l3]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bao cao tuan (chi doc).")
    ap.add_argument("--root", default=None, help="workspace root (mac dinh: repo)")
    ap.add_argument("--out", default=None, help="duong dan file md (mac dinh: artifacts/reports/weekly_<ISO-week>.md)")
    ap.add_argument("--now", default=None, help="moc thoi gian ISO (mac dinh: diem equity moi nhat)")
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else ROOT
    now = parse_ts(a.now) if a.now else None
    rep = build_report(root, now)
    text = format_markdown(rep)
    print(text)
    out = Path(a.out) if a.out else root / REPORTS_REL / f"weekly_{rep['iso_week']}.md"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"da ghi {out}")
    except OSError as e:
        print(f"khong ghi duoc {out}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
