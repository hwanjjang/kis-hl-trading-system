# Personas

## Purpose

These personas describe responsibilities and decision contexts visible in current behavior. They do not define application accounts or permissions because the CLI has no authentication or role-based access control.

## P-01 Solo Trading Operator

**Role:** Primary operator and final decision-maker.

**Context:** Runs the CLI on a controlled workstation, owns the selected Hyperliquid account or approved API wallet, and chooses whether a prepared action becomes live.

**Goals:**

- Resolve the intended instrument unambiguously.
- Review fresh market/account context before exposure changes.
- Keep live actions inside the supported asset and session policy.
- Preserve submission and protective-order evidence.

**Behaviors:**

- Uses dry-run first, then repeats a reviewed command with `--live`.
- Uses `hl-account`, mapping lists, verification, funding, and spread outputs as a manual checklist.
- Uses `--allow-outside-session` only for a separately reviewed exception.

**Failure concerns:** Wrong symbol namespace, stale verification, missing stop coverage, unrounded order values, unexpected exchange rejection, or confusing a reference quote with an executable price.

**Key surfaces:** ACCOUNT-001, ORDER-001, STRATEGY-001, STRATEGY-002, ASSET-004, ASSET-006, ASSET-007, JOURNAL-002.

## P-02 Market-Data Operator / Analyst

**Role:** Maintains comparable market evidence without authority or need to sign orders.

**Context:** Has network access and, for KIS paths, valid KIS credentials. May operate without a Hyperliquid private key.

**Goals:**

- Refresh the curated and observed trade.xyz universe.
- Collect current and historical reference data with source traceability.
- Identify missing, new, unsupported, skipped, or failed symbols.
- Avoid losing successful batch results because one symbol fails.

**Behaviors:**

- Seeds mappings before listing or collecting them.
- Uses filters and explicit symbol lists to bound calls.
- Reviews `succeeded`, `failed`, `skipped`, and stored-record counts.

**Failure concerns:** KIS token/rate-limit errors, Yahoo throttling or symbol changes, partial batches, stale database state, and assuming an observed market is tradable.

**Key surfaces:** MARKET-001 through MARKET-004, ASSET-002 through ASSET-007, KISMAP-001 through KISMAP-004, REFMAP-001 through REFMAP-004, HISTORY-001.

## P-03 Strategy and Risk Reviewer

**Role:** Reviews whether evidence and risk assumptions justify an operator action.

**Context:** Reads JSON output, local records, policy documentation, and completed-trade metrics. The same person may also be P-01 in a solo workflow.

**Goals:**

- Distinguish implemented signal logic from planned strategy controls.
- Confirm the entry basis, ATR input, session state, and protective plan.
- Evaluate performance by strategy using return percentages rather than currency PnL.
- Keep incomplete or undefined statistics visibly undefined.

**Behaviors:**

- Treats the BTC breakout as one signal component, not proof of a complete high-probability setup.
- Filters journal statistics by strategy before changing rules.
- Requires one completed flat-to-flat position per record.

**Failure concerns:** Treating aspirational daemon design as implemented, using stale ATR, combining unrelated strategies, recording an open or partially reconciled position, and misreading the adjusted ratio.

**Key surfaces:** STRATEGY-001, STRATEGY-002, ORDER-001, JOURNAL-002, HISTORY-001.

## P-04 Maintainer / Auditor

**Role:** Verifies traceability, policy alignment, and operational diagnostics.

**Context:** Has repository and local database access, but need not have live financial authority.

**Goals:**

- Reproduce command behavior with tests and stubbed transports.
- Trace external failures and partial batch outcomes through structured logs.
- Reconcile documentation, schema fields, mappings, and tests.
- Confirm that secrets do not enter output or version control.

**Behaviors:**

- Uses command IDs and acceptance criteria as executable-documentation anchors.
- Checks SQLite rows and JSON output after state-changing local operations.
- Treats external live verification as a separate operational step.

**Failure concerns:** Documentation drift, unlogged abnormal paths, silent schema incompatibility, external API changes, and broadening live asset coverage without tests and mapping updates.

**Key surfaces:** CORE-001, CORE-002, CORE-003, ASSET-001 through HISTORY-001.

## Persona-to-capability matrix

| Capability | P-01 | P-02 | P-03 | P-04 |
| --- | --- | --- | --- | --- |
| Public Hyperliquid reads | Primary | Primary | Review | Verify |
| KIS/secondary collection | Review | Primary | Review | Verify |
| Mapping and eligibility maintenance | Approve/use | Primary | Review | Verify |
| Dry-run order preparation | Primary | No operational need | Review | Test |
| Live Hyperliquid submission | Primary | Not intended | Approval responsibility only | Test/stub only |
| Journal entry | Primary | Not intended | Review | Verify |
| Journal analysis | Use | Optional | Primary | Verify |

## Assumptions

- **A-003:** One trusted OS user may perform several persona responsibilities in the same local session.
- **A-007:** “Reviewer” and “approval” describe an operating practice only; the current product has no four-eyes workflow or approval record.
- **A-008:** A user without a signing key can still use dry-run order preparation and public Hyperliquid reads, subject to the command's other inputs.

## Unresolved risks

- There is no technical separation between data-collection and live-trading roles.
- File-system access to `.env`, token caches, and SQLite determines practical authority outside the application.
