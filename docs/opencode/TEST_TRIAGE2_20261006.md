# Test triage 2, 2026-10-06 (ops_testtriage2)

Helper: `scripts/test_triage.py` (patched this task, see Fix). Method per file:
sequential `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag triage
--min-free-gb 1.5 -- .venv/Scripts/python.exe -m pytest -q -x -v <file>`
(300 s pytest bound, BELOW_NORMAL priority on the outer process, inner inherits;
outer timeout = slot wait 6 h + 300 s). RAM pre-gate 1.5 GB (was 2.0).
Raw JSON/logs in temp dir (`triage2_20261006.json/log`, `triage2_20261006_p2.json`
LOST — killed at the 100-min stop before the final write; `scan2_20261006.json`),
not in git. Classes as in triage 1. No commits, no deletions, no other files touched.

## Fix to scripts/test_triage.py (only repo file touched)

- `LOW_RAM_BYTES` 2.0 -> 1.5 GB to match the assigned wrapper (old gate would
  defer at 1.5–2.0 GB without ever reaching the wrapper; smoke run proved it:
  `test_oc_tsmom` ran at 1.84 GB free).
- `run_one` wraps pytest with the exact assigned heavy_slot CLI; BELOW_NORMAL
  set on the outer process. Slot-acquire line appears in `tail` (`[heavy_slot:triage]
  acquired slot_N`), verdict parsing unchanged (verified: smoke `test_oc_tsmom`
  5 passed -> COMMIT).

## Sweep 1 (full, JSON saved): 183-file snapshot — 76 COMMIT / 0 COMMIT-WITH-SKIP / 2 STALE / 1 DROP-CANDIDATE / 104 DEFERRED

First pass ran 31 files (up to `test_oc_bookvol`), then free RAM fell below
1.5 GB and the rest deferred. After the 600 s retry wait, 48 more ran
(`test_oc_bookweekend`..`test_oc_ethbtc` plus `test_oc_eventblk`), then RAM
dropped again and 104 stayed `deferred-low-ram`. Sum of executed runtimes 2018 s.

## Exact `git add` list for COMMIT rows (76 verified passes, sweep 1)

```sh
git add tests/test_bot_parity.py tests/test_carry_audit.py tests/test_diag_20261005_audit.py tests/test_freeze_d17bf.py tests/test_oc_adaptsig.py tests/test_oc_agentskip.py tests/test_oc_b1btc.py tests/test_oc_b1deeper.py tests/test_oc_b1soft.py tests/test_oc_b1wide.py tests/test_oc_basisbook.py tests/test_oc_bearshort.py tests/test_oc_beartp.py tests/test_oc_bidttl.py tests/test_oc_blendsens.py tests/test_oc_bnbvenue.py tests/test_oc_bookbrake.py tests/test_oc_bookcoinbrake.py tests/test_oc_bookcoinwf.py tests/test_oc_bookcorr.py tests/test_oc_bookdipnet.py tests/test_oc_bookevent.py tests/test_oc_bookexit.py tests/test_oc_bookfunding.py tests/test_oc_bookholdcap.py tests/test_oc_bookoffset.py tests/test_oc_bookthresh.py tests/test_oc_bookvenue.py tests/test_oc_bookvol.py tests/test_oc_bookweekend.py tests/test_oc_breadthbook.py tests/test_oc_breadthdip.py tests/test_oc_btclead.py tests/test_oc_bullbook.py tests/test_oc_bullshort.py tests/test_oc_bybittp.py tests/test_oc_c2ic.py tests/test_oc_cadence.py tests/test_oc_capscale.py tests/test_oc_carrycombo.py tests/test_oc_carryd13.py tests/test_oc_carryfar.py tests/test_oc_carryfric.py tests/test_oc_carrytopup.py tests/test_oc_cashcarry.py tests/test_oc_cbpremium.py tests/test_oc_clockanat.py tests/test_oc_clockluck.py tests/test_oc_cmegap.py tests/test_oc_cmegap4p.py tests/test_oc_coinbear.py tests/test_oc_coinwf.py tests/test_oc_condhold.py tests/test_oc_contrib.py tests/test_oc_cooldown.py tests/test_oc_corrbudget.py tests/test_oc_crash2020.py tests/test_oc_crashfreq.py tests/test_oc_d13robust.py tests/test_oc_dailyladder.py tests/test_oc_ddanat17.py tests/test_oc_ddanat4p.py tests/test_oc_ddanat_g2.py tests/test_oc_deepcheck.py tests/test_oc_deeptp.py tests/test_oc_depthregime.py tests/test_oc_depthtilt.py tests/test_oc_dipbe.py tests/test_oc_diptilt.py tests/test_oc_discsniper.py tests/test_oc_dombook.py tests/test_oc_dvolbook.py tests/test_oc_dvolshort.py tests/test_oc_earlystart.py tests/test_oc_edgedecay.py tests/test_oc_ethbtc.py
```

Prior verified trio (`test_bot_parity`, `test_tournament_oc_kpi`,
`test_oc_tsmom`) re-confirmed inside this sweep where run (`test_bot_parity`
pass; `test_oc_tsmom` pass in smoke; `test_tournament_oc_kpi` still DEFERRED).

## STALE failures with error line

- `tests/test_bot_maint.py` (STALE, no deps): triage run `1 failed, 3 passed`,
  `FAILED test_active_window_blocks_new_entries_and_cancels_resting`. NOTE:
  standalone rerun after the sweep: **8 passed** — file likely mutated under
  concurrent workers (or flaky); leader should rerun before dropping.
- `tests/test_oc_bookmodel_reaudit.py::test_kpack_bundles_clean_and_in_sync`
  (STALE; deps tracked/exist): `tests\test_oc_bookmodel_reaudit.py:133:
  AssertionError: ('kpack_C1', 'c1_pooled_tvflow.py')` (impl/kpack out of sync).
- Pass-3 extras (observed, JSON lost — confirm with one rerun each):
  `tests/test_oc_frontier.py::test_rows_match_sources`,
  `tests\test_oc_frontier.py:54: AssertionError: ('v421', 'R2B1D17BF')`;
  `tests/test_oc_g2k20robust.py` fails on missing local
  `research/diagnostics/oc_g2k20robust/results.json` (`FileNotFoundError`,
  `test_files_exist` asserts `exists()` False) — static scan missed the dep
  (path built dynamically), so triage says STALE but it is really
  COMMIT-WITH-SKIP material (generate artifact or add a skip guard).

## DROP-CANDIDATE

- `tests/test_oc_eventblk.py::test_calendar_utc` (dep
  `research/tournament/oc_eventblk` untracked-exists, 0 tracked):
  `tests\test_oc_eventblk.py:62: AssertionError: raw/fed_fomccalendars_20201224.htm`
  (manifest sha mismatch, local raw file re-hashed differently).

## DEFERRED (104, still need one passing run each; full list in temp `triage2_deferred.txt`)

`test_oc_ewmasig, expiry, expiry4p, expirybook, expirycb, expirydip, filltime,
fillttl, fomcbook, frontier, fundregime, g2k20robust, grindsignal, holdext,
idea1, idea10, idea2, idea2wf, idea3–idea9, idiocap, kellydip, ladderfill,
linvinv, liqcheck, liqlive, longcap, lots, lowvolrung, macro, manual2,
manual2coin, manual3, manualcap, manualcarry, manualnight, manualshallow,
manualtsmom, margin, marktrig, mcdd, optctx, outage, phase8, phaserebal,
placebo, placebo_dip, plateau, plateau2, postflush, premexpo, premfill, qbasis,
rearm, recent, regimetrue, rolling17, rungcap, rungspace, saturation,
seasondepth, seedengine, signedfunding, skewbook, skewbook2, stopslip, stoptf,
stresshist, topbook, tpbyn, tpdecay, tpfill, trendladder, tsmom,
tsmom_official, tsmomcombo, tsmomvar, underwater, usdt4p, usdtdip, usdtprem,
usdtshort, utamargin, utamargin2, velocity, venuegap, volflush, weekend,
wfselect, xsrev, ops_jitterjob, r2_4p_robust5, tournament_oc_agentens,
tournament_oc_gapstress, tournament_oc_kpi, tournament_oc_kpi_d13,
tournament_oc_kpi_g2, tournament_oc_regimeexp, tournament_oc_vipfees`
(scan-only now: 191 files, 160 COMMIT? / 31 DROP-CANDIDATE? — count drifts as
workers add files).

## Pass 3 (partial, stopped at 100 min)

Re-ran the 104 deferred via the wrapper (`--retry-wait 120` to fit the
budget). First attempt died on CRLF-mangled `--list` (103 false `vanished`,
1 real pass: `test_tournament_oc_vipfees` 9 passed -> COMMIT). Clean rerun:
first pass all deferred (RAM 1.3 GB, slot_1 held by another worker), after the
120 s wait the retry pass executed on recovery — preserved tail shows COMMIT:
`ewmasig(11) expiry(3) expiry4p(5) expirybook(6) expirycb(6) expirydip(14)
filltime(6) fillttl(15) fomcbook(6) fundregime(7) grindsignal(9) holdext(17)
idea1(4) idea10(5) idea2(5) idea2wf(7) idea3(5) idea4(5) idea5(9) idea6(8)
idea7(7) idea8(8) idea9(10) idiocap(2) kellydip(9) ladderfill(7) linvinv(6)
liqcheck(5) liqlive(6) longcap(6) lots(6)` — earlier retry rows scrolled off
and the process was killed at the time stop before writing JSON, so these
need one confirming run before `git add`. No COMMIT-WITH-SKIP observed
anywhere this task.

## Rerun (remaining 104 minus confirmed)

```sh
.venv/Scripts/python.exe -c "import sys; sys.argv=['test_triage.py','--json','C:/Users/trait/AppData/Local/Temp/opencode/triage3.json','--retry-wait','120','--list']+[l.strip() for l in open('C:/Users/trait/AppData/Local/Temp/opencode/triage2_deferred.txt') if l.strip()]; import runpy; runpy.run_path('scripts/test_triage.py', run_name='__main__')"
```

(use the `python -c` form, not `$(cat)`, to avoid CRLF `vanished` artefacts).
No tests/research code touched, no commits. Time stop: 100 minutes.
