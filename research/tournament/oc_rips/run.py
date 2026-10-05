"""oc_rips run: event study of the rip-fade ladder, regime-conditional.

One heavy process, one coin in memory at a time (RAM < 2.5 GB).
Usage: .venv/Scripts/python.exe research/tournament/oc_rips/run.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OC = Path(__file__).parent
sys.path.insert(0, str(OC))
import backtest as B
import regimes as RG

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
RAW_BTC = ROOT / "data/raw/btc_intraday_20260924"
RAW_MAJ = ROOT / "data/raw/majors_intraday_20260924"
END = pd.Timestamp("2026-09-24", tz="UTC")
START = pd.Timestamp("2020-01-01", tz="UTC")
ANCHORS = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
RULES = ["UNCOND", "R1", "R2", "R3"]


def minute_files(sym: str):
    if sym == "BTCUSDT":
        return sorted(RAW_BTC.glob("klines_1m_*.parquet"))
    return sorted(RAW_MAJ.glob(f"{sym}_1m_*.parquet"))


def load_close_daily(sym: str) -> pd.Series:
    parts = [pd.read_parquet(f, columns=["open_time", "close"]) for f in minute_files(sym)]
    m = pd.concat(parts)
    return RG.daily_closes_from_minutes(m)


def load_ohlc(sym: str) -> pd.DataFrame:
    parts = [pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"])
             for f in minute_files(sym)]
    m = pd.concat(parts)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    return m[(m.index >= START) & (m.index < END)]


def gate(row: pd.Series, rule: str) -> bool:
    if rule == "UNCOND":
        return True
    if rule == "R1":
        return np.isfinite(row.get("below200", np.nan)) and row["below200"] == 1.0
    if rule == "R2":
        return (np.isfinite(row.get("trend90", np.nan)) and row["trend90"] < 0
                and np.isfinite(row.get("volratio", np.nan)) and row["volratio"] < 1.0)
    if rule == "R3":
        return np.isfinite(row.get("breadth50", np.nan)) and row["breadth50"] < 0.4
    raise ValueError(rule)


def summarize(nets: np.ndarray):
    nets = np.asarray(nets, dtype=float)
    if len(nets) == 0:
        return {"n": 0, "mean_bps": None, "win": None, "sum": 0.0}
    return {"n": int(len(nets)), "mean_bps": round(1e4 * float(nets.mean()), 2),
            "win": round(float((nets > 0).mean()), 4), "sum": round(float(nets.sum()), 4)}


def main():
    print("building daily panel...", flush=True)
    panel = {}
    for s in SYMS:
        panel[s] = load_close_daily(s)
        print("  daily", s, panel[s].index.min(), panel[s].index.max(), len(panel[s]), flush=True)
    daily = pd.DataFrame(panel).sort_index()
    daily = daily[(daily.index >= pd.Timestamp("2020-01-01", tz="UTC"))
                  & (daily.index < END)]
    print("building regimes...", flush=True)
    reg = RG.build_regimes(daily)
    reg.to_parquet(OC / "regimes_daily_oc_rips.parquet")
    cross = {}
    ref_path = ROOT / "research/tournament/oc_regime/regimes_daily.parquet"
    if ref_path.exists():
        ref = pd.read_parquet(ref_path)
        ref.index = pd.to_datetime(ref.index, utc=True)
        common = reg.index.intersection(ref.index)
        for v in ("trend90", "volratio", "breadth50"):
            a = reg.loc[common, v].astype(float)
            b = ref.loc[common, v].astype(float)
            m = a.notna() & b.notna()
            if int(m.sum()) > 0:
                d = (a[m] - b[m]).abs()
                cross[v] = {"n": int(m.sum()), "median_abs_diff": round(float(d.median()), 6),
                            "note": "breadth50 universe differs (5 majors vs 35 coins)" if v == "breadth50" else ""}
    print("regime coverage:", reg.index.min(), reg.index.max(), flush=True)
    print("cross-check vs oc_regime parquet:", json.dumps(cross), flush=True)

    gid = pd.date_range(START, END - pd.Timedelta(minutes=1), freq="1min", tz="UTC")
    is_bar = (np.asarray((gid - gid.floor("D")).total_seconds()) // 60 % 240 == 0)
    bar_pos_all = np.flatnonzero(is_bar)
    bar_time_all = gid[is_bar]

    all_rip, all_dip = [], []
    for s in SYMS:
        print("loading", s, flush=True)
        m = load_ohlc(s).reindex(gid)
        O = m["open"].to_numpy(dtype=float)
        H = m["high"].to_numpy(dtype=float)
        Lw = m["low"].to_numpy(dtype=float)
        C = m["close"].to_numpy(dtype=float)
        ok = np.flatnonzero(bar_pos_all + 240 <= len(O))
        bp, bt = bar_pos_all[ok], bar_time_all[ok]
        opens = O[bp]
        sig = B.sigma_from_bar_opens(opens)
        print(f"  {s}: {len(bp)} bars, sigma coverage {np.isfinite(sig).mean():.2f}", flush=True)
        for side, store in ((-1, all_rip), (1, all_dip)):
            evs = B.simulate_symbol(gid.to_numpy(), O, H, Lw, C, bp, bt.to_numpy(), sig, side)
            for e in evs:
                e["sym"] = s
            store.extend(evs)
            print(f"  {s} side={side}: {len(evs)} fills", flush=True)
        del m, O, H, Lw, C

    rip = pd.DataFrame(all_rip)
    dip = pd.DataFrame(all_dip)
    for df in (rip, dip):
        df["fill_time"] = pd.to_datetime(df["fill_time"], utc=True)
        df["bar_open"] = pd.to_datetime(df["bar_open"], utc=True)
        df["reg_day"] = df["bar_open"].dt.floor("D")
    regd = {d: r for d, r in zip(reg.index, reg.to_dict("records"))}
    for df in (rip, dip):
        df["trend90"] = df["reg_day"].map(lambda d: regd.get(d, {}).get("trend90", np.nan))
        df["below200"] = df["reg_day"].map(lambda d: regd.get(d, {}).get("below200", np.nan))
        df["volratio"] = df["reg_day"].map(lambda d: regd.get(d, {}).get("volratio", np.nan))
        df["breadth50"] = df["reg_day"].map(lambda d: regd.get(d, {}).get("breadth50", np.nan))

    def rule_frame(rule: str) -> pd.DataFrame:
        if rule == "DIP":
            return dip
        mask = rip.apply(lambda r: gate(r, rule), axis=1)
        return rip[mask]

    per_year, daily_pnl = {}, {}
    for rule in RULES + ["DIP"]:
        df = rule_frame(rule)
        per_year[rule] = {}
        for A in ANCHORS:
            a = pd.Timestamp(A, tz="UTC")
            b = a + pd.Timedelta(days=365)
            sub = df[(df["fill_time"] >= a) & (df["fill_time"] < b)]
            per_year[rule][A] = {**summarize(sub["net"].to_numpy() if len(sub) else np.array([])),
                                 "stops": int((sub["how"] == "stop").sum()) if len(sub) else 0,
                                 "tps": int((sub["how"] == "tp").sum()) if len(sub) else 0}
        g = df[(df["fill_time"] >= pd.Timestamp(ANCHORS[0], tz="UTC"))
               & (df["fill_time"] < pd.Timestamp(ANCHORS[-1], tz="UTC") + pd.Timedelta(days=365))]
        dsum = g.groupby(g["fill_time"].dt.floor("D"))["net"].sum() if len(g) else pd.Series(dtype=float)
        days = pd.date_range(ANCHORS[0], "2026-09-24", freq="D", tz="UTC", inclusive="left")
        dsum = dsum.reindex(days, fill_value=0.0)
        daily_pnl[rule] = dsum
        cum = dsum.cumsum()
        dd = float((cum.cummax() - cum).max())
        per_year[rule]["_5y"] = {**summarize(g["net"].to_numpy() if len(g) else np.array([])), "dd": round(dd, 4)}

    dip_dd = per_year["DIP"]["_5y"]["dd"]
    decision = {}
    for rule in RULES:
        means = [per_year[rule][A]["mean_bps"] for A in ANCHORS]
        ok_years = sum(1 for v in means if v is not None and v > 5.0)
        sum5 = per_year[rule]["_5y"]["sum"]
        dd = per_year[rule]["_5y"]["dd"]
        reasons = []
        if not (ok_years >= 4):
            reasons.append(f"only {ok_years}/5 years > +5bps")
        if not (sum5 > 0):
            reasons.append("5y sum not positive")
        if not (dip_dd > 0 and dd < 2 * dip_dd):
            reasons.append(f"DD {dd} not < 2x dip DD {dip_dd}")
        decision[rule] = {"promising": len(reasons) == 0, "ok_years": ok_years,
                          "sum5": sum5, "dd": dd, "dip_dd": dip_dd,
                          "reasons": reasons if reasons else ["all three gates pass"]}

    loyo = {}
    for rule in RULES:
        df = rule_frame(rule)
        row = {}
        for h in ANCHORS:
            a = pd.Timestamp(h, tz="UTC")
            b = a + pd.Timedelta(days=365)
            held = df[(df["fill_time"] >= a) & (df["fill_time"] < b)]["net"].to_numpy()
            rest = df[~((df["fill_time"] >= a) & (df["fill_time"] < b))]
            rest = rest[(rest["fill_time"] >= pd.Timestamp(ANCHORS[0], tz="UTC"))
                        & (rest["fill_time"] < pd.Timestamp(ANCHORS[-1], tz="UTC") + pd.Timedelta(days=365))]
            rest = rest["net"].to_numpy()
            mh = float(held.mean()) if len(held) else float("nan")
            mr = float(rest.mean()) if len(rest) else float("nan")
            row[h] = {"mean_held_bps": round(1e4 * mh, 2) if np.isfinite(mh) else None,
                      "mean_rest_bps": round(1e4 * mr, 2) if np.isfinite(mr) else None,
                      "sign_match": bool(np.sign(mh) == np.sign(mr)) if np.isfinite(mh) and np.isfinite(mr) and mh != 0 and mr != 0 else False,
                      "n_held": int(len(held))}
        row["_matches"] = sum(1 for h in ANCHORS if row[h]["sign_match"])
        loyo[rule] = row

    corr = {}
    for rule in RULES:
        x, y = daily_pnl[rule].to_numpy(), daily_pnl["DIP"].to_numpy()
        corr[rule] = round(float(np.corrcoef(x, y)[0, 1]), 4) if x.std() > 0 and y.std() > 0 else None

    results = {
        "meta": {
            "coins": SYMS, "ks": list(B.KS), "grid": "4h standard (00,04,...,20 UTC)",
            "live_window": [B.LIVE_A, B.LIVE_B], "fill": "strict trade-through at level, maker 0.0002",
            "tp": "1 sigma, maker", "stop_close": "5-min-block close beyond 4 sigma, exit next open, taker",
            "backstop": "touch 8 sigma, exit max(bs,open) shorts / min(bs,open) longs, taker",
            "timeout": "next bar open, taker", "funding": "none (shorts pay nothing; holds <4h)",
            "same_minute": "stop-first", "sigma": "std of 4h open-to-open simple returns, 360 bars, min 120",
            "regimes": "daily, data strictly before day start; breadth50 over 5 majors",
            "rules": {"R1": "below200", "R2": "trend90<0 and volratio<1", "R3": "breadth50<0.4"},
            "anchors": ANCHORS, "data_end": "2026-09-24T00:00Z",
            "n_rip_fills_5y": int(len(rip[(rip['fill_time'] >= ANCHORS[0])])),
            "n_dip_fills_5y": int(len(dip[(dip['fill_time'] >= ANCHORS[0])])),
            "crosscheck_vs_oc_regime": cross,
        },
        "per_rule_per_year": per_year,
        "loyo_sign": loyo,
        "corr_daily_vs_dip": corr,
        "decision": decision,
    }
    (OC / "results.json").write_text(json.dumps(results, indent=1))
    print(json.dumps({r: {a: per_year[r][a] for a in ANCHORS} for r in RULES + ["DIP"]}, indent=1))
    print("corr vs dip:", corr)
    print("decision:", json.dumps(decision, indent=1))
    print("LOYO:", json.dumps({r: loyo[r]["_matches"] for r in RULES}))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
