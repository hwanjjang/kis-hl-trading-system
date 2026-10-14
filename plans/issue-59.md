# Issue 59 implementation plan

Inputs: intent/issue-59.md and specs/issue-59.md. Diagram: docs/architecture/read-outage-supervision.html. Owner: Claude Code (builder).

1. Red: add tests/test_read_outage_policy.py. It covers no exit on read outages for HL and KIS (count, grace, deadline, restart, in-session KIS gap), recovery to PROTECTED without duplicate SL, explicit and real-trigger exits preserved during an outage, outbox dedup/restart/failed-delivery retry, blocker separation, structured classification without secrets, legacy flag handling, recover refusal and withdraw guards. Update the old-policy assertions in test_managed_execution, test_kis_adoption and test_conditional_add.
2. Green:
   - kis_hl/managed_execution.py: read-outage branch, recovery/legacy handling, `pending_notifications` flush and `intervention_blocker` in `save`, `managed_notifications` table, `owner_diagnostics`, `exit_provenance`, `recovery_blockers`, `withdraw_read_outage_exit`, `request_exit` source, notification list/result helpers.
   - kis_hl/managed_gateways.py: HL `metadata` phase; KIS `observation_gap_ms` and gap anchor.
   - kis_hl/hyperliquid/client.py: structured `kind`/`http_status` on read errors.
   - kis_hl/operations_cli.py: status diagnostics, recover refusal, `withdraw-read-exit`, `supervisor notifications` / `notification-result`, pending count.
3. Refactor. Run the targeted and full unittest suites.
4. Smoke: add scripts/smoke_read_outage.py. It drives the real CLI entry (`kis_hl.cli.main`) with a scripted gateway against a temporary SQLite database: outage, notifications list, failed result, ack, recovery, status diagnostics, recover refusal and withdraw. Add it to CI.
5. Docs: docs/trading-operations.md (read outages, KIS gap, recover/withdraw, notifications/Hermes), README CLI usage, docs/architecture.md responsibility line, the .agents hyperliquid-api skill if the client error contract is documented there.
6. Commit, push, open the PR, check CI, run the different-provider review (Codex, then Grok as fallback), apply corrections and record merge-ready without merging.

## User scenarios

See reports/sdlc/issue-59/user-scenarios.json (S1–S5), mapped to AC1–AC5 and to the tests and smoke in reports/sdlc/issue-59/test-plan.md.

## Risks, blast radius and rollback

The blast radius is the shared supervisor read path and the CLI status/recover commands. The riskiest change is weakening a fail-closed path. Identity, foreign-order and UNKNOWN paths keep their tests unchanged, and the generic handler still enters INTERVENTION.

One alternative was rejected: keeping the latch but suppressing it while native SL is verified. That would still liquidate KIS local-SL owners, which contradicts AK's policy.

Rollback is a code revert. The `managed_notifications` table and the new row fields are additive and ignored by older code. Live deployment and the withdrawal of existing SP500/AVGO latches remain separate AK decisions.
