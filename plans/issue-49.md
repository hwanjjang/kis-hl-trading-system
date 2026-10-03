# Issue 49 implementation plan

Inputs: intent/issue-49.md and specs/issue-49.md. Owner: Codex /root.

1. Add tests/test_advisory_ts.py first; reproduce the existing generic error and silent recovery defect with an intended failing behavior test.
2. Add kis_hl/advisory_ts.py and scripts/hl_9m_ts_alert.py; preserve the current algorithm and isolate owner reads. Add a scoped installer with source hash checks and existing-script config extraction.
3. Document the monitor in docs/trading-operations.md and its responsibility in docs/architecture.md. Add a separate integrated SQLite/CLI smoke.
4. Run targeted and complete offline tests, plus the distinct smoke. Verify the profile wrapper/module identities and read-only invocation against a scratch backup of state. Preserve native protection and existing deployment checkout edits.
5. Commit/push, create PR, inspect independent reviewer capability/configuration and execute eligible review, apply selected findings, rerun affected checks and review. Observe CI, current head/base and disabled merge automation; produce current readiness evidence without merging.

## User scenarios

- S1 (AC1, AC2): Operator has a prior verified bar. On the first tick after a nine-minute boundary one minute is missing. Observe a coverage_gap with missing timestamp and unchanged high/threshold/end. Restore the minute and tick again: same start retried, covered-through advances, one recovery appears. Third tick is silent.
- S2 (AC2, AC5): Operator sees successive gap and invalid bid ValueErrors. Distinct reason codes notify separately; repeated identical reason is quiet. Secret-laden transport exceptions never expose their text in state/output.
- S3 (AC3, AC5): KORU owner is missing or mismatched while SP500 is valid. SP500 still verifies. Recording transport rejects any request outside the six /info read types and any /exchange/signature/action path.
- S4 (AC4, AC5): Operator installs only the tested advisory files and runs the deployed wrapper with scratch state and --report. Hashes match; report contains verified coverage or an allowlisted degraded reason. Operational state/quantity/protection/parameters remain untouched.

Risks/blast radius: Only advisory state and notifications. Most risky is advancing reconstructed bars before quote validation; commit them only after all evidence passes. Reject a raw-exception logging alternative because it can leak credentials. Do not deploy the entire dirty checkout. Roll back the saved wrapper/module, leaving bars and additive diagnostics intact. CI is offline; live trigger execution is outside this task.
