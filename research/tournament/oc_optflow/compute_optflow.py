"""oc_optflow: does INFORMED option flow predict the majors? (descriptive first).

Per PLAN.md (pre-registered): strike-level short-dated OTM taker/block flow -> F1/F2/F3,
(a) BOOK IC vs next 1-bar / 6-bar vol-normalised open-to-open returns, dev years only;
(b) DIPS join to the oc_placebo_dip D0+B1 replica (base 7.718 gate) with loss-rate terciles.
NO trading rule is scored here.

Usage:
  python research/tournament/oc_optflow/compute_optflow.py            # full (a)+(b), heavy 1m
  python research/tournament/oc_optflow/compute_optflow.py --only-a   # light part (a) only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
DATA_A = ROOT / "data/raw/deribit_strike_20261007"
OPENS = ROOT / "artifacts/research/engine_real/opens_v154.parquet"

COINS_OPT = ("BTC", "ETH")
MAP_COIN = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "BTC",
            "BNBUSDT": "BTC", "XRPUSDT": "BTC"}
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
DEV_YEARS = ANCHORS[:4]  # Y0..Y3; decisions with open in [A_k, A_{k+1})
SEED_BOOT = 20261007
N_BOOT = 1000
BLOCK = 42
HSTART = pd.Timestamp("2021-01-01", tz="UTC")
HEND = pd.Timestamp("2025-09-24", tz="UTC")  # exclusive upper for hourly starts


# --------------------------------------------------------------------------
# pure, testable building blocks
# --------------------------------------------------------------------------
def select_informed(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to informed universe; add per-row USD contribution columns.

    Keeps rows with 1 <= DTE_days <= 9 and OTM moneyness |m| in [0.03, 0.15].
    Adds: dte_days, m, net_usd (signed taker, +buy/-sell, only if OTM-kept),
    blk_usd (signed block notional, puts +, calls -).
    """
    d = df.copy()
    d["hour"] = pd.to_datetime(d["hour"], utc=True)
    d["expiry"] = pd.to_datetime(d["expiry"], utc=True)
    idx = pd.to_numeric(d["vwap_index"], errors="coerce")
    K = pd.to_numeric(d["strike"], errors="coerce")
    d["dte_days"] = (d["expiry"] - d["hour"]).dt.total_seconds() / 86400.0
    d["m"] = K / idx - 1.0
    is_put = d["cp"] == "P"
    is_call = d["cp"] == "C"
    ok_dte = (d["dte_days"] >= 1.0) & (d["dte_days"] <= 9.0)
    ok_put = is_put & (d["m"] >= -0.15) & (d["m"] <= -0.03)
    ok_call = is_call & (d["m"] >= 0.03) & (d["m"] <= 0.15)
    d["keep"] = ok_dte & (ok_put | ok_call) & np.isfinite(idx) & (idx > 0)
    tb = pd.to_numeric(d["taker_buy_amount"], errors="coerce").fillna(0.0)
    ts = pd.to_numeric(d["taker_sell_amount"], errors="coerce").fillna(0.0)
    bl = pd.to_numeric(d["block_amount"], errors="coerce").fillna(0.0)
    net = (tb - ts) * idx
    blk = bl * idx
    d["net_put_usd"] = np.where(d["keep"] & is_put, net, 0.0)
    d["net_call_usd"] = np.where(d["keep"] & is_call, net, 0.0)
    d["blk_put_usd"] = np.where(d["keep"] & is_put, blk, 0.0)
    d["blk_call_usd"] = np.where(d["keep"] & is_call, blk, 0.0)
    return d


def aggregate_hourly(sel: pd.DataFrame) -> pd.DataFrame:
    """Group selected rows to hourly NPB / NCB / BLK (USD notionals)."""
    k = sel[sel["keep"]]
    if len(k) == 0:
        return pd.DataFrame(columns=["NPB", "NCB", "BLK"])
    g = k.groupby("hour")
    out = pd.DataFrame({
        "NPB": g["net_put_usd"].sum(),
        "NCB": g["net_call_usd"].sum(),
        "BLKp": g["blk_put_usd"].sum(),
        "BLKc": g["blk_call_usd"].sum(),
    })
    out["BLK"] = out["BLKp"] - out["BLKc"]
    return out[["NPB", "NCB", "BLK"]]


def signals_from_hourly(hourly: pd.DataFrame) -> pd.DataFrame:
    """Hourly rolling aggregates; F(T) looks these up at hour T-1h (see signals_at)."""
    h = hourly.sort_index()
    net = h["NCB"] - h["NPB"]
    ab = h["NCB"].abs() + h["NPB"].abs()
    out = pd.DataFrame(index=h.index)
    out["R24"] = net.rolling(24, min_periods=24).sum()
    out["R4"] = net.rolling(4, min_periods=4).sum()
    out["Rblk24"] = h["BLK"].rolling(24, min_periods=24).sum()
    out["D"] = ab.rolling(720, min_periods=360).mean()
    return out


def signals_at(roll: pd.DataFrame, times: pd.DatetimeIndex) -> pd.DataFrame:
    """F1/F2/F3 at 4h bar opens T using only full hours ending at T (hour [T-1h,T) last)."""
    times = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    keys = times - pd.Timedelta(hours=1)
    r = roll.reindex(keys)
    D = r["D"].to_numpy(dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        F1 = r["R24"].to_numpy(dtype=float) / D
        F2 = r["Rblk24"].to_numpy(dtype=float) / D
        F3 = r["R4"].to_numpy(dtype=float) / D
    F1[(D == 0) | ~np.isfinite(D)] = np.nan
    F2[(D == 0) | ~np.isfinite(D)] = np.nan
    F3[(D == 0) | ~np.isfinite(D)] = np.nan
    return pd.DataFrame({"T": times, "F1": F1, "F2": F2, "F3": F3}).set_index("T")


def spearman_xy(x: np.ndarray, y: np.ndarray) -> tuple[float, int]:
    m = np.isfinite(x) & np.isfinite(y)
    xx, yy = x[m], y[m]
    n = int(len(xx))
    if n < 3:
        return float("nan"), n
    sx, sy = pd.Series(xx), pd.Series(yy)
    if sx.std() == 0 or sy.std() == 0:
        return float("nan"), n
    return float(sx.corr(sy, method="spearman")), n


def _rank(a: np.ndarray) -> np.ndarray:
    # average-rank (ties) via sort; fast enough for bootstrap vectors
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(1, len(a) + 1, dtype=float)
    # average ties
    _, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    if (cnt > 1).any():
        s = np.bincount(inv, weights=ranks)
        avg = s / cnt
        ranks = avg[inv]
    return ranks


def spearman_fast(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return float("nan")
    rx, ry = _rank(np.asarray(x, dtype=float)), _rank(np.asarray(y, dtype=float))
    c = np.corrcoef(rx, ry)
    v = float(c[0, 1])
    return v


def block_bootstrap_ci(x: np.ndarray, y: np.ndarray, seed: int = SEED_BOOT,
                       n_boot: int = N_BOOT, block: int = BLOCK) -> tuple[float, float, int]:
    """Moving-block bootstrap CI for Spearman; returns (lo, hi, n_effective)."""
    m = np.isfinite(x) & np.isfinite(y)
    xx, yy = np.asarray(x)[m], np.asarray(y)[m]
    n = int(len(xx))
    if n < 3:
        return float("nan"), float("nan"), n
    rng = np.random.default_rng(seed)
    stats = []
    starts = rng.integers(0, max(n - block + 1, 1), size=n_boot * 4)
    si = 0
    for _ in range(n_boot):
        idx = []
        while len(idx) < n:
            s = int(starts[si % len(starts)]) if n > block else 0
            si += 1
            idx.extend(range(s, min(s + block, n)))
            if si > len(starts) + n_boot * 60:
                break
        idx = np.array(idx[:n])
        stats.append(spearman_fast(xx[idx], yy[idx]))
    stats = np.array([s for s in stats if np.isfinite(s)])
    if len(stats) < 20:
        return float("nan"), float("nan"), n
    return float(np.quantile(stats, 0.025)), float(np.quantile(stats, 0.975)), n


# --------------------------------------------------------------------------
# IO builders
# --------------------------------------------------------------------------
def build_hourly_coin(coin: str) -> pd.DataFrame:
    files = sorted((DATA_A / coin).glob(f"{coin}_202*.parquet"))
    parts = []
    for f in files:
        df = pd.read_parquet(f)
        sel = select_informed(df)
        agg = aggregate_hourly(sel)
        parts.append(agg)
        del df, sel
    if not parts:
        raise FileNotFoundError(f"no option files for {coin}")
    cat = pd.concat(parts)
    cat = cat.groupby(level=0).sum()  # months disjoint; sum == concat
    full = pd.date_range(HSTART, HEND - pd.Timedelta(hours=1), freq="h", tz="UTC")
    cat = cat.reindex(full, fill_value=0.0).astype(float)
    cat.index.name = "hour"
    return cat.rename(columns={"NPB": "NPB", "NCB": "NCB", "BLK": "BLK"})


def year_idx(ts: pd.DatetimeIndex, k: int) -> np.ndarray:
    return ((ts >= ANCHORS[k]) & (ts < ANCHORS[k + 1])).to_numpy()


def study_a(hourly: dict) -> tuple[list, pd.DataFrame]:
    print("study (a): loading opens", flush=True)
    opens_full = pd.read_parquet(OPENS)
    rows, feat_rows = [], []
    # trailing sigma per coin on FULL history (causal)
    sig = {}
    for c in MAJORS:
        o = opens_full[c].sort_index().astype(float)
        lr = np.log(o / o.shift(1))
        sig[c] = lr.rolling(360, min_periods=120).std(ddof=1)
    opens = opens_full
    # standard-grid opens inside hourly coverage + dev window (warmup 744h = 31d)
    cands = opens.index[(opens.index >= HSTART + pd.Timedelta(hours=744))
                        & (opens.index < ANCHORS[4])]
    cands = cands[(cands - pd.Timedelta(hours=1)) >= hourly["BTC"].index.min()]
    roll = {c: signals_from_hourly(hourly[c]) for c in ("BTC", "ETH")}
    Fstd = {c: signals_at(roll[c], cands) for c in ("BTC", "ETH")}
    recs = []
    for c in MAJORS:
        oc = MAP_COIN[c]
        F = Fstd[oc].reindex(cands)
        o = opens[c].reindex(cands).astype(float)
        s = sig[c].reindex(cands).astype(float)
        fwd1 = opens[c].shift(-1).reindex(cands).astype(float) / o - 1.0
        fwd6 = opens[c].shift(-6).reindex(cands).astype(float) / o - 1.0
        z1 = fwd1 / s
        z6 = fwd6 / s
        df = pd.DataFrame({"T": cands, "coin": c, "F1": F["F1"].to_numpy(),
                           "F2": F["F2"].to_numpy(), "F3": F["F3"].to_numpy(),
                           "z1": z1.to_numpy(), "z6": z6.to_numpy()})
        recs.append(df)
    panel = pd.concat(recs, ignore_index=True)
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    return panel, opens_full


FEAT_I = {"F1": 0, "F2": 1, "F3": 2}
HOR_I = {"z1": 0, "z6": 1}
COIN_I = {c: i for i, c in enumerate(MAJORS)}


def summarise_a(panel: pd.DataFrame) -> list:
    out = []
    for k in range(4):
        ylab = ANCHORS[k].date().isoformat()
        sub = panel[(panel["T"] >= ANCHORS[k]) & (panel["T"] < ANCHORS[k + 1])]
        for feat in ("F1", "F2", "F3"):
            for hor in ("z1", "z6"):
                # pooled
                ic, n = spearman_xy(sub[feat].to_numpy(), sub[hor].to_numpy())
                lo, hi, _ = block_bootstrap_ci(
                    sub[feat].to_numpy(), sub[hor].to_numpy(),
                    seed=SEED_BOOT + k * 100 + FEAT_I[feat] * 10 + HOR_I[hor])
                out.append({"year": ylab, "coin": "POOLED", "feat": feat, "hor": hor,
                            "ic": round(ic, 4) if np.isfinite(ic) else None, "n": n,
                            "ci_lo": round(lo, 4) if np.isfinite(lo) else None,
                            "ci_hi": round(hi, 4) if np.isfinite(hi) else None})
                for c in MAJORS:
                    s2 = sub[sub["coin"] == c]
                    ic2, n2 = spearman_xy(s2[feat].to_numpy(), s2[hor].to_numpy())
                    lo2, hi2, _ = block_bootstrap_ci(
                        s2[feat].to_numpy(), s2[hor].to_numpy(),
                        seed=SEED_BOOT + k * 1000 + COIN_I[c] * 131
                        + FEAT_I[feat] * 37 + HOR_I[hor] * 11)
                    out.append({"year": ylab, "coin": c, "feat": feat, "hor": hor,
                                "ic": round(ic2, 4) if np.isfinite(ic2) else None, "n": n2,
                                "ci_lo": round(lo2, 4) if np.isfinite(lo2) else None,
                                "ci_hi": round(hi2, 4) if np.isfinite(hi2) else None})
        print(f"(a) year {ylab} done", flush=True)
    return out


def study_b(hourly: dict) -> dict:
    sys.path.insert(0, str(ROOT / "research/tournament/oc_placebo_dip"))
    import compute_placebo_dip as dip
    print("study (b): running dip replica build_base (heavy 1m)...", flush=True)
    led = dip.build_base()
    print(f"study (b): ledger fills={len(led['w'])}", flush=True)
    base_sc = dip.score_assignment(led["phase"], led["year"], led["w"], led["y10"], led["d10"])
    base_sum5y = float(base_sc["sum5y"])
    got_p0 = []
    for y in range(5):
        m = (led["phase"] == 0) & (led["year"] == y)
        got_p0.append(float((led["w"][m] * led["y10"][m]).sum()))
    chk = hashlib.sha256(np.round(np.stack(
        [led["w"], led["y09"], led["y10"], led["y11"]]), 9).tobytes()).hexdigest()[:16]
    fidelity = {"base_sum5y": round(base_sum5y, 6),
                "phase0_sums": [round(s, 6) for s in got_p0],
                "n_fills": int(len(led["w"])), "checksum": chk}
    print(f"study (b): fidelity {fidelity}", flush=True)
    # join F at each fill's phase-specific bar open
    START = pd.Timestamp("2020-08-01", tz="UTC")
    bt_min = led["bar_time"].astype(np.int64)
    Tfill = START + pd.to_timedelta(bt_min, unit="m")
    Tfill = pd.DatetimeIndex(Tfill)
    roll = {c: signals_from_hourly(hourly[c]) for c in ("BTC", "ETH")}
    uniq, inv = np.unique(Tfill.values, return_inverse=True)
    Funiq = {c: signals_at(roll[c], pd.DatetimeIndex(uniq)) for c in ("BTC", "ETH")}
    coins = np.array(["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"])[led["coin"]]
    mapped = np.array([MAP_COIN[c] for c in coins])
    F1 = np.empty(len(led["w"]), dtype=float)
    F3 = np.empty(len(led["w"]), dtype=float)
    for c in ("BTC", "ETH"):
        m = mapped == c
        F1[m] = Funiq[c]["F1"].to_numpy()[inv[m]]
        F3[m] = Funiq[c]["F3"].to_numpy()[inv[m]]
    y10 = led["y10"].astype(float)
    yr = led["year"].astype(int)
    per_year, terc = [], []
    for k in range(4):
        ylab = ANCHORS[k].date().isoformat()
        m = yr == k
        ic1, n1 = spearman_xy(F1[m], y10[m])
        ic3, n3 = spearman_xy(F3[m], y10[m])
        per_year.append({"year": ylab, "n": int(m.sum()),
                         "ic_F1_y10": round(ic1, 4) if np.isfinite(ic1) else None,
                         "ic_F3_y10": round(ic3, 4) if np.isfinite(ic3) else None})
        for feat, Fv in (("F1", F1[m]), ("F3", F3[m])):
            yy = y10[m]
            ok = np.isfinite(Fv) & np.isfinite(yy)
            Fv, yy = Fv[ok], yy[ok]
            if len(yy) < 30:
                for t in (1, 2, 3):
                    terc.append({"year": ylab, "feat": feat, "tercile": t,
                                 "n": 0, "mean_y10": None, "loss_rate": None,
                                 "cut_lo": None, "cut_hi": None})
                continue
            q1, q2 = float(np.quantile(Fv, 1 / 3)), float(np.quantile(Fv, 2 / 3))
            for t, (lo, hi) in enumerate([(float("-inf"), q1), (q1, q2), (q2, float("inf"))], 1):
                mm = (Fv > lo) & (Fv <= hi) if t > 1 else (Fv <= hi)
                if t == 3:
                    mm = Fv > q2
                seg = yy[mm]
                terc.append({"year": ylab, "feat": feat, "tercile": t,
                             "n": int(mm.sum()),
                             "mean_y10": round(float(seg.mean()), 6) if len(seg) else None,
                             "loss_rate": round(float((seg < 0).mean()), 4) if len(seg) else None,
                             "cut_lo": None if t == 1 else round(q1 if t == 2 else q2, 6),
                             "cut_hi": None if t == 3 else round(q1 if t == 1 else q2, 6)})
        print(f"(b) year {ylab} done", flush=True)
    return {"fidelity": fidelity, "per_year": per_year, "terciles": terc,
            "note": "loss_rate = P(y10<0); exit-type stop flag unavailable in replica ledger"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-a", action="store_true")
    args = ap.parse_args()
    print("oc_optflow: building hourly flows (BTC/ETH)...", flush=True)
    hourly = {}
    for c in COINS_OPT:
        hourly[c] = build_hourly_coin(c)
        print(f"  {c}: hours={len(hourly[c])} "
              f"NPB_absmean={hourly[c]['NPB'].abs().mean():.1f} "
              f"NCB_absmean={hourly[c]['NCB'].abs().mean():.1f} "
              f"BLK_absmean={hourly[c]['BLK'].abs().mean():.1f}", flush=True)
    panel, _ = study_a(hourly)
    print(f"oc_optflow: panel rows={len(panel)}", flush=True)
    a_rows = summarise_a(panel)
    ic_df = pd.DataFrame(a_rows)
    (HERE / "ic_book.csv").write_text(ic_df.to_csv(index=False))
    res: dict = {"config": "see PLAN.md", "a_ic": a_rows,
                 "hourly_stats": {c: {"hours": int(len(hourly[c])),
                                      "npb_sum": float(hourly[c]['NPB'].sum()),
                                      "ncb_sum": float(hourly[c]['NCB'].sum()),
                                      "blk_sum": float(hourly[c]['BLK'].sum())} for c in hourly}}
    if args.only_a:
        (HERE / "results.json").write_text(json.dumps(res, indent=1))
        print(json.dumps({"a_rows": len(a_rows)}, indent=1))
        return
    b = study_b(hourly)
    res["b_dips"] = b
    pd.DataFrame(b["terciles"]).to_csv(HERE / "dips_terciles.csv", index=False)
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({"a_rows": len(a_rows), "b_fidelity": b["fidelity"]}, indent=1))


if __name__ == "__main__":
    main()
