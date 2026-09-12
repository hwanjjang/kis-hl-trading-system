# Self-verification

Candidate `108d96a2f15e2825ff0d223db6e33740accc87f8b577f2dceb94c4071aaddd9f`: 253 unit/regression tests passed; 18-process real offline
CLI/SQLite functional smoke passed. Required red regressions failed before the
fixes, followed by green/post-format checks. Exact commands and sanitized evidence
are in test-results.json. All checks were rerun after native stop, scheduler lock and attribution corrections.

PT1 is covered by KIS route/pagination/error fixtures, HL payload/eligibility tests,
gateway behavior checks and read-only KIS metadata probes. PT2/PT3 have actual-fill
fixtures, cost/coverage/correction/chronology regressions and persistent scheduler
checks. PT4/PT5 have durable state, partial fill, unknown transmission, cancellation,
restart, stop semantics, entry kill-switch, ownership and bounded grant tests.
The existing subprocess account-lock test runs with actual file locks. The additional
CLI smoke exercises runtime/parser/storage wiring without mocked handlers.

No venue order, cancel or amendment was submitted. Live partial-fill, halt/gap and
broker cancellation behavior remain unverified; KIS exact journal finalization needs
statement supplementation. These are explicit operational gates/limitations.
Independent final verification and eligible PR review remain separate next stages.
