# Trading essentials: planning entry point

The initial discovery draft is superseded by the user-scoped 2026-09-12 design.
This is proposed functionality, not a claim that multi-venue trading is implemented.

- [Intent and requested instruments](../../intent/multi-venue-protection.md)
- [Capability, protection and journal specification](../../specs/multi-venue-protection.md)
- [Implementation slices and acceptance scenarios](../../plans/multi-venue-protection.md)
- [Archify main component/data path](../architecture/multi-venue-trading.html)
- [Archify main trade path and coverage failure](../architecture/protected-trade.html)
- [Archify signals, harnesses and account-wide history](../architecture/signals-and-journal.html)
- [Notification recommendation and sync cadence](trading-notifications.md)

KIS gold is GLD. Signal and execution instruments are distinct. Each entry requires
both SL and trailing policies; native providers are preferred only when their exact
semantics and target-instrument eligibility are verified. KIS native protective
SELL and trailing support remains unverified; the local fallback has explicit
worker/session limitations. One active strategy owns each account/instrument.
Completed cycles are reconciled into the existing trade-journal contract on request
or a schedule. Actual venue history includes agent, HTS and Hyperliquid web trades,
even without local protection ownership. Unknown strategy stays unassigned.
Future strategy skills feed notifications, then manual requests or explicitly
configured automatic execution through shared harness-neutral gates.

Archify official tools were obtained in a temporary work directory; no persistent
skill or host hook installation was performed. Tracked workflow diagrams live in
`docs/architecture/`; local SDLC receipts under `reports/sdlc/` are not shipped.
