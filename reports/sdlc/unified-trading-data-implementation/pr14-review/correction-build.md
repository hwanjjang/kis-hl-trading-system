# Correction build — attempt 4

F-1/F-2 are implemented in journal_exports.py: reject KIS oversells before splitting,
require a source-backed opening anchor, validate all DAY ending balances after the
last same-day event, and invalidate only overlapping cycles on every early error.
Previously validated earlier cycles and Hyperliquid reversals retain their behavior.
Reports pin kis-inventory-v1 separately from unchanged statistical formulas.

Independent preflight found IV-1/IV-2 in build attempt 3 despite 319 passing tests;
new failing tests reproduced both, and shared overlap invalidation addresses them.
The final 13 new regressions, existing anchored cash-conservation fixture, 321-test
full suite and separate seven-process CLI smoke pass. No source accounts, database
migration, live calls, orders, merge or deployment are involved.

Candidate manifest includes all 28 scoped source/test/docs files from the initial
implementation plus this correction. The retained correction diff and per-file
hashes bind the candidate before commit. Legacy reports are immutable; future runs
apply the policy. Unanchored overseas DAY rows intentionally remain pending until
source inventory evidence is supplied. F-3/F-4 remain deferred recommendations.
