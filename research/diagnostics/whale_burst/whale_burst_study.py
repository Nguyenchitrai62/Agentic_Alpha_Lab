"""Whale-burst reversal event study (dev years only).

Bounded research task: do taker order-flow "whale bursts" (>=1M USDT orders in one
minute) predict short-horizon reversals that a human/bot could trade with resting
limit orders?

HARD DATA LIMIT: only minutes with timestamp < 2025-09-24 00:00 UTC are ever used.
Thresholds are fit on minutes BEFORE 2021-09-24 only. Files that extend past the
cutoff are filtered to < CUTOFF immediately on read (per file, before concat) and
every loader asserts the final frame max timestamp < CUTOFF. Post-cutoff files
(klines_1m_2026, flow months >= 2025-10) are never opened.

Method (fixed before looking at results):
- W_sell[m] = sell_1m_3m + sell_ge3m, W_buy[m] = buy_1m_3m + buy_ge3m (taker
  notional, USDT, orders >= 1M).
- Burst thresholds q per symbol/side: 99.9th (primary), 99.5th, 99.97th percentiles
  of that side's per-minute W over minutes < 2021-09-24 with W > 0.
- Dedup: first burst minute in any 60-minute window, per symbol/side/q-level.
- Only bursts with 2021-09-24 <= m <= CUTOFF - 271min are evaluated (271 = 31min
  fill window + 240min max holding, so every exit is observable before CUTOFF).
- SELL burst -> LONG: limit buy at close[m]*(1-d), d in {0,10,30} bps, resting
  minutes m+2..m+31; fill only on a 1m trade-THROUGH (low < limit, strict),
  fill px = limit, maker 0.02%. BUY burst -> SHORT is the mirror (high > limit).
- After a fill at minute f: stop-loss market at limit*(1-1.5%) long
  (limit*(1+1.5%) short), taker 0.055%, filled at min(stop, open) long /
  max(stop, open) short when gapped; take-profit limit at limit*(1+t) long
  (limit*(1-t) short), t in {0.3%,0.6%,1.0%}, maker 0.02%; else market exit
  (taker) at the open of minute f+H, H in {60,240}. Stop/TP are checked from
  minute f+1 through f+H-1; a minute touching both resolves stop-first.
- Net return per filled trade in bps, net of the fees above.
- Baseline: identical trade rules from RANDOM minutes (same count per symbol and
  year as the real bursts of that side/q group, fixed seed 7).
- Dip-ladder overlap (long tests): fill already traded by the pipeline when
  fill px <= 4h-bar-open * (1 - 2.5*sigma_4h), where the bar is the 4h bar
  containing the fill minute and sigma_4h is the std of 4h open-to-open pct
  changes over the previous 360 bars (60 days, min_periods 360).
- A row is "stable" when the mean net bps > 0 in all four anchor years
  (y1=[2021-09-24,2022-09-24), ..., y4=[2024-09-24,2025-09-24)).

Outputs: results.csv + SUMMARY.md in this folder.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

CUTOFF = pd.Timestamp("2025-09-24 00:00", tz="UTC")
ANCHOR = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_STARTS = [pd.Timestamp(f"{y}-09-24 00:00", tz="UTC") for y in (2021, 2022, 2023, 2024)]
YEAR_END = CUTOFF  # y4 = [2024-09-24, 2025-09-24)

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
Q_LEVELS = (0.995, 0.999, 0.9997)
Q_NAMES = {0.995: "99.5", 0.999: "99.9", 0.9997: "99.97"}
D_BPS = (0, 10, 30)
TP_PCT = (0.3, 0.6, 1.0)
HOLD_MIN = (60, 240)
STOP_PCT = 1.5
FILL_OFF_0, FILL_OFF_1 = 2, 31  # resting minutes m+2 .. m+31
DEDUP_MIN = 60
MAX_AHEAD = FILL_OFF_1 + max(HOLD_MIN)  # 271: worst-case fill + hold after m
MAKER = 0.0002
TAKER = 0.00055
BASE_SEED = 7

SIDES = ("sell", "buy")  # sell burst -> LONG test, buy burst -> SHORT test
SIDE_TRADE = {"sell": "long", "buy": "short"}

DATA_ROOT = Path("data/raw")
FLOW_ROOT = DATA_ROOT / "aggflow_20260929_orders_1m"
BTC_KLINES = DATA_ROOT / "btc_intraday_20260924"
MAJ_KLINES = DATA_ROOT / "majors_intraday_20260924"
OUT_DIR = Path("research/diagnostics/whale_burst")


# ---------------------------------------------------------------- pure helpers
def enforce_cutoff(ts: pd.DatetimeIndex) -> np.ndarray:
    """Boolean mask keeping only minutes strictly before CUTOFF."""
    t = pd.DatetimeIndex(ts).tz_convert("UTC")
    return t.values < np.datetime64(CUTOFF.tz_convert("UTC").tz_localize(None))


def assert_cutoff(ts: pd.DatetimeIndex, what: str) -> None:
    bad = pd.DatetimeIndex(ts).tz_convert("UTC")
    assert (bad.values < np.datetime64("2025-09-24T00:00:00")).all(), (
        f"{what}: loaded a minute >= 2025-09-24 (max {bad.max()})"
    )


def dedup_positions(cand: np.ndarray) -> np.ndarray:
    """Keep the first candidate in any 60-minute window (positions on a 1/min grid)."""
    cand = np.asarray(sorted(set(int(c) for c in cand)), dtype=np.int64)
    if cand.size == 0:
        return cand
    keep = [cand[0]]
    for c in cand[1:]:
        if c - keep[-1] >= DEDUP_MIN:
            keep.append(c)
    return np.array(keep, dtype=np.int64)


def find_fill_long(limit: float, low_win: np.ndarray) -> int | None:
    """Offset of first minute with low strictly through the bid; None if no fill."""
    for k, low in enumerate(low_win):
        if low < limit:
            return k
    return None


def find_fill_short(limit: float, high_win: np.ndarray) -> int | None:
    for k, high in enumerate(high_win):
        if high > limit:
            return k
    return None


def resolve_exit_long(stop: float, tp: float, o: np.ndarray, h: np.ndarray,
                      l: np.ndarray, open_at_H: float):
    """Scan minutes f+1..f+H-1; stop-first on ties; else market at open of f+H."""
    for k in range(len(o)):
        sh, th = l[k] <= stop, h[k] >= tp
        if sh and th:
            return min(stop, o[k]), "stop", TAKER  # stop-first tie rule
        if sh:
            return min(stop, o[k]), "stop", TAKER
        if th:
            return tp, "tp", MAKER
    return open_at_H, "timed", TAKER


def resolve_exit_short(stop: float, tp: float, o: np.ndarray, h: np.ndarray,
                       l: np.ndarray, open_at_H: float):
    for k in range(len(o)):
        sh, th = h[k] >= stop, l[k] <= tp
        if sh and th:
            return max(stop, o[k]), "stop", TAKER
        if sh:
            return max(stop, o[k]), "stop", TAKER
        if th:
            return tp, "tp", MAKER
    return open_at_H, "timed", TAKER


def net_bps_long(entry: float, exit_px: float, exit_fee: float) -> float:
    return (exit_px * (1 - exit_fee) / (entry * (1 + MAKER)) - 1.0) * 1e4


def net_bps_short(entry: float, exit_px: float, exit_fee: float) -> float:
    return (entry * (1 - MAKER) / (exit_px * (1 + exit_fee)) - 1.0) * 1e4


def year_of(ts: pd.DatetimeIndex) -> np.ndarray:
    """Anchor-year code 1..4 for burst minutes; 0 outside the dev window."""
    t = pd.DatetimeIndex(ts).tz_convert("UTC").values
    y = np.zeros(len(t), dtype=np.int8)
    s = np.array([np.datetime64(x.tz_convert("UTC").tz_localize(None)) for x in YEAR_STARTS])
    end = np.datetime64("2025-09-24T00:00:00")
    for i in range(4):
        lo, hi = s[i], s[i + 1] if i < 3 else end
        y[(t >= lo) & (t < hi)] = i + 1
    return y


# ---------------------------------------------------------------- loaders
def _month_key(p: Path) -> tuple[int, int]:
    m = re.search(r"(\d{4})-(\d{2})", p.name)
    return (int(m.group(1)), int(m.group(2))) if m else (9999, 99)


def load_symbol(sym: str) -> pd.DataFrame:
    """Minute grid (o/h/l/c, W_buy, W_sell) for sym, strictly before CUTOFF."""
    kd = BTC_KLINES if sym == "BTCUSDT" else MAJ_KLINES
    pat = "klines_1m_20*.parquet" if sym == "BTCUSDT" else f"{sym}_1m_20*.parquet"
    kparts = []
    for f in sorted(kd.glob(pat)):
        if "2026" in f.name:  # locked year file: never opened
            continue
        k = pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"])
        k["open_time"] = pd.to_datetime(k["open_time"], utc=True)
        k = k[k["open_time"] < CUTOFF]  # immediate cut before any computation
        if len(k):
            kparts.append(k)
    k = pd.concat(kparts).drop_duplicates("open_time").sort_values("open_time")
    assert_cutoff(k["open_time"], f"{sym} klines")
    k = k.set_index("open_time")
    for c in ("open", "high", "low", "close"):
        k[c] = k[c].astype(float)

    wparts = []
    for f in sorted(FLOW_ROOT.joinpath(sym).glob("*.parquet")):
        yy, mm = _month_key(f)
        if (yy, mm) >= (2025, 10):  # locked months: never opened
            continue
        w = pd.read_parquet(f)
        w.index = pd.DatetimeIndex(w.index).tz_convert("UTC")
        w = w[w.index < CUTOFF]  # immediate cut before any computation
        if len(w):
            # early months lack the largest bins: missing notional = 0
            wparts.append(w.reindex(columns=["buy_1m_3m", "buy_ge3m",
                                             "sell_1m_3m", "sell_ge3m"],
                                    fill_value=0.0))
    w = (pd.concat(wparts).groupby(level=0).sum().sort_index() if wparts
         else pd.DataFrame(columns=["buy_1m_3m", "buy_ge3m", "sell_1m_3m", "sell_ge3m"]))
    assert_cutoff(w.index, f"{sym} flow")

    g = k.join(w, how="left").fillna(0.0)
    g["W_buy"] = g["buy_1m_3m"] + g["buy_ge3m"]
    g["W_sell"] = g["sell_1m_3m"] + g["sell_ge3m"]
    assert_cutoff(g.index, f"{sym} grid")
    return g[["open", "high", "low", "close", "W_buy", "W_sell"]]


def fit_thresholds(g: pd.DataFrame) -> dict[str, dict[float, float]]:
    """q per side from minutes < ANCHOR with W > 0 (pre-anchor fit only)."""
    pre = g[g.index < ANCHOR]
    out: dict[str, dict[float, float]] = {}
    for side in SIDES:
        w = pre[f"W_{side}"].to_numpy()
        w = w[w > 0]
        assert w.size > 0, f"no positive W_{side} minutes before anchor"
        out[side] = {q: float(np.quantile(w, q)) for q in Q_LEVELS}
    return out


def burst_positions(g: pd.DataFrame, side: str, q: float, thr: float) -> np.ndarray:
    """Deduped burst positions with ANCHOR <= m and full exit window inside data."""
    ts = g.index
    n = len(g)
    ok = enforce_cutoff(ts)  # all true by construction; belt and braces
    w = np.where(ok, g[f"W_{side}"].to_numpy(), -1.0)
    last = n - 1 - MAX_AHEAD
    cand = np.flatnonzero((ts.values >= np.datetime64(ANCHOR.tz_localize(None)))
                          & (np.arange(n) <= last) & (w >= thr))
    return dedup_positions(cand)


# ---------------------------------------------------------------- simulation
def simulate(E: np.ndarray, trade: str, d: float, t: float, H: int,
             O: np.ndarray, Hh: np.ndarray, L: np.ndarray, C: np.ndarray):
    """Vectorised trade simulation. Returns (fill_pos or -1, net_bps or nan, exit_kind)."""
    n = len(E)
    fill = np.full(n, -1, dtype=np.int64)
    net = np.full(n, np.nan)
    kind = np.full(n, "", dtype=object)
    if n == 0:
        return fill, net, kind
    ref = C[E]
    limit = ref * (1 - d) if trade == "long" else ref * (1 + d)
    offs = np.arange(FILL_OFF_0, FILL_OFF_1 + 1)
    li = E[:, None] + offs
    if trade == "long":
        cond = L[li] < limit[:, None]
    else:
        cond = Hh[li] > limit[:, None]
    has = cond.any(axis=1)
    first = cond.argmax(axis=1)
    F = E[has] + offs[first[has]]
    fill[has] = F
    lim = limit[has]
    stop = lim * (1 - STOP_PCT / 100) if trade == "long" else lim * (1 + STOP_PCT / 100)
    tp = lim * (1 + t) if trade == "long" else lim * (1 - t)
    m = int(has.sum())
    if m:
        go = np.arange(1, H)
        gg = F[:, None] + go
        o, h, l = O[gg], Hh[gg], L[gg]
        if trade == "long":
            sh, th = l <= stop[:, None], h >= tp[:, None]
            px_stop = np.minimum(stop[:, None], o)
            nps = net_bps_long
        else:
            sh, th = h >= stop[:, None], l <= tp[:, None]
            px_stop = np.maximum(stop[:, None], o)
            nps = net_bps_short
        any_sh, any_th = sh.any(axis=1), th.any(axis=1)
        fs = np.where(any_sh, sh.argmax(axis=1), np.iinfo(np.int64).max)
        ft = np.where(any_th, th.argmax(axis=1), np.iinfo(np.int64).max)
        use_stop = any_sh & (fs <= ft)  # ties -> stop
        use_tp = any_th & (~use_stop)
        timed = ~(use_stop | use_tp)
        ex = np.empty(m)
        xf = np.empty(m)
        rows = np.arange(m)
        ex[use_stop] = px_stop[rows[use_stop], fs[use_stop]]
        xf[use_stop] = TAKER
        ex[use_tp] = tp[use_tp]
        xf[use_tp] = MAKER
        ex[timed] = O[F[timed] + H]
        xf[timed] = TAKER
        idx = np.flatnonzero(has)
        net[idx] = [nps(e, x, f) for e, x, f in zip(lim, ex, xf)]
        kk = np.full(m, "timed", dtype=object)
        kk[use_stop] = "stop"
        kk[use_tp] = "tp"
        kind[idx] = kk
    return fill, net, kind


def dip_overlap(g: pd.DataFrame, fill_pos: np.ndarray, fill_px: np.ndarray) -> np.ndarray:
    """Which long fills were already <= 4h-open*(1-2.5*sigma_4h) (pipeline dip zone)."""
    ts = g.index
    bar = ts.floor("4h")
    opens = g["open"].to_numpy()
    is_first = np.r_[True, bar.values[1:] != bar.values[:-1]]
    bts = ts[is_first]
    bop = opens[is_first]
    ret = pd.Series(bop, index=bts).pct_change()
    sig = ret.rolling(360, min_periods=360).std().to_numpy()
    bi = np.searchsorted(bts.values, ts.values, side="right") - 1
    sigma = np.where(bi >= 0, sig[np.clip(bi, 0, len(sig) - 1)], np.nan)
    fbar = np.searchsorted(bts.values, ts.values[fill_pos], side="right") - 1
    fbar = np.clip(fbar, 0, len(bop) - 1)
    bo = bop[fbar]
    sg = np.where(fbar >= 0, sig[fbar], np.nan)
    return (fill_px <= bo * (1 - 2.5 * sg)) & ~np.isnan(sg)


# ---------------------------------------------------------------- driver
def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(BASE_SEED)
    trade_rows: list[pd.DataFrame] = []
    event_rows: list[dict] = []
    juris: dict[str, float] = {}
    for sym in SYMBOLS:
        g = load_symbol(sym)
        ts = g.index
        n = len(g)
        O, Hh, L, C = (g[c].to_numpy() for c in ("open", "high", "low", "close"))
        yrs_all = year_of(ts)
        thr = fit_thresholds(g)
        for k, v in thr.items():
            for q in Q_LEVELS:
                juris[f"{sym}|{k}|{Q_NAMES[q]}"] = v[q]
        for side in SIDES:
            trade = SIDE_TRADE[side]
            for q in Q_LEVELS:
                E = burst_positions(g, side, q, thr[side][q])
                Ey = year_of(ts[E]) if len(E) else np.zeros(0, dtype=np.int8)
                # random baseline: same count per symbol and year
                pool_by_year = {
                    y: np.flatnonzero((yrs_all == y) & (np.arange(n) <= n - 1 - MAX_AHEAD))
                    for y in (1, 2, 3, 4)
                }
                Rb = []
                for y in (1, 2, 3, 4):
                    cnt = int((Ey == y).sum())
                    pool = pool_by_year[y]
                    assert len(pool) >= cnt, f"{sym} {side} {q}: pool too small"
                    Rb.append(rng.choice(pool, size=cnt, replace=False) if cnt else
                              np.zeros(0, dtype=np.int64))
                R = np.sort(np.concatenate(Rb)) if Rb else np.zeros(0, dtype=np.int64)
                Ry = year_of(ts[R]) if len(R) else np.zeros(0, dtype=np.int8)
                for kd, (EE, EEy) in (("real", (E, Ey)), ("base", (R, Ry))):
                    for d_bps in D_BPS:
                        d = d_bps / 1e4
                        for t_pct in TP_PCT:
                            t = t_pct / 100
                            for H in HOLD_MIN:
                                fill, net, _ = simulate(EE, trade, d, t, H, O, Hh, L, C)
                                for y in (1, 2, 3, 4):
                                    event_rows.append({
                                        "kind": kd, "side": side, "trade": trade,
                                        "q": Q_NAMES[q], "d_bps": d_bps,
                                        "tp_pct": t_pct, "H_min": H,
                                        "sym": sym, "year": y,
                                        "events": int(((EEy == y)).sum()),
                                    })
                                ok = fill >= 0
                                if not ok.any():
                                    continue
                                Fp = fill[ok]
                                ov = (dip_overlap(g, Fp, (C[E[ok]] * (1 - d)).astype(float))
                                      if trade == "long" else np.zeros(ok.sum(), bool))
                                trade_rows.append(pd.DataFrame({
                                    "kind": kd, "side": side, "trade": trade,
                                    "q": Q_NAMES[q], "d_bps": d_bps,
                                    "tp_pct": t_pct, "H_min": H, "sym": sym,
                                    "year": EEy[ok], "net_bps": net[ok], "overlap": ov,
                                }))
    trades = (pd.concat(trade_rows, ignore_index=True) if trade_rows
              else pd.DataFrame(columns=["kind", "side", "trade", "q", "d_bps",
                                         "tp_pct", "H_min", "sym", "year",
                                         "net_bps", "overlap"]))
    events = pd.DataFrame(event_rows)
    return trades, events


def tstat(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    if x.size < 2 or x.std(ddof=1) == 0:
        return 0.0
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(x.size)))


def summarise(trades: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    keys = ["kind", "side", "trade", "q", "d_bps", "tp_pct", "H_min"]
    ev = events.groupby(keys + ["sym", "year"], as_index=False)["events"].sum()
    ev_all = events.groupby(keys, as_index=False)["events"].sum().rename(
        columns={"events": "events_all"})
    out: list[dict] = []
    grouped = trades.groupby(keys) if len(trades) else []
    yearly = (trades.groupby(keys + ["year"])["net_bps"]
              .agg(["mean", "count"]).reset_index() if len(trades) else pd.DataFrame())
    for name, grp in (grouped if len(trades) else []):
        base = dict(zip(keys, name))
        x = grp["net_bps"].to_numpy()
        ym = {y: float(yearly[(yearly[keys] == pd.Series(base)).all(axis=1) &
                              (yearly["year"] == y)]["mean"].iloc[0])
              if ((yearly[keys] == pd.Series(base)).all(axis=1) & (yearly["year"] == y)).any()
              else np.nan for y in (1, 2, 3, 4)}
        yc = {y: int(yearly[(yearly[keys] == pd.Series(base)).all(axis=1) &
                             (yearly["year"] == y)]["count"].iloc[0])
              if ((yearly[keys] == pd.Series(base)).all(axis=1) & (yearly["year"] == y)).any()
              else 0 for y in (1, 2, 3, 4)}
        stable = all(yc[y] > 0 and ym[y] > 0 for y in (1, 2, 3, 4))
        ev_row = ev_all[(ev_all[keys] == pd.Series(base)).all(axis=1)]
        nev = int(ev_row["events_all"].iloc[0]) if len(ev_row) else 0
        ov = grp["overlap"].to_numpy(dtype=bool)
        no = ~ov
        row = dict(base, scope="all", events=nev, fills=int(len(x)),
                   fill_rate=len(x) / nev if nev else 0.0,
                   mean_bps=float(x.mean()), median_bps=float(np.median(x)),
                   win_rate=float((x > 0).mean()), tstat=tstat(x),
                   stable=bool(stable),
                   y1_mean=ym[1], y2_mean=ym[2], y3_mean=ym[3], y4_mean=ym[4],
                   y1_n=yc[1], y2_n=yc[2], y3_n=yc[3], y4_n=yc[4],
                   overlap_share=float(ov.mean()),
                   nonoverlap_n=int(no.sum()),
                   nonoverlap_mean=float(x[no].mean()) if no.any() else np.nan)
        out.append(row)
        for y in (1, 2, 3, 4):
            xy = x[grp["year"].to_numpy() == y]
            evy = ev[(ev[keys] == pd.Series(base)).all(axis=1) & (ev["year"] == y)]
            nevy = int(evy["events"].sum())
            oyy = ov[grp["year"].to_numpy() == y]
            out.append(dict(base, scope=f"y{y}", events=nevy, fills=int(len(xy)),
                            fill_rate=len(xy) / nevy if nevy else 0.0,
                            mean_bps=float(xy.mean()) if len(xy) else np.nan,
                            median_bps=float(np.median(xy)) if len(xy) else np.nan,
                            win_rate=float((xy > 0).mean()) if len(xy) else np.nan,
                            tstat=tstat(xy), stable=False,
                            y1_mean=np.nan, y2_mean=np.nan, y3_mean=np.nan,
                            y4_mean=np.nan, y1_n=0, y2_n=0, y3_n=0, y4_n=0,
                            overlap_share=float(oyy.mean()) if len(oyy) else np.nan,
                            nonoverlap_n=int((~oyy).sum()),
                            nonoverlap_mean=(float(xy[~oyy].mean())
                                             if (~oyy).any() else np.nan)))
        for s in SYMBOLS:
            xs = x[grp["sym"].to_numpy() == s]
            evs = ev[(ev[keys] == pd.Series(base)).all(axis=1) & (ev["sym"] == s)]
            nevs = int(evs["events"].sum())
            os_ = ov[grp["sym"].to_numpy() == s]
            out.append(dict(base, scope=s, events=nevs, fills=int(len(xs)),
                            fill_rate=len(xs) / nevs if nevs else 0.0,
                            mean_bps=float(xs.mean()) if len(xs) else np.nan,
                            median_bps=float(np.median(xs)) if len(xs) else np.nan,
                            win_rate=float((xs > 0).mean()) if len(xs) else np.nan,
                            tstat=tstat(xs), stable=False,
                            y1_mean=np.nan, y2_mean=np.nan, y3_mean=np.nan,
                            y4_mean=np.nan, y1_n=0, y2_n=0, y3_n=0, y4_n=0,
                            overlap_share=float(os_.mean()) if len(os_) else np.nan,
                            nonoverlap_n=int((~os_).sum()),
                            nonoverlap_mean=(float(xs[~os_].mean())
                                             if (~os_).any() else np.nan)))
    # keys with events but zero fills (no trade rows): still report event counts
    seen = {tuple(r[k] for k in keys) for r in out}
    for _, er in events.groupby(keys, as_index=False)["events"].sum().iterrows():
        kk = tuple(er[k] for k in keys)
        if kk in seen:
            continue
        base = dict(zip(keys, kk))
        out.append(dict(base, scope="all", events=int(er["events"]), fills=0,
                        fill_rate=0.0, mean_bps=np.nan, median_bps=np.nan,
                        win_rate=np.nan, tstat=0.0, stable=False,
                        y1_mean=np.nan, y2_mean=np.nan, y3_mean=np.nan,
                        y4_mean=np.nan, y1_n=0, y2_n=0, y3_n=0, y4_n=0,
                        overlap_share=np.nan, nonoverlap_n=0, nonoverlap_mean=np.nan))
    cols = (keys + ["scope", "events", "fills", "fill_rate", "mean_bps",
                    "median_bps", "win_rate", "tstat", "stable", "y1_mean",
                    "y2_mean", "y3_mean", "y4_mean", "y1_n", "y2_n", "y3_n",
                    "y4_n", "overlap_share", "nonoverlap_n", "nonoverlap_mean"])
    res = pd.DataFrame(out)
    return res[cols].sort_values(keys + ["scope"]).reset_index(drop=True)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    trades, events = run()
    res = summarise(trades, events)
    res.to_csv(OUT_DIR / "results.csv", index=False)
    real = res[(res["kind"] == "real") & (res["scope"] == "all")].copy()
    base = res[(res["kind"] == "base") & (res["scope"] == "all")].copy()
    lines = [
        "# Whale-burst reversal study: summary",
        f"Universe: {', '.join(SYMBOLS)} 1m, dev window 2021-09-24..2025-09-23 "
        f"(bursts fit < 2021-09-24). Costs: maker 2 bps / taker 5.5 bps.",
        f"Grid: {len(real)} real + {len(base)} baseline param rows "
        f"(2 sides x 3 q x 3 d x 3 t x 2 H). Round-trip cost ~4-8 bps.",
    ]
    stab = real[real["stable"]].sort_values("mean_bps", ascending=False)
    lines.append(f"Stable rows (mean>0 in all 4 years): {len(stab)} of {len(real)}.")
    for _, r in stab.head(6).iterrows():
        b = base[(base["side"] == r["side"]) & (base["q"] == r["q"]) &
                 (base["d_bps"] == r["d_bps"]) & (base["tp_pct"] == r["tp_pct"]) &
                 (base["H_min"] == r["H_min"])]
        bm = float(b["mean_bps"].iloc[0]) if len(b) else float("nan")
        lines.append(
            f"{r['trade']} q{r['q']} d{r['d_bps']}bps tp{r['tp_pct']}% H{r['H_min']}: "
            f"n={r['fills']} fill={r['fill_rate']:.2f} mean={r['mean_bps']:.1f}bps "
            f"med={r['median_bps']:.1f} wr={r['win_rate']:.2f} t={r['tstat']:.2f} "
            f"y=[{r['y1_mean']:.1f},{r['y2_mean']:.1f},{r['y3_mean']:.1f},{r['y4_mean']:.1f}] "
            f"vs base {bm:.1f}bps; overlap={r['overlap_share']:.2f} "
            f"nonov n={r['nonoverlap_n']} mean={r['nonoverlap_mean']:.1f}bps.")
    if len(stab):
        r = stab.iloc[0]
        lines.append(
            f"Best stable: {r['trade']} q{r['q']} d{r['d_bps']}bps tp{r['tp_pct']}% "
            f"H{r['H_min']} mean {r['mean_bps']:.1f}bps/trade vs ~4-8bps costs.")
        lines.append("Verdict: " + (
            "TRADABLE EDGE if best-stable mean net of costs with fill rate "
            "high enough to matter, else NO EDGE (see numbers above)."
        ))
    else:
        lines.append("Verdict: NO TRADABLE EDGE - no param row is positive in all "
                     "four dev years net of costs.")
    (OUT_DIR / "SUMMARY.md").write_text("\n".join(lines[:20]) + "\n")
    print("\n".join(lines[:20]))


if __name__ == "__main__":
    main()
