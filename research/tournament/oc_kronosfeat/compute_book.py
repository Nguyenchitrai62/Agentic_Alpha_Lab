"""oc_kronosfeat book side (LIGHT: 4h parquets only, no 1m)."""
from __future__ import annotations
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import rankdata

HERE = Path(__file__).parent
TMP = HERE / "tmp"
CACHE = Path("artifacts/research/engine_real")
FEATS = Path("research/tournament/oc_kronoshidden/kronos_features_4shift.parquet")
BARS = Path("research/tournament/oc_kronoshidden/bars_4h_4shift.parquet")
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
BOOK_FEATS = ["er1", "er6", "low1", "pdrop2", "vol1"]
ALL8 = ["er1", "er6", "vol1", "vol6", "rng1", "low1", "pdrop2", "pdrop3"]
HORIZONS = (1, 2, 6, 18)
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
B_BOOT = 500


def spearman_xy(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = int(len(x))
    if n < 3:
        return float("nan"), n
    if np.std(x) == 0.0 or np.std(y) == 0.0:
        return float("nan"), n
    rx, ry = rankdata(x), rankdata(y)
    if np.std(rx) == 0.0 or np.std(ry) == 0.0:
        return float("nan"), n
    return float(np.corrcoef(rx, ry)[0, 1]), n


def load_final_weights():
    m = lambda f: pd.read_parquet(CACHE / f)[SYMS]  # noqa: E731
    A = m("member_A_O1_orders.parquet")
    Aq = m("member_Aq_O1_orders.parquet")
    B = m("member_B_tv.parquet")
    Bq = m("member_Bq_tv.parquet")
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    Dq = m("members_quarterly_D.parquet")
    books_std = pd.read_parquet(CACHE / "books_v154.parquet")[SYMS]
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")[SYMS].sort_index()
    std_idx = books_std.index.sort_values()
    f = lambda X: X.reindex(std_idx).fillna(0.0)  # noqa: E731
    A, Aq, B, Bq, D, Dq = f(A), f(Aq), f(B), f(Bq), f(D), f(Dq)
    o1 = (A + Aq + B + Bq) / 4.0
    cb = (D + Dq) / 2.0
    full = 0.8 * o1 + 0.2 * cb
    opens_std = opens_full.reindex(std_idx)
    btc = opens_std["BTCUSDT"]
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).fillna(False)
    final = full.copy()
    final[bear] = final[bear].where(final[bear] <= 0, final[bear] * 0.5)
    return final, std_idx


def week_ids(T):
    d = pd.DatetimeIndex(T).tz_convert("UTC")
    epoch_mon = pd.Timestamp("1970-01-05", tz="UTC")
    days = ((d - epoch_mon).total_seconds() // 86400).astype(int)
    return (days // 7).astype(int)


def boot_cis(dfin, cols_x, col_y, seed):
    wk = dfin["wk"].to_numpy()
    weeks = np.unique(wk)
    nW = len(weeks)
    yv = dfin[col_y].to_numpy(dtype=float)
    out = {}
    for c in cols_x:
        xv = dfin[c].to_numpy(dtype=float)
        ic, n = spearman_xy(xv, yv)
        out[c] = {"ic": round(float(ic), 4) if np.isfinite(ic) else None,
                  "n": int(n), "ci": None}
    if nW >= 2:
        rng = np.random.default_rng(seed)
        boots = {c: np.full(B_BOOT, np.nan) for c in cols_x}
        wpos = {w: np.where(wk == w)[0] for w in weeks}
        xcache = {c: dfin[c].to_numpy(dtype=float) for c in cols_x}
        for b in range(B_BOOT):
            pick = rng.integers(0, nW, size=nW)
            sel = np.concatenate([wpos[weeks[i]] for i in pick])
            yb = yv[sel]
            for c in cols_x:
                xb = xcache[c][sel]
                m = np.isfinite(xb) & np.isfinite(yb)
                xx, yy = xb[m], yb[m]
                if len(xx) < 3 or np.std(xx) == 0.0 or np.std(yy) == 0.0:
                    continue
                rx, ry = rankdata(xx), rankdata(yy)
                if np.std(rx) == 0.0 or np.std(ry) == 0.0:
                    continue
                boots[c][b] = np.corrcoef(rx, ry)[0, 1]
        for c in cols_x:
            ok = boots[c][np.isfinite(boots[c])]
            if len(ok) >= 50:
                out[c]["ci"] = [round(float(np.percentile(ok, 2.5)), 4),
                                round(float(np.percentile(ok, 97.5)), 4)]
    return out


def main():
    t0 = time.time()
    TMP.mkdir(parents=True, exist_ok=True)
    print("book: loading bars+features ...", flush=True)
    bars = pd.read_parquet(BARS)
    feats = pd.read_parquet(FEATS)
    print(f"bars {len(bars)} feats {len(feats)}", flush=True)
    bars = bars.sort_values(["sym", "shift", "T"]).reset_index(drop=True)
    bars["r1"] = bars.groupby(["sym", "shift"])["open"].transform(
        lambda s: s / s.shift(1) - 1.0)
    bars["sigma"] = bars.groupby(["sym", "shift"])["r1"].transform(
        lambda s: s.rolling(360, min_periods=120).std(ddof=1))
    for h in HORIZONS:
        hh = int(h)
        bars["fh%d" % hh] = bars.groupby(["sym", "shift"])["open"].transform(
            lambda s, hh=hh: s.shift(-hh) / s - 1.0)
        bars["y%d" % hh] = bars["fh%d" % hh] / bars["sigma"]
        bad = bars["sigma"].isna() | (bars["sigma"] <= 0) | bars["fh%d" % hh].isna()
        bars.loc[bad, "y%d" % hh] = np.nan
        bars["ay%d" % hh] = bars["y%d" % hh].abs()
    keep = ["sym", "shift", "T", "open", "sigma"]
    for h in HORIZONS:
        keep += ["y%d" % int(h), "ay%d" % int(h)]
    df = bars[keep].merge(feats[["sym", "shift", "T"] + ALL8],
                          on=["sym", "shift", "T"], how="inner")
    print("joined rows %d range %s..%s in %.0fs" % (
        len(df), df["T"].min(), df["T"].max(), time.time() - t0), flush=True)
    df["wk"] = week_ids(df["T"])
    df["year"] = -1
    for yi, a0 in enumerate(ANCHORS):
        a1 = a0 + pd.Timedelta(days=365)
        df.loc[(df["T"] >= a0) & (df["T"] < a1), "year"] = yi
    df = df[df["year"] >= 0].reset_index(drop=True)
    print("rows per year: %s" % str(df.groupby("year").size().to_dict()), flush=True)
    tables = {"book_ic": [], "book_vol": [], "n_rows": {},
              "sigma_note": "sigma=trailing-360 std of 1-bar simple returns per (sym,shift), min120, causal"}
    for yi in range(5):
        tables["n_rows"][str(yi)] = int((df["year"] == yi).sum())
    for yi in range(5):
        dy = df[df["year"] == yi].reset_index(drop=True)
        for h in HORIZONS:
            hh = int(h)
            print("book Y%d h=%d n=%d elapsed %.0fs" % (yi, hh, len(dy), time.time() - t0), flush=True)
            ycol = "y%d" % hh
            acol = "ay%d" % hh
            sub = dy[np.isfinite(dy[ycol].to_numpy())].reset_index(drop=True)
            res_p = boot_cis(sub, BOOK_FEATS, ycol, seed=(7, yi, hh, 0))
            suba = dy[np.isfinite(dy[acol].to_numpy())].reset_index(drop=True)
            res_pa = boot_cis(suba, BOOK_FEATS, acol, seed=(7, yi, hh, 1))
            for c in BOOK_FEATS:
                tables["book_ic"].append({"year": yi, "h": hh, "coin": "POOLED",
                                         "feat": c, "ic": res_p[c]["ic"],
                                         "n": res_p[c]["n"], "ci": res_p[c]["ci"]})
                tables["book_vol"].append({"year": yi, "h": hh, "coin": "POOLED",
                                          "feat": c, "ic": res_pa[c]["ic"],
                                          "n": res_pa[c]["n"], "ci": res_pa[c]["ci"]})
            for sym in SYMS:
                ds = dy[dy["sym"] == sym].reset_index(drop=True)
                s1 = ds[np.isfinite(ds[ycol].to_numpy())].reset_index(drop=True)
                r1 = boot_cis(s1, BOOK_FEATS, ycol, seed=(7, yi, hh, 2 + SYMS.index(sym)))
                s2 = ds[np.isfinite(ds[acol].to_numpy())].reset_index(drop=True)
                r2 = boot_cis(s2, BOOK_FEATS, acol, seed=(7, yi, hh, 12 + SYMS.index(sym)))
                for c in BOOK_FEATS:
                    tables["book_ic"].append({"year": yi, "h": hh, "coin": sym,
                                             "feat": c, "ic": r1[c]["ic"],
                                             "n": r1[c]["n"], "ci": r1[c]["ci"]})
                    tables["book_vol"].append({"year": yi, "h": hh, "coin": sym,
                                              "feat": c, "ic": r2[c]["ic"],
                                              "n": r2[c]["n"], "ci": r2[c]["ci"]})
    print("book: loading FINAL weights ...", flush=True)
    final, std_idx = load_final_weights()
    fw = final.stack().rename("w").reset_index()
    fw.columns = ["T", "sym", "w"]
    fw["T"] = pd.to_datetime(fw["T"], utc=True)
    fw["shift"] = 0
    f0 = feats[(feats["shift"] == 0)].merge(fw, on=["sym", "T"], how="inner")
    f0["wk"] = week_ids(f0["T"])
    f0["year"] = -1
    for yi, a0 in enumerate(ANCHORS):
        a1 = a0 + pd.Timedelta(days=365)
        f0.loc[(f0["T"] >= a0) & (f0["T"] < a1), "year"] = yi
    f0 = f0[f0["year"] >= 0].reset_index(drop=True)
    f0["aw"] = f0["w"].abs()
    print("book-weight join rows %d" % len(f0), flush=True)
    tables["w_corr"] = []
    tables["w_corr_abs"] = []
    for yi in range(5):
        dy = f0[f0["year"] == yi].reset_index(drop=True)
        print("weights Y%d n=%d elapsed %.0fs" % (yi, len(dy), time.time() - t0), flush=True)
        rp = boot_cis(dy, ALL8, "w", seed=(7, yi, 99, 0))
        ra = boot_cis(dy, ALL8, "aw", seed=(7, yi, 99, 1))
        for c in ALL8:
            tables["w_corr"].append({"year": yi, "coin": "POOLED", "feat": c,
                                    "ic": rp[c]["ic"], "n": rp[c]["n"], "ci": rp[c]["ci"]})
            tables["w_corr_abs"].append({"year": yi, "coin": "POOLED", "feat": c,
                                        "ic": ra[c]["ic"], "n": ra[c]["n"], "ci": ra[c]["ci"]})
        for sym in SYMS:
            ds = dy[dy["sym"] == sym].reset_index(drop=True)
            r1 = boot_cis(ds, ALL8, "w", seed=(7, yi, 99, 2 + SYMS.index(sym)))
            for c in ALL8:
                tables["w_corr"].append({"year": yi, "coin": sym, "feat": c,
                                        "ic": r1[c]["ic"], "n": r1[c]["n"], "ci": r1[c]["ci"]})
    (TMP / "book_tables.json").write_text(json.dumps(tables, indent=1))
    print("wrote tmp/book_tables.json rows ic=%d vol=%d w=%d in %.0fs" % (
        len(tables["book_ic"]), len(tables["book_vol"]), len(tables["w_corr"]), time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
