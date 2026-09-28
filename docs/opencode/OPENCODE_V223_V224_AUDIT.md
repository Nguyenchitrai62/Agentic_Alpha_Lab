# v223 + v224 blind audit - foundation component mixes (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v223_v224_audit/` and `tests/test_v223_v224_audit.py`. Use relative
paths without quoting. Do NOT open v223/v223_result.json, v224/v224_result.json or their logs until part A is saved (`replication.json`);
read `v223/build_components.py`, `v223/v223_component_mix.py`, `v224/v224_component_fast.py`.
A: (1) verify that build_components.py re-runs the audited member pipelines unchanged (v144 books_v142 logic, v150 option patches, v202
quarterly wrapper, same anchors/cutoffs) and that the components sum to members_v154 / members_quarterly exactly (you may reuse the
cached components after checking the sums and a spot re-build of one member). (2) With member book = w_lo lo/0.25 + w_ls ls/0.25 + w_fl
fl/0.5 and ensemble 0.5 (A+B)/2 annual + 0.5 (Aq+Bq)/2 quarterly, run your independent v218 D2 trade mode for the mixes of v223
(ref 0.25/0.25/0.5, W1 0.35/0.35/0.30, W2 0.4/0.4/0.2, W3 0.5/0.5/0) and v224 (F1 0.2/0.2/0.6, F2 0.125/0.125/0.75, F3 0/0.3/0.7). Report
dev4, worst first-four monthly, gate DD; robust selection per version; most recent year only for each selected row. Save
`replication.json`. B: compare with the result JSONs (return > 0.01pp/month, DD > 0.05pp). COMPARISON.md with PASS/FAIL. Do not report the
most recent year of non-selected rows. Do not edit leader files.
