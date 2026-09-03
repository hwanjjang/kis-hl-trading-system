# User Flows

## Flow notation

- `→` normal progression
- `◇` decision or guard
- `✕` fail-closed end
- Screen IDs refer to `screen-inventory.md`.

## UF-01 Start an operating session

**Actor:** P-01, P-02, or P-04
**Job:** JTBD-01

`CORE-001 command index → select database path/environment → CORE-002 or CORE-003 command-group index → choose a leaf surface`

Branches:

- Missing leaf command → root help and exit 2.
- Invalid argument/choice → argparse usage error and exit 2.
- Runtime command exception → structured failure log, JSON error on stderr, exit 1.

Completion: the user has selected an exact command, database, inputs, and intended dry-run/live mode.

## UF-02 Refresh the daily review dataset

**Actor:** P-02
**Jobs:** JTBD-03 through JTBD-09 and JTBD-18

`ASSET-002 seed eligibility → KISMAP-001 seed KIS routes → REFMAP-001 seed secondary routes → ASSET-005 collect observed universe → ASSET-004 verify metadata → ASSET-006 collect funding → ASSET-007 collect spread → KISMAP-004 collect active KIS quotes → REFMAP-004 collect active secondary quotes → HISTORY-001 collect daily bars`

At each batch surface:

`◇ per-symbol success?`
`yes → store unless --no-store → continue`
`no and fail-fast=false → record failed/skipped cause → continue`
`no and fail-fast=true → ✕ exit 1`

Completion: outputs identify requested/succeeded/failed/skipped/stored counts and the database contains the enabled successful records.

## UF-03 Review a newly observed trade.xyz market

**Actor:** P-02 with P-03 review
**Jobs:** JTBD-03 through JTBD-06

`ASSET-005 shows new/unmapped symbol → ASSET-001 resolve symbol → ASSET-003 inspect curated row`

Branches:

- No curated row or `tradable=false` → remain observation-only; no live eligibility.
- Curated and tradable → ASSET-004 metadata verification → ASSET-006/007 funding and spread review.
- Missing from latest live universe, failed verification, or unacceptable manually reviewed evidence → no live order.

Completion: the market is classified as observation-only or eligible under the existing curated policy. This flow does not edit the curated code seed.

## UF-04 Fetch one reference observation

**Actor:** P-01 or P-02
**Job:** JTBD-02, JTBD-07, or JTBD-08

Direct source:

`MARKET-001 or MARKET-002 → validate KIS config/token → fetch → ◇ KIS HTTP/body success → optional --store → JSON result`

Mapped source:

`KISMAP-002 or REFMAP-002 → select active mapping → KISMAP-003 or REFMAP-003 → ◇ mapping exists and active → fetch → optional --store → JSON result`

Failure branches:

- Mapping missing/inactive → ✕ exit 1 without pretending the asset is covered.
- KIS HTTP failure or `rt_cd != "0"` → ✕ exit 1 and do not store a successful observation.
- External timeout/rate limit/provider change → ✕ exit 1 with error text; retry is an operator decision except built-in client retries.

## UF-05 Inspect account state before action

**Actor:** P-01 or P-03
**Job:** JTBD-10

`ACCOUNT-001 → use explicit --user or configured account address → fetch main perp state → optional spot state → optional named dex states / ALL_DEXES → review JSON`

Branches:

- Missing address → ✕ exit 1.
- Account address is an API-wallet address rather than the funded account → upstream may return empty state; treat as invalid evidence.
- Optional aggregate unavailable → rerun without `--all-dexs` and/or with explicit repeated `--dex` values.

Completion: the user has an address-labelled state response suitable for manual review.

## UF-06 Evaluate BTC breakout without execution

**Actor:** P-01 or P-03
**Job:** JTBD-11

`MARKET-004 optional candle inspection → STRATEGY-001 fetch fixed 3h BTC perpetual candles → validate lookback → compare latest closed candle close with prior high(s) → return should_enter`

Branches:

- Insufficient/invalid candles or lookback → ✕ exit 1.
- `should_enter=false` → end with no order.
- `should_enter=true` → review as one signal input; no order is sent.

## UF-07 Monitor BTC and prepare or execute a plan

**Actor:** P-01
**Jobs:** JTBD-12 and JTBD-15

`STRATEGY-002 → obtain explicit ATR or fetch daily BTC perpetual candles → open maintained BTC spot allMids stream → build closed 3h spot candles → ◇ breakout → create 80-USDC-default BTC perpetual entry plus ATR×2-default stop plan`

Branches:

- No breakout before stop condition/max messages → monitor status with no execution.
- Default mode → prepare dry-run entry and stop; optionally store both and protective record.
- `--live` → apply live order guards and submit entry then reduce-only stop.
- Stream staleness/reconnect exhaustion/order error → ✕ exit 1 or stopped status according to runner behavior.

Completion: returned monitor status and execution list show exactly what was prepared/submitted and stored.

Known gap: the live path does not reconcile an existing BTC position or wait for confirmed average fill before deriving stop coverage.

## UF-08 Prepare a manual order and promote it to live

**Actor:** P-01 with P-03 review
**Jobs:** JTBD-13 and JTBD-14

`ASSET-001 resolve symbol → ORDER-001 without --live → review resolved asset/request payload → independently review account, evidence, and session policy → repeat exact command with --live`

Live guard sequence:

`◇ allowlisted asset? → ◇ trade.xyz recent verification if applicable? → ◇ signing credentials present? → ◇ underlying session open for non-reduce-only trade.xyz entry or explicit override? → submit`

Any failed guard → `✕ no exchange action, exit 1`.

Completion: dry-run returns `dry_run=true`; live success returns `status=submitted`, `dry_run=false`, response, timestamp, and stored ID unless storage is disabled.

Known gap: dry-run does not evaluate or include the underlying session decision, so session preflight remains a manual review until the applicable live path runs.

## UF-09 Create a manual protective stop

**Actor:** P-01
**Job:** JTBD-15

`ORDER-001 --order-type stop-market --trigger-price ... --reduce-only → validate trigger and reduce-only requirement → dry-run or live submit → store order submission → store protective-order record`

Branches:

- Missing trigger price or reduce-only → ✕ validation error.
- Reduce-only would increase a position or entry is not filled → exchange rejection in live mode.
- Storage disabled → valid command result but no local audit row.

Completion: output includes the order result and, when stored, `stored_id` plus `protective_order_id`.

## UF-10 Record and review a completed trade

**Actor:** P-01 and P-03
**Jobs:** JTBD-16 and JTBD-17

`◇ position is fully flat? → JOURNAL-001 enter venue/symbol/strategy/side/timestamps/average prices/quantity/fees and optional authoritative realized PnL → derive outcome, return percentage, holding days → store record and statistics snapshot → JOURNAL-002 filter and recalculate aggregate statistics`

Branches:

- Position open, unmatched quantities, or unreconciled partial fills → do not create a record.
- No wins or no losses → affected averages/ratios remain null.
- Breakeven → include in trade count, exclude from decisive win-rate and ratio denominators.

Completion: one flat-to-flat record is stored and current statistics are reproducible from raw journal fields.

## UF-11 Recover from a partial batch

**Actor:** P-02 or P-04
**Job:** JTBD-18

`batch result → inspect results where status=failed or skipped → classify mapping/policy/external/transient cause → correct only the input/config/external condition in scope → rerun with explicit symbols`

Completion: the rerun output isolates the previously affected symbols and preserves earlier successful idempotent data.

## Assumptions

- **A-014:** “Promote to live” means the operator manually reruns a reviewed command with `--live`; no persisted promotion token links the two calls.
- **A-015:** Batch reruns are safe only where the underlying storage operation is idempotent or duplicate behavior is understood; the flow does not promise universal deduplication.
- **A-016:** Manual review steps are operational requirements expressed in documentation, not enforced UI gates.

## Unresolved risks

- The exact compensation path after a live entry succeeds but stop submission fails is not implemented as a durable state machine.
- Process interruption between external success and local persistence can leave incomplete audit records.
- There is no command-level correlation ID connecting multiple surfaces in one operating session.
