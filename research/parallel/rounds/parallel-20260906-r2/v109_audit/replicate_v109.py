"""Blind v109 audit replication (Part A). Does NOT read research/.../v109/*.

Base: audited v103_v105 replication of v104.
  b_lo  = v92 LO weights  * v92 vol scale   (v92 OOS pred vs y,  h=42)
  b94   = v94 LS weights  * v94 scale       (v94 ensemble pred vs y42, h=42)
  b103  = v103 LS weights * own scale       (v103 pred vs y6, h=6)
  v104 wrapper (v99 constants, leader carry convention).

Gates (per spec): for each book and each daily decision bar tau (every 6th row
of the union 4h index of the three weight frames),
  IC_tau = Spearman(pred, label) pooled over rows with
    t >= tau - 60 days and t + (h+1)*4h <= tau   (NaN pred/label dropped).
  m_tau = clip(IC_tau / 0.10, 0, 1.5); m = 1 if <200 rows or IC not finite.
Forward-fill m_tau to 4h bars (1.0 before the first tau).

Primary: s computed exactly as v104 from UNGATED books
  (0.25 b_lo + 0.25 b94 + 0.5 b103 plus carry) and
  Wt = 0.8 * s * (0.25 b_lo m_lo + 0.25 b94 m94 + 0.5 b103 m103);
  carry exposure 0.6*s (ungated); net as v104.
Secondary: v92 book alone, scale = v92 vol scale * m_lo, through v92.simulate.

OOS predictions are reused from the audited replications (bit-exact to leader
per the v92/v93_v94/v103_v105 audits) to avoid heavy retraining:
  v92_audit/predictions_5asset.csv, v93_v94_audit/predictions_v94.csv,
  v103_v105_audit/predictions_v103.csv.
Weights/vol/simulate are reimplemented inline from the audited formulas.
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[5]
OUT_DIR = Path(__file__).resolve().parent
V92_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v92_audit/predictions_5asset.csv"
V94_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v93_v94_audit/predictions_v94.csv"
V103_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v103_v105_audit/predictions_v103.csv"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0), "execution_stress": (0.0006, 0.0005)}
W_BOOKS, W_CARRY, CARRY_LEV, TARGET, CAP = 0.8, 0.2, 3.0, 0.15, 2.0
GATE_WINDOW_DAYS = 60
GATE_DENOM = 0.10
GATE_CAP = 1.5
GATE_MIN_ROWS = 200


def weights_ls(oos, shorts):
    """Audited v94.weights_ls (also == v92 long-only when shorts=False)."""
    Wdict = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        p = g["pred"].astype(float)
        rib = g["rib"].astype(float)
        long_ = (p.clip(lower=0) / 0.5).clip(upper=1.0).where(rib != -1, 0.0)
        if shorts:
            short = ((-p).clip(lower=0) / 0.5).clip(upper=1.0).where(rib != 1, 0.0)
        else:
            short = 0.0 * long_
        raw = (long_ - short) / (g["vol42"].astype(float) * np.sqrt(PD * 365))
        raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        Wdict[s] = raw
    rawW = pd.DataFrame(Wdict).sort_index()
    row_sum = rawW.abs().sum(axis=1)
    n_nz = (rawW != 0).sum(axis=1).clip(lower=1)
    W = rawW.div(row_sum.clip(lower=1e-9), axis=0).mul(row_sum.gt(0), axis=0)
    W = W.mul((n_nz / 5).clip(upper=1.0), axis=0).fillna(0.0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    W = W.where(keep, np.nan).ffill().fillna(0.0)
    return W


def vol_target_scale(o, W, target=0.20, cap=2.0):
    """Audited v94.vol_target_scale: no fillna in realized, NaN->1."""
    ret1 = o / o.shift(1) - 1
    realized = (W.shift(2) * ret1).sum(axis=1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std(ddof=1) * np.sqrt(PD * 365)
    sc = (target / vol).clip(upper=cap).fillna(1.0)
    sc = sc.replace([np.inf, -np.inf], 2.0).fillna(1.0)
    return sc


def simulate(o, W, scale, fee, slip=0.0):
    """Audited v92.simulate."""
    r = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    Wk = W.mul(scale, axis=0) if isinstance(scale, pd.Series) else W * scale
    turn = Wk.diff().abs().sum(axis=1).fillna(Wk.abs().sum(axis=1))
    funding = Wk.clip(lower=0).sum(axis=1) * 0.00005
    net = (Wk * r).sum(axis=1) - turn * (fee + slip) - funding
    return net, turn


def stats(net, turn):
    eq = (1 + net).cumprod()
    days = len(net) / PD
    g = float(eq.iloc[-1]) if len(eq) else float("nan")
    dd = float(np.max(1 - eq / eq.cummax())) if len(eq) else float("nan")
    return dict(net_pct=round(100 * (g - 1), 2),
                monthly_geometric_net_percent=round(100 * (g ** (30.4375 / days) - 1), 3) if days > 0 else float("nan"),
                max_drawdown_percent=round(100 * dd, 2),
                fills=int((turn > 1e-6).sum()),
                months=round(days / 30.4375, 1),
                bars=int(len(net)))


def yearly_slices(net, turn):
    out = []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        m = (net.index >= a) & (net.index < a + pd.Timedelta(days=365))
        st = stats(net[m], turn[m])
        st["anchor"] = anchor
        out.append(st)
    return out


def compute_gate(oos_long, label_col, h):
    """IC gate per spec. Returns (m_full Series on union idx, tau frame).

    oos_long: DataFrame with columns t (tz-aware), pred, label_col.
    tau: every 6th row of the union 4h index (passed via union_idx).
    """
    raise NotImplementedError("use compute_gates_for_books")


def compute_gates_for_books(books_pred, union_idx):
    """books_pred: dict key -> DataFrame long (t, pred, label). Each has h.

    Returns dict key -> (m_full Series indexed by union_idx, tau DataFrame).
    """
    union_idx = union_idx.sort_values()
    taus = union_idx[::6]
    out = {}
    for key, cfg in books_pred.items():
        df = cfg["df"].copy()
        h = cfg["h"]
        df["t"] = pd.to_datetime(df["t"], utc=True)
        df = df.dropna(subset=["pred", "label"])
        t_ns = df["t"].to_numpy().astype("datetime64[ns]").astype("int64")
        pred = df["pred"].to_numpy(dtype=float)
        lab = df["label"].to_numpy(dtype=float)
        order = np.argsort(t_ns)
        t_ns, pred, lab = t_ns[order], pred[order], lab[order]
        lag_ns = int((h + 1) * 4 * 3600 * 1_000_000_000)
        win_ns = int(60 * 24 * 3600 * 1_000_000_000)
        m_vals = np.empty(len(taus), dtype=float)
        ic_vals = np.empty(len(taus), dtype=float)
        n_vals = np.empty(len(taus), dtype=int)
        tau_ns = taus.to_numpy().astype("datetime64[ns]").astype("int64")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for i, tau in enumerate(tau_ns):
                lo = tau - win_ns
                hi = tau - lag_ns
                l = int(np.searchsorted(t_ns, lo, side="left"))
                r = int(np.searchsorted(t_ns, hi, side="right"))
                n = r - l
                n_vals[i] = n
                if n < GATE_MIN_ROWS:
                    ic_vals[i] = np.nan
                    m_vals[i] = 1.0
                    continue
                a = pred[l:r]
                b = lab[l:r]
                m = np.isfinite(a) & np.isfinite(b)
                if int(m.sum()) < GATE_MIN_ROWS:
                    ic_vals[i] = np.nan
                    m_vals[i] = 1.0
                    continue
                try:
                    ic = float(spearmanr(a[m], b[m]).statistic)
                except Exception:
                    ic = float("nan")
                ic_vals[i] = ic
                if not np.isfinite(ic):
                    m_vals[i] = 1.0
                else:
                    m_vals[i] = float(np.clip(ic / GATE_DENOM, 0.0, GATE_CAP))
        m_tau = pd.Series(m_vals, index=taus)
        ic_tau = pd.Series(ic_vals, index=taus)
        n_tau = pd.Series(n_vals, index=taus)
        m_full = m_tau.reindex(union_idx).ffill().fillna(1.0)
        tau_df = pd.DataFrame({"tau": taus, "IC": ic_vals, "m": m_vals, "n_rows": n_vals})
        out[key] = dict(m_full=m_full, m_tau=m_tau, ic_tau=ic_tau, n_tau=n_tau, tau_df=tau_df)
    return out, taus


def run_v104_wrapper(books_ungated, books_gated, o, carry):
    """s from UNGATED books exactly as v104; Wt gated/ungated; nets per scenario."""
    ret1 = o / o.shift(1) - 1
    realized = W_BOOKS * (books_ungated.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry.shift(1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std(ddof=1) * np.sqrt(PD * 365)
    s = (TARGET / vol).clip(upper=CAP).fillna(1.0)
    s = s.replace([np.inf, -np.inf], 2.0).fillna(1.0)
    Wt_ung = books_ungated.mul(W_BOOKS * s, axis=0)
    Wt_g = books_gated.mul(W_BOOKS * s, axis=0)
    r_fwd = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    carry_exp = W_CARRY * CARRY_LEV * s  # ungated s
    out = {"scale": s, "carry": carry}
    for label, Wt in (("ungated", Wt_ung), ("gated", Wt_g)):
        per_sc = {}
        for sc, (fee, slip) in SCEN.items():
            turn = Wt.diff().abs().sum(axis=1).fillna(Wt.abs().sum(axis=1))
            cost = turn * (fee + slip)
            model_gross = (Wt * r_fwd).sum(axis=1)
            model_funding = Wt.clip(lower=0).sum(axis=1) * 0.00005
            carry_gross = carry_exp * carry
            carry_turn = carry_exp.diff().abs().fillna(0.0)
            carry_cost = carry_turn * 2 * 0.0004 / 1.2
            net = model_gross - cost - model_funding + carry_gross - carry_cost
            per_sc[sc] = dict(net=net, turn=turn, Wt=Wt)
        out[label] = per_sc
    return out


def main():
    o92 = pd.read_csv(V92_CSV, parse_dates=["t"])
    o94 = pd.read_csv(V94_CSV, parse_dates=["t"])
    o103 = pd.read_csv(V103_CSV, parse_dates=["t"])
    for df in (o92, o94, o103):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    o92 = o92.sort_values(["t", "sym"]).reset_index(drop=True)
    o94 = o94.sort_values(["t", "sym"]).reset_index(drop=True)
    o103 = o103.sort_values(["t", "sym"]).reset_index(drop=True)

    W_lo = weights_ls(o92, False)
    W94 = weights_ls(o94, True)
    W103 = weights_ls(o103, True)

    o = o92.pivot_table(index="t", columns="sym", values="open")
    o = o[list(SYMS)].sort_index()
    # sanity: opens identical across books (checked); use single o
    s_lo = vol_target_scale(o, W_lo.reindex(o.index).fillna(0.0), 0.20, 2.0)
    s94 = vol_target_scale(o, W94.reindex(o.index).fillna(0.0), 0.20, 2.0)
    s103 = vol_target_scale(o, W103.reindex(o.index).fillna(0.0), 0.20, 2.0)

    idx = W_lo.index.union(W94.index).union(W103.index).sort_values()
    assert len(idx) == 10950, len(idx)
    W_lo_a = W_lo.reindex(idx).fillna(0.0)
    W94_a = W94.reindex(idx).fillna(0.0)
    W103_a = W103.reindex(idx).fillna(0.0)
    s_lo_a = s_lo.reindex(idx).fillna(1.0)
    s94_a = s94.reindex(idx).fillna(1.0)
    s103_a = s103.reindex(idx).fillna(1.0)
    o = o.reindex(idx).sort_index()

    b_lo = W_lo_a.mul(s_lo_a, axis=0)
    b94 = W94_a.mul(s94_a, axis=0)
    b103 = W103_a.mul(s103_a, axis=0)

    books_pred = {
        "lo": dict(df=pd.DataFrame({"t": o92["t"], "pred": o92["pred"], "label": o92["y"]}), h=42),
        "b94": dict(df=pd.DataFrame({"t": o94["t"], "pred": o94["pred"], "label": o94["y42"]}), h=42),
        "b103": dict(df=pd.DataFrame({"t": o103["t"], "pred": o103["pred"], "label": o103["y6"]}), h=6),
    }
    gates, taus = compute_gates_for_books(books_pred, idx)
    m_lo = gates["lo"]["m_full"]
    m94 = gates["b94"]["m_full"]
    m103 = gates["b103"]["m_full"]

    books_ung = 0.25 * b_lo + 0.25 * b94 + 0.5 * b103
    books_g = 0.25 * b_lo.mul(m_lo, axis=0) + 0.25 * b94.mul(m94, axis=0) + 0.5 * b103.mul(m103, axis=0)

    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    carry = carry.reindex(idx)["carry"].astype(float).fillna(0.0)

    wrap = run_v104_wrapper(books_ung, books_g, o, carry)

    primary = {}
    for label in ("ungated", "gated"):
        per_sc = {}
        for sc in SCEN:
            net = wrap[label][sc]["net"]
            turn = wrap[label][sc]["turn"]
            per_sc[sc] = yearly_slices(net, turn)
        primary[label] = per_sc

    # secondary: v92 book alone, scale = s_lo * m_lo, via v92.simulate
    scale_ung_lo = s_lo_a
    scale_g_lo = s_lo_a * m_lo
    secondary = {}
    for label, scale in (("ungated", scale_ung_lo), ("gated", scale_g_lo)):
        per_sc = {}
        for sc, (fee, slip) in SCEN.items():
            net, turn = simulate(o, W_lo_a, scale, fee, slip)
            per_sc[sc] = yearly_slices(net, turn)
        secondary[label] = per_sc

    # mean gates per anchor year (over 4h bars)
    gate_means = []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        m = (idx >= a) & (idx < a + pd.Timedelta(days=365))
        gate_means.append(dict(
            anchor=anchor,
            m_lo=round(float(m_lo[m].mean()), 4),
            m94=round(float(m94[m].mean()), 4),
            m103=round(float(m103[m].mean()), 4),
            n_taus=int(((taus >= a) & (taus < a + pd.Timedelta(days=365))).sum()),
            n_bars=int(m.sum()),
        ))

    result = {
        "anchors": list(ANCHORS),
        "gate_spec": ("per book OOS (v92: pred vs y h=42; v94 ensemble: pred vs y42 h=42; "
                      "v103: pred vs y6 h=6); tau = every 6th row of union 4h index "
                      "(union 10950 bars -> 1825 taus, iloc[::6]); IC_tau = Spearman pooled over "
                      "rows t >= tau-60d and t+(h+1)*4h <= tau, NaN dropped; "
                      "m_tau = clip(IC/0.10, 0, 1.5); m=1 if <200 rows or IC not finite; "
                      "ffill to 4h bars, 1.0 before first tau"),
        "books_spec": ("b_lo = v92 LO weights (weights_ls shorts=False) * v92 vol scale (20% cap2); "
                       "b94 = v94 LS weights (shorts=True) * v94 scale; "
                       "b103 = v103 LS weights (shorts=True) * own scale; "
                       "OOS from audited CSVs (v92_audit/predictions_5asset.csv, "
                       "v93_v94_audit/predictions_v94.csv, v103_v105_audit/predictions_v103.csv)"),
        "wrapper_spec": ("s from UNGATED books exactly as v104/v99: realized=0.8*(books.shift(2)*ret1).sum"
                         "+0.6*carry.shift(1); vol trailing 360/min120*sqrt(2190); s=min(0.15/vol,2) NaN->1; "
                         "Wt_ung=0.8*s*books_ung; Wt_g=0.8*s*books_gated; carry_exp=0.6*s (ungated s); "
                         "r_fwd=o[t+2]/o[t+1]-1; fee on turn + 0.00005/bar long funding; "
                         "carry earns carry_exp[t]*carry[t], cost |diff|*2*0.0004/1.2 first diff 0"),
        "union_bars": int(len(idx)),
        "n_taus": int(len(taus)),
        "tau_start": str(taus[0]),
        "tau_end": str(taus[-1]),
        "gate_means_per_anchor_year": gate_means,
        "primary_ungated_yearly": primary["ungated"],
        "primary_gated_yearly": primary["gated"],
        "secondary_v92_ungated_yearly": secondary["ungated"],
        "secondary_v92_gated_yearly": secondary["gated"],
        "data": {"v92_oos": "v92_audit/predictions_5asset.csv",
                 "v94_oos": "v93_v94_audit/predictions_v94.csv",
                 "v103_oos": "v103_v105_audit/predictions_v103.csv",
                 "carry": "artifacts/research/carry/carry_oos_fee0.0004.parquet",
                 "oos_span": [str(idx[0]), str(idx[-1])]},
        "execution": {"fee_per_unit_turnover": 0.0002,
                      "long_funding_per_4h_bar": 5e-05,
                      "scenarios": {k: {"fee": v[0], "slip": v[1]} for k, v in SCEN.items()},
                      "wrapper_constants": {"W_BOOKS": W_BOOKS, "W_CARRY": W_CARRY,
                                            "CARRY_LEV": CARRY_LEV, "TARGET": TARGET, "CAP": CAP}},
        "assumptions": ["OOS preds/labels reused from audited CSVs (no retrain; deterministic per prior audits)",
                        "weights/vol/simulate reimplemented from audited v92/v94 formulas (daily rebalance, ffill)",
                        "gates causal: label realized before tau via t+(h+1)*4h<=tau; s from UNGATED books only",
                        "yearly slices [anchor, anchor+365d), 2190 bars each; fills = turnover bars >1e-6"],
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(result, f, indent=2)
    # supporting artifacts
    pd.DataFrame({"t": idx, "m_lo": m_lo.values, "m94": m94.values, "m103": m103.values,
                  "s": wrap["scale"].values}).to_csv(OUT_DIR / "gates.csv", index=False)
    for key in gates:
        gates[key]["tau_df"].to_csv(OUT_DIR / f"gates_tau_{key}.csv", index=False)
    for label in ("ungated", "gated"):
        for sc in SCEN:
            net = wrap[label][sc]["net"]
            turn = wrap[label][sc]["turn"]
            pd.DataFrame({"t": net.index, "net": net.values, "turnover": turn.values}).to_csv(
                OUT_DIR / f"equity_primary_{label}_{sc}.csv", index=False)
    for label in ("ungated", "gated"):
        for sc in SCEN:
            net, turn = simulate(o, W_lo_a, scale_g_lo if label == "gated" else scale_ung_lo,
                                 SCEN[sc][0], SCEN[sc][1])
            pd.DataFrame({"t": net.index, "net": net.values, "turnover": turn.values}).to_csv(
                OUT_DIR / f"equity_secondary_v92_{label}_{sc}.csv", index=False)
    print(json.dumps({"gate_means": gate_means,
                      "primary_gated_normal": primary["gated"]["normal"],
                      "primary_ungated_normal": primary["ungated"]["normal"]}, indent=2))


if __name__ == "__main__":
    main()
