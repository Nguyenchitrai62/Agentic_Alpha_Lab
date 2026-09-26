# v177 blind audit — Part B comparison

Blind: `replication.json` was saved before opening `v177/`.
Base: v175 audit replication + v176 spec (v176 audit has no saved
`replication.json`), plus the v177 2-fill cap.

## A. Replication vs v177_result.json (exact)

k per anchor: audit 4/4/4/4/4; v177 4.0 everywhere. MATCH.

Primary (`primary_cap2`):

| year | audit net% | v177 net% | audit DD% | v177 DD% |
|---|---|---|---|---|
| 2021-09-24 | 31.61 | 31.61 | 16.96 | 16.96 |
| 2022-09-24 | 35.38 | 35.38 | 15.66 | 15.66 |
| 2023-09-24 | 140.78 | 140.78 | 14.41 | 14.41 |
| 2024-09-24 | 97.70 | 97.70 | 8.85 | 8.85 |
| 2025-09-24 | 86.54 | 86.54 | 11.28 | 11.28 |

monthly 4.71 vs 4.71; full-path DD 21.10 vs 21.10; mean_s 1.606 vs
mean_scale 1.606. fills 2034/2180/2189/2190/2184 (audit) match v177
yearly fills. MATCH on every field.

Sleeve alone per anchor (events MATCH; net/DD differ by documented
scaling only):

| anchor | audit unit net% / DD% / ev | v177 raw net% / DD% / ev |
|---|---|---|
| 2021 | 10.83 / 2.08 / 78 | 18.35 / 3.45 / 78 |
| 2022 | 1.53 / 5.96 / 83 | 2.38 / 9.75 / 83 |
| 2023 | 17.10 / 3.42 / 104 | 29.65 / 5.65 / 104 |
| 2024 | 11.25 / 1.36 / 86 | 19.26 / 2.25 / 86 |
| 2025 | 6.86 / 1.61 / 87 | 11.55 / 2.67 / 87 |

v177 `sleeve_alone` compounds raw capped sleeve `0.25*sum r`; the audit
`sleeve_unit_per_anchor` compounds `sleeve/1.657` (v176 `sleeve_unit`
inside the vol target). Events identical => same capped fill set.
Scaling explains net/DD level differences; direction and ordering agree.

Cap effect (audit, full grid): bars with >2 fills k=2/2.5/3/3.5/4 =
851/497/307/194/128; dropped fills = 1777/995/593/375/242.
k flips vs uncapped v175 (2.5,4,4,3,4) to all-4 under the cap, as v177
reports.

Diagnostics (audit primary row): cost-stress 4.281%/mo, DD 21.52;
1m-marked full-path DD 23.61 (close 21.10) at 2022-11-09 12:00 UTC.

## B. Cap causality check (v177_sleeve_concurrency_cap.py)

`capped_limit_returns`: `lim=o1*(1-k*sig)` (bid from holding-bar open,
as v175); `hit=low<lim` on `low=L[:,16:239,:]`; `fmin=argmax(hit)` =
first fill minute; `key=fmin*10+col`, `rank=argsort(key)`,
`keep=filled & (rank<2)`. Ranking uses only `(fill minute, column
order)` — both known at fill time. A live system knows how many of its
own bids filled so far. No exit price, no future bar, no post-anchor
data enters keep/rank. k is re-chosen by `sleeve_walk_forward` on the
capped `ev`. PASS.

One non-material note: `filled` includes `isfinite(o2)` (exit-bar open
available). The audit caps on fills regardless of exit validity, then
zeros `r` when the exit is missing. Exit-missing bars contribute 0
either way; applied-window event counts match exactly (78/83/104/86/87),
so the difference has no numeric effect here.

## Verdict

REPRODUCED. Primary monthly/yearly/DD/mean_s and capped event sets match
v177 exactly. Cap is causal. v177 note stands: 4.71%/mo, DD 21.10 vs
v176 5.239/20.72 — worse on both; rejected.
