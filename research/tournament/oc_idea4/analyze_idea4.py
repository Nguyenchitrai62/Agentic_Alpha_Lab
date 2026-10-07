"""oc_idea4: funding-surprise dip filter (IDEAS.md #4).

Per PLAN.md (pre-registered): V1 surprise = settled(S) - 60m premium TWAP(S)
per coin; V2 = settled(S) - settled(S_prev). At bar open T use the last
settlement S < T (strict). Per-coin walk-forward p80 from strictly previous
dip rows (>= 100 rows else never flag). SKIP flagged rows; 5 anchor years +
LOYO; worst-day tail bar.

Single process; loads only *_funding.parquet + *_premium_1m.parquet (close
column, one coin at a time) + fills_U_ext.parquet. No intraday klines.

  python research/tournament/oc_idea4/analyze_idea4.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
PREM = ROOT / "data/raw/binance_premium_20260928"
FILLS = ROOT / "research/tournament/ext/fills_U_ext.parquet"

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
DEPTHS = [2.5, 3.0, 3.5, 4.0, 5.0]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MIN_TRAIN_COIN = 100
MIN_SIDE = 10
PREM_WIN = 60  # minutes of premium TWAP before each settlement
PREM_MIN_BARS = 30


def load_funding() -> dict[str, pd.DataFrame]:
    out = {}
    for s in MAJORS:
        df = pd.read_parquet(PREM / f"{s}_funding.parquet")
        df["calc_time"] = pd.to_datetime(df["calc_time"], utc=True)
        out[s] = df.sort_values("calc_time").reset_index(drop=True)
    return out


def settlement_surprises(fund: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Per-coin settlement table: S, settled, P (60m premium TWAP), s1, s2.

    P(S) = mean premium close over bars with open_time in
    [S_floor - 60m, S_floor - 1m]; >= 30 bars else NaN. Premium bars at/after
    the 2026-09-24 cutoff are never loaded into the window.
    """
    tabs = {}
    for s in MAJORS:
        f = fund[s]
        S = pd.to_datetime(f["calc_time"], utc=True)
        settled = f["last_funding_rate"].to_numpy(dtype=float)
        Sf = S.dt.floor("min")
        p = pd.read_parquet(PREM / f"{s}_premium_1m.parquet", columns=["open_time", "close"])
        p["open_time"] = pd.to_datetime(p["open_time"], utc=True)
        p = p[p["open_time"] < CUTOFF].sort_values("open_time").reset_index(drop=True)
        t = p["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
        c = p["close"].to_numpy(dtype=float)
        del p
        q = Sf.to_numpy(dtype="datetime64[ns]").astype(np.int64)
        lo = np.searchsorted(t, q - PREM_WIN * 60_000_000_000, side="left")
        hi = np.searchsorted(t, q, side="left")  # open_time < S_floor
        P = np.full(len(q), np.nan)
        for i in range(len(q)):
            n = hi[i] - lo[i]
            if n >= PREM_MIN_BARS:
                P[i] = float(np.mean(c[lo[i]:hi[i]]))
        s1 = settled - P
        s2 = np.full(len(q), np.nan)
        s2[1:] = settled[1:] - settled[:-1]
        tabs[s] = pd.DataFrame({"S": S, "settled": settled, "P": P, "s1": s1, "s2": s2})
    return tabs


def surprise_at_T(tabs: dict[str, pd.DataFrame], coin: str, T: pd.DatetimeIndex,
                  col: str) -> np.ndarray:
    """Last settlement S < T (strict) mapped to each T; NaN if none."""
    tab = tabs[coin]
    Sns = tab["S"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    v = tab[col].to_numpy(dtype=float)
    q = T.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    j = np.searchsorted(Sns, q, side="left") - 1
    out = np.full(len(q), np.nan)
    ok = j >= 0
    out[ok] = v[j[ok]]
    return out


def year_stats(yy: pd.DataFrame, flag: np.ndarray) -> dict:
    y = yy["y1.0"].to_numpy(dtype=float)
    fl = flag.astype(bool)
    n = len(y)
    n_flag, n_kept = int(fl.sum()), int(n - fl.sum())
    row = {"n": n, "n_flag": n_flag, "n_kept": n_kept,
           "retention": round(n_kept / n, 4) if n else None}
    for name, m in (("flagged", fl), ("kept", ~fl)):
        v = y[m]
        row[name] = {"mean_bps": round(float(v.mean() * 1e4), 2) if len(v) else None,
                     "win": round(float((v > 0).mean()), 4) if len(v) else None,
                     "min_bps": round(float(v.min() * 1e4), 1) if len(v) else None,
                     "n": int(len(v))}
    if n_flag >= MIN_SIDE and n_kept >= MIN_SIDE:
        row["spread_bps"] = round(float(y[fl].mean() - y[~fl].mean()) * 1e4, 2)
    else:
        row["spread_bps"] = None
    S_full = float(y.sum())
    S_skip = float(y[~fl].sum())
    S_flag = float(y[fl].sum())
    row["S_full"] = round(S_full, 4)
    row["S_skip"] = round(S_skip, 4)
    row["S_half"] = round(S_skip + 0.5 * S_flag, 4)
    row["cut"] = round((S_full - S_skip) / S_full, 4) if S_full > 0 else None
    day = yy["T"].dt.floor("D").to_numpy()
    w_full = float(pd.Series(y).groupby(day).sum().min())
    w_skip = float(pd.Series(y[~fl]).groupby(day[~fl]).sum().min()) if n_kept else None
    row["worst_day_full"] = round(w_full, 4)
    row["worst_day_skip"] = round(w_skip, 4) if w_skip is not None else None
    row["tail_improves"] = bool(w_skip is not None and w_skip > w_full)
    return row


def main() -> None:
    fund = load_funding()
    fspan = {s: (str(d["calc_time"].min()), str(d["calc_time"].max()), len(d))
             for s, d in fund.items()}
    tabs = settlement_surprises(fund)

    fills = pd.read_parquet(FILLS)
    fills["T"] = pd.to_datetime(fills["t_fill"], utc=True) - pd.to_timedelta(fills["f"], unit="m")
    m = fills["sym"].isin(MAJORS) & fills["x1"].isin(DEPTHS)
    d = fills[m].copy().sort_values("T").reset_index(drop=True)
    assert (d["T"] < CUTOFF).all()
    for col in ("s1", "s2"):
        vals = np.full(len(d), np.nan)
        for s in MAJORS:
            idx = (d["sym"] == s).to_numpy()
            vals[idx] = surprise_at_T(tabs, s, pd.DatetimeIndex(d.loc[idx, "T"]), col)
        d[col] = vals

    variants = {}
    for vname, scol in (("V1_prem", "s1"), ("V2_innov", "s2")):
        yearly, loyo = [], []
        for k, a0 in enumerate(ANCHORS):
            a1 = a0 + YEAR_LEN
            thr = {}
            for s in MAJORS:
                tr = d[(d["sym"] == s) & (d["T"] < a0)][scol].dropna()
                thr[s] = float(tr.quantile(0.8)) if len(tr) >= MIN_TRAIN_COIN else np.nan
            yy = d[(d["T"] >= a0) & (d["T"] < a1)].copy().reset_index(drop=True)
            fl = np.array([bool(np.isfinite(yy.loc[i, scol]) and np.isfinite(thr[yy.loc[i, "sym"]])
                                 and yy.loc[i, scol] > thr[yy.loc[i, "sym"]])
                           for i in range(len(yy))])
            st = year_stats(yy, fl)
            st["year"] = str(a0.date())
            st["coverage"] = round(float(yy[scol].notna().mean()), 4) if len(yy) else None
            st["thr_bps"] = {s: (round(thr[s] * 1e4, 3) if np.isfinite(thr[s]) else None)
                             for s in MAJORS}
            yearly.append(st)
        for h, ah in enumerate(ANCHORS):
            a1h = ah + YEAR_LEN
            thr = {}
            for s in MAJORS:
                in_any = pd.Series(False, index=d.index)
                for a0 in ANCHORS:
                    if a0 == ah:
                        continue
                    in_any |= (d["T"] >= a0) & (d["T"] < a0 + YEAR_LEN)
                tr = d[(d["sym"] == s) & in_any][scol].dropna()
                thr[s] = float(tr.quantile(0.8)) if len(tr) >= MIN_TRAIN_COIN else np.nan
            yy = d[(d["T"] >= ah) & (d["T"] < a1h)].copy().reset_index(drop=True)
            fl = np.array([bool(np.isfinite(yy.loc[i, scol]) and np.isfinite(thr[yy.loc[i, "sym"]])
                                 and yy.loc[i, scol] > thr[yy.loc[i, "sym"]])
                           for i in range(len(yy))])
            y = yy["y1.0"].to_numpy(dtype=float)
            fb, kb = y[fl.astype(bool)], y[~fl.astype(bool)]
            if len(fb) >= MIN_SIDE and len(kb) >= MIN_SIDE:
                spread = round(float(fb.mean() - kb.mean()) * 1e4, 2)
            else:
                spread = None
            # pooled other-4 spread with the same fold thresholds
            pool_f, pool_k = [], []
            for a0 in ANCHORS:
                if a0 == ah:
                    continue
                oo = d[(d["T"] >= a0) & (d["T"] < a0 + YEAR_LEN)]
                ofl = np.array([bool(np.isfinite(oo.iloc[i][scol])
                                      and np.isfinite(thr[oo.iloc[i]["sym"]])
                                      and oo.iloc[i][scol] > thr[oo.iloc[i]["sym"]])
                                for i in range(len(oo))])
                oy = oo["y1.0"].to_numpy(dtype=float)
                pool_f.append(oy[ofl])
                pool_k.append(oy[~ofl])
            pf = np.concatenate(pool_f) if pool_f else np.array([])
            pk = np.concatenate(pool_k) if pool_k else np.array([])
            pooled = (round(float(pf.mean() - pk.mean()) * 1e4, 2)
                      if len(pf) >= MIN_SIDE and len(pk) >= MIN_SIDE else None)
            if spread is not None and pooled is not None and pooled != 0 and spread != 0:
                agree = bool(np.sign(spread) == np.sign(pooled))
            else:
                agree = None
            loyo.append({"heldout": str(ah.date()), "spread_bps": spread,
                         "pooled_other4_bps": pooled, "agree": agree,
                         "n_flag": int(fl.sum()), "n_kept": int(len(fl) - fl.sum())})
        sp = [r["spread_bps"] for r in yearly]
        lo = [r["spread_bps"] for r in loyo]
        ag = [r["agree"] for r in loyo]
        tail = [r["tail_improves"] for r in yearly]
        dec = {"year_neg": sum(1 for x in sp if x is not None and x < 0),
               "loyo_neg": sum(1 for x in lo if x is not None and x < 0),
               "loyo_agree": sum(1 for x in ag if x is True),
               "tail_years": sum(1 for x in tail if x),
               "promising": bool(sum(1 for x in sp if x is not None and x < 0) >= 4
                                 and sum(1 for x in lo if x is not None and x < 0) >= 4
                                 and sum(1 for x in tail if x) >= 4)}
        variants[vname] = {"yearly": yearly, "loyo": loyo, "decision": dec}

    out = {
        "meta": {"universe": "majors-R2", "n": int(len(d)),
                 "T": [str(d["T"].min()), str(d["T"].max())],
                 "per_year_n": [int(((d["T"] >= a) & (d["T"] < a + YEAR_LEN)).sum())
                                for a in ANCHORS],
                 "funding_files": fspan,
                 "cutoff": str(CUTOFF),
                 "outcome": "y1.0 unit rung size"},
        "variants": variants,
        "overall_promising": bool(variants["V1_prem"]["decision"]["promising"]),
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for vname, v in variants.items():
        print(f"=== {vname} flagged-kept spread (bps, expect negative) ===")
        for r in v["yearly"]:
            print(r["year"], r["spread_bps"], "flag", r["flagged"], "kept", r["kept"],
                  "ret", r["retention"], "tail", r["tail_improves"], "cut", r["cut"])
        print("LOYO:", [(r["heldout"], r["spread_bps"], r["agree"]) for r in v["loyo"]],
              v["decision"])
    print("OVERALL PROMISING (V1):", out["overall_promising"])


if __name__ == "__main__":
    main()
