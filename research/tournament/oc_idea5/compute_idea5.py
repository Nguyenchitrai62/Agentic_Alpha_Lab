"""oc_idea5: premium-gated book flips (IDEAS.md idea #5).

Per PLAN.md (pre-registered): BASE = deployed 60d book-vol scale on
forward_v205.research_books_d2 (rebuilt exactly) x v154 4h opens;
GATE = BASE with per-coin 1-bar veto of strict reversals INTO a |z|>2
Coinbase-minus-Binance dislocation (z of 1h-mean premium vs trailing 90d).
Vectorised open-to-open replay: pn[t] = ws.r - 0.0005*TO. Causal: every
scale/x/z/veto at t uses only information with START < t (hourly) or
bars strictly before t (4h windows ending at t-1).

  python research/tournament/oc_idea5/compute_idea5.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
HOURLY_EXT = ROOT / "research/tournament/ext/hourly_ext.parquet"
CB_DIR = ROOT / "data/raw/coinbase_20260925"
CB_ALTS_DIR = ROOT / "data/raw/coinbase_alts_20260930"
CUTOFF = pd.Timestamp("2026-09-24 00:00", tz="UTC")

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
CB_MAP = {"BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD",
          "SOLUSDT": "SOL-USD", "XRPUSDT": "XRP-USD"}  # BNB: no Coinbase
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_END = ANCHORS[-1] + pd.Timedelta(days=365)
ANN = float(np.sqrt(6 * 365))
COST = 0.0005
TARGET, CAP = 0.25, 2.0
Z_THRESH = 2.0
WIN, MINP = 540, 270  # trailing ~90d of 4h samples


def research_books_d2() -> pd.DataFrame:
    """Mirror of scripts/forward_v205.py::research_books_d2 (same as oc_bookvol)."""
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


def load_hourly_close() -> pd.DataFrame:
    """Binance perp hourly closes pivoted (t = hour START), START < CUTOFF."""
    h = pd.read_parquet(HOURLY_EXT)
    h = h[h["t"] < CUTOFF]
    px = h.pivot(index="t", columns="sym", values="close").sort_index()
    for c in SYMS:
        if c not in px.columns:
            px[c] = np.nan
    return px[SYMS]


def load_coinbase_close(sym: str) -> pd.Series:
    """Coinbase hourly close indexed by bar START (< CUTOFF); BNB -> empty."""
    if sym not in CB_MAP:
        return pd.Series(dtype=float)
    prod = CB_MAP[sym]
    d = CB_DIR if sym in ("BTCUSDT", "ETHUSDT") else CB_ALTS_DIR
    df = pd.read_parquet(d / f"{prod}_1h.parquet")[["open_time", "close"]]
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df[df["open_time"] < CUTOFF].drop_duplicates("open_time").sort_values("open_time")
    s = pd.Series(df["close"].to_numpy(float), index=pd.DatetimeIndex(df["open_time"]))
    return s[~s.index.duplicated(keep="last")].sort_index()


def build_xz(grid_ext: pd.DatetimeIndex, bn: pd.DataFrame,
             cb: dict[str, pd.Series]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """x(T)=p(T-1h) bps, z vs prior 540 4h x (<T). All hourly START < T."""
    one_h = pd.Timedelta(hours=1)
    # hourly premium level indexed by hourly START
    prem = {}
    for c in SYMS:
        s = cb.get(c, pd.Series(dtype=float))
        if len(s) == 0:
            prem[c] = pd.Series(dtype=float)
            continue
        common = s.index.intersection(bn.index)
        # align: both hourly START; require finite positive
        a = s.reindex(common).astype(float)
        b = bn[c].reindex(common).astype(float)
        ok = np.isfinite(a.to_numpy()) & np.isfinite(b.to_numpy()) & (a > 0).to_numpy() & (b > 0).to_numpy()
        p = pd.Series(np.where(ok, 1e4 * np.log(a / b), np.nan), index=common).replace([np.inf, -np.inf], np.nan)
        prem[c] = p.sort_index()
    x = pd.DataFrame(np.nan, index=grid_ext, columns=SYMS)
    for c in SYMS:
        p = prem[c]
        if len(p) == 0:
            continue
        want = grid_ext - one_h
        # exact match on hourly START (4h boundary - 1h is an hourly boundary)
        x[c] = p.reindex(want).to_numpy()
    # z: rolling 540/min 270 on 4h x, shifted (strictly before T)
    mean = x.rolling(WIN, min_periods=MINP).mean().shift(1)
    std = x.rolling(WIN, min_periods=MINP).std(ddof=1).shift(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (x - mean) / std
    z = z.where(np.isfinite(std.to_numpy()) & (std > 0).to_numpy(), np.nan)
    return x, z, mean


def compute_veto(w: pd.DataFrame, z: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Strict-reversal flips; veto INTO dislocation; max 1-bar delay outside."""
    sgn = np.sign(w.to_numpy(float))
    prev = np.roll(sgn, 1, axis=0)
    prev[0, :] = 0.0
    flip = pd.DataFrame((sgn * prev < 0), index=w.index, columns=w.columns)
    wn = w.to_numpy(float)
    zn = z.to_numpy(float)
    veto = pd.DataFrame(False, index=w.index, columns=w.columns)
    for j, c in enumerate(w.columns):
        f = flip[c].to_numpy(bool)
        into = np.where(wn[:, j] > 0, zn[:, j] > Z_THRESH,
                        np.where(wn[:, j] < 0, zn[:, j] < -Z_THRESH, False))
        into = np.where(np.isfinite(zn[:, j]), into, False)
        veto[c] = f & into
    veto.iloc[0, :] = False
    return flip, veto


def apply_gate(ws_base: pd.DataFrame, veto: pd.DataFrame) -> pd.DataFrame:
    """ws_gate[T] = ws_base[T-1] iff veto[T] and not veto[T-1] (per coin)."""
    v = veto.to_numpy(bool)
    vprev = np.roll(v, 1, axis=0)
    vprev[0, :] = False
    hold = v & (~vprev)
    wb = ws_base.to_numpy(float)
    wprev = np.roll(wb, 1, axis=0)
    gated = np.where(hold, wprev, wb)
    out = pd.DataFrame(gated, index=ws_base.index, columns=ws_base.columns)
    out.iloc[0, :] = wb[0, :]
    return out


def roll_std(s: pd.Series, window: int, min_periods: int) -> pd.Series:
    return s.rolling(window, min_periods=min_periods).std(ddof=1)


def score_variant(ws: pd.DataFrame, fwd1: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    prev = ws.shift(1).fillna(0.0)
    to = (ws - prev).abs().sum(axis=1)
    return (ws * fwd1).sum(axis=1) - COST * to, to


def year_stats(pn: pd.Series) -> dict:
    v = pn.dropna().to_numpy(float)
    n = len(v)
    if n == 0:
        return dict(n_bars=0, ret=None, dd=None, sharpe=None)
    eq = np.cumprod(1.0 + v)
    peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:]
    dd = float(np.max(1.0 - eq / peak)) if n else 0.0
    ret = float(eq[-1] - 1.0)
    sh = float(v.mean() / v.std(ddof=1) * ANN) if n >= 30 and v.std(ddof=1) > 0 else float("nan")
    return dict(n_bars=int(n), ret=round(ret, 6),
                dd=round(dd, 6), sharpe=round(sh, 4) if np.isfinite(sh) else None)


def worst_day(pn: pd.Series) -> float:
    d = pn.groupby(pn.index.floor("D")).sum()
    return float(d.min()) if len(d) else float("nan")


def main() -> None:
    books = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books.index)
    grid = books.index.intersection(opens.dropna(how="all").index).sort_values()
    books, opens = books.reindex(grid), opens.reindex(grid)
    fwd1 = opens.shift(-1) / opens - 1.0
    valid = fwd1.notna().all(axis=1)
    books, opens, fwd1 = books[valid], opens[valid], fwd1[valid]
    grid = books.index.sort_values()

    bn = load_hourly_close()
    assert (bn.index < CUTOFF).all()
    cb = {c: load_coinbase_close(c) for c in SYMS}
    for c, s in cb.items():
        if len(s):
            assert (s.index < CUTOFF).all(), c

    grid_ext = pd.date_range(grid.min() - pd.Timedelta(days=90), grid.max(), freq="4h", tz="UTC")
    grid_ext = grid_ext.union(grid).sort_values()
    x_ext, z_ext, _ = build_xz(grid_ext, bn, cb)
    x = x_ext.reindex(grid)
    z = z_ext.reindex(grid)

    # BASE scale (deployed 60d, windows end at t-1)
    U = pd.Series((books.to_numpy() * fwd1.to_numpy()).sum(axis=1), index=grid)
    sig0 = roll_std(U.shift(1), 360, 120) * ANN
    s0 = pd.Series(np.where(sig0.notna() & (sig0 > 0),
                            np.minimum(TARGET / sig0.where(sig0 > 0, np.nan), CAP), 1.0),
                   index=grid).fillna(1.0)
    ws_base = books.mul(s0, axis=0)

    flip, veto = compute_veto(books, z)
    ws_gate = apply_gate(ws_base, veto)

    bounds = ANCHORS + [YEAR_END]
    masks = [((grid >= bounds[k]) & (grid < bounds[k + 1])) for k in range(5)]

    variants = {}
    for name, ws in (("base_60d", ws_base), ("gated_z2", ws_gate)):
        pn, to = score_variant(ws, fwd1)
        per_year = []
        for k, a0 in enumerate(ANCHORS):
            st = year_stats(pn[masks[k]])
            wd = worst_day(pn[masks[k]])
            per_year.append(dict(year=str(a0.date()), worst_day=round(wd, 6), **st))
        all_st = year_stats(pn)
        variants[name] = dict(per_year=per_year, pooled=all_st,
                              pooled_worst_day=round(worst_day(pn), 6),
                              mean_abs_w=round(float(ws.abs().mean().mean()), 6),
                              total_turnover=round(float(to.sum()), 4),
                              total_cost=round(float((COST * to).sum()), 6))
        print(f"{name}: " + " | ".join(
            f"{r['year']} ret={r['ret']} dd={r['dd']} sh={r['sharpe']} wd={r['worst_day']}"
            for r in per_year), flush=True)

    base, gate = variants["base_60d"]["per_year"], variants["gated_z2"]["per_year"]
    ddd = [None if (r["dd"] is None or b["dd"] is None) else round(b["dd"] - r["dd"], 6)
           for r, b in zip(gate, base)]
    dret = [None if (r["ret"] is None or b["ret"] is None) else round(r["ret"] - b["ret"], 6)
            for r, b in zip(gate, base)]
    dsh = [None if (r["sharpe"] is None or b["sharpe"] is None) else round(r["sharpe"] - b["sharpe"], 4)
           for r, b in zip(gate, base)]
    tail = [bool(r["worst_day"] >= b["worst_day"]) for r, b in zip(gate, base)]
    n_dd = sum(1 for d in ddd if d is not None and d > 0)
    loyo = []
    for h in range(5):
        tr = [d for k, d in enumerate(ddd) if k != h and d is not None]
        m = float(np.mean(tr)) if len(tr) == 4 else float("nan")
        loyo.append(bool(ddd[h] is not None and np.isfinite(m) and m > 0
                          and np.sign(ddd[h]) == np.sign(m)))
    promising = bool(n_dd >= 4 and sum(loyo) >= 4 and sum(tail) >= 4)
    decision = dict(dDD=ddd, dd_pos=f"{n_dd}/5", loyo_dd=f"{sum(loyo)}/5",
                    loyo_detail=[bool(x) for x in loyo],
                    tail_ok=[bool(x) for x in tail], tail_pos=f"{sum(tail)}/5",
                    dRet=dret, dSharpe=dsh, promising=promising,
                    first4_dd_pos=f"{sum(1 for d in ddd[:4] if d is not None and d > 0)}/4",
                    first4_tail_pos=f"{sum(1 for x in tail[:4] if x)}/4")

    # coverage / fire stats per year (descriptive, no outcomes)
    fire, flips = [], []
    for k, a0 in enumerate(ANCHORS):
        fire.append(round(float(veto[masks[k]].to_numpy().mean()), 6))
        flips.append(round(float(flip[masks[k]].to_numpy().mean()), 6))
    zcov = {c: round(float(z[c].notna().mean()), 4) for c in SYMS}
    xcov = {c: round(float(x[c].notna().mean()), 4) for c in SYMS}

    out = {
        "definitions": ("grid=books_d2 x opens_v154 inner join; r=open[t+1]/open[t]-1; "
                        "BASE V0 scale=min(2,0.25/sig60d), sig=std(u[t-360..t-1])*sqrt(2190) min120; "
                        "p(h)=1e4*ln(CB(h)/BN(h)) bps, CB=coinbase hourly close, BN=hourly_ext close; "
                        "x(T)=p(T-1h) (hourly START=T-1h, END==T); "
                        "z(T)=(x-mean(W))/std(W), W=up to 540 prior 4h x in [T-90d,T), min270, std>0; "
                        "flip=strict reversal sign(w[T])*sign(w[T-1])<0 (zero never); "
                        "veto=flip AND ((w>0 AND z>+2) OR (w<0 AND z<-2)); BNB/NaN never; "
                        "GATE=ws_base[T-1] iff veto[T] AND NOT veto[T-1] else ws_base[T] (1-bar max, per coin); "
                        "TO=sum|ws[t]-ws[t-1]| (first vs 0, per-variant); pn=sum(ws*r)-0.0005*TO; "
                        "eq compounded from 1; years [A_k,A_k+1) x4 + [A4,A4+365d); "
                        "Sharpe=mean/std*sqrt(2190); DD on year-rebased eq; worst_day=min UTC-day sum"),
        "symbols": SYMS, "anchor_years": [str(a.date()) for a in ANCHORS],
        "grid_start": str(grid.min()), "grid_end": str(grid.max()),
        "n_bars": int(len(grid)),
        "premium": dict(z_thresh=Z_THRESH, win=WIN, minp=MINP,
                        x_coverage=xcov, z_coverage=zcov,
                        veto_rate_per_year={str(a.date()): fire[k] for k, a in enumerate(ANCHORS)},
                        flip_rate_per_year={str(a.date()): flips[k] for k, a in enumerate(ANCHORS)},
                        veto_counts_per_year={str(a.date()): int(veto[masks[k]].to_numpy().sum())
                                              for k, a in enumerate(ANCHORS)}),
        "variants": variants, "decision": decision,
        "scale_summary": dict(s0_mean=round(float(s0.mean()), 4),
                              s0_p5=round(float(s0.quantile(0.05)), 4),
                              s0_p95=round(float(s0.quantile(0.95)), 4)),
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"premium": out["premium"], "decision": decision}, indent=1))


if __name__ == "__main__":
    main()
