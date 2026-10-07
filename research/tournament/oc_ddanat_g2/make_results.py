"""Assemble results.json from mix_episodes.json + attrib_sN.json (light)."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent

mix = json.loads((HERE / "mix_episodes.json").read_text())
att = {s: json.loads((HERE / f"attrib_s{s}.json").read_text()) for s in range(4)}

episodes = []
for k in range(4):
    mep = mix["reset_episodes"][k]
    per_phase = {}
    for s in range(4):
        per_phase[f"s{s}"] = att[s]["episodes"][k]
    episodes.append(dict(window=[mep["peak"], mep["trough"]],
                         mixed_dd_4h=mep["dd_4h_pct"], mixed_dd_1m=mep["dd_1m_pct"],
                         phases=mep["phases"], per_phase=per_phase))

full_episodes = []
for k, mep in enumerate(mix["full_episodes"]):
    full_episodes.append(dict(window=[mep["peak"], mep["trough"]],
                              mixed_dd_4h=mep["dd_4h_pct"], mixed_dd_1m=mep["dd_1m_pct"],
                              phases=mep["phases"]))

# rule to 15 on the gate episode (mixed 16.91 -> <15 needs >=1.91pp mixed)
sums = {f"s{s}": round(att[s]["episodes"][0]["book_long"]
                       + att[s]["episodes"][0]["book_short"]
                       + att[s]["episodes"][0]["dip"], 3) for s in range(4)}
need_mixed = round(mix["ep_1691"]["dd_1m_pct"] - 15.0, 2)
need_summed = round(need_mixed * 4, 2)

out = dict(
    variant="R2B1D17BFG2",
    gate=dict(yearly_R=[r["R"] for r in mix["yearly"]],
              yearly_DD=[r["DD"] for r in mix["yearly"]],
              full_path_DD=mix["full_path_dd"]),
    ep_1691=mix["ep_1691"],
    reset_episodes=mix["reset_episodes"],
    full_episodes_continuous_mix=mix["full_episodes"],
    episodes=episodes,
    full_episodes=full_episodes,
    replica_checks={f"s{s}": att[s]["checks"] for s in range(4)},
    rule_to_15=dict(
        need_pp_mixed=need_mixed,
        need_pp_summed=need_summed,
        phase_window_sums=sums,
        statement=(f"Cut >= {need_mixed}pp of mixed reset-path equity in the "
                   f"2023-04-17 -> 2023-06-15 window: i.e. remove >= {need_summed}pp summed "
                   "over the four phase windows (~=11% of their -66.9 combined loss, "
                   "e.g. cut ~1/4 of the dip stop+timeout net of TPs or ~1/4 of the "
                   "book-long loss; book shorts already offset +6.8 summed and have "
                   "nothing to cut).")),
    post_hoc_changes=[],
)
(HERE / "results.json").write_text(json.dumps(out, indent=1))
print("wrote results.json")
