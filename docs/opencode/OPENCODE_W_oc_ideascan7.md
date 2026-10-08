# OpenCode task oc_ideascan7 - 6 ideas around WHERE the dip edge lives: post-cascade liquidity provision
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `docs/opencode/IDEAS7_20261008.md`. No code, no engine. Print progress every 10 minutes.

## Evidence to build on (read the rows in docs/CLOSED_DIRECTIONS.md dated 2026-10-08)
oc_cascadedelay (halving dips after a > 4 sigma move loses decisively), oc_cascadeboost (x1.5 for 7 days after: dev4 6.74 vs 5.60, contaminated),
oc_cboostpre (helps 3 of 4 unseen pre-sample years, COVID leg fails), oc_cboostmanual (fails without the BOT's corr-aware sizing and gross cap),
oc_rungquality / oc_netting / oc_partialtp / oc_makerexit (removing or trimming winners fails), the vol-tilt family (helps outside crash legs).
Literature (2024-2026, web search allowed): liquidity provision after liquidation cascades, depth recovery, market-maker inventory after shocks.

## Output (<= 80 lines)
6 ideas about HOW to harvest the post-cascade edge better or more safely (e.g. how the boost decays, which coins / rung depths get it, how the
first cascade of a crash leg differs from later ones, how to avoid levering a crash leg like COVID 2020 with information known at the time),
each with: mechanism, exact causal rule with at most 2 pre-registered variants, data (local or free), harness (dip replica + gate, engine), the
contamination label (anything derived from the cascade results is contaminated for 2021-2026: say which unseen years - pre-sample 2017-2020 via
research/tournament/oc_presampletilt - can test it cleanly), prior, leakage traps. Rank by EV / cost; drop near-duplicates of closed rows.
