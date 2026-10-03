# Isolated-margin report contract

Intent: [issue 15](../intent/issue-15.md). No exchange calls, storage migration,
fund transfer, leverage change or execution integration are introduced.

AC1: optional margin_evidence binds scope, instrument, currency and freshness to
the sizing request. It names isolated mode and proposed_tranche_at_entry allocation,
selected integral leverage, collateral and optional nonnegative buffer. Unique
listed metadata supplies complete tiers; referenced tiered tables cannot be guessed.
Maintenance accumulates stop-notional intervals at 1/(2 * tier maximum leverage).
Required allocation is max(entry notional / selected leverage,
loss at stop + maintenance at stop + buffer); shortfall is max(0, required - allocated).

AC2: malformed inputs are unavailable with reasons, without numeric invention.
KIS and explicit cross margin are not applicable. No margin evidence does not
invalidate valid sizing. Zero rounded quantity cannot yield a requirement.

AC3: the advisory report uses actual rounded quantity including BTC fixed 80-USDC
notional. It neither resizes nor authorizes orders. Existing-position collateral
does not implicitly fund an add-up; combined liquidation is outside this contract.
Pure arithmetic tests, sizing integration tests and real offline CLI exercise the
interface. Existing full-suite behavior guards execution compatibility.

The change adds a report to the existing CLI-first architecture. No structural
diagram, concurrent state machine, retries or external mutation are applicable.
