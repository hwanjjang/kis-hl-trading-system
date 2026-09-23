# Corrective self-verification
Candidate: sha256:c0d6ed5976b9b61f90ad87e20c4ed8a4ec3472364bd41018e550bc46acb4d9c5. Exact input hashes in candidate.json. Commands and sanitized outputs in test-results.json and referenced .txt artifacts.
- AC1: local remains default, native is opt-in; no new exchange acceptance assertion.
- AC2: shared tick/significant-figure validation; normalized quote distance persisted before entry and zero blocks entry. Known readback grammar is distinct from request semantics. Real SDK signature recovery remains covered.
- AC3: focused 104 and full 447 tests pass; real gateway/SQLite smoke separately exercises waiting/rejection/restart/SL-loss with actual parser and fill reconciliation. No duplicate trail or waiting/rejection-only exit.
- AC4: Red/Green/full regression/additional smoke, renewed sequence diagram with 9 deterministic checks, four browser sizes and visual review. Independent verification follows.
All exchange I/O is deterministic offline simulation; no live order/activation/readback/cancel guarantee. The real smoke claim is about local integrated components and SDK, not remote exchange. git diff --check passes. No relevant source changes occurred after final test/smoke candidate capture.
