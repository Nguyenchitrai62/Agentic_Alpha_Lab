"""mj W16 capitulation event study: definitions fixed in patterns/capitulation.py, run once.

Evaluates ONLY via common.event_study (decisions before 2025-09-14).
Never computes forward returns for dates >= 2025-09-24.

Data:
- BTC 1h: data/raw/ma_ribbon_20260924/klines_1h.parquet (exists).
- BTC 15m: data/raw/btc_intraday_20260924/klines_15m.parquet (exists).
- ETH/SOL/BNB/XRP 15m/1h: data/raw/majors_intraday_20260924/{SYM}_{tf}.parquet,
  fetched with agentic_alpha_lab.data.binance_usdm.fetch_klines if absent.

Cascade (fixed before results): per timeframe, align single-asset flush flags
on open_time; cascade flag = >=3 of 5 majors flush in the same bar:
- cap_ev_cascade_down_rev: +1 where >=3 print flush_down_wick (BTC proxy).
- cap_ev_cascade_down_cont: -1 where >=3 print flush_down_nowick.
- cap_ev_cascade_up_rev: -1 where >=3 print flush_up_wick.
- cap_ev_cascade_up_cont: +1 where >=3 print flush_up_nowick.
Evaluated on BTC bars via common.event_study. BTC OI-flush cross-check uses
patterns.positioning pos_ev_oi_flush on BTC bars.
"""

import torch  # noqa: F401  (import first: Windows DLL load order)

from datetime import datetime, timezone
from pathlib import Path
import time

import pandas as pd
import requests

from agentic_alpha_lab.data import binance_usdm
from agentic_alpha_lab.patterns import capitulation as cap
from agentic_alpha_lab.patterns import common, positioning

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "research" / "mj" / "capitulation"
MAJORS_DIR = ROOT / "data" / "raw" / "majors_intraday_20260924"
BTC_1H = ROOT / "data" / "raw" / "ma_ribbon_20260924" / "klines_1h.parquet"
BTC_15M = ROOT / "data" / "raw" / "btc_intraday_20260924" / "klines_15m.parquet"

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
STARTS = {
    "BTCUSDT": datetime(2019, 9, 8, tzinfo=timezone.utc),
    "ETHUSDT": datetime(2019, 11, 1, tzinfo=timezone.utc),
    "BNBUSDT": datetime(2020, 2, 1, tzinfo=timezone.utc),
    "XRPUSDT": datetime(2020, 1, 1, tzinfo=timezone.utc),
    "SOLUSDT": datetime(2020, 9, 1, tzinfo=timezone.utc),
}
END = datetime(2026, 9, 24, tzinfo=timezone.utc)
HORIZONS = {"15m": (4, 16, 48, 96), "1h": (1, 4, 12, 24)}


def _fetch_with_retry(sym: str, tf: str) -> pd.DataFrame:
    """fetch_klines with backoff on 429/5xx (Binance weight limits)."""
    last: Exception | None = None
    for attempt in range(1, 8):
        try:
            return binance_usdm.fetch_klines(
                symbol=sym, interval=tf, start=STARTS[sym], end=END
            )
        except requests.exceptions.HTTPError as e:
            last = e
            status = e.response.status_code if e.response is not None else -1
            wait = 60 * attempt if status == 429 else 15 * attempt
            print(f"{sym} {tf}: HTTP {status}, retry {attempt}/7 after {wait}s",
                  flush=True)
            time.sleep(wait)
    raise RuntimeError(f"fetch failed for {sym} {tf}: {last}")


def _read_parquet_retry(path: Path, what: str) -> pd.DataFrame:
    """Read with retries: a peer worker may be mid-write on first attempt."""
    last: Exception | None = None
    for attempt in range(1, 7):
        try:
            return pd.read_parquet(path).sort_values("open_time").reset_index(drop=True)
        except Exception as e:  # noqa: BLE001 (transient peer write)
            last = e
            print(f"{what}: read attempt {attempt}/6 failed ({type(e).__name__}), "
                  "waiting 60s", flush=True)
            time.sleep(60)
    raise RuntimeError(f"could not read {path}: {last}")


def load_asset_tf(sym: str, tf: str) -> pd.DataFrame:
    if sym == "BTCUSDT":
        src = BTC_1H if tf == "1h" else BTC_15M
        bars = pd.read_parquet(src).sort_values("open_time").reset_index(drop=True)
        return bars
    MAJORS_DIR.mkdir(parents=True, exist_ok=True)
    path = MAJORS_DIR / f"{sym}_{tf}.parquet"
    if not path.exists():
        print(f"fetching {sym} {tf} ...", flush=True)
        bars = _fetch_with_retry(sym, tf)
        q = binance_usdm.validate_klines(bars, tf)
        print(f"{sym} {tf}: rows={q.rows} {q.first_open_time}..{q.last_close_time} "
              f"missing={q.missing_intervals}", flush=True)
        bars.to_parquet(path, index=False)
        time.sleep(30)  # cool down between symbols (weight limits)
    return _read_parquet_retry(path, f"{sym} {tf}")


def cascade_on_btc(btc: pd.DataFrame, feats: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Study-level cascade events aligned on BTC open_time (>=3 of 5 flush)."""
    base = pd.DataFrame({"open_time": pd.to_datetime(btc["open_time"], utc=True)})
    cols: dict[str, pd.Series] = {}
    for key in ("cap_flush_down_wick", "cap_flush_down_nowick",
                "cap_flush_up_wick", "cap_flush_up_nowick"):
        votes = pd.DataFrame({"open_time": base["open_time"]})
        for sym, f in feats.items():
            s = pd.Series(f[key].to_numpy(float).astype(bool))
            ot = pd.to_datetime(load_cache_ot[sym]).copy()
            v = pd.DataFrame({"open_time": ot, "v": s.to_numpy()})
            v = v.drop_duplicates("open_time").set_index("open_time")
            true_times = set(v.index[v["v"].to_numpy(dtype=bool)])
            votes[sym] = votes["open_time"].isin(true_times)
        n = votes[[s for s in feats]].sum(axis=1).to_numpy(int)
        cols[key] = pd.Series(n >= 3, index=btc.index)
    idx = btc.index
    ev = pd.DataFrame(index=idx)
    ev["cap_ev_cascade_down_rev"] = (cols["cap_flush_down_wick"].to_numpy(bool)
                                     .astype("int8"))
    ev["cap_ev_cascade_down_cont"] = (cols["cap_flush_down_nowick"].to_numpy(bool)
                                      .astype("int8") * -1)
    ev["cap_ev_cascade_up_rev"] = (cols["cap_flush_up_wick"].to_numpy(bool)
                                   .astype("int8") * -1)
    ev["cap_ev_cascade_up_cont"] = (cols["cap_flush_up_nowick"].to_numpy(bool)
                                    .astype("int8"))
    return ev.astype("int8")


load_cache_ot: dict[str, pd.Series] = {}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for tf in ("15m", "1h"):
        feats: dict[str, pd.DataFrame] = {}
        btc = None
        for sym in SYMS:
            bars = load_asset_tf(sym, tf)
            load_cache_ot[sym] = bars["open_time"]
            feats[sym] = cap.compute(bars)
            ev = cap.events(bars)
            res = common.event_study(bars, ev, horizons=HORIZONS[tf], tf=f"{sym}_{tf}")
            res.to_csv(OUT / f"event_study_{sym}_{tf}.csv", index=False)
            frames.append(res)
            n_sig = int(res["stable_significant"].sum()) if len(res) else 0
            print(f"{sym} {tf}: rows={len(res)} stable_significant={n_sig}", flush=True)
        btc = load_asset_tf("BTCUSDT", tf)
        casc = cascade_on_btc(btc, feats)
        res_c = common.event_study(btc, casc, horizons=HORIZONS[tf], tf=f"CASCADE_{tf}")
        res_c.to_csv(OUT / f"event_study_CASCADE_{tf}.csv", index=False)
        frames.append(res_c)
        print(f"CASCADE {tf}: rows={len(res_c)} "
              f"stable={int(res_c['stable_significant'].sum()) if len(res_c) else 0}",
              flush=True)
        oi = positioning.events(btc)[["pos_ev_oi_flush"]]
        res_o = common.event_study(btc, oi, horizons=HORIZONS[tf], tf=f"OI_BTC_{tf}")
        res_o.to_csv(OUT / f"event_study_OI_BTC_{tf}.csv", index=False)
        frames.append(res_o)
        print(f"OI_BTC {tf}: rows={len(res_o)} "
              f"stable={int(res_o['stable_significant'].sum()) if len(res_o) else 0}",
              flush=True)
    all_res = pd.concat(frames, ignore_index=True)
    all_res.to_csv(OUT / "event_study_all.csv", index=False)
    sig = all_res[all_res["stable_significant"]]
    sig.to_csv(OUT / "event_study_stable_significant.csv", index=False)
    print(f"total={len(all_res)} stable={len(sig)}", flush=True)
    mx = float(all_res["mean_excess_bps"].abs().max()) if len(all_res) else float("nan")
    with open(OUT / "SUMMARY.md", "w") as f:
        f.write("# mj W16 capitulation summary\n")
        f.write(f"1. rows={len(all_res)} stable_significant={len(sig)} (q<0.10, n>=30, sign-stable halves).\n")
        f.write(f"2. max |mean_excess|={mx:.1f} bps vs ~4-8 bps round-trip cost.\n")
        if len(sig):
            top = sig.sort_values("mean_excess_bps", ascending=False).iloc[0]
            f.write(f"3. top stable: {top['tf']} {top['pattern']} h={int(top['horizon'])} "
                    f"n={int(top['n'])} {float(top['mean_excess_bps']):.1f} bps "
                    f"hit={float(top['hit_rate']):.2f} q={float(top['q_value']):.3f}.\n")
        else:
            f.write("3. no stable_significant pattern-horizon; effects below cost.\n")
        f.write("4. cascade (>=3/5 flush): see event_study_CASCADE_*.csv for n/bps/hit/stability.\n")
        f.write("5. BTC OI-flush cross-check: see event_study_OI_BTC_*.csv.\n")
        f.write("6. verdict: leader decides; single-asset flush rare, cascade rarer.\n")


if __name__ == "__main__":
    main()
