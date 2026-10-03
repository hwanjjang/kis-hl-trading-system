# Issue 15 implementation and pre-merge plan

Consume [intent](../intent/issue-15.md) and [spec](../specs/issue-15.md).
The execution notebook is .planning/issue-15-margin-and-short-trailing, owned by
OpenAI /root; generated evidence stays in reports/sdlc/issue-15-51.

1. Preserve issue 51 changes and pull main; retain only margin code/tests/docs.
2. Verify calculate_isolated_margin and optional strategy size report. Existing
   intended-red evidence shows missing helper/report; reuse rather than manufacture.
3. Run focused green, full regression after pull, and additional offline CLI smoke.
4. Check manual source, real CLI capture and rendered PDF; stage only maintained files.
5. Commit/push a feature branch and open a PR closing issue 15 on future merge.
6. Independent Anthropic reviewer examines exact PR/candidate, tests and documents.
   Correct selected findings and repeat affected tests/review until PASS.
7. Verify CI, head/base, protections and disabled merge automation. Stop pre-merge.

User scenario S1 (AC1, AC3): operator with Python 3.11/runtime dependencies runs
the isolated ETH fixture at its replay clock; sees quantity 10, required 145,
shortfall 45 and order_authorized false. Wrong totals/changed authority fail.
Scenario S2 (AC2): operator changes scope or removes metadata; report is unavailable
with reasons while valid sizing remains. Cross mode and KIS are not applicable.
Tests: tests/test_isolated_margin.py; manual: docs/manuals/risk-units/usage.md.

Changed ownership: kis_hl/risk.py owns arithmetic; strategy_tools.py owns evidence
and advisory output; tests own behavior; docs/strategy-tools.md owns input/output;
operations/design/README provide context. No venue adapter changes are required.
Rollback removes the report addition; no database or live-state rollback is needed.

Risk: incorrect/missing tiers can misstate margin; reject unresolved references.
SL fill and liquidation behavior remain unverified live and explicitly constrained.
No repository read-only staged/outgoing/CI content checker exists; inspect git diff,
staged file list and outgoing range manually and record the enforcement gap.
Maintained docs/manual and PR comments retain durable conclusions; detailed local
logs and receipts are transferred to reviewer and final PR evidence attachments.
