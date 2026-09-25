# Plan: PR #32 review corrections

1. Tests (`tests/test_add_lifecycle.py`): add `test_protected_owner_with_cancel_entry_expires_unevaluated_add`, add `test_save_requires_explicit_time`, and change the rollback test to look up the tranche by id.
2. Code (`kis_hl/managed_execution.py`): remove the `now_ms=0` default from `save()`. Pass explicit times in `tests/test_manual_adoption.py`, `tests/test_managed_execution.py` and `tests/test_strategy_signals.py`.
3. Docs: reword `docs/trading-operations.md` and `docs/architecture.md` for R1/R2.
4. Diagram: add-termination node "Approval Expired" gets the sublabel "add not evaluated this tick", and the card wording is revised. Regenerate HTML and visual-check receipts.
5. Verify: targeted tests, full suite, smoke, `git diff --check`.
6. Independent verification by a separate Claude subagent context. Cross-provider PR review is skipped per AK.
7. Commit, push, update the PR #32 body, wait for CI, record the pre-merge readiness receipt. No merge.

Blast radius: `save()` signature only (all in-repo callers updated), plus docs and a diagram. Rollback: revert the commit.
