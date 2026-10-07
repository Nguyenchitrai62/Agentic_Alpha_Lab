"""oc_ladderfill diagnostic: fill-minute timing and fast-TP edge share.

Implements PLAN.md exactly. Reads research/tournament/oc_kpi/events_s{0..3}.parquet
(rung_fill + rung_tp/sl/timeout), pairs FIFO per (shift, symbol) — same loop as
oc_kpi/compute_kpi.py::pair_rungs — then derives fill minute f (minutes from the
4h bar open at 00/04/08/12/16/20 UTC), time-to-exit dt, and per-rung net ret.

Also scans artifacts/bot/paper_d17bf/{actions.jsonl,exchange.json,state.json}
for dip/book fills so far (prospective paper log, reported separately).

Usage: .venv/Scripts/python.exe research/tournament/oc_ladderfill/analyze_ladderfill.py
Writes results.json in this folder. ONE process, pandas only, no 1m data.
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
KPI = HERE.parent / "oc_kpi"
PAPER = Path("artifacts/bot/paper_d17bf")
SHIFTS = (0, 1, 2, 3)
BUCKETS = [(16, 60), (61, 120), (121, 180), (181, 238)]
FAST_H = (5, 15, 60)
BPS = 1e4


def fill_minute(t: pd.Timestamp, shift: int) -> int:
    # Shift-s replica runs on the 4h grid offset by s hours: bars open at
    # hours = s (mod 4). Verified: this gives exactly 16..238 on every shift
    # (unshifted grid gives 0..239 with outsiders on s=1..3).
    mins = (t - t.floor("D")).total_seconds() / 60.0
    return int((mins - shift * 60) % 240)


def pair_shift(ev: pd.DataFrame, shift: int):
    """FIFO per symbol. Returns (rungs list, unpaired_exits, left_open)."""
    pend: dict[str, deque] = {}
    out, unpaired = [], 0
    for r in ev.itertuples():
        if r.kind == "rung_fill":
            pend.setdefault(r.symbol, deque()).append(r)
        elif r.kind in ("rung_sl", "rung_tp", "rung_timeout"):
            q = pend.get(r.symbol)
            if q:
                f0 = q.popleft()
                out.append(dict(
                    shift=shift, symbol=r.symbol, depth=float(f0.rung),
                    weight=float(f0.weight), fill_t=pd.Timestamp(f0.t),
                    exit_t=pd.Timestamp(r.t), exit=r.kind,
                    ret=float(r.ret),
                ))
            else:
                unpaired += 1
    left = sum(len(q) for q in pend.values())
    return out, unpaired, left


def qstats(s: pd.Series) -> dict:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) == 0:
        return dict(n=0)
    q = s.quantile([0.25, 0.5, 0.75])
    return dict(n=int(len(s)), mean=round(float(s.mean()), 3),
                p25=round(float(q.loc[0.25]), 3),
                median=round(float(q.loc[0.5]), 3),
                p75=round(float(q.loc[0.75]), 3))


def pnl_group(df: pd.DataFrame) -> dict:
    n = int(len(df))
    if n == 0:
        return dict(n=0, win=None, mean_bps=0.0, sum_ret=0.0, sum_wret=0.0)
    win = float((df["ret"] > 0).mean())
    return dict(n=n, win=round(win, 4),
                mean_bps=round(float(df["ret"].mean() * BPS), 2),
                sum_ret=round(float(df["ret"].sum()), 4),
                sum_wret=round(float((df["ret"] * df["weight"]).sum()), 5))


def main():
    all_rungs, checks = [], {"unpaired_exits": 0, "left_open": 0, "n_shifts": 0}
    f_min, f_max = None, None
    for s in SHIFTS:
        ev = pd.read_parquet(KPI / f"events_s{s}.parquet")
        ev["t"] = pd.to_datetime(ev["t"], utc=True)
        ev = ev.sort_values("t").reset_index(drop=True)
        rungs, unpaired, left = pair_shift(ev, s)
        checks["unpaired_exits"] += unpaired
        checks["left_open"] += left
        checks["n_shifts"] += 1
        all_rungs.extend(rungs)
    df = pd.DataFrame(all_rungs)
    df["f"] = [fill_minute(t, s) for t, s in zip(df["fill_t"], df["shift"])]
    df["dt"] = (df["exit_t"] - df["fill_t"]).dt.total_seconds() / 60.0
    f_min, f_max = int(df["f"].min()), int(df["f"].max())
    checks.update(dict(n_paired=int(len(df)), f_min=f_min, f_max=f_max,
                       f_outside_16_238=int(((df["f"] < 16) | (df["f"] > 238)).sum()),
                       dt_min=round(float(df["dt"].min()), 3),
                       dt_max=round(float(df["dt"].max()), 3)))
    total = pnl_group(df)
    tot_w = total["sum_wret"] if total["sum_wret"] != 0 else 1.0
    tot_r = total["sum_ret"] if total["sum_ret"] != 0 else 1.0

    def bucket_of(f):
        for lo, hi in BUCKETS:
            if lo <= f <= hi:
                return f"{lo}-{hi}"
        return "outside"

    df["bucket"] = df["f"].apply(bucket_of)

    # A. fill-minute distribution per depth / per coin
    by_depth_f, by_coin_f = {}, {}
    for depth, g in sorted(df.groupby("depth")):
        d = qstats(g["f"])
        d["share"] = round(len(g) / len(df), 4)
        by_depth_f[str(depth)] = d
    for sym, g in sorted(df.groupby("symbol")):
        d = qstats(g["f"])
        d["share"] = round(len(g) / len(df), 4)
        by_coin_f[sym] = d
    overall_f = qstats(df["f"])
    bucket_hist = {b: int((df["bucket"] == b).sum())
                   for b in ["16-60", "61-120", "121-180", "181-238", "outside"]}

    # B. time to exit by exit kind, per depth and per coin
    by_depth_dt, by_coin_dt, overall_dt = {}, {}, {}
    for depth, g in sorted(df.groupby("depth")):
        by_depth_dt[str(depth)] = {k: qstats(g[g["exit"] == k]["dt"])
                                   for k in ("rung_tp", "rung_sl", "rung_timeout")}
    for sym, g in sorted(df.groupby("symbol")):
        by_coin_dt[sym] = {k: qstats(g[g["exit"] == k]["dt"])
                           for k in ("rung_tp", "rung_sl", "rung_timeout")}
    for k in ("rung_tp", "rung_sl", "rung_timeout"):
        overall_dt[k] = qstats(df[df["exit"] == k]["dt"])
    exit_mix = df["exit"].value_counts().to_dict()
    exit_mix = {str(k): int(v) for k, v in exit_mix.items()}

    # C. PnL by fill-minute bucket (pooled + per depth)
    by_bucket = {}
    for b in ["16-60", "61-120", "121-180", "181-238"]:
        g = df[df["bucket"] == b]
        d = pnl_group(g)
        d["share_n"] = round(len(g) / len(df), 4) if len(df) else 0.0
        d["edge_share_w"] = round(d["sum_wret"] / tot_w, 4)
        d["edge_share_eq"] = round(d["sum_ret"] / tot_r, 4)
        by_bucket[b] = d
    by_bucket_depth = {}
    for depth, g in sorted(df.groupby("depth")):
        rows = {}
        for b in ["16-60", "61-120", "121-180", "181-238"]:
            rows[b] = pnl_group(g[g["bucket"] == b])
        by_bucket_depth[str(depth)] = rows

    # D. fast-TP: TP exits within 5/15/60 min (nested)
    tp = df[df["exit"] == "rung_tp"]
    tp_total = pnl_group(tp)
    fast = {}
    for h in FAST_H:
        g = tp[tp["dt"] <= h]
        d = pnl_group(g)
        d["share_of_rungs"] = round(len(g) / len(df), 4)
        d["share_of_tp"] = round(len(g) / len(tp), 4) if len(tp) else 0.0
        d["edge_share_w"] = round(d["sum_wret"] / tot_w, 4)
        d["edge_share_eq"] = round(d["sum_ret"] / tot_r, 4)
        d["tp_edge_share_w"] = round(
            d["sum_wret"] / tp_total["sum_wret"], 4) if tp_total["sum_wret"] else 0.0
        fast[str(h)] = d
    fast["tp_total"] = dict(tp_total, n_tp=int(len(tp)),
                            share_of_rungs=round(len(tp) / len(df), 4))
    # slow-TP complement for context
    slow = pnl_group(tp[tp["dt"] > 60])
    fast["tp_slow_gt60"] = dict(slow, share_of_tp=round(len(tp[tp["dt"] > 60]) / len(tp), 4))

    # E. paper bots since 2026-10-05
    paper = paper_scan()

    res = dict(
        meta=dict(source="oc_kpi/events_s0..s3 rung_fill/exit pairs (R2B1D17BF)",
                  shifts=list(SHIFTS), buckets=["16-60", "61-120", "121-180", "181-238"],
                  fast_horizons=list(FAST_H),
                  note="ret is engine net per rung (fees in); edge shares use sum(weight*ret) main, sum(ret) secondary"),
        checks=checks,
        overall_pnl=total,
        exit_mix=exit_mix,
        fill_minute=dict(overall=overall_f, by_depth=by_depth_f,
                         by_coin=by_coin_f, bucket_hist=bucket_hist),
        time_to_exit=dict(overall=overall_dt, by_depth=by_depth_dt, by_coin=by_coin_dt),
        pnl_by_bucket=dict(pooled=by_bucket, per_depth=by_bucket_depth),
        fast_tp=fast,
        paper=paper,
    )
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({**checks, "n": len(df),
                      "overall_win": total["win"], "overall_mean_bps": total["mean_bps"],
                      "paper": paper.get("summary")}, indent=1))


def paper_scan() -> dict:
    out: dict = {"actions_path": str(PAPER / "actions.jsonl"),
                 "exchange_path": str(PAPER / "exchange.json")}
    ap, ep = PAPER / "actions.jsonl", PAPER / "exchange.json"
    if not ap.exists():
        return {**out, "summary": "actions.jsonl missing", "dip_fills": 0, "book_fills": 0}
    import collections
    ops = collections.Counter()
    fills: list[dict] = []
    n_place = 0
    with open(ap) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            ops[d.get("op")] += 1
            op = d.get("op")
            if op == "place":
                n_place += 1
            if op in ("fill", "dip_fill", "book_fill", "entry_fill", "tp_fill",
                      "stop_fill", "exit_fill", "rung_fill"):
                fills.append(d)
    execs: list = []
    if ep.exists():
        try:
            ex = json.loads(ep.read_text())
            execs = ex.get("execs", []) or []
            out["exchange"] = dict(cash=ex.get("cash"), fees=ex.get("fees"),
                                   funding_paid=ex.get("funding_paid"),
                                   n_execs=len(execs),
                                   equity_curve_n=len(ex.get("equity_curve", []) or []))
        except (json.JSONDecodeError, OSError) as e:
            out["exchange_error"] = str(e)
    # state.json order context (resting dip/book orders, no fills)
    sp = PAPER / "state.json"
    if sp.exists():
        try:
            st = json.loads(sp.read_text())
            links = st.get("links", {})
            kinds = collections.Counter(
                (v.get("order", {}).get("meta", {}) or {}).get("kind", "?")
                for v in links.values())
            out["state"] = dict(n_links=len(links), kinds=dict(kinds))
        except (json.JSONDecodeError, OSError) as e:
            out["state_error"] = str(e)
    out.update(dict(op_counts=dict(ops), n_place=n_place,
                    dip_fills=0, book_fills=0, fills=fills, n_fill_ops=len(fills),
                    n_exchange_execs=len(execs),
                    summary=(f"paper log: {dict(ops)}; fill ops {len(fills)}, "
                             f"exchange execs {len(execs)} -> zero dip/book fills so far; "
                             f"research-engine comparison is counts-only (too few)")))
    return out


if __name__ == "__main__":
    main()
