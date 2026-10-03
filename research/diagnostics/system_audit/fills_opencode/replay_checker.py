"""Independent trade-level replay checker for SYSTEM AUDIT 1.

Implements the exact rules in docs/opencode/OPENCODE_SYSAUDIT_FILLS.md
without importing or reading the engine. Pure helpers are importable for tests.
"""
import math
import random
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[4]
AUDIT_DIR = REPO / "artifacts" / "research" / "system_audit"
OUT_DIR = REPO / "research" / "diagnostics" / "system_audit" / "fills_opencode"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
MAKER = 0.0002
TAKER = 0.00055
TOL = 1e-6
K_V367 = (3.0, 4.0)
K_V321 = (2.5, 3.0, 3.5, 4.0, 5.0)


def rel_close(a, b, tol=TOL):
    try:
        a = float(a)
        b = float(b)
    except (TypeError, ValueError):
        return False
    if math.isnan(a) or math.isnan(b):
        return False
    denom = max(abs(a), abs(b), 1e-12)
    return abs(a - b) <= tol * denom


# ---- pure helpers (used by tests) ----
def is_trade_through(side, low, high, price):
    if side == "buy":
        return low < price
    return high > price


def first_touch_index(lows, highs, side, level, strict=True):
    """Return first index where touch holds (buy: low<lvl; sell: high>lvl)."""
    idx = None
    for i, (lo, hi) in enumerate(zip(lows, highs)):
        if side == "buy":
            hit = lo < level if strict else lo <= level
        else:
            hit = hi > level if strict else hi >= level
        if hit:
            return i
    return None


def book_stop_price(direction, sl, minute_open):
    if direction == "long":
        return min(sl, minute_open)
    return max(sl, minute_open)


def book_exit_hits(direction, low, high, sl, tp):
    if direction == "long":
        return (low <= sl, high > tp)
    return (high >= sl, low < tp)


def rung_price(bar_open, sig_d, k):
    return bar_open * (1.0 - k * sig_d / math.sqrt(6.0))


def rung_stop_v367(fill_price, sig_d):
    return fill_price * (1.0 - 8.0 * sig_d / math.sqrt(6.0))


def rung_stop5_v321(fill_price, sig_d):
    return fill_price * (1.0 - 4.0 * sig_d / math.sqrt(6.0))


def rung_backstop_v321(fill_price, sig_d):
    return fill_price * (1.0 - 8.0 * sig_d / math.sqrt(6.0))


def expected_rung_ret(fill_price, exit_price, exit_kind, exit_t):
    fee2 = TAKER if exit_kind in ("rung_sl", "rung_timeout") else MAKER
    funding = 0.0
    if exit_kind == "rung_timeout" and pd.Timestamp(exit_t).hour in (0, 8, 16):
        funding = 0.0001
    return exit_price / fill_price - 1.0 - MAKER - fee2 - funding


def bar_start(ts):
    return pd.Timestamp(ts).floor("4h")


# ---- 1m data loading ----
_kline_cache = {}


def _files_for(symbol):
    if symbol == "BTCUSDT":
        d = REPO / "data" / "raw" / "btc_intraday_20260924"
        return sorted(d.glob("klines_1m_20*.parquet"))
    d = REPO / "data" / "raw" / "majors_intraday_20260924"
    return sorted(d.glob(f"{symbol}_1m_20*.parquet"))


def _load_year(symbol, year):
    key = (symbol, year)
    if key in _kline_cache:
        return _kline_cache[key]
    if symbol == "BTCUSDT":
        p = REPO / "data" / "raw" / "btc_intraday_20260924" / f"klines_1m_{year}.parquet"
    else:
        p = REPO / "data" / "raw" / "majors_intraday_20260924" / f"{symbol}_1m_{year}.parquet"
    df = pd.read_parquet(p, columns=["open_time", "open", "high", "low", "close"])
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df.drop_duplicates(subset="open_time").sort_values("open_time").reset_index(drop=True)
    _kline_cache[key] = df
    return df


def _as_utc(ts):
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def minutes_window(symbol, start_incl, end_excl):
    """1m klines with open_time in [start_incl, end_excl)."""
    start_incl = _as_utc(start_incl)
    end_excl = _as_utc(end_excl)
    years = range(start_incl.year, end_excl.year + 1)
    parts = []
    for y in years:
        try:
            df = _load_year(symbol, y)
        except FileNotFoundError:
            continue
        m = df[(df["open_time"] >= start_incl) & (df["open_time"] < end_excl)]
        parts.append(m)
    if not parts:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close"])
    out = pd.concat(parts, ignore_index=True)
    out = out.drop_duplicates(subset="open_time").sort_values("open_time").reset_index(drop=True)
    return out


def minute_at(symbol, ts):
    ts = _as_utc(ts)
    w = minutes_window(symbol, ts, ts + pd.Timedelta(minutes=1))
    if len(w) == 0:
        return None
    return w.iloc[0]


class Checker:
    def __init__(self, version):
        assert version in ("v367", "v321")
        self.version = version
        self.events = pd.read_parquet(AUDIT_DIR / f"events_{version}.parquet")
        self.bars = pd.read_parquet(AUDIT_DIR / f"bars_{version}.parquet")
        self.events["t"] = pd.to_datetime(self.events["t"], utc=True)
        self.bars["t"] = pd.to_datetime(self.bars["t"], utc=True)
        self.bar_by_t = {pd.Timestamp(r["t"]): r for _, r in self.bars.iterrows()}
        self.kset = set(K_V367 if version == "v367" else K_V321)
        self.mismatches = []  # (rule, class, detail dict)
        self.counts = {}

    def add(self, rule, cls, ex):
        self.mismatches.append({"rule": rule, "class": cls, **ex})

    # ---- rule 1 ----
    def check_rule1(self, n=500, seed=0):
        rng = random.Random(seed)
        idx = rng.sample(range(len(self.bars)), min(n, len(self.bars)))
        syms = [SYMBOLS[rng.randrange(len(SYMBOLS))] for _ in idx]
        checked = 0
        bad = 0
        for i, s in zip(idx, syms):
            row = self.bars.iloc[i]
            bt = pd.Timestamp(row["t"])
            want = float(row[f"open_{s}"])
            m = minute_at(s, bt)
            checked += 1
            if m is None or not rel_close(want, float(m["open"])):
                bad += 1
                if len([x for x in self.mismatches if x["rule"] == 1]) < 10:
                    got = None if m is None else float(m["open"])
                    self.add(1, "bar_open_mismatch", {
                        "version": self.version, "symbol": s,
                        "bar": str(bt), "want": want, "got": got})
        self.counts["rule1"] = {"checked": checked, "mismatches": bad}
        return checked, bad

    # ---- rule 2 ----
    def check_rule2(self):
        ev = self.events
        entry_orders = ev[(ev.kind == "order_issue") & (ev["scale"].isna())].copy().sort_values("t")
        fills = ev[ev.kind == "book_fill"].copy().sort_values("t")
        terminals = ev[(ev.kind.isin(["order_expire", "order_cancel"])) & (ev["scale"].isna())].copy().sort_values("t")
        # index terminals by (symbol, side)
        checked_price = 0
        early = 0
        cond_false = 0
        late = 0
        missed = 0
        no_order = 0
        n_fill_checked = 0
        n_order_checked = 0
        # match fills -> orders
        fill_order = {}
        for fi, f in fills.iterrows():
            sym, side, fp, ft = f["symbol"], f["side"], float(f["price"]), pd.Timestamp(f["t"])
            ago = float(f["issued_bars_ago"])
            fb = bar_start(ft)
            ob = fb - pd.Timedelta(hours=4 * int(round(ago)))
            cand = entry_orders[(entry_orders.symbol == sym) & (entry_orders.side == side)
                                & (entry_orders.t == ob)
                                & ((entry_orders.price - fp).abs() <= TOL * entry_orders.price.abs().clip(lower=1e-12))]
            if len(cand) == 0:
                no_order += 1
                if len([x for x in self.mismatches if x["rule"] == 2 and x["class"] == "fill_without_order"]) < 10:
                    self.add(2, "fill_without_order", {"version": self.version, "symbol": sym,
                                                       "fill_t": str(ft), "price": fp, "order_bar": str(ob)})
                continue
            o = cand.iloc[0]
            fill_order[fi] = o
            n_fill_checked += 1
            # price equality already enforced; count
            checked_price += 1
            m = (ft - fb).total_seconds() / 60.0
            if ago == 0 and m < 5 - 1e-9:
                early += 1
                if len([x for x in self.mismatches if x["rule"] == 2 and x["class"] == "fill_too_early"]) < 10:
                    self.add(2, "fill_too_early", {"version": self.version, "symbol": sym,
                                                   "fill_t": str(ft), "minute": m, "price": fp})
        # per-order scan
        # build terminal lookup: for each order, earliest terminal same symbol/side/price after order t
        for oi, o in entry_orders.iterrows():
            sym, side, op, ot = o["symbol"], o["side"], float(o["price"]), pd.Timestamp(o["t"])
            if oi in [v.name if hasattr(v, "name") else None for v in fill_order.values()]:
                pass
            matched_fill = None
            for fi, mo in fill_order.items():
                if mo["symbol"] == sym and pd.Timestamp(mo["t"]) == ot and mo["side"] == side and rel_close(float(mo["price"]), op):
                    matched_fill = fills.loc[fi]
                    break
            if matched_fill is not None:
                end_t = pd.Timestamp(matched_fill["t"])
                is_filled = True
            else:
                cand = terminals[(terminals.symbol == sym) & (terminals.side == side)
                                 & (terminals.t > ot)
                                 & ((terminals.price - op).abs() <= TOL * abs(op))]
                if len(cand) == 0:
                    continue
                term = cand.iloc[0]
                end_t = pd.Timestamp(term["t"])
                is_filled = False
            n_order_checked += 1
            start_t = ot + pd.Timedelta(minutes=5)
            if is_filled:
                w = minutes_window(sym, start_t, end_t + pd.Timedelta(minutes=1))
                w = w[w.open_time <= end_t]
                if len(w) == 0:
                    continue
                if side == "buy":
                    hits = (w["low"] < op).to_numpy()
                    exit_row = w[w.open_time == end_t]
                else:
                    hits = (w["high"] > op).to_numpy()
                    exit_row = w[w.open_time == end_t]
                if len(exit_row) == 0:
                    cond_false += 1
                    if len([x for x in self.mismatches if x["rule"] == 2 and x["class"] == "fill_minute_missing"]) < 10:
                        self.add(2, "fill_minute_missing", {"version": self.version, "symbol": sym,
                                                            "order_t": str(ot), "fill_t": str(end_t), "price": op})
                    continue
                er = exit_row.iloc[0]
                ok = (er["low"] < op) if side == "buy" else (er["high"] > op)
                if not ok:
                    cond_false += 1
                    if len([x for x in self.mismatches if x["rule"] == 2 and x["class"] == "fill_without_tradethrough"]) < 10:
                        self.add(2, "fill_without_tradethrough", {"version": self.version, "symbol": sym,
                                                                  "order_t": str(ot), "fill_t": str(end_t), "price": op,
                                                                  "low": float(er["low"]), "high": float(er["high"])})
                first_idx = None
                for i, h in enumerate(hits):
                    if h:
                        first_idx = i
                        break
                if first_idx is not None:
                    first_t = pd.Timestamp(w.iloc[first_idx]["open_time"])
                    if first_t < end_t:
                        late += 1
                        if len([x for x in self.mismatches if x["rule"] == 2 and x["class"] == "should_have_filled_earlier"]) < 10:
                            self.add(2, "should_have_filled_earlier", {"version": self.version, "symbol": sym,
                                                                       "order_t": str(ot), "fill_t": str(end_t),
                                                                       "first_t": str(first_t), "price": op})
            else:
                w = minutes_window(sym, start_t, end_t)
                if len(w) == 0:
                    continue
                if side == "buy":
                    hit = bool((w["low"] < op).any())
                else:
                    hit = bool((w["high"] > op).any())
                if hit:
                    missed += 1
                    if len([x for x in self.mismatches if x["rule"] == 2 and x["class"] == "missed_fill"]) < 10:
                        fw = w[(w["low"] < op)] if side == "buy" else w[(w["high"] > op)]
                        self.add(2, "missed_fill", {"version": self.version, "symbol": sym,
                                                    "order_t": str(ot), "expire_t": str(end_t), "price": op,
                                                    "first_t": str(pd.Timestamp(fw.iloc[0]["open_time"]))})
        total_checked = n_fill_checked + n_order_checked
        total_bad = early + cond_false + late + missed + no_order
        self.counts["rule2"] = {"checked_fills": n_fill_checked, "checked_orders": n_order_checked,
                                "checked": total_checked, "too_early": early,
                                "fill_condition_false": cond_false, "late": late,
                                "missed": missed, "fill_without_order": no_order,
                                "mismatches": total_bad}
        return self.counts["rule2"]

    # ---- rule 3 ----
    def check_rule3(self):
        ev = self.events.sort_values("t").reset_index(drop=True)
        state = {}  # symbol -> dict(dir, sl, tp, set_t)
        checked = 0
        bad_price = 0
        bad_late = 0
        bad_tie = 0
        no_pos = 0
        for _, r in ev.iterrows():
            k = r["kind"]
            sym = r["symbol"]
            st = state.get(sym)
            if k in ("book_fill", "book_add"):
                d = "long" if r["side"] == "buy" else "short"
                sl = float(r["sl"]) if pd.notna(r["sl"]) else (st["sl"] if st else float("nan"))
                tp = float(r["tp"]) if pd.notna(r["tp"]) else (st["tp"] if st else float("nan"))
                state[sym] = {"dir": d, "sl": sl, "tp": tp, "set_t": pd.Timestamp(r["t"])}
            elif k == "sl_move":
                if st is None:
                    continue
                state[sym] = {"dir": st["dir"], "sl": float(r["price"]), "tp": st["tp"],
                              "set_t": pd.Timestamp(r["t"])}
            elif k in ("book_stop", "book_tp"):
                checked += 1
                xt = pd.Timestamp(r["t"])
                xp = float(r["price"])
                ex_side = r["side"]
                direction = "long" if ex_side == "sell" else "short"
                if st is None or st["dir"] != direction or pd.isna(st["sl"]) or pd.isna(st["tp"]):
                    no_pos += 1
                    if len([x for x in self.mismatches if x["rule"] == 3 and x["class"] == "exit_without_position"]) < 10:
                        self.add(3, "exit_without_position", {"version": self.version, "symbol": sym,
                                                             "exit_t": str(xt), "kind": k, "price": xp})
                    if k in ("book_stop", "book_tp"):
                        state.pop(sym, None)
                    continue
                sl, tp, set_t = st["sl"], st["tp"], st["set_t"]
                w = minutes_window(sym, set_t + pd.Timedelta(minutes=1), xt + pd.Timedelta(minutes=1))
                w = w[(w.open_time > set_t) & (w.open_time <= xt)]
                if len(w) == 0:
                    state.pop(sym, None)
                    continue
                if direction == "long":
                    stop_hit = (w["low"] <= sl).to_numpy()
                    tp_hit = (w["high"] > tp).to_numpy()
                else:
                    stop_hit = (w["high"] >= sl).to_numpy()
                    tp_hit = (w["low"] < tp).to_numpy()
                times = pd.to_datetime(w["open_time"])
                # exit row
                er = w[w.open_time == xt]
                if len(er) == 0:
                    bad_price += 1
                    if len([x for x in self.mismatches if x["rule"] == 3 and x["class"] == "exit_minute_missing"]) < 10:
                        self.add(3, "exit_minute_missing", {"version": self.version, "symbol": sym,
                                                            "exit_t": str(xt), "kind": k, "price": xp})
                    state.pop(sym, None)
                    continue
                er = er.iloc[0]
                mop = float(er["open"])
                if k == "book_stop":
                    want = min(sl, mop) if direction == "long" else max(sl, mop)
                    if not rel_close(xp, want):
                        bad_price += 1
                        if len([x for x in self.mismatches if x["rule"] == 3 and x["class"] == "stop_price"]) < 10:
                            self.add(3, "stop_price", {"version": self.version, "symbol": sym,
                                                      "exit_t": str(xt), "got": xp, "want": want,
                                                      "sl": sl, "open": mop})
                    # exit minute must satisfy stop
                    ei = int(w[w.open_time == xt].index[0] == w.index).sum() if False else None
                    pos = w.index[w.open_time == xt][0]
                    loc = w.index.get_loc(pos)
                    if not stop_hit[loc]:
                        bad_price += 1
                        if len([x for x in self.mismatches if x["rule"] == 3 and x["class"] == "stop_no_touch"]) < 10:
                            self.add(3, "stop_no_touch", {"version": self.version, "symbol": sym,
                                                         "exit_t": str(xt), "sl": sl,
                                                         "low": float(er["low"]), "high": float(er["high"])})
                    # no earlier touch of either
                    if stop_hit[:loc].any() or tp_hit[:loc].any():
                        bad_late += 1
                        if len([x for x in self.mismatches if x["rule"] == 3 and x["class"] == "late_exit"]) < 10:
                            self.add(3, "late_exit", {"version": self.version, "symbol": sym,
                                                     "exit_t": str(xt), "kind": k, "sl": sl, "tp": tp,
                                                     "set_t": str(set_t)})
                else:  # book_tp
                    if not rel_close(xp, tp):
                        bad_price += 1
                        if len([x for x in self.mismatches if x["rule"] == 3 and x["class"] == "tp_price"]) < 10:
                            self.add(3, "tp_price", {"version": self.version, "symbol": sym,
                                                    "exit_t": str(xt), "got": xp, "want": tp})
                    pos = w.index[w.open_time == xt][0]
                    loc = w.index.get_loc(pos)
                    if not tp_hit[loc]:
                        bad_price += 1
                        if len([x for x in self.mismatches if x["rule"] == 3 and x["class"] == "tp_no_touch"]) < 10:
                            self.add(3, "tp_no_touch", {"version": self.version, "symbol": sym,
                                                       "exit_t": str(xt), "tp": tp,
                                                       "low": float(er["low"]), "high": float(er["high"])})
                    if stop_hit[loc] and tp_hit[loc]:
                        bad_tie += 1
                        if len([x for x in self.mismatches if x["rule"] == 3 and x["class"] == "tie_not_stop"]) < 10:
                            self.add(3, "tie_not_stop", {"version": self.version, "symbol": sym,
                                                        "exit_t": str(xt), "sl": sl, "tp": tp})
                    if stop_hit[:loc].any() or tp_hit[:loc].any():
                        bad_late += 1
                        if len([x for x in self.mismatches if x["rule"] == 3 and x["class"] == "late_exit"]) < 10:
                            self.add(3, "late_exit", {"version": self.version, "symbol": sym,
                                                     "exit_t": str(xt), "kind": k, "sl": sl, "tp": tp,
                                                     "set_t": str(set_t)})
                state.pop(sym, None)
            elif k == "book_close":
                state.pop(sym, None)
            elif k == "book_reduce":
                pass
        self.counts["rule3"] = {"checked": checked, "price_mismatch": bad_price,
                                "late": bad_late, "tie": bad_tie,
                                "no_position": no_pos,
                                "mismatches": bad_price + bad_late + bad_tie + no_pos}
        return self.counts["rule3"]

    # ---- rule 4 ----
    def check_rule4(self):
        ev = self.events
        fills = ev[ev.kind == "rung_fill"].copy()
        checked = 0
        bad_price = 0
        bad_min = 0
        bad_first = 0
        bad_k = 0
        for _, f in fills.iterrows():
            sym = f["symbol"]
            ft = pd.Timestamp(f["t"])
            fp = float(f["price"])
            k = float(f["rung"])
            fb = bar_start(ft)
            m = int(round((ft - fb).total_seconds() / 60.0))
            brow = self.bar_by_t.get(fb)
            if brow is None:
                continue
            sigd = brow.get(f"sig_d_{sym}", float("nan"))
            bo = brow.get(f"open_{sym}", float("nan"))
            if pd.isna(sigd) or pd.isna(bo):
                continue
            checked += 1
            if k not in self.kset:
                bad_k += 1
                if len([x for x in self.mismatches if x["rule"] == 4 and x["class"] == "bad_k"]) < 10:
                    self.add(4, "bad_k", {"version": self.version, "symbol": sym, "fill_t": str(ft), "k": k})
            want = rung_price(float(bo), float(sigd), k)
            if not rel_close(fp, want):
                bad_price += 1
                if len([x for x in self.mismatches if x["rule"] == 4 and x["class"] == "rung_price"]) < 10:
                    self.add(4, "rung_price", {"version": self.version, "symbol": sym, "fill_t": str(ft),
                                               "k": k, "got": fp, "want": want, "bar_open": float(bo),
                                               "sig_d": float(sigd)})
            if m < 16 or m > 238:
                bad_min += 1
                if len([x for x in self.mismatches if x["rule"] == 4 and x["class"] == "rung_minute"]) < 10:
                    self.add(4, "rung_minute", {"version": self.version, "symbol": sym, "fill_t": str(ft), "minute": m})
                continue
            w = minutes_window(sym, fb + pd.Timedelta(minutes=16), ft + pd.Timedelta(minutes=1))
            w = w[(w.open_time >= fb + pd.Timedelta(minutes=16)) & (w.open_time <= ft)]
            if len(w) == 0:
                continue
            hits = (w["low"] < fp).to_numpy()
            if not hits[-1]:
                bad_first += 1
                if len([x for x in self.mismatches if x["rule"] == 4 and x["class"] == "fill_no_touch"]) < 10:
                    self.add(4, "fill_no_touch", {"version": self.version, "symbol": sym, "fill_t": str(ft),
                                                 "price": fp, "low": float(w.iloc[-1]["low"])})
                continue
            first = None
            for i, h in enumerate(hits):
                if h:
                    first = pd.Timestamp(w.iloc[i]["open_time"])
                    break
            if first != ft:
                bad_first += 1
                if len([x for x in self.mismatches if x["rule"] == 4 and x["class"] == "not_first_touch"]) < 10:
                    self.add(4, "not_first_touch", {"version": self.version, "symbol": sym, "fill_t": str(ft),
                                                   "first_t": str(first), "price": fp})
        self.counts["rule4"] = {"checked": checked, "price": bad_price, "minute": bad_min,
                                "first": bad_first, "bad_k": bad_k,
                                "mismatches": bad_price + bad_min + bad_first + bad_k}
        return self.counts["rule4"]

    # ---- rule 5 + 6 ----
    def check_rule5(self):
        ev = self.events
        fills = ev[ev.kind == "rung_fill"].copy()
        exits = ev[ev.kind.isin(["rung_tp", "rung_sl", "rung_timeout"])].copy()
        fills["bar"] = fills["t"].dt.floor("4h")
        # pair per (bar, symbol): sort fills asc, tp/sl asc
        checked = 0
        bad_timing = 0
        bad_ret = 0
        bad_timeout_px = 0
        rule6_count = 0
        pnl_effect = 0.0
        for (bar, sym), gf in fills.groupby(["bar", "symbol"]):
            bar = pd.Timestamp(bar)
            brow = self.bar_by_t.get(bar)
            if brow is None:
                continue
            sigd = brow.get(f"sig_d_{sym}", float("nan"))
            bo = brow.get(f"open_{sym}", float("nan"))
            if pd.isna(sigd) or pd.isna(bo):
                continue
            sig4 = float(sigd) / math.sqrt(6.0)
            gf = gf.sort_values("price", ascending=True).reset_index(drop=True)
            ge_ts = exits[(exits.symbol == sym) & (exits.kind.isin(["rung_tp", "rung_sl"]))
                          & (exits.t.dt.floor("4h") == bar)].copy().sort_values("price", ascending=True).reset_index(drop=True)
            ge_to = exits[(exits.symbol == sym) & (exits.kind == "rung_timeout")
                          & (exits.t == bar + pd.Timedelta(hours=4))].copy().reset_index(drop=True)
            n_pair = min(len(gf), len(ge_ts))
            # rule 6 + timing per fill needs raw scan; do per fill with its paired exit if any
            pairs = {}
            for i in range(n_pair):
                pairs[i] = ("touch", ge_to is not None and ge_ts.iloc[i])
            # leftover fills -> timeout
            leftovers = list(range(n_pair, len(gf)))
            # check counts: timeouts should equal leftovers (allow same-price multiple timeouts)
            # pair leftovers to timeouts in order
            to_idx = 0
            for li in leftovers:
                if to_idx < len(ge_to):
                    pairs[li] = ("timeout", ge_to.iloc[to_idx])
                    to_idx += 1
                else:
                    pairs[li] = (None, None)
            if len(ge_to) != len(leftovers):
                # count mismatch noted once per group
                bad_timing += abs(len(ge_to) - len(leftovers))
                if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "pair_count"]) < 10:
                    self.add(5, "pair_count", {"version": self.version, "symbol": sym, "bar": str(bar),
                                              "fills": len(gf), "touch_exits": len(ge_ts),
                                              "timeouts": len(ge_to), "leftovers": len(leftovers)})
            for li, (kind, ex) in pairs.items():
                f = gf.iloc[li]
                ft = pd.Timestamp(f["t"])
                fp = float(f["price"])
                fill_min = int(round((ft - bar).total_seconds() / 60.0))
                checked += 1
                stop = fp * (1.0 - 8.0 * sig4)
                # rule 6: fill-minute low already <= stop/backstop
                fm = minute_at(sym, ft)
                if fm is not None and float(fm["low"]) <= stop:
                    rule6_count += 1
                if kind is None:
                    bad_timing += 1
                    if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "missing_exit"]) < 10:
                        self.add(5, "missing_exit", {"version": self.version, "symbol": sym,
                                                    "bar": str(bar), "fill_t": str(ft), "price": fp})
                    continue
                xt = pd.Timestamp(ex["t"])
                xp = float(ex["price"])
                xk = ex["kind"]
                stored_ret = float(ex["ret"]) if pd.notna(ex["ret"]) else float("nan")
                # ret check
                if pd.notna(stored_ret):
                    want_ret = expected_rung_ret(fp, xp, xk, xt)
                    if abs(stored_ret - want_ret) > 1e-6:
                        bad_ret += 1
                        pnl_effect += (want_ret - stored_ret) * float(ex["weight"] if pd.notna(ex["weight"]) else 0.0)
                        if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "ret_mismatch"]) < 10:
                            self.add(5, "ret_mismatch", {"version": self.version, "symbol": sym,
                                                        "bar": str(bar), "fill_t": str(ft), "exit_t": str(xt),
                                                        "kind": xk, "fill": fp, "exit": xp,
                                                        "stored_ret": stored_ret, "want_ret": want_ret})
                if self.version == "v367":
                    if xk == "rung_timeout":
                        if xt != bar + pd.Timedelta(hours=4):
                            bad_timing += 1
                            if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "timeout_time"]) < 10:
                                self.add(5, "timeout_time", {"version": self.version, "symbol": sym,
                                                            "bar": str(bar), "exit_t": str(xt)})
                        nb = minute_at(sym, xt)
                        if nb is not None and not rel_close(xp, float(nb["open"])):
                            bad_timeout_px += 1
                            if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "timeout_price"]) < 10:
                                self.add(5, "timeout_price", {"version": self.version, "symbol": sym,
                                                             "bar": str(bar), "exit_t": str(xt),
                                                             "got": xp, "want": float(nb["open"])})
                        # no stop/tp touch in (fill, end]
                        w = minutes_window(sym, ft + pd.Timedelta(minutes=1), bar + pd.Timedelta(hours=4))
                        if len(w):
                            if bool((w["low"] <= stop).any()):
                                bad_timing += 1
                                if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "timeout_missed_stop"]) < 10:
                                    self.add(5, "timeout_missed_stop", {"version": self.version, "symbol": sym,
                                                                        "bar": str(bar), "fill_t": str(ft)})
                            tp_touch = bool((w["high"] > xp).any())
                            # xp here is timeout exit price (next bar open), not a TP level;
                            # skip TP-touch check for timeouts (TP level unknown)
                    elif xk == "rung_sl":
                        w = minutes_window(sym, ft + pd.Timedelta(minutes=1), xt + pd.Timedelta(minutes=1))
                        w = w[(w.open_time > ft) & (w.open_time <= xt)]
                        if len(w) == 0:
                            bad_timing += 1
                            continue
                        er = w[w.open_time == xt]
                        if len(er) == 0:
                            bad_timing += 1
                            continue
                        er = er.iloc[0]
                        want_px = min(stop, float(er["open"]))
                        if not rel_close(xp, want_px):
                            bad_timing += 1
                            if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "sl_price"]) < 10:
                                self.add(5, "sl_price", {"version": self.version, "symbol": sym,
                                                        "bar": str(bar), "fill_t": str(ft), "exit_t": str(xt),
                                                        "got": xp, "want": want_px, "stop": stop})
                        pre = w[w.open_time < xt]
                        if len(pre) and bool((pre["low"] <= stop).any()):
                            bad_timing += 1
                            if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "sl_late"]) < 10:
                                self.add(5, "sl_late", {"version": self.version, "symbol": sym,
                                                       "bar": str(bar), "fill_t": str(ft), "exit_t": str(xt)})
                        if float(er["low"]) > stop:
                            bad_timing += 1
                            if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "sl_no_touch"]) < 10:
                                self.add(5, "sl_no_touch", {"version": self.version, "symbol": sym,
                                                            "bar": str(bar), "exit_t": str(xt), "stop": stop,
                                                            "low": float(er["low"])})
                    else:  # rung_tp: TP level = exit price
                        w = minutes_window(sym, ft + pd.Timedelta(minutes=1), xt + pd.Timedelta(minutes=1))
                        w = w[(w.open_time > ft) & (w.open_time <= xt)]
                        if len(w) == 0:
                            bad_timing += 1
                            continue
                        er = w[w.open_time == xt]
                        if len(er) == 0:
                            bad_timing += 1
                            continue
                        er = er.iloc[0]
                        if not (float(er["high"]) > xp):
                            bad_timing += 1
                            if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "tp_no_touch"]) < 10:
                                self.add(5, "tp_no_touch", {"version": self.version, "symbol": sym,
                                                            "bar": str(bar), "exit_t": str(xt), "tp": xp,
                                                            "high": float(er["high"])})
                        if not rel_close(xp, xp):
                            pass
                        pre = w[w.open_time < xt]
                        if len(pre):
                            if bool((pre["low"] <= stop).any()) or bool((pre["high"] > xp).any()):
                                bad_timing += 1
                                if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "tp_not_first"]) < 10:
                                    self.add(5, "tp_not_first", {"version": self.version, "symbol": sym,
                                                                 "bar": str(bar), "fill_t": str(ft), "exit_t": str(xt)})
                        if float(er["low"]) <= stop:
                            # tie must be stop
                            bad_timing += 1
                            if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "tp_tie"]) < 10:
                                self.add(5, "tp_tie", {"version": self.version, "symbol": sym,
                                                      "bar": str(bar), "exit_t": str(xt)})
                else:  # v321
                    stop5 = fp * (1.0 - 4.0 * sig4)
                    back = stop
                    if xk == "rung_timeout":
                        if xt != bar + pd.Timedelta(hours=4):
                            bad_timing += 1
                            if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "timeout_time"]) < 10:
                                self.add(5, "timeout_time", {"version": self.version, "symbol": sym,
                                                            "bar": str(bar), "exit_t": str(xt)})
                        nb = minute_at(sym, xt)
                        if nb is not None and not rel_close(xp, float(nb["open"])):
                            bad_timeout_px += 1
                            if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "timeout_price"]) < 10:
                                self.add(5, "timeout_price", {"version": self.version, "symbol": sym,
                                                             "bar": str(bar), "exit_t": str(xt),
                                                             "got": xp, "want": float(nb["open"])})
                        # verify no 5-min stop and no backstop touch in (fill, end]
                        w = minutes_window(sym, ft + pd.Timedelta(minutes=1), bar + pd.Timedelta(hours=4))
                        if len(w):
                            w = w.sort_values("open_time").reset_index(drop=True)
                            # map to minute offsets
                            base = bar
                            w["m"] = ((pd.to_datetime(w["open_time"]) - base).dt.total_seconds() / 60.0).round().astype(int)
                            wmap = {int(r["m"]): r for _, r in w.iterrows()}
                            trig = False
                            for m in range(fill_min + 1, 240):
                                if (m + 1) % 5 == 0 and m in wmap and float(wmap[m]["close"]) <= stop5:
                                    trig = True
                                    break
                                if m in wmap and float(wmap[m]["low"]) <= back:
                                    trig = True
                                    break
                            if trig:
                                bad_timing += 1
                                if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "timeout_missed_stop"]) < 10:
                                    self.add(5, "timeout_missed_stop", {"version": self.version, "symbol": sym,
                                                                        "bar": str(bar), "fill_t": str(ft)})
                    elif xk == "rung_sl":
                        w = minutes_window(sym, ft + pd.Timedelta(minutes=1), xt + pd.Timedelta(minutes=1))
                        w = w[(w.open_time > ft) & (w.open_time <= xt)].sort_values("open_time").reset_index(drop=True)
                        if len(w) == 0:
                            bad_timing += 1
                            continue
                        w["m"] = ((pd.to_datetime(w["open_time"]) - bar).dt.total_seconds() / 60.0).round().astype(int)
                        wmap = {int(r["m"]): r for _, r in w.iterrows()}
                        exit_m = int(round((xt - bar).total_seconds() / 60.0))
                        # compute expected stop exit
                        exp_m, exp_px, exp_kind = None, None, None
                        # backstop candidate
                        b_m = None
                        for m in range(fill_min + 1, 240):
                            if m in wmap and float(wmap[m]["low"]) <= back:
                                b_m = m
                                break
                        # 5-min candidate
                        s_m = None
                        for m in range(fill_min + 1, 240):
                            if (m + 1) % 5 == 0 and m in wmap and float(wmap[m]["close"]) <= stop5:
                                s_m = m + 1  # exit next minute open
                                break
                        cand_back = (b_m, min(back, float(wmap[b_m]["open"])) if b_m is not None else None)
                        if b_m is not None and s_m is not None:
                            if b_m <= s_m:
                                exp_m, exp_px = b_m, min(back, float(wmap[b_m]["open"]))
                            else:
                                exp_m, exp_px = s_m, (float(wmap[s_m]["open"]) if s_m in wmap else None)
                                if s_m == 240:
                                    nb = minute_at(sym, bar + pd.Timedelta(hours=4))
                                    exp_px = float(nb["open"]) if nb is not None else exp_px
                        elif b_m is not None:
                            exp_m, exp_px = b_m, min(back, float(wmap[b_m]["open"]))
                        elif s_m is not None:
                            exp_m = s_m
                            if s_m in wmap:
                                exp_px = float(wmap[s_m]["open"])
                            elif s_m == 240:
                                nb = minute_at(sym, bar + pd.Timedelta(hours=4))
                                exp_px = float(nb["open"]) if nb is not None else None
                        if exp_m is None or exp_m != exit_m or (exp_px is not None and not rel_close(xp, exp_px)):
                            bad_timing += 1
                            if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "sl_timing"]) < 10:
                                self.add(5, "sl_timing", {"version": self.version, "symbol": sym,
                                                         "bar": str(bar), "fill_t": str(ft), "exit_t": str(xt),
                                                         "got": xp, "want": exp_px, "want_m": exp_m})
                    else:  # rung_tp
                        w = minutes_window(sym, ft + pd.Timedelta(minutes=1), xt + pd.Timedelta(minutes=1))
                        w = w[(w.open_time > ft) & (w.open_time <= xt)].sort_values("open_time").reset_index(drop=True)
                        if len(w) == 0:
                            bad_timing += 1
                            continue
                        er = w[w.open_time == xt]
                        if len(er) == 0:
                            bad_timing += 1
                            continue
                        er = er.iloc[0]
                        if not (float(er["high"]) > xp):
                            bad_timing += 1
                            if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "tp_no_touch"]) < 10:
                                self.add(5, "tp_no_touch", {"version": self.version, "symbol": sym,
                                                            "bar": str(bar), "exit_t": str(xt), "tp": xp,
                                                            "high": float(er["high"])})
                        pre = w[w.open_time < xt]
                        # check no stop before (either trigger)
                        stopped = False
                        if len(pre):
                            pre = pre.copy()
                            pre["m"] = ((pd.to_datetime(pre["open_time"]) - bar).dt.total_seconds() / 60.0).round().astype(int)
                            pmap = {int(r["m"]): r for _, r in pre.iterrows()}
                            for m in range(fill_min + 1, int(round((xt - bar).total_seconds() / 60.0))):
                                if (m + 1) % 5 == 0 and m in pmap and float(pmap[m]["close"]) <= stop5:
                                    stopped = True
                                    break
                                if m in pmap and float(pmap[m]["low"]) <= back:
                                    stopped = True
                                    break
                            if bool((pre["high"] > xp).any()):
                                bad_timing += 1
                                if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "tp_not_first"]) < 10:
                                    self.add(5, "tp_not_first", {"version": self.version, "symbol": sym,
                                                                 "bar": str(bar), "fill_t": str(ft), "exit_t": str(xt)})
                            if stopped:
                                bad_timing += 1
                                if len([x for x in self.mismatches if x["rule"] == 5 and x["class"] == "tp_after_stop"]) < 10:
                                    self.add(5, "tp_after_stop", {"version": self.version, "symbol": sym,
                                                                  "bar": str(bar), "fill_t": str(ft), "exit_t": str(xt)})
        self.counts["rule5"] = {"checked": checked, "timing": bad_timing, "ret": bad_ret,
                                "timeout_price": bad_timeout_px, "pnl_effect": pnl_effect,
                                "mismatches": bad_timing + bad_ret + bad_timeout_px}
        self.counts["rule6"] = {"fill_minute_through_stop": rule6_count}
        return self.counts["rule5"]

    def run_all(self):
        self.check_rule1()
        self.check_rule2()
        self.check_rule3()
        self.check_rule4()
        self.check_rule5()
        return self.counts


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_counts = {}
    all_mis = []
    for v in ("v367", "v321"):
        c = Checker(v)
        c.run_all()
        all_counts[v] = c.counts
        for m in c.mismatches:
            m2 = dict(m)
            m2["pipeline"] = ("M5" if v == "v367" else "R2")
            all_mis.append(m2)
        # per-version mismatch csv
        pd.DataFrame(c.mismatches).to_csv(OUT_DIR / f"mismatches_{v}.csv", index=False)
    rep = {"counts": all_counts, "mismatches_sample": all_mis[:200],
           "rules": "rules 1-6 per OPENCODE_SYSAUDIT_FILLS.md; ret want = exit/fill-1-0.0002-(0.00055 stops/timeouts else 0.0002)-0.0001 funding timeouts at 00/08/16UTC; tol 1e-6 rel",
           "pairing": "rung exits paired per (bar,symbol): fills asc with touch exits asc; leftovers to timeouts at next bar open"}
    import json
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(rep, f, indent=2, default=str)
    pd.DataFrame(all_mis).to_csv(OUT_DIR / "mismatches.csv", index=False)
    print(json.dumps(all_counts, indent=2, default=str))


if __name__ == "__main__":
    main()
