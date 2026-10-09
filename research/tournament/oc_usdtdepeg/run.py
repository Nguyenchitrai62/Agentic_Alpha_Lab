"""oc_usdtdepeg runner: dev4 standalone -> choice -> last year once -> overlay.

Usage: .venv/Scripts/python.exe research/tournament/oc_usdtdepeg/run.py
Writes results.json next to this file and prints the tables for REPORT.md.
"""

from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import renet, simulate, summarize

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"
USDT = ROOT / "data/raw/coinbase_usdt_20261006/USDT-USD_1h.parquet"

MAKER, TAKER = 0.0002, 0.00055          # gate (Coinbase-like, labelled)
R_MAKER, R_TAKER = 0.004, 0.006        # retail stress row
VARIANTS = {"E1": (0.9975, 0.9995, 0.9900), "E2": (0.995, 0.999, 0.985)}
ANCH = [pd.Timestamp(a, tz="UTC") for a in
        ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]]
YEAR = pd.Timedelta(days=365)
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
SEED = 7
N_PBO = 200
SLEEVE_F = 0.05


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    df = pd.read_parquet(USDT)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df[df["open_time"] < CAP].sort_values("open_time").reset_index(drop=True)
    rows = [{"t": df["open_time"].iloc[k], "open": float(df["open"].iloc[k]),
             "high": float(df["high"].iloc[k]), "low": float(df["low"].iloc[k]),
             "close": float(df["close"].iloc[k])} for k in range(len(df))]
    assert (df["open_time"].diff().dropna() > pd.Timedelta(0)).all(), "bars sorted"
    print(f"bars: {len(rows)} {rows[0]['t']} .. {rows[-1]['t']}")

    # ---- standalone, dev4 years first (signals in [A0, A4)) ----
    dev_events: dict[str, list[dict]] = {}
    dev_incomplete: dict[str, list[dict]] = {}
    for tag, (trig, tp, stop) in VARIANTS.items():
        ev, inc = simulate(rows, trig, tp, stop, MAKER, TAKER)
        dev_events[tag] = [e for e in ev if e["signal_t"] < ANCH[4]]
        dev_incomplete[tag] = [e for e in inc if e["signal_t"] < ANCH[4]]
    for tag in VARIANTS:
        n5 = len(dev_events[tag])
        print(tag, "dev4 filled events:", n5,
              "incomplete:", len(dev_incomplete[tag]))

    # ---- choice on dev4 only (PLAN.md rule) ----
    sums = {t: sum(e["net"] for e in dev_events[t]) for t in VARIANTS}
    means = {t: (sum(e["net"] for e in dev_events[t]) / len(dev_events[t])
                 if dev_events[t] else float("-inf")) for t in VARIANTS}
    # testability floor is on FIVE years; dev4 check here is provisional,
    # final floor uses dev4 + the single last-year scoring below.
    order = sorted(VARIANTS, key=lambda t: (sums[t], means[t],
                                            len(dev_events[t]), t))
    chosen = order[-1]
    print("dev4 sums:", {t: round(s, 6) for t, s in sums.items()},
          "-> provisional chosen:", chosen)

    # ---- most-recent year scored ONCE, chosen variant only ----
    last: list[dict] = []
    last_inc: list[dict] = []
    trig, tp, stop = VARIANTS[chosen]
    ev_all, inc_all = simulate(rows, trig, tp, stop, MAKER, TAKER)
    last = [e for e in ev_all if ANCH[4] <= e["signal_t"] < ANCH[4] + YEAR]
    last_inc = [e for e in inc_all if ANCH[4] <= e["signal_t"]]
    n5 = len(dev_events[chosen]) + len(last)
    print(f"{chosen}: last-year filled events: {len(last)} "
          f"incomplete: {len(last_inc)} | five-year filled total: {n5}")
    untestable = n5 < 10

    # ---- per-year standalone tables (both variants dev4; last year chosen) ----
    years_out: dict[str, dict] = {}
    for tag in VARIANTS:
        per_y = {}
        for y in range(4):
            evy = [e for e in dev_events[tag]
                   if ANCH[y] <= e["signal_t"] < ANCH[y] + YEAR]
            s = summarize(evy)
            rn = renet(evy, R_MAKER, R_TAKER)
            s["retail_sum"] = round(sum(rn), 6)
            s["retail_mean_bps"] = round(sum(rn) / len(rn) * 1e4, 2) if rn else 0.0
            per_y[str(ANCH[y].date())] = s
        years_out[tag] = per_y
    s = summarize(last)
    rn = renet(last, R_MAKER, R_TAKER)
    s["retail_sum"] = round(sum(rn), 6)
    s["retail_mean_bps"] = round(sum(rn) / len(rn) * 1e4, 2) if rn else 0.0
    years_out[chosen][str(ANCH[4].date())] = s

    # ---- placebo on dev4 (200 draws, seed 7) ----
    rng = np.random.default_rng(SEED)
    idx = np.array([r["t"].value for r in rows])
    pbo: dict[str, dict] = {}
    for tag, (trig, tp, stop) in VARIANTS.items():
        acts = dev_events[tag]
        per_y_n = []
        for y in range(4):
            per_y_n.append(len([e for e in acts
                                if ANCH[y] <= e["signal_t"] < ANCH[y] + YEAR]))
        actual_sum = sums[tag]
        sums_draw = []
        for _ in range(N_PBO):
            tot = 0.0
            for y, ny in enumerate(per_y_n):
                if ny == 0:
                    continue
                lo = np.searchsorted(idx, (ANCH[y]).value, side="left")
                hi = np.searchsorted(idx, (ANCH[y] + YEAR).value, side="left")
                picks = rng.integers(lo, hi, size=ny)
                for p in picks:
                    # forced fill at L (maker), same exits from bar p (PLAN.md)
                    lim = float(rows[p]["close"]) - 0.0001
                    kind, px, last_j = None, None, min(p + 72, len(rows) - 1)
                    for j in range(p, last_j + 1):
                        if float(rows[j]["low"]) <= stop:
                            kind, px = "stop", stop
                            break
                        if float(rows[j]["high"]) > tp:
                            kind, px = "tp", tp
                            break
                    if kind is None:
                        px = float(rows[last_j]["close"])
                        kind = "cap"
                    fee = MAKER if kind == "tp" else TAKER
                    tot += (px - lim) / lim - MAKER - fee
            sums_draw.append(tot)
        sums_draw = np.array(sums_draw)
        pct = float((sums_draw <= actual_sum).mean() * 100)
        pbo[tag] = {"n_draws": N_PBO, "seed": SEED,
                    "actual_sum": round(actual_sum, 6),
                    "pbo_mean": round(float(sums_draw.mean()), 6),
                    "pbo_p95": round(float(np.percentile(sums_draw, 95)), 6),
                    "percentile": round(pct, 1)}
        print(tag, "placebo:", pbo[tag])

    # ---- G2 baseline + overlay (exit-time dSleeve, 5 % sleeve) ----
    v388 = _load("v388_for_depeg", RD / "v388/v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid = pd.date_range(GRID0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    runs = pickle.loads(V421.read_bytes())
    strat = "R2B1D17BFG2"
    Es, Ms = [], []
    for s_ in range(4):
        e1, m1 = v388.hourly(runs[s_][strat], GRID0, g1)
        assert (e1.index == grid).all()
        Es.append(e1.to_numpy(dtype=float))
        Ms.append(m1.to_numpy(dtype=float))
    Es, Ms = np.stack(Es), np.stack(Ms)

    def overlay(all_events: list[dict], f: float):
        """Per-year reset pass + continuous full-path pass. f=0 -> base."""
        per_y = []
        for y, a0 in enumerate(ANCH):
            a1 = a0 + YEAR
            seg = (grid > a0) & (grid <= a1)
            ii = np.where(np.asarray(seg))[0]
            le = gn <= a0.value
            b = np.array([float(Es[s_][le][-1]) if le.any() else 1.0
                          for s_ in range(4)])
            E4 = [Es[s_][ii] / b[s_] for s_ in range(4)]
            M4 = [Ms[s_][ii] / b[s_] for s_ in range(4)]
            es = np.mean(E4, axis=0)
            ms = np.mean(M4, axis=0)
            if f == 0.0 or not all_events:
                A_arr, M_arr = es, ms
            else:
                evy = [e for e in all_events
                       if a0 <= e["signal_t"] < a1]
                g = es / np.concatenate([[1.0], es[:-1]])
                hh = ms / np.concatenate([[1.0], es[:-1]])
                # entry/exit hour positions on the segment
                ent = {int(np.searchsorted(gn[ii], e["fill_t"].value,
                                           side="right")): e for e in evy}
                ext = {}
                for e in evy:
                    p = int(np.searchsorted(gn[ii], e["exit_t"].value
                                            + 3_600_000_000_000, side="right")) - 1
                    ext.setdefault(max(p, 0), []).append(e)
                A_arr = np.empty(len(ii))
                M_arr = np.empty(len(ii))
                A_prev = 1.0
                open_n: dict[int, float] = {}
                for k in range(len(ii)):
                    if k in ent:
                        open_n[k] = f * A_prev
                    dU = 0.0
                    for e in ext.get(k, []):
                        # find its entry key (same event object identity kept)
                        key = next(q for q, ee in ent.items() if ee is e
                                   or ee["fill_t"] == e["fill_t"])
                        dU += open_n.pop(key, 0.0) * e["net"]
                    A_i = A_prev * g[k] + dU
                    M_i = A_prev * hh[k] + dU
                    A_arr[k], M_arr[k] = A_i, M_i
                    A_prev = A_i
            pk = np.maximum.accumulate(A_arr)
            R = round(100 * float(A_arr[-1] ** (1 / 12) - 1), 3)
            DD = round(100 * float(np.max(1 - M_arr / pk)), 2)
            per_y.append({"anchor": str(a0.date()), "R": R, "DD": DD,
                          "end": round(float(A_arr[-1]), 6)})
        R5 = round(float(np.prod([1 + yy["R"] / 100 for yy in per_y])
                         ** (1 / 5) - 1) * 100, 3)
        return {"years": per_y, "R": R5,
                "W": min(yy["R"] for yy in per_y),
                "DD": max(yy["DD"] for yy in per_y),
                "losing": sum(yy["R"] < 0 for yy in per_y)}

    base = overlay([], 0.0)
    exp = json.loads(V421_RES.read_text())["rows"][strat]
    assert [yy["R"] for yy in base["years"]] == [r for r, _ in exp["years"]], base
    assert [yy["DD"] for yy in base["years"]] == [d for _, d in exp["years"]], base
    assert base["R"] == exp["R"] and base["W"] == exp["W"], (base, exp)
    assert base["DD"] == exp["DD"], (base, exp)
    print("f=0 validation OK: reproduces v421_result G2 to the digit")

    # overlay uses the CHOSEN variant's five-year events (dev4 + last year)
    ch_all = [e for e in ev_all if e["signal_t"] < ANCH[4] + YEAR]
    ov = overlay(ch_all, SLEEVE_F)
    add = round(ov["R"] - base["R"], 3)
    print(f"G2+{chosen} f={SLEEVE_F}: R {ov['R']} W {ov['W']} DD {ov['DD']} "
          f"losing {ov['losing']} (add {add:+.3f} pp/mo)")

    # ---- daily correlation vs G2 (dev4) ----
    es_tot = Es.mean(axis=0)
    gret = pd.Series(es_tot, index=grid).resample("1D").last().pct_change()
    sl = pd.Series(0.0, index=pd.date_range("2021-09-24", "2025-09-23", freq="1D",
                                            tz="UTC"))
    for e in dev_events[chosen]:
        d = e["exit_t"].floor("D")
        if d in sl.index:
            sl[d] += e["net"] * SLEEVE_F
    al = gret.reindex(sl.index).fillna(0.0)
    corr = round(float(sl.corr(al)), 3) if sl.abs().sum() > 0 else float("nan")
    print("dev4 daily corr (sleeve vs G2):", corr)

    inc_out = {t: len(dev_incomplete[t]) for t in VARIANTS}
    inc_out[f"{chosen}_last"] = len(last_inc)
    out = {
        "meta": {
            "data": "data/raw/coinbase_usdt_20261006/USDT-USD_1h.parquet (1h only; no 1m/5m exist)",
            "bars": [str(rows[0]["t"]), str(rows[-1]["t"]), len(rows)],
            "variants": {t: {"trigger": v[0], "tp": v[1], "stop": v[2]}
                         for t, v in VARIANTS.items()},
            "entry": "limit BUY L=close-0.0001 valid 4 bars, strict trade-through (low<L), maker 0.0002",
            "exits": "TP limit strict (high>TP) maker; stop touch (low<=stop) taker STOP-FIRST; 72-bar cap close taker",
            "fees_gate": [MAKER, TAKER], "fees_retail": [R_MAKER, R_TAKER],
            "size": "0.05 x account equity per filled event; A(t)=A(t-1)(1+r_bot)+dSleeve at exit hour",
            "g2_src": "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl strat R2B1D17BFG2",
            "placebo": f"{N_PBO} draws seed {SEED}, same N per year, forced fill at L, same exits",
            "selection": "dev4 only; 2025-09-24..2026-09-23 scored once for chosen variant only",
        },
        "years": years_out,
        "incomplete": inc_out,
        "placebo": pbo,
        "chosen": chosen,
        "untestable": untestable,
        "five_year_filled": {chosen: n5},
        "overlay": {"G2": base, f"G2+{chosen}_f{SLEEVE_F}": ov,
                    "add_pp_per_month": add},
        "corr_daily_vs_g2_dev4": corr,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1,
                                                  default=str))
    print("wrote results.json; untestable(<10 events in 5y):", untestable)


if __name__ == "__main__":
    main()
