# PR #32 review corrections

Owner: main agent. Endpoint: pre-merge (merge excluded). Source/authority: AK 2026-09-25 asked to fix all four items of PR #32 review 5318629647 under SDLC up to pre-merge, skipping the other-provider model review.

## Problem
PR #32 retires expired unsent adds for every unfinished owner that did not evaluate the add this tick. That includes a `PROTECTED` owner with `cancel_entry` set. The docs, diagram and PR text instead say "owner not PROTECTED". The "no write lock" wording also overstates: the supervisor heartbeat writes on every tick. `ExecutionStore.save(now_ms=0)` can stamp `retired_ms=0`, and one test depends on tranche ordering.

## Outcome and acceptance
- AC1: Keep the code behavior. Docs, diagram and PR text state that any unfinished owner that did not evaluate the add this tick retires an expired unsent add as `EXPIRED`. A test pins `PROTECTED` + `cancel_entry` + expired → `EXPIRED`. The existing test still pins the evaluated `PROTECTED` path → `REJECTED`.
- AC2: Docs and the diagram card say "no additional retirement transaction", not "no write lock".
- AC3: `ExecutionStore.save` requires `now_ms`. All callers pass it, and a call that omits it raises `TypeError`.
- AC4: The rollback test looks up the authorized tranche by id.

## Exclusions and risks
No change to retirement semantics, cancellation budgets or order paths. There is no live exchange validation. Cross-provider PR review is skipped by AK's decision, so this workflow's review gate is recorded as not satisfied.
