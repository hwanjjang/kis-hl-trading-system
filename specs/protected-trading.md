# Protected trading implementation contract

Implements [the product specification](multi-venue-protection.md), except section
7 notification delivery and transport. The existing diagrams are the target design
and must be reconciled against actual implementation before PR handoff.

The CLI remains the harness-neutral boundary. Read-only operations and offline
preview/replay do not need signing credentials. Explicit live mutation requires
all existing and new risk/eligibility/ownership guards; tests use stub transports.
KIS stop-limit is not promoted to native SL without verified downside semantics.
Keep native capability uncertainty visible; do not silently broaden asset support.

Journal facts and scheduler state use additive SQLite tables; existing manual
records remain readable. Unknown costs/origin/history are explicit pending state.
No evidence of completion means no realized performance record. The scheduler
default is 10800 seconds and uses persistent intervals/cursors and an account lock.

Implementation-specific CLI/schema details and remaining live verification limits
will be documented with the code in docs/architecture.md and owner references.
