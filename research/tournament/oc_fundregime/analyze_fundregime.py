"""oc_fundregime: Binance settled funding as a crowding regime.

Per PLAN.md (pre-registered): F(T) = cross-major mean 7-day funding using ONLY
settlements with calc_time in [T-7d, T). (a) book long/short-leg gross P&L by
funding tercile with previous-clock-time cut-offs; (b) dip rung mean y1.0 by
funding tercile with previous-row cut-offs. 5 anchor years + LOYO.

Single process; loads only *_funding.parquet + 4h books/opens + fills (no 1m).

  python research/tournament/oc_fundregime/analyze_fundregime.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
PREM = ROOT / "data/raw/binance_premium_20260928"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
DEPTHS = [2.5, 3.0, 3.5, 4.0, 5.0]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
WIN = pd.Timedelta(days=7)
MIN_TRAIN = 100
MIN_SIDE = 30


def load_funding() -> dict[str, pd.DataFrame]:
    out = {}
    for s in SYMS:
        df = pd.read_parquet(PREM / f"{s}_funding.parquet")
        df["calc_time"] = pd.to_datetime(df["calc_time"], utc=True)
        out[s] = df.sort_values("calc_time").reset_index(drop=True)
    return out


def funding_feature(fund: dict[str, pd.DataFrame], queries: pd.DatetimeIndex) -> pd.Series:
    """F(T): per-coin mean rate over settlements in [T-7d, T); all 5 coins each
    need exactly 21 settlements, else NaN. queries must be tz-aware UTC."""
    q = queries.sort_values().unique()
    qns = q.values.astype("datetime64[ns]").astype(np.int64)
    wns = (q - WIN).values.astype("datetime64[ns]").astype(np.int64)
    per = np.full((len(q), len(SYMS)), np.nan)
    for j, s in enumerate(SYMS):
        df = fund[s]
        tns = df["calc_time"].values.astype("datetime64[ns]").astype(np.int64)
        r = df["last_funding_rate"].to_numpy(dtype=float)
        lo = np.searchsorted(tns, wns, side="left")
        hi = np.searchsorted(tns, qns, side="left")
        cnt = hi - lo
        csum = np.zeros(len(q))
        # cumulative-sum trick for window means
        cs = np.concatenate([[0.0], np.cumsum(r)])
        ok = cnt == 21
        csum[ok] = cs[hi[ok]] - cs[lo[ok]]
        per[ok, j] = csum[ok] / 21.0
    allok = ~np.isnan(per).any(axis=1)
    f = np.full(len(q), np.nan)
    f[allok] = per[allok].mean(axis=1)
    return pd.Series(f, index=q, name="F").reindex(queries)


def research_books_d2() -> pd.DataFrame:
    """Mirror of scripts/forward_v205.py::research_books_d2 (same as oc_bookic)."""
    m = lambda f: pd.read_parquet(CACHE / f)[SYMS]  # noqa: E731
    A, Aq = m("member_A_O1_orders.parquet"), m("member_Aq_O1_orders.parquet")
    B, Bq = m("member_B_tv.parquet"), m("member_Bq_tv.parquet")
    idx = A.index.union(Aq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)  # noqa: E731
    o1 = 0.5 * (f(A) + f(B)) / 2 + 0.5 * (f(Aq) + f(Bq)) / 2
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    Dq = pd.read_parquet(CACHE / "members_quarterly_D.parquet")[SYMS]
    idx2 = o1.index.union(D.index).union(Dq.index)
    g = lambda X: X.reindex(idx2).fillna(0.0)  # noqa: E731
    return 0.8 * g(o1) + 0.2 * (g(D) + g(Dq)) / 2


def tercile_stats(
    vals: pd.Series, outcome: pd.Series, q33: float, q67: float, scale: float = 1e4
) -> dict:
    m = vals.notna() & outcome.notna()
    v, y = vals[m], outcome[m]
    lo = y[v <= q33]
    hi = y[v > q67]
    mid = y[(v > q33) & (v <= q67)]
    d = {
        "lo": {"mean_bps": float(lo.mean() * scale) if len(lo) else None, "n": int(len(lo))},
        "mid": {"mean_bps": float(mid.mean() * scale) if len(mid) else None, "n": int(len(mid))},
        "hi": {"mean_bps": float(hi.mean() * scale) if len(hi) else None, "n": int(len(hi))},
    }
    if len(lo) >= MIN_SIDE and len(hi) >= MIN_SIDE:
        d["spread_bps"] = float((hi.mean() - lo.mean()) * scale)
    else:
        d["spread_bps"] = None
    return d


def main() -> None:
    fund = load_funding()
    fspan = {s: (str(d["calc_time"].min()), str(d["calc_time"].max()), len(d)) for s, d in fund.items()}

    # ---- books ----
    books = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books.index)
    grid = books.index.intersection(opens.dropna(how="all").index)
    books, opens = books.reindex(grid), opens.reindex(grid)
    fwd1 = opens.shift(-1) / opens - 1.0
    pnl = books * fwd1
    valid = fwd1.notna().all(axis=1)
    books, opens, pnl = books[valid], opens[valid], pnl[valid]
    Fbar = funding_feature(fund, pnl.index)
    long_m = books > 0
    short_m = books < 0

    # training clock times for book cut-offs: all 4h clock times back to 2020-09-21
    clock_pre = pd.date_range(pd.Timestamp("2020-09-21", tz="UTC"), ANCHORS[0], freq="4h")
    clock_pre = clock_pre[clock_pre < ANCHORS[0]]
    Fpre = funding_feature(fund, clock_pre)

    book_years, book_loyo = [], []
    for k, a0 in enumerate(ANCHORS):
        a1 = a0 + YEAR_LEN
        train_times = pnl.index[(pnl.index < a0) & Fbar.notna()]
        train_times = train_times.union(Fpre.index[Fpre.notna() & (Fpre.index < a0)])
        n_train = int(len(train_times))
        ym = (pnl.index >= a0) & (pnl.index < a1)
        row: dict = {"year": str(a0.date()), "n_bars": int(ym.sum()), "n_train_times": n_train}
        if n_train >= MIN_TRAIN:
            Ftrain = funding_feature(fund, train_times)
            q33, q67 = float(Ftrain.quantile(1 / 3)), float(Ftrain.quantile(2 / 3))
            row.update(cut_q33_bps=q33 * 1e4, cut_q67_bps=q67 * 1e4)
            Fy = Fbar[ym]
            for leg, lm in (("long", long_m), ("short", short_m)):
                # vectorised per-leg tercile aggregation over (bar, coin) rows
                out_leg = {}
                for name, tsel in (("lo", (Fy <= q33)), ("mid", (Fy > q33) & (Fy <= q67)), ("hi", (Fy > q67))):
                    tsel5 = pd.DataFrame(
                        np.repeat(tsel.to_numpy()[:, None], len(SYMS), axis=1),
                        index=pnl.index[ym], columns=SYMS)
                    cell = pnl[ym][lm[ym] & tsel5]
                    vals = cell.stack()
                    out_leg[name] = {
                        "sum": round(float(vals.sum()), 6),
                        "n": int(vals.count()),
                        "mean_bps": round(float(vals.mean() * 1e4), 3) if vals.count() else None,
                    }
                row[leg] = out_leg
                lo_n, hi_n = out_leg["lo"]["n"], out_leg["hi"]["n"]
                lomean, himean = out_leg["lo"]["mean_bps"], out_leg["hi"]["mean_bps"]
                if leg == "long" and lo_n >= MIN_SIDE and hi_n >= MIN_SIDE:
                    row["spread_long_bps"] = round(himean - lomean, 2)
                elif leg == "long":
                    row["spread_long_bps"] = None
            row["coverage"] = round(float(Fy.notna().mean()), 4)
        else:
            row.update(spread_long_bps=None, coverage=None)
        book_years.append(row)

    # book LOYO
    for h, ah in enumerate(ANCHORS):
        # training rows = long/short (bar, coin) rows of the other 4 anchor years
        trF_list, trL_list = [], []
        for k, a0 in enumerate(ANCHORS):
            if k == h:
                continue
            a1 = a0 + YEAR_LEN
            ym = (pnl.index >= a0) & (pnl.index < a1)
            Fm = Fbar[ym]
            ok = Fm.notna()
            trF_list.append(np.repeat(Fm[ok].to_numpy(), len(SYMS)))
            trL_list.append(long_m[ym][ok].to_numpy().ravel())
        trF = np.concatenate(trF_list)
        trL = np.concatenate(trL_list)
        q33, q67 = float(np.quantile(trF, 1 / 3)), float(np.quantile(trF, 2 / 3))
        a1h = ah + YEAR_LEN
        ym = (pnl.index >= ah) & (pnl.index < a1h)
        Fy = Fbar[ym]
        lo_sel = (Fy <= q33).to_numpy()[:, None] & long_m[ym].to_numpy() & Fy.notna().to_numpy()[:, None]
        hi_sel = (Fy > q67).to_numpy()[:, None] & long_m[ym].to_numpy() & Fy.notna().to_numpy()[:, None]
        lov = pnl[ym].to_numpy()[lo_sel]
        hiv = pnl[ym].to_numpy()[hi_sel]
        if len(lov) >= MIN_SIDE and len(hiv) >= MIN_SIDE:
            spread = float((hiv.mean() - lov.mean()) * 1e4)
        else:
            spread = None
        book_loyo.append({"heldout": str(ah.date()), "spread_long_bps": round(spread, 2) if spread is not None else None,
                          "q33_bps": q33 * 1e4, "q67_bps": q67 * 1e4,
                          "n_train": int(len(trF)), "n_lo": int(len(lov)), "n_hi": int(len(hiv))})

    # ---- dips ----
    fills = pd.read_parquet(ROOT / "research/tournament/ext/fills_U_ext.parquet")
    fills["T"] = fills["t_fill"] - pd.to_timedelta(fills["f"], unit="m")
    m = fills["sym"].isin(MAJORS) & fills["x1"].isin(DEPTHS)
    d = fills[m].copy().sort_values("T").reset_index(drop=True)
    d["F"] = funding_feature(fund, pd.DatetimeIndex(d["T"])).to_numpy()
    dip_years, dip_loyo = [], []
    for k, a0 in enumerate(ANCHORS):
        a1 = a0 + YEAR_LEN
        tr = d[(d["T"] < a0) & d["F"].notna()]
        ym = (d["T"] >= a0) & (d["T"] < a1)
        yy = d[ym]
        row = {"year": str(a0.date()), "n": int(ym.sum()),
               "n_valid": int((ym & d["F"].notna()).sum()),
               "coverage": round(float(yy["F"].notna().mean()), 4) if len(yy) else None,
               "n_train": int(len(tr))}
        if len(tr) >= MIN_TRAIN:
            q33, q67 = float(tr["F"].quantile(1 / 3)), float(tr["F"].quantile(2 / 3))
            row.update(cut_q33_bps=q33 * 1e4, cut_q67_bps=q67 * 1e4)
            t = tercile_stats(yy["F"], yy["y1.0"], q33, q67)
            row["terciles"] = {kk: {"mean_bps": round(v["mean_bps"], 2) if v["mean_bps"] is not None else None,
                                    "n": v["n"]} for kk, v in t.items() if kk in ("lo", "mid", "hi")}
            row["spread_bps"] = round(t["spread_bps"], 2) if t["spread_bps"] is not None else None
        else:
            row.update(spread_bps=None, terciles=None)
        dip_years.append(row)
    for h, ah in enumerate(ANCHORS):
        tr = d[~((d["T"] >= ah) & (d["T"] < ah + YEAR_LEN))]
        tr = tr[tr["F"].notna()]
        # restrict training to anchor-year rows only (not pre-2021 rows)
        in_any = pd.Series(False, index=tr.index)
        for a0 in ANCHORS:
            in_any |= (tr["T"] >= a0) & (tr["T"] < a0 + YEAR_LEN)
        tr = tr[in_any]
        yy = d[(d["T"] >= ah) & (d["T"] < ah + YEAR_LEN)]
        if len(tr) >= MIN_TRAIN:
            q33, q67 = float(tr["F"].quantile(1 / 3)), float(tr["F"].quantile(2 / 3))
            t = tercile_stats(yy["F"], yy["y1.0"], q33, q67)
            dip_loyo.append({"heldout": str(ah.date()),
                             "spread_bps": round(t["spread_bps"], 2) if t["spread_bps"] is not None else None,
                             "q33_bps": q33 * 1e4, "q67_bps": q67 * 1e4,
                             "n_train": int(len(tr)),
                             "n_lo": int(t["lo"]["n"]), "n_hi": int(t["hi"]["n"])})
        else:
            dip_loyo.append({"heldout": str(ah.date()), "spread_bps": None})

    def sgn(x):
        return "-" if (x is not None and x < 0) else ("+" if (x is not None and x > 0) else "0")

    b_sp = [r.get("spread_long_bps") for r in book_years]
    b_lo = [r["spread_long_bps"] for r in book_loyo]
    d_sp = [r.get("spread_bps") for r in dip_years]
    d_lo = [r["spread_bps"] for r in dip_loyo]
    book_dec = {"year_sign_neg": sum(1 for x in b_sp if x is not None and x < 0),
                "loyo_sign_neg": sum(1 for x in b_lo if x is not None and x < 0),
                "pass": sum(1 for x in b_sp if x is not None and x < 0) >= 4
                and sum(1 for x in b_lo if x is not None and x < 0) >= 4}
    dip_dec = {"year_sign_neg": sum(1 for x in d_sp if x is not None and x < 0),
               "loyo_sign_neg": sum(1 for x in d_lo if x is not None and x < 0),
               "pass": sum(1 for x in d_sp if x is not None and x < 0) >= 4
               and sum(1 for x in d_lo if x is not None and x < 0) >= 4}

    out = {
        "meta": {"feature": "F(T)=cross-major mean 7d settled funding, settlements in [T-7d,T), 21/coin else NaN",
                 "funding_files": fspan,
                 "grid": [str(pnl.index.min()), str(pnl.index.max()), int(len(pnl))],
                 "dip_T": [str(d['T'].min()), str(d['T'].max()), int(len(d))]},
        "books": {"yearly": book_years, "loyo": book_loyo, "decision": book_dec},
        "dips": {"yearly": dip_years, "loyo": dip_loyo, "decision": dip_dec},
        "overall_promising": bool(book_dec["pass"] and dip_dec["pass"]),
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("=== book long-leg Hi-Lo spread (bps) ===")
    for r in book_years:
        print(r["year"], r.get("spread_long_bps"),
              {leg: r.get(leg) for leg in ("long", "short")} if "long" in r else "NO CUTOFFS")
    print("book LOYO:", [(r["heldout"], r["spread_long_bps"]) for r in book_loyo], book_dec)
    print("=== dip y1.0 Hi-Lo spread (bps) ===")
    for r in dip_years:
        print(r["year"], r.get("spread_bps"), r.get("terciles"))
    print("dip LOYO:", [(r["heldout"], r["spread_bps"]) for r in dip_loyo], dip_dec)
    print("OVERALL PROMISING:", out["overall_promising"])


if __name__ == "__main__":
    main()
