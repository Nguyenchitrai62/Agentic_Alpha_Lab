"""Blind v115 audit replication (Part A). Does NOT read research/.../v115/*.

Base (per OPENCODE_V115_AUDIT.md):
  audited v113_v114 replication (extended v114 panel: predictions_v114_v92.csv,
    predictions_v114_v94.csv), v103_v105 (predictions_v103.csv, v104 strict fill
    rule + cost path) and v110 (sequential governor engine).

Spec:
  b_lo  = v92 LO weights (v92 model trained on v114 panel) * v92 vol scale (v114)
  b94   = v94 LS ensemble weights (trained on v114 panel) * v94 vol scale (v114)
  b103  = v103 LS weights * own vol scale (v103 panel)
  Union index restricted to t >= first v103 panel t.
  books = 0.25 b_lo + 0.25 b94 + 0.5 b103
  v110 sequential engine (panel opens from v103 panel):
    target 0.15 ungoverned (primary), 0.25 governed (secondary),
    three v92 scenarios; yearly net/DD + full-path DD.
  Hidden year: v104 fill rule + v104 cost path, target 0.15, vectorised over the
    whole index as in v104: net/DD/maker rate.

Blind choices (documented):
  - No retraining: weights/scales recomputed from audited OOS prediction CSVs
    with inline audited formulas (v92 weights_from LO, v94 weights_ls LS,
    20%-cap-2 vol_target_scale with W.shift(2), trailing 360/min-120). This is
    replay, not heavy local training (per AGENTS.md compute preference).
  - v114 OOS index == v103 OOS index (10950 bars 2021-09-24..2026-09-23 20:00);
    the t >= first-v103-t restriction is a no-op, applied literally.
  - Engine opens from the v103 OOS opens (candidate returns p103 as panel).
  - Sequential loop mirrors v110_dd_governor.run line-for-line (live mask
    [2021-09-24, 2026-09-23), governor j=i-2, 540-bar peak incl pre-start 1,
    s from combined books with W_BOOKS=0.8 / W_CARRY*LEV=0.6, cap 2).
  - Hidden path mirrors v104 vectorised path (s target 0.15 over whole index,
    Wt=0.8*s*books, r_next=o[t+2]/o[t+1]-1, carry_exp=0.6*s, v104 fill_strict
    with [T+2m,T+14m] through-window, T+15m fallback, missing-T taker).
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
HIDDEN = pd.Timestamp("2025-09-24", tz="UTC")
GOV_WIN = 90 * PD  # 540 bars


def weights_lo(oos):
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
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


def weights_ls(oos):
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
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
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


def run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip, governed):
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
            gi = 1.0
            if governed and i >= 2:
                j = i - 2
                lo = max(0, j - GOV_WIN + 1)
                peak = float(np.max(eq[lo: j + 1]))
                peak = max(1.0, peak)
                gi = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0.0, 1.0))
            w = W_BOOKS * s_vals[i] * books_vals[i] * gi
            c = W_CARRY * CARRY_LEV * s_vals[i] * gi
        else:
            gi = 1.0
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
        g[i] = gi
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


def load_1m(sym):
    d = ROOT / ("data/raw/btc_intraday_20260924" if sym == "BTCUSDT" else "data/raw/majors_intraday_20260924")
    pat = "klines_1m_202[56].parquet" if sym == "BTCUSDT" else f"{sym}_1m_202[56].parquet"
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low"]) for f in sorted(d.glob(pat))])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    return m.drop_duplicates("open_time").set_index("open_time").sort_index()


def fill_strict_v104(W):
    rel = pd.DataFrame(0.0, index=W.index, columns=W.columns)
    maker = pd.DataFrame(True, index=W.index, columns=W.columns)
    dW = W.diff().fillna(W)
    for s in W.columns:
        m = load_1m(s)
        for t in dW.index[(dW[s].abs() > 1e-9) & (dW.index >= HIDDEN)]:
            T = t + pd.Timedelta(hours=4)
            buy = dW.at[t, s] > 0
            if T not in m.index:
                maker.at[t, s] = False
                rel.at[t, s] = 0.0002 if buy else -0.0002
                continue
            p0 = m.at[T, "open"]
            w = m.loc[T + pd.Timedelta(minutes=2): T + pd.Timedelta(minutes=14)]
            through = (w["low"] < p0).any() if buy else (w["high"] > p0).any()
            if not through:
                T15 = T + pd.Timedelta(minutes=15)
                px = m.at[T15, "open"] if T15 in m.index else p0
                rel.at[t, s] = px / p0 - 1 + (0.0002 if buy else -0.0002)
                maker.at[t, s] = False
    return rel, maker


def main():
    o114_lo = pd.read_csv(V114_LO_CSV, parse_dates=["t"])
    o114_ls = pd.read_csv(V114_LS_CSV, parse_dates=["t"])
    o103_df = pd.read_csv(V103_CSV, parse_dates=["t"])
    for df in (o114_lo, o114_ls, o103_df):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    o114_lo = o114_lo.sort_values(["t", "sym"]).reset_index(drop=True)
    o114_ls = o114_ls.sort_values(["t", "sym"]).reset_index(drop=True)
    o103_df = o103_df.sort_values(["t", "sym"]).reset_index(drop=True)

    W_lo = weights_lo(o114_lo)
    W94 = weights_ls(o114_ls)
    W103 = weights_ls(o103_df)

    o_v114 = o114_lo.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    o_v103 = o103_df.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()

    s_lo = vol_scale(o_v114, W_lo.reindex(o_v114.index).fillna(0.0))
    s94 = vol_scale(o_v114, W94.reindex(o_v114.index).fillna(0.0))
    s103 = vol_scale(o_v103, W103.reindex(o_v103.index).fillna(0.0))

    idx = W_lo.index.union(W94.index).union(W103.index).sort_values()
    first_v103 = o_v103.index.min()
    idx = idx[idx >= first_v103]
    b_lo = W_lo.reindex(idx).fillna(0.0).mul(s_lo.reindex(idx).fillna(1.0), axis=0)
    b94 = W94.reindex(idx).fillna(0.0).mul(s94.reindex(idx).fillna(1.0), axis=0)
    b103 = W103.reindex(idx).fillna(0.0).mul(s103.reindex(idx).fillna(1.0), axis=0)
    books = 0.25 * b_lo + 0.25 * b94 + 0.5 * b103
    o = o_v103.reindex(idx).sort_index()
    books = books[o.columns]

    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    carry_s = carry.reindex(idx)["carry"].astype(float).fillna(0.0)

    # portfolio vol targeting from combined books (v99/v104 convention)
    ret1 = o / o.shift(1) - 1
    targets = {"primary_t15": (0.15, False), "secondary_t25_governed": (0.25, True)}
    s_by_key = {}
    for key, (tgt, _gov) in targets.items():
        realized = W_BOOKS * (books.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
        vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
        s = (tgt / vol).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
        s_by_key[key] = s

    live_mask = np.asarray((idx >= START) & (idx < END))
    o_vals = o.to_numpy(dtype=float)
    books_vals = books.to_numpy(dtype=float)
    carry_vals = carry_s.to_numpy(dtype=float)

    out = {"version": "v115_audit_replication"}
    for key, (tgt, gov) in targets.items():
        s_vals = s_by_key[key].to_numpy(dtype=float)
        res = {}
        for sc, (fee, slip) in SCEN.items():
            net, turn, g, _eq = run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip, gov)
            net_s = pd.Series(net, index=idx)
            turn_s = pd.Series(turn, index=idx)
            g_s = pd.Series(g, index=idx)
            res[sc] = summarize_seq(net_s, turn_s, g_s)
            print(key, sc, res[sc]["monthly_pct"], res[sc]["worst_year_dd"], res[sc]["full_path_dd"], flush=True)
        out[key] = res

    # hidden year: v104 cost path, target 0.15, vectorised over whole index
    realized_h = W_BOOKS * (books.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
    vol_h = realized_h.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    s_h = (0.15 / vol_h).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
    Wt = books.mul(W_BOOKS * s_h, axis=0)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    carry_exp = W_CARRY * CARRY_LEV * s_h
    rel, maker = fill_strict_v104(Wt)
    dW = Wt.diff().fillna(Wt)
    rate = np.where(maker.reindex_like(dW).to_numpy(), 0.0002, 0.0005)
    cost = pd.Series((dW.abs().to_numpy() * rate).sum(axis=1), index=idx) + (dW * rel.reindex_like(dW).fillna(0.0)).sum(axis=1)
    net_h = (Wt * r_next).sum(axis=1) - cost - Wt.clip(lower=0).sum(axis=1) * 0.00005 + carry_exp * carry_s - carry_exp.diff().abs().fillna(0.0) * 2 * 0.0004 / 1.2
    turn_h = dW.abs().sum(axis=1)
    mk = (idx >= HIDDEN) & (idx < HIDDEN + pd.Timedelta(days=365))
    orders = (dW.abs() > 1e-9) & (idx >= HIDDEN)[:, None]
    maker_rate = round(float(maker[orders].stack().mean()), 3)
    hid_stats = stats(net_h[mk], turn_h[mk])
    out["hidden_year_1m_execution_strict"] = dict(**hid_stats, maker_fill_rate=maker_rate)
    print("hidden", out["hidden_year_1m_execution_strict"], flush=True)

    out["meta"] = {
        "anchors": list(ANCHORS),
        "union_bars": int(len(idx)),
        "n_live_bars": int(live_mask.sum()),
        "oos_span": [str(idx[0]), str(idx[-1])],
        "first_v103_t": str(first_v103),
        "books_spec": "books=0.25*b_lo(v114 LO*scale114)+0.25*b94(v114 LS*scale114)+0.5*b103(v103 LS*scale103); union t>=first v103 t",
        "wrapper_spec": "realized=0.8*sum(books.shift(2)*ret1)+0.6*carry.shift(1); vol rolling-360 min-120 *sqrt(2190); s=min(target/vol,2) NaN->1; live [2021-09-24,2026-09-23); governor j=i-2 peak=max(E j-539..j incl 1) DD=1-Ej/peak g=clip((0.20-DD)/0.10,0,1); w=0.8*s*books*g c=0.6*s*g; net=w*fwd-|dw|(fee+slip)-0.00005*long+c*carry-|dc|*2*0.0004/1.2",
        "hidden_spec": "v104 vectorised path target 0.15 over whole index; v104 fill_strict [T+2m,T+14m] through -> maker 0.0002 else taker 0.0005 at T+15m +0.0002 adverse; missing-T taker at 4h open +/-0.0002",
        "scenarios": {k: {"fee": v[0], "slip": v[1]} for k, v in SCEN.items()},
        "data": {
            "v114_lo": "v113_v114_audit/predictions_v114_v92.csv",
            "v114_ls": "v113_v114_audit/predictions_v114_v94.csv",
            "v103": "v103_v105_audit/predictions_v103.csv",
            "carry": "artifacts/research/carry/carry_oos_fee0.0004.parquet",
            "opens_engine": "v103 OOS opens",
            "scales": "v114 opens for b_lo/b94; v103 opens for b103; target 0.20 cap 2",
        },
        "assumptions": [
            "No retraining; audited OOS CSVs + inline audited formulas (replay only).",
            "v114 and v103 OOS spans identical; t>=first-v103-t restriction applied literally.",
            "Yearly slices [anchor,anchor+365d); full-path DD over live-span equity.",
        ],
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    books.to_csv(OUT_DIR / "books.csv")
    pd.DataFrame({"t": idx, "s_primary_t15": s_by_key["primary_t15"].values,
                  "s_secondary_t25": s_by_key["secondary_t25_governed"].values,
                  "s_hidden_t15": s_h.values}).to_csv(OUT_DIR / "scales.csv", index=False)
    print(json.dumps({"union": len(idx), "n_live": int(live_mask.sum())}, indent=2))


if __name__ == "__main__":
    main()
