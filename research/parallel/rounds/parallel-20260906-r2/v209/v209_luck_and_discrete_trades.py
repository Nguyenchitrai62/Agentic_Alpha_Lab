"""v209: is v205's profit luck? PnL attribution, placebo / beta tests, and a discrete-trade version (registry v209).

Why (user, 2026-09-27): v205's book positions are rebalanced every 4h, their SL/TP move with sigma and the average entry,
and most episodes end by a flip or a rebalance to ~0 (TP 50, SL 80 of 1052), so the user suspects the PnL is luck
rather than a general edge.

PART A - diagnostics of the frozen v205 pipeline (never used to choose anything; all five walk-forward years shown):
  A1 attribution per anchor year: book (per coin) vs dip sleeve, in % of the year's starting equity.
  A2 book episodes (backend.pipeline.build_orders on the engine events) with their equity contribution grouped by exit
     reason (TP / SL / flip / rebalance to 0 / open), and the concentration: share of the book PnL made by the best 10
     episodes and the book PnL without them.
  A3 beta: daily book-only return vs the equal-weight market (5 coins, open-to-open); OLS alpha/beta with a Newey-West
     (5 lags) t-statistic of alpha.
  A4 placebo: the same books circularly shifted inside the live window by 40 random offsets (seed 209, offsets >= 180 days
     from 0 and from the end) - book-only (sleeve off); also long-only |books| and sign-flipped -books. The real book-only
     5-year and dev4 monthly returns are ranked against the placebo distribution.
PART B - discrete trades (pre-registered, fixed before running; selection on the first four years only):
  ref_v205          the v205 pipeline (continuous rebalancing).
  D1_signal_exit    one trade per signal: open (limit -/+0.10% of the open) when flat (|w| < 1.2%) and |target| >= 5%, size =
                    target at entry, no adds/trims; SL/TP fixed at entry (entry -/+ 4 / 8 sigma_d of the entry bar);
                    exit by SL, TP, a flip (opposite target >= 5% -> trade to the new target) or a close to 0 (limit) when
                    |target| < 1%.
  D2_tp_sl_only     as D1 but no close on a weak signal: exit only by SL, TP or a flip.
  D3_strong_only    as D1 with the opening threshold |target| >= 10%.
  Everything else = v205 (books 0.5 annual + 0.5 quarterly v151, aligned sleeve unchanged, engine_user, Bybit fees,
  adverse funding, 1m execution, unfilled limits expire). SELECTION = robust criterion (AGENTS.md); the most recent year
  is scored once for the selected row. Exit-reason counts are reported for every row.

  python research/parallel/rounds/parallel-20260906-r2/v209/v209_luck_and_discrete_trades.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


eu = _load("engine_user", HERE.parent / "engine_user/engine_user.py")
v204 = _load("v204", HERE.parent / "v204/v204_sleeve_book_alignment.py")
from backend.pipeline import build_orders  # noqa: E402  (pure function, no database access)

KW = dict(m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239, sleeve_risk_budget=0.12, size_mult=1.5, align=(1.5, 0.5))
FLAT, OPEN_T, OPEN_STRONG, CLOSE_T = 0.012, 0.05, 0.10, 0.01
N_PLACEBO, SEED, MIN_SHIFT_DAYS = 40, 209, 180
H4 = 4 * 3600_000


def discrete(open_t, close_on_weak):
    def pol(i, a, dw, w, tgt, s4):
        if abs(w) < FLAT:
            return ("limit", 0.001, tgt) if abs(tgt) >= open_t else ("skip", 0.0)
        if np.sign(tgt) != np.sign(w) and abs(tgt) >= open_t:
            return "limit", 0.001, tgt  # flip
        if close_on_weak and abs(tgt) < CLOSE_T:
            return "limit", 0.001, 0.0
        return "skip", 0.0
    return pol


def load_books():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    return books154, opens, 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2


def exit_counts(events, bars, cols):
    orders = build_orders(events, bars, cols)
    c = defaultdict(int)
    for o in orders:
        if o[1] == "book":
            c[o[12]] += 1
    return dict(c)


def attribution(books, opens, prep):
    events, bars, att = [], [], []
    r = eu.simulate(books, opens, prep, events=events, bars=bars, attrib=att, **KW)
    cols = list(books.columns)
    eq_prev, eq = [], 1.0  # equity at the start of every live bar (initial = 1)
    for t, bp, sp in att:
        eq_prev.append(eq)
        eq *= 1 + bp.sum() + sp
    ts = np.array([int(t.timestamp() * 1000) for t, _, _ in att])
    book = np.array([bp for _, bp, _ in att]) * np.array(eq_prev)[:, None]
    sleeve = np.array([sp for _, _, sp in att]) * np.array(eq_prev)
    years = []
    for a in eu.ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = (ts >= int(a0.timestamp() * 1000)) & (ts < int((a0 + pd.Timedelta(days=365)).timestamp() * 1000))
        if not mk.any():
            continue
        e0 = np.array(eq_prev)[mk][0]
        years.append(dict(anchor=a[:10], book_pct=round(100 * book[mk].sum() / e0, 2), sleeve_pct=round(100 * sleeve[mk].sum() / e0, 2),
                          book_by_coin={c: round(100 * book[mk, j].sum() / e0, 2) for j, c in enumerate(cols)}))
    # episodes: contribution of every book order = its coin's PnL over the bars it was held
    orders = build_orders(events, bars, cols)
    col_ix = {c: j for j, c in enumerate(cols)}
    bar_ix = {t: k for k, t in enumerate(ts)}
    eps = []
    for o in orders:
        if o[1] != "book":
            continue
        j, t0 = col_ix[o[0]], o[4] // H4 * H4
        t1 = (o[10] // H4 * H4) if o[10] else ts[-1]
        k0, k1 = bar_ix.get(t0), bar_ix.get(t1)
        if k0 is None or k1 is None:
            continue
        eps.append(dict(symbol=o[0], side=o[2], reason=o[12], entry_t=o[4], contrib=float(book[k0:k1 + 1, j].sum())))
    total = sum(e["contrib"] for e in eps)
    by = defaultdict(lambda: dict(n=0, contrib=0.0, wins=0))
    for e in eps:
        g = by[e["reason"]]
        g["n"] += 1
        g["contrib"] += e["contrib"]
        g["wins"] += e["contrib"] > 0
    top = sorted(eps, key=lambda e: -e["contrib"])
    conc = dict(episodes=len(eps), book_total=round(total, 4), top10_share=round(sum(e["contrib"] for e in top[:10]) / total, 3),
                book_without_top10=round(total - sum(e["contrib"] for e in top[:10]), 4),
                winners_share=round(np.mean([e["contrib"] > 0 for e in eps]), 3),
                top10=[dict(symbol=e["symbol"], side=e["side"], reason=e["reason"],
                            entry=str(pd.Timestamp(e["entry_t"], unit="ms", tz="UTC"))[:16], contrib_pct=round(100 * e["contrib"], 2)) for e in top[:10]])
    reasons = {k: dict(n=v["n"], contrib_pct_of_initial=round(100 * v["contrib"], 2), share_of_book=round(v["contrib"] / total, 3),
                       win_rate=round(v["wins"] / v["n"], 3)) for k, v in by.items()}
    return r, dict(years=years, episodes_by_exit=reasons, concentration=conc, sleeve_total_pct=round(100 * sleeve.sum(), 2)), att


def beta_test(att, opens, cols):
    ts = pd.DatetimeIndex([t for t, _, _ in att])
    book = pd.Series([bp.sum() for _, bp, _ in att], index=ts)
    day_book = (1 + book).groupby(ts.floor("D")).prod() - 1
    o = opens[cols]
    mret = o.pct_change().mean(axis=1)
    mret.index = mret.index + pd.Timedelta(hours=4)  # open-to-open return realised at the next bar start, like the book PnL
    day_mkt = (1 + mret.reindex(ts).fillna(0.0)).groupby(ts.floor("D")).prod() - 1
    y, x = day_book.to_numpy(), day_mkt.reindex(day_book.index).fillna(0.0).to_numpy()
    X = np.column_stack([np.ones_like(x), x])
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    u = y - X @ b
    n, L = len(y), 5
    S = (X * u[:, None]).T @ (X * u[:, None])
    for l in range(1, L + 1):
        w = 1 - l / (L + 1)
        G = (X[l:] * u[l:, None]).T @ (X[:-l] * u[:-l, None])
        S += w * (G + G.T)
    XtX = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(XtX @ S @ XtX))
    return dict(alpha_daily_pct=round(100 * b[0], 4), alpha_t_nw5=round(b[0] / se[0], 2), beta=round(b[1], 3),
                r2=round(1 - u.var() / y.var(), 3), alpha_monthly_pct=round(100 * ((1 + b[0]) ** 30.4 - 1), 2), days=n)


def placebo(books, opens, prep):
    kw = dict(KW, sleeve=False, align=None)
    live = np.asarray((books.index >= eu.v110.START) & (books.index < eu.v110.END))
    vals = books.to_numpy()
    seg = vals[live]
    n = len(seg)
    lo = MIN_SHIFT_DAYS * 6
    rng = np.random.default_rng(SEED)
    shifts = rng.integers(lo, n - lo, size=N_PLACEBO)

    def run(v):
        b = books.copy()
        arr = vals.copy()
        arr[live] = v
        b.iloc[:, :] = arr
        r = eu.simulate(b, opens, prep, **kw)
        return r["monthly_5y"], r["monthly_dev4"]

    real = run(seg)
    plc = []
    for n_done, k in enumerate(shifts, 1):
        plc.append(run(np.roll(seg, int(k), axis=0)))
        print(f"placebo {n_done}/{len(shifts)} shift {int(k)} -> {plc[-1]}", flush=True)
    longonly = run(np.abs(seg))
    flipped = run(-seg)
    p5 = np.array([p[0] for p in plc])
    p4 = np.array([p[1] for p in plc])
    return dict(book_only_real={"monthly_5y": real[0], "monthly_dev4": real[1]},
                placebo_monthly_5y=dict(mean=round(float(p5.mean()), 3), p95=round(float(np.percentile(p5, 95)), 3),
                                        max=round(float(p5.max()), 3), share_ge_real=round(float((p5 >= real[0]).mean()), 3)),
                placebo_monthly_dev4=dict(mean=round(float(p4.mean()), 3), p95=round(float(np.percentile(p4, 95)), 3),
                                          max=round(float(p4.max()), 3), share_ge_real=round(float((p4 >= real[1]).mean()), 3)),
                long_only_abs_books={"monthly_5y": longonly[0], "monthly_dev4": longonly[1]},
                sign_flipped_books={"monthly_5y": flipped[0], "monthly_dev4": flipped[1]},
                shifts_bars=[int(k) for k in shifts])


def main():
    books154, opens, books = load_books()
    cols = list(books.columns)
    prep = eu.prepare(books154, opens)
    out = {"version": "v209", "constants": dict(FLAT=FLAT, OPEN_T=OPEN_T, OPEN_STRONG=OPEN_STRONG, CLOSE_T=CLOSE_T,
                                                N_PLACEBO=N_PLACEBO, SEED=SEED, MIN_SHIFT_DAYS=MIN_SHIFT_DAYS)}
    # ---------------- PART B first (candidates; the printout hides the most recent year while choosing)
    rows = {}
    for key, pol in (("ref_v205", None), ("D1_signal_exit", discrete(OPEN_T, True)), ("D2_tp_sl_only", discrete(OPEN_T, False)),
                     ("D3_strong_only", discrete(OPEN_STRONG, True))):
        ev, bs = [], []
        r = eu.simulate(books, opens, prep, exec_policy=pol, fixed_levels=pol is not None, events=ev, bars=bs, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["book_exits"] = exit_counts(ev, bs, cols)
        rows[key] = r
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years", [(y["anchor"][:4], y["net_pct"]) for y in r["yearly"][:4]], "exits", r["book_exits"],
              "fills", r["stats"]["fills"], "fees", r["stats"]["fees"], flush=True)
        if key == "ref_v205":
            assert abs(r["monthly_dev4"] - 5.824) < 0.002, "reference must reproduce v205"
    sel = v204.robust_select(rows)
    s = rows[sel]
    out["partB"] = {"rows": rows, "selected": sel, "final_score_selected": {
        "monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"], "losing_years": s["losing_years"],
        "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"], "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]]}}
    print("SELECTED", sel, out["partB"]["final_score_selected"], flush=True)
    # ---------------- PART A diagnostics (v205)
    _, diag, att = attribution(books, opens, prep)
    diag["beta"] = beta_test(att, opens, cols)
    print("A1/A2", json.dumps({k: diag[k] for k in ("years", "episodes_by_exit", "sleeve_total_pct")}), flush=True)
    print("A2 concentration", json.dumps({k: v for k, v in diag["concentration"].items() if k != "top10"}), flush=True)
    print("A3 beta", diag["beta"], flush=True)
    (HERE / "v209_partial.json").write_text(json.dumps(dict(out, partA=diag), indent=1, default=str))  # survives a crash in A4
    diag["placebo"] = placebo(books, opens, prep)
    print("A4 placebo", json.dumps({k: v for k, v in diag["placebo"].items() if k != "shifts_bars"}), flush=True)
    out["partA"] = diag
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v209_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
