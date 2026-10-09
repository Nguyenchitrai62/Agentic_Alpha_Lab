"""oc_mvrvmech analysis (LIGHT, no engine run): window/year tables, trade tape, budgets.

Reads engine_mech.pkl (heavy, via compute_mech.py) + oc_mvrvrobust/events.json
episodes (frozen). Writes results.json and prints the tables that go into
REPORT.md. Run:

  .venv/Scripts/python.exe research/tournament/oc_mvrvmech/analyze_mech.py
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
MVRV = HERE.parent / "oc_mvrvrobust"

EPISODES = {2: "E2", 3: "E3", 4: "E4"}
MAKER, TAKER = 0.0002, 0.00055


def window_ret_4phase(runs, row, start, end) -> float:
    """4-phase mean equity return over [start, end] (nearest t <= bound)."""
    rs = []
    for s in runs:
        t = pd.to_datetime(pd.Series(runs[s][row]["t"]), utc=True)
        eq = np.asarray(runs[s][row]["eq"], float)
        sv, ev = pd.Timestamp(start).value, pd.Timestamp(end).value
        i0 = int(np.searchsorted(t.values.astype(np.int64), sv) - 1)
        i1 = int(np.searchsorted(t.values.astype(np.int64), ev) - 1)
        i0 = max(i0, 0)
        i1 = max(i1, i0 + 1)
        i1 = min(i1, len(eq) - 1)
        rs.append(float(eq[i1] / eq[i0] - 1.0))
    return float(np.mean(rs))


def pair_book_trades(events, symbols) -> list:
    """Pair trade-mode book events into trades (one position per asset).

    Returns list of dicts: symbol, entry_t/px/w, exit_t/px/kind, adds, parts.
    Trade net (fraction of entry-bar equity, approx): w*(exit/px-1)*side
    - w*(MAKER + exit_fee); exit_fee by kind: stop->TAKER else MAKER.
    Funding ignored at trade level (adverse 0.0001/8h on longs; stated).
    """
    by_sym = {s: [] for s in symbols}
    for e in events:
        if e.get("symbol") in by_sym and e.get("kind", "").startswith(
                ("book_", "order_")):
            by_sym[e["symbol"]].append(e)
    trades = []
    unclosed = 0
    for sym, evs in by_sym.items():
        evs = sorted(evs, key=lambda e: e["t"])
        pos = None
        for e in evs:
            k = e["kind"]
            if k == "book_fill" and pos is None:
                side = 1 if e["side"] == "buy" else -1
                pos = dict(symbol=sym, entry_t=e["t"], entry_px=float(e["price"]),
                           w=abs(float(e["weight"])), side=side, adds=0, parts=0,
                           fee_in=abs(float(e["weight"])) * MAKER)
            elif k == "book_add" and pos is not None:
                # scale-in: new average entry (weight fields are equity fractions)
                w_old, w_new = pos["w"], pos["w"] + abs(float(e["weight"]))
                pos["entry_px"] = ((w_old * pos["entry_px"]
                                    + abs(float(e["weight"])) * float(e["price"])) / w_new)
                pos["w"] = w_new
                pos["adds"] += 1
                pos["fee_in"] += abs(float(e["weight"])) * MAKER
            elif k in ("book_partial", "book_reduce") and pos is not None:
                pos["parts"] += 1
                # partial cash-out at limit (MAKER); shrink open weight
                frac = 0.5  # engine default partial_frac/reduce_frac when not in event
                dq = pos["w"] * frac
                pos.setdefault("cash_out", 0.0)
                pos["cash_out"] += dq * (float(e["price"]) / pos["entry_px"] - 1) * pos["side"] - dq * MAKER
                pos["w"] *= (1 - frac)
            elif k in ("book_stop", "book_tp", "book_close") and pos is not None:
                exit_fee = TAKER if k == "book_stop" else MAKER
                px = float(e["price"])
                ret = pos["side"] * (px / pos["entry_px"] - 1)
                net = pos["w"] * ret - pos["fee_in"] - pos["w"] * exit_fee + pos.get("cash_out", 0.0)
                trades.append({**pos, "exit_t": e["t"], "exit_px": px,
                               "exit_kind": k, "net": float(net),
                               "fee_out": pos["w"] * exit_fee})
                pos = None
        if pos is not None:
            unclosed += 1
    return trades, unclosed


def main():
    runs = pickle.loads((HERE / "engine_mech.pkl").read_bytes())
    ev = json.loads((MVRV / "events.json").read_text())
    episodes = [e for e in ev["episodes"] if e["episode"] in EPISODES]
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

    # --- Task 1: per-episode window returns (4-phase mean) ---
    win_table = []
    for e in episodes:
        s, en = e["start"], e["end"]
        row = dict(ep=f"E{e['episode']}", start=str(pd.Timestamp(s).date()),
                   end=str(pd.Timestamp(en).date()), btc=round(e["btc_ret"], 4))
        for cfg in ("G2_full", "M1_full", "G2_book", "M1_book", "Dip_only"):
            row[cfg] = round(window_ret_4phase(runs, cfg, s, en), 4)
        row["M1-G2_full"] = round(row["M1_full"] - row["G2_full"], 4)
        row["M1-G2_book"] = round(row["M1_book"] - row["G2_book"], 4)
        win_table.append(row)
        print(row, flush=True)

    # --- Task 1b: dip-only identity (single run serves both labels) ---
    for s in runs:
        a = np.asarray(runs[s]["Dip_only"]["eq"], float)
        print(f"shift {s}: Dip_only eq_end {a[-1]:.4f} "
              f"n_ev {runs[s]['Dip_only']['n_events']}", flush=True)

    # --- Task 2: book trade tape inside E2/E3/E4 (BOOKONLY legs) ---
    # Pair on a wide window (entry-60d .. exit+60d) so exits after the edge
    # are kept; attribute by ENTRY time inside the episode; count unclosed.
    tape = {}
    for e in episodes:
        s, en = pd.Timestamp(e["start"]), pd.Timestamp(e["end"])
        ep = f"E{e['episode']}"
        tape[ep] = {}
        for cfg, key in (("G2", "G2_book"), ("M1", "M1_book")):
            per_coin = {}
            all_tr, n_unclosed = [], 0
            for sh in runs:
                lo, hi = s - pd.Timedelta(days=60), en + pd.Timedelta(days=60)
                evs = [x for x in runs[sh][key]["events"]
                       if lo <= pd.Timestamp(x["t"]) <= hi]
                tr, uc = pair_book_trades(evs, symbols)
                n_unclosed += uc
                for t in tr:
                    t["shift"] = sh
                    all_tr.append(t)
            # attribute trades to episode by ENTRY time inside window
            inside = [t for t in all_tr if s <= pd.Timestamp(t["entry_t"]) <= en + pd.Timedelta(hours=8)]
            for sym in symbols:
                st = [t for t in inside if t["symbol"] == sym and t["side"] == 1]
                per_coin[sym] = dict(
                    n_long=len(st),
                    stops=sum(1 for t in st if t["exit_kind"] == "book_stop"),
                    tps=sum(1 for t in st if t["exit_kind"] == "book_tp"),
                    closes=sum(1 for t in st if t["exit_kind"] == "book_close"),
                    net=round(float(sum(t["net"] for t in st)), 5),
                    mean_w=round(float(np.mean([t["w"] for t in st])), 4) if st else 0.0,
                )
            per_coin["_all_long_net"] = round(float(sum(
                t["net"] for t in inside if t["side"] == 1)), 5)
            per_coin["_n_long"] = sum(1 for t in inside if t["side"] == 1)
            per_coin["_n_short"] = sum(1 for t in inside if t["side"] == -1)
            per_coin["_short_net"] = round(float(sum(
                t["net"] for t in inside if t["side"] == -1)), 5)
            per_coin["_unclosed_wide"] = n_unclosed
            # order flow: issues vs fills (min-notional skips) inside window
            iss, fl = 0, 0
            for sh in runs:
                for x in runs[sh][key]["events"]:
                    if s <= pd.Timestamp(x["t"]) <= en and x["kind"] == "order_issue":
                        iss += 1
                    if s <= pd.Timestamp(x["t"]) <= en and x["kind"] == "book_fill":
                        fl += 1
            per_coin["_order_issue"] = iss
            per_coin["_book_fill"] = fl
            tape[ep][cfg] = per_coin
        print(ep, json.dumps({k: v for k, v in tape[ep].items()}, default=str), flush=True)

    # --- Task 2b: budget utilisation in FULL runs per episode ---
    # attrib/book/sleeve sums are linear per-bar equity fractions: report the
    # 4-shift MEAN so they sit on the same scale as the 4-phase mean windows.
    budget = {}
    for e in episodes:
        s, en = pd.Timestamp(e["start"]), pd.Timestamp(e["end"])
        ep = f"E{e['episode']}"
        budget[ep] = {}
        for cfg, key in (("G2", "G2_full"), ("M1", "M1_full"), ("DIP", "Dip_only")):
            gs, tg, rungs, slp, blp, rsize = [], [], 0, 0.0, 0.0, []
            for sh in runs:
                b = runs[sh][key]["bars"]
                bt = pd.to_datetime(pd.Series(b["t"]), utc=True)
                m = (bt >= s) & (bt <= en)
                gs += [x for x, k in zip(b["g"], m) if k]
                tg += [x for x, k in zip(b["abs_tgt"], m) if k]
                a = runs[sh][key]["attrib"]
                at = pd.to_datetime(pd.Series(a["t"]), utc=True)
                m2 = (at >= s) & (at <= en)
                slp += float(sum(x for x, k in zip(a["sleeve"], m2) if k))
                blp += float(sum(x for x, k in zip(a["book"], m2) if k))
                for x in runs[sh][key]["events"]:
                    if x["kind"] == "rung_fill" and s <= pd.Timestamp(x["t"]) <= en:
                        rungs += 1
                        rsize.append(float(x["weight"]))
            nsh = len(runs)
            budget[ep][cfg] = dict(mean_g=round(float(np.mean(gs)), 4),
                                   mean_abs_tgt=round(float(np.mean(tg)), 4),
                                   max_abs_tgt=round(float(np.max(tg)), 4),
                                   dip_rungs=rungs,
                                   mean_rung_w=round(float(np.mean(rsize)), 5) if rsize else 0.0,
                                   book_leg=round(blp / nsh, 4),
                                   sleeve_leg=round(slp / nsh, 4))
        print(ep, budget[ep], flush=True)

    # --- Task 1c: per-year tables (from compute_mech) + per-shift gaps +
    # governor-shutdown fractions (exact, from captured bars) ---
    mech_years = json.loads((HERE / "tmp" / "mech_years.json").read_text())

    def wret(sh, row, s, en):
        t = pd.to_datetime(pd.Series(runs[sh][row]["t"]), utc=True)
        eq = np.asarray(runs[sh][row]["eq"], float)
        i0 = max(int(np.searchsorted(t.values.astype(np.int64),
                                     pd.Timestamp(s).value)) - 1, 0)
        i1 = max(int(np.searchsorted(t.values.astype(np.int64),
                                     pd.Timestamp(en).value)) - 1, i0 + 1)
        i1 = min(i1, len(eq) - 1)
        return float(eq[i1] / eq[i0] - 1.0)

    pershift = {}
    for e in episodes:
        s, en = pd.Timestamp(e["start"]), pd.Timestamp(e["end"])
        ep = f"E{e['episode']}"
        pershift[ep] = []
        for sh in runs:
            gf, mf = wret(sh, "G2_full", s, en), wret(sh, "M1_full", s, en)
            gb, mb = wret(sh, "G2_book", s, en), wret(sh, "M1_book", s, en)
            g0 = {}
            for key in ("G2_full", "M1_full"):
                b = runs[sh][key]["bars"]
                bt = pd.to_datetime(pd.Series(b["t"]), utc=True)
                m = (bt >= s) & (bt <= en)
                gv = [x for x, k in zip(b["g"], m) if k]
                g0[key] = dict(g0frac=round(
                    sum(1 for x in gv if x <= 1e-12) / max(len(gv), 1), 4),
                    meang=round(float(np.mean(gv)), 4))
            pershift[ep].append(dict(
                shift=sh, full_gap=round(mf - gf, 4),
                G2_full=round(gf, 4), M1_full=round(mf, 4),
                book_gap=round(mb - gb, 4),
                G2_book=round(gb, 4), M1_book=round(mb, 4), gov=g0))
        print(ep, json.dumps(pershift[ep]), flush=True)

    out = {"windows": win_table, "tape": tape, "budget": budget,
           "yearly": mech_years,
           "pershift": pershift,
           "note": ("trade net = equity-fraction approx (fees at gate rates, "
                    "adverse long funding not split per trade; engine equity "
                    "is the exact reference). attrib legs are 4-shift means "
                    "of linear per-bar sums (compounding ignored). "
                    "yearly = 4-phase reset metrics from compute_mech.")}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
