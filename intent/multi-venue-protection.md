# Multi-venue protected trading intent

Revision: 2026-09-12. Owner: operator; planning/build coordinator: /root.
Route: plan-only, local. Source: user requested SDLC planning through Archify,
then specified the strategies below and clarified KIS gold as GLD.

## Outcome

Define an implementable CLI-first system that analyzes a configured signal series,
trades an explicitly selected KIS or Hyperliquid instrument, sets both stop-loss
and trailing policies on entry, and journals each reconciled completed position.

Codex, Claude Code and Hermes are operator harnesses over the same CLI contracts.
The operator may also trade in KIS HTS or the Hyperliquid web app. Actual venue
history is authoritative for journaling regardless of order origin. Journal
updates run on request or a configurable schedule (default: every three hours);
immediate finalization is not
required. Future strategy skills produce signals followed by notification and
either a manual execution request or explicitly configured automatic execution.

## Requested cases

| Analysis/exposure | KIS execution candidates | Hyperliquid execution candidates |
| --- | --- | --- |
| KOSPI chart | 069500, 122630 | No Korean-index trade requested in this case |
| S&P 500 or explicit SPY proxy | SPY, UPRO | Verified S&P-style contract; existing seed SP500 is a candidate |
| Nasdaq-100 or explicit QQQ proxy | QQQ, TQQQ | Verified Nasdaq-100-style contract; existing seed XYZ100 is a candidate |
| BTC / ETH | None | BTC and ETH; proposed initial scope is perpetual longs |
| Gold | GLD (user confirmed) | GOLD contract, subject to contract identity and metadata verification |
| Quantum | QPUX | No equivalent assumed; venue remains KIS unless separately specified |
| Memory | DRAM ETF candidate | DRAM contract candidate; must verify underlying independently |

## Acceptance criteria

- MV1: Explicit mappings separate signal, execution instrument, venue, quote
  currency, price basis, sessions and instrument identity; no silent substitution.
- MV2: Protection capability matrix distinguishes documented API schema, proven
  operational behavior and unknown. Native SL and native trailing are evaluated
  separately for domestic/overseas, side, exchange, session and instrument.
- MV3: Entry, partial fills, protection, exit races, timeouts, restarts and expiry
  have bounded fail-closed behavior; process fallback is operationally explicit.
- MV4: Flat-to-flat journal finalization is idempotent, cost-aware and compatible
  with the existing trade-journal skill and nine statistics, including external
  HTS/web fills, deferred synchronization, history gaps and unknown attribution.
- MV5: Source-linked spec and ordered implementation/test plan distinguish existing
  code from proposed functionality and unresolved implementation gates; include
  harness-neutral signals, notification choices and manual/automatic authority.
- MV6: Archify architecture and trade workflow have retained JSON, checked HTML,
  deterministic receipts, browser measurements and perceptual review evidence.

## Constraints and authority

Preserve SQLite, CLI-first operation, dry-run default, English repository artifacts,
secret hygiene and current live eligibility rules. Native protection is preferred
only when its actual semantics satisfy the configured protective policy. The user
explicitly warned that an order name such as stop-limit is not proof of stop-loss.

This request authorizes research, local planning and diagrams. It does not authorize
live orders, cancellations, account transfers, deployment, commits or PR publication.
Existing account-command changes belong to the previous completed task.

## Proposed initial bounds and open decisions

Long entries, one local machine and independent account/venue position cycles.
Signal rules, timeframes, ATR multipliers, risk limits and overnight policy are
configurable and not invented here. KOSPI is retained as requested, while both
Korean ETFs reference KOSPI200; add a separate KOSPI200 analysis option if desired.
Confirm DRAM identity, KIS entitlement, and exact HL contracts before enabling
execution. Product discovery is not evidence of account-level tradability.
