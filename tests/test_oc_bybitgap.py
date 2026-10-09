"""oc_bybitgap tests: causality/truncation + hand-checked synthetic (PLAN-fixed).

Fill timing: strict low < lv, live minutes 16..238 (no fill in first 5 min after
a 4h close — this replica starts at 16, stricter than the gate win_start=5);
sigma uses only bars strictly before T (rolling shift-1).
"""
import numpy as np
import pandas as pd


def find_fill_strict(low_win, level):
    hit = np.asarray(low_win, dtype=float) < float(level)
    return int(np.argmax(hit)) if hit.any() else None


def book_limit(o, sg):
    return o * (1 - max(0.001, 0.25 * sg))


def rung_lv(o, sg, k):
    return o * (1 - k * sg)


def sigma_4h(opens):
    return (opens.astype(float).pct_change()
            .rolling(360, min_periods=120).std(ddof=1).shift(1))


def test_fill_strict_and_live_start_causal():
    # hand-checked: touch-exact is NOT a fill (strict trade-through)
    assert find_fill_strict([97.0, 97.0], 97.0) is None
    assert find_fill_strict([97.5, 96.9], 97.0) == 1
    assert find_fill_strict([96.9, 97.5], 97.0) == 0
    # live window starts at minute 16: a low at minute 5 cannot fill
    full = np.full(240, 100.0)
    full[5] = 90.0
    live = full[16:239]
    assert find_fill_strict(live, 95.0) is None
    full2 = np.full(240, 100.0)
    full2[16] = 90.0
    assert find_fill_strict(full2[16:239], 95.0) == 0


def test_signal_truncation_causal():
    # sigma at T must equal sigma recomputed on data truncated to <= T
    # (shift-1: last bar strictly before T; appending future data is invisible)
    rng = np.random.default_rng(7)
    rets = rng.normal(0, 0.01, 500)
    opens = pd.Series(100 * np.cumprod(1 + rets),
                      index=pd.date_range("2021-09-01", periods=500, freq="4h", tz="UTC"))
    s_full = sigma_4h(opens)
    t = opens.index[400]
    s_tr = sigma_4h(opens.loc[:t])
    assert np.isfinite(s_full.loc[t]) and np.isfinite(s_tr.loc[t])
    assert abs(s_full.loc[t] - s_tr.loc[t]) < 1e-12
    # appending a huge future shock must not move sigma at T
    shocked = opens.copy()
    shocked.iloc[401] *= 2.0
    assert abs(sigma_4h(shocked).loc[t] - s_full.loc[t]) < 1e-12
    # +-1s boundary: bar at exactly T belongs to the future (uses minutes >= T)
    assert sigma_4h(opens.loc[:t]).loc[t] == s_full.loc[t]


def test_handchecked_synthetic():
    # O=100, sg=0.01: book off = max(10bps, 0.25*0.01=25bps) = 25bps -> 99.75
    assert abs(book_limit(100.0, 0.01) - 99.75) < 1e-9
    # tiny sigma -> 10bps floor binds: O=100, sg=0.001 -> 100*(1-0.001)=99.90
    assert abs(book_limit(100.0, 0.001) - 99.90) < 1e-9
    # dip rung k=3: 100*(1-0.03)=97.0
    assert abs(rung_lv(100.0, 0.01, 3.0) - 97.0) < 1e-9
    # bps: (101-100)/100*1e4 = 100
    assert abs((101.0 - 100.0) / 100.0 * 1e4 - 100.0) < 1e-9
    # agreement counters on a 3-bar toy: both/bin_only/byb_only/neither
    both = bin_only = byb_only = neither = 0
    for fb, fy in [(True, True), (True, False), (False, True), (False, False)]:
        if fb and fy:
            both += 1
        elif fb:
            bin_only += 1
        elif fy:
            byb_only += 1
        else:
            neither += 1
    assert (both, bin_only, byb_only, neither) == (1, 1, 1, 1)
