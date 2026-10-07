"""oc_ethbtc regimes: causal ETH/BTC relative trend + BTC dominance proxy.

Built ONLY from 4h opens with index <= t (causal). No 1m data, one
process, small frames.

  python research/tournament/oc_ethbtc/regimes_ethbtc.py  # smoke print

Definitions (PLAN.md):
  ratio[t]    = O_ETH[t] / O_BTC[t]
  ethbtc30[t] = log(ratio[t] / ratio[t-180])              (30 d, 180 bars)
  ethbtc90[t] = log(ratio[t] / ratio[t-540])              (90 d, 540 bars)
  dom30[t]    = log(BTC[t]/BTC[t-180]) - mean_s log(S[t]/S[t-180])
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
VARS = ["ethbtc30", "ethbtc90", "dom30"]
B30, B90 = 180, 540


def load_opens() -> pd.DataFrame:
    o = pd.read_parquet(CACHE / "opens_v154.parquet")[SYMS]
    assert o.index.is_monotonic_increasing and o.index.tz is not None
    return o.sort_index()


def compute_regimes(opens: pd.DataFrame) -> pd.DataFrame:
    """Causal regimes on the opens grid; NaN until lags are available."""
    opens = opens.sort_index()
    ratio = opens["ETHUSDT"] / opens["BTCUSDT"]
    ethbtc30 = np.log(ratio / ratio.shift(B30))
    ethbtc90 = np.log(ratio / ratio.shift(B90))
    r30 = np.log(opens / opens.shift(B30))
    dom30 = r30["BTCUSDT"] - r30[SYMS].mean(axis=1)
    reg = pd.DataFrame(
        {"ethbtc30": ethbtc30, "ethbtc90": ethbtc90, "dom30": dom30},
        index=opens.index,
    )
    return reg


def regimes_truncated(opens: pd.DataFrame, end: pd.Timestamp) -> pd.DataFrame:
    """Recompute from opens truncated to index <= end (causality probe)."""
    return compute_regimes(opens.loc[opens.index <= end])


def assign_to_fills(
    fill_T: pd.Series, regimes: pd.DataFrame
) -> pd.DataFrame:
    """Map each fill decision time T to the last grid t <= T.

    Returns DataFrame indexed like fill_T with grid_t + regime columns.
    Rows with T before the first grid time get NaT/NaN (dropped later).
    """
    grid = pd.DatetimeIndex(regimes.index.sort_values())
    tvals = pd.DatetimeIndex(pd.to_datetime(fill_T, utc=True))
    pos = grid.searchsorted(tvals, side="right") - 1
    out = pd.DataFrame(
        index=fill_T.index,
        data={
            "grid_t": [grid[p] if p >= 0 else pd.NaT for p in pos],
        },
    )
    for v in VARS:
        vals = regimes[v].values
        out[v] = [float(vals[p]) if p >= 0 else float("nan") for p in pos]
    out["grid_t"] = pd.to_datetime(out["grid_t"], utc=True)
    return out


def research_books_d2() -> pd.DataFrame:
    """Mirror of oc_bookic compute (same files, same math)."""
    m = lambda f: pd.read_parquet(CACHE / f)[SYMS]  # noqa: E731
    A, Aq = m("member_A_O1_orders.parquet"), m("member_Aq_O1_orders.parquet")
    B, Bq = m("member_B_tv.parquet"), m("member_Bq_tv.parquet")
    idx = A.index.union(Aq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)  # noqa: E731
    o1 = 0.5 * (f(A) + f(B)) / 2 + 0.5 * (f(Aq) + f(Bq)) / 2
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    Dq = pd.read_parquet(CACHE / "members_quarterly_D.parquet")[SYMS]
    idx2 = o1.index.union(D.index).union(Dq.index)
    g = lambda X: X.reindex(idx2).fillna(0.0)  # noqa: E731
    return 0.8 * g(o1) + 0.2 * (g(D) + g(Dq)) / 2


if __name__ == "__main__":
    o = load_opens()
    r = compute_regimes(o)
    print(f"opens {o.index.min()} .. {o.index.max()} n={len(o)}")
    print(f"regimes valid from {r.dropna().index.min()} n_valid={int(r.dropna().shape[0])}")
    print(r.dropna().quantile([0.33, 0.67]).round(5).to_string())
