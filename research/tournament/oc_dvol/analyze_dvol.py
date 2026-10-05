"""oc_dvol analysis: causal DVOL features -> join to majors R2 rungs -> per-year IC + terciles + LOYO.

Strict as-of rule: a bar is usable at T iff its bar END is strictly before T
(implemented as end <= T - 1s via searchsorted side='left' on the key T-1s).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st

ROOT = Path(__file__).resolve().parents[3]
OC = ROOT / "research/tournament/oc_dvol"
RAW = ROOT / "data/raw/deribit_dvol_20261005"
FILLS = ROOT / "research/tournament/ext/fills_U_ext.parquet"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
FEAT_START = pd.Timestamp("2021-06-30", tz="UTC")  # ~90d after DVOL start
NS = 1_000_000_000
H = 3_600 * NS
DAY = 86_400 * NS
FEATURES = ["dvol_z90", "dvol_chg24", "vrp"]


def load_dvol() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per coin: (ends_ns sorted int64, closes float64). Dedupes month overlaps."""
    out = {}
    for cur in ("BTC", "ETH"):
        ts, cl = [], []
        for fp in sorted(RAW.glob(f"{cur}_*.json")):
            if fp.name == "manifest.json":
                continue
            p = json.loads(fp.read_text())
            for c in p["candles"]:
                ts.append((int(c[0]) + 3_600_000) * 1_000_000)  # bar END, ns
                cl.append(float(c[4]))            # close
        ts = np.array(ts, dtype=np.int64)
        cl = np.array(cl, dtype=float)
        o = np.argsort(ts)
        ts, cl = ts[o], cl[o]
        _, u = np.unique(ts, return_index=True)  # dedupe month-boundary overlap
        mask = np.zeros(len(ts), bool)
        mask[u] = True
        # drop bars starting at/after the 2026-09-24 00:00 UTC cutoff
        cutoff_ns = int(pd.Timestamp("2026-09-24", tz="UTC").value)
        mask &= (ts - 3_600 * NS) < cutoff_ns
        out[cur] = (ts[mask], cl[mask])
    return out


def build_panel(dvol) -> None:
    rows = []
    for cur, (ends, cl) in dvol.items():
        t = pd.to_datetime(ends - 3_600 * NS, utc=True)
        rows.append(pd.DataFrame({"t": t, "close": cl,
                                  "sym": ("BTCDVOL" if cur == "BTC" else "ETHDVOL")}))
    panel = pd.concat(rows, ignore_index=True).sort_values(["sym", "t"]).reset_index(drop=True)
    panel.to_parquet(OC / "dvol_hourly.parquet")


def asof_idx(ends: np.ndarray, Tns: np.ndarray) -> np.ndarray:
    """Index of last bar with end < T (i.e. end <= T - 1s). -1 if none."""
    return np.searchsorted(ends, Tns - NS, side="left") - 1


def compute_features(df: pd.DataFrame, dvol, daily: dict[str, tuple[np.ndarray, np.ndarray]]) -> pd.DataFrame:
    df = df.copy()
    Tns = df["TT"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    coinmap = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "BTC",
               "BNBUSDT": "BTC", "XRPUSDT": "BTC"}
    df["dvol_coin"] = df["sym"].map(coinmap)
    for feat in FEATURES:
        df[feat] = np.nan
    for cur in ("BTC", "ETH"):
        m = (df["dvol_coin"] == cur).to_numpy()
        if not m.any():
            continue
        ends, cl = dvol[cur]
        Tn = Tns[m]
        ii = asof_idx(ends, Tn)
        ok = ii >= 0
        v0 = np.full(len(Tn), np.nan)
        v0[ok] = cl[ii[ok]]
        # z90: literal asof samples asof(T-k*1h), k=1..2160
        cnt = np.zeros(len(Tn))
        s1 = np.zeros(len(Tn))
        s2 = np.zeros(len(Tn))
        for k in range(1, 2161):
            jk = np.searchsorted(ends, Tn - k * H - NS, side="left") - 1
            okk = jk >= 0
            w = np.full(len(Tn), np.nan)
            w[okk] = cl[jk[okk]]
            v = np.isfinite(w)
            cnt[v] += 1
            s1[v] += w[v]
            s2[v] += w[v] ** 2
        good = cnt >= 1728
        mean = np.full(len(Tn), np.nan)
        std = np.full(len(Tn), np.nan)
        mean[good] = s1[good] / cnt[good]
        var_sub = (s2[good] - s1[good] ** 2 / cnt[good]) / (cnt[good] - 1)
        gidx = np.where(good)[0]
        pos = var_sub > 0
        std[gidx[pos]] = np.sqrt(var_sub[pos])
        z = (v0 - mean) / std
        # lagged 24h value
        jl = np.searchsorted(ends, Tn - 24 * H - NS, side="left") - 1
        vl = np.full(len(Tn), np.nan)
        okkl = jl >= 0
        vl[okkl] = cl[jl[okkl]]
        chg = v0 - vl
        # vrp: last 31 usable daily closes -> 30 log returns
        dends, dcl = daily[cur]
        di = asof_idx(dends, Tn)
        rv = np.full(len(Tn), np.nan)
        for i in np.where(di >= 30)[0]:
            seg = dcl[di[i] - 30: di[i] + 1]  # 31 closes, all with end < T
            if np.all(np.isfinite(seg)) and np.all(seg > 0):
                r = np.log(seg[1:] / seg[:-1])
                rv[i] = float(np.std(r, ddof=1) * np.sqrt(365) * 100)
        vrp = v0 - rv
        df.loc[m, "dvol_z90"] = z
        df.loc[m, "dvol_chg24"] = chg
        df.loc[m, "vrp"] = vrp
    return df


def load_daily() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per mapped coin: (close_ends_ns, daily closes). C(D) = 23:00-bar close."""
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h = h[h["sym"].isin(["BTCUSDT", "ETHUSDT"])].copy()
    out = {}
    for sym, cur in (("BTCUSDT", "BTC"), ("ETHUSDT", "ETH")):
        g = h[h["sym"] == sym].sort_values("t").reset_index(drop=True)
        g["hm"] = g["t"].dt.strftime("%H:%M")
        d = g[g["hm"] == "23:00"].copy()
        ends = (d["t"] + pd.Timedelta(hours=1)).to_numpy(dtype="datetime64[ns]").astype(np.int64)
        out[cur] = (ends, d["close"].to_numpy(float))
    return out


def spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, int, float]:
    m = np.isfinite(x) & np.isfinite(y)
    n = int(m.sum())
    if n < 30:
        return np.nan, n, np.nan
    r, p = st.spearmanr(x[m], y[m])
    return float(r), n, float(p)


def main() -> None:
    dvol = load_dvol()
    for cur, (ends, cl) in dvol.items():
        dt0 = pd.to_datetime(ends[0], utc=True, unit="ns")
        dt1 = pd.to_datetime(ends[-1], utc=True, unit="ns")
        gaps = np.diff(ends) // H
        print(f"{cur}: bars={len(ends)} span={dt0}..{dt1} max_step_h={gaps.max()}", flush=True)
    build_panel(dvol)
    daily = load_daily()

    f = pd.read_parquet(FILLS)
    f["TT"] = pd.to_datetime(f["t_fill"], utc=True) - pd.to_timedelta(f["f"], unit="min")
    d = f[f["sym"].isin(MAJORS) & f["x1"].isin(R2)].copy().reset_index(drop=True)
    d = compute_features(d, dvol, daily)
    d[["TT", "sym", "x1", "y1.0", "dvol_coin"] + FEATURES].to_parquet(OC / "features_dvol.parquet")

    y = d["y1.0"].to_numpy(float)
    years = []
    for k, a0 in enumerate(ANCHORS):
        years.append(((d["TT"] >= a0) & (d["TT"] < a0 + pd.Timedelta(days=365))).to_numpy())
    prev_pool = (d["TT"] >= FEAT_START).to_numpy()

    res: dict = {"meta": {
        "fills": str(FILLS), "n_majors_r2": int(len(d)),
        "T_min": str(d["TT"].min()), "T_max": str(d["TT"].max()),
        "dvol_span": {c: [str(pd.to_datetime(v[0][0], utc=True, unit="ns")),
                          str(pd.to_datetime(v[0][-1], utc=True, unit="ns"))] for c, v in dvol.items()},
        "outcome": "y1.0", "unit": "bps in tables (x1e4)",
    }, "features": {}}
    for feat in FEATURES:
        x = d[feat].to_numpy(float)
        fx = np.isfinite(x)
        fr: dict = {"yearly": [], "loyo": []}
        for k, a0 in enumerate(ANCHORS):
            te = years[k]
            rho, n, p = spearman(x[te], y[te])
            cov = float(np.isfinite(x[te]).mean())
            tr = prev_pool & (d["TT"] < a0).to_numpy() & fx
            cut = {}
            terc = {}
            if int(tr.sum()) >= 100:
                q33, q67 = float(np.quantile(x[tr], 1 / 3)), float(np.quantile(x[tr], 2 / 3))
                cut = {"q33": q33, "q67": q67, "n_train": int(tr.sum())}
                lo = te & fx & (x <= q33)
                hi = te & fx & (x > q67)
                mid = te & fx & (x > q33) & (x <= q67)
                for nm, mm in (("lo", lo), ("mid", mid), ("hi", hi)):
                    yy = y[mm]
                    terc[nm] = {"mean_bps": round(float(np.mean(yy)) * 1e4, 2) if len(yy) else None,
                                "n": int(len(yy))}
            fr["yearly"].append({"year": str(a0.date()), "n": int(te.sum()),
                                 "n_valid": n, "rho": None if np.isnan(rho) else round(rho, 4),
                                 "p": None if np.isnan(p) else round(float(p), 4),
                                 "coverage": round(cov, 4), "cutoffs": cut, "terciles": terc})
        for h in range(5):
            tr = np.zeros(len(d), bool)
            for k in range(5):
                if k != h:
                    tr |= years[k]
            te = years[h]
            xv = x
            trm = tr & np.isfinite(xv)
            spread = None
            info = {}
            if int(trm.sum()) >= 100:
                q33, q67 = float(np.quantile(xv[trm], 1 / 3)), float(np.quantile(xv[trm], 2 / 3))
                lo = te & (xv <= q33)
                hi = te & (xv > q67)
                if int(lo.sum()) >= 30 and int(hi.sum()) >= 30:
                    spread = float(np.mean(y[hi]) - np.mean(y[lo])) * 1e4
                info = {"q33": q33, "q67": q67, "n_train": int(trm.sum()),
                        "n_lo": int(lo.sum()), "n_hi": int(hi.sum())}
            fr["loyo"].append({"heldout": str(ANCHORS[h].date()),
                               "spread_bps": None if spread is None else round(spread, 2),
                               **info})
        rhos = [w["rho"] for w in fr["yearly"]]
        signs_ic = [np.sign(r) for r in rhos if r is not None]
        spr = [w["spread_bps"] for w in fr["loyo"]]
        signs_sp = [np.sign(s) for s in spr if s is not None]
        n_ic = max(int((np.array(signs_ic) > 0).sum()), int((np.array(signs_ic) < 0).sum())) if signs_ic else 0
        n_sp = max(int((np.array(signs_sp) > 0).sum()), int((np.array(signs_sp) < 0).sum())) if signs_sp else 0
        fr["decision"] = {"ic_sign_count": f"{n_ic}/5", "spread_sign_count": f"{n_sp}/5",
                          "promising": bool(n_ic >= 4 and n_sp >= 4)}
        # descriptive coin splits (NOT part of the rule)
        splits = {}
        for nm, mm in (("BTC", d["sym"] == "BTCUSDT"), ("ETH", d["sym"] == "ETHUSDT"),
                       ("proxy", d["sym"].isin(["SOLUSDT", "BNBUSDT", "XRPUSDT"]))):
            r = []
            for k in range(5):
                te = years[k] & mm.to_numpy()
                rho, n, _ = spearman(x[te], y[te])
                r.append(None if np.isnan(rho) else round(rho, 4))
            splits[nm] = r
        fr["splits_ic"] = splits
        res["features"][feat] = fr
    fc = d[FEATURES].corr(method="spearman")
    res["feature_crosscorr_spearman"] = {a: {b: round(float(fc.loc[a, b]), 4) for b in FEATURES} for a in FEATURES}
    (OC / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({f: res["features"][f]["decision"] for f in FEATURES}, indent=1))


if __name__ == "__main__":
    main()
