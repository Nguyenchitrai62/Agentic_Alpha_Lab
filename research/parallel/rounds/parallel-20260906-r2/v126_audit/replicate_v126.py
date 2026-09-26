"""Blind v126 audit replication (Part A). Does NOT read research/.../v126/*.

Base (per OPENCODE_V126_AUDIT.md):
  audited v123_v125 replication (v125 un-subsampled weight formulas and phase
  helper). Audited v115 books path (v114 LO/LS + v103 LS OOS CSVs).

Spec:
  for phase p in 0..5, all three v115 books keep rows with position % 6 == p
  (ffill, fillna 0), own vol scales (0.20 cap 2, W.shift(2), trailing 360 /
  min-120), v115 primary portfolio (books = 0.25*b_lo + 0.25*b94 + 0.5*b103,
  target 0.15, ungoverned, v110 sequential engine).
  Report per phase monthly/full-path DD per scenario, yearly normal nets, and
  the phase mean/min/max (phase 0 must equal v115).

Blind choices documented in replication.json meta.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
OUT_DIR = Path(__file__).resolve().parent

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6
ANN = np.sqrt(PD * 365)
ROLL, ROLL_MIN, CAP = 60 * PD, 20 * PD, 2.0
W_BOOKS, W_CARRY, CARRY_LEV = 0.8, 0.2, 3.0
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0), "execution_stress": (0.0006, 0.0005)}
START = pd.Timestamp("2021-09-24", tz="UTC")
END = START + pd.Timedelta(days=5 * 365)

V114_LO_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v92.csv"
V114_LS_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v94.csv"
V103_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v103_v105_audit/predictions_v103.csv"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"


def weights_lo_from_oos(oos):
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
    return W


def weights_ls_from_oos(oos):
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
    return W


def phase_frame(W_raw, phase):
    keep = pd.Series(np.arange(len(W_raw)) % PD == phase, index=W_raw.index)
    return W_raw.where(keep, np.nan).ffill().fillna(0.0)


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


def yearly(net, turn):
    out = []
    for a in ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        m = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
        st = stats(net[m], turn[m])
        st["anchor"] = a
        out.append(st)
    return out


def run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip):
    n, k = o_vals.shape
    fwd = np.zeros_like(o_vals)
    with np.errstate(divide="ignore", invalid="ignore"):
        fm = o_vals[2:] / o_vals[1:-1] - 1.0
    fm = np.where(np.isfinite(fm), fm, 0.0)
    fwd[: n - 2] = fm
    net = np.zeros(n)
    turn = np.zeros(n)
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
        net[i] = gross - tcost - fund + cgross - ccost
        turn[i] = float(np.sum(np.abs(w - prev_w)))
        prev_w, prev_c = w, c
    return net, turn


def summarize_seq(net_s, turn_s):
    ys = yearly(net_s, turn_s)
    geo = np.prod([1 + y["net_pct"] / 100 for y in ys]) ** (1 / 5) - 1
    full = (net_s.index >= START) & (net_s.index < END)
    eq = (1 + net_s[full]).cumprod()
    return dict(yearly=ys, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
                worst_year_dd=max(y["max_drawdown_percent"] for y in ys),
                full_path_dd=round(100 * float((1 - eq / eq.cummax()).max()), 2))


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

    Wlo_raw = weights_lo_from_oos(o114_lo)
    W94_raw = weights_ls_from_oos(o114_ls)
    W103_raw = weights_ls_from_oos(o103_df)

    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)

    first_v103 = o_v103.index.min()

    phases = {}
    for p in range(PD):
        Wlo_p = phase_frame(Wlo_raw, p)
        W94_p = phase_frame(W94_raw, p)
        # mirror v125 helper: W103 raw index equals o_v103 index; phase on raw frame
        W103_p = phase_frame(W103_raw, p)
        s_lo = vol_scale(o_v114.reindex(Wlo_p.index).ffill(), Wlo_p)
        s94 = vol_scale(o_v114.reindex(W94_p.index).ffill(), W94_p)
        s103 = vol_scale(o_v103.reindex(W103_p.index), W103_p)
        idx = Wlo_p.index.union(W94_p.index).union(W103_p.index).sort_values()
        idx = idx[idx >= first_v103]
        b_lo = Wlo_p.reindex(idx).fillna(0.0).mul(s_lo.reindex(idx).fillna(1.0), axis=0)
        b94 = W94_p.reindex(idx).fillna(0.0).mul(s94.reindex(idx).fillna(1.0), axis=0)
        b103 = W103_p.reindex(idx).fillna(0.0).mul(s103.reindex(idx).fillna(1.0), axis=0)
        books = 0.25 * b_lo + 0.25 * b94 + 0.5 * b103
        o = o_v103.reindex(idx).sort_index()
        books = books[o.columns]
        carry_s = carry.reindex(idx)["carry"].astype(float).fillna(0.0)
        ret1 = o / o.shift(1) - 1
        realized = W_BOOKS * (books.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
        vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
        s15 = (0.15 / vol).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
        live_mask = np.asarray((idx >= START) & (idx < END))
        o_vals = o.to_numpy(dtype=float)
        books_vals = books.to_numpy(dtype=float)
        carry_vals = carry_s.to_numpy(dtype=float)
        s_vals = s15.to_numpy(dtype=float)
        res = {}
        for sc, (fee, slip) in SCEN.items():
            net, turn = run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip)
            res[sc] = summarize_seq(pd.Series(net, index=idx), pd.Series(turn, index=idx))
            print(f"phase {p} {sc} monthly={res[sc]['monthly_pct']} fullDD={res[sc]['full_path_dd']}", flush=True)
        phases[str(p)] = res

    # phase mean/min/max over monthly_pct and full-path DD per scenario + yearly normal nets
    summary = {}
    for sc in SCEN:
        monthlies = [phases[str(p)][sc]["monthly_pct"] for p in range(PD)]
        fulldds = [phases[str(p)][sc]["full_path_dd"] for p in range(PD)]
        summary[sc] = {
            "monthly_pct_mean": round(float(np.mean(monthlies)), 3),
            "monthly_pct_min": round(float(np.min(monthlies)), 3),
            "monthly_pct_max": round(float(np.max(monthlies)), 3),
            "full_path_dd_mean": round(float(np.mean(fulldds)), 2),
            "full_path_dd_min": round(float(np.min(fulldds)), 2),
            "full_path_dd_max": round(float(np.max(fulldds)), 2),
        }
    # yearly normal nets per phase + mean/min/max per anchor year
    yearly_normal = {}
    for j, a in enumerate(ANCHORS):
        nets = [phases[str(p)]["normal"]["yearly"][j]["net_pct"] for p in range(PD)]
        yearly_normal[a] = {
            "per_phase_net_pct": nets,
            "mean": round(float(np.mean(nets)), 2),
            "min": round(float(np.min(nets)), 2),
            "max": round(float(np.max(nets)), 2),
        }

    out = {
        "version": "v126_audit_replication",
        "phases": phases,
        "phase_summary": summary,
        "yearly_normal_nets": yearly_normal,
        "meta": {
            "anchors": list(ANCHORS),
            "scenarios": {k: {"fee": v[0], "slip": v[1]} for k, v in SCEN.items()},
            "spec": "phase p in 0..5: all three v115 books keep rows with position % 6 == p (ffill, fillna 0), own vol scales (0.20 cap 2, W.shift(2), trailing 360/min-120), v115 primary portfolio (0.25/0.25/0.5, target 0.15, ungoverned, v110 sequential engine)",
            "books_spec": "W_lo/W94 from v114 OOS CSVs with audited LO/LS formulas (no keep step); W103 from v103 OOS CSV; phased pos%6==p ffill; scales on phased weights with v114 opens (b_lo/b94) and v103 opens (b103); union t>=first v103 t",
            "wrapper_spec": "realized=0.8*sum(books.shift(2)*ret1)+0.6*carry.shift(1); vol rolling-360 min-120 *sqrt(2190); s=min(0.15/vol,2) NaN->1; live [2021-09-24,2026-09-23); ungoverned; w=0.8*s*books c=0.6*s; net=w*fwd-|dw|(fee+slip)-0.00005*long+c*carry-|dc|*2*0.0004/1.2",
            "data": {
                "v114_lo": "v113_v114_audit/predictions_v114_v92.csv",
                "v114_ls": "v113_v114_audit/predictions_v114_v94.csv",
                "v103": "v103_v105_audit/predictions_v103.csv",
                "carry": "artifacts/research/carry/carry_oos_fee0.0004.parquet",
                "opens_engine": "v103 OOS opens",
            },
        },
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"phase0_normal_monthly": phases["0"]["normal"]["monthly_pct"],
                      "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
