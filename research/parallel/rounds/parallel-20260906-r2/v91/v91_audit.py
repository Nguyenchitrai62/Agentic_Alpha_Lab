"""v91 worker: 3-book portfolio execution audit, hidden year 2025-09-24..2026-09-23.

Parameters frozen as of 2025-09-14: re-runs the portfolio_freeze selection code
with anchor 2025-09-24 (10-day embargo). Does NOT use portfolio_v1.json params
(which were fitted to 2026-09); that file is read only to record the policy it
implies (allocation thirds, trend 1.5x, carry 3x).

Books: (1) BTC regime_scaled 4h, (2) majors TSMOM 4h per-asset Sharpe selection
+ portfolio DD scale K, (3) majors funding carry per-asset Sharpe selection.
Target weights per 4h bar for BTC/ETH/SOL/BNB/XRP (perp + spot fractions).

Execution: every weight change is executed on real 1m bars. Limit at the 4h
open price; filled only if a LATER 1m bar trades THROUGH it within 15 minutes
(maker fee), else market at minute-15 open with taker fee + slippage. Spot legs
use the same rule on spot 4h opens with the fill test on perp 1m bars as proxy.
Actual funding (both signs) on perp legs.

Vectorized baseline: same weights, fills at the 4h open, same fees, actual
funding -- isolates the execution-model gap.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import agentic_alpha_lab.research_vf as V
from agentic_alpha_lab.backtest.ma_ribbon import funding_per_bar
from agentic_alpha_lab.backtest.portfolio import position_backtest, summarize_curve
from agentic_alpha_lab.oos_streams import context as oos_context
from agentic_alpha_lab.vf_families import FAMILIES
import carry_lab as C

from v91_lib import ALLOC, CAP, CARRY_LEV, TREND_LEV, book_weights, limit_filled

OUT = Path(__file__).parent
ANCHOR = "2025-09-24"
HIDE_START = pd.Timestamp("2025-09-24", tz="UTC")
HIDE_END = pd.Timestamp("2026-09-23", tz="UTC")  # inclusive date; last bar opens 20:00
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")

SCENARIOS = {
    "normal": dict(maker=0.0002, taker=0.0005, slip=0.0002, window_min=15),
    "fee_stress": dict(maker=0.0006, taker=0.0006, slip=0.0005, window_min=15),
    "execution_stress": dict(maker=0.0006, taker=0.0006, slip=0.0005, window_min=5),
}


def select_params():
    # --- book 1: BTC regime_scaled on extended history ---
    ctx_btc = V.load_context_extended("4h")
    fn_r, grid_r = FAMILIES["regime_scaled"]
    r = V.run(ctx_btc, fn_r, grid_r, anchors=(ANCHOR,), select_years=None)["per_anchor"][0]
    assert r["selected"] is not None, "regime selection failed"
    regime_params, regime_scale = r["selected"], r["scale"]
    # --- book 2: per-asset TSMOM Sharpe selection + portfolio K ---
    fn_t, grid_t = FAMILIES["tsmom"]
    ts_params, sel_curves = {}, {}
    for s in MAJORS:
        c = oos_context(s, "4h")
        w = V.windows(c, ANCHOR, None)
        best, score = None, -np.inf
        for p in grid_t:
            st = summarize_curve(position_backtest(
                c.bars, fn_t(c, p, fit_end=w["sel"][1]), *w["sel"], V.NORMAL, c.fr, c.fc))
            if st["changes"] >= 10 and st["sharpe"] > score:
                best, score = p, st["sharpe"]
        assert best is not None, f"tsmom selection failed for {s}"
        ts_params[s] = best
        res = position_backtest(c.bars, fn_t(c, best, fit_end=w["sel"][1]),
                                *w["sel"], V.NORMAL, c.fr, c.fc)
        sel_curves[s] = res["curve"]["equity"] / 100.0
    idx = sorted(set().union(*[c.index for c in sel_curves.values()]))
    pr = pd.DataFrame({s: c.reindex(idx).ffill().pct_change().fillna(0.0)
                       for s, c in sel_curves.items()}).mean(axis=1)
    eq = (1 + pr).cumprod()
    dd = float(np.max(1 - eq / eq.cummax()))
    K = float(np.floor(min(2.0, 0.20 / max(dd, 1e-6)) * 20) / 20)
    # --- book 3: per-asset carry Sharpe selection (fee 0.0004) ---
    a = pd.Timestamp(ANCHOR, tz="UTC")
    carry_params = {}
    for s in MAJORS:
        d = C.load(s)
        s0, s1 = d["idx"][0] + pd.Timedelta(days=30), a - pd.Timedelta(days=V.EMBARGO_DAYS)

        def score(q):
            rr = C.returns(d, C.position(d, q), 0.0004)
            rr = rr[(rr.index >= s0) & (rr.index <= s1)]
            return rr.mean() / rr.std() if rr.std() > 0 else -9

        carry_params[s] = max(C.GRID, key=score)
    # record what portfolio_v1.json implies (policy only, not its fitted params)
    frozen = json.loads((ROOT / "artifacts/research/advisor_shadow/portfolio_v1.json").read_text())
    sel = dict(anchor=ANCHOR, embargo_days=V.EMBARGO_DAYS,
               allocation=dict(regime_btc=ALLOC, tsmom_majors=ALLOC, carry=ALLOC),
               trend_leverage=TREND_LEV, carry_leverage=CARRY_LEV,
               regime_btc=dict(params=regime_params, scale=regime_scale),
               tsmom_majors=dict(params={s: {k: (list(v) if isinstance(v, tuple) else v)
                                             for k, v in p.items()} for s, p in ts_params.items()},
                                 K=K),
               carry=carry_params,
               policy_reference=dict(portfolio_v1_anchor=frozen.get("anchor"),
                                     portfolio_v1_note="NOT USED for params; allocation/leverage policy only"))
    return sel


def _params(p):
    return {k: (tuple(v) if isinstance(v, list) else v) for k, v in p.items()}


def _align(master, series):
    """Vectorized ffill-align of a signal series onto master open_times."""
    s = series.sort_index()
    idx = s.index.searchsorted(master, side="right") - 1
    vals = np.where(idx >= 0, s.to_numpy()[np.clip(idx, 0, len(s) - 1)], np.nan)
    vals = np.where(idx >= 0, vals, 0.0)
    return np.nan_to_num(vals.astype(float), nan=0.0)


def build_hidden_weights(sel):
    """Target perp/spot weights per hidden 4h bar (decision at close[t])."""
    # master hidden 4h index from BTC XS perp bars
    btc = pd.read_parquet(ROOT / "data/raw/xs_universe_20260924/BTCUSDT_4h.parquet")
    btc["open_time"] = pd.to_datetime(btc["open_time"], utc=True)
    btc["close_time"] = pd.to_datetime(btc["close_time"], utc=True)
    hid = btc[(btc["open_time"] >= HIDE_START) & (btc["open_time"] < HIDE_END + pd.Timedelta(days=1))]
    hid = hid.sort_values("open_time").reset_index(drop=True)
    master = hid["open_time"]
    n = len(hid)
    assert n == 2190, f"expected 2190 hidden 4h bars, got {n}"
    # signals per symbol mapped onto master
    ctx_btc = V.load_context_extended("4h")
    fn_r, _ = FAMILIES["regime_scaled"]
    rs_full = np.asarray(fn_r(ctx_btc, _params(sel["regime_btc"]["params"]),
                              fit_end=None), dtype=float)
    rs_map = pd.Series(rs_full, index=pd.to_datetime(ctx_btc.bars["open_time"], utc=True))
    fn_t, _ = FAMILIES["tsmom"]
    ts_map, carry_map = {}, {}
    for s in MAJORS:
        c = oos_context(s, "4h")
        ts_full = np.asarray(fn_t(c, _params(sel["tsmom_majors"]["params"][s]), fit_end=None), dtype=float)
        ts_map[s] = pd.Series(ts_full, index=pd.to_datetime(c.bars["open_time"], utc=True))
        d = C.load(s)
        pos = C.position(d, sel["carry"][s])
        carry_map[s] = pos
    K, scale = sel["tsmom_majors"]["K"], sel["regime_btc"]["scale"]
    rs_v = _align(master, rs_map)
    ts_v = {s: _align(master, ts_map[s]) for s in MAJORS}
    co_v = {s: _align(master, carry_map[s].astype(float)) for s in MAJORS}
    rows = []
    for t in range(n):
        row = {}
        for s in MAJORS:
            rs = rs_v[t] if s == "BTCUSDT" else 0.0
            pw, sw = book_weights(rs, ts_v[s][t], co_v[s][t], K, scale, s == "BTCUSDT")
            row[f"perp_{s}"] = pw
            row[f"spot_{s}"] = sw
        rows.append(row)
    w = pd.DataFrame(rows)
    w.insert(0, "open_time", master.to_numpy())
    for s in MAJORS:
        w[f"book_tsmom_perp_{s}"] = ALLOC * TREND_LEV * K * ts_v[s] / 5
        notion = ALLOC * CARRY_LEV * co_v[s] / 5 / CAP
        w[f"book_carry_perp_{s}"] = -notion
        w[f"book_carry_spot_{s}"] = notion
    w["book_regime_perp_BTCUSDT"] = ALLOC * TREND_LEV * rs_v * scale
    return hid.reset_index(drop=True), w


def load_price_block(hid):
    perp_o, perp_c, spot_o, spot_c, frate = {}, {}, {}, {}, {}
    for s in MAJORS:
        b = pd.read_parquet(ROOT / f"data/raw/xs_universe_20260924/{s}_4h.parquet")
        b["open_time"] = pd.to_datetime(b["open_time"], utc=True)
        b = b.set_index("open_time").reindex(hid["open_time"])
        assert b[["open", "close"]].notna().all().all(), f"perp gap {s}"
        perp_o[s] = b["open"].to_numpy(float)
        perp_c[s] = b["close"].to_numpy(float)
        f = pd.read_parquet(ROOT / f"data/raw/xs_universe_20260924/{s}_funding.parquet")
        f["fundingTime"] = pd.to_datetime(f["fundingTime"], utc=True)
        full_b = pd.read_parquet(ROOT / f"data/raw/xs_universe_20260924/{s}_4h.parquet")
        full_b["open_time"] = pd.to_datetime(full_b["open_time"], utc=True)
        fr_full, _ = funding_per_bar(full_b, f)
        # slice hidden window by open_time match
        full_ot = full_b["open_time"].to_numpy()
        hid_ot = hid["open_time"].to_numpy()
        j = np.searchsorted(full_ot.astype("datetime64[ns]"), hid_ot.astype("datetime64[ns]"))
        frate[s] = fr_full[j]
        sp = pd.read_parquet(ROOT / f"data/raw/spot_majors_20260925/{s}_spot_4h.parquet")
        sp["open_time"] = pd.to_datetime(sp["open_time"], utc=True)
        sp = sp.set_index("open_time").reindex(hid["open_time"])
        assert sp[["open", "close"]].notna().all().all(), f"spot gap {s}"
        spot_o[s] = sp["open"].to_numpy(float)
        spot_c[s] = sp["close"].to_numpy(float)
    return perp_o, perp_c, spot_o, spot_c, frate


def load_1m():
    bars1m = {}
    for s in MAJORS:
        if s == "BTCUSDT":
            files = [ROOT / f"data/raw/btc_intraday_20260924/klines_1m_{y}.parquet" for y in (2025, 2026)]
        else:
            files = [ROOT / f"data/raw/majors_intraday_20260924/{s}_1m_{y}.parquet" for y in (2025, 2026)]
        df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
        df = df[(df["open_time"] >= HIDE_START) & (df["open_time"] < HIDE_END + pd.Timedelta(days=2))]
        df = df.sort_values("open_time").reset_index(drop=True)
        bars1m[s] = df
    return bars1m


def run_portfolio(hid, w, perp_o, perp_c, spot_o, spot_c, frate, bars1m, mode, scen):
    """Joint multi-asset simulation. mode: 'vectorized' or 'execution'."""
    n = len(hid)
    legs = [f"perp_{s}" for s in MAJORS] + [f"spot_{s}" for s in MAJORS]
    targets = {leg: w[leg].to_numpy(float) for leg in legs}
    opens = {f"perp_{s}": perp_o[s] for s in MAJORS} | {f"spot_{s}": spot_o[s] for s in MAJORS}
    closes = {f"perp_{s}": perp_c[s] for s in MAJORS} | {f"spot_{s}": spot_c[s] for s in MAJORS}
    # 1m lookup arrays (+ precomputed 4h->1m positions to avoid per-fill searchsorted)
    m1 = {}
    j0map = {}
    if mode == "execution":
        hid_ns = hid["open_time"].to_numpy().astype("datetime64[ns]")
        for s in MAJORS:
            df = bars1m[s]
            ot = df["open_time"].to_numpy().astype("datetime64[ns]")
            m1[s] = (ot, df["open"].to_numpy(float),
                     df["high"].to_numpy(float), df["low"].to_numpy(float))
            j0map[s] = np.searchsorted(ot, hid_ns)
    cash, q = 100.0, {leg: 0.0 for leg in legs}
    held = {leg: 0.0 for leg in legs}
    fees = fund = turnover = 0.0
    n_orders = n_limit = n_market = 0
    eq_marks = []
    tol = 1e-9
    for i in range(1, n):
        eq_open = cash + sum(q[leg] * opens[leg][i] for leg in legs)
        for leg in legs:
            desired = float(targets[leg][i - 1])
            if abs(desired - held[leg]) <= tol:
                continue
            sym = leg.split("_", 1)[1]
            new_q = desired * eq_open / opens[leg][i]
            dq = new_q - q[leg]
            if abs(dq) * opens[leg][i] < 1e-9:
                held[leg] = desired
                q[leg] = new_q
                continue
            side = 1 if dq > 0 else -1
            n_orders += 1
            if mode == "vectorized":
                px = opens[leg][i]
                fee = scen["maker"] * abs(dq) * px
                cash -= dq * px + fee
            else:
                limit_px = opens[leg][i]
                ot, oo, oh, ol = m1[sym]
                j0 = int(j0map[sym][i])
                # strictly later 1m bars within window
                j1, j2 = j0 + 1, j0 + 1 + scen["window_min"]
                wh, wl = oh[j1:j2], ol[j1:j2]
                if limit_filled(side, limit_px, wh, wl):
                    px = limit_px
                    fee = scen["maker"] * abs(dq) * px
                    cash -= dq * px + fee
                    n_limit += 1
                else:
                    px15 = float(oo[min(j0 + scen["window_min"], len(oo) - 1)])
                    px = px15 * (1 + scen["slip"] * side)
                    fee = scen["taker"] * abs(dq) * px
                    cash -= dq * px + fee
                    n_market += 1
            fees += fee
            turnover += abs(dq) * px
            q[leg], held[leg] = new_q, desired
        # actual funding on perp legs (both signs) over bar i
        for s in MAJORS:
            leg = f"perp_{s}"
            if q[leg] != 0:
                paid = frate[s][i] * q[leg] * perp_c[s][i]
                cash -= paid
                fund += paid
        eq_marks.append(cash + sum(q[leg] * closes[leg][i] for leg in legs))
    # liquidate at last hidden close
    eq_last_open = cash + sum(q[leg] * opens[leg][n - 1] for leg in legs)
    for leg in legs:
        if abs(q[leg]) > 0:
            px = closes[leg][n - 1]
            fee = scen["maker"] * abs(q[leg]) * px
            cash += q[leg] * px - fee
            fees += fee
            turnover += abs(q[leg]) * px
            n_orders += 1  # closing fills
            q[leg] = 0.0
    eq_marks[-1] = cash
    eq = np.array(eq_marks)
    peaks = np.maximum.accumulate(np.concatenate([[100.0], eq]))[1:]
    dd = float(np.max(1 - eq / peaks))
    growth = cash / 100.0
    days = max((hid["close_time"].iloc[-1] - hid["close_time"].iloc[1]).total_seconds() / 86400, 1.0)
    monthly = float(growth ** (30.4375 / days) - 1) if growth > 0 else -1.0
    expo = np.abs(w[[f"perp_{s}" for s in MAJORS] + [f"spot_{s}" for s in MAJORS]].to_numpy()).sum(axis=1)
    return dict(equity=round(cash, 4), net_pct=round(100 * (growth - 1), 4),
                monthly_geo_pct=round(100 * monthly, 4), dd_close_pct=round(100 * dd, 4),
                gross=round(cash - 100 + fees + fund, 4), fees=round(fees, 4), funding=round(fund, 4),
                turnover_x=round(turnover / 100, 4), fills=int(n_orders),
                limit_fills=int(n_limit), market_fills=int(n_market),
                fill_rate=round(n_limit / max(n_orders, 1), 4) if mode == "execution" else 1.0,
                coverage=round(float(np.mean(expo[1:] > 1e-9)), 4), days=round(float(days), 2),
                months=round(float(days / 30.4375), 2))


def book_vectorized(hid, w, perp_o, perp_c, spot_o, spot_c, frate):
    books = {}
    scen = SCENARIOS["normal"]
    for book, legmap in (
            ("regime_btc", {"perp_BTCUSDT": "book_regime_perp_BTCUSDT"}),
            ("tsmom_majors", {f"perp_{s}": f"book_tsmom_perp_{s}" for s in MAJORS}),
            ("carry", {f"perp_{s}": f"book_carry_perp_{s}" for s in MAJORS} |
                      {f"spot_{s}": f"book_carry_spot_{s}" for s in MAJORS})):
        full = pd.DataFrame({f"perp_{s}": np.zeros(len(hid)) for s in MAJORS} |
                            {f"spot_{s}": np.zeros(len(hid)) for s in MAJORS})
        for leg, col in legmap.items():
            full[leg] = w[col].to_numpy(float)
        books[book] = run_portfolio(hid, full, perp_o, perp_c, spot_o, spot_c, frate,
                                    None, "vectorized", scen)
    return books


def main():
    if (OUT / "selection.json").exists() and "--reselect" not in sys.argv:
        sel = json.loads((OUT / "selection.json").read_text())
        print("resume: loaded selection.json (anchor", sel.get("anchor"), ")")
    else:
        sel = select_params()
        (OUT / "selection.json").write_text(json.dumps(sel, indent=1, default=str))
    hid, w = build_hidden_weights(sel)
    w_out = pd.DataFrame({"open_time": hid["open_time"]})
    for s in MAJORS:
        w_out[f"perp_{s}"] = w[f"perp_{s}"]
        w_out[f"spot_{s}"] = w[f"spot_{s}"]
    w_out.to_csv(OUT / "weights_4h.csv", index=False)
    perp_o, perp_c, spot_o, spot_c, frate = load_price_block(hid)
    bars1m = load_1m()
    vec = {name: run_portfolio(hid, w_out, perp_o, perp_c, spot_o, spot_c, frate,
                               None, "vectorized", scen)
           for name, scen in SCENARIOS.items()}
    exe = {name: run_portfolio(hid, w_out, perp_o, perp_c, spot_o, spot_c, frate,
                               bars1m, "execution", scen)
           for name, scen in SCENARIOS.items()}
    books = book_vectorized(hid, w, perp_o, perp_c, spot_o, spot_c, frate)
    res = dict(vectorized=vec, execution=exe, per_book_vectorized=books,
               costs=dict(note="vectorized fills at 4h open with scenario maker fee; "
                               "execution uses 1m limit-through-15min else minute-15 market; "
                               "actual funding both signs on perp legs; spot fill test on perp 1m as proxy",
                          scenarios={k: dict(maker=v["maker"], taker=v["taker"],
                                             slippage=v["slip"], window_min=v["window_min"])
                                     for k, v in SCENARIOS.items()}),
               selection_anchor=ANCHOR, hidden="2025-09-24..2026-09-23", bars=len(hid),
               months=vec["normal"]["months"])
    (OUT / "backtest_results.json").write_text(json.dumps(res, indent=1))
    # SUMMARY.md (<=15 lines per VF common guidance; keep tight)
    e = exe["normal"]
    v = vec["normal"]
    lines = [
        "# v91 3-book portfolio execution audit (hidden year 2025-09-24..2026-09-23)",
        f"Params frozen as of 2025-09-14 (anchor 2025-09-24; portfolio_v1.json NOT used for params).",
        f"Selection: regime {sel['regime_btc']['params']} x{sel['regime_btc']['scale']}; "
        f"tsmom K={sel['tsmom_majors']['K']}; carry {[sel['carry'][s]['win'] for s in MAJORS]}.",
        f"Vectorized normal: net {v['net_pct']}% (~{v['monthly_geo_pct']}%/mo), DD {v['dd_close_pct']}%, "
        f"fees {v['fees']}, funding {v['funding']}, turnover {v['turnover_x']}x, fills {v['fills']}.",
        f"Execution normal: net {e['net_pct']}% (~{e['monthly_geo_pct']}%/mo), DD {e['dd_close_pct']}%, "
        f"fees {e['fees']}, funding {e['funding']}, turnover {e['turnover_x']}x, fills {e['fills']}, "
        f"limit {e['limit_fills']}/{e['fills']} (rate {e['fill_rate']}).",
        f"Fee-stress exec: net {exe['fee_stress']['net_pct']}% (~{exe['fee_stress']['monthly_geo_pct']}%/mo), "
        f"DD {exe['fee_stress']['dd_close_pct']}%, fills {exe['fee_stress']['fills']}.",
        f"Execution-stress (5-min window): net {exe['execution_stress']['net_pct']}% "
        f"(~{exe['execution_stress']['monthly_geo_pct']}%/mo), DD {exe['execution_stress']['dd_close_pct']}%, "
        f"fills {exe['execution_stress']['fills']}, rate {exe['execution_stress']['fill_rate']}.",
        f"Per-book vectorized net: regime {books['regime_btc']['net_pct']}%, "
        f"tsmom {books['tsmom_majors']['net_pct']}%, carry {books['carry']['net_pct']}% (standalone, don't sum).",
        f"Costs: maker/taker/slip normal {SCENARIOS['normal']}; actual funding both signs; spot proxy = perp 1m.",
        f"Rows: {len(hid)} 4h bars; months {e['months']}; coverage {e['coverage']}; "
        f"vs ~4-8 bps round-trip cost: see monthly gaps above.",
        f"Worker self-report; awaiting leader audit. Files: weights_4h.csv, backtest_results.json, selection.json.",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    # result_manifest.json: assignment fields + schema-compatible extras
    manifest = dict(
        schema_version=1, experiment_id="v91", track="C", status="audited",
        parent_commit="1ecf947baddd5ef78444670330e9db62128dad50",
        hypothesis=("The 3-book majors portfolio with 2025-09-14-frozen params keeps its "
                    "edge net of realistic 1m limit/market execution and actual funding."),
        hashes=dict(data=dict(hidden="2025-09-24..2026-09-23",
                             intraday_1m=["btc_intraday_20260924", "majors_intraday_20260924"],
                              spot="spot_majors_20260925", universe="xs_universe_20260924"),
                    config=dict(selection="research/parallel/rounds/parallel-20260906-r2/v91/selection.json"),
                    code=dict(lib="v91_lib.py", audit="v91_audit.py")),
        chronology=dict(fold_type="hidden-year", embargo_days=10,
                        decision_start="2025-09-24", decision_end="2026-09-23",
                        anchor=ANCHOR, months=e["months"], bars=len(hid)),
        scenarios={name: dict(gross_pnl=exe[name]["gross"], fees=exe[name]["fees"],
                              funding=exe[name]["funding"], net_pnl=exe[name]["net_pct"],
                              max_drawdown_percent=exe[name]["dd_close_pct"], fills=exe[name]["fills"],
                              coverage_percent=round(100 * exe[name]["coverage"], 4),
                              monthly_geometric_return_percent=exe[name]["monthly_geo_pct"],
                              monthly_geometric_net_percent=exe[name]["monthly_geo_pct"],
                              months=exe[name]["months"]) for name in SCENARIOS},
        vectorized_baseline={name: dict(net_pnl=vec[name]["net_pct"],
                                        monthly_geometric_net_percent=vec[name]["monthly_geo_pct"],
                                        max_drawdown_percent=vec[name]["dd_close_pct"],
                                        fills=vec[name]["fills"]) for name in SCENARIOS},
        per_book_vectorized={b: dict(net_pnl=books[b]["net_pct"],
                                     monthly_geometric_net_percent=books[b]["monthly_geo_pct"],
                                     max_drawdown_percent=books[b]["dd_close_pct"],
                                     fills=books[b]["fills"]) for b in books},
        independent_test=False, live_approved=False,
        audit=dict(passed=False, replay_complete=False,
                   notes="worker self-report; awaiting leader audit"))
    (OUT / "result_manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps({k: exe[k] for k in exe}, indent=1))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
