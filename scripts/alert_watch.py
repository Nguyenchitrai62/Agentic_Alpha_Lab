"""Watcher canh bao CRITICAL cho runner trien khai (chi doc + log local, khong network ngoai localhost).

Su dung (chu tu chay tay):
  python scripts/alert_watch.py --every 300        # vong lap moi 300s
  python scripts/alert_watch.py --once             # mot lan (kiem tra tay)
  python scripts/alert_watch.py --every 60 --once --no-toast   # test khong toast

Moi N giay doc health cua cac runner trien khai bang ham san co
(scripts/bot_health.py check_dir, scripts/daily_status.py check_plan,
scripts/stop_rules.py summarize_runner — che do nhanh/local, khong doc
parquet collector, khong cham .env, khong start/stop process, khong commit)
va khi mot muc tro thanh CRITICAL thi hien Windows toast MỘT LAN cho moi
incident moi + ghi them vao artifacts/alerts/alerts.log; khi het thi ghi
'resolved'. Khong lap toast cho cung mot incident dang mo (de-dup trong
bo nho tien trinh).

6 loai CRITICAL theo doi:
  (0) backend_down: GET /health localhost that bai (backend tat: plan se cu),
  (1) unprotected: vi the mo thieu stop hoac TP (bot_health.unprotected),
  (2) qty_mismatch: so bot lech vi the san (bot_health.qty_mismatch),
  (3) cycle_stale: chu ky cuoi > 5 phut (state.json mtime / actions.jsonl),
  (4) plan_stale: plan > 4h30m CRITICAL, plan > 1h15m WARNING (daily_status.check_plan),
  (5) stop_rule: stop_rules STOP (DD > 20% / lo thang > 10% / phan vi < 5 sau >= 8 tuan),
  (6) carry_unhedged: chan carry lech hedge > 2 cycle (state carry.positions[*].unhedged_cycles).

Toast Windows: BurntToast KHONG co san nen dung [Windows.UI.Notifications]
co san qua powershell; that bai -> fallback `msg` / beep console.
LOCAL ONLY: khong gui di dau, khong credentials, chi localhost
(GET /health 127.0.0.1 + doc file local; khong start/stop process, khong commit).
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT_REL = Path("artifacts/bot")
PLAN_REL = Path("artifacts/research/advisor_shadow/trade_plan_v376.json")
ALERT_LOG_REL = Path("artifacts/alerts/alerts.log")

RUNNERS = ("paper_d17bfg2", "paper_d17bfg2c")
CYCLE_STALE_S = 300.0      # last cycle > 5 phut
PLAN_WARN_H = 1.25         # plan > 1h15m = WARNING
PLAN_STALE_H = 4.5         # plan > 4h30m
HEALTH_URL = "http://127.0.0.1:8724/health"  # localhost only
HEALTH_TIMEOUT = 3.0
MAX_UNHEDGED_CYCLES = 2    # carry lech hedge > 2 cycle
DEFAULT_INTERVAL = 20.0    # bot loop interval (cho bot_health.check_dir)


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


try:
    bot_health = _load("alert_watch_bot_health", "scripts/bot_health.py")
except Exception:  # pragma: no cover - giu watcher song khi thieu file
    bot_health = None
try:
    daily_status = _load("alert_watch_daily_status", "scripts/daily_status.py")
except Exception:  # pragma: no cover
    daily_status = None
try:
    stop_rules = _load("alert_watch_stop_rules", "scripts/stop_rules.py")
except Exception:  # pragma: no cover
    stop_rules = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _plan_age_h(plan) -> float | None:
    try:
        gen = bot_health.parse_ts((plan or {}).get("generated_at")) if bot_health else None
    except Exception:
        return None
    if gen is None:
        return None
    return (utcnow() - gen).total_seconds() / 3600


def check_backend_down(url: str = HEALTH_URL, timeout: float = HEALTH_TIMEOUT) -> tuple[bool, str]:
    """GET /health localhost; True+detail khi khong noi duoc (CRITICAL). Khong bao gio raise."""
    try:
        if daily_status is not None and hasattr(daily_status, "check_backend"):
            res = daily_status.check_backend(url, timeout)
            down = (not res.get("ok")) or res.get("severity") == "critical"
            return bool(down), str(res.get("line", ""))
    except Exception as e:  # phong thu: loi code check -> khong bao dong gia
        return False, f"check loi: {type(e).__name__}"
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=timeout) as r:
            code = getattr(r, "status", 200)
            if code != 200:
                return True, f"backend tat: plan se cu (HTTP {code})"
            return False, "backend song (GET /health OK)"
    except Exception as e:
        return True, f"backend tat: plan se cu (khong noi duoc {url}: {type(e).__name__})"


def extract_incidents(runner: str, rep: dict | None, stop_rep: dict | None,
                       carry_positions: dict | None, plan_stale: bool,
                       plan_detail: str = "",
                       plan_warn: bool = False, plan_warn_detail: str = "",
                       backend_down: bool = False,
                       backend_detail: str = "") -> list[dict]:
    """Pure: tu ket qua health (co the fake trong test) -> danh sach incident.

    Moi incident: {"key", "runner", "kind", "severity", "title", "detail"};
    key on dinh de de-dup. CRITICAL cho moi muc tru plan_warn (WARNING).
    """
    out: list[dict] = []
    rep = rep or {}
    for item in rep.get("unprotected") or []:
        out.append({"key": f"{runner}:unprotected:{item}", "runner": runner,
                    "kind": "unprotected", "severity": "critical",
                    "title": f"{runner}: vi the thieu stop/TP",
                    "detail": str(item)})
    for item in rep.get("qty_mismatch") or []:
        out.append({"key": f"{runner}:qty:{item}", "runner": runner,
                    "kind": "qty_mismatch", "severity": "critical",
                    "title": f"{runner}: lech so lieu voi san",
                    "detail": str(item)})
    try:
        age_s = rep.get("cycle_age_s")
        age_s = float(age_s) if age_s is not None else None
    except (TypeError, ValueError):
        age_s = None
    if age_s is None or age_s > CYCLE_STALE_S:
        age_txt = "khong ro (khong co timestamp)" if age_s is None else f"{age_s / 60:.1f} phut truoc"
        out.append({"key": f"{runner}:cycle_stale", "runner": runner,
                    "kind": "cycle_stale", "severity": "critical",
                    "title": f"{runner}: chu ky cuoi > 5 phut (runner dung?)",
                    "detail": f"last cycle {age_txt}"})
    if backend_down:
        out.append({"key": "backend:down", "runner": "-",
                    "kind": "backend_down", "severity": "critical",
                    "title": "backend tat: plan se cu",
                    "detail": backend_detail or "GET /health khong dap ung"})
    if plan_stale:
        out.append({"key": "plan:stale", "runner": "-",
                    "kind": "plan_stale", "severity": "critical",
                    "title": "plan cu > 4h30m (bot chi giu bao ve)",
                    "detail": plan_detail or f"plan age > {PLAN_STALE_H}h"})
    elif plan_warn:
        out.append({"key": "plan:warn", "runner": "-",
                    "kind": "plan_warn", "severity": "warning",
                    "title": "plan cu > 1h15m",
                    "detail": plan_warn_detail or f"plan age > {PLAN_WARN_H}h"})
    stops = ((stop_rep or {}).get("stops") or {}) if isinstance(stop_rep, dict) else {}
    for rule in ("dd", "month", "percentile"):
        if stops.get(rule) == "STOP":
            out.append({"key": f"{runner}:stop:{rule}", "runner": runner,
                        "kind": "stop_rule", "severity": "critical",
                        "title": f"{runner}: nguong DUNG ({rule})",
                        "detail": f"stop_rules {rule}=STOP"})
    if isinstance(carry_positions, dict):
        for coin in sorted(carry_positions):
            pos = carry_positions[coin] or {}
            try:
                n = int(pos.get("unhedged_cycles", 0) or 0)
            except (TypeError, ValueError):
                n = 0
            if n > MAX_UNHEDGED_CYCLES:
                out.append({"key": f"{runner}:carry_unhedged:{coin}", "runner": runner,
                            "kind": "carry_unhedged", "severity": "critical",
                            "title": f"{runner}: carry {coin} lech hedge > 2 cycle",
                            "detail": f"{coin} unhedged_cycles={n} (> {MAX_UNHEDGED_CYCLES})"})
    return out


def collect_incidents(root: Path = ROOT, now: datetime | None = None,
                      interval: float = DEFAULT_INTERVAL,
                      runners: tuple = RUNNERS,
                      backend_url: str = HEALTH_URL,
                      check_backend_fn=None) -> list[dict]:
    """Doc health that (local + GET /health localhost) cho cac runner. Khong bao gio raise."""
    now = now or utcnow()
    if bot_health is None:
        return [{"key": "watcher:no_bot_health", "runner": "-", "kind": "watcher",
                  "severity": "critical",
                  "title": "watcher: thieu scripts/bot_health.py",
                  "detail": "khong doc duoc health (kiem tra cay repo)"}]
    try:
        plan = bot_health.load_json(root / PLAN_REL)
    except Exception:
        plan = None
    plan_stale, plan_detail = False, ""
    plan_warn, plan_warn_detail = False, ""
    try:
        if daily_status is not None:
            pres = daily_status.check_plan(root, now)
            plan_stale = pres.get("severity") == "critical"
            plan_detail = pres.get("line", "") if plan_stale else ""
            plan_warn = pres.get("severity") == "warning"
            plan_warn_detail = pres.get("line", "") if plan_warn else ""
        else:
            age_h = _plan_age_h(plan)
            plan_stale = age_h is None or age_h > PLAN_STALE_H
            plan_detail = "khong doc duoc plan" if age_h is None else f"plan age {age_h:.1f}h"
            plan_warn = (age_h is not None and age_h > PLAN_WARN_H) and not plan_stale
            plan_warn_detail = "" if not plan_warn else f"plan age {age_h:.1f}h"
    except Exception:
        plan_stale, plan_detail = False, ""
        plan_warn, plan_warn_detail = False, ""
    try:
        if check_backend_fn is not None:
            _down, _detail = check_backend_fn()
            backend_down, backend_detail = bool(_down), str(_detail)
        else:
            backend_down, backend_detail = check_backend_down(backend_url, HEALTH_TIMEOUT)
    except Exception:
        backend_down, backend_detail = False, ""
    out: list[dict] = []
    for runner in runners:
        d = root / BOT_REL / runner
        if not d.is_dir():
            continue
        try:
            rep = bot_health.check_dir(d, plan, now, interval)
        except Exception as e:  # phong thu: bo qua runner loi, watcher van chay
            out.append({"key": f"{runner}:read_error", "runner": runner,
                        "kind": "watcher", "severity": "critical",
                        "title": f"{runner}: khong doc duoc health",
                        "detail": f"{type(e).__name__}: {e}"[:200]})
            continue
        try:
            stop_rep = stop_rules.summarize_runner(root, runner) if stop_rules else None
        except Exception:
            stop_rep = None
        try:
            st = bot_health.load_json(d / "state.json") or {}
            carry = (st.get("carry") or {}).get("positions")
        except Exception:
            carry = None
        out.extend(extract_incidents(runner, rep, stop_rep, carry, plan_stale, plan_detail,
                                       plan_warn, plan_warn_detail,
                                       backend_down, backend_detail))
    # plan/backend la global nhung extract them 1 lan moi runner -> dedup theo key
    seen, deduped = set(), []
    for inc in out:
        if inc["key"] in seen:
            continue
        seen.add(inc["key"])
        deduped.append(inc)
    return deduped


def diff_state(open_map: dict, current: list[dict]) -> tuple[list[dict], list[dict]]:
    """So sanh open hien tai voi poll moi: (moi_xuat_hien, da_het). Pure."""
    cur = {c["key"]: c for c in current}
    new = [cur[k] for k in cur if k not in open_map]
    resolved = [open_map[k] for k in open_map if k not in cur]
    return new, resolved


def append_log(log_path: Path, now: datetime, verb: str, inc: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{now.isoformat()} {verb} {inc['key']} | {inc.get('title', '')} | {inc.get('detail', '')}\n"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def notify_windows(title: str, body: str) -> bool:
    """Toast Windows bang [Windows.UI.Notifications] co san; that bai -> msg/beep.

    Tra ve True neu da hien (hoac fallback) thanh cong. LOCAL ONLY.
    """
    text = f"{title}: {body}"[:2000]
    print(f"[ALERT] {text}", flush=True)
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
        "ContentType=WindowsRuntime] | Out-Null; "
        "$t = [Windows.UI.Notifications.ToastTemplateType]::ToastText02; "
        "$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($t); "
        "$n = $x.GetElementsByTagName('text'); "
        "$n.Item(0).AppendChild($x.CreateTextNode($args[0])) | Out-Null; "
        "$n.Item(1).AppendChild($x.CreateTextNode($args[1])) | Out-Null; "
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($x); "
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        "'Agentic Alpha Lab').Show($toast);"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps,
                            "--", str(title)[:120], str(body)[:800]],
                           capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            return True
    except (OSError, subprocess.SubprocessError):
        pass
    try:  # fallback: popup msg tren session hien tai
        r = subprocess.run(["msg", "*", text[:400]], capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            return True
    except (OSError, subprocess.SubprocessError):
        pass
    try:  # fallback cuoi: beep console (van giu log file)
        print("\a", end="", flush=True)
    except Exception:
        pass
    return False


def poll_once(root: Path = ROOT, now: datetime | None = None,
              open_map: dict | None = None, interval: float = DEFAULT_INTERVAL,
              runners: tuple = RUNNERS, log_path: Path | None = None,
              notifier=None, collect_fn=None) -> dict:
    """Mot vong: thu thap -> diff -> toast 1 lan/incident moi -> log.

    notifier(title, body) de test inject fake; collect_fn(root, now) de inject fake.
    Tra ve {"current", "new", "resolved", "open"}; open_map duoc cap nhat tai cho.
    """
    now = now or utcnow()
    open_map = open_map if open_map is not None else {}
    log_path = log_path if log_path is not None else root / ALERT_LOG_REL
    current = collect_fn(root, now) if collect_fn else collect_incidents(root, now, interval, runners)
    new, resolved = diff_state(open_map, current)
    for inc in new:
        if notifier is not None:
            try:
                notifier(inc["title"], inc["detail"])
            except Exception:
                pass
        else:
            notify_windows(inc["title"], inc["detail"])
        try:
            append_log(log_path, now, "ALERT", inc)
        except OSError:
            pass
        open_map[inc["key"]] = inc
    for inc in resolved:
        try:
            append_log(log_path, now, "RESOLVED", inc)
        except OSError:
            pass
        open_map.pop(inc["key"], None)
    for inc in current:  # lam tuoi title/detail cua incident van mo
        if inc["key"] in open_map:
            open_map[inc["key"]] = inc
    return {"current": current, "new": new, "resolved": resolved, "open": open_map}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Watcher CRITICAL cho runner trien khai (local only).")
    ap.add_argument("--every", type=float, default=300.0, help="giay giua cac vong (mac dinh 300)")
    ap.add_argument("--once", action="store_true", help="chi chay mot vong roi thoat")
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                    help="bot loop interval giay cho bot_health (mac dinh 20)")
    ap.add_argument("--root", default=None, help="workspace root (mac dinh: repo)")
    ap.add_argument("--log", default=None, help="duong dan alerts.log (mac dinh artifacts/alerts/alerts.log)")
    ap.add_argument("--no-toast", action="store_true", help="chi log, khong hien toast")
    ap.add_argument("runners", nargs="*", default=list(RUNNERS),
                    help="ten runner (mac dinh: paper_d17bfg2 paper_d17bfg2c)")
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else ROOT
    log_path = Path(a.log) if a.log else root / ALERT_LOG_REL
    notifier = (lambda _t, _b: None) if a.no_toast else None
    open_map: dict = {}
    if a.once:
        rep = poll_once(root, utcnow(), open_map, a.interval, tuple(a.runners), log_path,
                        notifier=notifier)
        print(f"incidents dang mo: {len(rep['open'])}")
        for inc in rep["current"]:
            print(f"  - [{inc.get('severity', 'critical')}] {inc['key']}: "
                  f"{inc.get('title', '')} | {inc['detail']}")
        return 2 if rep["current"] else 0
    print(f"alert_watch: moi {a.every:g}s kiem tra {list(a.runners)} (Ctrl+C de dung)", flush=True)
    try:
        while True:
            rep = poll_once(root, utcnow(), open_map, a.interval, tuple(a.runners), log_path,
                            notifier=notifier)
            stamp = utcnow().isoformat(timespec="seconds")
            print(f"{stamp} mo: {len(rep['open'])} incident"
                  + (f" (+{len(rep['new'])} moi)" if rep["new"] else ""), flush=True)
            time.sleep(max(5.0, float(a.every)))
    except KeyboardInterrupt:
        print("alert_watch: dung (Ctrl+C).", flush=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
