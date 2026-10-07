"""oc_bookdipnet: book/dip long-overlap guard (idea #19, PLAN pre-registered).

LIGHT job: one process, no 1m data. Loads only the engine replica attrib
(raw_s0.pkl: exact per-coin-bar NET book P&L + per-bar dip P&L, fractions of
bar-start equity), the paired rungs table (rungs_s0.parquet), and small 4h
parquets to rebuild the book-target sign (research_books_d2 + bear filter,
exactly as run_ddanat17.py).

Guard (fixed): at holding-bar start B, for coin c, openW = sum of weights of
rungs with fill_t in [B-4h, B) and exit_t > B; thr_c = 2 * mean rung weight of
coin c (full-sample fixed scale); if openW >= thr_c and the book target for
(B, c) is long (> 0), that coin-bar's book P&L is x0.5 (shorts/flat unchanged).
Dip P&L unchanged (disclosed LIGHT approximation: no re-simulation of fills /
stops; halving the target halves gross + fees/funding proportionally).

Usage: .venv/Scripts/python.exe research/tournament/oc_bookdipnet/compute_bookdipnet.py
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
DD = ROOT / "research/tournament/oc_ddanat17"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
A5 = pd.Timestamp("2026-09-24", tz="UTC")
BAR = pd.Timedelta(hours=4)
GUARD_SCALE = 0.5


def research_books_d2() -> pd.DataFrame:
    """Mirror of scripts/forward_v205.py::research_books_d2 (same files, same math)."""
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


def bear_scaled_books() -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    """Bear-scaled d2 books on the books154 4h index (exactly as run_ddanat17)."""
    books154 = pd.read_parquet(CACHE / "books_v154.parquet")[SYMS]
    opens = pd.read_parquet(CACHE / "opens_v154.parquet")
    std = research_books_d2().reindex(books154.index).fillna(0.0)[SYMS]
    btc = opens["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std.copy()
    bv = bear
    arr = sb.to_numpy()
    arr[bv] = np.where(arr[bv] <= 0, arr[bv], arr[bv] * 0.5)
    sb = pd.DataFrame(arr, index=sb.index, columns=sb.columns)
    return sb, books154.index


def load_attrib() -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Attrib bar starts B, per-coin book fractions, sleeve fractions, raw eq grid."""
    raw = pickle.loads((DD / "raw_s0.pkl").read_bytes())
    att = raw["attrib"]
    B = pd.DatetimeIndex([pd.Timestamp(t, tz="UTC") for t, _, _ in att])
    abook = np.stack([np.asarray(b, float) for _, b, _ in att])
    asleep = np.array([float(s) for _, _, s in att])
    t = pd.DatetimeIndex(raw["t"])
    eq = np.asarray(raw["eq"], float)
    assert abook.shape[1] == 5 and len(B) == len(abook) == len(asleep)
    return B, abook, asleep, t, eq


def load_rungs() -> pd.DataFrame:
    r = pd.read_parquet(DD / "rungs_s0.parquet")
    r["fill_t"] = pd.to_datetime(r["fill_t"], utc=True)
    r["exit_t"] = pd.to_datetime(r["exit_t"], utc=True)
    return r


def overlap_open_weights(
    B: pd.DatetimeIndex, rungs: pd.DataFrame, inclusive: bool = False
) -> tuple[np.ndarray, dict, dict]:
    """openW[j, a] = sum of weights of coin-a rungs with fill in [B-4h,B).

    Strict (pre-registered): still open means exit_t > B.
    Inclusive (post-hoc sensitivity): exit_t >= B (keeps rungs that close at
    the B open — all 2422 rung_timeouts exit exactly on a B).
    Returns (openW matrix, avg per coin, thr per coin = 2*avg).
    """
    avg = {s: float(rungs.loc[rungs["symbol"] == s, "weight"].mean()) for s in SYMS}
    thr = {s: 2 * avg[s] for s in SYMS}
    per: dict[str, pd.DataFrame] = {}
    for s in SYMS:
        q = rungs.loc[rungs["symbol"] == s, ["fill_t", "exit_t", "weight"]].sort_values("fill_t")
        per[s] = q.reset_index(drop=True)
    Bi = B.asi8
    openW = np.zeros((len(B), len(SYMS)))
    for a, s in enumerate(SYMS):
        q = per[s]
        f = q["fill_t"].values.astype("datetime64[ns]").astype("int64")
        x = q["exit_t"].values.astype("datetime64[ns]").astype("int64")
        w = q["weight"].to_numpy(float)
        lo = np.searchsorted(f, (Bi - BAR.value))
        hi = np.searchsorted(f, Bi)
        for j in range(len(B)):
            if hi[j] > lo[j]:
                sl = slice(lo[j], hi[j])
                m = x[sl] >= Bi[j] if inclusive else x[sl] > Bi[j]
                if m.any():
                    openW[j, a] = float(w[sl][m].sum())
    return openW, avg, thr


def guard_mask(openW: np.ndarray, tgt: np.ndarray, thr: dict) -> np.ndarray:
    """True where the guard scales the coin-bar (overlap AND long target)."""
    thr_v = np.array([thr[s] for s in SYMS])
    overlap = openW >= thr_v[None, :]
    long = tgt > 0
    return overlap & long


def year_masks(B: pd.DatetimeIndex) -> list[tuple[str, np.ndarray]]:
    bounds = ANCHORS + [A5]
    out = []
    for k in range(5):
        m = (B >= bounds[k]) & (B < bounds[k + 1])
        out.append((f"{bounds[k].date()}", m))
    return out


def maxdd(e: np.ndarray) -> float:
    if len(e) == 0 or not np.isfinite(e).all():
        return float("nan")
    peak = np.maximum.accumulate(e)
    return float(np.max(1 - e / peak))


def year_stats(n: np.ndarray, B: pd.DatetimeIndex, m: np.ndarray) -> dict:
    """Compounded yearly path stats on 4h bars + UTC-date daily path stats."""
    nn = n[m]
    Bb = B[m]
    if len(nn) == 0:
        return dict(n_bars=0, ret=np.nan, lin=np.nan, maxdd_d=np.nan, worst_day=np.nan)
    eq = np.cumprod(1 + nn)
    eq = np.concatenate([[1.0], eq])[1:]
    ret = float(eq[-1] - 1)
    lin = float(nn.sum())
    dates = Bb.floor("D")
    df = pd.DataFrame(dict(n=nn), index=dates)
    # daily net per UTC date (compounded over that date's bars)
    daily = (1 + df["n"]).groupby(level=0).prod() - 1
    deq = (1 + daily).cumprod().to_numpy()
    return dict(
        n_bars=int(len(nn)),
        ret=ret,
        lin=lin,
        maxdd_d=maxdd(deq),
        worst_day=float(daily.min()),
        n_days=int(len(daily)),
    )


def main() -> None:
    B, abook, asleep, tgrid, eq = load_attrib()
    rungs = load_rungs()
    assert len(rungs) == 5466, len(rungs)
    assert len(B) == 10944, len(B)
    openW, avg, thr = overlap_open_weights(B, rungs, inclusive=False)
    openW_inc, _, _ = overlap_open_weights(B, rungs, inclusive=True)
    sb, _ = bear_scaled_books()
    # target for bar starting at B = bear-scaled d2 ffilled at B-4h
    dec = (B - BAR).tz_convert("UTC")
    tgt = sb.reindex(dec).ffill().to_numpy()
    assert tgt.shape == abook.shape, (tgt.shape, abook.shape)
    gm = guard_mask(openW, tgt, thr)
    gm_inc = guard_mask(openW_inc, tgt, thr)
    book_base = abook.copy()
    book_guard = abook.copy()
    book_guard[gm] *= GUARD_SCALE
    book_guard_inc = abook.copy()
    book_guard_inc[gm_inc] *= GUARD_SCALE
    n_base = book_base.sum(axis=1) + asleep
    n_guard = book_guard.sum(axis=1) + asleep
    n_guard_inc = book_guard_inc.sum(axis=1) + asleep
    long_leg = tgt > 0
    book_long_base = float(book_base[long_leg].sum())
    book_long_guard = float(book_guard[long_leg].sum())
    book_long_guard_inc = float(book_guard_inc[long_leg].sum())

    # expanding-mean causal sensitivity (side row only, not the decision)
    per_fill: dict[str, np.ndarray] = {}
    per_cum: dict[str, np.ndarray] = {}
    for s in SYMS:
        q = rungs.loc[rungs["symbol"] == s].sort_values("fill_t")
        w = q["weight"].to_numpy(float)
        per_fill[s] = q["fill_t"].values.astype("datetime64[ns]").astype("int64")
        per_cum[s] = np.cumsum(w)
    thr_exp = np.zeros_like(openW)
    Bi = B.asi8
    for a, s in enumerate(SYMS):
        f = per_fill[s]
        c = per_cum[s]
        # fills with fill_t < B (strictly before B)
        k = np.searchsorted(f, Bi, side="left")
        with np.errstate(invalid="ignore", divide="ignore"):
            mean_exp = np.where(k > 0, c[np.maximum(k - 1, 0)] / np.maximum(k, 1), np.nan)
        thr_exp[:, a] = 2 * mean_exp
    overlap_exp = (openW >= thr_exp) & np.isfinite(thr_exp)
    gm_exp = overlap_exp & long_leg
    book_guard_exp = abook.copy()
    book_guard_exp[gm_exp] *= GUARD_SCALE
    n_guard_exp = book_guard_exp.sum(axis=1) + asleep

    per_year = []
    masks = year_masks(B)
    for (name, m) in masks:
        st_b = year_stats(n_base, B, m)
        st_g = year_stats(n_guard, B, m)
        st_i = year_stats(n_guard_inc, B, m)
        st_e = year_stats(n_guard_exp, B, m)
        bl_b = float(book_base[m][long_leg[m]].sum())
        bl_g = float(book_guard[m][long_leg[m]].sum())
        bl_i = float(book_guard_inc[m][long_leg[m]].sum())
        per_year.append(dict(
            year=name,
            n_bars=int(m.sum()),
            guard_coin_bars=int(gm[m].sum()),
            overlap_coin_bars=int(((openW >= np.array([thr[s] for s in SYMS])[None, :])[m]).sum()),
            guard_coin_bars_inc=int(gm_inc[m].sum()),
            overlap_coin_bars_inc=int(((openW_inc >= np.array([thr[s] for s in SYMS])[None, :])[m]).sum()),
            guard_coin_bars_exp=int(gm_exp[m].sum()),
            book_long_base=bl_b,
            book_long_guard=bl_g,
            book_long_guard_inc=bl_i,
            base_ret=st_b["ret"], guard_ret=st_g["ret"], guard_inc_ret=st_i["ret"],
            base_lin=st_b["lin"], guard_lin=st_g["lin"], guard_inc_lin=st_i["lin"],
            base_maxdd_d=st_b["maxdd_d"], guard_maxdd_d=st_g["maxdd_d"],
            guard_inc_maxdd_d=st_i["maxdd_d"],
            base_worst_day=st_b["worst_day"], guard_worst_day=st_g["worst_day"],
            guard_inc_worst_day=st_i["worst_day"],
            guard_exp_ret=st_e["ret"], guard_exp_maxdd_d=st_e["maxdd_d"],
        ))
    dd_wins = sum(1 for y in per_year if np.isfinite(y["guard_maxdd_d"]) and np.isfinite(y["base_maxdd_d"]) and y["guard_maxdd_d"] < y["base_maxdd_d"])
    sum_wins = sum(1 for y in per_year if np.isfinite(y["guard_ret"]) and np.isfinite(y["base_ret"]) and y["guard_ret"] >= y["base_ret"])
    promising = bool(dd_wins >= 4 and sum_wins >= 3)
    dd_wins_inc = sum(1 for y in per_year if np.isfinite(y["guard_inc_maxdd_d"]) and np.isfinite(y["base_maxdd_d"]) and y["guard_inc_maxdd_d"] < y["base_maxdd_d"])
    sum_wins_inc = sum(1 for y in per_year if np.isfinite(y["guard_inc_ret"]) and np.isfinite(y["base_ret"]) and y["guard_inc_ret"] >= y["base_ret"])
    promising_inc = bool(dd_wins_inc >= 4 and sum_wins_inc >= 3)

    # cross-check: attrib-compounded base path vs raw engine equity over the same bars.
    # First attrib B <-> idx pos 0 (B-4h == tgrid[0]); map each attrib j to tgrid pos via B-4h.
    pos = tgrid.get_indexer((B - BAR).tz_convert("UTC"))
    assert int((pos < 0).sum()) == 0
    eq_rebased = eq[pos] / eq[pos[0] - 1] if pos[0] > 0 else eq[pos] / 1.0
    eq_attr = np.cumprod(1 + n_base)
    # align: eq[pos[j]] should equal prev_base * cumprod up to j; compare yearly ends
    rel = float(eq_attr[-1] / eq_rebased[-1] - 1) if eq_rebased[-1] != 0 else float("nan")

    out = dict(
        variant="book/dip long-overlap guard x0.5 on >=2-avg-rungs-open longs",
        phase=0,
        base="R2B1D17BF s=0 attrib (exact NET per-coin-bar book + dip, fractions of bar-start equity)",
        book_pnl_reconstruction="attrib per-coin-bar book fractions from raw_s0.pkl (engine NET of book fees/funding); dip = sleeve fractions; guarded = 0.5x on guard-on long coin-bars; fallback vectorised turnover model NOT used",
        overlap="fill_t in [B-4h,B) and exit_t > B strict (pre-registered); inclusive sensitivity exit_t >= B (keeps timeouts closing at the B open); thr_c = 2 * full-sample mean rung weight (fixed scale)",
        overlap_note="STRICT FIRES ZERO: max rung lifetime 224m < 240m bar, all 2422 timeouts exit exactly on a B, so no rung is strictly open across a holding-bar boundary (sleeve flat at every B). Inclusive variant is a disclosed post-hoc extra (dip-timeout brake, not true simultaneous exposure).",
        n_bars=int(len(B)),
        n_rungs=int(len(rungs)),
        avg_weight={s: round(avg[s], 6) for s in SYMS},
        thr={s: round(thr[s], 6) for s in SYMS},
        guard_coin_bars=int(gm.sum()),
        overlap_coin_bars=int((openW >= np.array([thr[s] for s in SYMS])[None, :]).sum()),
        guard_coin_bars_inc=int(gm_inc.sum()),
        overlap_coin_bars_inc=int((openW_inc >= np.array([thr[s] for s in SYMS])[None, :]).sum()),
        guard_share=float(gm.sum() / gm.size),
        guard_share_inc=float(gm_inc.sum() / gm_inc.size),
        book_long_base_full=round(book_long_base, 6),
        book_long_guard_full=round(book_long_guard, 6),
        book_long_guard_inc_full=round(book_long_guard_inc, 6),
        combined_base_full_ret=round(float(np.cumprod(1 + n_base)[-1] - 1), 6),
        combined_guard_full_ret=round(float(np.cumprod(1 + n_guard)[-1] - 1), 6),
        combined_guard_inc_full_ret=round(float(np.cumprod(1 + n_guard_inc)[-1] - 1), 6),
        per_year=[{k: (round(v, 6) if isinstance(v, float) else v) for k, v in y.items()} for y in per_year],
        decision=dict(
            maxdd_years_improved=int(dd_wins),
            sum_years_not_lower=int(sum_wins),
            PROMISING=promising,
            rule_text="PROMISING iff combined daily-close maxDD improves in >=4/5 years AND combined SUM (compounded yearly net) not lower in >=3/5 (pre-registered strict rule)",
        ),
        decision_inc=dict(
            maxdd_years_improved=int(dd_wins_inc),
            sum_years_not_lower=int(sum_wins_inc),
            PROMISING=promising_inc,
            rule_text="same bar, post-hoc inclusive-boundary extra variant (exit_t >= B)",
        ),
        checks=dict(
            n_attrib=int(len(B)),
            n_rungs=int(len(rungs)),
            attrib_vs_raw_eq_rel_diff=round(rel, 6),
        ),
    )
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(dict(strict=out["decision"], inclusive=out["decision_inc"]), indent=1))
    for y in per_year:
        print(y["year"], "bars", y["n_bars"], "guard", y["guard_coin_bars"],
              "guard_inc", y["guard_coin_bars_inc"],
              "bookL", round(y["book_long_base"], 4), "->", round(y["book_long_guard"], 4),
              "->inc", round(y["book_long_guard_inc"], 4),
              "ret", round(y["base_ret"], 4), "->", round(y["guard_ret"], 4),
              "->inc", round(y["guard_inc_ret"], 4),
              "DDd", round(y["base_maxdd_d"], 4), "->", round(y["guard_maxdd_d"], 4),
              "->inc", round(y["guard_inc_maxdd_d"], 4))


if __name__ == "__main__":
    main()
