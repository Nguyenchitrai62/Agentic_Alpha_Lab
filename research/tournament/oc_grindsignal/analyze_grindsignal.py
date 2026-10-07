"""oc_grindsignal: causal pre-signal diagnostic for the G2 59-day grind.

Per PLAN.md (pre-registered): at the grind window start E0 = 2023-04-17 00:00
UTC and the other big DD starts E1..E3 (oc_ddanat4p mix_episodes.json reset
peaks), compute 30 causal statistics (funding, 30d vol + change, 90d trend,
breadth, dip fill/TP rate, book win rate, BNB-vs-BTC RS) using ONLY data
strictly before T, then percentile each against its distribution over all 4h
bars of the 5 years. Hypotheses-only: stats extreme (<=5 / >=95) in >=3 of 4
episodes on the same tail.

Single process; loads only hourly_ext + settled funding + oc_kpi events.
No 1m data of any kind.

  python research/tournament/oc_grindsignal/analyze_grindsignal.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
EXT = ROOT / "research/tournament/ext"
PREM = ROOT / "data/raw/binance_premium_20260928"
OCKPI = ROOT / "research/tournament/oc_kpi"
MIX4P = ROOT / "research/tournament/oc_ddanat4p/mix_episodes.json"
MIXG2 = ROOT / "research/tournament/oc_ddanat_g2/mix_episodes.json"

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
GRID_START = pd.Timestamp("2021-09-24", tz="UTC")
GRID_END = pd.Timestamp("2026-09-24", tz="UTC")
D30 = pd.Timedelta(days=30)
D90 = pd.Timedelta(days=90)
D200 = pd.Timedelta(days=200)
D7 = pd.Timedelta(days=7)
ANN = float(np.sqrt(24 * 365))
MAKER, TAKER = 0.0002, 0.00055


def load_hourly() -> dict[str, pd.DataFrame]:
    """Per-coin frame indexed by bar-end (t + 1h), columns close/logret."""
    h = pd.read_parquet(EXT / "hourly_ext.parquet", columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    out = {}
    for s in MAJORS:
        d = h[h["sym"] == s].sort_values("t").reset_index(drop=True)
        be = d["t"] + pd.Timedelta(hours=1)
        close = d["close"].to_numpy(dtype=float)
        lr = np.full(len(close), np.nan)
        lr[1:] = np.log(close[1:] / close[:-1])
        out[s] = pd.DataFrame({"close": close, "logret": lr}, index=be)
        out[s].index.name = "bar_end"
    return out


def load_funding() -> dict[str, pd.DataFrame]:
    out = {}
    for s in MAJORS:
        df = pd.read_parquet(PREM / f"{s}_funding.parquet")
        df["calc_time"] = pd.to_datetime(df["calc_time"], utc=True)
        out[s] = df.sort_values("calc_time").reset_index(drop=True)
    return out


def fund7_at(fund, queries: pd.DatetimeIndex) -> pd.DataFrame:
    """Per-coin mean funding over [T-7d, T); NaN unless exactly 21 settlements."""
    q = queries.sort_values().unique()
    qns = q.values.astype("datetime64[ns]").astype(np.int64)
    wns = (q - D7).values.astype("datetime64[ns]").astype(np.int64)
    per = {}
    for s in MAJORS:
        df = fund[s]
        tns = df["calc_time"].values.astype("datetime64[ns]").astype(np.int64)
        r = df["last_funding_rate"].to_numpy(dtype=float)
        lo = np.searchsorted(tns, wns, side="left")
        hi = np.searchsorted(tns, qns, side="left")
        cs = np.concatenate([[0.0], np.cumsum(r)])
        v = np.full(len(q), np.nan)
        ok = (hi - lo) == 21
        v[ok] = (cs[hi[ok]] - cs[lo[ok]]) / 21.0
        per[s] = pd.Series(v, index=q).reindex(queries)
    return pd.DataFrame(per, index=queries)


def book_episodes_pooled() -> pd.DataFrame:
    """Book episodes (exact compute_kpi loop) per shift, pooled: exit_t, win."""
    rows = []
    for s in range(4):
        ev = pd.read_parquet(OCKPI / f"events_s{s}.parquet",
                              columns=["t", "symbol", "kind", "side", "price", "weight"])
        ev["t"] = pd.to_datetime(ev["t"], utc=True)
        ev = ev.sort_values("t").reset_index(drop=True)
        pos = {}
        for e in ev.itertuples():
            k, sym = e.kind, e.symbol
            if k == "book_fill":
                qq = abs(e.weight) / e.price
                pos[sym] = dict(side=1 if e.side == "buy" else -1, qty=qq,
                                 cost=qq * e.price, proceeds=0.0,
                                 fees=qq * e.price * MAKER)
                continue
            o = pos.get(sym)
            if o is None:
                continue
            if k == "book_add":
                qq = abs(e.weight) / e.price
                o["qty"] += qq
                o["cost"] += qq * e.price
                o["fees"] += qq * e.price * MAKER
            elif k in ("book_reduce", "book_partial"):
                qq = min(abs(e.weight) / e.price, o["qty"])
                o["qty"] -= qq
                o["proceeds"] += qq * e.price
                o["fees"] += qq * e.price * MAKER
            elif k in ("book_stop", "book_tp", "book_close"):
                o["proceeds"] += o["qty"] * e.price
                o["fees"] += o["qty"] * e.price * (TAKER if k == "book_stop" else MAKER)
                net = (o["side"] * (o["proceeds"] - o["cost"]) - o["fees"]) / o["cost"]
                rows.append((pd.Timestamp(e.t), float(net) > 0))
                pos.pop(sym, None)
    df = pd.DataFrame(rows, columns=["exit_t", "win"]).sort_values("exit_t").reset_index(drop=True)
    return df


def load_strategy_events():
    fills, exits = [], []
    for s in range(4):
        ev = pd.read_parquet(OCKPI / f"events_s{s}.parquet", columns=["t", "kind"])
        ev["t"] = pd.to_datetime(ev["t"], utc=True)
        fills.append(ev.loc[ev["kind"] == "rung_fill", "t"])
        exits.append(ev.loc[ev["kind"].isin(("rung_sl", "rung_tp", "rung_timeout")),
                            ["t", "kind"]])
    fills = pd.to_datetime(pd.concat(fills)).sort_values().reset_index(drop=True)
    exits = pd.concat(exits).sort_values("t").reset_index(drop=True)
    exits["is_tp"] = (exits["kind"] == "rung_tp").to_numpy(dtype=float)
    return fills, exits


class Stats:
    """Precomputed causal panels; stat_at(T) uses only data strictly < T."""

    def __init__(self, px, fund, fills, exits, book, fund_lookup=None):
        self.px = px
        self.fund = fund
        self.fund_lookup = fund_lookup  # DataFrame indexed by T -> per-coin fund7
        self.fill_ns = fills.values.astype("datetime64[ns]").astype(np.int64)
        ex = exits.sort_values("t").reset_index(drop=True)
        self.exit_ns = ex["t"].values.astype("datetime64[ns]").astype(np.int64)
        self.exit_tp_cs = np.concatenate([[0.0], np.cumsum(ex["is_tp"].to_numpy())])
        self.book_ns = book["exit_t"].values.astype("datetime64[ns]").astype(np.int64)
        self.book_win_cs = np.concatenate([[0.0], np.cumsum(book["win"].to_numpy(dtype=float))])
        # hourly-derived panels per coin
        self.be = {}
        self.close = {}
        self.rv = {}
        self.ma200 = {}
        for s in MAJORS:
            d = px[s].sort_index()
            be = d.index.values.astype("datetime64[ns]").astype(np.int64)
            cl = d["close"].to_numpy()
            lr = d["logret"].to_numpy()
            rv = pd.Series(lr).rolling(720, min_periods=720).std(ddof=1).to_numpy() * ANN
            ma = pd.Series(cl).rolling(4800, min_periods=4800).mean().shift(1).to_numpy()
            self.be[s] = be
            self.close[s] = cl
            self.rv[s] = rv
            self.ma200[s] = ma

    def _pos(self, s, t_ns, side="right"):
        be = self.be[s]
        if side == "right":
            # last bar-end <= T  -> searchsorted right - 1
            return int(np.searchsorted(be, t_ns, side="right")) - 1
        # last bar-end < T
        return int(np.searchsorted(be, t_ns, side="left")) - 1

    def close_at(self, s, T) -> float:
        t_ns = pd.Timestamp(T).value
        i = self._pos(s, t_ns)
        if i < 0:
            return np.nan
        return float(self.close[s][i])

    def rv_at(self, s, T) -> float:
        t_ns = pd.Timestamp(T).value
        i = self._pos(s, t_ns)
        if i < 0:
            return np.nan
        v = self.rv[s][i]
        return float(v) if np.isfinite(v) else np.nan

    def ma_at(self, s, T) -> float:
        t_ns = pd.Timestamp(T).value
        i = self._pos(s, t_ns)
        if i < 0:
            return np.nan
        v = self.ma200[s][i]
        return float(v) if np.isfinite(v) else np.nan

    def stat_at(self, T) -> dict:
        T = pd.Timestamp(T).tz_convert("UTC") if pd.Timestamp(T).tzinfo is not None \
            else pd.Timestamp(T).tz_localize("UTC")
        out: dict[str, float] = {}
        if self.fund_lookup is not None and T in self.fund_lookup.index:
            frow = self.fund_lookup.loc[T]
        else:
            frow = fund7_at(self.fund, pd.DatetimeIndex([T])).iloc[0]
        for s in MAJORS:
            out[f"fund7_{s}"] = float(frow[s]) if np.isfinite(frow[s]) else np.nan
        mkt_f = [out[f"fund7_{s}"] for s in MAJORS]
        out["fund7_mkt"] = float(np.mean(mkt_f)) if all(np.isfinite(mkt_f)) else np.nan
        for s in MAJORS:
            out[f"rv30_{s}"] = self.rv_at(s, T)
            r0 = self.rv_at(s, T)
            r1 = self.rv_at(s, T - D30)
            out[f"d_rv30_{s}"] = r0 - r1 if np.isfinite(r0) and np.isfinite(r1) else np.nan
            c0, c1 = self.close_at(s, T), self.close_at(s, T - D90)
            out[f"trend90_{s}"] = float(np.log(c0 / c1)) if np.isfinite(c0) and np.isfinite(c1) and c1 > 0 else np.nan
        for pre in ("rv30", "d_rv30", "trend90"):
            vv = [out[f"{pre}_{s}"] for s in MAJORS]
            out[f"{pre}_mkt"] = float(np.mean(vv)) if all(np.isfinite(vv)) else np.nan
        br = []
        for s in MAJORS:
            c0, m0 = self.close_at(s, T), self.ma_at(s, T)
            br.append(1.0 if np.isfinite(c0) and np.isfinite(m0) and c0 > m0 else
                      (0.0 if np.isfinite(c0) and np.isfinite(m0) else np.nan))
        out["breadth"] = float(np.mean(br)) if all(np.isfinite(br)) else np.nan
        tns = T.value
        wns = (T - D30).value
        lo = int(np.searchsorted(self.fill_ns, wns, side="right"))
        hi = int(np.searchsorted(self.fill_ns, tns, side="right"))
        out["dip_fill30"] = float(hi - lo) / 30.0
        elo = int(np.searchsorted(self.exit_ns, wns, side="right"))
        ehi = int(np.searchsorted(self.exit_ns, tns, side="right"))
        n_ex = ehi - elo
        out["dip_tp_share30"] = float((self.exit_tp_cs[ehi] - self.exit_tp_cs[elo]) / n_ex) \
            if n_ex >= 10 else np.nan
        blo = int(np.searchsorted(self.book_ns, wns, side="right"))
        bhi = int(np.searchsorted(self.book_ns, tns, side="right"))
        n_b = bhi - blo
        out["book_win30"] = float((self.book_win_cs[bhi] - self.book_win_cs[blo]) / n_b) \
            if n_b >= 10 else np.nan
        bnb0, bnb1 = self.close_at("BNBUSDT", T), self.close_at("BNBUSDT", T - D30)
        btc0, btc1 = self.close_at("BTCUSDT", T), self.close_at("BTCUSDT", T - D30)
        out["bnb_rs30"] = float(np.log(bnb0 / bnb1) - np.log(btc0 / btc1)) \
            if all(np.isfinite([bnb0, bnb1, btc0, btc1])) and min(bnb1, btc1) > 0 else np.nan
        B0, B1 = self.close_at("BNBUSDT", T), self.close_at("BNBUSDT", T - D90)
        C0, C1 = self.close_at("BTCUSDT", T), self.close_at("BTCUSDT", T - D90)
        out["bnb_rs90"] = float(np.log(B0 / B1) - np.log(C0 / C1)) \
            if all(np.isfinite([B0, B1, C0, C1])) and min(B1, C1) > 0 else np.nan
        return out


STAT_ORDER = ([f"fund7_{s}" for s in MAJORS] + ["fund7_mkt"] +
              [f"rv30_{s}" for s in MAJORS] + ["rv30_mkt"] +
              [f"d_rv30_{s}" for s in MAJORS] + ["d_rv30_mkt"] +
              [f"trend90_{s}" for s in MAJORS] + ["trend90_mkt"] +
              ["breadth", "dip_fill30", "dip_tp_share30", "book_win30",
               "bnb_rs30", "bnb_rs90"])


def main():
    mix4 = json.loads(MIX4P.read_text())
    peaks = [e["peak"] for e in mix4["reset_episodes"]]
    assert len(peaks) == 4, peaks
    grind_peak_g2 = json.loads(MIXG2.read_text())["reset_episodes"][0]["peak"]
    assert peaks[0] == grind_peak_g2, (peaks[0], grind_peak_g2)
    eps = [("E0_grind", peaks[0]), ("E1", peaks[1]), ("E2_flash", peaks[2]), ("E3", peaks[3])]
    ep_T = [(k, pd.Timestamp(p, tz="UTC")) for k, p in eps]

    px = load_hourly()
    fund = load_funding()
    fills, exits = load_strategy_events()
    book = book_episodes_pooled()

    grid = pd.date_range(GRID_START, GRID_END, freq="4h", tz="UTC")
    grid = grid[grid > GRID_START]
    assert grid.max() == GRID_END and (grid.hour % 4 == 0).all()

    # funding once, vectorised, for grid + episode starts
    allq = pd.DatetimeIndex(sorted(set(grid) | {T for _, T in ep_T}))
    fund_all = fund7_at(fund, allq)
    st = Stats(px, fund, fills, exits, book, fund_lookup=fund_all)

    bg = {s: [] for s in STAT_ORDER}
    for T in grid:
        r = st.stat_at(T)
        for s in STAT_ORDER:
            bg[s].append(r[s])
    bg = {s: np.array(v, dtype=float) for s, v in bg.items()}

    ep_vals = {}
    for k, T in ep_T:
        ep_vals[k] = st.stat_at(T)

    stats = []
    for s in STAT_ORDER:
        valid = bg[s][np.isfinite(bg[s])]
        row = {"name": s, "valid_n": int(len(valid)), "episodes": {}}
        sl = []
        for k, _ in ep_T:
            v = float(ep_vals[k][s])
            if np.isfinite(v) and len(valid):
                pct = float(100.0 * np.mean(valid <= v))
            else:
                pct = float("nan")
            row["episodes"][k] = {"value": v, "pct": pct}
            sl.append(pct)
        ext = [(k, p) for (k, _), p in zip(ep_T, sl) if np.isfinite(p) and (p <= 5 or p >= 95)]
        tails = set("lo" if p <= 5 else "hi" for _, p in ext)
        row["n_extreme"] = len(ext)
        row["extreme_episodes"] = [k for k, _ in ext]
        row["same_tail"] = len(tails) == 1 if ext else False
        row["tail"] = next(iter(tails)) if len(tails) == 1 else None
        row["hypothesis"] = bool(len(ext) >= 3 and len(tails) == 1)
        stats.append(row)

    out = {
        "meta": {
            "episodes": [{"id": k, "peak": str(T)} for k, T in ep_T],
            "grid": {"start": str(GRID_START), "end": str(GRID_END), "freq": "4h",
                     "n": int(len(grid))},
            "sources": {
                "hourly": "research/tournament/ext/hourly_ext.parquet",
                "funding": "data/raw/binance_premium_20260928/*_funding.parquet",
                "events": "research/tournament/oc_kpi/events_s{0..3}.parquet",
                "episodes": "research/tournament/oc_ddanat4p/mix_episodes.json",
            },
            "causality": ("hourly closes with bar-end <= T; funding settlements "
                          "calc_time in [T-7d,T) exactly 21 else NaN; strategy "
                          "events t in (T-30d,T]; book episodes exit in window, "
                          "v213 loop, maker 0.0002/taker 0.00055"),
            "extreme_rule": "pct<=5 or pct>=95 vs all valid 4h grid bars; "
                            "hypothesis iff >=3 of 4 episodes extreme same tail",
        },
        "stats": stats,
        "checks": {
            "peaks_match_ddanat4p": peaks,
            "grind_peak_matches_ddanat_g2": grind_peak_g2,
            "n_book_episodes_pooled": int(len(book)),
            "n_rung_fills_pooled": int(len(fills)),
        },
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    hyps = [r["name"] for r in stats if r["hypothesis"]]
    print("episodes:", [(k, str(T)) for k, T in ep_T], flush=True)
    print("grid_n:", len(grid), flush=True)
    print("hypotheses(n_extreme>=3 same tail):", hyps, flush=True)
    for r in stats:
        if r["n_extreme"] >= 2:
            print(r["name"], r["n_extreme"], r["tail"],
                  {k: round(v["pct"], 1) for k, v in r["episodes"].items()}, flush=True)


if __name__ == "__main__":
    main()
