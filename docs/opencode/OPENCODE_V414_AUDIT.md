# v414 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v414 runs R2B1D17BF (B1 dip size x 1/(1+n), dips x1.7, budget 0.26 x 1.7, bear-regime book longs x0.5; reference
= v411 cache) on the 5-year 4-phase harness (see the version docstrings = pre-registration). Rows R2B1D17BFV1 / V2 multiply the dip size by a BTC DVOL tilt: z90 = (BTC DVOL hourly close at the hour starting T - 2h, T = holding bar start - mean of the trailing 2160 hourly closes) / std (min 720), from research/tournament/oc_dvol/dvol_hourly.parquet; V1 x1.3 if z90 > 0.5, x0.7 if < -0.5; V2 x clip(1 + 0.3 z90, 0.6, 1.4); NaN -> 1.
Part A (blind, before opening the v414 result JSON, run logs or pkls): check the DVOL z90 lookup is causal (truncation test on 10 rows);
reproduce R2B1D17BFV1 on phase 2 and R2B1D17BFV2 on phase 0 with your own wiring; save replication.json. Part B: compare (final equity
relative > 1e-6 = mismatch); recompute rows / folds / finals / full-path DD from the pkls. COMPARISON.md with "## Verdict" per version.
At most 1 heavy process. Write only under `research/parallel/rounds/parallel-20260906-r2/v414_audit/` and `tests/test_v414_audit.py`.
