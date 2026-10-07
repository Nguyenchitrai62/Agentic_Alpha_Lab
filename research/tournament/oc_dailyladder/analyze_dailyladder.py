"""oc_dailyladder: DAILY-timeframe dip ladder (IDEAS.md idea #21).

Frozen PLAN.md definitions. LIGHT: hourly data only, one process, < 1 GB.
Causality: sigma_d uses daily opens <= O_{D-1}; levels from O_D (00:00 bar);
fills/exits on hourly bars of day D .. D+2 with time exit at D+3 00:00 open.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import harness5 as H5

OUT = ROOT / "research" / "tournament" / "oc_dailyladder"
HOURLY = H5.HOURLY
MAJORS = H5.MAJORS
ANCHORS = H5.ANCHORS
YEAR = pd.Timedelta(days=365)

RUNGS = (1.5, 2.0, 2.5)
FILL_BUF = 0.0005
FEE_MAKER = 0.0002
FEE_TAKER = 0.00055
FUND_8H = 0.0001
SIG_WIN = 90
SIG_MIN = 60
H_NS = 3_600_000_000_000
D_NS = 86_400_000_000_000


# ---------- pure helpers (imported by tests) ----------

def daily_sigma(opens: np.ndarray, win: int = SIG_WIN, min_n: int = SIG_MIN) -> np.ndarray:
    """Per-day sigma_d: std(ddof=1) of open-to-open simple returns over the
    win days ending D-1; NaN unless >= min_n finite returns."""
    o = np.asarray(opens, float)
    n = len(o)
    r = np.full(n, np.nan)
    ok = np.isfinite(o[1:]) & np.isfinite(o[:-1]) & (o[:-1] > 0)
    r[1:][ok] = o[1:][ok] / o[:-1][ok] - 1.0
    sig = np.full(n, np.nan)
    for i in range(n):
        seg = r[max(0, i - win):i]
        seg = seg[np.isfinite(seg)]
        if len(seg) >= min_n:
            sig[i] = float(np.std(seg, ddof=1))
    return sig


def first_fill_idx(lows: np.ndarray, level: float, buf: float = FILL_BUF) -> int:
    """First hour with low < level*(1-buf) (STRICT trade-through), else -1."""
    thr = level * (1.0 - buf)
    hit = np.nonzero(np.asarray(lows, float) < thr)[0]
    return int(hit[0]) if len(hit) else -1


def race_window(highs: np.ndarray, closes: np.ndarray, tp: float, sl: float):
    """Stop-first race over post-fill hourly bars: first j with close<=sl ->
    ('stop', j); elif high>tp -> ('tp', j); else (None, 'time')."""
    h = np.asarray(highs, float)
    c = np.asarray(closes, float)
    for j in range(len(h)):
        if np.isfinite(c[j]) and c[j] <= sl:
            return j, "stop"
        if np.isfinite(h[j]) and h[j] > tp:
            return j, "tp"
    return None, "time"


def count_settlements(fill_ns: int, exit_ns: int) -> int:
    """# of 00/08/16 UTC hour starts S with fill_ns < S <= exit_ns."""
    n = 0
    s = (int(fill_ns) // H_NS + 1) * H_NS
    e = int(exit_ns)
    while s <= e:
        if ((s // H_NS) % 24) in (0, 8, 16):
            n += 1
        s += H_NS
    return n


def max_dd(path: np.ndarray) -> float:
    """Max drawdown of a cumsum path starting at 0 (P_0=0 in the peak)."""
    p = np.asarray(path, float)
    peak = np.maximum.accumulate(np.concatenate([[0.0], p]))
    return float(np.max(peak - np.concatenate([[0.0], p])))


def pearson(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


# ---------- main simulation ----------

def load_hourly_majors():
    h = pd.read_parquet(HOURLY, columns=["t", "open", "high", "low", "close", "sym"])
    h = h[h["sym"].isin(MAJORS)].copy()
    h["t"] = pd.to_datetime(h["t"], utc=True)
    h = h.sort_values(["sym", "t"]).reset_index(drop=True)
    return h


def simulate_coin(g: pd.DataFrame) -> list:
    """Simulate all daily rungs for one coin. Returns trade dicts."""
    t = g["t"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    o = g["open"].to_numpy(float)
    hh = g["high"].to_numpy(float)
    ll = g["low"].to_numpy(float)
    cc = g["close"].to_numpy(float)
    sym = str(g["sym"].iloc[0])
    # day starts: t values at 00:00 UTC
    hod = (t // H_NS) % 24
    is_mid = hod == 0
    dpos = np.nonzero(is_mid)[0]  # positions of 00:00 bars
    ddate = pd.to_datetime(t[dpos]).floor("D")
    opens = o[dpos]
    sig = daily_sigma(opens)
    day0 = pd.Timestamp("2021-09-24", tz="UTC").value
    daymax = pd.Timestamp("2026-09-20", tz="UTC").value  # D+3 00:00 <= last bar
    devend = pd.Timestamp("2026-09-24", tz="UTC").value
    out = []
    for di in range(len(dpos)):
        d_ns = int(t[dpos[di]])
        if d_ns < day0 or d_ns > daymax or d_ns >= devend:
            continue
        s = sig[di]
        if not np.isfinite(s) or s <= 0:
            continue
        p0 = int(dpos[di])
        if p0 + 72 >= len(t):
            continue
        # contiguity: 73 bars p0..p0+72 exactly hourly, last = D+3 00:00
        if int(t[p0 + 72]) - int(t[p0]) != 72 * H_NS:
            continue
        o_d = opens[di]
        if not np.isfinite(o_d) or o_d <= 0:
            continue
        day_low = ll[p0:p0 + 24]
        for k in RUNGS:
            lv = o_d * (1.0 - k * s)
            if not np.isfinite(lv) or lv <= 0:
                continue
            fi = first_fill_idx(day_low, lv)
            if fi < 0:
                continue
            pf = p0 + fi
            tp = lv * (1.0 + 1.0 * s)
            sl = lv * (1.0 - 2.0 * s)
            j, kind = race_window(hh[pf + 1:p0 + 72], cc[pf + 1:p0 + 72], tp, sl)
            if kind == "tp":
                je = pf + 1 + j  # trigger hour
                px, fee_x, ets = tp, FEE_MAKER, int(t[je])
            elif kind == "stop":
                je = pf + 1 + j
                px, fee_x, ets = float(o[je + 1]), FEE_TAKER, int(t[je + 1])
            else:
                px, fee_x, ets = float(o[p0 + 72]), FEE_TAKER, int(t[p0 + 72])
            if not np.isfinite(px) or px <= 0:
                continue
            fund = FUND_8H * count_settlements(int(t[pf]), ets)
            net = px / lv - 1.0 - FEE_MAKER - fee_x - fund
            out.append(dict(sym=sym, D=pd.to_datetime(d_ns).strftime("%Y-%m-%d"),
                            k=k, sigma=float(s), level=float(lv),
                            fill_hour=int(fi), exit=kind, exit_px=float(px),
                            exit_ts=pd.to_datetime(ets).strftime("%Y-%m-%d %H:%M"),
                            exit_day=pd.to_datetime(ets).floor("D").strftime("%Y-%m-%d"),
                            fund=float(fund), net=float(net)))
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    h = load_hourly_majors()
    trades = []
    for sym, g in h.groupby("sym", sort=True):
        trades.extend(simulate_coin(g))
    tr = pd.DataFrame(trades)
    tr.to_parquet(OUT / "trades.parquet", index=False)
    tr["D"] = pd.to_datetime(tr["D"], utc=True)
    tr["exit_day"] = pd.to_datetime(tr["exit_day"], utc=True)

    # 4h BOT dip stream (harness5 test masks, selection by T; sums by exit date)
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    d["t_exit"] = pd.to_datetime(d["t_exit"], utc=True)
    folds = H5.folds(d)

    years_out, dd_tests, loyo, corr_y = [], [], [], []
    full_s = []
    full_b = []
    for yi, (y, a0, trm, te) in enumerate(folds):
        a0d = pd.Timestamp(a0)
        m_entry = (tr["D"] >= a0d) & (tr["D"] < a0d + YEAR)
        sub = tr[m_entry]
        n = int(len(sub))
        nets = sub["net"].to_numpy(float) if n else np.array([])
        s_sum = float(nets.sum()) if n else 0.0
        win = float((nets > 0).mean()) if n else float("nan")
        mean_bps = float(nets.mean() * 1e4) if n else float("nan")
        s_daily = sub.groupby(sub["exit_day"].dt.floor("D"))["net"].sum() if n else None

        te4 = d[te]
        b_daily = te4.groupby(te4["t_exit"].dt.floor("D"))["y_dep"].sum()

        grid = pd.date_range(a0d, a0d + YEAR + pd.Timedelta(days=3), freq="D", tz="UTC")
        sv = pd.Series(0.0, index=grid)
        bv = pd.Series(0.0, index=grid)
        if n:
            sv = sv.add(s_daily, fill_value=0.0).reindex(grid, fill_value=0.0)
        if len(te4):
            bv = bv.add(b_daily, fill_value=0.0).reindex(grid, fill_value=0.0)
        worst = float(sv.min())
        dd_s = max_dd(sv.to_numpy().cumsum())
        c = float(pearson(sv.to_numpy(), bv.to_numpy()))
        corr_y.append(c)
        full_s.append(sv)
        full_b.append(bv)

        # combined-DD test: c = b + 0.5*s vs scaled 4h alone
        Sb, Sc = float(bv.sum()), float((bv + 0.5 * sv).sum())
        if Sb > 0 and Sc > 0:
            dd_comb = max_dd((bv + 0.5 * sv).to_numpy().cumsum())
            dd_b = max_dd((bv * (Sc / Sb)).to_numpy().cumsum())
            dd_pass = bool(dd_comb <= dd_b)
        else:
            dd_comb, dd_b, dd_pass = float("nan"), float("nan"), False
        dd_tests.append({"anchor": str(a0.date()), "S_4h": round(Sb, 4),
                         "S_comb": round(Sc, 4), "maxDD_comb": round(dd_comb, 4),
                         "maxDD_4h_scaled": round(dd_b, 4), "pass": dd_pass})

        # LOYO pool (descriptive): sum over other 4 entry-years
        years_out.append({"anchor": str(a0.date()), "n": n,
                          "win_rate": round(win, 4) if n else None,
                          "mean_net_bps": round(mean_bps, 2) if n else None,
                          "sum": round(s_sum, 4),
                          "worst_day": round(worst, 4), "maxDD": round(dd_s, 4),
                          "corr_4h": round(c, 4) if np.isfinite(c) else None,
                          "n_4h": int(te.sum()), "sum_4h": round(Sb, 4),
                          "sum_pass": bool(s_sum > 0)})
    # full-period correlation on concatenated grids
    Sall = pd.concat(full_s).groupby(level=0).sum().sort_index()
    Ball = pd.concat(full_b).groupby(level=0).sum().sort_index()
    Sall, Ball = Sall.align(Ball, join="outer", fill_value=0.0)
    cfull = float(pearson(Sall.to_numpy(), Ball.to_numpy()))

    for hh in range(5):
        pool = sum(y["sum"] for k, y in enumerate(years_out) if k != hh)
        loyo.append({"heldout": years_out[hh]["anchor"], "pooled_sum": round(pool, 4),
                     "pass": bool(pool > 0)})

    n_sum = sum(1 for y in years_out if y["sum_pass"])
    n_dd = sum(1 for t in dd_tests if t["pass"])
    promising = bool(n_sum >= 4 and np.isfinite(cfull) and cfull < 0.5 and n_dd >= 3)
    res = {
        "meta": {"hourly": str(HOURLY), "fills": "research/tournament/ext/fills_U_ext.parquet via harness5.load",
                 "universe": "majors x daily rungs {1.5,2.0,2.5}, unit size per filled rung",
                 "rule": "PLAN.md frozen: sigma_d 90d open-to-open (min 60); fill low<lv*(1-5bps); TP +1sg maker; stop -2sg hourly-close next-open taker stop-first; time exit D+3 open taker; funding 1bp/8h; fill hour never TPs",
                 "years": "entry day D in [anchor, anchor+365d); daily sums by exit date; 4h stream = harness5 test masks, unweighted sum(y_dep) by exit date",
                 "T_min": str(tr["D"].min()) if len(tr) else None,
                 "T_max": str(tr["D"].max()) if len(tr) else None, "n_trades": int(len(tr))},
        "years": years_out, "corr_full": round(cfull, 4) if np.isfinite(cfull) else None,
        "dd_tests": dd_tests, "loyo": loyo,
        "decision": {"sum_pos": f"{n_sum}/5", "corr_lt_0.5": bool(np.isfinite(cfull) and cfull < 0.5),
                     "dd_not_worse": f"{n_dd}/5", "promising": promising},
    }
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1), "corr_full=", res["corr_full"])
    for y in years_out:
        print(y["anchor"], "n", y["n"], "win", y["win_rate"], "mean_bps", y["mean_net_bps"],
              "sum", y["sum"], "worst", y["worst_day"], "DD", y["maxDD"], "corr", y["corr_4h"])
    for t in dd_tests:
        print("DD", t["anchor"], "comb", t["maxDD_comb"], "vs 4h-scaled", t["maxDD_4h_scaled"], t["pass"])


if __name__ == "__main__":
    main()
