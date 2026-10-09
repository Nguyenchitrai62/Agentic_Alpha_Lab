"""oc_presamplebook metrics: IC + block-bootstrap CI, hit rate, diagnostic book P&L.

Reads preds_<anchor>.csv + tmp/fits.json (written by presamplebook.py).
Writes results.json. REPORT.md / SUMMARY.md are written separately after
inspecting results.json. Definitions frozen in PLAN.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
TMP = HERE / "tmp"
ANCHORS = ["2019-03-01", "2019-09-24", "2020-03-01",
           "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24"]
BLOCK = 42
NBOOT = 1000
COST = 0.0002


def spearman(a: pd.Series, b: pd.Series) -> float:
    return float(a.corr(b, method="spearman"))


def block_ci(df: pd.DataFrame, n_boot: int = NBOOT, seed: int = 0):
    """Block bootstrap CI for pooled Spearman IC. Blocks = 42 consecutive
    distinct bars in time order. Returns (point, lo, hi, n_blocks)."""
    d = df.sort_values("open_time").reset_index(drop=True)
    times = d["open_time"].unique()
    blocks = [np.flatnonzero(d["open_time"].isin(times[i:i + BLOCK]))
              for i in range(0, len(times), BLOCK)]
    blocks = [b for b in blocks if len(b) > 0]
    point = spearman(d["pred"], d["label"])
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(n_boot):
        idx = np.concatenate([blocks[i] for i in
                              rng.integers(0, len(blocks), len(blocks))])
        s = d.iloc[idx]
        v = spearman(s["pred"], s["label"])
        if np.isfinite(v):
            stats.append(v)
    if len(stats) == 0 or not np.isfinite(point):
        return point, float("nan"), float("nan"), len(blocks)
    return point, float(np.percentile(stats, 2.5)), \
        float(np.percentile(stats, 97.5)), len(blocks)


def diag_book(df: pd.DataFrame, s_train: float):
    """Vectorised diagnostic (NOT the engine): w = clip(pred/s, -1, 1) per
    coin, set at close t, earns next-bar open-to-open r_next; cost 0.0002 per
    unit turnover; portfolio = equal-weight mean over valid coins."""
    d = df.copy()
    d["w"] = (d["pred"] / s_train).clip(-1, 1)
    d = d[np.isfinite(d["w"]) & np.isfinite(d["r_next"])]
    d = d.sort_values(["sym", "open_time"])
    d["dw"] = d.groupby("sym")["w"].diff().abs()
    first = d.groupby("sym").head(1).index
    d.loc[first, "dw"] = d.loc[first, "w"].abs()  # establishing turnover
    d["coin_net"] = d["w"] * d["r_next"] - COST * d["dw"]
    per_t = d.groupby("open_time")["coin_net"].mean()
    eq = (1 + per_t).cumprod()
    n_days = (pd.to_datetime(d["open_time"]).max()
              - pd.to_datetime(d["open_time"]).min()
              + pd.Timedelta(hours=4)).total_seconds() / 86400.0
    e_end = float(eq.iloc[-1])
    dd = float(np.max(1 - eq / eq.cummax()))
    return {
        "monthly_pct": round(100 * (e_end ** (30.4375 / n_days) - 1), 3),
        "total_pct": round(100 * (e_end - 1), 2),
        "max_dd_pct": round(100 * dd, 2),
        "end_equity": round(e_end, 4),
        "n_bars": int(len(per_t)),
        "n_coin_bars": int(len(d)),
        "turnover_units": round(float(d["dw"].sum()), 1),
        "n_days": round(n_days, 1),
    }


def main():
    fits = json.loads((TMP / "fits.json").read_text())
    years = {}
    for a in ANCHORS:
        df = pd.read_csv(HERE / f"preds_{a}.csv",
                         parse_dates=["open_time"])
        df = df[np.isfinite(df["pred"]) & np.isfinite(df["label"])]
        s_train = float(fits[a]["s_train"])
        ic, lo, hi, nb = block_ci(df)
        per_coin = {}
        for sym, g in df.groupby("sym"):
            ci, clo, chi, _ = block_ci(g)
            hit = float(((np.sign(g["pred"]) == np.sign(g["label"]))).mean())
            per_coin[sym] = {"n": int(len(g)), "ic": round(ci, 4),
                             "ci_lo": round(clo, 4), "ci_hi": round(chi, 4),
                             "hit_rate": round(hit, 4)}
        hit_all = float((np.sign(df["pred"]) == np.sign(df["label"])).mean())
        book = diag_book(df, s_train)
        years[a] = {
            "n": int(len(df)),
            "n_spot_rows": int((df["src"] == "spot").sum()),
            "train_rows": int(fits[a]["train_rows"]),
            "train_ic": float(fits[a].get("train_ic", float("nan"))),
            "s_train": round(s_train, 4),
            "ic_pooled": round(ic, 4), "ic_lo": round(lo, 4),
            "ic_hi": round(hi, 4), "n_blocks": nb,
            "hit_rate": round(hit_all, 4),
            "per_coin": per_coin,
            "diag_book": book,
        }
        print(a, "n=", len(df), "IC=", round(ic, 4),
              f"[{round(lo,4)},{round(hi,4)}]", "hit=", round(hit_all, 4),
              "book %/mo=", book["monthly_pct"], flush=True)
    out = {
        "config": {
            "member": "pooled HGBR(max_depth=4, lr=0.03, iter=400, leaf=300, "
                      "l2=1.0, seed=0) on 17 TV features only; "
                      "label = clip(log(o[t+43]/o[t+1])/(vol42*sqrt(42)),-4,4)",
            "train_rule": "label_end < anchor - 7d",
            "test_rule": "[A, A+365d) rows with realised label",
            "ic": "Spearman pred vs label; 95% block(42)-bootstrap CI, 1000 reps, seed 0",
            "diag_book": "VECTORISED DIAGNOSTIC (not the engine): "
                         "w=clip(pred/s_train,-1,1), next-bar open-to-open, "
                         "cost 0.0002/unit turnover, equal-weight mean, no leverage",
        },
        "years": years,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("results.json written", flush=True)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE.parents[2]))
    main()
