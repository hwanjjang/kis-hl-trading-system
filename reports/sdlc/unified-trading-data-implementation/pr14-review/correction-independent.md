# PR #14 inventory correction: independent verification (iteration 2)

Verdict: **BLOCKED**. Reviewer `/root/verify_inventory_correction` independently
inspected the correction by builder `/root` on base
`76d22d4a1aa0ee2ce804bae1aa2d074af5793a51`. No source edits, commits, vendor calls or
private-data reads were performed. Exact source/test hashes and the complete
reproducible temporary probe script/results are retained in
`correction-independent.json`.

## Checks

- `python3 -m unittest tests.test_canonical_inventory -v`: PASS, 11 tests, 1.491 s.
- `python3 -m unittest discover -s tests -t . -q`: PASS, 319 tests, 21.964 s.
- `PYTHONPATH=. python3 /tmp/verify_inventory_correction.py`: exit 0; independently
  constructed synthetic DAY statements expose the two remaining failures below.
  Each probe initializes real temporary SQLite, imports statements, records complete
  trade coverage, and runs the canonical journal. Temporary databases are deleted.
- Positive inspected/tested cases: oversell before closing the current long,
  unanchored first buy and inferred later flat, later explicit flat anchor,
  anchored partial exit/add, normal sell/re-entry on one day, funding/fee conserving
  Hyperliquid reversal, immutable old reports, policy version.

## Must fix IV-1: early failure bypasses DAY invalidation

`kis_hl/journal_exports.py:74` marks only a still-open cycle and exits before
lines 118-128 validate the day's ending inventory. Reproduction (all rows use
DAY precision, price 100, fee 1): day 1 buy 1 with position_before=0 and end=1;
day 2 sell 1 with position_before=1 and end=7; day 2 sell 2 without a starting
position and end=7. The first day-2 sell closes the long; the next sell is rejected
as an oversell. The journal nevertheless reports that cycle FINALIZED with -2%
return and trade_count=1, while the account net is correctly unavailable.

The contradictory day-end holdings and unresolved remaining DAY activity prevent
confirmation of a flat-to-flat cycle. Invalidate every affected overlapping DAY
cycle before any early exit, including closed cycles that ended during that day.
Do not invalidate cycles closed before that day's interval. Cover other early
exits (position-before mismatch and ambiguity), which likewise skip day-end checks.

## Must fix IV-2: unrelated later ambiguity removes a verified prior cycle

`kis_hl/journal_exports.py:61` unconditionally marks `active`, even when it closed
on an earlier day. Reproduction: day 1 buy 1 before=0, end=1; day 2 sell 1, end=0;
day 3 buy 1 and sell 1 without sequence evidence. The correctly anchored day-1/2
cycle becomes PENDING with ambiguous_chronology and disappears from statistics.

This branch predates the patch but directly violates the accepted preservation
criterion and is adjacent to the corrected opening-gap branch. Apply the same
interval-aware invalidation boundary to ambiguity rather than invalidating a stale
closed `active` pointer. A separate probe confirms later day-end mismatch already
preserves the prior cycle correctly.

## Acceptance and limits

AC3 remains blocked by IV-1; AC6 remains blocked by IV-1/IV-2 despite passing
existing suites. No other findings in the assigned correction scope. This is
synthetic, local independent verification, not live-broker verification or a
separate-provider PR re-review. Parent owns documentation, CLI smoke, shared SDLC
ledgers and subsequent publication. No new skill observation was identified;
parent may include that in its shared deliverable checkpoint.

Reviewed SHA256 `kis_hl/journal_exports.py`: `75973b01415023b382b989e19a395c83b339dbb5e43751c533eb73e6a09df076`.

Reviewed SHA256 `tests/test_canonical_inventory.py`: `b43ea8bcd0e082bb86a1b65b84ba3d0bc7b2bca821e1c8d50ca81a12ee4561b7`.

The parent changed the test file after the 11-test run; its subsequent hash is recorded separately in JSON, with no claim that those additions were tested. Production source remained unchanged.
