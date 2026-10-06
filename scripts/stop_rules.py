"""Nguong dung + dieu kien go-live (chi doc, khong network, khong keys).

Su dung:
  python scripts/stop_rules.py [--json out.json] [--root PATH]

Doc DUY NHAT file trong cac thu muc runner trien khai
(artifacts/bot/paper_d17bfg2, artifacts/bot/paper_d17bfg2c):
exchange.json (equity_curve), state.json + actions.jsonl (stop/TP, loi cycle),
trade_plan_v376.json (divergence), prospective_scorecard.json / DB app.db
(phan vi bootstrap). Khong cham .env, khong start/stop process, khong commit.

Nguon nguong (docs/DEPLOYMENT_PLAN_VI.md):
  muc 4 (ca hai san pham, tien that):
    (1) DD tai khoan > 20% -> dung mo lenh moi, chi giu SL/TP;
    (2) lo mot thang > 10% -> giam von dung mot nua trong thang ke tiep;
    (3) phan vi loi nhuan thuc < 5 sau >= 8 tuan -> dung.
  muc 2 buoc 3 (tien that nho, sau toi thieu 8 tuan, do tren bot giay):
    (a) phan vi bot giay >= 20 cua phan phoi bootstrap trung thuc
        cung so ngay (scripts/prospective_scorecard.py);
    (b) DD bot giay <= 15%;
    (c) lech bot giay so voi ke hoach paper <= 1.5 diem %/thang
        (scripts/paper_divergence.py; truoc 14 ngay 'too early' la binh thuong);
    (d) khong loi cycle_error keo dai > 1 gio, khong vi the nao thieu stop.

Moi rule in mot dong tieng Viet: OK / WATCH / STOP
(STOP chi khi rule bi vuot that su VOI DU DU LIEU), cong dong
'go-live: chua du / du dieu kien' cho moi runner.
Exit code: 2 neu co STOP, 1 neu co WATCH/CHUA DAT, 0 neu tat ca OK/DAT.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT_REL = Path("artifacts/bot")
PLAN_REL = Path("artifacts/research/advisor_shadow/trade_plan_v376.json")
SCORECARD_REL = Path("artifacts/research/advisor_shadow/prospective_scorecard.json")
DB_REL = Path("artifacts/web/app.db")

RUNNERS = ("paper_d17bfg2", "paper_d17bfg2c")
# runner dir -> pipeline key trong prospective_scorecard.json (BOT_DIRS).
SCORECARD_KEY = {"paper_d17bfg2": "bot_paper_d17bfg2", "paper_d17bfg2c": None}

# --- nguong (docs/DEPLOYMENT_PLAN_VI.md muc 2 + muc 4) ---
STOP_DD = 0.20          # muc 4: DD > 20% -> dung mo lenh moi
GOLIVE_DD = 0.15        # muc 2(b): DD <= 15%
MONTH_HALVE = 0.10      # muc 4: lo thang > 10% -> giam mot nua von thang sau
STOP_PCT = 5.0          # muc 4: phan vi < 5 sau >= 8 tuan -> dung
GOLIVE_PCT = 20.0       # muc 2(a): phan vi >= 20
MIN_WEEKS = 8.0         # toi thieu 8 tuan cho (a) va rule phan vi
MIN_DAYS_DIVERGENCE = 14.0  # muc 2(c): du 14 ngay moi PASS/FAIL
DIVERGENCE_PP_MONTH = 1.5
DAYS_PER_MONTH = 365.25 / 12
CYCLE_ERROR_SPAN_S = 3600.0  # muc 2(d): cycle_error keo dai > 1 gio

OK, WATCH, STOP = "OK", "WATCH", "STOP"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def load_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_curve(exchange: dict) -> list[tuple]:
    """Equity points [(datetime, float)] sap xep theo thoi gian (chi doc)."""
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


def running_dd(equities: list[float]) -> float | None:
    """Max drawdown dang phan so (0.21 = 21%). None khi chua du du lieu."""
    if len(equities) < 2:
        return None
    peak, worst = equities[0], 0.0
    for v in equities:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return worst


def weeks_of_evidence(pts: list[tuple]) -> float | None:
    if len(pts) < 2:
        return None
    return (pts[-1][0] - pts[0][0]).total_seconds() / 86400.0 / 7.0


def live_return(pts: list[tuple]) -> float | None:
    """Loi nhuan tich luy dang phan so tu diem dau den diem cuoi."""
    if len(pts) < 2 or not pts[0][1]:
        return None
    return pts[-1][1] / pts[0][1] - 1.0


def current_month_return(pts: list[tuple], equity0) -> tuple[str | None, float | None]:
    """Loi nhuan % cua thang lich hien tai (diem cuoi).

    Moc la equity cuoi thang truoc, hoac equity0 cho thang dau tien.
    Tra ve (nhan_thang 'YYYY-MM', pct) ; (None, None) khi chua du du lieu.
    """
    if len(pts) < 2:
        return None, None
    last_of_month: dict[str, float] = {}
    order: list[str] = []
    for t, v in pts:
        k = t.strftime("%Y-%m")
        if k not in order:
            order.append(k)
        last_of_month[k] = v
    cur = order[-1]
    if len(order) >= 2:
        ref = last_of_month[order[-2]]
    else:
        try:
            ref = float(equity0)
        except (TypeError, ValueError):
            return cur, None
    if not ref:
        return cur, None
    return cur, 100.0 * (last_of_month[cur] - ref) / ref


def stop_dd_status(dd: float | None) -> str:
    """Rule (1): DD > 20% -> STOP. WATCH tu 15% (nguong go-live)."""
    if dd is None:
        return WATCH  # chua du du lieu -> khong STOP som (caller ghi ro ly do)
    if dd > STOP_DD:
        return STOP
    if dd > GOLIVE_DD:
        return WATCH
    return OK


def stop_month_status(mret: float | None) -> str:
    """Rule (2): lo thang > 10% -> STOP (hanh dong: giam mot nua von)."""
    if mret is None:
        return WATCH  # chua du du lieu -> khong STOP som
    if mret <= -100.0 * MONTH_HALVE:
        return STOP
    if mret < 0:
        return WATCH
    return OK


def stop_percentile_status(pct: float | None, weeks: float | None) -> str:
    """Rule (3): phan vi < 5 sau >= 8 tuan -> STOP; truoc 8 tuan khong STOP."""
    if pct is None or weeks is None or weeks < MIN_WEEKS:
        return WATCH  # chua du 8 tuan / chua co band -> khong STOP som
    if pct < STOP_PCT:
        return STOP
    if pct < GOLIVE_PCT:
        return WATCH
    return OK


def scorecard_row(root: Path, pipeline: str | None) -> dict | None:
    if not pipeline:
        return None
    sc = load_json(root / SCORECARD_REL)
    if not isinstance(sc, dict):
        return None
    for r in sc.get("rows") or []:
        if isinstance(r, dict) and r.get("pipeline") == pipeline:
            return r
    return None


def bootstrap_percentile(live_ret: float, days: float, daily, draws: int = 4000,
                         block: int = 10, seed: int = 0) -> float | None:
    """Phan vi cua live_ret trong bootstrap (giong prospective_scorecard)."""
    try:
        import numpy as np
    except ImportError:
        return None
    if daily is None or len(daily) <= block or days < 0.5:
        return None
    rng = np.random.default_rng(seed)
    n = max(1, int(round(days)))
    out = np.empty(draws)
    for q in range(draws):
        path = []
        while len(path) < n:
            st = int(rng.integers(0, len(daily) - block))
            path.extend(daily[st:st + block])
        out[q] = float(np.prod(1.0 + np.array(path[:n])) - 1.0)
    return float(100.0 * (out <= live_ret).mean())


def research_daily_v376(root: Path):
    """Daily returns dev 2021-09-24..2025-09-24 cua tm_v376 (lazy pandas)."""
    try:
        import sqlite3

        import pandas as pd
    except ImportError:
        return None
    db = root / DB_REL
    if not db.exists():
        return None
    try:
        con = sqlite3.connect(db)
        rows = con.execute(
            "SELECT t, equity FROM equity WHERE source = ? ORDER BY t",
            ("tm_v376",)).fetchall()
        con.close()
    except Exception:
        return None
    if not rows:
        return None
    s = pd.Series([e for _, e in rows],
                  index=pd.to_datetime([t for t, _ in rows], unit="ms", utc=True))
    s = s[(s.index >= pd.Timestamp("2021-09-24", tz="UTC"))
          & (s.index < pd.Timestamp("2025-09-24", tz="UTC"))]
    return s.resample("1D").last().dropna().pct_change().dropna().to_numpy()


def paper_percentile(root: Path, runner: str, pts: list[tuple]) -> tuple[float | None, str]:
    """Phan vi paper vs band scorecard san co; tinh lai khi thieu/hu.

    Tra ve (percentile|None, ghi_chu_nguon).
    """
    if len(pts) < 2:
        return None, "chua co equity_curve"
    days = (pts[-1][0] - pts[0][0]).total_seconds() / 86400.0
    ret = live_return(pts)
    if ret is None or days < 0.5:
        return None, f"moi {days:.2f} ngay (<0.5d): chua du du lieu"
    row = scorecard_row(root, SCORECARD_KEY.get(runner))
    if row and row.get("percentile") is not None:
        try:
            sdays = float(row.get("days", 0))
        except (TypeError, ValueError):
            sdays = 0.0
        if abs(sdays - days) <= 1.0:
            return float(row["percentile"]), (
                f"band scorecard san co (p05 {row.get('expected_p05')}% / "
                f"p50 {row.get('expected_p50')}% / p95 {row.get('expected_p95')}%)")
    daily = research_daily_v376(root)
    pct = bootstrap_percentile(ret, days, daily)
    if pct is None:
        return None, "khong co band scorecard/DB de tinh phan vi"
    return pct, "tinh lai bootstrap tm_v376 (block 10d, 4000 draws, seed 0)"


def long_cycle_error(actions_path: Path) -> tuple[bool, str]:
    """True neu co chuoi cycle_error keo dai > 1 gio (muc 2d)."""
    times = []
    try:
        lines = Path(actions_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return False, "khong doc duoc actions.jsonl"
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("op") == "cycle_error":
            t = parse_ts(r.get("t"))
            if t is not None:
                times.append(t)
    if len(times) < 2:
        return False, f"{len(times)} cycle_error (can >= 2 de do do dai)"
    times.sort()
    span_s = (times[-1] - times[0]).total_seconds()
    if span_s > CYCLE_ERROR_SPAN_S:
        return True, (f"cycle_error tu {times[0].isoformat()} den "
                      f"{times[-1].isoformat()} (>{CYCLE_ERROR_SPAN_S / 3600:.0f}h)")
    return False, f"{len(times)} cycle_error trong {span_s / 3600:.1f}h (<1h)"


def open_without_stop(state: dict, exchange: dict | None) -> list[str]:
    """Cac piece dang mo thieu stop (tai su dung logic bot_health)."""
    try:
        bh = _load("stop_rules_bot_health", "scripts/bot_health.py")
    except Exception:
        bh = None
    if bh is not None:
        try:
            links = (state or {}).get("links") or {}
            ex_orders = exchange.get("orders") if isinstance(exchange, dict) else None
            missing = []
            for pid, pc in ((state or {}).get("ledger") or {}).items():
                if not isinstance(pc, dict) or not pc.get("qty", 0) > 0:
                    continue
                stop_ok, _ = bh.open_piece_exits(pid, links, ex_orders)
                if not stop_ok:
                    missing.append(f"{pid}({pc.get('symbol')}:no-stop)")
            return missing
        except Exception:
            pass
    # fallback: coi nhu thieu stop neu khong tim thay link stop/TP nao
    missing = []
    ledger = (state or {}).get("ledger") or {}
    links = (state or {}).get("links") or {}
    for pid, pc in ledger.items():
        if not isinstance(pc, dict) or not pc.get("qty", 0) > 0:
            continue
        if pid + "S" not in links and pid + "T" not in links:
            missing.append(f"{pid}({pc.get('symbol')}:no-stop?)")
    return missing


def divergence_status(root: Path, bot_dir: Path, days: float | None) -> tuple[str, str]:
    """Gate (c): paper-vs-plan <= 1.5pp/thang (du 14 ngay moi PASS/FAIL)."""
    try:
        pdv = _load("stop_rules_paper_divergence", "scripts/paper_divergence.py")
    except Exception as e:  # pragma: no cover - phong thu
        return "CHUA DU", f"khong tai duoc paper_divergence ({e})"
    plan_path = root / PLAN_REL
    if not plan_path.exists():
        return "CHUA DU", "khong thay trade_plan_v376.json"
    try:
        plan = pdv.load_plan(str(plan_path))
    except (OSError, ValueError) as e:
        return "CHUA DU", f"khong doc duoc plan ({e})"
    try:
        r = pdv.summarize(str(bot_dir), plan)
    except Exception as e:  # pragma: no cover - phong thu
        return "CHUA DU", f"khong tinh duoc divergence ({e})"
    if r.get("verdict") == "PASS":
        return "DAT", (f"lech {r.get('div_pp_per_month')}pp/thang "
                       f"(bot {r.get('bot_return_pct')}% vs plan {r.get('plan_return_pct')}%)")
    if r.get("verdict") == "FAIL":
        return "CHUA DAT", (f"lech {r.get('div_pp_per_month')}pp/thang "
                            f"vuot 1.5 (bot {r.get('bot_return_pct')}% vs plan {r.get('plan_return_pct')}%)")
    d = r.get("days", days)
    return "CHUA DU", f"moi {d}d (<14d): too early la binh thuong"


def summarize_runner(root: Path, runner: str) -> dict:
    """Tong hop stop rules + go-live gates cho mot runner (chi doc)."""
    d = root / BOT_REL / runner
    if not d.is_dir():
        return {"runner": runner, "exists": False, "severity": "ok",
                "lines": [f"{runner}: khong thay thu muc (bo qua) => {OK}"]}
    exchange = load_json(d / "exchange.json") or {}
    state = load_json(d / "state.json") or {}
    pts = load_curve(exchange)
    eqs = [v for _, v in pts]
    dd = running_dd(eqs)
    weeks = weeks_of_evidence(pts)
    days = (pts[-1][0] - pts[0][0]).total_seconds() / 86400.0 if len(pts) >= 2 else None
    mlabel, mret = current_month_return(pts, exchange.get("equity0"))
    pct, pct_src = paper_percentile(root, runner, pts)

    # --- 3 stop rules ---
    s_dd = stop_dd_status(dd)
    s_m = stop_month_status(mret)
    s_p = stop_percentile_status(pct, weeks)
    dd_s = "n/a" if dd is None else f"{100 * dd:.2f}%"
    m_s = "n/a" if mret is None else f"{mret:+.2f}% ({mlabel})"
    if pct is None:
        p_s = f"n/a ({pct_src})"
    else:
        w_s = "n/a" if weeks is None else f"{weeks:.1f} tuan"
        p_s = f"{pct:.1f} (sau {w_s}; {pct_src})"

    lines = [
        f"{runner}: DD tai khoan {dd_s} (nguong dung >20%, canh bao >15%) => {s_dd}"
        + (" - DUNG MO LENH MOI, chi giu SL/TP" if s_dd == STOP else ""),
        f"{runner}: loi nhuan thang hien tai {m_s} (lo >10% -> giam mot nua von thang sau) => {s_m}",
        f"{runner}: phan vi loi nhuan {p_s} (dung khi <5 sau >=8 tuan) => {s_p}",
    ]

    # --- 4 go-live gates ---
    if weeks is None or weeks < MIN_WEEKS or pct is None:
        g_a = ("CHUA DU", f"sau {0.0 if weeks is None else weeks:.1f} tuan (<8 tuan): chua du du lieu")
    elif pct >= GOLIVE_PCT:
        g_a = ("DAT", f"phan vi {pct:.1f} >= 20")
    else:
        g_a = ("CHUA DAT", f"phan vi {pct:.1f} < 20")
    if dd is None:
        g_b = ("CHUA DU", "chua co equity_curve")
    elif dd <= GOLIVE_DD:
        g_b = ("DAT", f"DD {100 * dd:.2f}% <= 15%")
    else:
        g_b = ("CHUA DAT", f"DD {100 * dd:.2f}% > 15%")
    g_c = divergence_status(root, d, days)
    long_err, err_note = long_cycle_error(d / "actions.jsonl")
    missing = open_without_stop(state, exchange if isinstance(exchange, dict) else None)
    if not long_err and not missing:
        g_d = ("DAT", f"khong cycle_error >1h ({err_note}); moi vi the co stop")
    else:
        why = "; ".join(([f"cycle_error keo dai: {err_note}"] if long_err else [])
                        + ([f"thieu stop: {', '.join(missing)}"] if missing else []))
        g_d = ("CHUA DAT", why)
    for gate, val in (("(a) phan vi >=20", g_a), ("(b) DD <=15%", g_b),
                      ("(c) lech vs plan <=1.5pp/thang", g_c),
                      ("(d) khong loi cycle >1h + du stop", g_d)):
        lines.append(f"{runner}: go-live {gate}: {val[1]} => {val[0]}")

    gates_ok = all(g[0] == "DAT" for g in (g_a, g_b, g_c, g_d))
    if gates_ok and weeks is not None and weeks >= MIN_WEEKS:
        lines.append(f"{runner}: go-live: du dieu kien (ca 4 cong a-d DAT, sau {weeks:.1f} tuan)")
    else:
        w_txt = "n/a" if weeks is None else f"{weeks:.1f} tuan"
        lines.append(f"{runner}: go-live: chua du (sau {w_txt}; can ca 4 cong a-d DAT sau >=8 tuan)")

    stops = [s_dd, s_m, s_p]
    if STOP in stops:
        sev = "critical"
    elif (WATCH in stops and not (s_p == WATCH and (weeks is None or weeks < MIN_WEEKS)
                                  and s_dd == OK and s_m == OK)):
        # WATCH vi chua du 8 tuan o rule phan vi (paper moi chay) khong day verdict;
        # WATCH that su (DD/thang/phan vi du lieu) moi canh bao.
        sev = "warning"
    elif any(g[0] == "CHUA DAT" for g in (g_a, g_b, g_c, g_d)):
        sev = "warning"
    else:
        sev = "ok"
    return {"runner": runner, "exists": True, "dd": dd, "weeks": weeks, "days": days,
            "month": mret, "month_label": mlabel, "percentile": pct,
            "stops": {"dd": s_dd, "month": s_m, "percentile": s_p},
            "gates": {"a": g_a[0], "b": g_b[0], "c": g_c[0], "d": g_d[0]},
            "golive": gates_ok and weeks is not None and weeks >= MIN_WEEKS,
            "severity": sev, "lines": lines}


def summarize_all(root: Path = ROOT, runners: tuple = RUNNERS) -> list[dict]:
    return [summarize_runner(root, r) for r in runners]


def worst_severity(reps: list[dict]) -> str:
    order = {"ok": 0, "warning": 1, "critical": 2}
    sev = "ok"
    for r in reps:
        if order.get(r.get("severity", "ok"), 0) > order[sev]:
            sev = r["severity"]
    return sev


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Nguong dung + go-live (chi doc).")
    ap.add_argument("--root", default=None, help="workspace root (mac dinh: repo)")
    ap.add_argument("--json", default=None, help="ghi JSON ra PATH")
    ap.add_argument("runners", nargs="*", default=list(RUNNERS),
                    help="ten runner (mac dinh: paper_d17bfg2 paper_d17bfg2c)")
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else ROOT
    reps = summarize_all(root, tuple(a.runners))
    for r in reps:
        for line in r["lines"]:
            print(line)
    if a.json:
        Path(a.json).write_text(json.dumps({"runners": reps}, indent=1,
                                           default=str, ensure_ascii=False) + "\n",
                                encoding="utf-8")
        print(f"da ghi {a.json}")
    return {"ok": 0, "warning": 1, "critical": 2}[worst_severity(reps)]


if __name__ == "__main__":
    sys.exit(main())
