"""oc_postflush: post-flush recovery book overlay (idea #30).

Frozen PLAN.md definitions. LIGHT: hourly panel + 1m one coin at a time.
Causality: event at C=T+4h uses only hourly bars in [T,T+4h) and sigma4 from
opens strictly before T; entry at C+5min open, exit at C+4h open.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import harness5 as H5

OUT = ROOT / "research" / "tournament" / "oc_postflush"
HOURLY = H5.HOURLY
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
ANCHORS = H5.ANCHORS  # 2021-09-24 .. 2025-09-24 UTC
DEV_END = pd.Timestamp("2026-09-24", tz="UTC")
GRID0 = pd.Timestamp("2020-08-01", tz="UTC")
MAKER, TAKER, FUND = 0.0002, 0.00055, 0.0001


def one_m_files(sym: str):
    if sym == "BTCUSDT":
        pat = "klines_1m_*.parquet"
        base = ROOT / "data" / "raw" / "btc_intraday_20260924"
    else:
        pat = f"{sym}_1m_*.parquet"
        base = ROOT / "data" / "raw" / "majors_intraday_20260924"
    return sorted(base.glob(pat))


def load_1m_open(sym: str) -> pd.Series:
    """1m OPEN indexed by open_time (UTC), strictly < DEV_END. One coin."""
    frames = []
    for f in one_m_files(sym):
        d = pd.read_parquet(f, columns=["open_time", "open"])
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        d = d[d["open_time"] < DEV_END]
        frames.append(d)
    m = pd.concat(frames, ignore_index=True).drop_duplicates("open_time")
    m = m.sort_values("open_time")
    return pd.Series(m["open"].to_numpy(float), index=pd.DatetimeIndex(m["open_time"]))


def build_4h(h: pd.DataFrame) -> dict:
    """Per coin: DataFrame indexed by 4h open T with O, L, Cc. Hourly only."""
    grid = pd.date_range(GRID0, DEV_END - pd.Timedelta(hours=4), freq="4h", tz="UTC")
    out = {}
    for s in MAJORS:
        hs = h[h["sym"] == s].sort_values("t").reset_index(drop=True)
        o_map = dict(zip(hs["t"], hs["open"].to_numpy(float)))
        c_map = dict(zip(hs["t"], hs["close"].to_numpy(float)))
        l_map = dict(zip(hs["t"], hs["low"].to_numpy(float)))
        O = np.array([o_map.get(t, np.nan) for t in grid], float)
        Cc = np.array([c_map.get(t + pd.Timedelta(hours=3), np.nan) for t in grid], float)
        L = np.full(len(grid), np.nan)
        for i, t in enumerate(grid):
            vals = [l_map.get(t + pd.Timedelta(hours=k), np.nan) for k in range(4)]
            if all(np.isfinite(vals)):
                L[i] = min(vals)
        df = pd.DataFrame({"O": O, "L": L, "Cc": Cc}, index=grid)
        o = df["O"]
        pc = o / o.shift(1) - 1
        df["sigma4"] = pc.rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy(float)
        out[s] = df
    return out


def detect_events(p4: dict) -> pd.DataFrame:
    grid = next(iter(p4.values())).index
    rows = []
    for t in grid:
        rec = []
        for s in MAJORS:
            r = p4[s].loc[t]
            O, L, Cc, sg = r["O"], r["L"], r["Cc"], r["sigma4"]
            if not (np.isfinite(O) and np.isfinite(L) and np.isfinite(Cc)
                    and np.isfinite(sg) and sg > 0 and O > 0):
                continue
            if L < O * (1 - 2.5 * sg) and Cc > O * (1 - 1.0 * sg):
                rec.append(s)
        if len(rec) >= 3:
            rows.append({"T": t, "C": t + pd.Timedelta(hours=4),
                         "coins": "+".join(rec), "n_coins": len(rec)})
    return pd.DataFrame(rows)


def price_legs(events: pd.DataFrame) -> pd.DataFrame:
    """Add entry/exit prices per recovered coin (1m, one coin at a time)."""
    ev = events.copy()
    for s in MAJORS:
        ev[f"in_{s}"] = np.nan
        ev[f"out_{s}"] = np.nan
    for s in MAJORS:
        px = load_1m_open(s)
        idx = px.index
        need = ev["coins"].str.split("+").apply(lambda lst: s in lst)
        if not need.any():
            del px
            continue
        t_in = pd.DatetimeIndex(ev.loc[need, "C"] + pd.Timedelta(minutes=5))
        t_out = pd.DatetimeIndex(ev.loc[need, "C"] + pd.Timedelta(hours=4))
        pos_in = idx.get_indexer(t_in)  # exact match required
        pos_out = idx.get_indexer(t_out)
        arr = px.to_numpy(float)
        v_in = np.where(pos_in >= 0, arr[np.maximum(pos_in, 0)], np.nan)
        v_out = np.where(pos_out >= 0, arr[np.maximum(pos_out, 0)], np.nan)
        v_in[pos_in < 0] = np.nan
        v_out[pos_out < 0] = np.nan
        ev.loc[need, f"in_{s}"] = v_in
        ev.loc[need, f"out_{s}"] = v_out
        del px, arr
    return ev


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    h = pd.read_parquet(HOURLY, columns=["t", "open", "high", "low", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    h = h[(h["sym"].isin(MAJORS)) & (h["t"] < DEV_END)].reset_index(drop=True)

    p4 = build_4h(h)
    events = detect_events(p4)
    events = events[(events["C"] >= ANCHORS[0])
                    & (events["C"] < ANCHORS[-1] + pd.Timedelta(days=365))].reset_index(drop=True)
    # exit must be within data: C+4h <= DEV_END
    events = events[(events["C"] + pd.Timedelta(hours=4) <= DEV_END)].reset_index(drop=True)
    n_raw = len(events)

    ev = price_legs(events)
    # strict: every recovered coin priced; funding by exit hour
    R, ok, legs = [], [], []
    for _, r in ev.iterrows():
        coins = r["coins"].split("+")
        ins = np.array([r[f"in_{s}"] for s in coins], float)
        outs = np.array([r[f"out_{s}"] for s in coins], float)
        if not (np.all(np.isfinite(ins)) and np.all(np.isfinite(outs))
                and np.all(ins > 0) and np.all(outs > 0)):
            ok.append(False)
            R.append(np.nan)
            legs.append({})
            continue
        ex = r["C"] + pd.Timedelta(hours=4)
        fund = FUND if ex.hour in (0, 8, 16) else 0.0
        lr = outs / ins - 1 - MAKER - TAKER - fund
        ok.append(True)
        R.append(float(lr.mean()))
        legs.append({s: float(v) for s, v in zip(coins, lr)})
    ev["R"] = np.array(R, float)
    ev["valid"] = np.array(ok, bool)
    n_dropped = int((~ev["valid"]).sum())
    valid = ev[ev["valid"]].reset_index(drop=True)
    valid.to_parquet(OUT / "events_postflush.parquet")

    # dip daily (harness5 exact, as oc_idea7)
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    is_r2 = d["sym"].isin(MAJORS) & d["k"].isin(H5.R2) & d["size_dep"].notna()
    dd = d[is_r2].copy()
    dd["day"] = dd["T"].dt.floor("D")
    dip_day = dd.groupby("day").apply(lambda g: float((g["size_dep"] * g["y_dep"]).sum()),
                                      include_groups=False)

    years, loyo = [], []
    for k, a0 in enumerate(ANCHORS):
        a1 = a0 + pd.Timedelta(days=365)
        sub = valid[(valid["C"] >= a0) & (valid["C"] < a1)].reset_index(drop=True)
        r = sub["R"].to_numpy(float)
        n = len(r)
        mean = float(r.mean()) if n else float("nan")
        med = float(np.median(r)) if n else float("nan")
        win = float((r > 0).mean()) if n else float("nan")
        sd = float(r.std(ddof=1)) if n >= 3 else float("nan")
        tstat = float(mean / (sd / np.sqrt(n))) if n >= 3 and sd > 0 else float("nan")
        if n:
            wi = int(r.argmin())
            worst = {"R": float(r[wi]), "C": str(sub.loc[wi, "C"]), "coins": sub.loc[wi, "coins"]}
        else:
            worst = {"R": float("nan"), "C": None, "coins": None}
        # daily correlation over calendar days of the year
        days = pd.date_range(a0.floor("D"), a1 - pd.Timedelta(days=1), freq="D", tz="UTC")
        ov = sub.groupby(sub["C"].dt.floor("D"))["R"].sum()
        x = np.array([float(ov.get(dday, 0.0)) for dday in days], float)
        y = np.array([float(dip_day.get(dday, 0.0)) for dday in days], float)
        if np.std(x) > 0 and np.std(y) > 0:
            corr = float(np.corrcoef(x, y)[0, 1])
        else:
            corr = float("nan")
        coins_hist = sub["coins"].str.split("+").explode()
        per_coin = {s: round(float(sub["coins"].str.contains(s).mean()), 3) if n else None
                    for s in MAJORS}
        years.append({
            "anchor": str(a0.date()), "n": n, "mean_net": mean, "mean_bps": mean * 1e4 if n else None,
            "median_net": med, "win_rate": win, "t_stat": tstat, "worst": worst,
            "total_net": float(r.sum()) if n else 0.0,
            "mean_coins": float(sub["n_coins"].mean()) if n else None,
            "coin_share": per_coin, "dip_corr_daily": corr, "n_days": len(days),
        })
    for hh in range(5):
        m = years[hh]["mean_net"]
        loyo.append({"heldout": years[hh]["anchor"],
                     "mean_heldout": m, "pass": bool(np.isfinite(m) and m > 0)})

    n_pos = sum(1 for y in years if np.isfinite(y["mean_net"]) and y["mean_net"] > 0)
    n_loyo = sum(1 for r_ in loyo if r_["pass"])
    min_n = min((y["n"] for y in years), default=0)
    promising = bool(n_pos >= 4 and n_loyo >= 4 and min_n >= 10)
    res = {
        "meta": {
            "hourly": str(HOURLY), "majors": MAJORS,
            "sigma4": "v293: std of 4h-open pct_change rolling 360 min_periods 120 shifted 1 (opens from hourly_ext)",
            "event": "bar T: >=3 majors with L < O*(1-2.5*sg) AND Cc > O*(1-1.0*sg); C=T+4h",
            "signal": "long recovered coins equal weight; entry 1m open C+5min maker 0.0002; exit 1m open C+4h taker 0.00055; funding 0.0001 if exit hour in {0,8,16}",
            "years": "by C in [A, A+365d), A=2021-09-24..2025-09-24; exits <= 2026-09-24",
            "dip_corr": "Pearson(sum R per C-day, sum size_dep*y_dep per T-day) over calendar days incl. zeros",
            "loyo_note": "parameter-free overlay: LOYO held-out mean == sequential year mean by construction",
            "n_raw_events": n_raw, "n_valid": len(valid), "n_dropped_incomplete": n_dropped,
            "costs": {"maker": MAKER, "taker": TAKER, "funding_long": FUND},
        },
        "years": years, "loyo": loyo,
        "decision": {
            "mean_pos_years": f"{n_pos}/5", "loyo_pass": f"{n_loyo}/5",
            "min_events_per_year": min_n, "events_ge_10_every_year": bool(min_n >= 10),
            "promising": promising,
        },
    }
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print(y["anchor"], "n", y["n"], "mean_bps",
              round(y["mean_bps"], 2) if y["mean_bps"] is not None else None,
              "win", round(y["win_rate"], 3) if y["win_rate"] == y["win_rate"] else None,
              "t", round(y["t_stat"], 2) if y["t_stat"] == y["t_stat"] else None,
              "corr", round(y["dip_corr_daily"], 3) if y["dip_corr_daily"] == y["dip_corr_daily"] else None)


if __name__ == "__main__":
    main()
