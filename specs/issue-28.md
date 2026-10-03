# Partial take-profit contract

Decision. `ExecutionStore.request_take_profit(position_id, now_ms, decision_id,
rationale)` stores `row["take_profit"] = {decision_id, rationale, requested_ms,
status: REQUESTED}` and appends the ID to `take_profit_decisions`. The same active
ID returns the row unchanged. A used ID, another active TP, a non-`hl:` instrument,
a non-PROTECTED/finished/paper owner, a latched exit or entry cancel, or a pending
add tranche is rejected. `enqueue_add` and add authorization reject an owner with
an active TP (REQUESTED or EXECUTING).

Freezing. The supervisor freezes the basis only on a PROTECTED, fresh step with no
active entry/add attempt, no unresolved exit and no exit latch:
`basis_size = size`, `target_quantity = floor(size * 0.5 / quantity_step) *
quantity_step`. When `target * price` is below the Hyperliquid USD 10 minimum, the
status becomes BELOW_MINIMUM with a reason and no order (the residual is never
smaller than the floor-rounded target, so it needs no separate check). Status EXECUTING records `frozen_ms`.

Execution. TP orders use attempt kind `take_profit`: reduce-only IOC sell limit at
`price * (1 - slippage)` rounded up to tick, quantity
`min(target - filled, size, sellable)` rounded down to lot. `filled` is the sum of
per-attempt sell fills reported in `fills_by_attempt`. Any unresolved TP attempt
(SUBMITTED/UNKNOWN) blocks a new one. The attempt count is capped by
`max_exit_attempts` and the frozen basis age by `exit_deadline_ms`; exhaustion sets
status EXHAUSTED and keeps the residual protected without a forced full exit. A
remaining quantity whose notional is below the minimum ends as BELOW_MINIMUM.
`filled >= target` while the step is PROTECTED sets COMPLETED with
`residual_size`. TP attempts never count toward the full-exit budget and TP fills
never count as protective fills.

Competition. When an exit latches or the position is flat, an active TP becomes
SUPERSEDED. The full-exit loop treats unresolved TP attempts like unresolved exits:
no new full exit is sent until they are terminal, open ones are cancelled after the
reprice delay, and flat cleanup cancels remaining owned TP orders. Reduce-only
orders cannot reverse exposure.

Protection. Existing coverage logic is unchanged: reduce-only SL/TS whose size is at
least the residual counts as coverage. Native trails and local trail state
(watermark, threshold) are never reset by the TP. The KIS gateway rejects
`take_profit` submissions.

CLI. `order take-profit --id ID --decision-id ID --rationale TEXT` records the
request. It does not place an order directly; the supervisor executes it.

Alternatives rejected: reusing `request_exit` (full-exit latch semantics), resizing
or recreating TS orders (resets watermarks), freezing size at CLI time (no fresh
reconciled snapshot).
