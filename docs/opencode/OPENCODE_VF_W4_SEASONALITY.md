# vf W4: calendar seasonality (read OPENCODE_VF_COMMON.md first)
Files: `src/agentic_alpha_lab/patterns/seasonality.py`, `tests/test_vf_seasonality.py`,
`research/vf/seasonality_study.py`, `artifacts/research/vf/seasonality/*`. Prefix `sea_`.
compute(): hour-of-day (sin/cos), day-of-week, weekend flag, month-end/start
window, US/EU/Asia session flags, CME weekend-gap flag (Friday 21:00 UTC to
Sunday 22:00 UTC), days to quarterly options/futures expiry (last Friday of
Mar/Jun/Sep/Dec 08:00 UTC).
events(): one column per hour-of-day (1h bars) and per weekday with the
direction +1 (long) so event_study measures each bucket's excess return;
also per-session. Additionally report per calendar YEAR the sign of each
bucket's mean excess (2020..2025-09) to judge persistence, and a
Bonferroni/BH-adjusted view. Horizon 1 bar is the key test for hour buckets.
