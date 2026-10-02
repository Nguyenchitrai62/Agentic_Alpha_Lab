"""v316: POOLED-EXPERIENCE book member - the v94 long/short horizon ensemble trained on the 5 majors + the survivorship-free U2020 alt universe
(registry v316; controlled A/B, dev years only).

Why: the learned dip decisions beat the rules only once they were trained on pooled cross-asset experience (v293 -> v295: 5 -> 35 coins); the book
signal model has always been trained on the 5 majors (+ BTC / ETH history prefixes). v101 (13 survivor alts, 2026-09) was worse; U2020 removes the
survivorship bias (every USDT perp listed >= 28 days in Dec-2020, delisted coins end at delisting; research / training only, never traded).
DATA: majors = the audited v113 extended loader (ext.load_asset_ext: Binance perps + spot / Bitstamp / Coinbase prefixes, funding); alts = 4h bars
resampled from data/raw/alts2020_intraday_20260930 + alts_intraday_20260926 1m klines (open first, high max, low min, close last, volumes summed;
bar open time = 4h boundary; close_time = open + 4h - 1 ms), daily bars from the 4h bars, funding from data/raw/xs_universe_20260924/<sym>_funding
when it exists (else NaN; the v92 funding features become NaN). Features = v92.features (ret / snr 6..540, vol42 / 180, ema20 / 200, d50 / d200 / rib
from the daily bars known at the 4h close, f7 / f30, volz) + the BTC cross features (btc_ret42 / 180 / rib / snr42) of the same bar; asset id =
0..4 for the majors, 5 for every alt (no per-alt identity). Targets = v94 y18 / y42 / y84 (vol-normalised forward open-to-open returns, clip +-4).
MODELS (per anchor 2021-2024; cutoff = anchor - v94 embargo (84 + 60 bars), label end before the cutoff, HGB v94 hyper-parameters, seed 0):
  CTRL   trained on the majors rows only (= v94 on this panel)
  POOL   trained on majors + alt rows
Predictions for the MAJORS only; books = v94.weights_ls(shorts=True) on the mean of the three horizon predictions.
REPORT (dev years only, the most recent year is not computed): per-year Spearman IC of the prediction vs y42 for the majors; the MANUAL engine
(G2 manual rules: target 0.25, cap 2, grid trader, sleeve off) with books = 0.8 x (2 A + 2 B + D)/5 + 0.2 x member (CTRL vs POOL), v310 robust fitness
on dev4 and per year.
DECISION (fixed before running): POOL is a candidate member for the next walk-forward searches only if its IC beats CTRL in >= 3 of 4 dev years AND
its blended dev4 fitness beats CTRL's blend. No most-recent-year score in this version.

  python research/parallel/rounds/parallel-20260906-r2/v316/v316_pooled_universe_book_member.py
"""
from __future__ import annotations

import glob
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
RD = HERE.parent
DEV = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")
ALT4H = Path("artifacts/research/engine_real/v316_alt4h")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def alt_bars(sym):
    p = ALT4H / f"{sym}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    files = sorted(glob.glob(f"data/raw/alts2020_intraday_20260930/{sym}_1m_*.parquet")) or sorted(glob.glob(f"data/raw/alts_intraday_20260926/{sym}_1m_*.parquet"))
    parts = []
    for f in files:
        m = pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close", "volume", "quote_volume", "num_trades", "taker_buy_volume",
                                        "taker_buy_quote_volume"])
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        g = m.groupby(m["open_time"].dt.floor("4h"))
        parts.append(pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
                                   "volume": g["volume"].sum(), "quote_volume": g["quote_volume"].sum(), "num_trades": g["num_trades"].sum(),
                                   "taker_buy_volume": g["taker_buy_volume"].sum(), "taker_buy_quote_volume": g["taker_buy_quote_volume"].sum(),
                                   "n_min": g["open"].count()}))
    b = pd.concat(parts).sort_index()
    b = b[~b.index.duplicated()]
    b = b[b["n_min"] >= 200].drop(columns="n_min")  # drop bars with large gaps
    b.index.name = "open_time"
    b = b.reset_index()
    b["close_time"] = b["open_time"] + pd.Timedelta(hours=4) - pd.Timedelta(milliseconds=1)
    ALT4H.mkdir(parents=True, exist_ok=True)
    b.to_parquet(p)
    return b


def alt_asset(sym):
    b = alt_bars(sym)
    d = b.set_index("open_time").resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()
    d["close_time"] = d["open_time"] + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
    fp = Path(f"data/raw/xs_universe_20260924/{sym}_funding.parquet")
    if fp.exists():
        f = pd.read_parquet(fp)
        f["fundingTime"] = pd.to_datetime(f["fundingTime"], utc=True)
        f = f.sort_values("fundingTime")
    else:
        f = pd.DataFrame({"fundingTime": pd.to_datetime([], utc=True), "fundingRate": []})
    return b, d, f


def main():
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    v144 = _load("v144_u", RD / "v144/v144_deploy_v3.py")
    ext = v144.v115.v114.v113
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    v92, v94 = ext.v92, ext.v94
    majors = v92.build()  # audited majors panel (features, y, t, open, sym, asset, btc_*)
    btc = majors[majors.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    # U2020_all = v299.universe_all(): every non-major USDT perp listed >= 28 days in Dec-2020, by Dec-2020 quote volume (delisted included)
    v = pd.read_csv("data/raw/um_universe_20260930/volume_2020_12.csv")
    uni = list(v[(v.days >= 28) & ~v.symbol.isin(v92.SYMS)].sort_values("quote_volume_usd", ascending=False).symbol)
    rows = []
    for s in uni:
        try:
            b, d, f = alt_asset(s)
        except Exception as e:  # noqa: BLE001
            log(f"alt {s} skipped: {e}")
            continue
        if len(b) < 600:
            continue
        x, y = v92.features(b, d, f)
        x["asset"] = 5
        x["y"] = y
        x["t"] = b["open_time"].to_numpy()
        x["open"] = b["open"].to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x.join(btc, on="t"))
    alts = pd.concat(rows, ignore_index=True)
    log(f"alts: {alts.sym.nunique()} symbols, {len(alts)} rows; majors {len(majors)} rows")
    panel = v94.add_targets(pd.concat([majors, alts], ignore_index=True))
    feats = [c for c in majors.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    is_major = panel.sym.isin(v92.SYMS)
    out = {"version": "v316", "ic": {}, "rows": {}}
    books = {}
    for name, train_mask in (("CTRL", is_major), ("POOL", pd.Series(True, index=panel.index))):
        oos = []
        for a in DEV:
            a0 = pd.Timestamp(a, tz="UTC")
            cutoff = a0 - pd.Timedelta(hours=4 * v94.EMBARGO_BARS)
            te = panel[is_major & (panel.t >= a0) & (panel.t < a0 + pd.Timedelta(days=365))].copy()
            preds = []
            for h in v94.HORIZONS:
                tr = panel[train_mask & (panel.t < cutoff) & panel[f"y{h}"].notna()]
                tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
                m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0,
                                                  random_state=0)
                m.fit(tr[feats], tr[f"y{h}"])
                preds.append(m.predict(te[feats]))
            te["pred"] = np.mean(preds, axis=0)
            ic = float(te[["pred", "y42"]].corr(method="spearman").iloc[0, 1])
            out["ic"].setdefault(name, {})[a] = round(ic, 4)
            log(f"{name} {a} train rows {len(tr)} IC {ic:.4f}")
            oos.append(te)
        oos = pd.concat(oos, ignore_index=True)
        books[name] = v94.weights_ls(oos, True)
    C = Path("artifacts/research/engine_real")
    for name, W in books.items():
        W.to_parquet(C / f"member_{'U' if name == 'POOL' else 'Uc'}_pooled_dev.parquet")
    # MANUAL engine blend (dev years only)
    v310 = _load("v310_u", RD / "v310/v310_manual_book_robust_evolution.py")
    v310.init_worker()
    W0 = v310.W
    base = sum(dict(wA=2, wB=2, wD=1)[n] * W0["grp"][n] for n in ("wA", "wB", "wD")) / 5
    idx, cols = W0["idx"], W0["cols"]
    for name, W in books.items():
        mb = W.reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
        # integer weights (A2, B2, D1, P1) normalise to (2A + 2B + D + P) / 6; P is set so that the mix is exactly 0.8 x base + 0.2 x member
        mix = 0.8 * base + 0.2 * mb
        W0["grp"]["wP"] = 6 * mix - (2 * W0["grp"]["wA"] + 2 * W0["grp"]["wB"] + W0["grp"]["wD"])
        g = v310.encode(dict(target=0.25, cap=2.0, wP=1))
        r = v310.run_genome(g)
        out["rows"][name] = dict(dev4=v310.metrics(r, [0, 1, 2, 3]), F=round(v310.fitness(r, [0, 1, 2, 3]), 4),
                                 years=[v310.metrics(r, [y]) for y in range(4)])
        log(f"blend {name} dev4 {out['rows'][name]['dev4']} F {out['rows'][name]['F']}")
    wins = sum(out["ic"]["POOL"][a] > out["ic"]["CTRL"][a] for a in DEV)
    out["decision"] = dict(ic_wins=int(wins), blend_better=bool(out["rows"]["POOL"]["F"] > out["rows"]["CTRL"]["F"]))
    out["decision"]["candidate"] = bool(wins >= 3 and out["decision"]["blend_better"])
    log(f"DECISION {out['decision']}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v316_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
