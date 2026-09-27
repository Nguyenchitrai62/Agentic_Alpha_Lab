# Analysis task (no code changes): practical execution, confidence scoring, RL trade management

Read AGENTS.md (2026-09-27 rules), CONTINUOUS_RESEARCH.md (top: v205, v208, v209), and
`research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py`. Write ONLY
`research/parallel/rounds/parallel-20260906-r2/analysis_rl_execution/REPORT.md` (Vietnamese is fine, keep numbers exact).
Do not run heavy jobs; small read-only checks of existing result JSONs are fine. Do not edit any other file.

Context: the best pipeline v205 re-decides target weights every 4h (5 majors, Binance USD-M), trades the difference with
limit orders at open -/+0.10%, SL/TP move with the average entry and sigma; most book episodes end by flips/rebalances;
win rate ~35-49%, profit comes from few trend episodes (v209: alpha t 3.5, placebo-robust). Discrete one-trade-per-signal
versions (v209 D1-D3) keep every dev year positive but lose ~1.5%/month. The user trades by hand or with a bot on Bybit
(maker 0.02%, taker 0.055%), wants fewer, clearer orders, tolerance to latency (signal computed after the bar close; a
human may act minutes to hours later), a per-order confidence score with its historical win rate, a training loss that
punishes confident large wrong bets, and a reinforcement-learning agent that manages trades like a trader (limit entry,
SL/TP, move SL to break-even, partial take-profit, tighten SL on reversal signals, avoid market orders). The user
mentioned the "Kev/Jev" decision models (https://huggingface.co/collections/jaredpalmer/kev: LoRA on Qwen 0.5-27B,
text document + typed questions -> calibrated probabilities; the model card says it does not support numeric
time-series or tabular features).

Answer, with concrete designs and risks:
1. Latency/cadence: how to make suggestions valid for hours (e.g. decide on 4h/1d closes but with entry zones valid N
   bars, limit ladders, no-trade bands, minimum holding times). How to test latency tolerance in engine_user (entry delayed
   by 5/15/60/240 minutes) without leakage.
2. Confidence score: definition(s) that are causal, a walk-forward calibration (fit on orders before each anchor only),
   what "win" means for continuous positions vs discrete trades, and how to display score + historical win rate.
3. Asymmetric / size-aware training loss for the HGB/LightGBM book models (e.g. sample weights by |return|, profit-based
   objectives, penalising confident wrong predictions): options, expected effect, leakage traps.
4. RL for trade management: state/action/reward design (actions limited to limit entries, SL/TP moves, partial exits,
   break-even; market only for stops), simulator = engine_user 1m execution, training data volume (~5 years x 5 coins),
   overfitting risk vs the walk-forward protocol (anchors 2021-2024 for selection, last year once), compute (local
   GTX1650 4GB for inference only, Kaggle free GPUs for training), and a staged plan (rule-based trade management first,
   then contextual bandit, then full RL). Say plainly if RL is unlikely to beat simpler baselines here and why.
5. Kev/Jev: is it usable here at all (e.g. only as a text-regime classifier)? Cost vs benefit.
End with a ranked recommendation: what to do first (cheap, testable), what later, what not to do.
