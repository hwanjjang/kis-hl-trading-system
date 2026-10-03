# Issue 28: 50% discretionary take profit with residual SL/TS protection

Source: https://github.com/hwanjjang/kis-hl-trading-system/issues/28, plan comment
https://github.com/hwanjjang/kis-hl-trading-system/issues/28#issuecomment-5973905056,
and AK's explicit request on 2026-10-04 to comment and proceed to pre-merge.
Owner: Claude Code (main). Route: implementation / behavior / pre-merge.

## Scope and authority

Add one Hyperliquid-only lifecycle for an explicitly identified discretionary
take-profit decision that reduces the current owned position by 50%, then keeps the
residual under the existing fixed-SL and TS protection. Reuse the account owner,
SQLite attempts, reduce-only orders and protection readback. Commit, push, open a
PR, run CI and cross-provider PR review/corrections. No live order, `--live`
command, merge, auto-merge, merge queue or permission change is authorized. KIS
partial take profit and any top-detection strategy are excluded and fail closed.

## Acceptance criteria

- AC1: A TP decision freezes 50% of the reconciled remaining position (including
  add fills), rounded down to the lot step; a below-minimum target or residual is
  reported without any order and never promoted to a full exit. A profitable TS
  remains a full-position exit.
- AC2: One persisted decision produces at most one reduction: repeated requests,
  reused decision IDs, restarts and UNKNOWN outcomes never resubmit or re-halve;
  fills are reconciled before any retry within existing attempt/deadline budgets.
- AC3: After the TP, the residual is verified covered by existing reduce-only SL/TS
  without cancelling/recreating trails or resetting watermarks; TP completes only
  with verified coverage, and adds are blocked while a TP is active.
- AC4: A competing full SL/TS exit supersedes the TP: no oversell, no duplicate TP,
  no protection recreation for a flat position, and owned TP orders are cleaned up.
- AC5: Unsupported paths fail closed (KIS, non-protected owners, pending exit/add);
  the CLI contract and exit-quantity owner docs describe the actual behavior and
  the unverified live risk.

Risks: Hyperliquid handling of oversized resting reduce-only SL/TS after a position
shrinks is not verified offline. Offline success does not certify live behavior.
