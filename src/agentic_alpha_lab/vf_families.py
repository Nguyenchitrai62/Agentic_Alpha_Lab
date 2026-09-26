"""Strategy families for the virtual-forward program. All targets are causal at the decision bar close."""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from agentic_alpha_lab.models.pattern_pipeline import daily_context, join_daily
from agentic_alpha_lab.research_vf import Context


def _daily(ctx: Context) -> pd.DataFrame:
    if "daily_ctx" not in ctx.cache:
        ctx.cache["daily_ctx"] = join_daily(ctx.bars, ctx.daily, daily_context(ctx.daily))
    return ctx.cache["daily_ctx"]


def _ema(ctx: Context, span: int) -> np.ndarray:
    key = ("ema", span)
    if key not in ctx.cache:
        ctx.cache[key] = ctx.bars["close"].ewm(span=span, adjust=False, min_periods=span).mean().to_numpy()
    return ctx.cache[key]


def hold(cond: np.ndarray, allow_entry: np.ndarray, size_at_entry: np.ndarray | None = None) -> np.ndarray:
    """Position 1*size while ``cond`` stays on after an allowed start; 0 otherwise."""
    out = np.zeros(len(cond))
    holding, size = False, 1.0
    for t in range(len(cond)):
        if not cond[t]:
            holding = False
        elif t == 0 or not cond[t - 1]:
            holding = bool(allow_entry[t])
            size = 1.0 if size_at_entry is None else float(size_at_entry[t])
        out[t] = size if holding else 0.0
    return out


def gate_mask(ctx: Context, gate: str, side: int) -> np.ndarray:
    rib = np.nan_to_num(_daily(ctx)["d_ribbon"].to_numpy(), nan=0.0)
    if gate == "none":
        return np.ones(len(rib), bool)
    if gate == "not_against":
        return rib != -side
    if gate == "with":
        return rib == side
    raise ValueError(gate)


def ribbon_cond(ctx: Context, fast: int, slow: int, side: int) -> np.ndarray:
    c = ctx.bars["close"].to_numpy()
    f, s = _ema(ctx, fast), _ema(ctx, slow)
    with np.errstate(invalid="ignore"):
        return ((c > f) & (f > s)) if side > 0 else ((c < f) & (f < s))


# ---- F1 / F2: 4h EMA ribbon trend with daily entry gate
def trend_ribbon(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    tgt = hold(ribbon_cond(ctx, p["fast"], p["slow"], 1), gate_mask(ctx, p["gate"], 1))
    if p.get("shorts"):
        tgt -= hold(ribbon_cond(ctx, p["fast"], p["slow"], -1), gate_mask(ctx, p["short_gate"], -1))
    return tgt


GRID_TREND_LONG = [dict(fast=f, slow=s, gate=g) for f, s, g in itertools.product((10, 20, 50), (100, 200), ("none", "not_against", "with"))]
GRID_TREND_LS = [dict(fast=f, slow=s, gate=g, shorts=True, short_gate=sg)
                 for f, s, g, sg in itertools.product((10, 20, 50), (100, 200), ("not_against", "with"), ("with",))]


# ---- F3: Donchian breakout (turtle-style) with daily gate
def donchian(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    b = ctx.bars
    c = b["close"].to_numpy()
    hi = b["high"].rolling(p["entry"]).max().shift(1).to_numpy()
    lo_exit = b["low"].rolling(p["exit"]).min().shift(1).to_numpy()
    allow = gate_mask(ctx, p["gate"], 1)
    out = np.zeros(len(c))
    holding = False
    for t in range(len(c)):
        if holding and not (c[t] > lo_exit[t]):
            holding = False
        elif not holding and c[t] > hi[t] and allow[t]:
            holding = True
        out[t] = 1.0 if holding else 0.0
    if p.get("shorts"):
        lo = b["low"].rolling(p["entry"]).min().shift(1).to_numpy()
        hi_exit = b["high"].rolling(p["exit"]).max().shift(1).to_numpy()
        allow_s = gate_mask(ctx, "with", -1)
        holding = False
        for t in range(len(c)):
            if holding and not (c[t] < hi_exit[t]):
                holding = False
            elif not holding and out[t] == 0 and c[t] < lo[t] and allow_s[t]:
                holding = True
            if holding and out[t] == 0:
                out[t] = -1.0
            elif holding:
                holding = False
    return out


GRID_DONCHIAN = [dict(entry=e, exit=x, gate=g) for e, x, g in itertools.product((20, 55, 120), (10, 20, 55), ("none", "not_against")) if x < e]
GRID_DONCHIAN_LS = [dict(d, shorts=True) for d in GRID_DONCHIAN]


# ---- F4: multi-timeframe trend ensemble (fractional position)
def ensemble(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    d = _daily(ctx)
    c = ctx.bars["close"].to_numpy()
    votes = []
    for fast, slow in ((20, 200), (50, 200), (10, 100)):
        f, s = _ema(ctx, fast), _ema(ctx, slow)
        with np.errstate(invalid="ignore"):
            v = np.where((c > f) & (f > s), 1.0, np.where((c < f) & (f < s), -1.0, 0.0))
        votes.append(v)
    votes.append(np.nan_to_num(d["d_ribbon"].to_numpy()))
    votes.append(np.sign(np.nan_to_num(d["d_sma50_200"].to_numpy())))
    m = np.mean(votes, axis=0)
    if not p.get("shorts"):
        m = np.clip(m, 0, None)
    # quantize to limit churn
    q = p["step"]
    return np.round(m / q) * q


GRID_ENSEMBLE = [dict(step=s, shorts=sh) for s, sh in itertools.product((0.2, 0.5, 1.0), (False, True))]

FAMILIES = {
    "trend_long": (trend_ribbon, GRID_TREND_LONG),
    "trend_long_short": (trend_ribbon, GRID_TREND_LS),
    "donchian_long": (donchian, GRID_DONCHIAN),
    "donchian_long_short": (donchian, GRID_DONCHIAN_LS),
    "ensemble": (ensemble, GRID_ENSEMBLE),
}


# ---- F5: two-book combination (trend ribbon long + Donchian long/short)
def combo(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    a = trend_ribbon(ctx, dict(fast=p["fast"], slow=200, gate="not_against"))
    b = donchian(ctx, dict(entry=p["entry"], exit=p["exit"], gate=p["gate"], shorts=True))
    return p["w"] * a + (1 - p["w"]) * b


GRID_COMBO = [dict(fast=f, entry=e, exit=x, gate=g, w=w)
              for f, e, x, g, w in itertools.product((20, 50), (55, 120), (10, 20), ("none", "not_against"), (0.5,))]


# ---- F6: vol-managed trend (continuous scale, quantized to limit churn)
def vol_managed(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    base = trend_ribbon(ctx, dict(fast=p["fast"], slow=200, gate="not_against"))
    r = np.log(ctx.bars["close"]).diff()
    per_year = {"4h": 6 * 365, "1d": 365, "1h": 24 * 365}[ctx.tf]
    vol = (r.rolling(p["lookback"]).std() * np.sqrt(per_year)).to_numpy()
    scale = np.clip(p["target_vol"] / vol, 0, 2.0)
    scale = np.floor(np.nan_to_num(scale, nan=0.0) / 0.25) * 0.25
    return base * scale


GRID_VOLMAN = [dict(fast=f, lookback=lb, target_vol=tv) for f, lb, tv in itertools.product((20, 50), (42, 180), (0.4, 0.6))]

FAMILIES.update({"combo": (combo, GRID_COMBO), "vol_managed": (vol_managed, GRID_VOLMAN)})


# ---- F7: multi-book portfolio; the subset of books is selected on training data
def _book(ctx: Context, name: str) -> np.ndarray:
    key = ("book", name)
    if key not in ctx.cache:
        if name == "trend":
            v = trend_ribbon(ctx, dict(fast=20, slow=200, gate="not_against"))
        elif name == "donchian_ls":
            v = donchian(ctx, dict(entry=55, exit=10, gate="none", shorts=True))
        elif name == "daily_ribbon_ls":
            v = np.nan_to_num(_daily(ctx)["d_ribbon"].to_numpy())
        elif name == "daily_ribbon_long":
            v = np.clip(np.nan_to_num(_daily(ctx)["d_ribbon"].to_numpy()), 0, None)
        elif name == "donchian_slow_long":
            v = donchian(ctx, dict(entry=120, exit=20, gate="not_against"))
        else:
            raise ValueError(name)
        ctx.cache[key] = v
    return ctx.cache[key]


BOOKS = ("trend", "donchian_ls", "daily_ribbon_ls", "daily_ribbon_long", "donchian_slow_long")


def multibook(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    return np.mean([_book(ctx, b) for b in p["books"]], axis=0)


GRID_MULTIBOOK = [dict(books=c) for r in (2, 3, 4) for c in itertools.combinations(BOOKS, r)
                  if not ("daily_ribbon_ls" in c and "daily_ribbon_long" in c)]
FAMILIES["multibook"] = (multibook, GRID_MULTIBOOK)


# ---- F8: ML forward-return model (walk-forward inside training, frozen fit for the hidden year)
def _ml_matrix(ctx: Context) -> np.ndarray:
    if "ml_x" not in ctx.cache:
        from agentic_alpha_lab.models.pattern_pipeline import build_matrix
        x = build_matrix(ctx.bars, ctx.daily, ctx.funding, ("cdl", "chp", "ind"))
        ctx.cache["ml_x"] = x.to_numpy(np.float32)
    return ctx.cache["ml_x"]


def _ml_pred(ctx: Context, horizon: int, fit_end: int) -> np.ndarray:
    key = ("ml_pred", horizon, fit_end)
    if key in ctx.cache:
        return ctx.cache[key]
    from sklearn.ensemble import HistGradientBoostingRegressor
    x = _ml_matrix(ctx)
    c = ctx.bars["close"].to_numpy()
    o = ctx.bars["open"].to_numpy()
    n = len(c)
    fwd = np.full(n, np.nan)
    fwd[: n - 1 - horizon] = np.log(o[1 + horizon : n] / o[1 : n - horizon])
    vol = pd.Series(np.log(c)).diff().rolling(180).std().to_numpy() * np.sqrt(horizon)
    y = fwd / vol
    realized = np.arange(n) + 1 + horizon
    pred = np.full(n, np.nan)
    refit = 1080  # ~180 days of 4h bars
    first = int(np.flatnonzero(ctx.bars["open_time"] >= pd.Timestamp("2021-01-01", tz="UTC"))[0])
    starts = list(range(first, fit_end, refit)) + [fit_end]
    for i, r in enumerate(starts):
        stop = starts[i + 1] if i + 1 < len(starts) else n
        tr = (realized + horizon < r) & np.isfinite(y)
        m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=300, min_samples_leaf=200, l2_regularization=1.0, random_state=0)
        m.fit(x[tr], np.clip(y[tr], -3, 3))
        pred[r:stop] = m.predict(x[r:stop])
    ctx.cache[key] = pred
    return pred


def ml_book(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    pred = _ml_pred(ctx, p["horizon"], fit_end)
    trend = _book(ctx, "trend")
    if p["mode"] == "overlay":  # hold the trend book only while the model is not negative
        return trend * (np.nan_to_num(pred, nan=0.0) > 0)
    # standalone: long/short on prediction sign beyond a dead band, quantized
    s = np.where(pred > p["band"], 1.0, np.where(pred < -p["band"], -1.0, 0.0))
    s = np.nan_to_num(s)
    if p["mode"] == "blend":
        return 0.5 * trend + 0.5 * s
    return s


GRID_ML = [dict(horizon=h, mode=m, band=b) for h in (12, 42) for m, b in (("overlay", 0.0), ("standalone", 0.1), ("standalone", 0.3), ("blend", 0.1), ("blend", 0.3))]
FAMILIES["ml"] = (ml_book, GRID_ML)


# ---- F9: alt-breadth overlays (W6 events) on the trend / combo books
def _event_hold(ev: np.ndarray, horizon: int) -> np.ndarray:
    """Signed exposure for ``horizon`` bars starting at the event decision bar."""
    out = np.zeros(len(ev))
    for t in np.flatnonzero(ev != 0):
        out[t : t + horizon] = ev[t]
    return out


def _breadth_events(ctx: Context) -> pd.DataFrame:
    if "brd_ev" not in ctx.cache:
        from agentic_alpha_lab.patterns import breadth
        ctx.cache["brd_ev"] = breadth.events(ctx.bars)
    return ctx.cache["brd_ev"]


def breadth_overlay(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    ev = _breadth_events(ctx)
    base = _book(ctx, "trend") if p["base"] == "trend" else combo(ctx, dict(fast=20, entry=55, exit=10, gate="none", w=0.5))
    out = base.copy()
    if p["crowd"] != "off":
        crowd = _event_hold(ev["brd_ev_fund_crowd"].to_numpy(), p["h"]) < 0
        out = np.where(crowd, 0.0 if p["crowd"] == "flat" else -1.0, out)
    if p["div"]:
        follow = _event_hold(-ev["brd_ev_divergence"].to_numpy(), p["h"]) > 0  # sign flipped: continuation
        out = np.where(follow & (out == 0), 1.0, out)
    return out


GRID_BREADTH = [dict(base=b, crowd=c, div=d, h=h) for b in ("trend", "combo") for c in ("off", "flat", "short") for d in (False, True) for h in (3, 6)
                if not (c == "off" and not d)]
FAMILIES["breadth"] = (breadth_overlay, GRID_BREADTH)


# ---- F10: trend ribbon with a chandelier (ATR trailing) exit, evaluated on closes
def trend_trail(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    from agentic_alpha_lab.backtest.bracket import atr
    c = ctx.bars["close"].to_numpy()
    a = atr(ctx.bars)
    cond = ribbon_cond(ctx, p["fast"], 200, 1)
    allow = gate_mask(ctx, "not_against", 1)
    out = np.zeros(len(c))
    holding, peak, blocked = False, 0.0, False
    for t in range(len(c)):
        if not cond[t]:
            holding, blocked = False, False
        elif not holding and not blocked and (t == 0 or not cond[t - 1] or p["reenter"]) and allow[t]:
            holding, peak = True, c[t]
        if holding:
            peak = max(peak, c[t])
            if c[t] < peak - p["mult"] * a[t]:
                holding, blocked = False, not p["reenter"]
        out[t] = 1.0 if holding else 0.0
    return out


GRID_TRAIL = [dict(fast=f, mult=m, reenter=r) for f in (20, 50) for m in (2.0, 3.0, 5.0) for r in (False, True)]
FAMILIES["trend_trail"] = (trend_trail, GRID_TRAIL)


# ---- F11: pullback entries inside an established trend; F12: funding-crowding filter
def trend_pullback(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    b = ctx.bars
    c, lo = b["close"].to_numpy(), b["low"].to_numpy()
    f = _ema(ctx, p["fast"])
    cond = ribbon_cond(ctx, p["fast"], 200, 1)
    allow = gate_mask(ctx, p["gate"], 1)
    touch = lo <= f * (1 + p["tol"])
    out = np.zeros(len(c))
    holding = False
    for t in range(len(c)):
        if not cond[t]:
            holding = False
        elif not holding and touch[t] and c[t] > f[t] and allow[t]:
            holding = True
        out[t] = 1.0 if holding else 0.0
    return out


GRID_PULLBACK = [dict(fast=f, tol=tol, gate=g) for f in (20, 50) for tol in (0.0, 0.005, 0.01) for g in ("not_against", "with")]


def _funding_z(ctx: Context, days: int = 30) -> np.ndarray:
    key = ("fund_z", days)
    if key not in ctx.cache:
        f = ctx.funding
        s = f.set_index("fundingTime")["fundingRate"]
        m7 = s.rolling(21, min_periods=21).mean()
        z = (m7 - m7.rolling(days * 3 * 6, min_periods=90).mean()) / m7.rolling(days * 3 * 6, min_periods=90).std()
        left = pd.DataFrame({"t": ctx.bars["close_time"].to_numpy()})
        right = pd.DataFrame({"t": z.index.to_numpy(), "z": z.to_numpy()})
        ctx.cache[key] = pd.merge_asof(left, right, on="t", direction="backward")["z"].to_numpy()
    return ctx.cache[key]


def trend_funding(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    z = np.nan_to_num(_funding_z(ctx), nan=0.0)
    cond = ribbon_cond(ctx, p["fast"], 200, 1)
    allow = gate_mask(ctx, "not_against", 1) & (z < p["zmax"])
    base = hold(cond, allow)
    if p["exit_on_crowd"]:
        base = np.where(z >= p["zmax"], 0.0, base)
    return base


GRID_FUNDING = [dict(fast=f, zmax=zm, exit_on_crowd=e) for f in (20, 50) for zm in (1.0, 1.5, 2.0, 99.0) for e in (False, True) if not (zm == 99.0 and e)]
FAMILIES.update({"trend_pullback": (trend_pullback, GRID_PULLBACK), "trend_funding": (trend_funding, GRID_FUNDING)})


# ---- F13: ribbon with hysteresis band around the fast EMA (fewer whipsaws), optional Donchian L/S sleeve
def trend_hyst(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    c = ctx.bars["close"].to_numpy()
    f, s = _ema(ctx, p["fast"]), _ema(ctx, 200)
    allow = gate_mask(ctx, "not_against", 1)
    d = p["band"]
    out = np.zeros(len(c))
    holding = False
    for t in range(len(c)):
        if holding and (c[t] < f[t] * (1 - d) or not f[t] > s[t]):
            holding = False
        elif not holding and c[t] > f[t] * (1 + d) and f[t] > s[t] and allow[t]:
            holding = True
        out[t] = 1.0 if holding else 0.0
    if p.get("sleeve"):
        out = 0.5 * out + 0.5 * donchian(ctx, dict(entry=55, exit=10, gate="none", shorts=True))
    return out


GRID_HYST = [dict(fast=f, band=b, sleeve=sl) for f in (20, 50) for b in (0.0, 0.005, 0.01, 0.02, 0.03) for sl in (False, True)]
FAMILIES["trend_hyst"] = (trend_hyst, GRID_HYST)


# ---- F14: rotate between books by trailing performance (causal: uses book returns realized so far)
def rotation(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    o = ctx.bars["open"].to_numpy()
    r = np.zeros(len(o))
    r[1:-1] = o[2:] / o[1:-1] - 1  # return earned over bar t by a position decided at t-1 (open t -> open t+1)
    names = ("trend", "donchian_ls", "daily_ribbon_long", "donchian_slow_long")
    pos = np.vstack([_book(ctx, n) for n in names])
    book_ret = np.zeros_like(pos)
    book_ret[:, 1:] = pos[:, :-1] * r[None, :-1]  # realized by the close of bar t... uses open[t+1]
    # performance known at decision t must exclude open[t+1]: shift one more bar
    known = np.zeros_like(book_ret)
    known[:, 1:] = book_ret[:, :-1]
    perf = pd.DataFrame(known.T).rolling(p["lookback"], min_periods=p["lookback"]).sum().to_numpy().T
    out = np.zeros(len(o))
    chosen = None
    for t in range(len(o)):
        if t % 42 == 0 and np.isfinite(perf[:, t]).all():
            order = np.argsort(-perf[:, t])[: p["top"]]
            chosen = order if perf[order[0], t] > 0 or not p["cash_if_negative"] else np.array([], dtype=int)
        if chosen is not None and len(chosen):
            out[t] = pos[chosen, t].mean()
    return out


GRID_ROTATION = [dict(lookback=lb, top=k, cash_if_negative=c) for lb in (180, 540, 1080) for k in (1, 2) for c in (False, True)]
FAMILIES["rotation"] = (rotation, GRID_ROTATION)


# ---- F15: OI-surge continuation (W5 event), fixed holding period, optional daily trend gate
def oi_cont(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    if "pos_ev" not in ctx.cache:
        from agentic_alpha_lab.patterns import positioning
        ctx.cache["pos_ev"] = positioning.events(ctx.bars)
    ev = ctx.cache["pos_ev"]["pos_ev_oi_cont"].to_numpy().astype(float)
    if p["gate"] != "none":
        rib = np.nan_to_num(_daily(ctx)["d_ribbon"].to_numpy())
        ev = np.where((ev > 0) & (rib == -1), 0, ev)
        ev = np.where((ev < 0) & (rib != -1 if p["gate"] == "with" else rib == 1), 0, ev)
    out = _event_hold(ev, p["h"])
    if p.get("long_only"):
        out = np.clip(out, 0, None)
    return out


GRID_OI = [dict(h=h, gate=g, long_only=lo) for h in (6, 12, 24) for g in ("none", "not_against", "with") for lo in (False, True)]
FAMILIES["oi_cont"] = (oi_cont, GRID_OI)


# ---- F16: macro risk-on gate (W7, leader-fixed calendar alignment) on the trend and combo books
def trend_macro(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    if "mac" not in ctx.cache:
        from agentic_alpha_lab.patterns import macro
        ctx.cache["mac"] = macro.compute(ctx.bars)
    score = np.nan_to_num(ctx.cache["mac"]["mac_risk_on_score"].to_numpy(), nan=4.0)
    cond = ribbon_cond(ctx, p["fast"], 200, 1)
    allow = gate_mask(ctx, "not_against", 1) & (score >= p["min_score"])
    base = hold(cond, allow)
    if p["hold_rule"] == "exit":
        base = np.where(score >= p["min_score"], base, 0.0)
    if p.get("sleeve"):
        base = 0.5 * base + 0.5 * donchian(ctx, dict(entry=55, exit=10, gate="none", shorts=True))
    return base


GRID_MACRO = [dict(fast=f, min_score=s, hold_rule=h, sleeve=sl) for f in (20, 50) for s in (0, 2, 3) for h in ("entry", "exit") for sl in (False, True)
              if not (s == 0 and h == "exit")]
FAMILIES["trend_macro"] = (trend_macro, GRID_MACRO)


# ---- F17: learned market-regime gate (Gaussian mixture on daily state, fit only before fit_end)
def gmm_gate(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    from sklearn.mixture import GaussianMixture
    d = _daily(ctx)
    feats = np.column_stack([d["d_ret30"].to_numpy(), d["d_vol30"].to_numpy(), d["d_dist_sma200"].to_numpy(), d["d_ret7"].to_numpy()])
    ok = np.isfinite(feats).all(axis=1)
    fe = len(feats) if fit_end is None else fit_end
    train = ok & (np.arange(len(feats)) < fe)
    g = GaussianMixture(p["k"], covariance_type="full", random_state=0).fit(feats[train])
    # bull state = component with the highest mean 30d return; label chosen from training data only
    bull = int(np.argmax(g.means_[:, 0]))
    prob = np.zeros(len(feats))
    prob[ok] = g.predict_proba(feats[ok])[:, bull]
    allow = prob > p["th"]
    base = hold(ribbon_cond(ctx, 20, 200, 1), allow)
    if p.get("sleeve"):
        base = 0.5 * base + 0.5 * donchian(ctx, dict(entry=55, exit=10, gate="none", shorts=True))
    return base


GRID_GMM = [dict(k=k, th=th, sleeve=sl) for k in (2, 3) for th in (0.3, 0.5, 0.7) for sl in (False, True)]
FAMILIES["gmm_gate"] = (gmm_gate, GRID_GMM)


# ---- F18: stablecoin-liquidity gate (W10 on-chain) on the trend and combo books
def liquidity_gate(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    if "onc" not in ctx.cache:
        from agentic_alpha_lab.patterns import onchain
        ctx.cache["onc"] = onchain.compute(ctx.bars)
    g = ctx.cache["onc"][p["feature"]].to_numpy()
    allow = gate_mask(ctx, "not_against", 1) & (np.nan_to_num(g, nan=1.0) > p["min"])
    base = hold(ribbon_cond(ctx, 20, 200, 1), allow)
    if p["exit"]:
        base = np.where(np.nan_to_num(g, nan=1.0) > p["min"], base, 0.0)
    if p["sleeve"]:
        base = 0.5 * base + 0.5 * donchian(ctx, dict(entry=55, exit=10, gate="none", shorts=True))
    return base


GRID_LIQ = [dict(feature=f, min=m, exit=e, sleeve=sl) for f in ("onc_stable_g30", "onc_stable_g90") for m in (-0.02, 0.0, 0.02)
            for e in (False, True) for sl in (False, True)]
FAMILIES["liquidity_gate"] = (liquidity_gate, GRID_LIQ)


# ---- F19: multi-timeframe MA-ribbon model (ma-sr program, user suggestion 2026-09-24)
def _mtf_x(ctx: Context) -> np.ndarray:
    if "mtf_x" not in ctx.cache:
        from agentic_alpha_lab.models.mtf import mtf_matrix
        from agentic_alpha_lab.patterns.common import load_bars
        higher = {"4h": load_bars("4h", include_opened_year=True), "1d": ctx.daily}
        if ctx.tf == "15m":
            higher = {"1h": load_bars("1h", include_opened_year=True), **higher}
        higher = {k: v[v["close_time"] <= ctx.bars["close_time"].iloc[-1]].reset_index(drop=True) for k, v in higher.items()}
        ctx.cache["mtf_x"] = mtf_matrix(ctx.bars, higher, ctx.tf).to_numpy(np.float32)
    return ctx.cache["mtf_x"]


def _mtf_pred(ctx: Context, horizon: int, fit_end: int) -> np.ndarray:
    key = ("mtf_pred", horizon, fit_end)
    if key in ctx.cache:
        return ctx.cache[key]
    from sklearn.ensemble import HistGradientBoostingRegressor
    x = _mtf_x(ctx)
    o, c = ctx.bars["open"].to_numpy(), ctx.bars["close"].to_numpy()
    n = len(c)
    fwd = np.full(n, np.nan)
    fwd[: n - 1 - horizon] = np.log(o[1 + horizon:] / o[1: n - horizon])
    vol = pd.Series(np.log(c)).diff().rolling(24 * 30).std().to_numpy() * np.sqrt(horizon)
    y = np.clip(fwd / vol, -4, 4)
    per_day = {"15m": 96, "1h": 24, "4h": 6}[ctx.tf]
    refit = per_day * 180
    first = int(np.flatnonzero(ctx.bars["open_time"] >= pd.Timestamp("2021-01-01", tz="UTC"))[0])
    starts = list(range(first, fit_end, refit)) + [fit_end]
    realized = np.arange(n) + 1 + horizon
    pred = np.full(n, np.nan)
    for i, r in enumerate(starts):
        stop = starts[i + 1] if i + 1 < len(starts) else n
        tr = (realized + horizon < r) & np.isfinite(y)
        m = HistGradientBoostingRegressor(max_depth=5, learning_rate=0.05, max_iter=300, min_samples_leaf=400, l2_regularization=1.0, random_state=0)
        m.fit(x[tr], y[tr])
        pred[r:stop] = m.predict(x[r:stop])
        ctx.cache[("mtf_train_q", horizon, r)] = np.quantile(m.predict(x[tr][-per_day * 365:]), [0.2, 0.8])
    ctx.cache[key] = pred
    return pred


def mtf_ml(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    pred = np.nan_to_num(_mtf_pred(ctx, p["h"], fit_end), nan=0.0)
    long_ = pred > p["band"]
    short = pred < -p["band"]
    if p["gate"] == "trend":  # trade only with the daily ribbon
        rib = np.nan_to_num(_daily(ctx)["d_ribbon"].to_numpy())
        long_ &= rib != -1
        short &= rib == -1
    sig = np.where(long_, 1.0, np.where(short, -1.0 if p["shorts"] else 0.0, 0.0))
    if p["hold"] > 1:  # keep each signal for at least `hold` bars to cut churn
        s = pd.Series(np.where(sig != 0, sig, np.nan)).ffill(limit=p["hold"] - 1).fillna(0.0).to_numpy()
        sig = s
    return sig


GRID_MTF = [dict(h=h, band=b, gate=g, shorts=sh, hold=hd) for h in (4, 12, 24) for b in (0.1, 0.25, 0.5) for g in ("none", "trend")
            for sh in (False, True) for hd in (1, 4)]
FAMILIES["mtf_ml"] = (mtf_ml, GRID_MTF)


# ---- F20: volume-confirmed impulse continuation (W16: no-wick flush/squeeze bars continue)
def impulse(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    if "cap_ev" not in ctx.cache:
        from agentic_alpha_lab.patterns import capitulation
        ctx.cache["cap_ev"] = capitulation.events(ctx.bars)
    ev = ctx.cache["cap_ev"][p["event"]].to_numpy().astype(float)
    if p["gate"] == "not_against":
        rib = np.nan_to_num(_daily(ctx)["d_ribbon"].to_numpy())
        ev = np.where((ev > 0) & (rib == -1), 0.0, np.where((ev < 0) & (rib == 1), 0.0, ev))
    if p.get("long_only"):
        ev = np.clip(ev, 0, None)
    return _event_hold(ev, p["h"])


GRID_IMPULSE = [dict(event=e, h=h, gate=g, long_only=lo) for e in ("cap_ev_cont", "cap_ev_up_cont") for h in (4, 12, 24)
                for g in ("none", "not_against") for lo in (False, True) if not (e == "cap_ev_up_cont" and not lo)]
FAMILIES["impulse"] = (impulse, GRID_IMPULSE)


# ---- F21: regime-scaled breadth/combo (size by the user's daily SMA50/SMA200 ribbon state)
def regime_scaled(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    base = breadth_overlay(ctx, dict(base="combo", crowd="short", div=True, h=3))
    rib = np.nan_to_num(_daily(ctx)["d_ribbon"].to_numpy())
    scale = np.where(rib == 1, p["bull"], np.where(rib == 0, p["neutral"], p["bear"]))
    return base * scale


GRID_REGIME = [dict(bull=b, neutral=n, bear=r) for b in (1.0, 1.5, 2.0) for n in (0.0, 0.5, 1.0) for r in (0.5, 1.0)]
FAMILIES["regime_scaled"] = (regime_scaled, GRID_REGIME)


# ---- F22: pyramiding trend (Turtle-style adds only while in profit), daily-regime gated
def pyramid(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    from agentic_alpha_lab.backtest.bracket import atr as _atr
    b = ctx.bars
    c = b["close"].to_numpy()
    a = _atr(b)
    if p["entry"] == "ribbon":
        cond = ribbon_cond(ctx, 20, 200, 1)
        start = cond & ~np.concatenate([[False], cond[:-1]])
    else:
        hi = b["high"].rolling(p["entry"]).max().shift(1).to_numpy()
        start = c > hi
    rib = np.nan_to_num(_daily(ctx)["d_ribbon"].to_numpy())
    rc = ribbon_cond(ctx, 20, 200, 1)
    out = np.zeros(len(c))
    units, last_add, peak = 0, 0.0, 0.0
    for t in range(len(c)):
        if units > 0:
            peak = max(peak, c[t])
            stop_hit = c[t] < peak - p["trail"] * a[t]
            regime_off = rib[t] == -1
            if stop_hit or regime_off or (p["entry"] == "ribbon" and not rc[t]):
                units = 0
            elif units < p["max_units"] and c[t] >= last_add + p["step"] * a[t]:
                units += 1
                last_add = c[t]
        elif start[t] and rib[t] != -1 and np.isfinite(a[t]):
            units, last_add, peak = 1, c[t], c[t]
        out[t] = units / p["max_units"] * p["gross"]
    return out


GRID_PYRAMID = [dict(entry=e, max_units=u, step=s, trail=tr, gross=1.0)
                for e in ("ribbon", 55, 20) for u in (1, 2, 4) for s in (0.5, 1.0) for tr in (2.0, 3.0, 5.0) if not (u == 1 and s == 1.0)]
FAMILIES["pyramid"] = (pyramid, GRID_PYRAMID)


# ---- F23: multi-horizon time-series momentum with volatility targeting (CTA style)
def tsmom(ctx: Context, p: dict, fit_end: int | None = None) -> np.ndarray:
    c = ctx.bars["close"]
    per_day = {"4h": 6, "1h": 24, "1d": 1}[ctx.tf]
    lc = np.log(c)
    sig = sum(np.sign(lc - lc.shift(h * per_day)) for h in p["horizons"]) / len(p["horizons"])
    if not p["shorts"]:
        sig = sig.clip(lower=0)
    if p["gate"]:
        rib = pd.Series(np.nan_to_num(_daily(ctx)["d_ribbon"].to_numpy()), index=c.index)
        sig = sig.where(~((sig > 0) & (rib == -1)), 0.0).where(~((sig < 0) & (rib == 1)), 0.0)
    vol = lc.diff().rolling(per_day * 30).std() * np.sqrt(per_day * 365)
    lev = (p["target_vol"] / vol).clip(upper=2.0)
    pos = (sig * lev).fillna(0.0)
    step = p["step"]
    return (np.round(pos / step) * step).to_numpy()


GRID_TSMOM = [dict(horizons=hz, shorts=sh, gate=g, target_vol=tv, step=0.25)
              for hz in ((7, 30, 90), (14, 60, 180), (30, 90), (7, 30)) for sh in (False, True) for g in (False, True) for tv in (0.3, 0.5)]
FAMILIES["tsmom"] = (tsmom, GRID_TSMOM)

GRID_TSMOM_FAST = [dict(horizons=hz, shorts=sh, gate=g, target_vol=tv, step=0.25)
                   for hz in ((1, 3), (1, 3, 7), (2, 7), (3, 7, 14)) for sh in (False, True) for g in (False, True) for tv in (0.3, 0.5)]
FAMILIES["tsmom_fast"] = (tsmom, GRID_TSMOM_FAST)
