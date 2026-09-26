"""Blind v98+v99 audit reproduction from OPENCODE_V98_V99_AUDIT.md spec.

Reads only raw data under data/raw/*, artifacts/research/carry/*, and audited
replications v92_audit/predictions_5asset.csv + v93_v94_audit/predictions_v94.csv.
Does NOT read research/.../v98/* or research/.../v99/* (blind until
replication.json is saved).

A1 (v98): v92 5-asset HGB with sample_weight = 0.5**(age_years/H),
  age = (training cutoff - row open_time) in 365.25-day years,
  H=2 (primary) and H=1 (secondary); everything else as v92
  (long-only book, causal 20% vol target, fee 0.0002, funding 0.00005).
A2 (v99): books = 0.5*W92*s92 + 0.5*W94ls*s94 (v96 replication);
  book_t = 0.8*sum(books_{t-2}*ret1_t) + 0.6*carry_{t-1};
  vol = rolling360(min120)std*sqrt(2190); s = min(0.15/vol,2) NaN->1;
  Wt = 0.8*s*books;
  net = sum(Wt*fwd) - turn(Wt)*0.0002 - 0.00005*long_gross
        + 0.6*s*carry_fwd - |diff(0.6*s)|*2*0.0004/1.2.
  Blind carry-forward convention (as v93 blind): carry position at t earns
  carry[t+1]; Part B reconciles if leader uses contemporaneous carry[t].
  Hidden-year 1m limit execution (blind assumption documented in code):
  each nonzero diff(Wt) per asset executes as limit at next 4h open;
  maker (0.0002) iff a 1m bar in minutes 2..15 trades STRICTLY through
  (buy: low<limit; sell: high>limit), else taker at minute-15 1m open
  with 0.0002 adverse slippage and 0.0005 fee. Carry leg keeps lab costs.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[5]
OUT_DIR = Path(__file__).resolve().parent
V92_DIR = ROOT / "research/parallel/rounds/parallel-20260906-r2/v92_audit"
V9394_DIR = ROOT / "research/parallel/rounds/parallel-20260906-r2/v93_v94_audit"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6
H_V92 = 42
EMBARGO_BARS = H_V92 + 10 * PD  # 102 bars = 408h, as v92
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"
HGB_PARAMS = dict(max_depth=4, learning_rate=0.03, max_iter=400,
                  min_samples_leaf=300, l2_regularization=1.0, random_state=0)
YEAR_DAYS = 365.25


def load_asset(s):
    if s == "BTCUSDT":
        b = pd.read_parquet(BTC_DIR / "klines_4h.parquet")
        d = pd.read_parquet(BTC_DIR / "klines_1d.parquet")
        f = pd.read_parquet(BTC_DIR / "funding.parquet")
    else:
        b = pd.read_parquet(XS_DIR / f"{s}_4h.parquet")
        d = pd.read_parquet(XS_DIR / f"{s}_1d.parquet")
        f = pd.read_parquet(XS_DIR / f"{s}_funding.parquet")
    for x in (b, d):
        x["open_time"] = pd.to_datetime(x["open_time"], utc=True)
        x["close_time"] = pd.to_datetime(x["close_time"], utc=True)
    f["fundingTime"] = pd.to_datetime(f["fundingTime"], utc=True)
    b = b.sort_values("open_time").reset_index(drop=True)
    d = d.sort_values("open_time").reset_index(drop=True)
    f = f.sort_values("fundingTime").reset_index(drop=True)
    if not (SPOT_DIR / f"{s}_spot_4h_2017.parquet").exists():
        s4 = b.iloc[:0].copy()
        s1 = d.iloc[:0].copy()
    else:
        s4 = pd.read_parquet(SPOT_DIR / f"{s}_spot_4h_2017.parquet")
        s1 = pd.read_parquet(SPOT_DIR / f"{s}_spot_1d_2017.parquet")
    for x in (s4, s1):
        x["open_time"] = pd.to_datetime(x["open_time"], utc=True)
        x["close_time"] = pd.to_datetime(x["close_time"], utc=True)
    first_4h = b["open_time"].min()
    first_1d = d["open_time"].min()
    pre4 = s4[s4["open_time"] < first_4h].copy()
    pre1 = s1[s1["open_time"] < first_1d].copy()
    b = pd.concat([pre4, b], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    d = pd.concat([pre1, d], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    return b, d, f


def base_features(b, d, f):
    c = b["close"].astype(float)
    lc = np.log(c)
    r1 = lc.diff()
    x = pd.DataFrame(index=b.index)
    vol42 = r1.rolling(42).std()
    for k in (6, 42, 90, 180, 540):
        dk = lc.diff(k)
        x[f"ret{k}"] = dk
        x[f"snr{k}"] = dk / (vol42 * np.sqrt(k))
    x["vol42"] = vol42
    x["vol180"] = r1.rolling(180).std()
    x["vol_ratio"] = x["vol42"] / x["vol180"]
    for sp in (20, 200):
        x[f"ema{sp}"] = np.log(c / c.ewm(span=sp, adjust=False, min_periods=sp).mean())
    dc = d["close"].astype(float)
    sma50 = dc.rolling(50).mean()
    sma200 = dc.rolling(200).mean()
    dfe = pd.DataFrame({
        "t": d["close_time"],
        "d50": np.log(dc / sma50),
        "d200": np.log(dc / sma200),
        "rib": np.where((dc > sma50) & (sma50 > sma200), 1.0,
                        np.where((dc < sma50) & (sma50 < sma200), -1.0, 0.0)),
    })
    j = pd.merge_asof(pd.DataFrame({"t": b["close_time"]}), dfe.sort_values("t"), on="t", direction="backward")
    x[["d50", "d200", "rib"]] = j[["d50", "d200", "rib"]].to_numpy()
    fr = f.set_index("fundingTime")["fundingRate"].astype(float)
    fm = pd.DataFrame({"t": fr.index,
                       "f7": fr.rolling(21, min_periods=3).mean().to_numpy(),
                       "f30": fr.rolling(90, min_periods=9).mean().to_numpy()})
    jf = pd.merge_asof(pd.DataFrame({"t": b["close_time"]}), fm.sort_values("t"), on="t", direction="backward")
    x["f7"] = jf["f7"].to_numpy() * 1e4
    x["f30"] = jf["f30"].to_numpy() * 1e4
    lv = np.log(b["quote_volume"].astype(float).clip(lower=1))
    x["volz"] = (lv - lv.rolling(180).mean()) / lv.rolling(180).std()
    o = b["open"].astype(float).to_numpy()
    n = len(b)
    fwd = np.full(n, np.nan)
    if n > 1 + H_V92:
        fwd[: n - 1 - H_V92] = np.log(o[1 + H_V92:] / o[1: n - H_V92])
    y = np.clip(fwd / (vol42.to_numpy() * np.sqrt(H_V92)), -4, 4)
    return x, y


def build_base_panel():
    rows = []
    for i, s in enumerate(SYMS):
        b, d, f = load_asset(s)
        x, y = base_features(b, d, f)
        x["asset"] = i
        x["y"] = y
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel = panel.join(btc, on="t")
    return panel


FEATS = None


def train_predict_recency(panel, anchor, half_life):
    """v92 train/predict with recency sample_weight (blind, causal)."""
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMBARGO_BARS)
    tr = panel[(panel.t < cutoff) & panel.y.notna()].copy()
    tr = tr[tr.t + pd.Timedelta(hours=4 * (H_V92 + 1)) < cutoff]
    age_years = (cutoff - tr["t"]).dt.total_seconds() / (YEAR_DAYS * 86400.0)
    # train rows are strictly before cutoff, so age >= 0 (clip tiny negatives)
    age_years = age_years.clip(lower=0.0)
    w = np.power(0.5, (age_years.to_numpy(dtype=float) / float(half_life)))
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    m = HistGradientBoostingRegressor(**HGB_PARAMS)
    m.fit(tr[FEATS], tr["y"], sample_weight=w)
    te["pred"] = m.predict(te[FEATS])
    return te, len(tr), w


def compute_weights_longonly(oos):
    Wdict = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        sig = g["pred"].clip(lower=0) / 0.5
        sig = sig.where(g["rib"] != -1, 0.0).clip(upper=1.0)
        Wdict[s] = sig / (g["vol42"] * np.sqrt(PD * 365))
    W = pd.DataFrame(Wdict).sort_index().fillna(0.0)
    W = W.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    row_sum = W.abs().sum(axis=1)
    n_pos = W.gt(0).sum(axis=1).clip(lower=1)
    W = W.div(row_sum.clip(lower=1e-9), axis=0).mul(row_sum.gt(0), axis=0)
    W = W.mul((n_pos / 5).clip(upper=1.0), axis=0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    W = W.where(keep, np.nan).ffill().fillna(0.0)
    return W


def compute_weights_longshort(oos):
    Wdict = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        p = g["pred"].astype(float)
        rib = g["rib"].astype(float)
        long = (p.clip(lower=0) / 0.5).clip(upper=1.0).where(rib != -1, 0.0)
        short = ((-p).clip(lower=0) / 0.5).clip(upper=1.0).where(rib != 1, 0.0)
        raw = (long - short) / (g["vol42"].astype(float) * np.sqrt(PD * 365))
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


def backtest_v92_style(oos_opens, W, vol_target=0.20):
    o = oos_opens
    ret1 = o / o.shift(1) - 1
    book = (W.shift(2).fillna(0.0) * ret1.fillna(0.0)).sum(axis=1)
    vol = book.rolling(360, min_periods=120).std(ddof=1) * np.sqrt(2190)
    scale = (vol_target / vol).clip(upper=2.0).fillna(1.0)
    scale = scale.replace([np.inf, -np.inf], 2.0).fillna(1.0)
    r_fwd = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    Wk = W.mul(scale, axis=0)
    turn = Wk.diff().abs().sum(axis=1).fillna(Wk.abs().sum(axis=1))
    funding = Wk.clip(lower=0).sum(axis=1) * 0.00005
    net = (Wk * r_fwd).sum(axis=1) - turn * 0.0002 - funding
    return net, turn, scale, book, vol


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


def run_v98(panel):
    out = {}
    for Hl in (2, 1):
        anchors_rec, oos_parts = [], []
        for anchor in ANCHORS:
            te, ntr, w = train_predict_recency(panel, anchor, Hl)
            ev = te.dropna(subset=["y"])
            rho = float(spearmanr(ev["pred"], ev["y"]).statistic) if len(ev) > 2 else float("nan")
            anchors_rec.append(dict(anchor=anchor, train_rows=int(ntr),
                                    n_pred_rows=int(len(te)),
                                    n_pred_rows_with_y=int(len(ev)),
                                    ic=round(rho, 4),
                                    w_min=round(float(w.min()), 6),
                                    w_max=round(float(w.max()), 6),
                                    w_mean=round(float(w.mean()), 6)))
            oos_parts.append(te)
            print(f"v98 H={Hl} {anchor} train {ntr} IC {round(rho,4)} wmean {float(w.mean()):.4f}", flush=True)
        oos = pd.concat(oos_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
        W = compute_weights_longonly(oos)
        o = oos.pivot_table(index="t", columns="sym", values="open")
        o = o[list(SYMS)]
        net, turn, scale, book, vol = backtest_v92_style(o, W, vol_target=0.20)
        yearly = yearly_slices(net, turn)
        out[Hl] = dict(anchors=anchors_rec, oos=oos, W=W, o=o, net=net,
                       turn=turn, scale=scale, yearly=yearly)
        print(f"v98 H={Hl} yearly:", json.dumps(yearly, indent=2), flush=True)
    return out


def run_v99_books():
    """Rebuild v96 books from audited OOS CSVs (no retrain)."""
    pred92 = pd.read_csv(V92_DIR / "predictions_5asset.csv", parse_dates=["t"])
    pred92["t"] = pd.to_datetime(pred92["t"], utc=True)
    oos92 = pred92.sort_values(["t", "sym"]).reset_index(drop=True)
    pred94 = pd.read_csv(V9394_DIR / "predictions_v94.csv", parse_dates=["t"])
    pred94["t"] = pd.to_datetime(pred94["t"], utc=True)
    oos94 = pred94.sort_values(["t", "sym"]).reset_index(drop=True)
    W92 = compute_weights_longonly(oos92)
    W94 = compute_weights_longshort(oos94)
    o = oos92.pivot_table(index="t", columns="sym", values="open").reindex(W92.index).sort_index()
    o = o[list(SYMS)]
    ret1 = o / o.shift(1) - 1

    def _scale(W):
        Wx = W.reindex(o.index).fillna(0.0)
        book = (Wx.shift(2).fillna(0.0) * ret1.fillna(0.0)).sum(axis=1)
        vol = book.rolling(360, min_periods=120).std(ddof=1) * np.sqrt(2190)
        sc = (0.20 / vol).clip(upper=2.0).fillna(1.0)
        sc = sc.replace([np.inf, -np.inf], 2.0).fillna(1.0)
        return sc, book, vol, Wx

    s92, book92, vol92, W92a = _scale(W92)
    s94, book94, vol94, W94a = _scale(W94)
    books = 0.5 * W92a.mul(s92, axis=0) + 0.5 * W94a.mul(s94, axis=0)
    return dict(W92=W92a, s92=s92, W94=W94a, s94=s94, books=books, o=o, ret1=ret1)


def run_v99_portfolio(books, o, ret1):
    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    c = carry.reindex(o.index)["carry"].astype(float).fillna(0.0)
    book = 0.8 * (books.shift(2).fillna(0.0) * ret1.fillna(0.0)).sum(axis=1) + 0.6 * c.shift(1).fillna(0.0)
    vol = book.rolling(360, min_periods=120).std(ddof=1) * np.sqrt(2190)
    s = (0.15 / vol).clip(upper=2.0).fillna(1.0)
    s = s.replace([np.inf, -np.inf], 2.0).fillna(1.0)
    r_fwd = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    carry_fwd = c.shift(-1).fillna(0.0)  # blind forward convention; see docstring
    Wt = books.mul(0.8 * s, axis=0)
    model_gross = (Wt * r_fwd).sum(axis=1)
    model_turn = Wt.diff().abs().sum(axis=1).fillna(Wt.abs().sum(axis=1))
    model_funding = Wt.clip(lower=0).sum(axis=1) * 0.00005
    model_net = model_gross - model_turn * 0.0002 - model_funding
    pos_c = 0.6 * s
    carry_gross = pos_c * carry_fwd
    carry_turn = pos_c.diff().abs().fillna(pos_c.abs())
    carry_cost = carry_turn * 2 * 0.0004 / 1.2
    carry_net = carry_gross - carry_cost
    net = model_net + carry_net
    return dict(net=net, model_turn=model_turn, carry_turn=carry_turn,
                scale=s, book=book, vol=vol, Wt=Wt, carry=c,
                model_net=model_net, carry_net=carry_net,
                r_fwd=r_fwd, carry_fwd=carry_fwd)


def limit_filled(side, limit_px, highs, lows):
    if highs.size == 0 or lows.size == 0:
        return False
    if not np.isfinite(limit_px):
        return False
    if side > 0:
        return bool(np.any(lows < limit_px))
    if side < 0:
        return bool(np.any(highs > limit_px))
    return False


def load_1m_hidden(start, end):
    bars = {}
    for s in SYMS:
        if s == "BTCUSDT":
            files = [ROOT / f"data/raw/btc_intraday_20260924/klines_1m_{y}.parquet" for y in (2025, 2026)]
        else:
            files = [ROOT / f"data/raw/majors_intraday_20260924/{s}_1m_{y}.parquet" for y in (2025, 2026)]
        parts = [pd.read_parquet(f) for f in files if f.exists()]
        df = pd.concat(parts, ignore_index=True)
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
        df = df[(df["open_time"] >= start - pd.Timedelta(days=2)) & (df["open_time"] < end + pd.Timedelta(days=2))]
        df = df.sort_values("open_time").reset_index(drop=True)
        bars[s] = df
    return bars


def run_hidden_execution(Wt, o, net, model_turn):
    """Blind 1m limit execution for hidden year trend leg.

    For each decision bar t with diff(Wt)[t]!=0, the order executes at the next
    4h bar open o[t+1]; maker iff 1m lows/highs in minutes 2..15 trade strictly
    through the limit; else taker at minute-15 1m open with 0.0002 adverse slip
    and 0.0005 fee. Extra cost vs normal (maker 0.0002 at open) is charged.
    """
    HIDDEN = pd.Timestamp("2025-09-24", tz="UTC")
    HEND = HIDDEN + pd.Timedelta(days=365)
    mask = (Wt.index >= HIDDEN) & (Wt.index < HEND)
    idx = Wt.index
    pos = {t: i for i, t in enumerate(idx)}
    m1 = load_1m_hidden(HIDDEN, HEND)
    # precompute searchsorted positions
    look = {}
    for s in SYMS:
        ot = m1[s]["open_time"].to_numpy().astype("datetime64[ns]")
        look[s] = (ot, m1[s]["open"].to_numpy(float),
                   m1[s]["high"].to_numpy(float), m1[s]["low"].to_numpy(float))
    diff = Wt.diff().fillna(Wt)
    total = 0
    maker = 0
    extra = pd.Series(0.0, index=Wt.index)
    missing_1m = 0
    for t in Wt.index[mask]:
        i = pos[t]
        if i + 1 >= len(idx):
            continue
        t_exec = idx[i + 1]
        limit_row = o.loc[t_exec] if t_exec in o.index else None
        if limit_row is None:
            continue
        for s in SYMS:
            d = float(diff.loc[t, s])
            if abs(d) <= 1e-9:
                continue
            side = 1 if d > 0 else -1
            limit_px = float(limit_row[s])
            if not np.isfinite(limit_px):
                continue
            total += 1
            ot, oo, oh, ol = look[s]
            j0 = int(np.searchsorted(ot, np.datetime64(t_exec)))
            # need exact 4h->1m match; if missing, count as missing and taker
            if j0 >= len(ot) or pd.Timestamp(ot[j0]).tz_localize("UTC") != t_exec:
                missing_1m += 1
                px15 = float(oo[min(j0, len(oo) - 1)]) if len(oo) else limit_px
                fill_px = px15 * (1 + 0.0002 * side)
                drag = abs(fill_px / limit_px - 1) * abs(d) if limit_px != 0 else 0.0
                extra.loc[t] += abs(d) * (0.0005 - 0.0002) + drag
                continue
            # minutes 2..15 inclusive: j0+2 .. j0+15
            j1, j2 = j0 + 2, j0 + 16
            wh, wl = oh[j1:j2], ol[j1:j2]
            if limit_filled(side, limit_px, wh, wl):
                maker += 1
            else:
                px15 = float(oo[j0 + 15]) if (j0 + 15) < len(oo) else limit_px
                fill_px = px15 * (1 + 0.0002 * side)
                drag = abs(fill_px / limit_px - 1) * abs(d) if limit_px != 0 else 0.0
                extra.loc[t] += abs(d) * (0.0005 - 0.0002) + drag
    maker_rate = (maker / total) if total else float("nan")
    exec_net_full = net - extra
    hm = (exec_net_full.index >= HIDDEN) & (exec_net_full.index < HEND)
    exec_stats = stats(exec_net_full[hm], model_turn[hm])
    norm_stats = stats(net[hm], model_turn[hm])
    return dict(maker_fills=int(maker), total_orders=int(total),
                maker_rate=round(float(maker_rate), 4) if total else float("nan"),
                missing_1m=int(missing_1m),
                exec_stats=exec_stats, normal_stats=norm_stats,
                exec_net=exec_net_full[hm], extra=extra[hm])


def main():
    global FEATS
    panel = build_base_panel()
    FEATS = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar")]
    v98 = run_v98(panel)
    b = run_v99_books()
    v99 = run_v99_portfolio(b["books"], b["o"], b["ret1"])
    yearly99 = yearly_slices(v99["net"], v99["model_turn"])
    print("v99 yearly:", json.dumps(yearly99, indent=2), flush=True)
    hidden_exec = run_hidden_execution(v99["Wt"], b["o"], v99["net"], v99["model_turn"])
    print("v99 hidden exec:", json.dumps({k: v for k, v in hidden_exec.items()
                                          if k in ("maker_fills", "total_orders", "maker_rate",
                                                   "missing_1m", "exec_stats", "normal_stats")}, indent=2), flush=True)
    result = {
        "anchors_v98_H2": v98[2]["anchors"],
        "yearly_v98_H2_normal": v98[2]["yearly"],
        "hidden_v98_H2_2025_2026_normal": next(y for y in v98[2]["yearly"] if y["anchor"] == "2025-09-24"),
        "anchors_v98_H1": v98[1]["anchors"],
        "yearly_v98_H1_normal": v98[1]["yearly"],
        "hidden_v98_H1_2025_2026_normal": next(y for y in v98[1]["yearly"] if y["anchor"] == "2025-09-24"),
        "model": HGB_PARAMS,
        "recency_weight": "sample_weight = 0.5**(age_years / H); age_years = (cutoff - open_time)/365.25d; H=2 primary, H=1 secondary",
        "cutoffs": {a: str(pd.Timestamp(a, tz="UTC") - pd.Timedelta(hours=4 * EMBARGO_BARS)) for a in ANCHORS},
        "features": FEATS,
        "assets": list(SYMS),
        "data": {
            "usdm_btc": "data/raw/ma_ribbon_20260924",
            "usdm_others": "data/raw/xs_universe_20260924",
            "spot_prefix": "data/raw/spot_majors_20260925/{SYM}_spot_{4h,1d}_2017.parquet open_time < first USD-M bar (SOL none)",
            "carry": "artifacts/research/carry/carry_oos_fee0.0004.parquet (column carry, reindexed to books index, NaN->0)",
            "v96_books_source": "v92_audit/predictions_5asset.csv + v93_v94_audit/predictions_v94.csv recomputed (v96 replication)",
        },
        "execution_v98": {
            "weight": "v92 long-only; raw=s/(vol42*sqrt(2190)); /sum|raw| then *min(1,count/5); every 6th bar ffill",
            "vol_target": "book=sum W_{t-2}*ret1; vol=rolling360(min120)std*sqrt(2190); scale=min(0.20/vol,2) NaN->1",
            "realisation": "W_t*scale_t earns open[t+2]/open[t+1]-1; fee 0.0002; funding 0.00005 long gross",
        },
        "execution_v99_blind_assumption": {
            "books": "books=0.5*W92*s92+0.5*W94ls*s94 (v96 replication, own 20% scales)",
            "book_for_vol": "book_t=0.8*sum books_{t-2}*ret1_t + 0.6*carry_{t-1}; vol=rolling360(min120)std*sqrt(2190); s=min(0.15/vol,2) NaN->1",
            "model_net_forward": "Wt=0.8*s*books earns o[t+2]/o[t+1]-1; cost turn(Wt)*0.0002 + 0.00005*long gross",
            "carry_net_forward": "pos=0.6*s earns carry[t+1]; cost |diff(pos)|*2*0.0004/1.2; first-bar diff filled with |pos|",
            "fills": "model_turn>1e-6 bars (trend-leg only, as v93 leader); carry rescale costs charged but not counted",
            "note": "forward carry convention chosen blind; Part B reconciles with leader timing if different",
        },
        "yearly_v99_normal": yearly99,
        "hidden_v99_2025_2026_normal": next(y for y in yearly99 if y["anchor"] == "2025-09-24"),
        "hidden_v99_1m_execution": {
            **hidden_exec["exec_stats"],
            "maker_fills": hidden_exec["maker_fills"],
            "total_orders": hidden_exec["total_orders"],
            "maker_rate": hidden_exec["maker_rate"],
            "missing_1m": hidden_exec["missing_1m"],
            "rule": "limit at next 4h open; maker iff 1m min2..15 trades strictly through (buy low<limit, sell high>limit); else minute-15 1m open * (1+0.0002*side), taker 0.0005; extra vs normal = 0.0003*|diff| + |fill/limit-1|*|diff|; carry leg unchanged",
        },
        "assumptions": [
            "v98 features/labels/embargo/weights/vol/execution identical to v92 5-asset except HGB sample_weight recency decay; HGB NaN-native.",
            "v99 books reuse audited OOS preds (no retrain); scales recomputed causally per book then v99 15% vol target.",
            "yearly slices [A,A+365d); 2190 bars per year; 10950 total; fills = trend-leg turnover bars.",
        ],
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(result, f, indent=2)
    # equities / predictions
    for Hl in (2, 1):
        d = v98[Hl]
        pd.DataFrame({"t": d["net"].index, "net": d["net"].values,
                      "turnover": d["turn"].values, "scale": d["scale"].values}).to_csv(
            OUT_DIR / f"equity_v98_H{Hl}.csv", index=False)
        d["oos"][["t", "sym", "open", "pred", "y", "vol42", "rib"]].to_csv(
            OUT_DIR / f"predictions_v98_H{Hl}.csv", index=False)
    pd.DataFrame({"t": v99["net"].index, "net": v99["net"].values,
                  "turnover_model": v99["model_turn"].values,
                  "turnover_carry": v99["carry_turn"].values,
                  "scale": v99["scale"].values,
                  "model_net": v99["model_net"].values,
                  "carry_net": v99["carry_net"].values}).to_csv(OUT_DIR / "equity_v99.csv", index=False)
    pd.DataFrame({"t": hidden_exec["exec_net"].index, "net_exec": hidden_exec["exec_net"].values,
                  "extra_cost": hidden_exec["extra"].values}).to_csv(
        OUT_DIR / "equity_v99_hidden_exec.csv", index=False)
    print("saved replication.json", flush=True)


if __name__ == "__main__":
    main()
