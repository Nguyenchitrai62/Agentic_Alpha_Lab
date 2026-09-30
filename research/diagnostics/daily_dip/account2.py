"""12h dip sub-account simulator with configurable stops (extends v289.simulate_account; same fills, TP, time exit, fees, funding).

stop_mode: "touch" (1m low <= L exp(-m_stop sigma), gap -> minute open; fill minute checked, stop-first),
           "close5" (bot-watched: the close of a clock 5-minute block <= L exp(-m_stop sigma) -> market exit at the next minute's open),
backstop: optional exchange-native touch stop at L exp(-backstop sigma) (always active, also with close5).
Sizing: every rung risks r_risk of the placement equity at risk_at sigma: notional = r_risk E / (risk_at sigma).
"""
from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd

_s = importlib.util.spec_from_file_location("v289_base", "research/parallel/rounds/parallel-20260906-r2/v289/v289_dip12h_account.py")
v289 = importlib.util.module_from_spec(_s)
_s.loader.exec_module(v289)
SYMS, P, WIN0, WIN1, KS = v289.SYMS, v289.P, v289.WIN0, v289.WIN1, v289.KS
MAKER, TAKER, FUND = v289.MAKER, v289.TAKER, v289.FUND


def simulate_account(data, r_risk=0.01, risk_at=4.0, stop_mode="close5", m_stop=4.0, backstop=8.0, m_tp=1.0, ks=KS):
    grid = data[SYMS[0]].index
    nm = len(grid)
    npd = nm // P
    O = {s: data[s]["open"].to_numpy(float) for s in SYMS}
    H = {s: data[s]["high"].to_numpy(float) for s in SYMS}
    L_ = {s: data[s]["low"].to_numpy(float) for s in SYMS}
    Cl = {s: data[s]["close"].to_numpy(float) for s in SYMS}
    sig = {}
    for s in SYMS:
        pc = Cl[s][P - 1: npd * P: P]
        r = np.diff(np.log(pc), prepend=np.nan)
        sig[s] = pd.Series(r).rolling(30, min_periods=20).std().shift(1).to_numpy()
    hours, mins = grid.hour.to_numpy(), grid.minute.to_numpy()
    fund_cum = np.cumsum((mins == 0) & np.isin(hours, (0, 8, 16)))
    block_end = (mins % 5) == 4                                  # last minute of a clock 5-minute block
    realized = np.zeros(nm + 1)
    u_low, u_close, notional = np.zeros(nm), np.zeros(nm), np.zeros(nm)
    cash, trades, liquidated = 1.0, [], None
    for p in range(npd):
        s0 = p * P
        if p > 0:
            cash += realized[s0 - P + 1: s0 + 1].sum()
        if liquidated is not None or cash <= 0:
            break
        E = cash
        for s in SYMS:
            sg = sig[s][p]
            if not np.isfinite(sg) or sg <= 0:
                continue
            o0 = O[s][s0]
            for k in ks:
                lim = o0 * np.exp(-k * sg)
                hit = np.flatnonzero(L_[s][s0 + WIN0: s0 + WIN1] < lim)
                if not len(hit):
                    continue
                f = s0 + WIN0 + int(hit[0])
                N = r_risk * E / (risk_at * sg)
                q = N / lim
                stop = lim * np.exp(-m_stop * sg)
                bstop = lim * np.exp(-backstop * sg) if backstop else -np.inf
                touch = stop if stop_mode == "touch" else bstop
                tp = lim * np.exp(m_tp * sg)
                end = s0 + P
                ex_j, ex_px, kind = end, (O[s][end] if end < nm else Cl[s][nm - 1]), "time"
                pending = False
                for j in range(f, min(end, nm)):
                    if pending:                                  # close-stop signalled at the previous minute's close
                        ex_j, ex_px, kind = j, O[s][j], "stop"
                        break
                    if j > f and O[s][j] <= touch:
                        ex_j, ex_px, kind = j, O[s][j], "stop"
                        break
                    if L_[s][j] <= touch:
                        ex_j, ex_px, kind = j, touch, "stop"
                        break
                    if j > f and H[s][j] > tp:
                        ex_j, ex_px, kind = j, tp, "tp"
                        break
                    if stop_mode == "close5" and block_end[j] and Cl[s][j] <= stop:
                        pending = True
                fee = N * MAKER + q * ex_px * (MAKER if kind == "tp" else TAKER)
                nf = fund_cum[min(ex_j, nm - 1)] - fund_cum[f]
                pnl = q * (ex_px - lim) - fee - FUND * N * nf
                seg = slice(f, min(ex_j, nm))
                u_low[seg] += q * (L_[s][seg] - lim) - N * MAKER
                u_close[seg] += q * (Cl[s][seg] - lim) - N * MAKER
                notional[seg] += N
                realized[min(ex_j, nm)] += pnl
                trades.append(dict(t=grid[f], sym=s, k=k, kind=kind, pnl_frac=pnl / E, ret=pnl / N))
        seg = slice(s0, min(s0 + P, nm))
        run_cash = cash + np.concatenate([[0.0], np.cumsum(realized[s0 + 1: min(s0 + P, nm)])])
        bad = np.flatnonzero(run_cash + u_low[seg] <= 0.01 * notional[seg])
        if len(bad) and notional[seg][bad[0]] > 0:
            liquidated = grid[s0 + int(bad[0])]
    return dict(grid=grid, cash=1.0 + np.cumsum(realized[:nm]), u_low=u_low, u_close=u_close, trades=pd.DataFrame(trades), liquidated=liquidated)
