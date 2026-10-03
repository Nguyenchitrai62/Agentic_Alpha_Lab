"""Part-B matcher: per (bar,symbol) group, test whether ANY bijection
fills->exits is fully consistent with engine-true levels (net-aware prices).

Consistency (v367 touch mode; v321 close5+backstop):
- tp exit X <-> fill F: TPc = X.price + 2*MAKER*F.price; X.t is the FIRST minute
  after F.t with high > TPc; no minute in (F.t, X.t) has low <= stop(F);
  X.t minute satisfies high > TPc.
- sl exit X <-> fill F: S = F.price*(1-8*sig4); X.t first minute after F.t with
  low <= S (v367) [v321: close/backstop logic vs next-open price]; stored price
  == min(S, open(X.t)) - (MAKER+TAKER)*F.price.
- timeout X <-> fill F: no stop touch in (F.t, bar_end]; no tp touch of the
  rung's true TP... (TP multiple unknown) -> check only stop side + price
  == next_open - (MAKER+TAKER+fund?)*F.price.
For tp-timeout ambiguity (leftover fills), require stop-side cleanliness.
Reports groups with no perfect matching.
"""
import itertools
import math
from collections import Counter

import pandas as pd

from replay_checker import minutes_window, minute_at, MAKER, TAKER, AUDIT_DIR

TOL = 1e-6


def rel(a, b):
    return abs(a - b) <= TOL * max(abs(a), abs(b), 1e-12)


def load(version):
    ev = pd.read_parquet(AUDIT_DIR / f"events_{version}.parquet")
    bars = pd.read_parquet(AUDIT_DIR / f"bars_{version}.parquet")
    ev["t"] = pd.to_datetime(ev["t"], utc=True)
    bars["t"] = pd.to_datetime(bars["t"], utc=True)
    return ev, {pd.Timestamp(r["t"]): r for _, r in bars.iterrows()}


def consistent_tp_v367(sym, F, X, sig4):
    ft, fp = pd.Timestamp(F["t"]), float(F["price"])
    xt, xp = pd.Timestamp(X["t"]), float(X["price"])
    if xt <= ft:
        return False
    stop = fp * (1 - 8 * sig4)
    tpc = xp + 2 * MAKER * fp
    w = minutes_window(sym, ft + pd.Timedelta(minutes=1), xt + pd.Timedelta(minutes=1))
    w = w[(w.open_time > ft) & (w.open_time <= xt)]
    if len(w) == 0:
        return False
    er = w[w.open_time == xt]
    if len(er) == 0 or not (float(er.iloc[0]["high"]) > tpc):
        return False
    if float(er.iloc[0]["low"]) <= stop:
        return False  # tie must be stop
    pre = w[w.open_time < xt]
    if len(pre) and (bool((pre["low"] <= stop).any()) or bool((pre["high"] > tpc).any())):
        return False
    return True


def consistent_sl_v367(sym, F, X, sig4):
    ft, fp = pd.Timestamp(F["t"]), float(F["price"])
    xt, xp = pd.Timestamp(X["t"]), float(X["price"])
    if xt <= ft:
        return False
    stop = fp * (1 - 8 * sig4)
    w = minutes_window(sym, ft + pd.Timedelta(minutes=1), xt + pd.Timedelta(minutes=1))
    w = w[(w.open_time > ft) & (w.open_time <= xt)]
    if len(w) == 0:
        return False
    er = w[w.open_time == xt]
    if len(er) == 0 or not (float(er.iloc[0]["low"]) <= stop):
        return False
    if not rel(xp, min(stop, float(er.iloc[0]["open"])) - (MAKER + TAKER) * fp):
        return False
    pre = w[w.open_time < xt]
    if len(pre) and bool((pre["low"] <= stop).any()):
        return False
    return True


def consistent_to(sym, F, X):
    ft, fp = pd.Timestamp(F["t"]), float(F["price"])
    xt, xp = pd.Timestamp(X["t"]), float(X["price"])
    nb = minute_at(sym, xt)
    if nb is None:
        return False
    op = float(nb["open"])
    fund = 0.0001 if xt.hour in (0, 8, 16) else 0.0
    return rel(xp, op - (MAKER + TAKER + fund) * fp)


def clean_stop_side_v367(sym, F, bar, sig4):
    ft, fp = pd.Timestamp(F["t"]), float(F["price"])
    stop = fp * (1 - 8 * sig4)
    w = minutes_window(sym, ft + pd.Timedelta(minutes=1), bar + pd.Timedelta(hours=4))
    return not (len(w) and bool((w["low"] <= stop).any()))


def winmap(sym, a, b):
    w = minutes_window(sym, a, b).sort_values("open_time").reset_index(drop=True)
    return w


def consistent_tp_v321(sym, F, X, sig4, bar):
    ft, fp = pd.Timestamp(F["t"]), float(F["price"])
    xt, xp = pd.Timestamp(X["t"]), float(X["price"])
    if xt <= ft:
        return False
    stop5 = fp * (1 - 4 * sig4)
    back = fp * (1 - 8 * sig4)
    tpc = xp + 2 * MAKER * fp
    w = winmap(sym, ft + pd.Timedelta(minutes=1), xt + pd.Timedelta(minutes=1))
    w = w[(w.open_time > ft) & (w.open_time <= xt)]
    if len(w) == 0:
        return False
    er = w[w.open_time == xt]
    if len(er) == 0 or not (float(er.iloc[0]["high"]) > tpc):
        return False
    pre = w[w.open_time < xt]
    if len(pre):
        if bool((pre["high"] > tpc).any()):
            return False
        pmap = {int(round((pd.Timestamp(r["open_time"]) - bar).total_seconds() / 60)): r
                for _, r in pre.iterrows()}
        xm = int(round((xt - bar).total_seconds() / 60))
        fm = int(round((ft - bar).total_seconds() / 60))
        for m in range(fm + 1, xm):
            if (m + 1) % 5 == 0 and m in pmap and float(pmap[m]["close"]) <= stop5:
                return False
            if m in pmap and float(pmap[m]["low"]) <= back:
                return False
    return True


def consistent_sl_v321(sym, F, X, sig4, bar):
    """Close-trigger or backstop sl: recompute expected exit minute+price, must match."""
    ft, fp = pd.Timestamp(F["t"]), float(F["price"])
    xt, xp = pd.Timestamp(X["t"]), float(X["price"])
    if xt <= ft:
        return False
    stop5 = fp * (1 - 4 * sig4)
    back = fp * (1 - 8 * sig4)
    w = winmap(sym, ft + pd.Timedelta(minutes=1), xt + pd.Timedelta(minutes=1))
    w = w[(w.open_time > ft) & (w.open_time <= xt)]
    if len(w) == 0:
        return False
    wmap = {int(round((pd.Timestamp(r["open_time"]) - bar).total_seconds() / 60)): r
            for _, r in w.iterrows()}
    fm = int(round((ft - bar).total_seconds() / 60))
    xm = int(round((xt - bar).total_seconds() / 60))
    # backstop candidate
    b_m = next((m for m in range(fm + 1, 240) if m in wmap and float(wmap[m]["low"]) <= back), None)
    # close-trigger candidate -> exit next minute open
    s_m = next((m + 1 for m in range(fm + 1, 240)
                if (m + 1) % 5 == 0 and m in wmap and float(wmap[m]["close"]) <= stop5), None)
    if b_m is not None and s_m is not None:
        # engine compares indices: backstop wins iff b_m <= trig minute (s_m - 1)
        exp_m = b_m if b_m < s_m else s_m
    else:
        exp_m = b_m if b_m is not None else s_m
    if exp_m is None or exp_m != xm:
        return False
    if exp_m == b_m and (s_m is None or b_m < s_m):
        want = min(back, float(wmap[b_m]["open"])) - (MAKER + TAKER) * fp
    else:
        o = float(wmap[s_m]["open"]) if s_m in wmap else None
        if o is None:
            nb = minute_at(sym, bar + pd.Timedelta(hours=4))
            o = float(nb["open"]) if nb is not None else None
        if o is None:
            return False
        want = o - (MAKER + TAKER) * fp
    return rel(xp, want)


def clean_stop_side_v321(sym, F, bar, sig4):
    ft = pd.Timestamp(F["t"])
    fp = float(F["price"])
    stop5 = fp * (1 - 4 * sig4)
    back = fp * (1 - 8 * sig4)
    w = winmap(sym, ft + pd.Timedelta(minutes=1), bar + pd.Timedelta(hours=4))
    if not len(w):
        return True
    wmap = {int(round((pd.Timestamp(r["open_time"]) - bar).total_seconds() / 60)): r
            for _, r in w.iterrows()}
    fm = int(round((ft - bar).total_seconds() / 60))
    for m in range(fm + 1, 240):
        if (m + 1) % 5 == 0 and m in wmap and float(wmap[m]["close"]) <= stop5:
            return False
        if m in wmap and float(wmap[m]["low"]) <= back:
            return False
    return True


def run_match(version):
    ev, bidx = load(version)
    fills = ev[ev.kind == "rung_fill"].copy()
    exits = ev[ev.kind.isin(["rung_tp", "rung_sl", "rung_timeout"])].copy()
    fills["bar"] = fills["t"].dt.floor("4h")
    stat = Counter()
    bad_groups = []
    for (bar, sym), gf in fills.groupby(["bar", "symbol"]):
        bar = pd.Timestamp(bar)
        row = bidx.get(bar)
        if row is None:
            continue
        sigd = row.get(f"sig_d_{sym}", float("nan"))
        if pd.isna(sigd):
            continue
        sig4 = float(sigd) / math.sqrt(6.0)
        gf = gf.sort_values("t").reset_index(drop=True)
        # touch exits timestamped within (bar, bar+4h]: a close-triggered stop can
        # exit at minute 240 = next bar open (engine lines 750-760), same t as timeouts
        ge = exits[(exits.symbol == sym) & (exits.kind.isin(["rung_tp", "rung_sl"]))
                   & (exits.t > bar) & (exits.t <= bar + pd.Timedelta(hours=4))].reset_index(drop=True)
        gt = exits[(exits.symbol == sym) & (exits.kind == "rung_timeout")
                   & (exits.t == bar + pd.Timedelta(hours=4))].reset_index(drop=True)
        stat["groups"] += 1
        stat["fills"] += len(gf)
        touch = [ge.iloc[i] for i in range(len(ge))]
        F = [gf.iloc[i] for i in range(len(gf))]
        if version == "v367":
            ctp, csl, cto, cstop = (consistent_tp_v367, consistent_sl_v367,
                                    consistent_to, clean_stop_side_v367)
            clo = None
        else:
            ctp, csl, cto, cstop, clo = (consistent_tp_v321, consistent_sl_v321,
                                         consistent_to, clean_stop_side_v321, True)
        ok = False
        if len(touch) <= len(F) <= 5 and math.factorial(len(F)) <= 120:
            for combo in itertools.permutations(range(len(F)), len(touch)):
                good = True
                used = set(combo)
                for fi, X in zip(combo, touch):
                    if X["kind"] == "rung_tp":
                        good = (ctp(sym, F[fi], X, sig4) if clo is None
                                else ctp(sym, F[fi], X, sig4, bar))
                    else:
                        good = (csl(sym, F[fi], X, sig4) if clo is None
                                else csl(sym, F[fi], X, sig4, bar))
                    if not good:
                        break
                if not good:
                    continue
                # leftovers -> timeouts: try all assignments (prices differ per fill: px=open-c*fill)
                rest = [F[i] for i in range(len(F)) if i not in used]
                if len(rest) != len(gt):
                    continue
                Tout = [gt.iloc[i] for i in range(len(gt))]
                for tperm in itertools.permutations(range(len(Tout))):
                    good2 = True
                    for F0, X in zip(rest, [Tout[j] for j in tperm]):
                        if not cto(sym, F0, X):
                            good2 = False
                            break
                        if not cstop(sym, F0, bar, sig4):
                            good2 = False
                            break
                    if good2:
                        break
                if not good2:
                    continue
                if good:
                    ok = True
                    break
        else:
            ok = None
        if ok:
            stat["clean"] += 1
        elif ok is None:
            stat["skipped_large"] += 1
        else:
            stat["unclean"] += 1
            if len(bad_groups) < 15:
                bad_groups.append((str(bar), sym, len(F), len(touch), len(gt)))
    return stat, bad_groups


if __name__ == "__main__":
    import json
    import sys
    for v in (sys.argv[1:] or ("v367",)):
        stat, bad = run_match(v)
        print(v, json.dumps(dict(stat), indent=2))
        print("bad groups:", bad)
