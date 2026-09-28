# Implementation plan

Owner: main. Upstream: intent/issue-38.md, specs/issue-38.md, issue #38. Endpoint local; no commit/push.

1. Tests first: `tests/test_timing_opinion.py` (request shape/limits, parser validation, gating, HTTP errors via injected opener, dry-run CLI) and decide-binding cases in the existing strategy tools tests. Observe intended failure.
2. `kis_hl/timing_opinion.py`: build_request, post, parse, gate, request_opinion.
3. `kis_hl/strategy_tools.py`: optional `timing_opinion` validation in `ingest_decision`.
4. `kis_hl/operations_cli.py`: `strategy opinion --input [--dry-run] [--model]`.
5. Docs: docs/strategy-tools.md, trend-strategy SKILL.md, README.md, .env.example, docs/architecture.md.
6. Smoke: `scripts/smoke_timing_opinion.py` with a local HTTP stub and temporary SQLite DB.

Validation: `python3 -m unittest tests.test_timing_opinion tests.test_strategy_tools -q`, full discovery, smoke script, `git diff --check`. Rollback: remove the command/module; stored decisions keep the extra field harmlessly. Blast radius: strategy decide validation only when `timing_opinion` is present.

## Correction plan (verification round 1)

1. Regression tests: CR/LF/space keys and non-HTTPS URL rejected without echo; BadStatusLine/IncompleteRead/deep JSON/oversized model unavailable; usage sanitized; 302 not followed (local stub); forged/inconsistent attached opinions rejected; dry-run hash.
2. timing_opinion.py: key/endpoint validation, no-redirect opener, broader transport catch reporting type only, 1 MB cap, shared answer validation with Decimal for attached opinions.
3. Docs/spec/CLAUDE.md pairing row. Re-run focused tests, smoke, full suite; renewed independent verification by the same separate context.
