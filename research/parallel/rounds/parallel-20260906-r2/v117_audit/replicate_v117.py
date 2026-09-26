"""Blind v117 audit replication (Part A). Does NOT read research/.../v117/* nor v115/*.

Base (per OPENCODE_V117_AUDIT.md): audited v115 replication (replicate_v115.py):
  b_lo  = v92 LO weights (v114 panel) * v92 vol scale (v114 opens)
  b94   = v94 LS ensemble weights (v114 panel) * v94 vol scale (v114 opens)
  b103  = v103 LS weights * own vol scale (v103 panel)
  Union index restricted to t >= first v103 panel t.
  books = 0.25 b_lo + 0.25 b94 + 0.5 b103
  v110 sequential engine (panel opens from v103 panel):
    target 0.15 ungoverned primary, three v92 scenarios; yearly net/DD + full-path DD.

v117 variation (blind, from assignment text only):
  v92 LO and v94 LS weight frames keep every k-th row of their own index
  (k = 12 primary, 42 secondary; 6 = v115 reference) and forward-fill;
  v103 LS book stays at k = 6.
  Vol scales of each book computed on the k-rebalanced weights as in v115
  (20%-cap-2, W.shift(2), trailing 360/min-120, NaN->1).
  Portfolio wrapper s (target 0.15) recomputed from the combined k-books
  with the v99/v104 convention; v110 sequential engine ungoverned.

Blind choices (documented, fixed before running):
  - No retraining: weights/scales recomputed from audited OOS prediction CSVs
    with inline audited formulas (same as replicate_v115.py). Replay only.
  - "keep every k-th row of their own index" = positional arange(len(W)) % k == 0
    on each book's own frame (same convention as v115 PD=6 daily), then ffill.
  - v103 book always k=6.
  - Union + t>=first-v103-t restriction applied literally (no-op, spans identical).
  - Engine opens from v103 OOS opens; live [2021-09-24, 2026-09-23).
  - Primary only (target 0.15 ungoverned); three scenarios; no hidden year.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
OUT_DIR = Path(__file__).resolve().parent
V114_LO_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v92.csv"
V114_LS_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v94.csv"
V103_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v103_v105_audit/predictions_v103.csv"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6
ANN = np.sqrt(PD * 365)
ROLL, ROLL_MIN, CAP = 60 * PD, 20 * PD, 2.0
W_BOOKS, W_CARRY, CARRY_LEV = 0.8, 0.2, 3.0
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0), "execution_stress": (0.0006, 0.0005)}
START = pd.Timestamp("2021-09-24", tz="UTC")
END = START + pd.Timedelta(days=5 * 365)  # 2026-09-23 exclusive
TARGET = 0.15


def weights_lo(oos, k):
    Wd = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        sig = g["pred"].clip(lower=0) / 0.5
        sig = sig.where(g["rib"] != -1, 0.0).clip(upper=1.0)
        Wd[s] = sig / (g["vol42"].astype(float) * ANN)
    W = pd.DataFrame(Wd).sort_index().fillna(0.0)
    gross = W.abs().sum(axis=1)
    n_pos = W.gt(0).sum(axis=1).clip(lower=1)
    W = W.div(gross.clip(lower=1e-9), axis=0).mul(gross.gt(0), axis=0)
    W = W.mul((n_pos / 5).clip(upper=1.0), axis=0)
    keep = pd.Series(np.arange(len(W)) % k == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


def weights_ls(oos, k):
    Wd = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        p = g["pred"].astype(float)
        rib = g["rib"].astype(float)
        long_ = (p.clip(lower=0) / 0.5).clip(upper=1.0).where(rib != -1, 0.0)
        short = ((-p).clip(lower=0) / 0.5).clip(upper=1.0).where(rib != 1, 0.0)
        raw = (long_ - short) / (g["vol42"].astype(float) * ANN)
        Wd[s] = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    rawW = pd.DataFrame(Wd).sort_index()
    gross = rawW.abs().sum(axis=1)
    n_nz = (rawW != 0).sum(axis=1).clip(lower=1)
    W = rawW.div(gross.clip(lower=1e-9), axis=0).mul(gross.gt(0), axis=0)
    W = W.mul((n_nz / 5).clip(upper=1.0), axis=0).fillna(0.0)
    keep = pd.Series(np.arange(len(W)) % k == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


def vol_scale(o, W, target=0.20):
    ret1 = o / o.shift(1) - 1
    realized = (W.shift(2) * ret1).sum(axis=1)
    vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    sc = (target / vol).clip(upper=CAP).fillna(1.0)
    return sc.replace([np.inf, -np.inf], CAP).fillna(1.0)


def stats(net, turn):
    eq = (1 + net).cumprod()
    days = len(net) / PD
    g = float(eq.iloc[-1]) if len(eq) else float("nan")
    dd = float(np.max(1 - eq / eq.cummax())) if len(eq) else float("nan")
    return dict(
        net_pct=round(100 * (g - 1), 2),
        monthly_geometric_net_percent=round(100 * (g ** (30.4375 / days) - 1), 3) if days > 0 else float("nan"),
        max_drawdown_percent=round(100 * dd, 2),
        sharpe=round(float(net.mean() / net.std() * ANN), 2) if float(net.std()) > 0 else 0.0,
        fills=int((turn > 1e-6).sum()),
        months=round(days / 30.4375, 1),
    )


def run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip):
    n, k = o_vals.shape[0], o_vals.shape[1]
    fwd = np.full_like(o_vals, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        fm = o_vals[2:] / o_vals[1:-1] - 1.0
    fm = np.where(np.isfinite(fm), fm, 0.0)
    fwd[: n - 2] = fm
    net = np.zeros(n)
    turn = np.zeros(n)
    g = np.ones(n)
    eq = np.ones(n)
    prev_w = np.zeros(k)
    prev_c = 0.0
    for i in range(n):
        if live_mask[i]:
            w = W_BOOKS * s_vals[i] * books_vals[i]
            c = W_CARRY * CARRY_LEV * s_vals[i]
        else:
            w = np.zeros(k)
            c = 0.0
        gross = float(np.sum(w * fwd[i]))
        tcost = float(np.sum(np.abs(w - prev_w)) * (fee + slip))
        fund = float(np.sum(np.maximum(w, 0.0)) * 0.00005)
        cgross = float(c * carry_vals[i])
        ccost = float(abs(c - prev_c) * 2 * 0.0004 / 1.2)
        ni = gross - tcost - fund + cgross - ccost
        eq[i] = (eq[i - 1] if i else 1.0) * (1 + ni)
        net[i] = ni
        turn[i] = float(np.sum(np.abs(w - prev_w)))
        prev_w, prev_c = w, c
    return net, turn, g, eq


def summarize_seq(net_s, turn_s, g_s):
    ys = []
    for a in ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = (net_s.index >= a0) & (net_s.index < a0 + pd.Timedelta(days=365))
        ys.append(dict(anchor=a, **stats(net_s[mk], turn_s[mk]), mean_g=round(float(g_s[mk].mean()), 3)))
    geo = np.prod([1 + y["net_pct"] / 100 for y in ys]) ** (1 / 5) - 1
    full = (net_s.index >= START) & (net_s.index < END)
    eq = (1 + net_s[full]).cumprod()
    return dict(
        yearly=ys,
        monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
        worst_year_dd=max(y["max_drawdown_percent"] for y in ys),
        full_path_dd=round(100 * float((1 - eq / eq.cummax()).max()), 2),
    )


def main():
    o114_lo = pd.read_csv(V114_LO_CSV, parse_dates=["t"])
    o114_ls = pd.read_csv(V114_LS_CSV, parse_dates=["t"])
    o103_df = pd.read_csv(V103_CSV, parse_dates=["t"])
    for df in (o114_lo, o114_ls, o103_df):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    o114_lo = o114_lo.sort_values(["t", "sym"]).reset_index(drop=True)
    o114_ls = o114_ls.sort_values(["t", "sym"]).reset_index(drop=True)
    o103_df = o103_df.sort_values(["t", "sym"]).reset_index(drop=True)

    o_v114 = o114_lo.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    o_v103 = o103_df.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    first_v103 = o_v103.index.min()

    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)

    out = {"version": "v117_audit_replication"}
    scales_frame = None
    for k, key in ((12, "k12_primary_t15"), (42, "k42_primary_t15"), (6, "k6_reference_primary_t15")):
        W_lo = weights_lo(o114_lo, k)
        W94 = weights_ls(o114_ls, k)
        W103 = weights_ls(o103_df, 6)

        s_lo = vol_scale(o_v114, W_lo.reindex(o_v114.index).fillna(0.0))
        s94 = vol_scale(o_v114, W94.reindex(o_v114.index).fillna(0.0))
        s103 = vol_scale(o_v103, W103.reindex(o_v103.index).fillna(0.0))

        idx = W_lo.index.union(W94.index).union(W103.index).sort_values()
        idx = idx[idx >= first_v103]
        b_lo = W_lo.reindex(idx).fillna(0.0).mul(s_lo.reindex(idx).fillna(1.0), axis=0)
        b94 = W94.reindex(idx).fillna(0.0).mul(s94.reindex(idx).fillna(1.0), axis=0)
        b103 = W103.reindex(idx).fillna(0.0).mul(s103.reindex(idx).fillna(1.0), axis=0)
        books = 0.25 * b_lo + 0.25 * b94 + 0.5 * b103
        o = o_v103.reindex(idx).sort_index()
        books = books[o.columns]

        carry_s = carry.reindex(idx)["carry"].astype(float).fillna(0.0)
        ret1 = o / o.shift(1) - 1
        realized = W_BOOKS * (books.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
        vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
        s = (TARGET / vol).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)

        live_mask = np.asarray((idx >= START) & (idx < END))
        o_vals = o.to_numpy(dtype=float)
        books_vals = books.to_numpy(dtype=float)
        carry_vals = carry_s.to_numpy(dtype=float)
        s_vals = s.to_numpy(dtype=float)

        res = {}
        for sc, (fee, slip) in SCEN.items():
            net, turn, g, _eq = run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip)
            net_s = pd.Series(net, index=idx)
            turn_s = pd.Series(turn, index=idx)
            g_s = pd.Series(g, index=idx)
            res[sc] = summarize_seq(net_s, turn_s, g_s)
            print(key, sc, res[sc]["monthly_pct"], res[sc]["worst_year_dd"], res[sc]["full_path_dd"], flush=True)
        out[key] = res

        books.to_csv(OUT_DIR / f"books_k{k}.csv")
        col = pd.DataFrame({"t": idx, f"s_k{k}_t15": s.values})
        scales_frame = col if scales_frame is None else scales_frame.merge(col, on="t", how="outer")
        if k == 12:
            out_k12_meta = {"union_bars": int(len(idx)), "n_live_bars": int(live_mask.sum()),
                            "oos_span": [str(idx[0]), str(idx[-1])]}

    scales_frame.to_csv(OUT_DIR / "scales.csv", index=False)
    out["meta"] = {
        "anchors": list(ANCHORS),
        "union_bars": out_k12_meta["union_bars"],
        "n_live_bars": out_k12_meta["n_live_bars"],
        "oos_span": out_k12_meta["oos_span"],
        "first_v103_t": str(first_v103),
        "target": TARGET,
        "governed": False,
        "books_spec": "books=0.25*b_lo(v114 LO k-rebalanced*scale114_k)+0.25*b94(v114 LS k-rebalanced*scale114_k)+0.5*b103(v103 LS k=6*scale103); union t>=first v103 t; k=12 primary, 42 secondary, 6 reference; v103 stays k=6",
        "rebalance_spec": "keep every k-th row of own index (arange%k==0) then ffill; vol scales 20%-cap-2 on k-rebalanced W (W.shift(2), trailing 360/min-120, NaN->1)",
        "wrapper_spec": "realized=0.8*sum(books.shift(2)*ret1)+0.6*carry.shift(1); vol rolling-360 min-120 *sqrt(2190); s=min(0.15/vol,2) NaN->1; live [2021-09-24,2026-09-23); ungoverned (mean_g=1); w=0.8*s*books c=0.6*s; net=w*fwd-|dw|(fee+slip)-0.00005*long+c*carry-|dc|*2*0.0004/1.2",
        "scenarios": {kk: {"fee": v[0], "slip": v[1]} for kk, v in SCEN.items()},
        "data": {
            "v114_lo": "v113_v114_audit/predictions_v114_v92.csv",
            "v114_ls": "v113_v114_audit/predictions_v114_v94.csv",
            "v103": "v103_v105_audit/predictions_v103.csv",
            "carry": "artifacts/research/carry/carry_oos_fee0.0004.parquet",
            "opens_engine": "v103 OOS opens",
            "scales": "v114 opens for b_lo/b94 (k-rebalanced); v103 opens for b103 (k=6); target 0.20 cap 2",
        },
        "assumptions": [
            "No retraining; audited OOS CSVs + inline audited formulas (replay only).",
            "Yearly slices [anchor,anchor+365d); full-path DD over live-span equity.",
        ],
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"union": out["meta"]["union_bars"], "n_live": out["meta"]["n_live_bars"]}, indent=2))


if __name__ == "__main__":
    main()
