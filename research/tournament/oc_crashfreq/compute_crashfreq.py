"""oc_crashfreq: per-4h-bar dip crash census from oc_ddanat4p replicas (light, one process)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
SRC = HERE.parent / "oc_ddanat4p"
EXT = HERE.parent / "ext"

LIVE_LO = pd.Timestamp("2021-09-24 00:00", tz="UTC")
LIVE_HI = pd.Timestamp("2026-09-24 00:00", tz="UTC")
YEARS = [
    (pd.Timestamp("2021-09-24", tz="UTC"), pd.Timestamp("2022-09-24", tz="UTC")),
    (pd.Timestamp("2022-09-24", tz="UTC"), pd.Timestamp("2023-09-24", tz="UTC")),
    (pd.Timestamp("2023-09-24", tz="UTC"), pd.Timestamp("2024-09-24", tz="UTC")),
    (pd.Timestamp("2024-09-24", tz="UTC"), pd.Timestamp("2025-09-24", tz="UTC")),
    (pd.Timestamp("2025-09-24", tz="UTC"), pd.Timestamp("2026-09-24", tz="UTC")),
]


def bar_end_for(ts: pd.Timestamp, s: int) -> pd.Timestamp:
    h = ts.floor("h")
    if ts != h:
        h = h + pd.Timedelta(hours=1)
    while int(h.hour % 4) != int(s % 4):
        h = h + pd.Timedelta(hours=1)
    return h


def main() -> None:
    # --- load rungs per phase (tiny) ---
    rungs = {}
    for s in range(4):
        r = pd.read_parquet(SRC / f"rungs_s{s}.parquet")
        r["exit_t"] = pd.to_datetime(r["exit_t"], utc=True)
        r = r[(r["exit_t"] > LIVE_LO) & (r["exit_t"] <= LIVE_HI)].copy()
        r["bar_end"] = [bar_end_for(t, s) for t in r["exit_t"]]
        r = r[(r["bar_end"] > LIVE_LO) & (r["bar_end"] <= LIVE_HI)]
        rungs[s] = r

    # --- BTC hourly closes for 4h returns (causal, <= T) ---
    h = pd.read_parquet(EXT / "hourly_ext.parquet", columns=["t", "close", "sym"])
    h = h[h["sym"] == "BTCUSDT"].copy()
    h["t"] = pd.to_datetime(h["t"], utc=True)
    h = h[(h["t"] < LIVE_HI)].sort_values("t")
    cmap = dict(zip(h["t"], h["close"]))

    def btc_ret(t_end: pd.Timestamp):
        try:
            c1 = cmap.get(t_end - pd.Timedelta(hours=1))
            c0 = cmap.get(t_end - pd.Timedelta(hours=5))
            if c1 is None or c0 is None or not c0:
                return None
            return float(c1 / c0 - 1) * 100.0
        except Exception:
            return None

    # --- per-bar aggregation ---
    bars = {}  # (s, T) -> dict
    for s in range(4):
        r = rungs[s]
        for T, g in r.groupby("bar_end"):
            tot = float(g["loss"].sum()) * 100.0
            by = {}
            ct = {}
            for k in ("rung_sl", "rung_tp", "rung_timeout"):
                sub = g[g["exit"] == k]
                by[k] = round(float(sub["loss"].sum()) * 100.0, 3)
                ct[k] = int(len(sub))
            coins = {c: round(float(g[g["symbol"] == c]["loss"].sum()) * 100.0, 3)
                     for c in sorted(g["symbol"].unique())}
            bars[(s, pd.Timestamp(T))] = {
                "phase": s, "bar_end": pd.Timestamp(T),
                "dip_loss": tot, "by_kind": by, "counts": ct,
                "n_stops": int((g["exit"] == "rung_sl").sum()),
                "n_exits": int(len(g)), "per_coin": coins,
            }

    # --- events >= 3% ---
    events = [v for v in bars.values() if v["dip_loss"] <= -3.0]
    events.sort(key=lambda d: d["dip_loss"])

    # wall-clock coincidence + btc ret per event
    exit_ts = {s: pd.DatetimeIndex(pd.to_datetime(rungs[s]["exit_t"], utc=True)) for s in range(4)}
    exit_ls = {s: rungs[s]["loss"].values * 100.0 for s in range(4)}
    for e in events:
        T = e["bar_end"]
        lo = T - pd.Timedelta(hours=4)
        e["btc_r4h"] = None if btc_ret(T) is None else round(float(btc_ret(T)), 2)
        others = {}
        for p in range(4):
            if p == e["phase"]:
                continue
            ts = exit_ts[p]
            m = (ts > lo) & (ts <= T)
            w = float(exit_ls[p][m].sum()) if len(ts) else 0.0
            others[f"s{p}"] = round(w, 3)
        e["other_wall"] = others
        e["others_ge3"] = sorted([k for k, v in others.items() if v <= -3.0])

    # --- yearly counts ---
    yearly = []
    for i, (a, b) in enumerate(YEARS):
        row = {"year": f"{a.date()}..{b.date()}"}
        for thr in (3, 5, 10, 15):
            row[f"ge{thr}"] = int(sum(1 for e in events if a <= e["bar_end"] < b and e["dip_loss"] <= -thr))
        row["n"] = row["ge3"]
        yearly.append(row)

    # per-phase totals
    per_phase = {}
    for s in range(4):
        ev = [e for e in events if e["phase"] == s]
        per_phase[f"s{s}"] = {
            "ge3": sum(1 for e in ev if e["dip_loss"] <= -3),
            "ge5": sum(1 for e in ev if e["dip_loss"] <= -5),
            "ge10": sum(1 for e in ev if e["dip_loss"] <= -10),
            "ge15": sum(1 for e in ev if e["dip_loss"] <= -15),
        }

    # --- top15 + concentration ---
    top15 = events[:15]
    neg = [v["dip_loss"] for v in bars.values() if v["dip_loss"] < 0]
    sum_neg = float(sum(neg))
    order = sorted(neg)[:10]
    top10_sum = float(sum(order))
    frac = float(top10_sum / sum_neg) if sum_neg else 0.0

    # --- 2024-01-03-type (<=-15%) frequency ---
    big = [e for e in events if e["dip_loss"] <= -15.0]
    dates = sorted({e["bar_end"].date().isoformat() for e in big})
    n_phase_years = 4 * 5
    rate_per_phase_year = len(big) / n_phase_years if n_phase_years else 0.0
    rate_per_cal_year = len(big) / 5.0

    # bars scanned per phase (grid count)
    scanned = {}
    for s in range(4):
        # generate grid T in (LIVE_LO, LIVE_HI] with hour%4==s%4
        t = LIVE_LO + pd.Timedelta(hours=1)
        n = 0
        while t <= LIVE_HI:
            if int(t.hour % 4) == int(s % 4) and t.minute == 0 and t.second == 0:
                n += 1
            t += pd.Timedelta(hours=1)
        scanned[f"s{s}"] = n

    def ev_json(e):
        return {
            "bar_end": str(e["bar_end"]), "phase": e["phase"],
            "dip_loss": round(float(e["dip_loss"]), 3),
            "by_kind": e["by_kind"], "counts": e["counts"],
            "n_stops": e["n_stops"], "n_exits": e["n_exits"],
            "per_coin": e["per_coin"], "btc_r4h": e["btc_r4h"],
            "other_wall": e["other_wall"], "others_ge3": e["others_ge3"],
        }

    out = {
        "variant": "R2B1D17BF",
        "live": [str(LIVE_LO), str(LIVE_HI)],
        "definition": ("dip_loss(s,T)=100*sum(weight*ret) over rung exits with "
                       "exit_t in (T-4h,T]; phase grids hour%4==s%4; "
                       "btc_r4h from BTCUSDT hourly closes C(T-1h)/C(T-5h)-1; "
                       "other_wall = wall-clock (T-4h,T] rung sums per other phase."),
        "n_events_ge3": len(events),
        "events": [ev_json(e) for e in events],
        "yearly_counts": yearly,
        "per_phase": per_phase,
        "bars_scanned": scanned,
        "top15": [ev_json(e) for e in top15],
        "concentration": {
            "n_negative_bars": len(neg),
            "sum_negative_pp": round(sum_neg, 3),
            "top10_sum_pp": round(top10_sum, 3),
            "top10_fraction": round(frac, 4),
        },
        "type15": {
            "threshold": -15.0,
            "n_bars": len(big),
            "dates": dates,
            "bars": [ev_json(e) for e in big],
            "rate_per_phase_year": round(rate_per_phase_year, 4),
            "rate_per_calendar_year": round(rate_per_cal_year, 3),
        },
        "checks": {
            f"s{s}": {"n_rungs": int(len(rungs[s])),
                      "n_exit_bars": int(sum(1 for k in bars if k[0] == s))}
            for s in range(4)
        },
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"events_ge3={len(events)} sum_neg={sum_neg:.1f} top10_frac={frac:.3f} type15={len(big)}")
    print("wrote results.json")


if __name__ == "__main__":
    main()
