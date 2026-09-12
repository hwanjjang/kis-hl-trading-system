Implement locally in one bounded change.
1. Add offline endpoint/CLI tests, observe intended failure.
2. Add thin method and summary handler; sync README, architecture and KIS endpoint table.
3. Run relevant tests, then real CLI read-only smoke and independent verification.
Risk: secrets leaking through exception text or stale credentials; whitelist output, sanitize failures and separate cache.
Rejected: committing temporary script or adding a new service. Rollback is removal of additive method, command and docs. No migration.
