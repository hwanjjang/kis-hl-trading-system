# Issue 38: Jev long/short/wait timing opinion

Owner: main agent. Route: implementation / local. Authority: AK's 2026-09-26 request to publish an issue and implement it; no commit, push, live order, paid TypeSafe call or activation.

Give strategy reviews an independent, calibrated trade-timing opinion from TypeSafe AI's Jev model: one Choice question with options `long`, `short`, `wait`, returning probabilities and confidence. The opinion is advisory reference evidence retained with the decision record; it never authorizes, sizes, blocks or places an order. Hermes decides when to request it; deterministic code builds the request, validates the answer and gates on confidence.

Acceptance (issue 38): AC1 offline dry-run request shape and state limits; AC2 response validation, confidence gating and fail-closed unavailable results; AC3 optional `timing_opinion` binding in `strategy decide` with required disagreement note; AC4 offline CLI smoke against a local HTTP stub plus decide/list on temporary SQLite with no key leakage; AC5 owner docs and full unittest suite.

Exclusions: live TypeSafe calls in tests, scheduling, execution gating, sizing, short trading. Risk: Jev answer quality for market timing is unverified; thresholds are conservative starting values.

## Pre-merge authority amendment — 2026-09-28

AK: "pre-merge까지 진행" after confirming TYPESAFE_API_KEY works (one real `strategy opinion` call returned jev-1.13.0, available, no key in output). Endpoint changes from local to pre-merge: commit, push branch `feat/issue-38-jev-timing-opinion`, open a PR to `main`, read CI, obtain an independent cross-provider review (Codex/OpenAI, latest GA model, medium effort, auto mode, isolated clone) and apply corrections. Merge, auto-merge, merge queue, live orders, production activation and credential transfer remain prohibited. Existing stage counters and receipts persist.
