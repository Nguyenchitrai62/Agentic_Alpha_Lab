"""engine_user: evaluation engine matching the user's real trading (AGENTS.md rules of 2026-09-27).

Every position is traded like the user trades on Bybit (majors only, account < 10k USDT):
- Book orders: at each 4h decision the target weight per asset (v154 books, vol target, governor) is compared with the
  drifted current position; the change is sent as a LIMIT order 10 bps better than the minute-0 price, live in
  minutes 2..59 of the holding bar, filled at the limit on a 1m trade-through (maker 0.0002); unfilled orders expire.
- Every book position carries a stop-loss (market, taker 0.00055) and a take-profit (limit, maker 0.0002):
  SL = entry * (1 -/+ m * sigma_d), TP = entry * (1 +/- 2 m * sigma_d), entry = average entry price of the open
  position, sigma_d = daily sigma = std of 4h open-to-open returns over 360 bars (known at the decision) * sqrt(6).
  Levels are reset at each decision from the current entry. Checked on every 1m bar: stop if low <= SL (long) /
  high >= SL (short), filled at SL or at the minute open if it gapped through; take-profit on a strict trade-through
  at TP; both in one minute -> stop first. After a stop or take-profit the asset is flat until the next decision.
- Dip sleeve (v183 rules): ladder bids 2.5/3/3.5/4 sigma_4h below the 4h open (minutes 16..238, maker on
  trade-through), TP limit at L(1 + sigma_4h) (maker), SL market at L(1 - M_S * sigma_4h) (taker), else market exit
  at the next 4h open (taker); open-notional budget 1/6 equity; rung notional s*g*0.25/4/1.657.
- Funding (adverse, user rule): a long position held at a settlement (00/08/16 UTC) pays 0.0001 of its notional;
  shorts pay/receive nothing. No carry sleeve.
- Positions are tracked in quantities (weights drift with prices); equity compounds per bar; 1m mark-to-market equity
  for the drawdown (gate DD = max(4h close, 1m-marked)); Binance/Bybit minimum notional at 10k USDT; cross-margin
  liquidation check (maintenance 1% of gross notional).
- Reports per anchor year and the user gate: 5-year mean, most recent year, no losing year, DD; the selection metric
  is the mean over the FIRST FOUR anchors only (the most recent year is reported but never used to choose).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
MAKER, TAKER = 0.0002, 0.00055
D_LIMIT = 0.001
FUND_LONG = 0.0001
N_MAX = 0.05 / 0.30
MMR = 0.01
ACCOUNT = 10_000.0
MIN_NOTIONAL = {"BTCUSDT": 100.0, "ETHUSDT": 20.0}
RUNGS = (2.5, 3.0, 3.5, 4.0)
SIZE, S_REF = 0.25, 1.657


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


er = _load("engine_real_u", HERE.parent / "engine_real/engine_real.py")
v172 = _load("v172_u", HERE.parent / "v172/v172_sleeve_realistic.py")
v99, v110, PD = er.v99, er.v110, er.PD
ANCHORS = er.v92.ANCHORS


def prepare(books, opens):
    """Aligned arrays: 1m cube for the holding bar of every decision, 4h sigma, settlement flags."""
    idx, cols = books.index, list(books.columns)
    A = v172.cube_ohlc(idx, cols)  # cube row i = holding bar T = idx[i] + 4h
    o = opens.reindex(idx)[cols]
    sig4 = o.pct_change().rolling(60 * PD, min_periods=20 * PD).std().to_numpy()
    o1, o2 = o.shift(-1).to_numpy(), o.shift(-2).to_numpy()
    exit_hour = (idx + pd.Timedelta(hours=8)).hour
    settle_at_end = np.isin(exit_hour, (0, 8, 16))  # T + 4h is a funding settlement
    n, na = A["open"].shape[0], len(cols)
    h_open = A["open"][:, [0, 60, 120, 180], :].astype(float).reshape(n * 4, na)
    sig_h = pd.DataFrame(h_open).pct_change().rolling(1440, min_periods=480).std().to_numpy().reshape(n, 4, na)
    sig1h = np.full((n, na), np.nan)
    sig1h[1:] = sig_h[:-1, 3, :]  # hourly sigma known before the holding bar starts
    return dict(idx=idx, cols=cols, O=A["open"], H=A["high"], L=A["low"], C=A["close"], sig4=sig4, o1=o1, o2=o2,
                settle=settle_at_end, sig1h=sig1h)


def simulate(books, opens, prep, m_sl=3.0, m_sleeve_sl=2.0, sleeve=True, target=0.25, cap=2.0, d_limit=D_LIMIT, win_end=60, sleeve_risk_budget=None, gap=0.02, m_sleeve_tp=1.0, rung_scale_fixed=None, size_mult=1.0, rungs=RUNGS, m_tp=None, hourly=False, align=None, events=None, bars=None, exec_policy=None, fixed_levels=False, attrib=None):
    # events: optional list; when given, every fill / stop / take-profit / sleeve rung is appended as a dict (no effect on results)
    # exec_policy: optional callable (i, a, dw, w_a, tgt_a, sig4_ia) -> ("limit", offset[, weight]) | ("market", 0[, weight]) | ("skip", 0)
    #   deciding how (and, with the optional weight, to which weight instead of the target)
    #   the book change of asset a at decision i is executed; None = limit d_limit (the audited default, unchanged results).
    #   market = taker fill at the minute-0 open of the holding bar; skip = no order this bar (position kept).
    # fixed_levels: SL/TP use sigma_d of the bar the position was opened (or flipped) instead of the current bar's sigma,
    #   so the levels only move when the average entry moves (never, when the policy sends no adds).
    # attrib: optional list; per live bar appends (t, per-asset book PnL array, sleeve PnL), fractions of bar-start equity.
    idx, cols = prep["idx"], prep["cols"]
    O, H, L, C = prep["O"], prep["H"], prep["L"], prep["C"]
    sig4, o1, o2, settle = prep["sig4"], prep["o1"], prep["o2"], prep["settle"]
    B = books.to_numpy()
    na, n = len(cols), len(idx)
    o = opens.reindex(idx)[cols]
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy()
    s = np.where(np.isnan(vol), 1.0, np.minimum(target / np.where(np.isnan(vol), 1.0, vol), cap))
    live = np.asarray((idx >= v110.START) & (idx < v110.END))
    mins = np.array([MIN_NOTIONAL.get(c, 5.0) for c in cols])
    net, g, eq, eq_min, eq_max = np.zeros(n), np.ones(n), np.ones(n), np.ones(n), np.ones(n)
    w = np.zeros(na)            # position weights at bar start (fraction of equity, drifted)
    entry = np.full(na, np.nan)  # average entry price per asset
    entry_sd = np.full(na, np.nan)  # sigma_d at the opening of the current position (fixed_levels)
    stats = dict(fills=0, unfilled=0, stops=0, tps=0, rungs=0, rung_stops=0, rung_tps=0, liq=0, fees=0.0, funding=0.0, gross_sum=0.0, gross_max=0.0, bars=0)
    if exec_policy is not None:
        stats.update(market=0, skipped=0, limit_offset_sum=0.0)
    minute = np.arange(240)
    for i in range(n):
        if i >= 2:
            j = i - 2
            peak = eq[max(0, j - 90 * PD + 1): j + 1].max()
            g[i] = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0.0, 1.0))
        prev_eq = eq[i - 1] if i else 1.0
        if not live[i] or not np.all(np.isfinite(o1[i])) or not np.all(np.isfinite(o2[i])):
            eq[i] = prev_eq
            eq_min[i] = prev_eq
            eq_max[i] = prev_eq
            continue
        tgt = v99.W_BOOKS * s[i] * B[i] * g[i]
        sd = sig4[i] * np.sqrt(6)
        cash = 0.0                       # relative to equity at bar start (=1)
        q = w / o1[i]                    # quantities (equity units per price unit)
        start_val = float((q * o1[i]).sum())
        path = np.zeros(240)             # mark-to-market PnL path (fraction of start equity)
        asset_pnl = np.zeros(na)
        for a in range(na):
            Oa, Ha, La, Ca = (X[i, :, a].astype(float) for X in (O, H, L, C))
            if not np.isfinite(Oa[0]):
                continue
            qa, ea = q[a], entry[a]
            dw = tgt[a] - w[a]
            fill_min, fill_px, fill_fee, fill_type = 999, np.nan, MAKER, "limit"
            if abs(dw) * prev_eq * ACCOUNT >= mins[a] or (tgt[a] == 0 and w[a] != 0):
                how, off, *over = ("limit", d_limit) if exec_policy is None else exec_policy(i, a, dw, w[a], tgt[a], sig4[i][a])
                if over and over[0] is not None:  # the policy trades to its own weight (e.g. 0 = close fully)
                    dw = over[0] - w[a]
                if how == "market":
                    fill_min, fill_px, fill_fee, fill_type = 0, Oa[0], TAKER, "market"
                    stats["fills"] += 1
                    stats["market"] += 1
                elif how == "skip":
                    stats["skipped"] += 1
                else:
                    lim = Oa[0] * (1 - off) if dw > 0 else Oa[0] * (1 + off)
                    win = La[2:win_end] < lim if dw > 0 else Ha[2:win_end] > lim
                    fill_type = f"limit {100 * off:.2f}%"
                    if win.any():
                        fill_min, fill_px = 2 + int(np.argmax(win)), lim
                        stats["fills"] += 1
                        if exec_policy is not None:
                            stats["limit_offset_sum"] += off
                    else:
                        stats["unfilled"] += 1
            dq = dw / o1[i][a] if fill_min < 999 else 0.0
            qarr = np.full(240, qa)
            carr = np.zeros(240)
            cur_q, cur_e = qa, ea
            exit_done = False

            def levels(qq, ee):
                sg = entry_sd[a] if fixed_levels and np.isfinite(entry_sd[a]) else sd[a]
                if qq == 0 or not np.isfinite(ee) or not np.isfinite(sg):
                    return None, None
                mt = 2 * m_sl if m_tp is None else m_tp
                if qq > 0:
                    return ee * (1 - m_sl * sg), ee * (1 + mt * sg)
                return ee * (1 + m_sl * sg), ee * (1 - mt * sg)

            def first_exit(qq, lo_m, hi_m):
                sl, tp = levels(qq, cur_e)
                if sl is None or hi_m <= lo_m:
                    return None
                Ls, Hs = La[lo_m:hi_m], Ha[lo_m:hi_m]
                hs = Ls <= sl if qq > 0 else Hs >= sl
                ht = Hs > tp if qq > 0 else Ls < tp
                hit = hs | ht
                if not hit.any():
                    return None
                k = int(np.argmax(hit))
                mm = lo_m + k
                if hs[k]:
                    px = min(sl, Oa[mm]) if qq > 0 else max(sl, Oa[mm])
                    return mm, px, TAKER, "stops"
                return mm, tp, MAKER, "tps"

            def apply_exit(ev):
                nonlocal cur_q, cur_e
                mm, px, fee, kind = ev
                if events is not None:
                    events.append(dict(t=idx[i] + pd.Timedelta(hours=4, minutes=int(mm)), symbol=cols[a], kind="book_" + kind[:-1],
                                       side="sell" if cur_q > 0 else "buy", price=float(px), weight=float(-cur_q * px / (prev_eq if prev_eq else 1.0))))
                carr[mm:] += cur_q * px - abs(cur_q) * px * fee
                stats["fees"] += abs(cur_q) * px * fee
                stats[kind] += 1
                qarr[mm:] = 0.0
                cur_q, cur_e = 0.0, np.nan
                entry_sd[a] = np.nan

            seg_end = fill_min + 1 if fill_min < 240 else 240  # stop on the held position wins a same-minute tie (audit v188)
            ev = first_exit(cur_q, 0, seg_end)
            if ev is not None:
                apply_exit(ev)
                exit_done = True
            elif fill_min < 240:
                new_q = cur_q + dq
                if cur_q == 0 or np.sign(new_q) != np.sign(cur_q):
                    cur_e = fill_px if new_q != 0 else np.nan
                    entry_sd[a] = sd[a] if new_q != 0 else np.nan
                elif abs(new_q) > abs(cur_q):
                    cur_e = (abs(cur_q) * cur_e + abs(dq) * fill_px) / abs(new_q)
                carr[fill_min:] -= dq * fill_px + abs(dq) * fill_px * fill_fee
                stats["fees"] += abs(dq) * fill_px * fill_fee
                qarr[fill_min:] = new_q
                if events is not None:
                    events.append(dict(t=idx[i] + pd.Timedelta(hours=4, minutes=int(fill_min)), symbol=cols[a], kind="book_fill",
                                       side="buy" if dq > 0 else "sell", price=float(fill_px), weight=float(dw), target=float(tgt[a]),
                                       entry_type=fill_type))
                cur_q = new_q
                ev = first_exit(cur_q, fill_min, 240)
                if ev is not None:
                    apply_exit(ev)
            val_path = carr + qarr * Ca - qa * o1[i][a]
            pnl_cash = carr[-1]
            end_val = pnl_cash + cur_q * o2[i][a]
            fund = FUND_LONG * max(cur_q, 0.0) * o2[i][a] if settle[i] else 0.0
            stats["funding"] += fund
            path += val_path
            cash += end_val - qa * o1[i][a] - fund
            asset_pnl[a] = end_val - qa * o1[i][a] - fund
            q[a], entry[a] = cur_q, cur_e
        # dip sleeve
        sleeve_pnl = 0.0
        if sleeve:
            rn = (s[i] if rung_scale_fixed is None else rung_scale_fixed) * g[i] * size_mult * SIZE / 4 / S_REF  # per-rung size fixed
            fills = []  # (fill minute, ladder 0=4h / 1=hourly, rung, asset, limit, sigma, end minute)
            for r, k in enumerate(rungs):
                for a in range(na):
                    if not np.isfinite(sig4[i][a]):
                        continue
                    lv = o1[i][a] * (1 - k * sig4[i][a])
                    hit = L[i, 16:239, a].astype(float) < lv
                    if hit.any():
                        fills.append((16 + int(np.argmax(hit)), 0, r, a, lv, sig4[i][a], 240))
            if hourly and "sig1h" in prep:
                s1 = prep["sig1h"][i]
                for h in range(4):
                    a0, a1 = (16 if h == 0 else 60 * h + 4), 60 * h + 57
                    for r, k in enumerate(rungs):
                        for a in range(na):
                            if not np.isfinite(s1[a]) or not np.isfinite(O[i, 60 * h, a]):
                                continue
                            lv = float(O[i, 60 * h, a]) * (1 - k * s1[a])
                            hit = L[i, a0:a1 + 1, a].astype(float) < lv
                            if hit.any():
                                fills.append((a0 + int(np.argmax(hit)), 1, r, a, lv, s1[a], 60 * (h + 1)))
            fills.sort(key=lambda t: t[:4])
            taken = []
            rn_base = rn
            for f, lad, r, a, lv, sg, end_m in fills:
                rn = rn_base if align is None else rn_base * (align[0] if tgt[a] > 0 else align[1])
                if rn <= 0:
                    continue
                if sleeve_risk_budget is None:
                    open_now = sum(1 for t in taken if t[4] > f)
                    if (open_now + 1) * rn > N_MAX + 1e-12:
                        continue
                else:  # risk budget: loss if every open rung and the new one stop out (stop distance + gap allowance)
                    risk_open = sum(t[7] * (m_sleeve_sl * t[6] + gap) for t in taken if t[4] > f)
                    if risk_open + rn * (m_sleeve_sl * sg + gap) > sleeve_risk_budget + 1e-12:
                        continue
                Ha, La, Ca, Oa = (X[i, :, a].astype(float) for X in (H, L, C, O))
                tp = lv * (1 + m_sleeve_tp * sg)
                sl = lv * (1 - m_sleeve_sl * sg)
                x, ret, xk = end_m, None, "rung_timeout"
                if f + 1 < end_m:
                    hs = La[f + 1:end_m] <= sl
                    ht = Ha[f + 1:end_m] > tp
                    hit = hs | ht
                    if hit.any():
                        k = int(np.argmax(hit))
                        x = f + 1 + k
                        if hs[k]:
                            ret = min(sl, Oa[x]) / lv - 1 - MAKER - TAKER
                            stats["rung_stops"] += 1
                            xk = "rung_sl"
                        else:
                            ret = tp / lv - 1 - 2 * MAKER
                            stats["rung_tps"] += 1
                            xk = "rung_tp"
                if ret is None:
                    if end_m >= 240:
                        ret = o2[i][a] / lv - 1 - MAKER - TAKER - (FUND_LONG if settle[i] else 0.0)
                    else:
                        ret = Oa[end_m] / lv - 1 - MAKER - TAKER
                taken.append((f, r, a, lv, x, ret, sg, rn))
                sleeve_pnl += rn * ret
                if events is not None:
                    t0 = idx[i] + pd.Timedelta(hours=4)
                    events.append(dict(t=t0 + pd.Timedelta(minutes=int(f)), symbol=cols[a], kind="rung_fill", side="buy", price=float(lv),
                                       weight=float(rn), rung=float(rungs[r])))
                    events.append(dict(t=t0 + pd.Timedelta(minutes=int(min(x, 240))), symbol=cols[a], kind=xk, side="sell",
                                       price=float(lv * (1 + ret)), weight=float(rn), ret=float(ret)))
                seg = np.zeros(240)
                end = min(x, 240)
                seg[f:end] = Ca[f:end] / lv - 1
                if x < 240:
                    seg[x:] = ret
                path += rn * seg
            stats["rungs"] += len(taken)
        pnl = cash + sleeve_pnl
        if attrib is not None:
            attrib.append((idx[i] + pd.Timedelta(hours=4), asset_pnl.copy(), float(sleeve_pnl)))
        eq[i] = prev_eq * (1 + pnl)
        eq_min[i] = prev_eq * (1 + min(0.0, float(path.min())))
        eq_max[i] = prev_eq * (1 + max(0.0, float(path.max())))
        gross = float(np.abs(q * o2[i]).sum()) + (N_MAX if sleeve else 0.0)
        if 1 + float(path.min()) < MMR * max(gross, 1e-9):
            stats["liq"] += 1
        gb = float(np.abs(tgt).sum())
        stats["gross_sum"] += gb
        stats["gross_max"] = max(stats["gross_max"], gb)
        stats["bars"] += 1
        # drift weights to next bar start
        end_eq_rel = 1 + pnl
        w = np.where(np.isfinite(o2[i]), q * o2[i] / end_eq_rel, 0.0)
        net[i] = pnl
        if bars is not None:
            bars.append(dict(t=idx[i] + pd.Timedelta(hours=4), target=[float(x) for x in tgt], scale=float(s[i]), governor=float(g[i]),
                             equity=float(eq[i]), sig_d=[float(x) for x in sd], open=[float(x) for x in o1[i]],
                             entry=[float(x) for x in entry], qty=[float(x) for x in q]))
    return summarize(idx, net, eq, eq_min, g, stats, eq_max)


def summarize(idx, net, eq, eq_min, g, stats, eq_max=None):
    if eq_max is None:
        eq_max = eq
    full = np.asarray((idx >= v110.START) & (idx < v110.END))
    years = []
    for a in ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = np.asarray((idx >= a0) & (idx < a0 + pd.Timedelta(days=365)))
        first = int(np.argmax(mk))
        base = eq[first - 1] if first > 0 else 1.0
        e, em, ex = eq[mk] / base, eq_min[mk] / base, eq_max[mk] / base
        years.append(dict(anchor=a, net_pct=round(100 * float(e[-1] - 1), 2),
                          monthly_pct=round(100 * float(e[-1] ** (1 / 12) - 1), 3),
                          dd_1m_pct=round(100 * float(np.max(1 - np.minimum(e, em) / np.maximum.accumulate(np.concatenate([[1.0], np.maximum(e, ex)]))[1:])), 2),
                          mean_g=round(float(g[mk].mean()), 3)))
    first = int(np.argmax(full))
    base = eq[first - 1] if first > 0 else 1.0
    e, em, ex = eq[full] / base, eq_min[full] / base, eq_max[full] / base
    peak = np.maximum.accumulate(np.concatenate([[1.0], e]))[1:]
    peak1 = np.maximum.accumulate(np.concatenate([[1.0], np.maximum(e, ex)]))[1:]
    dd4 = float(np.max(1 - e / peak))
    dd1 = float(np.max(1 - np.minimum(e, em) / peak1))  # 1m-marked: peaks and troughs on the minute path (audit v188)
    geo5 = np.prod([1 + y["net_pct"] / 100 for y in years]) ** (1 / 5) - 1
    geo4 = np.prod([1 + y["net_pct"] / 100 for y in years[:4]]) ** (1 / 4) - 1
    out = dict(yearly=years,
               monthly_5y=round(100 * ((1 + geo5) ** (1 / 12) - 1), 3),
               monthly_dev4=round(100 * ((1 + geo4) ** (1 / 12) - 1), 3),
               monthly_last_year=years[-1]["monthly_pct"],
               dd_4h=round(100 * dd4, 2), dd_1m=round(100 * dd1, 2), gate_dd=round(100 * max(dd4, dd1), 2),
               losing_years=sum(1 for y in years if y["net_pct"] < 0),
               stats={k: (round(v, 4) if isinstance(v, float) else v) for k, v in stats.items()})
    out["gate_pass"] = bool(out["monthly_5y"] >= 5 and out["monthly_last_year"] >= 5 and out["losing_years"] == 0 and out["gate_dd"] <= 20)
    return out
