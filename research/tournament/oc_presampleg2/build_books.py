"""oc_presampleg2 Part B: pre-sample book from the buildable members (walk-forward).

Frozen by PLAN.md (read it first). Method: fresh module copies (the v233/v240
pattern: importlib _load, never edit the originals); ONLY the price-panel
loader and the anchor lists are pointed at pre-sample spot data. Every feature
function, merge, model, hyperparameter, label, cutoff and embargo is the frozen
code, called as-is.

  python research/tournament/oc_presampleg2/build_books.py panel   # spot panel -> tmp/
  python research/tournament/oc_presampleg2/build_books.py B       # B + Bq (v233 TV+options recipe)
  python research/tournament/oc_presampleg2/build_books.py D       # D + Dq (v154/v285 premium recipe)
  python research/tournament/oc_presampleg2/build_books.py blend   # PB blend -> tmp/books_ps.parquet

Run under heavy_slot (tag oc_presampleg2). CPU only. Progress per anchor.
"""
from __future__ import annotations

import gc
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TMP = HERE / "tmp"
TMP.mkdir(exist_ok=True)

COINS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
SP = ROOT / "data/raw/spot_majors_20260925"
CUT = pd.Timestamp("2019-09-01", tz="UTC")

# Pre-registered anchors (PLAN.md): quarterly on the 24th from 2018-03-24
# (first anchor with >= 6 months of spot history) through 2020-06-24.
Q = [str(d.date()) for d in pd.date_range("2018-03-24", "2020-06-24",
                                          freq=pd.DateOffset(months=3))]
QANN = ("2018-09-24", "2019-09-24")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ============================================================ spot panel
def _read4(p: Path) -> pd.DataFrame:
    df = pd.read_parquet(p)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    # archive artefact: some prefix files store taker columns as strings
    for c in ("open", "high", "low", "close", "volume", "quote_volume",
              "num_trades", "taker_buy_volume", "taker_buy_quote_volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("open_time").reset_index(drop=True)


def build_panel():
    """Stitched Binance SPOT 4h/1d per coin (disclosed construction, my code):
    spot2017-prefix 4h/1d for t < 2019-09-01, spot_majors spot_4h after
    (dedup by open_time); 1d after the cut resampled from the stitched 4h
    (no spot_1d files exist). Same venue throughout; no seam choice."""
    B4, B1 = {}, {}
    for s in COINS:
        pre = _read4(SP / f"{s}_spot_4h_2017.parquet")
        post = _read4(SP / f"{s}_spot_4h.parquet")
        pre = pre[pre["open_time"] < CUT]
        b = pd.concat([pre, post], ignore_index=True)
        b = b.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
        B4[s] = b
        pre1 = _read4(SP / f"{s}_spot_1d_2017.parquet")
        pre1 = pre1[pre1["open_time"] < CUT]
        g = b.set_index("open_time")
        agg = {"open": "first", "high": "max", "low": "min", "close": "last",
               "volume": "sum", "quote_volume": "sum", "num_trades": "sum",
               "taker_buy_volume": "sum", "taker_buy_quote_volume": "sum"}
        d = g.resample("1D", label="left", closed="left").agg(agg).reset_index()
        d = d[d["open_time"] >= CUT].copy()
        d["close_time"] = d["open_time"] + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
        d1 = pd.concat([pre1, d[d.columns.intersection(pre1.columns)]],
                       ignore_index=True)
        d1 = d1.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
        B1[s] = d1
        print(f"panel {s}: 4h {b['open_time'].min()}..{b['open_time'].max()} n={len(b)}; "
              f"1d n={len(d1)}", flush=True)
    B4_all = pd.concat([df.assign(sym=s) for s, df in B4.items()], ignore_index=True)
    B4_all.to_parquet(TMP / "panel_4h.parquet")
    B1_all = pd.concat([df.assign(sym=s) for s, df in B1.items()], ignore_index=True)
    B1_all.to_parquet(TMP / "panel_1d.parquet")
    meta = {s: {"first_4h": str(B4[s]["open_time"].min()),
                "last_4h": str(B4[s]["open_time"].max()), "n_4h": len(B4[s]),
                "has_taker": bool("taker_buy_quote_volume" in B4[s].columns)}
            for s in COINS}
    (TMP / "panel_meta.json").write_text(json.dumps(meta, indent=1))
    return B4, B1


def make_loader(B4, B1):
    """v92.load_asset contract (b 4h, d 1d, f funding); funding is an EMPTY
    frame (f7/f30 NaN - disclosed; same NaN-tolerance the frozen stack already
    uses for its 2017 prefix). SOL (or any non-coin) -> 1 NaN row, filtered by
    the caller before any merge (SOL excluded: no pre-2020 data)."""
    cols4 = list(B4[COINS[0]].columns)
    cols1 = list(B1[COINS[0]].columns)

    def load_asset(s):
        if s in COINS:
            return (B4[s].copy(), B1[s].copy(),
                    pd.DataFrame({"fundingTime": pd.to_datetime([], utc=True),
                                  "fundingRate": np.array([], dtype=float)}))
        b = pd.DataFrame({c: [np.nan] for c in cols4})
        # valid but ancient timestamp (NaT keys crash merge_asof); the row is
        # filtered by _filt before any merge or fit (SOL excluded pre-2020).
        b["open_time"] = pd.to_datetime(["2010-01-01"], utc=True)
        b["close_time"] = pd.to_datetime(["2010-01-01"], utc=True)
        d = pd.DataFrame({c: [np.nan] for c in cols1})
        d["open_time"] = pd.to_datetime(["2010-01-01"], utc=True)
        d["close_time"] = pd.to_datetime(["2010-01-01"], utc=True)
        return (b, d, pd.DataFrame({"fundingTime": pd.to_datetime([], utc=True),
                                    "fundingRate": np.array([], dtype=float)}))

    return load_asset


def _filt(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["sym"].isin(COINS)].reset_index(drop=True)


# ============================================================ member recipes
def _prep_stack(tag: str, quarterly: bool, anchors, load_asset):
    """Fresh v144 stack with the spot loader + pre-sample anchors (my glue;
    every fitted/merge step below is the frozen code, called as-is)."""
    v144 = _load(f"v144_ps_{tag}", RD / "v144/v144_deploy_v3.py")
    ext = v144.v115.v114.v113
    v103 = v144.v103
    # Price panel: spot loader everywhere the stack reads bars.
    ext.v92.load_asset = load_asset
    v103.v92.load_asset = load_asset
    if quarterly:
        v202m = _load(f"v202_ps_{tag}", RD / "v202/v202_quarterly_retrain.py")
        v202m.Q = list(anchors)
        v202m.END = {a: (list(anchors)[i + 1] if i + 1 < len(anchors) else "2020-09-24")
                     for i, a in enumerate(anchors)}
        v202m.quarterly(v144)
    else:
        ext.v92.ANCHORS = tuple(anchors)
    return v144, ext, v103


def build_B(quarterly: bool, load_asset):
    """Deployed B/Bq recipe (v233.build_member with options=True): v144 base +
    17 TV features + 5 Deribit options features. Options merge is the frozen
    v150 code on its fixed deribit path (NaN before 2019-01/03, disclosed)."""
    tag = f"Bq" if quarterly else "B"
    anchors = Q if quarterly else list(QANN)
    v144, ext, v103 = _prep_stack(tag, quarterly, anchors, load_asset)
    v150 = _load(f"v150_ps_{tag}", RD / "v150/v150_options_flow.py")
    v231m = _load(f"v231_ps_{tag}", RD / "v231/v231_quality_features.py")
    OPT = list(v150.OPT)
    ofeats = v150.opt_features()
    TV = list(v231m.tvm.TV)
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    base92 = _filt(b92())
    xf = _filt(v231m.extra_features(("tv",), load_asset, None))
    drop = set(OPT) | set(TV)
    v144.v129.vol_predict = lambda panel, fs, a, emb: orig_vp(
        panel, [c for c in fs if c not in drop], a, emb)

    def add(p, _ofeats=ofeats):
        p = p.merge(_ofeats, on="t", how="left")
        return p.merge(xf, on=["t", "sym"], how="left")

    base103 = _filt(b103())
    ext.v92.build = lambda: _filt(add(base92))
    v103.build = lambda: _filt(add(base103))
    _, books = v144.books_v142()
    del base92, base103, xf
    gc.collect()
    return books


def build_D(quarterly: bool, load_asset):
    """Deployed D/Dq recipe (v154.books_coinbase / v206.member_d_quarterly):
    v144 base + 5 Coinbase-premium features via the frozen v111 code on its
    fixed (spot-based) sources."""
    tag = f"Dq" if quarterly else "D"
    anchors = Q if quarterly else list(QANN)
    v144, ext, v103 = _prep_stack(tag, quarterly, anchors, load_asset)
    v111 = _load(f"v111_ps_{tag}", RD / "v111/v111_coinbase_premium.py")
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    cbf = v111.add_cb(_filt(b103())[["t", "sym"]]).drop(
        columns="sym").drop_duplicates("t")
    base92 = _filt(b92())
    base103 = _filt(b103())
    v144.v129.vol_predict = lambda panel, fs, a, emb: orig_vp(
        panel, [c for c in fs if c not in v111.CB], a, emb)
    ext.v92.build = lambda: _filt(base92.merge(cbf, on="t", how="left"))
    v103.build = lambda: _filt(base103.merge(cbf, on="t", how="left"))
    _, books = v144.books_v142()
    del base92, base103, cbf
    gc.collect()
    return books


# ============================================================ driver
def cmd_books(which: str, scope: str = "all"):
    B4 = {s: g for s, g in pd.read_parquet(TMP / "panel_4h.parquet").groupby("sym")}
    B1 = {s: g for s, g in pd.read_parquet(TMP / "panel_1d.parquet").groupby("sym")}
    B4 = {s: B4[s].drop(columns="sym").reset_index(drop=True) for s in COINS}
    B1 = {s: B1[s].drop(columns="sym").reset_index(drop=True) for s in COINS}
    load_asset = make_loader(B4, B1)
    fits = json.loads((TMP / "fits.json").read_text()) if (TMP / "fits.json").exists() else {}
    builder = build_B if which == "B" else build_D
    flags = {"ann": (False,), "qtr": (True,)}.get(scope, (False, True))
    for quarterly in flags:
        name = f"{which}{'q' if quarterly else ''}_ps"
        print(f"building {name} anchors={Q if quarterly else list(QANN)}", flush=True)
        books = builder(quarterly, load_asset)
        books.to_parquet(TMP / f"member_{name}.parquet")
        fits[name] = {"anchors": Q if quarterly else list(QANN),
                      "first": str(books.index.min()), "last": str(books.index.max()),
                      "shape": list(books.shape), "cols": list(books.columns)}
        (TMP / "fits.json").write_text(json.dumps(fits, indent=1, default=str))
        print(f"{name} done shape={books.shape} "
              f"{books.index.min()}..{books.index.max()}", flush=True)
        del books
        gc.collect()


def cmd_blend():
    parts = {}
    for name in ("B_ps", "Bq_ps", "D_ps", "Dq_ps"):
        p = TMP / f"member_{name}.parquet"
        parts[name] = pd.read_parquet(p) if p.exists() else None
    have_D = parts["D_ps"] is not None and parts["Dq_ps"] is not None
    o1 = (parts["B_ps"].reindex(
        parts["B_ps"].index.union(parts["Bq_ps"].index)).fillna(0.0)
        + parts["Bq_ps"].reindex(
            parts["B_ps"].index.union(parts["Bq_ps"].index)).fillna(0.0)) / 2
    if have_D:
        idx = o1.index.union(parts["D_ps"].index).union(parts["Dq_ps"].index)
        f = lambda X: X.reindex(idx).fillna(0.0)
        PB = 0.8 * f(o1) + 0.2 * (f(parts["D_ps"]) + f(parts["Dq_ps"])) / 2
        blend_note = "0.8*o1p+0.2*dp (full pre-registered blend)"
    else:  # pre-registered FALLBACK, labelled
        PB = o1.fillna(0.0)
        blend_note = "FALLBACK o1p only (D_ps/Dq_ps missing)"
    PB = PB.reindex(columns=list(COINS)).fillna(0.0)
    PB.to_parquet(TMP / "books_ps.parquet")
    out = {"blend": blend_note,
           "have_D": bool(have_D),
           "first": str(PB.index.min()), "last": str(PB.index.max()),
           "shape": list(PB.shape),
           "nnz_by_coin": {c: int((PB[c] != 0).sum()) for c in COINS}}
    (TMP / "blend.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1), flush=True)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    which = sys.argv[1] if len(sys.argv) > 1 else "panel"
    if which == "panel":
        build_panel()
    elif which in ("B", "D"):
        cmd_books(which, sys.argv[2] if len(sys.argv) > 2 else "all")
    elif which == "blend":
        cmd_blend()
    else:
        raise SystemExit(f"unknown subcommand {which}")
