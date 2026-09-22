# KIS inventory correction contract and plan

Authority: user requested SDLC correction of Fable F-1 and author-escalated F-2.
Parent task: unified-trading-data-implementation, AC3 and AC6. PR #14 head before
correction: 76d22d4a1aa0ee2ce804bae1aa2d074af5793a51. Update the existing PR and
request actual Fable 5.1 medium review; no merge, deployment, vendor calls or
private-data migration. F-3/F-4 remain recommendations outside this correction.

Requirements:
- Reject KIS cash sells beyond tracked inventory BEFORE splitting/finalizing them;
  affected cycles cannot supply confirmed returns or completed-position statistics.
- Range coverage alone never proves zero opening inventory. KIS cycle eligibility
  requires an explicit zero position_before anchor, or continuous inventory from a
  previously anchored cycle. Preserve missing-anchor reasons until a new confirmed
  flat anchor. Native domestic cost/inventory reconciliation already supplies these
  anchors; unanchored overseas DAY statements remain pending until evidence arrives.
- Check DAY ending holdings after every same-day event is consumed, not after each
  individual event. Contradictions invalidate cycles overlapping that day while
  leaving earlier verified cycles intact. Never infer a cost basis for prior holdings.
- Retain source facts, fees, raw evidence and immutable old reports. Ineligible cycle
  returns and computed account net must be unavailable, with explicit quality reasons.
- Preserve correctly anchored partial exits/adds, account/currency separation, normal
  Hyperliquid reversals and funding/fee treatment. Version the updated journal policy.

Implementation: kis_hl/journal_exports.py; behavior tests in
 tests/test_canonical_inventory.py; update the existing anchored accounting fixture,
 docs/unified-data-operations.md and trade-journal record-contract reference.
No database schema/API/architecture changes. Existing Archify data-flow remains
valid; no new structural diagram is necessary for these narrow validation guards.

Proof: regression tests first (oversell, unanchored first buy, day-end contradiction,
multiple same-day events, preserved earlier cycles, anchor resumption, HL reversals),
then focused and full suites. Additional real subprocess CLI smoke performs synthetic
manifest preview/apply/replay, journal creation and immutable export. It asserts fees
are retained and invalid KIS returns are absent; no mocks/vendor access. Temporary
fixtures removed on exit. Independent verification/re-review consumes exact hashes.

Rollout: future report runs use new policy metadata; old report IDs remain frozen.
Do not rewrite private reports in this task. Re-export a newly generated report to
adopt the correction. Main risk is over-rejecting legitimate DAY data, so positive
anchored domestic and same-day cases are mandatory. Reject inventing opening costs
or silently treating a requested history interval as an inventory anchor.
