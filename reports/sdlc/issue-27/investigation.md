# Investigation

Signals accepted only enter. ExecutionStore had one owner per account/instrument and
durable intent/attempt IDs. Supervisor already reconciled fills, bounded exits and
scoped flat cleanup; gateway originally classified all non-entry attempts as sells.
Native trailing has no client ID or supported watermark-preserving resize. Therefore
adds extend the same owner and use retained native orders plus a verified full-size
overlay, with inherited local backup required. No scheduler or second executor.

Official Hyperliquid sources checked 2026-09-24:
- https://hyperliquid.gitbook.io/hyperliquid-docs/trading/account-abstraction-modes
- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/spot
- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals

Unified balances come from spot clearinghouse state; segment accountValue cannot be
summed into them. Initial reconciliation supports explicit unified USDC-only balances;
other modes/valuations are rejected. activeAssetData supplies independently validated
account/instrument buying power; smaller directional quantity is conservative.
Remaining live uncertainties are in docs/trading-operations.md. No live reads or writes.
