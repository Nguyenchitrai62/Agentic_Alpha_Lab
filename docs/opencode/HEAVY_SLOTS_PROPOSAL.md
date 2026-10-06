# Heavy slots proposal (worker `ops_heavyslots`)

Proposed rule: wrap every 4-phase engine job in
`with heavy_slot("<study>", max_slots=2, min_free_gb=2.5, poll=30, timeout_h=6):`
(or `python scripts/heavy_slot.py run --tag <study> -- <cmd...>`);
the leader's own runs pass `leader=True` (CLI `--leader`) to take the reserved
third slot, replacing the ad-hoc per-study PowerShell RAM gates with this one
shared semaphore. (`OPENCODE_VF_COMMON.md` itself is left for the leader to amend.)
