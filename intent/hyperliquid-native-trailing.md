# Intent: Hyperliquid Native Trailing
Owner: /root. Authority: AK's 2026-09-22 issue + implementation request. Endpoint: local.
Problem: documented exchange trailing support is not integrated. Desired outcome: opt-in exchange trailing with explicit continuous-mark semantics and conservative reconciliation.
AC1: distinguish documented native functionality, available adapter and actual account-scoped readback.
AC2: prepare/submit evidenced trailingStop actions with dry-run default and eligibility guards; reuse ordinary orderStatus/cancel by native ID.
AC3: preserve native fixed SL for partial entries; opt-in trailing after entry terminality and full SL coverage; persist before send; unknown outcomes never resent or adopted by resemblance; restart/partial exit/flat cleanup remain safe. Existing local nine-minute policy is default.
AC4: behavior tests, separate offline functional smoke using real SDK signing/SQLite, independent verification, and updated docs.
Constraints: no live operations, expanded asset set, silent policy migration or new store. Managed native policy initially uses frozen ATR quote distance, not percentage/activation customization.
Risks: app contract precedes public SDK/docs; missing client order IDs make unknown acknowledgements unrecoverable automatically. No live exchange behavior will be claimed verified.
