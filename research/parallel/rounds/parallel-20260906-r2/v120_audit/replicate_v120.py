"""Blind v120 audit replication (Part A). Does NOT read research/.../v120/*.

Base (per OPENCODE_V120_AUDIT.md):
  audited v118 replication (v115 books + per-asset no-trade band in the
  sequential engine).

Spec A: band 0.05, ungoverned, portfolio vol target in
  (0.10, 0.12, 0.15, 0.18, 0.20, 0.22, 0.25): the target enters only via
  s = min(target/vol, 2) (vol from the ungated books + carry as v115).
  Report monthly, worst-year DD and full-path DD per target and scenario
  (0.15 must equal the v118 band-0.05 row).

Blind choices (fixed before running, documented):
  - Books/s/carry/opens/live/scenarios identical to audited v115 primary
    (replicate_v115.py) and v118 audit Part A1 (replicate_v118_v119.py):
    books=0.25*b_lo+0.25*b94+0.5*b103, 20%-cap-2 book scales, union
    t>=first-v103-t, opens=v103 OOS opens, live [2021-09-24,2026-09-23),
    realized=0.8*sum(books.shift(2)*ret1)+0.6*carry.shift(1),
    rolling-360/min-120*sqrt(2190), cap 2, NaN->1.
  - Vol series computed ONCE from ungated books + carry (target-independent);
    each target scales as s_t = min(target/vol, 2), NaN->1.
  - Targets w=0.8*s_t*books (ungoverned, g=1); carry c=0.6*s_t unchanged.
  - Band 0.05 applied per asset vs previous HELD (not target): if live and
    |w-h_prev|>0.05 -> h=w else h=h_prev; if not live -> h=0 immediately.
    Turnover=sum|h-h_prev|; gross=sum(h*fwd) with fwd=o[i+2]/o[i+1]-1
    (last two ->0); funding=0.00005*sum(max(h,0));
    carry cost=|dc|*2*0.0004/1.2.
  - Scenarios normal(0.0002,0)/fee_stress(0.0006,0)/exec(0.0006,0.0005).
  - Yearly slices [anchor,anchor+365d) for 5 anchors; monthly geometric net,
    worst-year DD, full-path DD over live span.
  - No v120/v118/v115 leader module imported; all formulas inline from the
    assignment text + audited OOS CSVs + carry parquet.
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
BAND = 0.05
TARGETS = (0.10, 0.12, 0.15, 0.18, 0.20, 0.22, 0.25)
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0), "execution_stress": (0.0006, 0.0005)}
START = pd.Timestamp("2021-09-24", tz="UTC")
END = START + pd.Timedelta(days=5 * 365)

V114_LO_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v92.csv"
V114_LS_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v94.csv"
V103_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v103_v105_audit/predictions_v103.csv"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"


def tkey(t):
    return f"t{int(round(t * 100)):03d}"


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


def summarize_seq(net_s, turn_s):
    ys = []
    for a in ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = (net_s.index >= a0) & (net_s.index < a0 + pd.Timedelta(days=365))
        ys.append(dict(anchor=a, **stats(net_s[mk], turn_s[mk])))
    geo = np.prod([1 + y["net_pct"] / 100 for y in ys]) ** (1 / 5) - 1
    full = (net_s.index >= START) & (net_s.index < END)
    eq = (1 + net_s[full]).cumprod()
    return dict(
        yearly=ys,
        monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
        worst_year_dd=max(y["max_drawdown_percent"] for y in ys),
        full_path_dd=round(100 * float((1 - eq / eq.cummax()).max()), 2),
    )


def run_band(o_vals, targ_vals, carry_vals, s_vals, live_mask, fee, slip, band):
    n, k = o_vals.shape
    fwd = np.zeros_like(o_vals)
    with np.errstate(divide="ignore", invalid="ignore"):
        fm = o_vals[2:] / o_vals[1:-1] - 1.0
    fm = np.where(np.isfinite(fm), fm, 0.0)
    fwd[: n - 2] = fm
    net = np.zeros(n)
    turn = np.zeros(n)
    held = np.zeros(k)
    prev_c = 0.0
    for i in range(n):
        if live_mask[i]:
            w = targ_vals[i]
            diff = np.abs(w - held)
            take = diff > band
            new = np.where(take, w, held)
        else:
            new = np.zeros(k)
        c = W_CARRY * CARRY_LEV * s_vals[i] if live_mask[i] else 0.0
        gross = float(np.sum(new * fwd[i]))
        tcost = float(np.sum(np.abs(new - held)) * (fee + slip))
        fund = float(np.sum(np.maximum(new, 0.0)) * 0.00005)
        cgross = float(c * carry_vals[i])
        ccost = float(abs(c - prev_c) * 2 * 0.0004 / 1.2)
        ni = gross - tcost - fund + cgross - ccost
        net[i] = ni
        turn[i] = float(np.sum(np.abs(new - held)))
        held = new
        prev_c = c
    return net, turn


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
    ret1 = o / o.shift(1) - 1
    realized = W_BOOKS * (books.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
    vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN

    live_mask = np.asarray((idx >= START) & (idx < END))
    o_vals = o.to_numpy(dtype=float)
    books_vals = books.to_numpy(dtype=float)
    carry_vals = carry_s.to_numpy(dtype=float)

    out = {"version": "v120_audit_replication"}
    for tgt in TARGETS:
        s = (tgt / vol).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
        s_vals = s.to_numpy(dtype=float)
        targ_vals = W_BOOKS * s_vals[:, None] * books_vals
        key = tkey(tgt)
        res = {}
        for sc, (fee, slip) in SCEN.items():
            net, turn = run_band(o_vals, targ_vals, carry_vals, s_vals, live_mask, fee, slip, BAND)
            net_s = pd.Series(net, index=idx)
            turn_s = pd.Series(turn, index=idx)
            res[sc] = summarize_seq(net_s, turn_s)
            print(f"A {key} band={BAND} target={tgt} {sc} monthly={res[sc]['monthly_pct']} "
                  f"worstDD={res[sc]['worst_year_dd']} fullDD={res[sc]['full_path_dd']}", flush=True)
        out[key] = res
    out["meta"] = {
        "anchors": list(ANCHORS),
        "band": BAND,
        "governed": False,
        "targets": list(TARGETS),
        "keys": {tkey(t): t for t in TARGETS},
        "union_bars": int(len(idx)),
        "n_live_bars": int(live_mask.sum()),
        "oos_span": [str(idx[0]), str(idx[-1])],
        "first_v103_t": str(first_v103),
        "books_spec": "books=0.25*b_lo(v114 LO*scale114)+0.25*b94(v114 LS*scale114)+0.5*b103(v103 LS*scale103); union t>=first v103 t; opens=v103 OOS",
        "wrapper_spec": "vol from ungated books+carry: realized=0.8*sum(books.shift(2)*ret1)+0.6*carry.shift(1), rolling-360/min-120*sqrt(2190); s=min(target/vol,2) NaN->1; live [2021-09-24,2026-09-23); targets w=0.8*s*books g=1; held per-asset band (|w-h|>0.05 -> w else h), outside h=0 immediately; turnover=sum|new-held|; carry c=0.6*s unchanged; net=held*fwd-turn*(fee+slip)-0.00005*long+c*carry-|dc|*2*0.0004/1.2",
        "scenarios": {k: {"fee": v[0], "slip": v[1]} for k, v in SCEN.items()},
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"targets": out["meta"]["keys"], "union": len(idx), "n_live": int(live_mask.sum())}, indent=2))


if __name__ == "__main__":
    main()
