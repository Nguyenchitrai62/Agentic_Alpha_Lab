"""Phase-shifted CB book members: rebuild the deployed CB members on 4h grids shifted by s hours (research diagnostic).

CB = scripts/forward_v205.research_books_d2 = 0.8 x O1 + 0.2 x (D + Dq)/2, O1 = 0.5 (A + B)/2 + 0.5 (Aq + Bq)/2 with
  A / Aq  = v240 O1 members  (v144 builder + TradingView 4h set + order-level whale flow; v202 quarterly wrapper)
  B / Bq  = v233 B_tv members (v150 options-flow builder + TradingView 4h set)
  D / Dq  = v154 / v206 Coinbase-premium members (v144 builder + v111 cb_* features)
The audited builders are used unchanged (fresh module instances); only their DATA entry points are replaced:
  * perp 4h bars           : Binance USD-M 1h klines aggregated to [s + 4k, s + 4k + 4) UTC (partial bars kept, as Binance does)
  * spot 2017 prefix 4h    : Binance spot 1h_2017 klines aggregated the same way (only where the original used a prefix)
  * Coinbase / Bitstamp 4h : the v113/v114 1h resampler with offset s hours (daily bars unchanged)
  * order-level flow 4h    : the 1m order store (8 log bins) summed into the 4 v236 tiers on the shifted bars
  * daily bars, funding    : unchanged (they enter via merge_asof on the bar close, i.e. the last closed value)
  * options (B), Coinbase premium (D): only 4h-grid inputs exist locally (Deribit 4h aggregates; Binance SPOT 4h closes),
    so the shifted row t uses the standard row t - s h, i.e. the last standard bar closed s hours earlier (as-of, causal).
Labels, horizons, embargoes, anchors, model specs and seeds are the builders' own (bars are 4h on every grid).

Fits are checkpointed per (phase, feature panel, model, anchor) under ckpt/, together with leakage records (max label end
of the training rows vs anchor - embargo). Annual anchors are a subset of the quarterly anchors and give identical fits, so
annual members reuse the quarterly checkpoints; the 'frozen' quarterly variant (last year predicted only by the
2025-09-24 model) reuses them too.

  python research/diagnostics/phase_books/phase_books.py --phase 1            # all members + books for s = 1
  python research/diagnostics/phase_books/phase_books.py --phase 0 --native   # wiring check with the original 4h files
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import importlib.util
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OUT = Path(__file__).resolve().parent
CACHE = ROOT / "artifacts/research/engine_real"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
XS = ROOT / "data/raw/xs_universe_20260924"
BTCD = ROOT / "data/raw/ma_ribbon_20260924"
SP = ROOT / "data/raw/spot_majors_20260925"
INTRA = ROOT / "data/raw/majors_intraday_20260924"
FLOW1M = ROOT / "data/raw/aggflow_20260929_orders_1m"
ORDERS = ROOT / "data/raw/aggflow_20260928_orders"
CBD = ROOT / "data/raw/coinbase_20260925"
BSD = ROOT / "data/raw/bitstamp_20260925"
FLOW_START = pd.Timestamp("2020-01-01", tz="UTC")  # first minute of the order archive download
H4 = pd.Timedelta(hours=4)
TIER_OF_BIN = {"lt1k": "lt10k", "1k_10k": "lt10k", "10k_30k": "10k_100k", "30k_100k": "10k_100k",
               "100k_300k": "100k_1m", "300k_1m": "100k_1m", "1m_3m": "ge1m", "ge3m": "ge1m"}
TIERS = ("lt10k", "10k_100k", "100k_1m", "ge1m")
KLINE_SUM = ("volume", "quote_volume", "num_trades", "taker_buy_volume", "taker_buy_quote_volume")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _utc(x):
    return pd.to_datetime(x, utc=True)


# ----------------------------------------------------------------------------------------------------------- data layer
def agg_klines(h: pd.DataFrame, s: int, drop_leading_partial: bool = True) -> pd.DataFrame:
    """1h klines -> 4h bars opening at s + 4k UTC (open first, high max, low min, close last, sums). A leading bar with
    fewer than 4 hours (listing / file start) is dropped; later bars with missing hours are kept (as Binance 4h klines)."""
    h = h.copy()
    h["open_time"] = _utc(h["open_time"])
    h = h.drop_duplicates("open_time").sort_values("open_time")
    key = ((h["open_time"] - pd.Timedelta(hours=s)).dt.floor("4h") + pd.Timedelta(hours=s)).rename("open_time")
    g = h.groupby(key)
    b = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last()})
    for c in KLINE_SUM:
        if c in h.columns:
            b[c] = g[c].sum()
    n = g["open"].count().to_numpy()
    if drop_leading_partial:
        b = b.iloc[int(np.argmax(n >= 4)):]
    b = b.rename_axis("open_time").reset_index()
    b["close_time"] = b["open_time"] + H4 - pd.Timedelta(milliseconds=1)
    return b


class Sources:
    """Data entry points of the member builders on the grid shifted by s hours, optionally truncated at time `cut`
    (only information with timestamp < cut, i.e. what is known at the close `cut` of a shifted bar)."""

    def __init__(self, s: int, native: bool = False, cut: pd.Timestamp | None = None):
        assert s in (0, 1, 2, 3) and (not native or s == 0)
        self.s, self.native, self.cut = s, native, cut
        self._b = {}

    # ---- truncation helpers
    def _tr_open(self, df, col="open_time", width=pd.Timedelta(0)):
        """keep rows whose period [t, t + width) has closed by cut (width 0: timestamp < cut)."""
        if self.cut is None:
            return df
        t = _utc(df[col])
        return df[(t + width <= self.cut) if width > pd.Timedelta(0) else (t < self.cut)]

    # ---- perp / spot klines
    def perp_4h(self, sym):
        if self.native:
            b = pd.read_parquet(BTCD / "klines_4h.parquet") if sym == "BTCUSDT" else pd.read_parquet(XS / f"{sym}_4h.parquet")
            b["open_time"], b["close_time"] = _utc(b["open_time"]), _utc(b["close_time"])
            return self._tr_open(b, width=H4)
        h = pd.read_parquet(BTCD / "klines_1h.parquet") if sym == "BTCUSDT" else pd.read_parquet(INTRA / f"{sym}_1h.parquet")
        return agg_klines(self._tr_open(h, width=pd.Timedelta(hours=1)), self.s)

    def spot_prefix_4h(self, sym):
        if not (SP / f"{sym}_spot_4h_2017.parquet").exists():  # v92: prefix only where the 4h_2017 file exists (not SOL)
            return None
        if self.native:
            p = pd.read_parquet(SP / f"{sym}_spot_4h_2017.parquet")
            p["open_time"] = _utc(p["open_time"])
            return self._tr_open(p, width=H4)
        h = pd.read_parquet(SP / f"{sym}_spot_1h_2017.parquet")
        h["open_time"] = _utc(h["open_time"])
        span_end = _utc(pd.read_parquet(SP / f"{sym}_spot_4h_2017.parquet", columns=["open_time"])["open_time"]).max() + H4
        h = h[h["open_time"] < span_end]  # the original prefix covers only the 4h_2017 file's span
        b = agg_klines(self._tr_open(h, width=pd.Timedelta(hours=1)), self.s)
        return b[b["open_time"] + H4 <= span_end]

    def load_asset(self, s):
        """= v92.load_asset (perp 4h + daily + funding, spot 2017 prefix) on the shifted grid."""
        if s in self._b:
            b, d, f = self._b[s]
            return b.copy(), d.copy(), f.copy()
        b = self.perp_4h(s)
        if s == "BTCUSDT":
            d, f = pd.read_parquet(BTCD / "klines_1d.parquet"), pd.read_parquet(BTCD / "funding.parquet")
        else:
            d, f = pd.read_parquet(XS / f"{s}_1d.parquet"), pd.read_parquet(XS / f"{s}_funding.parquet")
        for x in (b, d):
            x["open_time"] = _utc(x["open_time"])
            x["close_time"] = _utc(x["close_time"])
        d = self._tr_open(d, col="close_time")  # daily bar known after its close
        pre_b = self.spot_prefix_4h(s)
        if pre_b is not None:
            pre_d = pd.read_parquet(SP / f"{s}_spot_1d_2017.parquet")
            pre_d["open_time"] = _utc(pre_d["open_time"])
            if "close_time" in pre_d.columns:
                pre_d["close_time"] = _utc(pre_d["close_time"])
                pre_d = self._tr_open(pre_d, col="close_time")
            pre_b = pre_b[pre_b["open_time"] < b["open_time"].iloc[0]]
            pre_d = pre_d[pre_d["open_time"] < d["open_time"].iloc[0]]
            b = pd.concat([pre_b[b.columns.intersection(pre_b.columns)], b], ignore_index=True)
            d = pd.concat([pre_d[d.columns.intersection(pre_d.columns)], d], ignore_index=True)
        f["fundingTime"] = _utc(f["fundingTime"])
        f = self._tr_open(f, col="fundingTime")
        out = (b.sort_values("open_time").reset_index(drop=True), d.sort_values("open_time").reset_index(drop=True), f.sort_values("fundingTime"))
        self._b[s] = out
        return out[0].copy(), out[1].copy(), out[2].copy()

    # ---- Coinbase / Bitstamp history prefix (v113 cb_bars / v114 cb_bars_ext with a shifted 4h origin)
    def _hourly(self, product):
        cb = pd.concat([pd.read_parquet(CBD / f"{product}_1h_pre2017.parquet"), pd.read_parquet(CBD / f"{product}_1h.parquet")], ignore_index=True)
        cb["open_time"] = _utc(cb["open_time"])
        if product == "BTC-USD":
            bs = pd.read_parquet(BSD / "btcusd_1h_2011_2015.parquet")
            bs["open_time"] = _utc(bs["open_time"])
            bs = bs[(bs.open_time >= pd.Timestamp("2013-01-01", tz="UTC")) & (bs.open_time < cb.open_time.min())]
            h = pd.concat([bs[["open_time", "open", "high", "low", "close", "volume"]], cb[["open_time", "open", "high", "low", "close", "volume"]]], ignore_index=True)
        else:
            h = cb
        return self._tr_open(h, width=pd.Timedelta(hours=1))

    def cb_bars_ext(self, product, rule, min_hours):
        h = self._hourly(product).drop_duplicates("open_time").set_index("open_time").sort_index()
        h["qv"] = h["volume"] * h["close"]
        off = pd.Timedelta(hours=self.s) if rule == "4h" else pd.Timedelta(0)
        g = h.resample(rule, label="left", closed="left", offset=off) if off > pd.Timedelta(0) else h.resample(rule, label="left", closed="left")
        b = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
                          "volume": g["volume"].sum(), "quote_volume": g["qv"].sum(), "n": g["close"].count()})
        b = b[b["n"] >= min_hours].drop(columns="n").reset_index()
        b["close_time"] = b["open_time"] + pd.Timedelta(rule) - pd.Timedelta(milliseconds=1)
        if self.cut is not None:
            b = b[b["close_time"] < self.cut]
        return b

    # ---- order-level whale flow (v236 tier table) from the 1m store
    def flow_table(self, sym):
        if self.native:
            f = pd.read_parquet(ORDERS / f"{sym}_flow_4h.parquet").sort_index()
            return f[f.index + H4 <= self.cut] if self.cut is not None else f
        parts, last = [], None
        for fn in sorted(glob.glob(str(FLOW1M / sym / "*.parquet"))):  # monthly files, then the daily files of the last month
            x = pd.read_parquet(fn)
            if not len(x):
                continue
            if last is not None and x.index.min() <= last:
                x = x[x.index > last]  # never count a minute twice (monthly + daily archive files)
            last = max(last, x.index.max()) if last is not None else x.index.max()
            if self.cut is not None:
                x = x[x.index < self.cut]
            if not len(x):
                continue
            key = (x.index - pd.Timedelta(hours=self.s)).floor("4h") + pd.Timedelta(hours=self.s)
            parts.append(x.astype("float64").groupby(key).sum())
        m = pd.concat(parts).groupby(level=0).sum()
        out = pd.DataFrame(0.0, index=m.index, columns=[f"{k}_{t}" for k in ("buy", "sell", "n") for t in TIERS])
        for c in m.columns:
            side, b = c.split("_", 1)
            t = TIER_OF_BIN[b]
            if side in ("buy", "sell"):
                out[f"{side}_{t}"] += m[c]
            else:  # nb_ / ns_ -> n_
                out[f"n_{t}"] += m[c]
        out = out[out.index >= FLOW_START]  # a shifted bar starting before the archive would be partial
        if self.cut is not None:
            out = out[out.index + H4 <= self.cut]
        out.index.name = None
        return out

    # ---- market-wide 4h-grid features (as-of the last standard bar closed s hours earlier)
    def opt_frame(self):
        o = pd.read_parquet(ROOT / "data/raw/deribit_opt_20260926/BTC_options_4h.parquet")
        o["t"] = _utc(o["bar"])
        if self.cut is not None:  # standard bars closed by cut
            o = o[o["t"] + H4 <= self.cut]
        o = o.set_index("t").sort_index()
        full = pd.date_range(o.index.min(), o.index.max(), freq="4h", tz="UTC")
        o = o.reindex(full)
        for c in ("call_buy", "call_sell", "put_buy", "put_sell", "n_trades"):
            o[c] = o[c].fillna(0.0)
        z = lambda s: (s - s.rolling(180, min_periods=90).mean()) / s.rolling(180, min_periods=90).std()
        tot = o[["call_buy", "call_sell", "put_buy", "put_sell"]].sum(axis=1)
        net = o["put_buy"] - o["put_sell"] - o["call_buy"] + o["call_sell"]
        pcr = np.log((o["put_buy"] + o["put_sell"]).clip(lower=1) / (o["call_buy"] + o["call_sell"]).clip(lower=1))
        skew = o["iv_otm_put"] - o["iv_otm_call"]
        fr = pd.DataFrame({"t": o.index, "opt_net6": (net.rolling(6).sum() / tot.rolling(6).sum().replace(0, np.nan)).to_numpy(),
                           "opt_pcr_z": z(pcr).to_numpy(), "opt_skew6": skew.rolling(6, min_periods=3).mean().to_numpy(),
                           "opt_skew_z": z(skew).to_numpy(), "opt_act_z": z(np.log(o["n_trades"].clip(lower=1))).to_numpy()})
        fr["t"] = fr["t"] + pd.Timedelta(hours=self.s)
        return fr

    def _premium(self, asset):
        cb = pd.read_parquet(CBD / f"{asset}-USD_1h.parquet")[["open_time", "close"]].rename(columns={"close": "cb"})
        cb["open_time"] = _utc(cb["open_time"])
        cb = self._tr_open(cb, width=pd.Timedelta(hours=1))
        parts = [pd.read_parquet(SP / f"{asset}USDT_spot_4h_2017.parquet"), pd.read_parquet(SP / f"{asset}USDT_spot_4h.parquet")]
        bn = pd.concat([p[["open_time", "close"]] for p in parts], ignore_index=True)
        bn["open_time"] = _utc(bn["open_time"])
        bn = bn.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
        if self.cut is not None:  # standard spot bars closed by cut
            bn = bn[bn["open_time"] + H4 <= self.cut].reset_index(drop=True)
        bn["key"] = bn["open_time"] + pd.Timedelta(hours=3)
        j = pd.merge_asof(bn, cb.sort_values("open_time"), left_on="key", right_on="open_time", direction="backward",
                          tolerance=pd.Timedelta(hours=2), suffixes=("", "_cb"))
        p = pd.DataFrame({"t": bn["open_time"], "cbp": 1e4 * np.log(j["cb"].astype(float) / j["close"].astype(float))})
        p6, p42 = p["cbp"].rolling(6, min_periods=4).mean(), p["cbp"].rolling(42, min_periods=30).mean()
        m540, s540 = p["cbp"].rolling(540, min_periods=270).mean(), p["cbp"].rolling(540, min_periods=270).std()
        return pd.DataFrame({"t": p["t"], "dev": p6 - m540, "z": (p6 - m540) / s540, "chg": p6 - p42})

    def cb_frame(self, grid_t):
        """v111.add_cb features on the standard grid restricted to grid_t (standard times), shifted by +s h."""
        b, e = self._premium("BTC"), self._premium("ETH")
        feat = pd.DataFrame({"t": b["t"], "cb_btc_dev": b["dev"], "cb_btc_z": b["z"], "cb_btc_chg": b["chg"]})
        feat = feat.merge(pd.DataFrame({"t": e["t"], "cb_eth_z": e["z"], "cb_eth_chg": e["chg"]}), on="t", how="left")
        cbf = grid_t.merge(feat, on="t", how="left").drop(columns="sym").drop_duplicates("t")
        cbf["t"] = cbf["t"] + pd.Timedelta(hours=self.s)
        return cbf


def standard_p103_grid():
    """t/sym grid of the original (unshifted, unpatched) v103 panel, as v154/v206 use for the cb merge."""
    p = OUT / "ckpt" / "std_p103_grid.pkl"
    if p.exists():
        return pd.read_pickle(p)
    v103 = _load("v103_grid", RD / "v103/v103_flow_short_horizon.py")
    g = v103.build()[["t", "sym"]]
    p.parent.mkdir(parents=True, exist_ok=True)
    g.to_pickle(p)
    return g


# ------------------------------------------------------------------------------------------------ fit instrumentation
LOOKUP = {"t": None}
FITS = []


class RecHGB(HistGradientBoostingRegressor):
    """HistGradientBoostingRegressor that records the timestamps of its training rows (behaviour unchanged)."""

    def fit(self, X, y, sample_weight=None):
        t = LOOKUP["t"]
        tt = t.loc[X.index] if t is not None else None
        FITS.append({"target": getattr(y, "name", None), "n": int(len(X)),
                     "t_max": None if tt is None else tt.max(), "t_min": None if tt is None else tt.min()})
        return super().fit(X, y) if sample_weight is None else super().fit(X, y, sample_weight=sample_weight)


def _label_end(target, t_max):
    """time of the latest price the training label of a row at t_max uses (open of that bar)."""
    if target == "fv":
        k = 43  # std of log-open returns over bars t+2..t+43 -> opens up to t+43
    elif target == "y":
        k = 1 + 42  # v92: log(o[t+1+H]/o[t+1]), H = 42
    else:
        k = 1 + int(str(target)[1:])
    return t_max + k * H4


KEEP = ["t", "sym", "pred", "rib", "vol42"]


class Checkpointer:
    def __init__(self, s, panel_name, native, log, tag=""):
        self.dir = OUT / "ckpt" / f"s{s}{'_native' if native else ''}{tag}" / panel_name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.log = log
        self.leak = {}

    def _sig(self, panel, feats):
        return hashlib.sha256((str(len(panel)) + "|" + ",".join(map(str, feats)) + "|" + str(panel["t"].min()) + "|" + str(panel["t"].max())).encode()).hexdigest()[:16]

    def wrap_tp(self, kind, fn, embargo_bars, feats_of):
        def w(panel, a, *args):
            feats = feats_of(args)
            sig = self._sig(panel, feats)
            p = self.dir / f"{kind}_{a}.pkl"
            if p.exists():
                obj = pickle.loads(p.read_bytes())
                if obj["sig"] == sig:
                    self.leak[(kind, a)] = obj["leak"]
                    return (obj["te"],) + tuple(obj["rest"])
                self.log(f"checkpoint signature mismatch {p} -> refit")
            FITS.clear()
            LOOKUP["t"] = panel["t"]
            t0 = time.time()
            r = fn(panel, a, *args)
            LOOKUP["t"] = None
            te = r[0][[c for c in KEEP if c in r[0].columns]].copy()
            cutoff = pd.Timestamp(a, tz="UTC") - embargo_bars * H4
            leak = [dict(f, label_end=_label_end(f["target"], f["t_max"]), cutoff=cutoff, anchor=pd.Timestamp(a, tz="UTC"),
                         ok=bool(_label_end(f["target"], f["t_max"]) < cutoff)) for f in FITS]
            p.write_bytes(pickle.dumps({"sig": sig, "te": te, "rest": r[1:], "leak": leak}))
            self.leak[(kind, a)] = leak
            self.log(f"fit {self.dir.name}/{kind} {a} rows={[f['n'] for f in leak]} {time.time() - t0:.0f}s")
            return (te,) + tuple(r[1:])
        return w

    def wrap_vp(self, fn, v129, embargo_bars):
        orig_add_fv = v129.add_fv

        def add_fv(panel):
            p = orig_add_fv(panel)
            LOOKUP["t"] = p["t"]
            return p
        v129.add_fv = add_fv

        def w(panel, feats, anchors, emb):
            assert emb == embargo_bars
            kind = "vol103" if "tbr_1" in feats else "vol92"
            sig = self._sig(panel, feats)
            res = []
            for a in anchors:
                p = self.dir / f"{kind}_{a}.pkl"
                if p.exists():
                    obj = pickle.loads(p.read_bytes())
                    if obj["sig"] == sig:
                        self.leak[(kind, a)] = obj["leak"]
                        res.append(obj["te"])
                        continue
                    self.log(f"checkpoint signature mismatch {p} -> refit")
                FITS.clear()
                t0 = time.time()
                te = fn(panel, feats, [a], emb)[0]
                LOOKUP["t"] = None
                cutoff = pd.Timestamp(a, tz="UTC") - emb * H4
                leak = [dict(f, label_end=_label_end(f["target"], f["t_max"]), cutoff=cutoff, anchor=pd.Timestamp(a, tz="UTC"),
                             ok=bool(_label_end(f["target"], f["t_max"]) < cutoff)) for f in FITS]
                p.write_bytes(pickle.dumps({"sig": sig, "te": te, "rest": (), "leak": leak}))
                self.leak[(kind, a)] = leak
                self.log(f"fit {self.dir.name}/{kind} {a} rows={[f['n'] for f in leak]} {time.time() - t0:.0f}s")
                res.append(te)
            return pd.concat(res, ignore_index=True), {}
        return w


# ---------------------------------------------------------------------------------------------------- member builders
Q20 = [str(d.date()) for d in pd.date_range("2021-09-24", periods=20, freq=pd.DateOffset(months=3))]


def _patch_data(v144, src):
    """Replace the data entry points of the builder modules."""
    ext, v103, v129 = v144.v115.v114.v113, v144.v103, v144.v129
    ext._orig_load = src.load_asset            # used by v113.load_asset_ext (adds the Coinbase/Bitstamp prefix)
    v144.v115.v114.cb_bars_ext = src.cb_bars_ext
    ext.cb_bars = src.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    v103.v92.load_asset = src.load_asset       # v103 panel: no Coinbase prefix (as in the original)
    return ext, v103, v129


def _patch_fits(v144, ck):
    """Wrap the four fit functions (before any schedule wrapper) with checkpoints + leakage records."""
    ext, v103, v129 = v144.v115.v114.v113, v144.v103, v144.v129
    for m in (ext.v92, ext.v94, v103, v129):
        m.HistGradientBoostingRegressor = RecHGB
    ext.v92.train_predict = ck.wrap_tp("v92", ext.v92.train_predict, ext.v92.EMBARGO_BARS, lambda args: ext.v92.FEATS)
    ext.v94.train_predict = ck.wrap_tp("v94", ext.v94.train_predict, ext.v94.EMBARGO_BARS, lambda args: args[0])
    v103.train_predict = ck.wrap_tp("v103", v103.train_predict, v103.EMBARGO, lambda args: args[0])
    v129.vol_predict = ck.wrap_vp(v129.vol_predict, v129, ext.v92.EMBARGO_BARS)
    return ext, v103, v129


def _schedule(v144, v202, schedule):
    if schedule == "annual":
        return
    if schedule == "quarterly":
        v202.Q = list(Q20)
        v202.END = {a: (Q20[i + 1] if i + 1 < len(Q20) else "2026-09-24") for i, a in enumerate(Q20)}
    elif schedule == "quarterly_frozen":  # the most recent year is predicted only by the 2025-09-24 model
        q = [a for a in Q20 if a <= "2025-09-24"]
        v202.Q = q
        v202.END = {a: (q[i + 1] if i + 1 < len(q) else "2026-09-24") for i, a in enumerate(q)}
    else:
        raise ValueError(schedule)
    v202.quarterly(v144)


def _tv_frame(tvm, load_asset):
    rows = []
    for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
        b, _, _ = load_asset(s)
        x = pd.DataFrame({"t": b["open_time"].to_numpy(), "sym": s})
        rows.append(pd.concat([x, tvm.tv_features(b).reset_index(drop=True)], axis=1))
    return pd.concat(rows, ignore_index=True)


def _flow_frame(tvm, flo, load_asset, src):
    rows = []
    for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
        b, _, _ = load_asset(s)
        t = pd.DatetimeIndex(b["open_time"])
        parts = [pd.DataFrame({"t": t, "sym": s}), tvm.tv_features(b).reset_index(drop=True),
                 flo.flow_features(s, t, None if src.native and src.cut is None else src.flow_table(s)).reset_index(drop=True)]
        rows.append(pd.concat(parts, axis=1))
    return pd.concat(rows, ignore_index=True)


def prepare(member, schedule, src, log, ckpt=True, anchors=None):
    """Patched module set for member in {A, B, D}; returns (v144, ck). books via v144.books_v142()[1]."""
    tag = f"{member}_{schedule}_{src.s}_{int(time.time() * 1e6) % 10**9}"
    v202 = _load(f"v202_{tag}", RD / "v202/v202_quarterly_retrain.py")
    tvm = _load(f"tv_{tag}", RD / "v231/tv_indicators.py")
    if member == "B":
        v150 = _load(f"v150_{tag}", RD / "v150/v150_options_flow.py")
        v144, extra_drop = v150.v144, set(v150.OPT)
    else:
        v144, extra_drop = _load(f"v144_{tag}", RD / "v144/v144_deploy_v3.py"), set()
    ext, v103, v129 = _patch_data(v144, src)
    ck = None
    if ckpt:  # (feature-panel use for the truncation test: data patches only)
        ck = Checkpointer(src.s, member, src.native, log, getattr(src, "tag", ""))
        _patch_fits(v144, ck)
    _schedule(v144, v202, schedule)
    if anchors is not None:
        ext.v92.ANCHORS = tuple(anchors)
    b92, b103, orig_vp = ext.v92.build, v103.build, v129.vol_predict
    if member == "A":  # v240 build_member(quarterly, keep_fills=False)
        flo = _load(f"flo_{tag}", RD / "v236/flow_features.py")
        flo.D = ORDERS
        base92 = b92()
        xf = _flow_frame(tvm, flo, ext.v92.load_asset, src)
        drop = {c for c in xf.columns if c not in ("t", "sym")}
        add = lambda p: p.merge(xf, on=["t", "sym"], how="left")
        ext.v92.build = lambda: add(base92)
    elif member == "B":  # v233 build_member(quarterly, options=True)
        ofeats = src.opt_frame()
        base92 = b92()
        xf = _tv_frame(tvm, ext.v92.load_asset)
        drop = extra_drop | set(tvm.TV)

        def add(p):
            return p.merge(ofeats, on="t", how="left").merge(xf, on=["t", "sym"], how="left")
        ext.v92.build = lambda: add(base92)
    elif member == "D":  # v154 books_coinbase / v206 member_d_quarterly
        cbf = src.cb_frame(standard_p103_grid())
        drop = {"cb_btc_dev", "cb_btc_z", "cb_btc_chg", "cb_eth_z", "cb_eth_chg"}
        add = lambda p: p.merge(cbf, on="t", how="left")
        ext.v92.build = lambda: add(b92())
    else:
        raise ValueError(member)
    v129.vol_predict = lambda panel, fs, anchors_, emb: orig_vp(panel, [c for c in fs if c not in drop], anchors_, emb)
    v103.build = lambda: add(b103())
    return v144, ck


def feature_panels(member, src):
    """Model-input panels of a member (v92/v94 panel after the v142 xs step, v103 panel after xs) - no fits."""
    v144, _ = prepare(member, "annual", src, print, ckpt=False)
    ext, v103, v142 = v144.v115.v114.v113, v144.v103, v144.v142
    p92 = ext.v92.build()
    p103 = v103.build()
    return v142.add_xs(p92, v142.BASE), v142.add_xs(p103, v142.BASE + v142.FLOWX)


def build_member(member, schedule, src, log, anchors=None):
    t0 = time.time()
    v144, ck = prepare(member, schedule, src, log, anchors=anchors)
    books = v144.books_v142()[1]
    log(f"member {member} {schedule} s={src.s} built {books.shape} in {time.time() - t0:.0f}s")
    return books[SYMS], ck.leak


def cb_books(m):
    """scripts/forward_v205.research_books_d2 on member frames m[A, Aq, B, Bq, D, Dq]."""
    idx = m["A"].index.union(m["Aq"].index)
    f = lambda X: X.reindex(idx).fillna(0.0)
    o1 = 0.5 * (f(m["A"][SYMS]) + f(m["B"][SYMS])) / 2 + 0.5 * (f(m["Aq"][SYMS]) + f(m["Bq"][SYMS])) / 2
    idx2 = o1.index.union(m["D"].index).union(m["Dq"].index)
    g = lambda X: X.reindex(idx2).fillna(0.0)
    return 0.8 * g(o1) + 0.2 * (g(m["D"][SYMS]) + g(m["Dq"][SYMS])) / 2


def run_phase(s, native=False, members=("A", "B", "D")):
    src = Sources(s, native=native)
    sfx = "_native" if native else ""
    logp = OUT / f"run_s{s}{sfx}.log"

    def log(msg):
        line = f"{pd.Timestamp.now():%Y-%m-%d %H:%M:%S} {msg}"
        print(line, flush=True)
        with open(logp, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    t_all = time.time()
    leak_all, timing = {}, {}
    names = {"annual": "", "quarterly": "q", "quarterly_frozen": "qf"}
    for mem in members:
        for sched in ("quarterly", "annual", "quarterly_frozen"):  # quarterly first: annual + frozen reuse its fits
            name = f"{mem}{names[sched]}"
            p = OUT / f"member_{name}_s{s}{sfx}.parquet"
            if p.exists():
                log(f"member {name} s={s} cached")
                continue
            t0 = time.time()
            bk, leak = build_member(mem, sched, src, log)
            bk.to_parquet(p)
            timing[name] = round(time.time() - t0, 1)
            leak_all[name] = {f"{k[0]}|{k[1]}": v for k, v in leak.items()}
    lp = OUT / f"leakage_s{s}{sfx}.json"
    old = json.loads(lp.read_text()) if lp.exists() else {}
    old.update(json.loads(json.dumps(leak_all, default=str)))
    lp.write_text(json.dumps(old, indent=1, default=str))
    if set(members) == {"A", "B", "D"}:
        m = {k: pd.read_parquet(OUT / f"member_{k}_s{s}{sfx}.parquet") for k in ("A", "Aq", "Aqf", "B", "Bq", "Bqf", "D", "Dq", "Dqf")}
        cb_books({"A": m["A"], "Aq": m["Aqf"], "B": m["B"], "Bq": m["Bqf"], "D": m["D"], "Dq": m["Dqf"]}).to_parquet(OUT / f"books_s{s}{sfx}.parquet")
        cb_books({k: m[k] for k in ("A", "Aq", "B", "Bq", "D", "Dq")}).to_parquet(OUT / f"books_s{s}{sfx}_v202sched.parquet")
    tp = OUT / f"timing_s{s}{sfx}.json"
    old = json.loads(tp.read_text()) if tp.exists() else {}
    old.update(timing)
    old["_last_run_total_s"] = round(time.time() - t_all, 1)
    tp.write_text(json.dumps(old, indent=1))
    log(f"phase s={s} done in {time.time() - t_all:.0f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", type=int, required=True)
    ap.add_argument("--native", action="store_true")
    ap.add_argument("--members", default="A,B,D")
    a = ap.parse_args()
    run_phase(a.phase, a.native, tuple(a.members.split(",")))


if __name__ == "__main__":
    sys.exit(main())
