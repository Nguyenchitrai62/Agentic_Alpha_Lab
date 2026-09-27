# v154 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v154_audit/` and `tests/test_v154_audit.py`.
Base: your v144 replication, your v150 member WITH the v142 xs features (options columns joined before the xs step, no xs
of the options columns), and your v111 Coinbase-premium features. Do NOT open v154/ until part A is saved.
A: A = v144 books; B = v150 member; D = v144 builder with the five v111 Coinbase columns (cb_btc_dev, cb_btc_z, cb_btc_chg,
cb_eth_z, cb_eth_chg; one value per t) merged on t into the v114 and v103 panels BEFORE the v142 xs step (no xs versions
of them; vol models exclude them). Books = (A + B + D)/3 on the union index; v144 engine rows (0.15 ungoverned, 0.20/0.25
governed, 10 bps 1m execution). Report monthly, yearly, full-path DD.
Save `replication.json`, compare with v154/v154_result.json (explain return diff > 1pp or DD diff > 0.5pp), audit
v154_ensemble_coinbase.py for look-ahead, write COMPARISON.md. Do not edit leader files.
