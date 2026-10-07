"""oc_qbasis: quarterly-futures basis (leverage/euphoria) regime.

Per PLAN.md (pre-registered): F(T) = BTC qb_front z-score vs trailing 90d,
using ONLY 4h rows with close_time strictly before T. (a) book long/short-leg
gross P&L by basis tercile with previous-time cut-offs; (b) dip rung mean
y1.0 by basis tercile with previous-row cut-offs. 5 anchor years + LOYO.
Secondary descriptive: ETH z90 (same method).

Single process; loads only qbasis 4h + 4h books/opens + fills (no 1m).

  python research/tournament/oc_qbasis/analyze_qbasis.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
QB_PATH = CACHE / "qbasis_features_4h.parquet"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
DEPTHS = [2.5, 3.0, 3.5, 4.0, 5.0]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
WIN90 = pd.Timedelta(days=90)
MIN_WIN = 300
MIN_TRAIN = 100
MIN_SIDE = 30


class ZFeat:
    """Causal trailing-90d z-score of a 4h qb_front series (close_time < T strict)."""

    def __init__(self, frame: pd.DataFrame):
        d = frame.sort_values("close_time").reset_index(drop=True)
        self.ct = d["close_time"].values.astype("datetime64[ns]").astype(np.int64)
        v = d["qb_front"].to_numpy(dtype=float)
        self.v = v
        ok = ~np.isnan(v)
        self.cs = np.concatenate([[0.0], np.cumsum(np.where(ok, v, 0.0))])
        self.cs2 = np.concatenate([[0.0], np.cumsum(np.where(ok, v * v, 0.0))])
        self.cc = np.concatenate([[0], np.cumsum(ok.astype(np.int64))])
        ff = np.full_like(v, np.nan)
        last = np.nan
        for i, x in enumerate(v):
            if not np.isnan(x):
                last = x
            ff[i] = last
        self.ff = ff
        self.win_ns = int(WIN90.total_seconds() * 1e9)

    def compute(self, queries: pd.DatetimeIndex) -> pd.DataFrame:
        """Returns DataFrame(z, level) indexed like queries (level = last qb < T)."""
        q = queries.sort_values().unique()
        qns = q.values.astype("datetime64[ns]").astype(np.int64)
        lo = qns - self.win_ns
        i0 = np.searchsorted(self.ct, qns, side="left")
        li = np.searchsorted(self.ct, lo, side="left")
        n = self.cc[i0] - self.cc[li]
        s = self.cs[i0] - self.cs[li]
        s2 = self.cs2[i0] - self.cs2[li]
        z = np.full(len(q), np.nan)
        lvl = np.full(len(q), np.nan)
        has_prev = i0 > 0
        lvl0 = np.full(len(q), np.nan)
        lvl0[has_prev] = self.ff[i0[has_prev] - 1]
        lvl[:] = lvl0
        ok = (n >= MIN_WIN) & has_prev & (~np.isnan(lvl0))
        nn = n[ok].astype(float)
        mean = s[ok] / nn
        var = (s2[ok] - s[ok] * s[ok] / nn) / (nn - 1)
        std = np.sqrt(np.maximum(var, 0.0))
        good = ok.copy()
        good[ok] = std > 0
        zvals = np.full(ok.sum(), np.nan)
        m = std > 0
        zvals[m] = (lvl0[ok][m] - mean[m]) / std[m]
        z[ok] = zvals
        out = pd.DataFrame({"z": z, "level": lvl}, index=q)
        return out.reindex(queries)


def research_books_d2() -> pd.DataFrame:
    """Mirror of scripts/forward_v205.py::research_books_d2 (same as oc_fundregime)."""
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
    q = pd.read_parquet(QB_PATH)
    q["close_time"] = pd.to_datetime(q["close_time"], utc=True)
    q["open_time"] = pd.to_datetime(q["open_time"], utc=True)
    btc = q[q.sym == "BTCUSDT"][["close_time", "qb_front"]]
    eth = q[q.sym == "ETHUSDT"][["close_time", "qb_front"]]
    Fbtc, Feth = ZFeat(btc), ZFeat(eth)
    qb_span = {
        "BTC": [str(btc["close_time"].min()), str(btc["close_time"].max()),
                int(btc["qb_front"].notna().sum())],
        "ETH": [str(eth["close_time"].min()), str(eth["close_time"].max()),
                int(eth["qb_front"].notna().sum())],
    }

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
    Fbar = Fbtc.compute(pnl.index)["z"]
    Gbar = Feth.compute(pnl.index)["z"]
    Lbar = Fbtc.compute(pnl.index)["level"]
    long_m = books > 0
    short_m = books < 0

    book_years, book_loyo = [], []
    for k, a0 in enumerate(ANCHORS):
        a1 = a0 + YEAR_LEN
        train_times = pnl.index[(pnl.index < a0) & Fbar.notna()]
        n_train = int(len(train_times))
        ym = (pnl.index >= a0) & (pnl.index < a1)
        row: dict = {"year": str(a0.date()), "n_bars": int(ym.sum()), "n_train_times": n_train}
        if n_train >= MIN_TRAIN:
            Ftrain = Fbar[train_times]
            q33, q67 = float(Ftrain.quantile(1 / 3)), float(Ftrain.quantile(2 / 3))
            row.update(cut_q33=q33, cut_q67=q67)
            Fy = Fbar[ym]
            Ly = Lbar[ym]
            for leg, lm in (("long", long_m), ("short", short_m)):
                out_leg = {}
                for name, tsel in (("lo", (Fy <= q33)), ("mid", (Fy > q33) & (Fy <= q67)), ("hi", (Fy > q67))):
                    tsel5 = pd.DataFrame(
                        np.repeat(tsel.to_numpy()[:, None], len(SYMS), axis=1),
                        index=pnl.index[ym], columns=SYMS)
                    cell = pnl[ym][lm[ym] & tsel5]
                    vals = cell.stack()
                    if name == "lo":
                        lvl_rows = Ly[(Fy <= q33) & Fy.notna()]
                    elif name == "hi":
                        lvl_rows = Ly[(Fy > q67) & Fy.notna()]
                    else:
                        lvl_rows = Ly[(Fy > q33) & (Fy <= q67)]
                    out_leg[name] = {
                        "sum": round(float(vals.sum()), 6),
                        "n": int(vals.count()),
                        "mean_bps": round(float(vals.mean() * 1e4), 3) if vals.count() else None,
                        "lvl_med_pct": round(float(lvl_rows.median() * 100), 3) if len(lvl_rows) else None,
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

    for h, ah in enumerate(ANCHORS):
        trF_list = []
        for k, a0 in enumerate(ANCHORS):
            if k == h:
                continue
            a1 = a0 + YEAR_LEN
            ym = (pnl.index >= a0) & (pnl.index < a1)
            Fm = Fbar[ym]
            trF_list.append(Fm[Fm.notna()].to_numpy())
        trF = np.concatenate(trF_list) if trF_list else np.array([])
        if len(trF) >= MIN_TRAIN:
            q33, q67 = float(np.quantile(trF, 1 / 3)), float(np.quantile(trF, 2 / 3))
        else:
            q33 = q67 = np.nan
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
                          "q33": float(q33), "q67": float(q67),
                          "n_train": int(len(trF)), "n_lo": int(len(lov)), "n_hi": int(len(hiv))})

    # ---- dips ----
    fills = pd.read_parquet(ROOT / "research/tournament/ext/fills_U_ext.parquet")
    fills["t_fill"] = pd.to_datetime(fills["t_fill"], utc=True)
    fills["T"] = fills["t_fill"] - pd.to_timedelta(fills["f"], unit="m")
    m = fills["sym"].isin(MAJORS) & fills["x1"].isin(DEPTHS)
    d = fills[m].copy().sort_values("T").reset_index(drop=True)
    dT = pd.DatetimeIndex(d["T"])
    d["F"] = Fbtc.compute(dT)["z"].to_numpy()
    d["G"] = Feth.compute(dT)["z"].to_numpy()
    d["Lvl"] = Fbtc.compute(dT)["level"].to_numpy()
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
            row.update(cut_q33=q33, cut_q67=q67)
            t = tercile_stats(yy["F"], yy["y1.0"], q33, q67)
            row["terciles"] = {kk: {"mean_bps": round(v["mean_bps"], 2) if v["mean_bps"] is not None else None,
                                    "n": v["n"]} for kk, v in t.items() if kk in ("lo", "mid", "hi")}
            row["spread_bps"] = round(t["spread_bps"], 2) if t["spread_bps"] is not None else None
            for kk in ("lo", "mid", "hi"):
                sub = yy[(yy["F"] <= q33) if kk == "lo" else ((yy["F"] > q67) if kk == "hi" else ((yy["F"] > q33) & (yy["F"] <= q67)))]
                sub = sub[sub["F"].notna()]
                row["terciles"][kk]["lvl_med_pct"] = round(float(sub["Lvl"].median() * 100), 3) if len(sub) else None
        else:
            row.update(spread_bps=None, terciles=None)
        dip_years.append(row)
    for h, ah in enumerate(ANCHORS):
        tr = d[~((d["T"] >= ah) & (d["T"] < ah + YEAR_LEN))]
        tr = tr[tr["F"].notna()]
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
                             "q33": float(q33), "q67": float(q67),
                             "n_train": int(len(tr)),
                             "n_lo": int(t["lo"]["n"]), "n_hi": int(t["hi"]["n"])})
        else:
            dip_loyo.append({"heldout": str(ah.date()), "spread_bps": None})

    # ---- ETH secondary (descriptive): same tercile spreads, no rule ----
    eth_desc = {"books": [], "dips": []}
    Gbar_nn = Gbar
    for k, a0 in enumerate(ANCHORS):
        a1 = a0 + YEAR_LEN
        tr = Gbar_nn[(pnl.index < a0) & Gbar_nn.notna()]
        ym = (pnl.index >= a0) & (pnl.index < a1)
        if len(tr) >= MIN_TRAIN:
            q33, q67 = float(tr.quantile(1 / 3)), float(tr.quantile(2 / 3))
            Gy = Gbar_nn[ym]
            lo_sel = (Gy <= q33).to_numpy()[:, None] & long_m[ym].to_numpy() & Gy.notna().to_numpy()[:, None]
            hi_sel = (Gy > q67).to_numpy()[:, None] & long_m[ym].to_numpy() & Gy.notna().to_numpy()[:, None]
            lov = pnl[ym].to_numpy()[lo_sel]
            hiv = pnl[ym].to_numpy()[hi_sel]
            sp = round(float((hiv.mean() - lov.mean()) * 1e4), 2) if len(lov) >= MIN_SIDE and len(hiv) >= MIN_SIDE else None
        else:
            sp, q33, q67 = None, None, None
        eth_desc["books"].append({"year": str(a0.date()), "spread_long_bps": sp})
    for k, a0 in enumerate(ANCHORS):
        a1 = a0 + YEAR_LEN
        tr = d[(d["T"] < a0) & d["G"].notna()]
        yy = d[(d["T"] >= a0) & (d["T"] < a1)]
        if len(tr) >= MIN_TRAIN:
            q33, q67 = float(tr["G"].quantile(1 / 3)), float(tr["G"].quantile(2 / 3))
            t = tercile_stats(yy["G"], yy["y1.0"], q33, q67)
            eth_desc["dips"].append({"year": str(a0.date()), "spread_bps": t["spread_bps"]})
        else:
            eth_desc["dips"].append({"year": str(a0.date()), "spread_bps": None})

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
    overall = bool(book_dec["pass"] and dip_dec["pass"])
    verdict = "PROMISING" if overall else ("PARTIAL" if (book_dec["pass"] or dip_dec["pass"]) else "NOT PROMISING")

    out = {
        "meta": {"feature": "F(T)=BTC qb_front z vs trailing 90d, 4h closes with close_time<T strict, min 300/540; G(T)=ETH z same (descriptive)",
                 "qb_span": qb_span,
                 "grid": [str(pnl.index.min()), str(pnl.index.max()), int(len(pnl))],
                 "dip_T": [str(d["T"].min()), str(d["T"].max()), int(len(d))],
                 "per_year_n": [(r["year"], r["n"]) for r in dip_years]},
        "books": {"yearly": book_years, "loyo": book_loyo, "decision": book_dec},
        "dips": {"yearly": dip_years, "loyo": dip_loyo, "decision": dip_dec},
        "eth_secondary": eth_desc,
        "overall_promising": overall,
        "verdict": verdict,
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
    print("ETH secondary books:", [(r["year"], r["spread_long_bps"]) for r in eth_desc["books"]])
    print("ETH secondary dips:", [(r["year"], r["spread_bps"]) for r in eth_desc["dips"]])
    print("VERDICT:", verdict)


if __name__ == "__main__":
    main()
