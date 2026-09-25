# Post-merge regression and smoke plan

Existing unittest fixtures and installed /tmp/hl-trailing-venv; no live account or
paid data. Temporary SQLite only. Primary new test module: tests.test_add_lifecycle.

AC2/AC3 cancel-history: initial partial entry expires/cancels then later approved add
expires; new target receives first cancel, keeps verified protection; own deadline
and attempts remain bounded across reopen and process death. Legacy same-target
records preserve old budget, unmatched owner clock does not poison later orders.
Actual partial fill while cancel acknowledgement awaits readback extends SL coverage.

AC2/AC5 terminal cleanup: full exit and associated cleanup closes owner, only unsent
QUEUED tranche becomes CANCELED with evidence. Supervisor repairs already-finished
legacy rows; repeated steps preserve terminal timestamp/history. Any durable attempt
(including UNKNOWN) prevents unsent retirement. CLI status stays read-only.

Separate real CLI/SQLite smoke extends scripts/smoke_conditional_add.py with a
canceled historical entry, expired new add with partial cancellation fill, and
terminal queued-add retirement/reopen. Each CLI invocation reopens DB; socket
creation forbidden, stub gateway only. Wrong target, duplicate cancel on unknown,
expired budget reset, false retirement, stale pending status or lost protection
fails. TemporaryDirectory cleans all fixture state. Run fixtures serially for lock.

Existing full changed-scope suite preserves AC1 capital, AC4 migration/full exits
and other AC2/AC3 authorization/protection boundaries. Diagram artifact/browser/
perceptual checks complement code tests. Main and Grok produce distinct reports.
