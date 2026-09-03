---
name: trade-journal
description: Trade-journal metric contract for this repo. Use when recording or interpreting completed trades, changing kis_hl/trade_journal.py or journal CLI/storage behavior, or calculating the nine Minervini-style review statistics. Do not use it to authorize or place live orders.
---

# Trade Journal

Use this skill for completed-position journal work in this repository. It owns the
meaning of the nine review statistics exposed by `journal add` and `journal stats`.
The contract is adapted from the performance-review method in Section 4 of Mark
Minervini's *Think & Trade Like a Champion*; repository behavior is defined here and
in the tests, not by translated labels alone.

## Ground rules

- Treat one completed flat-to-flat position as one journal record. Open positions do
  not belong in realized performance statistics.
- Calculate return statistics from `realized_pnl_pct`, never from currency
  `realized_pnl`. Otherwise position size changes the average win/loss relationship.
- Keep percentage returns unweighted: every completed position contributes one
  observation. Report portfolio PnL separately.
- Determine outcome from net realized PnL: positive is success, negative is failure,
  and zero is breakeven. Exclude breakevens from win-rate and ratio denominators while
  retaining them in `trade_count`.
- `success_failure_ratio` means average positive return divided by the absolute
  average negative return. It is not a count ratio.
- `adjusted_success_failure_ratio` weights average positive and negative returns by
  win and loss frequency. It is not a manual reclassification count.
- Preserve the legacy `adjusted_outcome` record field for stored-row and CLI
  compatibility, but never use it to calculate the required statistics.
- Keep records strategy-specific when evaluating an edge. Do not combine day,
  swing, and long-term strategies into one decision metric.
- Use `Decimal` for PnL, returns, averages, and ratios. Do not introduce binary float
  arithmetic into journal calculations.

## Before changing journal behavior

Read the relevant contract:

- [references/statistics.md](references/statistics.md) for the nine formulas, signs,
  display format, breakevens, and undefined samples.
- [references/record-contract.md](references/record-contract.md) for completed-position
  boundaries, fees, partial fills, holding days, storage compatibility, and CLI input.

The implementation is `kis_hl/trade_journal.py`; persistence is in
`kis_hl/storage.py`; CLI routing is in `kis_hl/cli.py`. Update the owner reference and
behavior-focused tests in the same change when semantics change.

## Implementation checklist

1. Write or update tests in `tests/test_trade_journal.py` before production code.
   Cover unequal position sizes so currency PnL cannot accidentally replace return
   percentage.
2. Cover fees, breakeven, empty, all-win, all-loss, and both long and short outcomes
   when the affected behavior can differ.
3. If serialized output changes, update `tests/test_cli.py` and the stored statistics
   snapshot assertions in `tests/test_storage.py`.
4. Keep old SQLite rows readable. A change to calculated snapshots does not justify
   rewriting historical rows silently.
5. Update README usage and `docs/architecture.md` or
   `docs/strategy_execution_design.md` when the record or statistic contract changes.
6. Run:

   ```bash
   python3 -m unittest tests.test_trade_journal tests.test_cli tests.test_storage -q
   python3 -m unittest discover -s tests -t . -q
   ```

## Safety boundary

Journal commands are read/write operations against local SQLite state only. This skill
does not grant permission to submit, cancel, or modify an exchange order. Do not infer
missing fills or overwrite a broker/exchange-reported realized PnL without making that
assumption explicit.
