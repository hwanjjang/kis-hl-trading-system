# Issue 27: bounded conditional add

Owner: main agent. Route: implementation / local. Authority: AK's implementation request and issue 27; no live orders, activation, publication or merge.

Implement one immutable, explicitly authorized Hyperliquid long add per signal on an existing account/instrument owner. Reconcile total account balance for sizing independently from available funds. Preserve fixed stops and frozen ATR/watermarks and exit the entire remaining position. Hermes remains responsible for review and notification. Issue 28 partial take-profit is excluded.

Acceptance: AC1 account-total capital and ambiguous-collateral rejection; AC2 completed/fresh condition, bounded authority, exposure and durable replay gate; AC3 partial/completed add with tranche evidence and combined SL/TS, bounded failure; AC4 external-trail migration has no signed mutation and competing/partial exits close residual quantity with scoped cleanup; AC5 CLI/SQLite stub smoke, owner docs and changed-scope tests/diff check. Offline evidence only; no live behavior claim.
