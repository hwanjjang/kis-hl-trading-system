# Reusable account audit and explicit adjustment

The private account comparison scripts cannot be reused from a clean checkout.
PR19 must include a CLI workflow that captures KIS/Hyperliquid source history,
compares it to the canonical store and explicitly applies reviewed revisions.
Source: user requested implementation, completed smoke validation and PR19 update
on 2026-09-21, extending the prior operating-policy documentation task.

Acceptance: (AC1) explicit account/range capture and comparison do not mutate the
operational database; (AC2) differences, costs, funding overlap and inventory
uncertainty are visible; (AC3) digest-bound, current-state-checked transactional
apply preserves history and rejects unresolved discrepancies; (AC4) replay adds
no duplicate economic facts or journal runs and selected account/combined reports
are regenerated immutably; (AC5) synthetic offline CLI smoke verifies the complete
flow and negative paths. No live orders, active-account adjustment, backup,
scheduling, merge or private-data publication is authorized by this implementation.
