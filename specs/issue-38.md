# Jev timing opinion contract

Add `kis_hl/timing_opinion.py` (request builder, stdlib HTTP client, strict parser, confidence gate) and expose it as `strategy opinion`. Extend `ingest_decision` with an optional, validated `timing_opinion`. No schema migration: the opinion rides inside the existing immutable signal payload.

## Review input

`instrument` (non-empty string, bound to the decision's `signal_instrument`), `snapshot_id` (bound to `setup_input.snapshot.id`), `asof_ms` (positive integer, retained but not sent), `horizon` (short text such as "daily swing"), `facts` (1–40 named values; keys ≤ 64 chars; values are strings ≤ 300 chars, booleans, integers or finite numbers; no nesting), optional `notes` (≤ 10 strings ≤ 300 chars) and optional `min_confidence` (decimal in (0, 1], default 0.5). Facts should carry tool outputs and named buckets computed by deterministic tools; Jev must not do arithmetic or date comparison.

## Request

`POST {TYPESAFE_BASE_URL or https://api.typesafe.ai}/v1/systemone` (HTTPS, or HTTP to loopback only), `Authorization: Bearer $TYPESAFE_API_KEY`, 10 s timeout, no retries, no redirects, 1 MB response cap. Keys with whitespace/control characters are rejected without echo; transport failures report only the exception type. Body: `model` (default pinned `jev-1.13.0`, override with `--model` or `TYPESAFE_MODEL`), `state` `{instrument, horizon, facts, notes}` and one Choice question `timing` whose criteria keys are exactly `long`, `short`, `wait` with fixed English rubrics. `input_sha256` hashes the canonical request body. `--dry-run` returns URL, body and hash without a key or network.

## Output

Always `tool: timing_opinion`, `provider: typesafe`, `status`, `instrument`, `snapshot_id`, `asof_ms`, `requested_model`, `input_sha256`, `min_confidence`, `advisory: true`, `order_authorized: false`. Available results add answering `model`, raw `choice`, decimal-string `probabilities` and `confidence`, `band` (`high` ≥ 0.8, `medium` ≥ min, else `low`) and `effective_opinion` (raw choice unless confidence < min, then `wait`), plus token `usage`. Unavailable results carry `reason` and null opinion fields. HTTP 401/422/429/529/other, timeout/connection errors, non-JSON, wrong answer type, option-set mismatch, non-finite/out-of-range probabilities, |sum − 1| > 0.01, choice not a highest-probability option, or confidence outside [0, 1] are unavailable, never a guessed opinion. A missing key is a configuration error (non-zero exit). The key never appears in output.

## Decision binding

When `strategy decide` receives `timing_opinion`: it must be an opinion-tool object with `order_authorized: false`, matching `signal_instrument` and `setup_input.snapshot.id`, a known status, `provider: typesafe`, `advisory: true`, valid probabilities with the choice as a highest option, decimal confidence, and `band`/`effective_opinion` equal to the recomputed gate. `enter`/`add` whose effective opinion is not `long` (including unavailable) requires a non-empty `opinion_note`. The opinion never replaces the predicate, confluence or management checks and grants no authority. Records without it are unchanged.

## Semantics

Advisory only. `short` means "avoid new long exposure / review protection" in the long-only strategy, never a short order. Hermes decides when to ask; the skill states how it weighed the opinion.

Verification: unit tests with injected HTTP opener; offline CLI smoke against a local stub server; full unittest suite. Alternatives rejected: typesafe SDK dependency (adds a package for one POST), using the opinion as an execution gate (violates authority boundary), Score/Noul primitives (a three-way stance is a Choice).

## Verification corrections (2026-09-26)

Independent verification round 1 found a key echo via CR/LF keys, followed redirects, escaping protocol exceptions and lenient decide binding. The contract above now includes those corrections; tie handling is unchanged (confidence gating already covers flat distributions).
