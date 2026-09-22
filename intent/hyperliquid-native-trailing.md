# Intent: Hyperliquid Native Trailing
Owner: /root. Authority: AK's 2026-09-22 issue + implementation request. Endpoint: local.
Problem: documented exchange trailing support is not integrated. Desired outcome: opt-in exchange trailing with explicit continuous-mark semantics and conservative reconciliation.
AC1: distinguish documented native functionality, available adapter and actual account-scoped readback.
AC2: prepare/submit evidenced trailingStop actions with dry-run default and eligibility guards; reuse ordinary orderStatus/cancel by native ID.
AC3: preserve native fixed SL for partial entries; opt-in trailing after entry terminality and full SL coverage; persist before send; unknown outcomes never resent or adopted by resemblance; restart/partial exit/flat cleanup remain safe. Existing local nine-minute policy is default.
AC4: behavior tests, separate offline functional smoke using real SDK signing/SQLite, independent verification, and updated docs.
Constraints: no live operations, expanded asset set, silent policy migration or new store. Managed native policy initially uses frozen ATR quote distance, not percentage/activation customization.
Risks: app contract precedes public SDK/docs; missing client order IDs make unknown acknowledgements unrecoverable automatically. No live exchange behavior will be claimed verified.

## 2026-09-22 PR correction amendment
AK authorized a PR response and SDLC corrections after review. Publish verified changes to existing PR #21; no merge, live order or deployment authority. AC3 now explicitly distinguishes never-accepted rejection, pending watermark, and termination of an established trail: rejection/unknown remains manual intervention with fixed-SL monitoring, waiting alone never forces exit, and an established terminal trail retains residual-exit policy. AC2 includes retracement precision validation before entry and fail-closed request/readback semantic matching. AC4 requires regressions for each finding, integrated offline smoke and renewed independent verification. Earlier verification assumed rejection should exit; that expectation is superseded.
