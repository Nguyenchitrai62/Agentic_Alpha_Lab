"""Assemble results.json from mix_episodes.json + attrib_sN.json (light)."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent

mix = json.loads((HERE / "mix_episodes.json").read_text())
att = {s: json.loads((HERE / f"attrib_s{s}.json").read_text()) for s in range(4)}

crash_attrib = {}
for s in range(4):
    c = att[s]["crash_window"]
    crash_attrib[f"s{s}"] = c

out = dict(
    variant="R2B1D17BF",
    gate=dict(yearly_R=[2.831, 3.505, 4.669, 11.27, 5.06],
             yearly_DD=[r["DD"] for r in mix["yearly"]],
             full_path_DD=mix["full_path_dd"]),
    ep_1833=mix["ep_1833"],
    reset_episodes=mix["reset_episodes"],
    full_episodes_continuous_mix=mix["full_episodes"],
    crash_attrib=crash_attrib,
    replica_checks={f"s{s}": att[s]["checks"] for s in range(4)},
    rule_to_15=dict(
        need_pp=3.34,
        phase_window_sums={f"s{s}": round(
            att[s]["crash_window"]["book_long"] + att[s]["crash_window"]["book_short"]
            + att[s]["crash_window"]["dip"], 3) for s in range(4)},
        statement=("Cut >=3.34pp of mixed reset-path equity in the 2024-01-03 window: "
                    "i.e. remove >=13.4pp summed over phases 1-3 crash bars "
                    "(~=25% of their -60.2 dip loss, e.g. halve in-crash rung stops net of TPs, "
                    "or cap single-bar dip loss per phase at ~-12/-13%). Book has almost "
                    "nothing to cut (longs -1.5/-1.5/-2.4/-2.3, shorts exactly 0.0).")),
    rejected_levers=dict(
        cooldown_v417C=dict(yearly_DD="18.33->18.45", full_DD="16.9->17.42",
                            note="blocks next-bar fills only; stops cascade within one bar; eats TP offsets"),
        xrp_stop_v417X=dict(yearly_DD="18.33->18.37", full_DD="16.9->16.89",
                            note="XRP is ~1/5 of crash dip loss; -10% flash blows through 5.5 sigma"),
        bear_book_BF=dict(note="already IN the gate number; crash-bar shorts 0.0, longs already halved yet -1.5..-2.4; zeroing longs saves ~2pp of 18.33"),
        wider_stop_v388=dict(note="wider close-stops hold losers longer into a flash exceeding 5.5-6 sigma; wrong direction for a one-bar cascade"),
        governor_v110_v141=dict(note="g keys off 90-day own-equity DD with 2-bar lag; pre-crash DD~0 so g=1 at the crash bar; can only de-risk after the first -20% bar")),
    post_hoc_changes=[
        "close_trough extension + reset-chained path added after seeing the max-DD pair is a 1-hour mark artifact (mixed closes flat 11:00->12:00); logged here.",
        "crash attribution window uses (peak, close_trough]=(11:00,16:00] bar-ends instead of PLAN's (peak,trough_1h]; the 1h window contains no crash-bar close.",
    ],
)
(HERE / "results.json").write_text(json.dumps(out, indent=1))
print("wrote results.json")
