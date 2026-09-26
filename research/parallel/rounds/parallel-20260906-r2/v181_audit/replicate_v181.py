"""Independent v181 blind-audit replication (Part A).

Reads ONLY the raw data + assignment spec. Never imports v181 code.
Uses relative paths (run from repo root).

Spec:
  symbols: DOGE, ADA, LINK, LTC, AVAX, TRX USDT
  1m: data/raw/alts_intraday_20260926/<SYM>_1m_<YYYY>.parquet
  4h + funding: data/raw/xs_universe_20260924/<SYM>_4h.parquet / <SYM>_funding.parquet
  grid t = 4h bars 2020-02-01 .. 2026-09-23 20:00 UTC; T = t + 4h
  sigma(t) = sample std of 360 4h open-to-open pct changes ending at t (min 120)
  k in (2.5, 3, 3.5, 4): L = open(T) * (1 - k*sigma)
  filled if any 1m low with open_time in [T+16min, T+238min] is < L
    (missing minutes never fill)
  r = open(T+4h) * (1 - s_out) / L - 1 - maker - taker - funding(T+4h)
  funding(T+4h) = sum of fundingRate with fundingTime floored to 4h == T+4h
  s_base = max(0.0002, 0.25*(H-L)/O of 1m minute 0 of T+4h [+fallback 0.0002 if missing])
  s_out = s_base + extra
  normal: maker 0.0002, taker 0.0005, extra 0
  stress: maker 0.0004, taker 0.0007, extra 0.0005
  anchor years: T in [A, A+365d) for A = 2021-09-24 .. 2025-09-24 00:00 UTC
  sleeve: w = 0.25/4 = 0.0625 per filled (asset, rung); per-T bucket return =
    w * sum(r); equity compounded in T order from 1.0; net% and max DD (%).
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

UTC = timezone.utc
OUT_DIR = Path("research/parallel/rounds/parallel-20260906-r2/v181_audit")
SYMS = ["DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "AVAXUSDT", "TRXUSDT"]
KS = (2.5, 3.0, 3.5, 4.0)
GRID_START = pd.Timestamp("2020-02-01 00:00", tz="UTC")
GRID_T_END = pd.Timestamp("2026-09-23 20:00", tz="UTC")
ANCHORS = [pd.Timestamp(f"{y}-09-24 00:00", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
ANCHOR_LEN = timedelta(days=365)
W = 0.25 / 4  # per filled (asset, rung), literal spec reading
SCEN = {
    "normal": {"maker": 0.0002, "taker": 0.0005, "extra": 0.0},
    "stress": {"maker": 0.0004, "taker": 0.0007, "extra": 0.0005},
}
YEARS_1M = (2020, 2021, 2022, 2023, 2024, 2025, 2026)


def floor_4h(ts: pd.Timestamp) -> pd.Timestamp:
    return ts.tz_convert("UTC").floor("4h")


def load_symbol(sym):
    b4 = pd.read_parquet(f"data/raw/xs_universe_20260924/{sym}_4h.parquet")
    b4 = b4.sort_values("open_time").reset_index(drop=True)
    f = pd.read_parquet(f"data/raw/xs_universe_20260924/{sym}_funding.parquet")
    parts = []
    for y in YEARS_1M:
        p = Path(f"data/raw/alts_intraday_20260926/{sym}_1m_{y}.parquet")
        if p.exists():
            parts.append(pd.read_parquet(p))
    m1 = pd.concat(parts, ignore_index=True).sort_values("open_time").reset_index(drop=True)
    return b4, f, m1


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(Path("data/raw/alts_intraday_20260926/manifest.json").read_text())
    fills = []  # one row per (T, sym, k) filled
    diagnostics = {"symbols": {}, "manifest_rows_expected": {}, "grid": {}}
    sleeve_inputs = {}  # (scenario) -> list not needed; compute later from fills

    for sym in SYMS:
        b4, fund, m1 = load_symbol(sym)
        exp_rows = manifest["symbols"][sym]
        diagnostics["manifest_rows_expected"][sym] = {
            "manifest_rows": exp_rows["rows"],
            "manifest_missing": exp_rows["missing"],
            "loaded_1m_rows": int(len(m1)),
        }
        # duplicates / bad rows
        dup_1m = int(m1.duplicated(subset=["open_time"]).sum())
        bad_1m = int(((m1["high"] < m1["low"]) | (m1["open"] <= 0) | (m1["close"] <= 0)).sum())
        dup_4h = int(b4.duplicated(subset=["open_time"]).sum())
        # 1m arrays
        ts = m1["open_time"].values.astype("datetime64[ns]").astype("int64")
        low = m1["open"].values * 0 + m1["low"].values  # ensure float copy
        low = low.astype(float)
        # minute-0 lookup arrays
        m1_idx = {t: i for i, t in enumerate(m1["open_time"].tolist())}
        m1_high = m1["high"].values.astype(float)
        m1_lowA = m1["low"].values.astype(float)
        m1_openA = m1["open"].values.astype(float)
        # 4h maps
        b4_times = b4["open_time"].tolist()
        open_map = dict(zip(b4_times, b4["open"].astype(float).tolist()))
        b4_sorted = sorted(b4_times)
        opens = pd.Series([open_map[t] for t in b4_sorted],
                          index=pd.DatetimeIndex(b4_sorted))
        pct = opens.pct_change()
        sigma = pct.rolling(360, min_periods=120).std(ddof=1)
        # funding floored sums
        ft = pd.to_datetime(fund["fundingTime"], utc=True)
        floored = ft.dt.floor("4h")
        fund_sum = fund.assign(_b=floored.tolist()).groupby("_b")["fundingRate"].sum()
        fund_map = {pd.Timestamp(k).tz_localize("UTC") if pd.Timestamp(k).tzinfo is None else pd.Timestamp(k).tz_convert("UTC"): float(v) for k, v in fund_sum.items()}
        # grid
        grid = [t for t in b4_sorted if GRID_START <= t <= GRID_T_END]
        n_t = len(grid)
        n_valid_sigma = 0
        n_win_nom1m = 0
        missing_exit_min0 = 0
        sym_fills = 0
        grid_set = set(b4_sorted)
        for t in grid:
            s = float(sigma.get(t, float("nan")))
            if not np.isfinite(s) or s <= 0:
                continue
            n_valid_sigma += 1
            T = t + pd.Timedelta(hours=4)
            T2 = T + pd.Timedelta(hours=4)
            if T not in open_map or T2 not in open_map:
                continue  # truncated holding window rejected
            oT = float(open_map[T])
            oX = float(open_map[T2])
            if not (np.isfinite(oT) and np.isfinite(oX) and oT > 0 and oX > 0):
                continue
            # 1m window min low
            lo_ns = T.value + 16 * 60 * 10 ** 9
            hi_ns = T.value + 238 * 60 * 10 ** 9
            i0 = int(np.searchsorted(ts, lo_ns, side="left"))
            i1 = int(np.searchsorted(ts, hi_ns, side="right")) - 1
            if i0 > i1 or i0 >= len(ts):
                continue
            i1 = min(i1, len(ts) - 1)
            # guard: slice must lie within [lo, hi]; searchsorted ensures it
            min_low = float(np.min(low[i0:i1 + 1]))
            n_exist = i1 - i0 + 1
            if n_exist < 223:
                n_win_nom1m += 1
            # exit minute-0 spread
            j = m1_idx.get(T2, None)
            if j is None:
                s_base = 0.0002
                missing_exit_min0 += 1
                spread = None
            else:
                o0, h0, l0 = float(m1_openA[j]), float(m1_high[j]), float(m1_lowA[j])
                spread = (0.25 * (h0 - l0) / o0) if o0 > 0 else float("nan")
                s_base = max(0.0002, spread) if np.isfinite(spread) else 0.0002
                if j is None:
                    missing_exit_min0 += 1
            fund_c = float(fund_map.get(T2, 0.0))
            for k in KS:
                L = oT * (1.0 - k * s)
                if not np.isfinite(L) or L <= 0:
                    continue
                if not (min_low < L):
                    continue
                row = {"T": T.isoformat(), "sym": sym, "k": k, "L": L,
                       "open_T": oT, "open_exit": oX, "sigma": s,
                       "min_low": min_low, "funding": fund_c, "s_base": s_base,
                       "spread0": spread}
                for scen, c in SCEN.items():
                    s_out = s_base + c["extra"]
                    r = oX * (1.0 - s_out) / L - 1.0 - c["maker"] - c["taker"] - fund_c
                    row[f"r_{scen}"] = float(r)
                fills.append(row)
                sym_fills += 1
        diagnostics["symbols"][sym] = {
            "b4_rows": int(len(b4)), "dup_4h": dup_4h,
            "dup_1m": dup_1m, "bad_1m": bad_1m,
            "grid_t_count": n_t, "valid_sigma_t": n_valid_sigma,
            "windows_with_missing_1m": n_win_nom1m,
            "missing_exit_minute0": missing_exit_min0,
            "fills_total_all_rungs": sym_fills,
        }

    fdf = pd.DataFrame(fills)
    if len(fdf):
        fdf["T"] = pd.to_datetime(fdf["T"], utc=True)
    # anchor aggregation
    per_year = {}
    pooled_rows = []
    for ai, A in enumerate(ANCHORS):
        B = A + ANCHOR_LEN
        label = f"{A.date()}_+365d"
        if len(fdf):
            sub = fdf[(fdf["T"] >= A) & (fdf["T"] < B)].copy()
        else:
            sub = fdf
        y = {"anchor": A.isoformat(), "end": B.isoformat(), "label": label,
             "n_fills": int(len(sub))}
        for scen in SCEN:
            if len(sub):
                r = sub[f"r_{scen}"].values.astype(float)
                y[f"{scen}_mean_bps"] = float(np.mean(r) * 1e4)
                y[f"{scen}_fills"] = int(len(sub))
                per_asset = sub.groupby("sym")[f"r_{scen}"].mean() * 1e4
                y[f"{scen}_per_asset_mean_bps"] = {s: float(v) for s, v in per_asset.items()}
                # sleeve equity in T order
                g = sub.groupby("T")[f"r_{scen}"].sum()  # sum of r per bucket
                g = g.sort_index()
                eq = 1.0
                peak = 1.0
                maxdd = 0.0
                for _, ssum in g.items():
                    eq *= (1.0 + W * float(ssum))
                    peak = max(peak, eq)
                    dd = (peak - eq) / peak * 100 if peak > 0 else 0.0
                    maxdd = max(maxdd, dd)
                y[f"{scen}_sleeve_net_pct"] = float((eq - 1.0) * 100)
                y[f"{scen}_sleeve_dd_pct"] = float(maxdd)
                y[f"{scen}_sleeve_buckets"] = int(len(g))
            else:
                y[f"{scen}_mean_bps"] = None
                y[f"{scen}_fills"] = 0
                y[f"{scen}_per_asset_mean_bps"] = {}
                y[f"{scen}_sleeve_net_pct"] = 0.0
                y[f"{scen}_sleeve_dd_pct"] = 0.0
                y[f"{scen}_sleeve_buckets"] = 0
        per_year[label] = y
    pooled = {}
    for scen in SCEN:
        if len(fdf):
            in_all = fdf[(fdf["T"] >= ANCHORS[0]) & (fdf["T"] < ANCHORS[-1] + ANCHOR_LEN)]
            r = in_all[f"r_{scen}"].values.astype(float)
            pooled[scen] = {"fills": int(len(in_all)),
                            "mean_bps": float(np.mean(r) * 1e4) if len(in_all) else None}
            pooled_rows.append(len(in_all))
        else:
            pooled[scen] = {"fills": 0, "mean_bps": None}
    # criterion
    normal_means = [per_year[l]["normal_mean_bps"] for l in per_year]
    n_pos = sum(1 for m in normal_means if m is not None and m > 0)
    criterion = {
        "normal_years_positive": n_pos,
        "normal_pass_ge4of5": bool(n_pos >= 4 and all(m is not None for m in normal_means)),
        "stress_pooled_bps": pooled["stress"]["mean_bps"],
        "stress_pooled_positive": bool(pooled["stress"]["mean_bps"] is not None
                                       and pooled["stress"]["mean_bps"] > 0),
    }
    criterion["pass"] = bool(criterion["normal_pass_ge4of5"] and criterion["stress_pooled_positive"])
    # top-10 per scenario
    top10 = {}
    top10_in_anchor = {}
    for scen in SCEN:
        if len(fdf):
            t = fdf.nlargest(10, f"r_{scen}")[
                ["T", "sym", "k", "L", "open_T", "open_exit", "sigma", "min_low",
                 "funding", "s_base", f"r_{scen}"]].copy()
            t["T"] = t["T"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            t[f"r_{scen}_bps"] = t[f"r_{scen}"] * 1e4
            top10[scen] = t.to_dict(orient="records")
            ina = fdf[(fdf["T"] >= ANCHORS[0]) & (fdf["T"] < ANCHORS[-1] + ANCHOR_LEN)]
            ti = ina.nlargest(10, f"r_{scen}")[
                ["T", "sym", "k", "L", "open_T", "open_exit", "sigma", "min_low",
                 "funding", "s_base", f"r_{scen}"]].copy()
            ti["T"] = ti["T"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            ti[f"r_{scen}_bps"] = ti[f"r_{scen}"] * 1e4
            top10_in_anchor[scen] = ti.to_dict(orient="records")
        else:
            top10[scen] = []
            top10_in_anchor[scen] = []
    out = {
        "spec": {
            "symbols": SYMS, "ks": list(KS), "scenarios": SCEN,
            "grid": [GRID_START.isoformat(), GRID_T_END.isoformat()],
            "sigma": "std22ddof1 of 360 4h open pct changes ending at t, min 120",
            "fill_window": "[T+16min, T+238min] 1m low < L; missing never fills",
            "exit": "open(T+4h)*(1-s_out)/L-1-maker-taker-funding(T+4h floored)",
            "s_out": "max(0.0002, 0.25*range/open of 1m minute 0 of T+4h)+extra; fallback 0.0002",
            "anchors": [a.isoformat() for a in ANCHORS], "anchor_len_days": 365,
            "membership": "T in [anchor, anchor+365d)",
            "sleeve_w": W, "sleeve": "equity compounded per-T bucket from 1.0; DD peak-to-trough %",
        },
        "diagnostics": diagnostics,
        "per_anchor_year": per_year,
        "pooled": pooled,
        "criterion": criterion,
        "top10": top10,
        "top10_in_anchor": top10_in_anchor,
        "n_fill_rows": int(len(fdf)),
    }
    with open(OUT_DIR / "replication.json", "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"fills={len(fdf)} criterion={criterion}")


if __name__ == "__main__":
    main()
