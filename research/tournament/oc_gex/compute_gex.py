"""oc_gex: dealer-GEX hourly proxy from Deribit strike-level trades.

Pre-registered in PLAN.md (fixed before any outcome). One process, one coin
at a time. Run through the shared semaphore (see module docstring of the
assignment).

Outputs: research/tournament/oc_gex/gex_hourly_{BTC,ETH}.parquet
Columns: hour_end (UTC, value known at this time), S, GEX, H, N30, GEXn.

Formula (r=0): q_i(t)=cumsum(buy-sell) since first trade; alive iff
t < expiry_date+08:00 UTC; iv as-of ffill clipped to [0.05,3.0];
T=floor 1h; gamma=N'(d1)/(S*iv*sqrt(T)); GEX=-sum q*gamma*S^2*0.01;
H=sum amount*vwap_index; N30=trailing 720h mean of H (>=168h else NaN);
GEXn=GEX/(S*N30). S=hourly median vwap_index (ffilled).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_gex \\
    --min-free-gb 2.0 -- .venv/Scripts/python.exe \\
    research/tournament/oc_gex/compute_gex.py
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
DIR_A = ROOT / "data/raw/deribit_strike_20261007"
DIR_B = ROOT / "data/raw/deribit_strike_20261007_b"

COINS = ("BTC", "ETH")
GRID0 = pd.Timestamp("2021-01-01 00:00", tz="UTC")
GRID1 = pd.Timestamp("2026-09-24 00:00", tz="UTC")
PROXY_START = pd.Timestamp("2021-04-01 00:00", tz="UTC")
OLD_CUTOFF = pd.Timestamp("2021-01-15 00:00", tz="UTC")  # "older" (listed 2020): first trade <= this
YEAR_SEC = 365.25 * 86400.0
IV_LO, IV_HI = 0.05, 3.0
IV_RAW_LO, IV_RAW_HI = 1.0, 990.0  # raw vwap_iv is in PERCENT (Deribit convention)
N30_WIN = 720
N30_MIN = 168
SQRT2PI = np.sqrt(2.0 * np.pi)

t0 = time.time()


def log(msg: str) -> None:
    print(f"[oc_gex {time.time()-t0:8.1f}s] {msg}", flush=True)


def month_files(coin: str) -> list[Path]:
    a = sorted((DIR_A / coin).glob(f"{coin}_*.parquet"))
    b = sorted((DIR_B / coin).glob(f"{coin}_*.parquet"))
    have = {p.name for p in a}
    out = list(a) + [p for p in b if p.name not in have]
    return sorted(out)


def load_coin(coin: str) -> pd.DataFrame:
    files = month_files(coin)
    log(f"{coin}: {len(files)} month files")
    cols = ["hour", "instrument_name", "expiry", "strike", "cp",
            "sum_amount", "vwap_iv", "vwap_index",
            "taker_buy_amount", "taker_sell_amount"]
    parts = []
    for k, f in enumerate(files):
        d = pd.read_parquet(f, columns=cols)
        parts.append(d)
        if (k + 1) % 12 == 0 or k + 1 == len(files):
            log(f"{coin}: loaded {k+1}/{len(files)} ({f.name})")
    d = pd.concat(parts, ignore_index=True)
    del parts
    d["hour"] = pd.to_datetime(d["hour"], utc=True)
    d["expiry"] = pd.to_datetime(d["expiry"], utc=True)
    d = d.drop_duplicates(["hour", "instrument_name"], keep="first")
    d = d[(d["hour"] >= GRID0) & (d["hour"] < GRID1)]
    d = d.sort_values("hour").reset_index(drop=True)
    log(f"{coin}: concat rows={len(d)} instruments={d['instrument_name'].nunique()} "
        f"hours={d['hour'].nunique()}")
    return d


def build_series(coin: str, d: pd.DataFrame) -> pd.DataFrame:
    grid = pd.date_range(GRID0, GRID1 - pd.Timedelta(hours=1), freq="h")
    n = len(grid)
    gns = grid.values.astype("datetime64[ns]").astype(np.int64)
    hidx = ((pd.to_datetime(d["hour"], utc=True).values.astype("datetime64[ns]")
             .astype(np.int64) - gns[0]) // 3_600_000_000_000).astype(np.int64)
    hidx = np.clip(hidx, 0, n - 1)

    inst = d["instrument_name"].astype(str).to_numpy()
    unames, iidx = np.unique(inst, return_inverse=True)
    ni = len(unames)
    strike = np.zeros(ni)
    expiry08 = np.zeros(ni, dtype=np.int64)
    first_h = np.full(ni, n + 10**6, dtype=np.int64)
    # per-instrument static: first row in time order is representative
    # (strike/cp/expiry constant per instrument name)
    df_first = d.groupby("instrument_name", sort=False).first()
    fmap = {k: i for i, k in enumerate(unames)}
    exp08 = (pd.to_datetime(df_first["expiry"], utc=True).dt.floor("D")
             + pd.Timedelta(hours=8))
    for name, row_i in df_first.iterrows():
        i = fmap[str(name)]
        strike[i] = float(row_i["strike"])
    for name, ts in exp08.items():
        fmap_i = fmap[str(name)]
        expiry08[fmap_i] = int(pd.Timestamp(ts).value)

    dq = (pd.to_numeric(d["taker_buy_amount"], errors="coerce").fillna(0.0)
          - pd.to_numeric(d["taker_sell_amount"], errors="coerce").fillna(0.0)).to_numpy(dtype=float)
    # raw vwap_iv is PERCENT; convert to decimal, sentinel >=990 / <1.0 -> NaN
    iv_raw = pd.to_numeric(d["vwap_iv"], errors="coerce").to_numpy(dtype=float)
    iv = np.where(np.isfinite(iv_raw) & (iv_raw >= IV_RAW_LO) & (iv_raw < IV_RAW_HI),
                  iv_raw / 100.0, np.nan)
    vx = pd.to_numeric(d["vwap_index"], errors="coerce").to_numpy(dtype=float)
    amt = pd.to_numeric(d["sum_amount"], errors="coerce").fillna(0.0).to_numpy(dtype=float)

    S_med = np.full(n, np.nan)
    H = np.zeros(n)
    med = d.assign(_h=hidx, _vx=vx).groupby("_h")["_vx"].median()
    S_med[med.index.to_numpy()] = med.to_numpy(dtype=float)
    notional = d.assign(_h=hidx, _n=amt * vx).groupby("_h")["_n"].sum(min_count=1)
    H[notional.index.to_numpy()] = np.nan_to_num(notional.to_numpy(dtype=float), nan=0.0)

    # per-hour row lists
    order = np.argsort(hidx, kind="stable")
    hs = hidx[order]
    ii = iidx[order]
    dqq = dq[order]
    ivv = iv[order]
    uniq_h, ptr = np.unique(hs, return_index=True)
    bounds = np.append(ptr[1:], len(hs))

    q = np.zeros(ni)
    iv_last = np.full(ni, np.nan)
    S_last = np.nan
    GEX = np.full(n, np.nan)
    S_out = np.full(n, np.nan)
    K = strike
    exp_ns = expiry08
    ui = 0
    for j in range(n):
        t_end_ns = gns[j] + 3_600_000_000_000
        # apply this hour's flows first (hour's trades known at hour end)
        while ui < len(uniq_h) and uniq_h[ui] == j:
            s, e = ptr[ui], bounds[ui]
            seg = ii[s:e]
            q[seg] += dqq[s:e]
            giv = ivv[s:e]
            good = np.isfinite(giv)  # already filtered to [0.01, 9.9) decimal at load
            iv_last[seg[good]] = giv[good]
            # first-trade hour (vectorised)
            np.minimum.at(first_h, seg, j)
            ui += 1
        while ui < len(uniq_h) and uniq_h[ui] < j:
            ui += 1  # safety (should not happen; hidx sorted)
        if np.isfinite(S_med[j]):
            S_last = S_med[j]
        S_out[j] = S_last
        if np.isfinite(S_last) and S_last > 0:
            alive = exp_ns > t_end_ns
            ok = alive & np.isfinite(iv_last) & (K > 0)
            if ok.any():
                ivu = np.clip(iv_last[ok], IV_LO, IV_HI)
                T = np.maximum((exp_ns[ok] - t_end_ns) / 1e9 / YEAR_SEC, 1.0 / 8760.0)
                sq = ivu * np.sqrt(T)
                d1 = (np.log(S_last / K[ok]) + 0.5 * ivu * ivu * T) / sq
                gam = np.exp(-0.5 * d1 * d1) / SQRT2PI / (S_last * sq)
                GEX[j] = float(-np.sum(q[ok] * gam * S_last * S_last * 0.01))
        if (j + 1) % 10000 == 0 or j + 1 == n:
            log(f"{coin}: hour {j+1}/{n}")
    Hc = np.cumsum(np.concatenate([[0.0], H]))
    N30 = np.full(n, np.nan)
    # trailing 720h mean; first 719 grid hours have no full window (-> NaN).
    # min-history 168 is satisfied for every j >= 719, so the rule binds there.
    N30[N30_WIN - 1:] = (Hc[N30_WIN:] - Hc[:-N30_WIN]) / N30_WIN
    GEXn = GEX / (S_out * N30)
    hour_end = grid + pd.Timedelta(hours=1)
    out = pd.DataFrame({"hour_end": hour_end, "S": S_out, "GEX": GEX,
                        "H": H, "N30": N30, "GEXn": GEXn})
    out = out[out["hour_end"] >= PROXY_START].reset_index(drop=True)
    # censored-share diagnostics: "older" (listed 2020) = first in-sample trade
    # at/before OLD_CUTOFF; "relevant" = alive at PROXY_START and listed by then.
    ps_j = int((PROXY_START - GRID0).total_seconds() // 3600)
    old_j = int((OLD_CUTOFF - GRID0).total_seconds() // 3600)
    ps_end_ns = gns[ps_j] + 3_600_000_000_000
    alive_ps = exp_ns > ps_end_ns
    listed_ps = first_h <= ps_j
    older = first_h <= old_j
    rel = alive_ps & listed_ps
    n_rel = int(rel.sum())
    n_old = int((rel & older).sum())
    log(f"{coin}: relevant(alive+listed)@2021-04-01={n_rel} older(first<={OLD_CUTOFF.date()})={n_old} "
        f"share={n_old/max(n_rel,1):.3f}")
    return out, {"n_rel": n_rel, "n_old": n_old,
                 "first_h": first_h, "exp_ns": exp_ns, "unames": unames,
                 "ps_j": ps_j, "old_j": old_j}


def censored_volume_share(coin: str, d: pd.DataFrame, info: dict) -> dict:
    fmap = {k: i for i, k in enumerate(info["unames"])}
    fh = info["first_h"]
    old_j = info["old_j"]
    ps_end = int(pd.Timestamp("2021-04-01 00:00", tz="UTC").value) + 3_600_000_000_000
    old_set = {u for u in info["unames"] if fh[fmap[u]] <= old_j}
    rel_set = {u for i, u in enumerate(info["unames"])
               if info["exp_ns"][i] > ps_end and fh[fmap[u]] <= info["ps_j"]}
    m = (d["hour"] >= GRID0) & (d["hour"] < PROXY_START)
    dd = d.loc[m]
    dd = dd.assign(_n=pd.to_numeric(dd["sum_amount"], errors="coerce").fillna(0.0)
                   * pd.to_numeric(dd["vwap_index"], errors="coerce"))
    tot = float(dd["_n"].sum())
    old_not = float(dd.loc[dd["instrument_name"].astype(str).isin(old_set), "_n"].sum())
    # |q| at proxy start per instrument (flows strictly before PROXY_START)
    dq = (pd.to_numeric(dd["taker_buy_amount"], errors="coerce").fillna(0.0)
          - pd.to_numeric(dd["taker_sell_amount"], errors="coerce").fillna(0.0))
    qq = dq.groupby(dd["instrument_name"].astype(str)).sum()
    qa = qq.reindex(sorted(rel_set)).fillna(0.0).abs()
    oqa = qa.reindex(sorted(old_set)).fillna(0.0).sum()
    return {"preVol_total": tot, "preVol_old": old_not,
            "preVol_old_share": old_not / tot if tot else float("nan"),
            "n_rel": info["n_rel"], "n_old": info["n_old"],
            "absQ_old_share": float(oqa / qa.sum()) if float(qa.sum()) > 0 else float("nan")}


def main() -> None:
    meta = {}
    for coin in COINS:
        d = load_coin(coin)
        out, info = build_series(coin, d)
        cs = censored_volume_share(coin, d, info)
        meta[coin] = cs
        log(f"{coin}: pre-start older-instrument volume share={cs['preVol_old_share']:.3f} "
            f"|q| share={cs['absQ_old_share']:.3f}")
        fp = HERE / f"gex_hourly_{coin}.parquet"
        out.to_parquet(fp, index=False)
        log(f"{coin}: wrote {fp.name} rows={len(out)} "
            f"GEXn finite={int(np.isfinite(out['GEXn']).sum())} "
            f"median GEXn={float(np.nanmedian(out['GEXn'])):.6g}")
        del d, out
    import json
    (HERE / "tmp" / "gex_meta.json").write_text(json.dumps(meta, indent=1))
    log("done")


if __name__ == "__main__":
    main()
