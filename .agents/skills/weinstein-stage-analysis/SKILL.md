---
name: weinstein-stage-analysis
description: Explain and apply Stan Weinstein stage analysis from his 1988 book, including investor/trader entries, market and sector context, exits and short setups. Use for Weinstein-method chart reviews, study questions and comparisons with later adaptations.
---

# Weinstein Stage Analysis

One book-centered analytical skill, with topic references loaded as needed. It is an independently written synthesis of researched principles, not the book, a complete edition audit, or a mechanical trading system. Answer in the user's language.

## Choose the task

- **Explain or compare:** answer the specific question; read [sources](references/sources.md) before attributing a rule to the book or comparing variants.
- **Analyze a setup or position:** read [method](references/method.md) and [evidence](references/evidence.md). Select investor or trader mode. If unstated, use investor mode and disclose that assumption; position-management decisions also need the actual position and existing stop.
- **Historical/backtest specification:** distinguish source principles from numerical operationalization. Do not claim tested performance without a defined dataset, costs and executed results.

The baseline is the 1988 framework. Label later teachings, third-party conventions and local adaptations explicitly. Read the source register for disputed thresholds or advanced topics; say when the evidence is insufficient to attribute a rule confidently.

## Analysis workflow

1. Establish instrument, venue, benchmark, as-of time, evidence source and mode. Current recommendations need current evidence; a supplied historical snapshot supports only an as-of analysis. If retrieval tools are unavailable, analyze what is supplied and identify the gaps. Do not fabricate bars or quotations.
2. Examine market, industry/group and stock in that order. Missing group or breadth data is unknown, not favorable. Explain a justified proxy when the instrument has no meaningful industry group.
3. Assess stage from preceding trend, price structure, moving-average direction and participation. Permit uncertain/transition classifications. A moving-average crossing alone does not establish a base breakout or a completed stage change.
4. Separately assess entry eligibility: setup type, resistance, relative performance, volume evidence and distance from the structural invalidation. An established Stage 2 stock can be too extended for a new entry.
5. For an existing position, assess the protective stop and invalidation before discussing a fresh entry. A breached protective level does not wait for a later stage label. Produce an analytical management conclusion without placing an order.
6. Report the evidence that could change the conclusion. Separate observed facts, chart judgment and implementation choices. Do not substitute a majority vote of checklist items for resolving a material contradiction.

## Response contract

Keep educational answers focused. For a decision review, provide:

- **Scope:** instrument, as-of date, investor/trader mode and source profile.
- **Context and stage:** market/group/stock evidence, stage or transition, confidence and why.
- **Setup and decision:** initial breakout, retest, continuation, short setup or none; eligibility = supported / not supported / insufficient evidence. Distinguish new-position watch/wait/entry candidate from existing-position hold/reduce/exit/protection review.
- **Management:** supplied or calculated invalidation/stop, relevant position facts and reassessment trigger. Omit numerical sizing if necessary inputs are absent.
- **Limitations and provenance:** missing/stale data, competing interpretation, original principle versus chosen convention.

Use only the fields needed by the request; do not imply that “entry candidate” is authorization to trade.

## Host use

No other skill, broker, API key or executable script is required for supplied-data analysis. Use the host's available read-only data and calculation tools when necessary. In Hermes, load this skill with `skill_view(name="weinstein-stage-analysis")` and load a reference with `skill_view(name="weinstein-stage-analysis", file_path="references/method.md")`. Other hosts read the same relative files.

Hermes may invoke this skill from its own briefings or scheduled work. This skill neither creates schedules nor sends notifications nor grants order authority. Host execution, account limits and instrument eligibility remain separate requirements.
