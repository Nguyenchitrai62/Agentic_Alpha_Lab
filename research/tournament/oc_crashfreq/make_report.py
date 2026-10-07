"""Build REPORT.md tables from results.json (deterministic, no recompute)."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
r = json.loads((HERE / "results.json").read_text())
evs = r["events"]

def coins_str(e):
    pc = e["per_coin"]
    parts = sorted(pc.items(), key=lambda kv: kv[1])
    return ", ".join(f"{s.replace('USDT','')} {v:.1f}" for s, v in parts)

def kind_str(e):
    b = e["by_kind"]
    return f"sl {b.get('rung_sl',0):.1f} / tp {b.get('rung_tp',0):.2f} / to {b.get('rung_timeout',0):.2f}"

lines = []
lines.append("# oc_crashfreq REPORT - one-bar dip crashes, all four phases (2026-10-05; PLAN pre-registered)")
lines.append("")
lines.append("## Setup")
lines.append("R2B1D17BF replicas (oc_ddanat4p s0..s3, live 2021-09-24..2026-09-23; "
             "1m/hourly read to 2026-09-24 00:00 UTC; all five years research data, "
             "prospective validation still needed). Per-phase 4h bars "
             "(hour%4==s%4); dip_loss(s,T)=100*sum(weight*ret) over rung exits with "
             "exit_t in (T-4h,T], by exit kind; BTC 4h = hourly C(T-1h)/C(T-5h)-1; "
             "others = wall-clock (T-4h,T] rung sums per other phase. "
             "Repro: research/tournament/oc_crashfreq/{PLAN.md,compute_crashfreq.py,"
             "make_report.py,results.json,REPORT.md}. No post-hoc definition changes.")
lines.append("")
lines.append(f"N>=3% one-bar dip losses: {r['n_events_ge3']} (phase-bars over "
             f"{r['bars_scanned']['s0']} grid bars/phase x4). "
             f"Negative-bar dip sum {r['concentration']['sum_negative_pp']:.1f}pp over "
             f"{r['concentration']['n_negative_bars']} bars; top-10 carry "
             f"{100*r['concentration']['top10_fraction']:.1f}%.")
lines.append("")
lines.append("## Counts per anchor year (>=3 / 5 / 10 / 15% one-bar dip loss, all phases pooled)")
lines.append("| year | >=3% | >=5% | >=10% | >=15% |")
lines.append("|---|---|---|---|---|")
for y in r["yearly_counts"]:
    lines.append(f"| {y['year']} | {y['ge3']} | {y['ge5']} | {y['ge10']} | {y['ge15']} |")
pp = r["per_phase"]
lines.append("")
lines.append(f"Per phase >=3/5/10/15: s0 {pp['s0']['ge3']}/{pp['s0']['ge5']}/{pp['s0']['ge10']}/{pp['s0']['ge15']}; "
             f"s1 {pp['s1']['ge3']}/{pp['s1']['ge5']}/{pp['s1']['ge10']}/{pp['s1']['ge15']}; "
             f"s2 {pp['s2']['ge3']}/{pp['s2']['ge5']}/{pp['s2']['ge10']}/{pp['s2']['ge15']}; "
             f"s3 {pp['s3']['ge3']}/{pp['s3']['ge5']}/{pp['s3']['ge10']}/{pp['s3']['ge15']}.")
lines.append("")
lines.append("## Largest 15 one-bar dip losses")
lines.append("| # | bar_end UTC | s | dip% | stops/exits | sl/tp/to | BTC4h% | others>=3% | coins (pp, worst first) |")
lines.append("|---|---|---|---|---|---|---|---|---|")
for i, e in enumerate(r["top15"], 1):
    others = ",".join(e["others_ge3"]) if e["others_ge3"] else "-"
    lines.append(f"| {i} | {e['bar_end'][:16]} | {e['phase']} | {e['dip_loss']:.2f} | "
                 f"{e['n_stops']}/{e['n_exits']} | {kind_str(e)} | {e['btc_r4h']:.2f} | "
                 f"{others} | {coins_str(e)} |")
lines.append("")
c = r["concentration"]
lines.append("## Concentration")
lines.append(f"Sum over all negative (s,T) bars: {c['sum_negative_pp']:.1f}pp "
             f"({c['n_negative_bars']} bars). Top-10 most-negative bars sum "
             f"{c['top10_sum_pp']:.1f}pp = {100*c['top10_fraction']:.1f}% of all "
             "dip-sleeve losses. Tail is concentrated but not single-event dominated "
             "outside the 2024-01-03 trio (top 3 = -60.2pp, 6.9% of the negative sum).")
lines.append("")
lines.append("## All 82 bars with dip_loss <= -3% (sorted worst first)")
lines.append("| bar_end UTC | s | dip% | stops/exits | sl/tp/to | BTC4h% | others>=3% (wall sums) | coins |")
lines.append("|---|---|---|---|---|---|---|---|")
for e in evs:
    if e["others_ge3"]:
        ow = ",".join(f"{k}:{e['other_wall'][k]:.1f}" for k in e["others_ge3"])
    else:
        mx = max(e["other_wall"].items(), key=lambda kv: kv[1])
        ow = f"- (max {mx[0]}:{mx[1]:.1f})"
    lines.append(f"| {e['bar_end'][:16]} | {e['phase']} | {e['dip_loss']:.2f} | "
                 f"{e['n_stops']}/{e['n_exits']} | {kind_str(e)} | {e['btc_r4h']:.2f} | "
                 f"{ow} | {coins_str(e)} |")
lines.append("")
t = r["type15"]
lines.append("## How often does a 2024-01-03-type event happen?")
lines.append(f"A 2024-01-03-type bar is fixed as dip_loss <= -15% (just below the "
             f"smallest gate-crash bar -17.5%). There are {t['n_bars']} such phase-bars "
             f"in 5 years x4 phases, all on one calendar date {', '.join(t['dates'])} "
             f"(s1 13:00 -17.5%, s2 14:00 -21.7%, s3 15:00 -21.0%; BTC 4h -5.4/-6.2/-6.6%; "
             "18-22 stops each, BTC-led multi-coin). That is "
             f"{t['rate_per_phase_year']:.2f}/phase-year and {t['rate_per_calendar_year']:.1f} "
             "phase-bars per calendar year, i.e. one synchronous triple-crash date in 5 years "
             "(~0.2 dates/year point estimate; Poisson 95% upper ~0.96 dates/year from a single "
             "observed date). For risk planning treat a ~-20% single-bar dip loss on any live "
             "phase, synchronous across phases in the same wall-clock hours, as a once-in-several-years "
             "event that dominates the yearly DD whenever it prints: cap same-bar dip inventory/loss "
             "per phase (e.g. ~-12% circuit-breaker) rather than relying on next-bar cooldowns, wider "
             "stops, or book hedges, which oc_ddanat4p showed cannot touch a same-bar 18-22-stop cascade.")
lines.append("")
lines.append("## Verdict")
lines.append("VERDICT: One-bar dip crashes >=3% hit 82 phase-bars in 5y (7-24/year, 15 fully synchronous across all 4 phases in the same wall hours); the 2024-01-03-type (<=-15%) printed once - three -17/-22/-21% BTC-led multi-coin stop cascades on one date - and the top 10 bars carry 15.9% of all dip-sleeve losses, so risk planning must assume a synchronous ~-20% single-bar dip loss every few years.")
lines.append("")
(HERE / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
print(f"wrote REPORT.md with {len(evs)} events")
