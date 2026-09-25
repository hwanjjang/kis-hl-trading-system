# Evidence and calculation contract

This file defines this skill's analytical operating choices, not additional rules attributed to Weinstein.

## Required evidence depends on the question

For a chart review, seek dated weekly OHLCV, sufficient preceding history to interpret the base/top, benchmark data, group context and the chosen long average. For managing a holding, also seek position direction, entry context, horizon and the existing stop. Lack of sizing inputs need not prevent stage analysis; lack of volume prevents a confident volume conclusion.

Identify exchange, currency, timezone, adjustment policy and the last completed period when available. Splits, dividends, symbol changes and different trading calendars can distort comparisons. State unresolved mismatches instead of interpolating certainty. A screenshot supports visible qualitative observations, not exact hidden indicators.

Use completed weekly bars for confirmed analysis. Label the current incomplete week provisional and do not compare its raw volume to a complete week's volume as though equivalent. This is a reproducibility convention; it does not assert that the book forbids all intraday action.

## Indicator conventions

- **Long moving average:** disclose period, bar frequency and weighting. The sampled book describes a weighted 30-week Mansfield average; the exact historical weighting is not established here. A 30-week SMA or EMA is a declared approximation. Daily 150/200-day averages and the repository's 30-week EMA are not silently interchangeable with it. [B1]
- **Slope:** use the supplied calculation or an explicit comparison window. “Flat” requires a stated numerical tolerance when automated. Without one, label the assessment a visual judgment; do not invent a book percentage.
- **Relative performance:** disclose benchmark and aligned timestamps. A usable third-party convention is `RP = 100 * instrument_close / benchmark_close`, then `MRP = 100 * (RP / SMA(RP, 52) - 1)` on weekly data. This is the StageAnalysis.net convention [S4], not proof of the exact original chart formula. Keep level and direction distinct; it is not RSI.
- **Volume:** record timeframe, lookback, completed bars, whether the tested bar is excluded and the observed accumulation sequence. Do not substitute an unexplained 50-day or 52-week baseline for a shorter book example. FX tick volume, missing volume and some index feeds are not equivalent to traded share volume.
- **Structure:** identify the bars or visible region supporting base, support, resistance and overhead supply. A moving-average crossing alone is not a resistance breakout. Avoid fabricated fixed base lengths or automatic stage scores.

Perform arithmetic with available deterministic tools when raw data is supplied. Do not claim a calculation was executed if it was only described. If the required averaging history is unavailable, mark the value unavailable rather than treating it as zero.

## Risk and host boundaries

If sizing is requested, require an explicit risk budget, entry, stop, contract multiplier/units, and relevant costs. Explain gap/slippage assumptions. This skill supplies no universal position-size percentage and no model-backed expected return.

ETF leverage, futures rolls, perpetual funding and index proxies require instrument-specific interpretation; do not treat them as ordinary cash-stock evidence by default. A strong chart does not override listing-age restrictions, supported-asset policy or account constraints in the host. Report methodology conclusion and operational eligibility separately.

For current asset-specific decisions, obtain current information or state that the result is limited to the supplied snapshot. Educational examples need no live market access. Fetch only data needed for the analysis; broker credentials and write access are unnecessary for this skill's reasoning.
