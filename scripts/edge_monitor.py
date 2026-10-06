"""Giam sat canh bao som edge (chi doc, khong network, khong keys).

Su dung:
  python scripts/edge_monitor.py artifacts/bot/paper_d17bfg2 [--now ISO] [--json]

Doc DUY NHAT cac file trong thu muc runner (actions.jsonl, state.json,
exchange.json); khong cham .env, khong start/stop process, khong commit.

Nguong (tu research/diagnostics/oc_edgedecay/REPORT.md + results.json,
5 nam 2021-09-24..2026-09-23, G2 = R2B1D17BFG2):
  (1) trung binh 6 thang gan nhat < 1.61%/thang (p10 lich su cua 55 cua so
      truot 6 thang; trung vi 5.44) -> dieu tra;
  (2) TP rate dip cua mot nua nam kin < 0.434 (p10 lich su cua 10 nua nam;
      trung vi 0.488) -> dieu tra. Vo nguong la dieu tra, khong phai hanh
      dong giao dich (diagnostic-only).
Phan vi lich su de doi chieu (REPORT muc 1):
  thang: mean 6.10, median 3.65, std 11.10, min -7.17,
  p10 -3.01 / p25 -0.69 / p75 9.33 / p90 17.86, max 63.83;
  trailing-12m p10 3.08 (trung vi 6.07) chi de tham khao.

Quy tac du lieu toi thieu (khong bao gio bao dong gia):
  < 2 thang loi nhuan -> 'chua du du lieu' (metric thang);
  < 30 exit dip -> 'chua du du lieu' (metric TP rate).
Trang thai moi dong: OK / WATCH / INVESTIGATE; INVESTIGATE chi khi da du
du lieu ma vo nguong canh bao.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- nguong lich su (oc_edgedecay) ---
TRAIL6_ALERT = 1.61
TRAIL6_MEDIAN = 5.44
TRAIL12_P10 = 3.08
TRAIL12_MEDIAN = 6.07
TP_ALERT = 0.434
TP_MEDIAN = 0.488
MONTHLY_P10 = -3.01
MONTHLY_P25 = -0.69
MONTHLY_MEDIAN = 3.65
MONTHLY_P75 = 9.33
MONTHLY_P90 = 17.86

MIN_MONTHS = 2
MIN_DIP_EXITS = 30
TRAIL_DAYS = 182

STOP_REASONS = {"close5_stop", "stop", "backstop", "rung_sl"}


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
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_actions(path: Path):
    recs = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except ValueError:
            continue
    return recs


def piece_of(link):
    if isinstance(link, str) and len(link) > 1 and link[-1] in "ETSMX":
        return link[:-1]
    return link


def load_state_links(state):
    out = {}
    for link, rec in ((state or {}).get("links") or {}).items():
        o = (rec or {}).get("order") or {}
        out[link] = (o.get("kind"), o.get("piece") or piece_of(link),
                      (o.get("meta") or {}).get("kind"))
    return out


def piece_kind_of(pid, state_links, ledger):
    for _link, (_k, piece, meta) in (state_links or {}).items():
        if piece == pid and meta in ("dip", "book"):
            return meta
    pc = (ledger or {}).get(pid) or {}
    if pc.get("kind") in ("dip", "book"):
        return pc["kind"]
    if str(pid).startswith("d"):
        return "dip"
    if str(pid).startswith("b"):
        return "book"
    return None


def _ref_time(curve_times, exec_times, action_times, override=None):
    if override is not None:
        return override
    cands = [t for t in list(curve_times) + list(exec_times) + list(action_times)
             if t is not None]
    if cands:
        return max(cands)
    return datetime.now(timezone.utc)


def monthly_returns(curve, equity0):
    """Loi nhuan % theo thang lich tu equity_curve [[ts, eq], ...].

    Thang r = 100*(eq_cuoi_thang / eq_cuoi_thang_truoc - 1); thang dau tien
    dung equity0 lam moc (neu co), neu khong thi thang dau = 0.0.
    """
    pts = []
    for row in curve or []:
        try:
            pts.append((parse_ts(row[0]), float(row[1])))
        except (TypeError, ValueError, IndexError):
            continue
    pts = [(t, v) for t, v in pts if t is not None]
    pts.sort(key=lambda r: r[0])
    if not pts:
        return []
    last_of_month: dict[str, float] = {}
    order: list[str] = []
    for t, v in pts:
        k = t.strftime("%Y-%m")
        if k not in last_of_month:
            order.append(k)
        last_of_month[k] = v
    out = []
    prev = None
    try:
        base = float(equity0) if equity0 is not None else None
    except (TypeError, ValueError):
        base = None
    for k in order:
        last = last_of_month[k]
        ref = prev if prev is not None else base
        if ref is None:
            out.append((k, 0.0))
        elif ref > 0:
            out.append((k, 100.0 * (last - ref) / ref))
        else:
            out.append((k, 0.0))
        prev = last
    return out


def _classify_exit(link, state_links, reason_by_link):
    """(piece, bucket) cua mot lenh exit; entry -> (None, None)."""
    info = (state_links or {}).get(link)
    if info is not None:
        kind, piece, _meta = info
    else:
        kind, piece = None, piece_of(link)
    if kind in ("entry", "add"):
        return None, None
    if kind is None:
        last = str(link)[-1:] if link else ""
        if last == "E":
            return None, None
        if last == "T":
            return piece, "tp"
        if last == "S":
            return piece, "stop"
        # M / X / U ...: market exit -> phan biet stop-close5 vs time
        # qua ly do market_exit trong actions.jsonl.
        if reason_by_link.get(link) in STOP_REASONS:
            return piece, "stop"
        return piece, "time"
    if kind == "tp":
        return piece, "tp"
    if kind == "stop":
        return piece, "stop"
    # reduce / market-exit links (X/M/U...): stop chi khi ly do la close-stop.
    if reason_by_link.get(link) in STOP_REASONS:
        return piece, "stop"
    return piece, "time"


def dip_exits(state, exchange, actions):
    """Cac exit dip (time, bucket, link): uu tien execs, dedupe theo link.

    execs (exchange.json) la su that khop lenh (co execTime); actions.jsonl
    op=fill cua runner log lai moi exec (ke ca exit) nen duoc dung lam
    fallback khi thieu exchange.json. Moi link chi dem 1 lan.
    """
    ledger = (state or {}).get("ledger") or {}
    state_links = load_state_links(state)
    reason_by_link: dict[str, str] = {}
    for r in actions or []:
        if not isinstance(r, dict) or r.get("op") != "market_exit":
            continue
        pay = r.get("payload") or {}
        link = pay.get("orderLinkId") or r.get("link")
        reason = r.get("reason")
        if link and reason and link not in reason_by_link:
            reason_by_link[str(link)] = str(reason)
    by_link: dict[str, tuple] = {}
    for e in ((exchange or {}).get("execs") or []):
        if not isinstance(e, dict):
            continue
        link = e.get("orderLinkId") or ""
        if not link or link in by_link:
            continue
        try:
            qty = float(e.get("execQty", 0))
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        piece, bucket = _classify_exit(link, state_links, reason_by_link)
        if bucket is None:
            continue
        if piece_kind_of(piece, state_links, ledger) != "dip":
            if not (str(link).startswith("d") and piece_kind_of(piece, state_links, ledger) is None):
                # link dip khong co metadata van dem; con lai bo qua (book/carry).
                if piece_kind_of(piece, state_links, ledger) is not None:
                    continue
                if not str(link).startswith("d"):
                    continue
        t = parse_ms(e.get("execTime"))
        by_link[link] = (t, bucket, link)
    for r in actions or []:
        if not isinstance(r, dict) or r.get("op") != "fill":
            continue
        link = r.get("link") or (r.get("payload") or {}).get("orderLinkId") or ""
        if not link or link in by_link:
            continue
        piece, bucket = _classify_exit(link, state_links, reason_by_link)
        if bucket is None:
            continue
        if piece_kind_of(piece, state_links, ledger) != "dip":
            if piece_kind_of(piece, state_links, ledger) is not None:
                continue
            if not str(link).startswith("d"):
                continue
        by_link[link] = (parse_ts(r.get("t")), bucket, link)
    return sorted((v for v in by_link.values() if v[0] is not None),
                  key=lambda r: r[0])


def tp_rate(exits):
    n = len(exits)
    tp = sum(1 for _, b, _ in exits if b == "tp")
    return (tp / n) if n else None, tp, n


def _status_6m(mean, n):
    if n < MIN_MONTHS:
        return "CHUA DU DU LIEU"
    if mean < TRAIL6_ALERT:
        return "INVESTIGATE"
    if mean < TRAIL6_MEDIAN:
        return "WATCH"
    return "OK"


def _status_tp(rate, n):
    if n < MIN_DIP_EXITS:
        return "CHUA DU DU LIEU"
    if rate < TP_ALERT:
        return "INVESTIGATE"
    if rate < TP_MEDIAN:
        return "WATCH"
    return "OK"


def summarize_dir(d: Path, now: datetime | None = None) -> dict:
    d = Path(d)
    actions = load_actions(d / "actions.jsonl")
    state = load_json(d / "state.json") or {}
    exchange = load_json(d / "exchange.json") or {}
    curve = (exchange.get("equity_curve") or []) if isinstance(exchange, dict) else []
    equity0 = (exchange.get("equity0") if isinstance(exchange, dict) else None)
    curve_times = []
    for row in curve:
        try:
            t = parse_ts(row[0])
        except (TypeError, IndexError):
            t = None
        if t is not None:
            curve_times.append(t)
    exec_times = [parse_ms((e or {}).get("execTime"))
                  for e in ((exchange or {}).get("execs") or []) if isinstance(e, dict)]
    action_times = [parse_ts((r or {}).get("t")) for r in actions
                    if isinstance(r, dict)]
    ref = _ref_time(curve_times, exec_times, action_times, now)

    monthly = monthly_returns(curve, equity0)
    last6 = monthly[-6:]
    mean6 = (sum(r for _, r in last6) / len(last6)) if last6 else None
    st_monthly = ("CHUA DU DU LIEU" if len(monthly) < MIN_MONTHS
                  else ("WATCH" if monthly[-1][1] < MONTHLY_P10 else "OK"))
    st_6m = _status_6m(mean6 if mean6 is not None else 0.0, len(monthly))

    exits = dip_exits(state, exchange, actions)
    cutoff = ref - timedelta(days=TRAIL_DAYS)
    trail = [e for e in exits if e[0] >= cutoff]
    rate_trail, tp_trail, n_trail = tp_rate(trail)
    rate_all, tp_all, n_all = tp_rate(exits)
    st_trail = _status_tp(rate_trail if rate_trail is not None else 0.0, n_trail)
    st_all = _status_tp(rate_all if rate_all is not None else 0.0, n_all)

    if monthly:
        m_txt = ", ".join(f"{k} {v:+.2f}%" for k, v in monthly[-6:])
    else:
        m_txt = "khong co equity_curve"
    m_val = f"cac thang gan nhat (n={len(monthly)}): {m_txt}"
    m_thr = (f"nguong tham khao p10 thang {MONTHLY_P10:.2f}%/thang "
             f"(trung vi {MONTHLY_MEDIAN:.2f}, p25 {MONTHLY_P25:.2f})")
    if len(monthly) < MIN_MONTHS:
        l1 = (f"loi nhuan thang: {m_val} | {m_thr} | CHUA DU DU LIEU "
              f"(can >= {MIN_MONTHS} thang, khong canh bao)")
    else:
        l1 = f"loi nhuan thang: {m_val} | {m_thr} | {st_monthly}"

    if mean6 is None:
        l2 = (f"trung binh 6 thang gan nhat: khong tinh duoc (n=0) | nguong canh bao "
              f"{TRAIL6_ALERT:.2f}%/thang (p10 lich su 55 cua so 6 thang, trung vi "
              f"{TRAIL6_MEDIAN:.2f}) | CHUA DU DU LIEU (khong canh bao)")
    elif len(monthly) < MIN_MONTHS:
        l2 = (f"trung binh 6 thang gan nhat: {mean6:+.2f}%/thang (n={len(last6)}) | nguong canh bao "
              f"{TRAIL6_ALERT:.2f}%/thang (p10 lich su, trung vi {TRAIL6_MEDIAN:.2f}) | "
              f"CHUA DU DU LIEU (can >= {MIN_MONTHS} thang, khong canh bao)")
    else:
        extra = (" — can dieu tra, khong phai hanh dong giao dich"
                 if st_6m == "INVESTIGATE" else "")
        l2 = (f"trung binh 6 thang gan nhat: {mean6:+.2f}%/thang (n={len(last6)}) | nguong canh bao "
              f"{TRAIL6_ALERT:.2f}%/thang (p10 lich su 55 cua so 6 thang, trung vi "
              f"{TRAIL6_MEDIAN:.2f}) | {st_6m}{extra}")

    if n_trail < MIN_DIP_EXITS:
        l3 = (f"TP rate dip {TRAIL_DAYS} ngay: chua tinh duoc (n={n_trail} exit, can >= "
              f"{MIN_DIP_EXITS}) | nguong {TP_ALERT:.3f} (p10 lich su 10 nua nam, trung vi "
              f"{TP_MEDIAN:.3f}) | CHUA DU DU LIEU (khong canh bao)")
    else:
        extra = (" — can dieu tra, khong phai hanh dong giao dich"
                 if st_trail == "INVESTIGATE" else "")
        l3 = (f"TP rate dip {TRAIL_DAYS} ngay: {rate_trail:.3f} (tp {tp_trail}/{n_trail}) | nguong "
              f"{TP_ALERT:.3f} (p10 lich su 10 nua nam, trung vi {TP_MEDIAN:.3f}) | "
              f"{st_trail}{extra}")

    if n_all < MIN_DIP_EXITS:
        l4 = (f"TP rate dip toan lich su: chua tinh duoc (n={n_all} exit, can >= "
              f"{MIN_DIP_EXITS}) | nguong tham khao {TP_ALERT:.3f} | CHUA DU DU LIEU "
              f"(khong canh bao)")
    else:
        l4 = (f"TP rate dip toan lich su: {rate_all:.3f} (tp {tp_all}/{n_all}) | nguong tham khao "
              f"{TP_ALERT:.3f} (p10 lich su, trung vi {TP_MEDIAN:.3f}) | {st_all}")

    worst = "OK"
    for s in (st_monthly, st_6m, st_trail, st_all):
        if s == "INVESTIGATE":
            worst = "INVESTIGATE"
            break
    if worst == "OK" and any(s == "WATCH" for s in (st_monthly, st_6m, st_trail, st_all)):
        worst = "WATCH"
    code = {"OK": 0, "WATCH": 1, "INVESTIGATE": 2,
            "CHUA DU DU LIEU": 0}[worst]
    return {"dir": str(d), "ref": ref, "monthly": monthly, "mean6": mean6,
            "n_months": len(monthly), "tp_trail": rate_trail,
            "tp_trail_n": n_trail, "tp_trail_tp": tp_trail,
            "tp_all": rate_all, "tp_all_n": n_all, "tp_all_tp": tp_all,
            "statuses": {"monthly": st_monthly, "mean6": st_6m,
                         "tp_trail": st_trail, "tp_all": st_all},
            "worst": worst, "exit": code, "lines": [l1, l2, l3, l4]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Giam sat canh bao som edge (chi doc).")
    ap.add_argument("dir", help="thu muc runner (actions.jsonl, state.json, exchange.json)")
    ap.add_argument("--now", default=None, help="moc thoi gian ISO (mac dinh: moc moi nhat trong file)")
    ap.add_argument("--json", nargs="?", const="-", default=None,
                    help="ghi JSON ra PATH (--json in stdout)")
    a = ap.parse_args(argv)
    now = parse_ts(a.now) if a.now else None
    rep = summarize_dir(Path(a.dir), now)
    for line in rep["lines"]:
        print(line)
    if a.json is not None:
        payload = json.dumps(rep, indent=1, default=str)
        if a.json == "-":
            print(payload)
        else:
            Path(a.json).write_text(payload + "\n", encoding="utf-8")
            print(f"da ghi {a.json}")
    return rep["exit"]


if __name__ == "__main__":
    sys.exit(main())
