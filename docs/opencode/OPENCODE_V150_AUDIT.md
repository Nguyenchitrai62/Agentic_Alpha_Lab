# v150 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v150_audit/` and `tests/test_v150_audit.py`.
Base: your v144 replication. Do NOT open v150/ until part A is saved (`replication.json`).
A: options bars = data/raw/deribit_opt_20260926/BTC_options_4h.parquet (column bar = UTC 4h bar start), reindexed to a
complete 4h grid from the first to the last bar (missing flows/trades -> 0, IVs NaN). net = put_buy - put_sell - call_buy +
call_sell; tot = sum of the four; opt_net6 = rolling-6 sum(net) / rolling-6 sum(tot) (0 -> NaN); pcr = log(max(put_buy+
put_sell,1)/max(call_buy+call_sell,1)); skew = iv_otm_put - iv_otm_call; z(s) = (s - rolling180 mean(min 90))/rolling180
std(min 90); opt_pcr_z = z(pcr); opt_skew6 = rolling-6 mean(min 3) of skew; opt_skew_z = z(skew); opt_act_z =
z(log(max(n_trades,1))). Left-join on t (options bar start == panel row open time) to the v114 panel and to the v103 panel
before the v142 xs step (no xs versions); all return models use them; vol models do NOT. v144 engine otherwise. Also check
the aggregation script research/mj/fetch_deribit_options_4h.py for time alignment (trades in [T, T+4h) only).
Save `replication.json`, compare with v150/v150_result.json (explain return diff > 1pp or DD diff > 0.5pp), audit
v150_options_flow.py for look-ahead, write COMPARISON.md. Do not edit leader files.
