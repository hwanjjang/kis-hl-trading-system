# Corrective self-verification
Candidate: sha256:e5ac77a4207f4964f7146a84838d74182b276b1afed0211a4b7779c0959391a9. Exact input hashes in candidate.json. Commands and sanitized outputs in test-results.json and referenced .txt artifacts.
- AC1: local remains default, native is opt-in; no new exchange acceptance assertion.
- AC2: shared tick/significant-figure validation; normalized quote distance persisted before entry and zero blocks entry. Known readback grammar is distinct from request semantics. Real SDK signature recovery remains covered.
- AC3: focused 105 and full 448 tests pass; real gateway/SQLite smoke separately exercises waiting/rejection/restart/SL-loss with actual parser and fill reconciliation. No duplicate trail or waiting/rejection-only exit.
- AC4: Red/Green/full regression/additional smoke, renewed sequence diagram with 9 deterministic checks, four browser sizes and visual review. Independent verification follows.
All exchange I/O is deterministic offline simulation; no live order/activation/readback/cancel guarantee. The real smoke claim is about local integrated components and SDK, not remote exchange. git diff --check passes. No relevant source changes occurred after final test/smoke candidate capture.

Renewed iteration3 adds accepted known-ID active then rejected regression, now passing with residual exit. Both initial and accepted-terminal Red logs are retained; previous self-verification preserved as self-verification-initial.md. Final candidate unchanged through renewed tests/smoke.
