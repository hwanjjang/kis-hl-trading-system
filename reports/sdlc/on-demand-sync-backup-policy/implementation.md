# Account audit implementation and acceptance

PR19 was extended from operator-policy documentation to reusable executable account
audit and explicit adjustment at the user's request. The original private account
scripts and all real source records remain outside Git. Intent, specification and
plan are in `intent/account-audit.md`, `specs/account-audit.md` and
`plans/account-audit.md`. The existing stable task and stage counters were resumed;
this is not a new review cycle for PR14.

## Delivered behavior

- `data audit-collect`: explicit account/range, native read-only client capture,
  private new-path evidence bundles, no operational DB initialization or writes.
- `data audit-compare`: native normalization with captured-evidence checks, source
  changes/missing records, fees/funding, bounded inventory reconstruction, a
  current selected-account state digest and a private reviewable plan.
- `data audit-apply`: exact report hash, re-derived plan, transactional state check,
  explicit correction flag, no unresolved differences, append-only source/fact
  history and a durable replay receipt. No deletion or completeness certification.
- `--journals`: per-account plus combined reports in the same transaction. Old
  reports/exports remain immutable; repeated application returns the same IDs.
- Operator-triggered sync and backup policy remain documented. No schedules,
  operational adjustments, actual backups or orders were executed by this task.

## Smoke scenarios

Run `python3 scripts/smoke_account_audit.py`. This uses real CLI subprocesses,
native clients and SQLite. Provider I/O alone is replaced with synthetic fixtures;
network connection attempts fail. Environment variables and working directory are
isolated from user credentials and `.env`. Temporary state is cleaned on exit.

| Scenario | Required observation | Failure condition |
| --- | --- | --- |
| Collect both venues before DB initialization | Two private source bundles, operational DB absent | Capture opens/creates operational DB |
| Compare selected accounts | Five synthetic source facts, unchanged DB counters | Comparison writes source/fact/report state |
| Wrong report SHA-256 | Error and no writes | Tampered/wrong digest accepted |
| Apply with journals | Five facts; two account journals and combined journal | Missing reports or partial transaction |
| Replay same report/options | Existing receipt/IDs, unchanged counters | Duplicate facts or journal runs |
| Verify source costs and cashflows | USDC net 1.6 and KRW net 2; coverage pending | Double charged funding/fees or false certified returns |
| Existing commission correction | Rejected without explicit flag, new revision with it | Silent correction or source-history overwrite |
| Stale comparison | Rejected after selected facts change | Old plan applies to drifted state |
| Preserve old export | Original bytes unchanged after correction | Historical output rewritten |
| Missing source records | Blocked plan and no mutation | Missing facts silently deleted or ignored |

Unit tests additionally cover atomic rollback on journal failure, scope identity,
KIS query windows/epoch boundary, orphan executed orders, same-time inventory
chains, raw/decoded/position evidence contradictions, funding representation and
duplicate intervals, permissions and operator-source provenance. Incremental
funding-only capture carries forward recorded inventory instead of assuming zero.

## Independent verification

The [independent report](independent-verification.md) retains initial findings and
actual correction re-execution. Its synthetic scratch probes are published
unchanged as [independent_probes.py](independent_probes.py); run:

```bash
PYTHONPATH=. python3 reports/sdlc/on-demand-sync-backup-policy/independent_probes.py
```

Private scratch paths in the original verifier receipt refer to the identical
publication copy here. Candidate hashes and actual final counts are recorded in
[validation.json](validation.json). Archify source/HTML remain tracked under
`docs/diagrams/account-audit.*`; deterministic, browser and visual results are
summarized in [diagram-validation.json](diagram-validation.json).

## Limits

All new runtime checks are offline and synthetic; no live retention, production
recoverability or broker authenticity is asserted. API capture/adjustment does not
replace independent-statement coverage certification. KIS collection covers
domestic and US equities; native DAY precision is retained. Unknown opening
inventory and unsupported accounting remain visible, and unresolved source
contradictions block adjustment. Source bundles/reports must remain private.

The authorized endpoint is PR19 update. Independent implementation verification
is distinct from eligible cross-provider PR review; no formal PR-review PASS,
merge readiness, merge authorization or production deployment is claimed here.
