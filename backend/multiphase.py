"""Multi-phase paper pipelines (registry v376 R2-4P): one strategy run as four sub-books on 4h clocks shifted by 0 / 1 / 2 / 3 hours,
each with 1/4 of the capital, never rebalanced.

- Each phase s has its own plan, produced by scripts/forward_trade_phase.py right after its shifted 4h bar closes (minute `offset` of
  every hour h with h % 4 == s), stored as kv trade_plan_v376_s{s} + plan_status_v376_s{s} (completed_slot = the shifted bar start).
- The merged plan trade_plan_v376 (what the web shows) lists, per coin, every sub-book's position / order / dip ladder tagged with its phase
  and expressed as fractions of the TOTAL account (sub-book capital = 1/4 x its own growth / the mix growth); the paper return is the mean
  of the four sub-books' net returns (= the four sub-accounts summed).
- Walk-forward evidence: summary_tm_v376 / tm_v376 from the v376 research outputs (research/.../v376/v376_mix_series.py ->
  artifacts/research/v376/v376_mix_series.json).
The 4h cycle of the other pipelines is untouched; pipeline.job_trade_plan / stale_plans / build_missing_summaries dispatch here for v376.
"""

from __future__ import annotations

import json
import subprocess

import pandas as pd

from .config import SETTINGS, log

PIPE = "v376"
PIPES = (PIPE,)
PHASES = (0, 1, 2, 3)
SUB_CANDIDATE = "v321_R2"
SCRIPT = "scripts/forward_trade_phase.py"
PLAN_DIR = "artifacts/research/advisor_shadow"
SERIES = "artifacts/research/v376/v376_mix_series.json"
H1_MS, H4_MS = 3600_000, 4 * 3600_000
CODE = (SCRIPT, "scripts/forward_trade.py", "scripts/forward_v205.py", "scripts/v321_r2_dip_agents.py",
        "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")


def _root():
    """The project root as the pipeline module sees it (tests point pipeline.ROOT at a temporary folder)."""
    from . import pipeline
    return pipeline.ROOT


def _ms(ts) -> int:
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return int(t.timestamp() * 1000)


def label(s: int) -> str:
    return f"khung +{s}h"


def sub_key(s: int) -> str:
    return f"trade_plan_{PIPE}_s{s}"


def phase_due_slot(now_ms: int, s: int, offset_min: int | None = None) -> int:
    """Start (ms) of the latest phase-s 4h bar whose plan must exist now (the previous one until `offset` minutes after its start)."""
    off = SETTINGS.schedule_offset_minutes if offset_min is None else offset_min
    t = now_ms - s * H1_MS - off * 60_000
    return t // H4_MS * H4_MS + s * H1_MS


def due_phases(db, now_ms: int | None = None) -> list[int]:
    now_ms = db.now_ms() if now_ms is None else now_ms
    out = []
    for s in PHASES:
        done = (db.kv_get(f"plan_status_{PIPE}_s{s}", {}) or {}).get("completed_slot")
        if not isinstance(done, int) or done < phase_due_slot(now_ms, s) or not db.kv_get(sub_key(s)):
            out.append(s)
    return out


def code_mtime_ms() -> int:
    return max((int((_root() / f).stat().st_mtime * 1000) for f in CODE if (_root() / f).exists()), default=0)


def run_phase(db, s: int, now_ms: int | None = None) -> dict:
    """forward_trade_phase.py for phase s -> kv trade_plan_v376_s{s} (without the per-bar state) + its completion marker."""
    now_ms = db.now_ms() if now_ms is None else now_ms
    slot = phase_due_slot(now_ms, s)
    cmd = [SETTINGS.python_exe, str(_root() / SCRIPT), "--candidate", SUB_CANDIDATE, "--phase", str(s)]
    p = subprocess.run(cmd, cwd=str(_root()), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**__import__("os").environ, "PYTHONUTF8": "1"}, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(f"phase {s} plan failed ({p.returncode}): {p.stderr[-1500:]}")
    plan = json.loads((_root() / PLAN_DIR / f"{sub_key(s)}.json").read_text(encoding="utf-8"))
    started = _ms(plan.get("freeze", 0)) <= now_ms
    if started and _ms(plan["decision_bar"]) < slot:
        raise RuntimeError(f"phase {s} plan artifact is older than its due shifted bar")
    plan.pop("bars", None)
    db.kv_set(sub_key(s), plan)
    db.kv_set(f"plan_status_{PIPE}_s{s}", {"completed_slot": slot, "completed_at": db.now_ms()})
    return plan


def _scale(d: dict | None, k: float, keys=("weight",)) -> dict | None:
    if not d:
        return None
    out = dict(d)
    for key in keys:
        if isinstance(out.get(key), (int, float)):
            out[f"{key}_sub"] = out[key]
            out[key] = out[key] * k
    return out


def merge(subs: dict, now=None) -> dict:
    """Four sub-book plans (phase -> plan) -> the merged plan of the web (see module docstring). Pure function."""
    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    phases = sorted(subs)
    started = {s: pd.Timestamp(subs[s]["freeze"]) <= now and bool(subs[s].get("equity_curve")) for s in phases}
    growth = {s: 1 + float(subs[s].get("net_return_pct") or 0.0) / 100 for s in phases}
    mix = sum(growth.values()) / len(phases)
    cap = {s: 0.25 * growth[s] / mix for s in phases}  # each sub-book's share of the total account now
    syms = list(next(iter(subs.values())).get("coins", {}).keys()) if subs else []
    latest = max(phases, key=lambda s: subs[s].get("generated_at", "")) if phases else None
    coins = {}
    for sym in syms:
        rows, dips, tw = [], [], 0.0
        for s in phases:
            c = (subs[s].get("coins") or {}).get(sym) or {}
            r = {"phase": s, "label": label(s), "capital": round(cap[s], 6), "state": c.get("state", "flat")}
            if c.get("position"):
                r["position"] = _scale(c["position"], cap[s])
            if c.get("order"):
                o = c["order"]
                r["order"] = _scale(o, cap[s], ("weight",) if o.get("kind") == "open" else (("amount",) if o.get("kind") == "add" else ()))
            rows.append(r)
            tw += cap[s] * float(c.get("target_weight") or 0.0)
            for d in c.get("dips") or []:
                dips.append(dict(_scale(d, cap[s], ("size_frac",)), phase=s, label=label(s)))
        states = [r["state"] for r in rows]
        agg = "position" if "position" in states else ("pending" if "pending" in states else "flat")
        price = ((subs[latest].get("coins") or {}).get(sym) or {}).get("price") if latest is not None else None
        out = {"symbol": sym, "price": price, "target_weight": tw, "state": agg, "subs": rows,
               "dips": sorted(dips, key=lambda d: (d["phase"], d.get("rung", 0))), "dip_size": None}
        first_pos = next((r for r in rows if r.get("position")), None)
        first_ord = next((r for r in rows if r.get("order")), None)
        if first_pos:
            out["position"] = dict(first_pos["position"], phase=first_pos["phase"])
        if first_ord:
            out["order"] = dict(first_ord["order"], phase=first_ord["phase"])
        coins[sym] = out
    events = []
    for s in phases:
        for e in subs[s].get("events") or []:
            events.append(dict(_scale(e, cap[s]), phase=s))
    events.sort(key=lambda e: (pd.Timestamp(e["t"]), e["phase"]))
    curves = []
    for s in phases:
        cv = subs[s].get("equity_curve") or []
        if cv:
            curves.append(pd.Series([float(v) for _, v in cv], index=pd.to_datetime([t for t, _ in cv], utc=True)))
    curve = []
    if curves:
        grid = pd.DatetimeIndex(sorted(set().union(*[c.index for c in curves])))
        tot = sum(c.reindex(grid, method="ffill").fillna(1.0) for c in curves) + (len(phases) - len(curves))
        curve = [(str(t), round(float(v) / len(phases), 6)) for t, v in tot.items()]
    nexts = [pd.Timestamp(subs[s]["next_decision"]) for s in phases if subs[s].get("next_decision")]
    return {"pipeline": "v376 R2-4P: R2 on four 4h clocks shifted 0/1/2/3 h, 1/4 capital each, never rebalanced",
            "pipeline_id": PIPE, "multi_phase": True,
            "phases": [{"phase": s, "label": label(s), "capital": round(cap[s], 6), "freeze": subs[s].get("freeze"),
                        "decision_bar": subs[s].get("decision_bar"), "next_decision": subs[s].get("next_decision"),
                        "net_return_pct": subs[s].get("net_return_pct"), "generated_at": subs[s].get("generated_at"),
                        "started": started[s]} for s in phases],
            "policy": next(iter(subs.values())).get("policy") if subs else None,
            "freeze": min((subs[s]["freeze"] for s in phases), key=pd.Timestamp) if phases else None,
            "generated_at": max((subs[s].get("generated_at", "") for s in phases), default=None),
            "decision_bar": max((subs[s]["decision_bar"] for s in phases), key=pd.Timestamp) if phases else None,
            "next_decision": str(min(nexts)) if nexts else None,
            "net_return_pct": round(100 * (mix - 1), 3), "coins": coins, "events": events, "equity_curve": curve,
            "rules": "four R2 sub-books on 4h clocks shifted 0/1/2/3 h (bars from 00/01/02/03 UTC), 1/4 capital each, never rebalanced; "
                     "each sub-book: limit entries, SL market / TP limit, R2 dip ladder with 5m-close bot stops + 8-sigma native backstop, "
                     "Bybit fees, adverse funding. Weights are fractions of the total account. Research output only."}


def store_paper(db, subs: dict) -> str:
    """Paper window as orders / trades under 'paper_v376' (each sub-book's trades, sizes x its 1/4 capital, tagged with the phase)."""
    from . import history_tm
    src = f"paper_{PIPE}"
    orders, trades = [], []
    for s in sorted(subs):
        ev = [dict(e, t=pd.Timestamp(e["t"])) for e in subs[s].get("events") or []]
        for o in history_tm.build_orders(ev):
            o = list(o)
            o[8] = o[8] * 0.25 if isinstance(o[8], (int, float)) else o[8]
            orders.append(tuple(o[:16]) + (f"paper {label(s)}",))
        trades += [(src, _ms(e["t"]), e["symbol"], e["kind"], e.get("side"), e.get("price"), 0.25 * float(e.get("weight") or 0.0),
                    json.dumps({**{k: v for k, v in e.items() if k not in ("t", "symbol", "kind", "side", "price", "weight")}, "phase": s},
                               default=str)) for e in ev]
    with db.write() as c:
        c.execute("DELETE FROM run_books WHERE run_id IN (SELECT id FROM runs WHERE source = ?)", (src,))
        for tb in ("runs", "trades", "orders"):
            c.execute(f"DELETE FROM {tb} WHERE source = ?", (src,))
        c.executemany("INSERT INTO orders(source, symbol, kind, side, signal_t, entry_t, entry_px, sl, tp, size, adds, exit_t, exit_px, "
                      "exit_reason, pnl_pct, avg_px, fills, entry_type) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      [(src,) + o for o in orders])
        c.executemany("INSERT INTO trades(source, t, symbol, kind, side, price, weight, extra) VALUES(?,?,?,?,?,?,?,?)", trades)
    return f"{src}: {len(orders)} orders"


def refresh(db, now_ms: int | None = None, phases=None, slot: int | None = None) -> str:
    """Run the due phases (or the given ones), then rebuild the merged plan from the four stored sub-plans."""
    now_ms = db.now_ms() if now_ms is None else now_ms
    todo = due_phases(db, now_ms) if phases is None else list(phases)
    msgs, failures = [], []
    for s in todo:
        try:
            plan = run_phase(db, s, now_ms)
            msgs.append(f"{label(s)}: " + ", ".join(f"{c['symbol'][:-4]} {c['state']}" for c in plan["coins"].values())
                        + f"; paper {plan['net_return_pct']}%")
        except Exception as exc:  # noqa: BLE001 - one phase must not block the others
            failures.append(f"{label(s)} FAILED: {type(exc).__name__}: {exc}"[:1500])
            log.error("v376 %s", failures[-1])
    subs = {s: db.kv_get(sub_key(s)) for s in PHASES}
    if all(subs.values()):
        merged = merge(subs, pd.Timestamp(now_ms, unit="ms", tz="UTC"))
        path = _root() / PLAN_DIR / f"trade_plan_{PIPE}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(merged, indent=1, default=str), encoding="utf-8")
        tmp.replace(path)
        store_paper(db, subs)
        db.kv_set(f"trade_plan_{PIPE}", merged)
        msgs.append(f"merged paper {merged['net_return_pct']}%")
        if not failures and not due_phases(db, now_ms):
            db.kv_set(f"plan_status_{PIPE}", {"completed_slot": now_ms // H4_MS * H4_MS if slot is None else slot, "completed_at": db.now_ms()})
    else:
        failures.append("merged plan not built: sub-plans missing for " + ", ".join(label(s) for s in PHASES if not subs[s]))
    msg = f"trade_plan_{PIPE}: " + " | ".join(msgs + failures)
    if failures:
        raise RuntimeError(msg)
    return msg


def stale_reason(db, now_ms: int) -> str | None:
    """Sub-plan checks for the data check (the merged plan's generic checks run in pipeline.stale_plans)."""
    code_ms = code_mtime_ms()
    for s in PHASES:
        plan = db.kv_get(sub_key(s))
        done = (db.kv_get(f"plan_status_{PIPE}_s{s}", {}) or {}).get("completed_slot")
        if not plan:
            return f"{label(s)}: no stored sub-plan"
        if not isinstance(done, int) or done < phase_due_slot(now_ms, s):
            return f"{label(s)}: not completed for its due shifted bar"
        if not (_root() / PLAN_DIR / f"{sub_key(s)}.json").exists():
            return f"{label(s)}: sub-plan file missing"
        try:
            if plan.get("generated_at") and _ms(plan["generated_at"]) < code_ms:
                return f"{label(s)}: plan code changed after the sub-plan was generated"
        except Exception:  # noqa: BLE001
            pass
    return None


def build_summary(db) -> str:
    """summary_tm_v376 + tm_v376 equity / orders from the v376 research outputs (v376_mix_series.py)."""
    path = _root() / SERIES
    if not path.exists():
        raise RuntimeError(f"{SERIES} missing: run research/parallel/rounds/parallel-20260906-r2/v376/v376_mix_series.py")
    d = json.loads(path.read_text(encoding="utf-8"))
    summary = dict(d["summary"], source="v376 research (R2_4P mix of four phase sub-books)", note=d.get("note"))
    src = f"tm_{PIPE}"
    orders = []
    for s, rows in sorted(d.get("orders", {}).items(), key=lambda x: int(x[0])):
        for o in rows:
            o = list(o)
            o[8] = o[8] * 0.25 if isinstance(o[8], (int, float)) else o[8]
            o[16] = f"{o[16]} {label(int(s))}"
            orders.append(tuple(o))
    with db.write() as c:
        c.execute("DELETE FROM run_books WHERE run_id IN (SELECT id FROM runs WHERE source = ?)", (src,))
        for tb in ("runs", "trades", "equity", "orders"):
            c.execute(f"DELETE FROM {tb} WHERE source = ?", (src,))
        c.executemany("INSERT INTO orders(source, symbol, kind, side, signal_t, entry_t, entry_px, sl, tp, size, adds, exit_t, exit_px, "
                      "exit_reason, pnl_pct, avg_px, fills, entry_type) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      [(src,) + o for o in orders])
        c.executemany("INSERT INTO equity(source, t, equity) VALUES(?, ?, ?)", [(src, _ms(t), float(v)) for t, v in d["equity"]])
        c.execute("INSERT INTO kv(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (f"summary_{src}", json.dumps(summary)))
    return f"{src}: {len(d['equity'])} bars, {len(orders)} orders (4 phases), 5y {summary.get('monthly_5y')}%/month"
