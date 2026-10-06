"""Deployed-bot reaction latency vs research friction scenarios (read-only).

Measures from paper logs (no writes to bot state, no network):
  (a) plan latency       = plan generated_at - 4h phase bar close (decision_bar)
  (b) placement latency  = first place/amend of an entry link - plan generated_at
                           (only for bars whose plan file is still on disk)
  (c) end-to-end latency = first place/amend of an entry link - bar close
                           (decoded from the link suffix, works for all bars)
  (d) protection latency = TP/SL placement - fill time (same piece)

Research friction reference (research/diagnostics/oc_d13robust/robust_d13.py):
  base: win_start=5 (book) / sleeve_start=16 (dip)
  S2:   win_start=15 / sleeve_start=16  (book +10 min, dips unchanged)
  S3:   win_start=30 / sleeve_start=31  (book +25 min, dips +15 min)
(engine_user.py: win_start = first minute a new book limit may fill,
sleeve_start = first minute a dip-ladder bid may fill.)

Link encoding (bot/mirror.py): book b{phase}{SYM}{t36(issued)},
dip d{phase}{SYM}{rung*10}{t36(bar)}; both suffixes decode to the bar close.
Entry links end with 'E', protection with 'S'/'T' (same piece prefix).

Usage:
  .venv/Scripts/python.exe scripts/latency_report.py [--json]
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_GLOB = str(ROOT / "artifacts" / "research" / "advisor_shadow" / "trade_plan_v376*.json")
RUNNER_GLOB = str(ROOT / "artifacts" / "bot" / "paper_d17bfg2*" / "actions.jsonl")

B36 = "0123456789abcdefghijklmnopqrstuvwxyz"
LINK_RE = re.compile(r"^[bd](\d)([A-Z]+)(\d*)([0-9a-z]+)([EST])$")

# Research friction minutes (robust_d13.py run_phase extra dicts).
BASE_WIN, BASE_SLEEVE = 5, 16
S2_WIN, S2_SLEEVE = 15, 16
S3_WIN, S3_SLEEVE = 30, 31


def parse_ts(x):
    if x is None:
        return None
    try:
        t = datetime.fromisoformat(str(x))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc)


def f36(s: str):
    """Base-36 minute timestamp -> aware datetime (inverse of mirror.t36)."""
    n = 0
    for ch in s:
        n = n * 36 + B36.index(ch)
    return datetime.fromtimestamp(n * 60, tz=timezone.utc)


def parse_link(link: str):
    """Return dict(kind, phase, sym, rung, bar, entry) or None for non book/dip links."""
    if not link:
        return None
    m = LINK_RE.match(link)
    if not m:
        return None
    ph, sym, rung, core, tail = m.groups()
    kind = "book" if link[0] == "b" else "dip"
    try:
        bar = f36(core)
    except (ValueError, IndexError, OverflowError, OSError):
        return None
    return {
        "kind": kind,
        "phase": int(ph),
        "sym": sym,
        "rung": (int(rung) / 10.0) if rung else None,
        "bar": bar,
        "entry": tail == "E",
    }


def summarize(vals):
    """Distribution summary in minutes (median / p90 / max per assignment)."""
    v = sorted(float(x) for x in vals)
    if not v:
        return {"n": 0, "min": None, "median": None, "p90": None, "max": None}
    def pct(p):
        k = (len(v) - 1) * p / 100.0
        lo, hi = math.floor(k), math.ceil(k)
        return v[lo] if lo == hi else v[lo] + (v[hi] - v[lo]) * (k - lo)
    return {"n": len(v), "min": round(v[0], 3), "median": round(pct(50), 3),
            "p90": round(pct(90), 3), "max": round(v[-1], 3)}


def load_plans():
    out = []
    for fp in sorted(glob.glob(PLAN_GLOB)):
        try:
            d = json.loads(Path(fp).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        gen, dec = parse_ts(d.get("generated_at")), parse_ts(d.get("decision_bar"))
        if gen is None or dec is None:
            continue
        out.append({"file": Path(fp).name, "phase": d.get("phase"),
                    "decision_bar": dec, "generated_at": gen,
                    "plan_lat_min": (gen - dec).total_seconds() / 60.0})
    return out


def load_actions(path: Path):
    recs = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return recs
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except ValueError:
            continue
    return recs


def link_of(rec):
    if not isinstance(rec, dict):
        return None
    if rec.get("link"):
        return rec["link"]
    pay = rec.get("payload")
    if isinstance(pay, dict) and pay.get("orderLinkId"):
        return pay["orderLinkId"]
    return None


def first_placements(recs):
    """Entry-link -> first place/amend datetime (insertion order = log order)."""
    first = {}
    for r in recs:
        if r.get("op") not in ("place", "amend"):
            continue
        link = link_of(r)
        info = parse_link(link) if link else None
        if info is None or not info["entry"]:
            continue
        t = parse_ts(r.get("t"))
        if t is None:
            continue
        first.setdefault(link, t)
    return first


def protection_latencies(recs):
    """Fill-link -> minutes to first TP/SL place of the same piece."""
    fills = {}
    for r in recs:
        if r.get("op") != "fill":
            continue
        link = r.get("link")
        t = parse_ts(r.get("t"))
        if not link or t is None or not link.endswith("E"):
            continue
        fills.setdefault(link, t)
    if not fills:
        return []
    placed: dict[str, list] = {}
    for r in recs:
        if r.get("op") not in ("place", "amend"):
            continue
        link = link_of(r)
        t = parse_ts(r.get("t"))
        if not link or t is None or link.endswith("E"):
            continue
        placed.setdefault(link, []).append(t)
    out = []
    for flink, ft in fills.items():
        piece = flink[:-1]
        cands = []
        for suffix in ("S", "T"):
            ts = placed.get(piece + suffix)
            if ts:
                cands.extend(x for x in ts if x >= ft)
        if cands:
            out.append((min(cands) - ft).total_seconds() / 60.0)
    return out


def analyze_runner(runner_dir: Path, plans):
    recs = load_actions(runner_dir / "actions.jsonl")
    plan_by_bar = {}
    for p in plans:
        if p["phase"] is not None:
            plan_by_bar[(p["decision_bar"], p["phase"])] = p
    first = first_placements(recs)
    # Per-bar first order (assignment: "first order of a bar minus the bar close").
    # Group entry links by (bar, phase); late deep-rung re-placements must not
    # inflate the reaction latency, so each bar contributes ONE value.
    bar_first: dict[tuple, datetime] = {}
    bar_first_book: dict[tuple, datetime] = {}
    bar_first_dip: dict[tuple, datetime] = {}
    for link, t0 in first.items():
        info = parse_link(link)
        key = (info["bar"], info["phase"])
        if key not in bar_first or t0 < bar_first[key]:
            bar_first[key] = t0
        slot = bar_first_book if info["kind"] == "book" else bar_first_dip
        if key not in slot or t0 < slot[key]:
            slot[key] = t0
    def e2e_list(slot):
        out = []
        for (bar, _ph), t0 in slot.items():
            e2e = (t0 - bar).total_seconds() / 60.0
            if -5.0 <= e2e <= 240.0:
                out.append(e2e)
        return out
    e2e_all = e2e_list(bar_first)
    e2e_book = e2e_list(bar_first_book)
    e2e_dip = e2e_list(bar_first_dip)
    plc_book, plc_dip, plc_all = [], [], []
    for slot, buf in ((bar_first, plc_all), (bar_first_book, plc_book),
                      (bar_first_dip, plc_dip)):
        for (bar, ph), t0 in slot.items():
            p = plan_by_bar.get((bar, ph))
            if p is None:
                continue
            plc = (t0 - p["generated_at"]).total_seconds() / 60.0
            buf.append(plc)
    prot = protection_latencies(recs)
    steady = lambda xs: [x for x in xs if x <= 35.0]
    return {
        "actions": len(recs),
        "entry_links": len(first),
        "bars": len(bar_first),
        "end_to_end_all_min": summarize(e2e_all),
        "end_to_end_book_min": summarize(e2e_book),
        "end_to_end_dip_min": summarize(e2e_dip),
        "end_to_end_steady_all_min": summarize(steady(e2e_all)),
        "end_to_end_steady_book_min": summarize(steady(e2e_book)),
        "end_to_end_steady_dip_min": summarize(steady(e2e_dip)),
        "placement_exact_all_min": summarize(plc_all),
        "placement_exact_book_min": summarize(plc_book),
        "placement_exact_dip_min": summarize(plc_dip),
        "protection_min": summarize(prot),
    }


def friction_verdict(e2e_book_med, e2e_dip_med):
    """Which research latency the real bot is closest to (base / S2 / S3)."""
    def dist(med, targets):
        return min(targets, key=lambda t: abs(med - t))
    book_ref = {BASE_WIN: "base(5)", S2_WIN: "S2(15)", S3_WIN: "S3(30)"}
    dip_ref = {BASE_SLEEVE: "base/S2(16)", S3_SLEEVE: "S3(31)"}
    b = dist(e2e_book_med, list(book_ref)) if e2e_book_med is not None else None
    d = dist(e2e_dip_med, list(dip_ref)) if e2e_dip_med is not None else None
    return {"book": book_ref.get(b), "dip": dip_ref.get(d)}


def build_report():
    plans = load_plans()
    plan_lats = [p["plan_lat_min"] for p in plans]
    runners = {}
    for fp in sorted(glob.glob(RUNNER_GLOB)):
        d = Path(fp).parent
        runners[d.name] = analyze_runner(d, plans)
    verdict = {}
    for name, r in runners.items():
        verdict[name] = friction_verdict(r["end_to_end_book_min"]["median"],
                                         r["end_to_end_dip_min"]["median"])
    return {
        "plan_latency_min": summarize(plan_lats),
        "plans": [{"file": p["file"], "phase": p["phase"],
                   "decision_bar": p["decision_bar"].isoformat(),
                   "generated_at": p["generated_at"].isoformat(),
                   "plan_lat_min": round(p["plan_lat_min"], 3)} for p in plans],
        "friction_min": {"base": {"book": BASE_WIN, "dip": BASE_SLEEVE},
                         "S2": {"book": S2_WIN, "dip": S2_SLEEVE},
                         "S3": {"book": S3_WIN, "dip": S3_SLEEVE}},
        "runners": runners,
        "closest": verdict,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Paper-bot latency report (read-only).")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = ap.parse_args(argv)
    rep = build_report()
    if args.json:
        print(json.dumps(rep, indent=1, default=str))
        return rep
    print("plan latency (generated_at - decision_bar), min: n=%(n)s min=%(min)s med=%(median)s p90=%(p90)s max=%(max)s" % rep["plan_latency_min"])
    for f in rep["plans"]:
        print("  %(file)s phase=%(phase)s bar=%(decision_bar)s gen=%(generated_at)s lat=%(plan_lat_min)s min" % f)
    print("friction: base book/dip %s/%s | S2 %s/%s | S3 %s/%s min"
          % (BASE_WIN, BASE_SLEEVE, S2_WIN, S2_SLEEVE, S3_WIN, S3_SLEEVE))
    for name, r in rep["runners"].items():
        print("[%s] actions=%d entry_links=%d bars=%d" % (name, r["actions"], r["entry_links"], r["bars"]))
        for k in ("end_to_end_all_min", "end_to_end_book_min", "end_to_end_dip_min",
                  "end_to_end_steady_all_min", "end_to_end_steady_book_min",
                  "end_to_end_steady_dip_min", "placement_exact_all_min",
                  "placement_exact_book_min", "placement_exact_dip_min",
                  "protection_min"):
            s = r[k]
            print("  %s: n=%s min=%s med=%s p90=%s max=%s" % (k, s["n"], s["min"], s["median"], s["p90"], s["max"]))
        print("  closest research latency: %s" % rep["closest"][name])
    return rep


if __name__ == "__main__":
    main()
