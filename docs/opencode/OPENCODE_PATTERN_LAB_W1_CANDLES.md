# pattern_lab W1: candlestick patterns (read OPENCODE_PATTERN_LAB_COMMON.md first)

Files you may write: `src/agentic_alpha_lab/patterns/candles.py`,
`tests/test_pattern_lab_candles.py`, `research/pattern_lab/candles_study.py`,
`artifacts/research/pattern_lab/candles/*`. Column prefix: `cdl_`.

Patterns (textbook definitions, parameters recorded in module constants):
doji (standard, dragonfly, gravestone, long-legged), spinning top, marubozu,
hammer, hanging man, inverted hammer, shooting star, pin bar, bullish/bearish
engulfing, bullish/bearish harami, piercing line, dark cloud cover, morning
star, evening star, three white soldiers, three black crows, tweezer top and
bottom, inside bar, outside bar. Where tradition requires a prior trend
(hammer after decline, hanging man after rise, ...), define the trend causally
(e.g. close below close 5 bars ago and below 10-bar SMA) and record it.
Sizes relative to ATR14 or bar range, not absolute prices.
compute(): continuous shape features too (body/range, upper/lower wick ratios,
body vs ATR, close location value, gap vs previous close, 3-bar body sums),
plus each pattern as a 0/1 or signed column.
