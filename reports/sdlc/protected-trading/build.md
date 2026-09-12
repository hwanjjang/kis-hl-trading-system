# Build result

Candidate: `108d96a2f15e2825ff0d223db6e33740accc87f8b577f2dceb94c4071aaddd9f`. Base: `9360b0cdd2753d5ca94ce052b03fd67d7b0c4af1`. File set and exact SHA256 values are in
candidate.json; actual code/document diff is change-record.patch. Generated HTML
is separately hashed and mapped to its validated source JSON.

PT1: exact KIS market/account/limit/cancel/amend adapters, catalog and quote/ATR
provenance, ETH support and metadata/capability inspection. PT2: immutable facts,
coverage/cost gaps, source-backed cycle revisions and statements. PT3: persistent
10800-second configurable scheduler. PT4: durable protected entry, partial native
coverage, local SL/trailing, bounded cancellation/exit and unknown outcome handling.
PT5: account multiplexing/ownership plus future immutable strategy/signal/grant
interfaces. PT6: test/smoke/independent review and PR handoff, with notifications,
actual trading, merge and deployment excluded.

Build reviews core-review.md and core-review-2.md found reproducible defects;
regressions now cover them, including kill-switch changes during preflight.
Existing deterministic trailing policy and nine journal formulas are unchanged.
Formatting used Black 25.1.0 on new modules/tests only. KIS account-summary work and
skill temporary-file ignore rules from earlier authorized requests are included.

Operational refinements: journal materialization is one SQLite transaction;
KIS cumulative summaries cannot finalize exact journals without source statements;
active-order amendment uses cancellation/reconciliation rather than unsafe in-place
ownership replacement. No actual strategy timing code is invented. All remaining
venue rollout limits are explicit in docs/trading-operations.md.
