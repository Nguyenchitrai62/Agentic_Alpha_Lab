"""oc_bnbvenue: BNB share of the Bybit-vs-Binance drag (DIAGNOSTIC, light).

Reads ONLY published results.json aggregates (no 1m data, no engine runs):
  research/tournament/oc_topbook/results.json
  research/diagnostics/oc_bookvenue/results.json
  research/tournament/oc_venuegap/results.json
  research/tournament/oc_bybittp/results.json
  research/tournament/oc_contrib/results.json
  research/tournament/oc_kpi_g2/results.json
One process, RAM < 1 GB (JSONs total < 5 MB). Writes results.json.
Definitions frozen in PLAN.md.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
T = ROOT / "research" / "tournament"
D = ROOT / "research" / "diagnostics"


def bnb_share_net(bnb_gap: float, total_gap: float) -> float:
    """BNB share of a net gap (can exceed 1 / go negative; caller labels it)."""
    return bnb_gap / total_gap if total_gap != 0 else float("nan")


def monthly_geo(eq_end: float, months: float = 60.0) -> float:
    """Geometric monthly mean from a growth factor over `months` anchor-months."""
    return float(eq_end ** (1.0 / months) - 1.0)


def additive_share(part: float, total: float) -> float:
    return part / total if total != 0 else float("nan")


def scenario_a_illustration(share_net: float, dip_eff_monthly: float) -> float:
    """Proportional illustration ONLY: share of deployment dip_eff scale."""
    return share_net * dip_eff_monthly


def _load(p: Path):
    return json.loads(p.read_text())


def main() -> dict:
    top = _load(T / "oc_topbook" / "results.json")
    bookv = _load(D / "oc_bookvenue" / "results.json")
    venue = _load(T / "oc_venuegap" / "results.json")
    bytp = _load(T / "oc_bybittp" / "results.json")
    contrib = _load(T / "oc_contrib" / "results.json")
    kpi = _load(T / "oc_kpi_g2" / "results.json")

    # 1. Top-of-book spreads per coin
    spreads = {}
    for row in top["venue_spread_comparison"]:
        sym = row["symbol"]
        b, y = row["binance"]["spread_mean"], row["bybit"]["spread_mean"]
        spreads[sym] = {
            "bin_mean_bps": b,
            "byb_mean_bps": y,
            "extra_bps": y - b,
            "ratio": row["bybit_over_binance_mean_ratio"],
        }

    # 2. Dip-leg B1 venue gap (equal-weight rung-y sums)
    pcy = venue["per_coin_year"]
    coins = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    per_coin_5y = {s: round(sum(r["gap"] for r in pcy if r["sym"] == s), 6) for s in coins}
    total_gap = venue["gap_total_sum"]
    assert abs(sum(per_coin_5y.values()) - total_gap) < 0.01, (
        sum(per_coin_5y.values()), total_gap)
    bnb_gap = per_coin_5y["BNBUSDT"]
    share_net = bnb_share_net(bnb_gap, total_gap)
    bnb_yearly = [
        {"year": r["year"], "gap": r["gap"], "n_bin": r["n_bin"], "n_byb": r["n_byb"]}
        for r in pcy if r["sym"] == "BNBUSDT"
    ]
    bnb_pos_years = sum(1 for r in bnb_yearly if r["gap"] > 0)
    # BNB depth cells (bin-byb sums from per_coin_depth venue rows)
    depth_cells = {}
    for k in (2.5, 3.0, 3.5, 4.0, 5.0):
        sb = next(r["sum_ret"] for r in venue["per_coin_depth"]
                  if r["sym"] == "BNBUSDT" and r["k"] == k and r["venue"] == "bin")
        sy = next(r["sum_ret"] for r in venue["per_coin_depth"]
                  if r["sym"] == "BNBUSDT" and r["k"] == k and r["venue"] == "byb")
        depth_cells[str(k)] = {"bin": sb, "byb": sy, "gap": sb - sy}
    byb_rung_pnl = venue["totals"]["byb"]["sum"]
    bin_rung_pnl = venue["totals"]["bin"]["sum"]

    # 3. Divergent-TP context (B1 replica)
    div = bytp["div_counts"]
    single = bytp["single_venue_tp"]

    # 4. Book-leg deployment replay (s=0/s=2, single-phase %/month)
    legs = {}
    for sh in ("0", "2"):
        runs = bookv["shifts"][sh]["runs"]
        base, s5 = runs["base"], runs["s5"]
        bb, bn = runs["book_byb"], runs["book_bin"]
        gap = s5["full"]["monthly"] - base["full"]["monthly"]
        beff = bb["full"]["monthly"] - base["full"]["monthly"]
        deff = bn["full"]["monthly"] - base["full"]["monthly"]
        legs[sh] = {
            "base_m": base["full"]["monthly"],
            "s5_m": s5["full"]["monthly"],
            "gap_m": gap,
            "book_eff_m": beff,
            "dip_eff_m": deff,
            "residual_m": gap - beff - deff,
            "base_dd": base["full"]["dd"],
            "s5_dd": s5["full"]["dd"],
            "book_byb_dd": bb["full"]["dd"],
            "book_bin_dd": bn["full"]["dd"],
            "yearly": [
                {"anchor": a["anchor"],
                 "base": a["monthly"],
                 "s5_minus_base": b["monthly"] - a["monthly"],
                 "book_eff": c["monthly"] - a["monthly"],
                 "dip_eff": d["monthly"] - a["monthly"]}
                for a, b, c, d in zip(base["yearly"], s5["yearly"],
                                      bb["yearly"], bn["yearly"])
            ],
            "book_exec": {
                "base": {k: base["book"][k] for k in
                         ("order_issue", "book_fill", "fill_rate", "book_stop",
                          "book_tp", "book_close", "rung_fill", "rung_tp",
                          "rung_sl", "rung_timeout", "rung_tp_rate")},
                "s5": {k: s5["book"][k] for k in
                       ("order_issue", "book_fill", "fill_rate", "book_stop",
                        "book_tp", "book_close", "rung_fill", "rung_tp",
                        "rung_sl", "rung_timeout", "rung_tp_rate")},
            },
            "fill_rate_diff_pp": (s5["book"]["fill_rate"] - base["book"]["fill_rate"]) * 100.0,
            "tp_shortfall": s5["book"]["rung_tp"] - base["book"]["rung_tp"],
            "fill_shortfall": s5["book"]["rung_fill"] - base["book"]["rung_fill"],
            "stop_excess": s5["book"]["rung_sl"] - base["book"]["rung_sl"],
        }
    diffs = bookv["shifts"]["0"]["diffs"]
    open_shift_bnb = bookv["shifts"]["0"]["open_shift"]["BNBUSDT"]

    # 5. Deployment baseline (G2) + BNB additive share (oc_contrib true-pair)
    full = kpi["equity"]["full_path"]
    r5 = monthly_geo(full["eq_end"], 60.0)
    assert 0.05 < r5 < 0.06, r5  # ~5.6 %/month band guard
    years_r = [{"anchor": y["anchor"], "R": y["R"], "DD": y["DD_reset"]}
               for y in kpi["equity"]["years"]]
    bnb_add = contrib["by_coin"]["pooled"]["BNBUSDT"]["pnl_mix_pct"]
    tot_add = contrib["pooled"]["pnl_mix_pct"]
    assert abs(sum(contrib["by_coin"]["pooled"][s]["pnl_mix_pct"] for s in coins) - tot_add) < 1.0
    assert abs(sum(contrib["by_coin"][str(y)]["BNBUSDT"]["pnl_mix_pct"] for y in range(5)) - bnb_add) < 0.05
    bnb_share_add = additive_share(bnb_add, tot_add)
    bnb_yearly_add = [
        {"anchor": contrib["per_year_entry_totals"][y]["anchor"] if False else
         ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"][y],
         "bnb_mix_pct": contrib["by_coin"][str(y)]["BNBUSDT"]["pnl_mix_pct"],
         "bnb_n": contrib["by_coin"][str(y)]["BNBUSDT"]["n"],
         "bnb_win": contrib["by_coin"][str(y)]["BNBUSDT"]["win"]}
        for y in range(5)
    ]
    book_add = (contrib["by_sleeve"]["pooled"]["book_long"]["pnl_mix_pct"]
                + contrib["by_sleeve"]["pooled"]["book_short"]["pnl_mix_pct"])
    dip_add = contrib["by_sleeve"]["pooled"]["dip"]["pnl_mix_pct"]
    book_share = additive_share(book_add, tot_add)
    # (b) proportional illustration: BNB book/dip split assumed even with sleeve mix
    bnb_book_est = bnb_add * book_share
    bnb_dip_est = bnb_add - bnb_book_est

    # 6. DD episodes: BNB window shares
    dd_bnb = [
        {"peak": e["peak"], "trough": e["trough"],
         "dd_4h": e["dd_4h_pct"], "dd_1m": e["dd_1m_pct"],
         "window_mix": e["window_realized_mix_pct"],
         "bnb_mix": e["by_coin"]["BNBUSDT"]["pnl_mix_pct"],
         "bnb_share": e["by_coin"]["BNBUSDT"]["share_of_window"]}
        for e in contrib["dd_episodes"]
    ]

    # 7. Scenarios (HYPOTHESIS arithmetic only)
    scen_a = {
        sh: {
            "dip_eff_m": legs[sh]["dip_eff_m"],
            "bnb_prop_m": scenario_a_illustration(share_net, legs[sh]["dip_eff_m"]),
            "spread_extra_bps_per_side": spreads["BNBUSDT"]["extra_bps"],
            "note": ("BNB dip share of B1 net gap times deployment dip_eff scale; "
                     "rung-y units are not %/month — illustration only."),
        } for sh in ("0", "2")
    }
    scen = {
        "a_bnb_on_bybit_unchanged": scen_a,
        "a_rungy_context": {
            "bnb_gap_units": bnb_gap,
            "byb_rung_pnl_units": byb_rung_pnl,
            "bnb_over_byb_rungpnl": bnb_gap / byb_rung_pnl,
            "bin_rung_pnl_units": bin_rung_pnl,
        },
        "b_bnb_dip_only_no_bnb_book": {
            "bnb_book_est_mix": bnb_book_est,
            "bnb_dip_est_mix": bnb_dip_est,
            "book_share_of_total": book_share,
            "assumption": ("BNB book/dip split assumed proportional to overall "
                           "sleeve mix; no-assumption bound is 0..bnb_add."),
            "no_assumption_bound_mix": [0.0, bnb_add],
        },
        "c_no_bnb": {
            "drop_mix": bnb_add,
            "share_of_additive": bnb_share_add,
            "illustrative_monthly_haircut_pp": r5 * bnb_share_add * 100.0,
            "yearly_bnb_mix": bnb_yearly_add,
            "note": ("Linear haircut on the geometric mean is order-of-magnitude "
                     "only; no re-simulation, no compounding re-fit."),
        },
    }

    res = {
        "config": {
            "diagnostic": True,
            "selection_rule": "none (diagnostic, no PROMISING rule)",
            "boundary": "market data up to 2026-09-24 00:00 UTC; all five anchor "
                        "years are research data; findings need prospective validation",
            "bookvenue_source": ("research/diagnostics/oc_bookvenue (assignment text "
                                 "cites research/tournament/oc_bookvenue, which does not exist)"),
            "deployment": "R2B1D17BFG2 (oc_kpi_g2; BF neighbour only)",
            "bot_book_ref": "scripts/forward_v205.py research_books_d2 via "
                            "research/diagnostics/r2_decompose5/r2_decompose5.py (reference only, not executed)",
            "resources": "one process, RAM < 1 GB, no 1m data, stdlib json only",
        },
        "topbook_spreads_bps": spreads,
        "dip_leg_b1_replica_rungy": {
            "total_gap_bin_minus_byb": total_gap,
            "per_coin_5y": per_coin_5y,
            "bnb_gap": bnb_gap,
            "bnb_share_of_net_gap": share_net,
            "bnb_yearly": bnb_yearly,
            "bnb_pos_years_of_5": bnb_pos_years,
            "bnb_depth_cells": depth_cells,
            "per_year_gaps": venue["per_year"],
            "unit_note": "equal-weight sums of net rung returns; NOT portfolio %/month",
        },
        "divergent_tp_b1": {
            "div_counts": div,
            "single_venue_tp": single,
            "bnb_bin_only_share": div["BNBUSDT"]["bin_only"] / div["ALL"]["bin_only"],
            "bnb_byb_only_share": div["BNBUSDT"]["byb_only"] / div["ALL"]["byb_only"],
            "totals": bytp["totals"],
        },
        "book_leg_deployment_engine": legs,
        "matched_price_diffs_bps_s0": {
            "order_issue": diffs["s5_vs_base_order_issue"],
            "book_fill": diffs["s5_vs_base_book_fill"],
            "book_stop": diffs["s5_vs_base_book_stop"],
            "book_tp": diffs["s5_vs_base_book_tp"],
        },
        "open_shift_bnb_byb_minus_bin_bps": open_shift_bnb,
        "deployment_g2": {
            "full_path": full,
            "monthly_geo_mean_60m": r5,
            "monthly_geo_mean_60m_pct": r5 * 100.0,
            "per_anchor_R": years_r,
        },
        "bnb_pnl_share_contrib": {
            "bnb_add_mix": bnb_add,
            "tot_add_mix": tot_add,
            "bnb_share_additive": bnb_share_add,
            "bnb_yearly_add": bnb_yearly_add,
            "book_add_mix": book_add,
            "dip_add_mix": dip_add,
            "book_share": book_share,
        },
        "dd_episodes_bnb": dd_bnb,
        "scenarios_hypothesis_only": scen,
        "checks": {
            "venuegap_coins_sum_vs_total": sum(per_coin_5y.values()),
            "contrib_bnb_yearly_sum_vs_pooled": sum(
                contrib["by_coin"][str(y)]["BNBUSDT"]["pnl_mix_pct"] for y in range(5)),
            "topbook_bnb_ratio_band": spreads["BNBUSDT"]["ratio"],
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({
        "bnb_gap": bnb_gap, "total_gap": total_gap, "bnb_share_net": share_net,
        "bnb_pos_years": bnb_pos_years,
        "book_eff_s0": legs["0"]["book_eff_m"], "book_eff_s2": legs["2"]["book_eff_m"],
        "dip_eff_s0": legs["0"]["dip_eff_m"], "dip_eff_s2": legs["2"]["dip_eff_m"],
        "bnb_share_add": bnb_share_add, "R5_pct": r5 * 100.0,
        "bnb_extra_spread_bps": spreads["BNBUSDT"]["extra_bps"],
    }, indent=1))
    return res


if __name__ == "__main__":
    main()
