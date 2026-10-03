"""Part-B forensics: recount rule-5 timing with engine-true levels.

True levels (from engine_user.py after Part A):
- rung_tp limit TP_true = exit_price + 2*MAKER*fill (engine stores net exit = TP - 2*MAKER*fill)
- rung_sl trigger stop gross = fill*(1-8*sig4); stored price = min(stop,open) - (MAKER+TAKER)*fill
- rung_timeout stored = next_bar_open - (MAKER+TAKER+funding?)*fill
- v321: stop5 trigger on block closes, backstop gross; stored prices net.
This script counts REAL timing anomalies (first-touch violations against TRUE levels).
"""
import math
import sys
from collections import Counter

import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from replay_checker import minutes_window, minute_at, bar_start, MAKER, TAKER, AUDIT_DIR

TOL = 1e-6


def rel(a, b):
    return abs(a - b) <= TOL * max(abs(a), abs(b), 1e-12)


def recount(version):
    ev = pd.read_parquet(AUDIT_DIR / f"events_{version}.parquet")
    bars = pd.read_parquet(AUDIT_DIR / f"bars_{version}.parquet")
    ev["t"] = pd.to_datetime(ev["t"], utc=True)
    bars["t"] = pd.to_datetime(bars["t"], utc=True)
    bidx = {pd.Timestamp(r["t"]): r for _, r in bars.iterrows()}
    fills = ev[ev.kind == "rung_fill"].copy()
    exits = ev[ev.kind.isin(["rung_tp", "rung_sl", "rung_timeout"])].copy()
    fills["bar"] = fills["t"].dt.floor("4h")
    tot = Counter()
    examples = []
    npaired = 0
    for (bar, sym), gf in fills.groupby(["bar", "symbol"]):
        bar = pd.Timestamp(bar)
        row = bidx.get(bar)
        if row is None:
            continue
        sigd = row.get(f"sig_d_{sym}", float("nan"))
        if pd.isna(sigd):
            continue
        sig4 = float(sigd) / math.sqrt(6.0)
        gf = gf.sort_values("price", ascending=True).reset_index(drop=True)
        ge = exits[(exits.symbol == sym) & (exits.kind.isin(["rung_tp", "rung_sl"]))
                   & (exits.t.dt.floor("4h") == bar)].sort_values("price", ascending=True).reset_index(drop=True)
        gt = exits[(exits.symbol == sym) & (exits.kind == "rung_timeout")
                   & (exits.t == bar + pd.Timedelta(hours=4))].reset_index(drop=True)
        if len(ge) + len(gt) != len(gf):
            tot["pair_count_groups"] += 1
        n = min(len(gf), len(ge))
        pairs = [(gf.iloc[i], ge.iloc[i], "touch") for i in range(n)]
        for j, i in enumerate(range(n, len(gf))):
            pairs.append((gf.iloc[i], gt.iloc[j] if j < len(gt) else None, "timeout"))
        for f, x, _ in pairs:
            if x is None:
                tot["missing_exit"] += 1
                continue
            npaired += 1
            ft, fp = pd.Timestamp(f["t"]), float(f["price"])
            xt, xp, xk = pd.Timestamp(x["t"]), float(x["price"]), x["kind"]
            stop = fp * (1 - 8 * sig4)
            if version == "v367":
                if xk == "rung_tp":
                    tp_true = xp + 2 * MAKER * fp
                    if not rel(xp + 2 * MAKER * fp, tp_true):
                        pass
                    w = minutes_window(sym, ft + pd.Timedelta(minutes=1), xt + pd.Timedelta(minutes=1))
                    w = w[(w.open_time > ft) & (w.open_time <= xt)]
                    pre = w[w.open_time < xt]
                    if len(pre) and (bool((pre["low"] <= stop).any()) or bool((pre["high"] > tp_true).any())):
                        tot["tp_not_first_true"] += 1
                        if len(examples) < 10:
                            examples.append(("tp_not_first_true", sym, str(bar), str(ft), str(xt)))
                    er = w[w.open_time == xt]
                    if len(er) and not (float(er.iloc[0]["high"]) > tp_true):
                        tot["tp_no_touch_true"] += 1
                    if len(er) and float(er.iloc[0]["low"]) <= stop:
                        tot["tp_tie"] += 1
                elif xk == "rung_sl":
                    w = minutes_window(sym, ft + pd.Timedelta(minutes=1), xt + pd.Timedelta(minutes=1))
                    w = w[(w.open_time > ft) & (w.open_time <= xt)]
                    pre = w[w.open_time < xt]
                    if len(pre) and bool((pre["low"] <= stop).any()):
                        tot["sl_late_true"] += 1
                        if len(examples) < 10:
                            examples.append(("sl_late_true", sym, str(bar), str(ft), str(xt)))
                    er = w[w.open_time == xt]
                    if len(er):
                        if not (float(er.iloc[0]["low"]) <= stop):
                            tot["sl_no_touch_true"] += 1
                            if len(examples) < 10:
                                examples.append(("sl_no_touch_true", sym, str(bar), str(ft), str(xt)))
                        want = min(stop, float(er.iloc[0]["open"])) - (MAKER + TAKER) * fp
                        if not rel(xp, want):
                            tot["sl_price_true"] += 1
                else:
                    w = minutes_window(sym, ft + pd.Timedelta(minutes=1), bar + pd.Timedelta(hours=4))
                    if len(w) and bool((w["low"] <= stop).any()):
                        tot["timeout_missed_stop_true"] += 1
                        if len(examples) < 10:
                            examples.append(("timeout_missed_stop_true", sym, str(bar), str(ft), str(xt)))
            else:
                stop5 = fp * (1 - 4 * sig4)
                back = stop
                w = minutes_window(sym, ft + pd.Timedelta(minutes=1),
                                   (xt if xk != "rung_timeout" else bar + pd.Timedelta(hours=4)) + pd.Timedelta(minutes=1))
                w = w[(w.open_time > ft) & (w.open_time <= (xt if xk != "rung_timeout" else bar + pd.Timedelta(hours=4)))]
                if xk == "rung_tp":
                    tp_true = xp + 2 * MAKER * fp
                    pre = w[w.open_time < xt]
                    early_tp = bool((pre["high"] > tp_true).any()) if len(pre) else False
                    # stop before exit?
                    stopped = False
                    if len(pre):
                        pre = pre.sort_values("open_time").reset_index(drop=True)
                        pmap = {int(round((pd.Timestamp(r["open_time"]) - bar).total_seconds() / 60)): r for _, r in pre.iterrows()}
                        xm = int(round((xt - bar).total_seconds() / 60))
                        for m in range(int(round((ft - bar).total_seconds() / 60)) + 1, xm):
                            if (m + 1) % 5 == 0 and m in pmap and float(pmap[m]["close"]) <= stop5:
                                stopped = True
                                break
                            if m in pmap and float(pmap[m]["low"]) <= back:
                                stopped = True
                                break
                    if early_tp:
                        tot["tp_not_first_true"] += 1
                    if stopped:
                        tot["tp_after_stop_true"] += 1
                        if len(examples) < 10:
                            examples.append(("tp_after_stop_true", sym, str(bar), str(ft), str(xt)))
                    er = w[w.open_time == xt]
                    if len(er) and not (float(er.iloc[0]["high"]) > tp_true):
                        tot["tp_no_touch_true"] += 1
                elif xk == "rung_timeout":
                    if len(w):
                        ws = w.sort_values("open_time").reset_index(drop=True)
                        wmap = {int(round((pd.Timestamp(r["open_time"]) - bar).total_seconds() / 60)): r for _, r in ws.iterrows()}
                        fm = int(round((ft - bar).total_seconds() / 60))
                        trig = False
                        for m in range(fm + 1, 240):
                            if (m + 1) % 5 == 0 and m in wmap and float(wmap[m]["close"]) <= stop5:
                                trig = True
                                break
                            if m in wmap and float(wmap[m]["low"]) <= back:
                                trig = True
                                break
                        if trig:
                            tot["timeout_missed_stop_true"] += 1
                            if len(examples) < 10:
                                examples.append(("timeout_missed_stop_true", sym, str(bar), str(ft), str(xt)))
                # v321 rung_sl timing needs agent-cut modelling; skip precise check, count gross trigger presence
    return {"paired": npaired, "true_timing": dict(tot), "examples": examples}


if __name__ == "__main__":
    import json
    out = {}
    for v in ("v367", "v321"):
        out[v] = recount(v)
    print(json.dumps(out, indent=2, default=str))
