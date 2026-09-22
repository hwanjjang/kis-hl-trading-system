# Multi-venue protected trading implementation plan

Status: proposed local plan, 2026-09-12. Not an instruction to submit orders.
Intent: [scope](../intent/multi-venue-protection.md).
Spec: [contract](../specs/multi-venue-protection.md).
Notebook owner /root: [.planning/multi-venue-protection](../.planning/multi-venue-protection/task_plan.md).

## Ordered slices

| Slice | Files / responsibility | Required proof before next slice |
| --- | --- | --- |
| 0. Capability evidence | Instrument/capability contracts and KIS/HL skill references | Exact KIS enum, side trigger, post-trigger type, sessions, expiry and target symbol availability; unknown stays disabled |
| 1. Read-only foundation | KIS chart/position/order/fill/buying-power methods; explicit mappings; CLI; tests | KOSPI, SPX/NDX or explicitly labeled SPY/QQQ series; pagination; adjustment/freshness; GLD/QPUX/DRAM quote routes; account separation |
| 2. Durable previews | instruments/capabilities/execution_storage; order preview | Signal vs execution prices; integer/share and HL lot/tick rules; cash/margin/FX/exposure bounds; no signed calls in preview |
| 3. Orders and reconciliation | Thin venue methods plus execution coordinator | Correct domestic vs overseas enums; partial fills, cancel/amend races, UNKNOWN handling, dedupe, full snapshot reconciliation |
| 4. Entry protection | Protection policies/providers and coverage events | Actual fill-to-stop coverage, bracket activation gaps, stop rejection, cancellation gaps, available sell quantity, triggered-but-unfilled stop-limit |
| 5. Supervised trailing | Account supervisor plus existing Trail/runner handoff | Per-account ownership, multiple positions, frozen per-strategy config, stale feeds, crashes/reconnects, terminality and overnight expiry |
| 6. Journal integration | Account-wide fill/cost ledger, journal outbox, sync CLI and scheduler contract | Agent/HTS/web inclusion, on-demand/scheduled overlap, history gaps, legacy dedupe, unassigned/mixed attribution, audited revisions and skill metrics |
| 7. Signals and notification | Versioned signal contract, SQLite notification adapter, harness-neutral CLI | Observe/manual modes first; outbound Telegram or selected adapter; stale/duplicate signals, provider timeout, secret redaction; no strategy skill invented |
| 8. Configured automation | Explicit execution grants and signal claim through existing coordinator | Manual/automatic race, grant expiry, changed preview, delivery failure policy, risk gates and kill switch; requires an actual strategy contract |
| 9. Release candidate | CLI/docs, capability fixtures, integration/replay evidence | Independent verification and venue-specific paper tests; explicit unresolved-live-behavior list; no implicit production enablement |

Start with account reads and replay; do not begin with a monolithic autonomous
strategy runner. The existing account CLI is usable independently. Each slice
updates its owner docs, endpoint skills, focused tests and schema together.

Journal ingestion/reconstruction in slice 6 can start immediately after slice 1:
it must work without any local order having been created, and does not depend on
slices 3–5. Link to managed execution later. Notification storage/adapters in slice
7 can likewise be tested using fixture signals before strategy skills exist.
All harnesses invoke the same CLI. Choose one configured scheduler for a job; do
not install independent Codex/Claude Code/Hermes copies of the same periodic sync.

## Behavioral scenario matrix

| Scenario | Criteria | Observable pass / important failure |
| --- | --- | --- |
| Domestic and US order types differ | MV2 | Unsupported enum/side/session fails before network write; no name-based normalization |
| Stop-limit semantics incomplete | MV2/MV3 | No native SL provider selected; explicit healthy local fallback or blocked entry |
| Index differs from ETF/perpetual | MV1 | Stop/sizing uses traded price/ATR; KOSPI/KOSPI200 and NDX/QQQ labels retained |
| Full and partial entry fills | MV3 | Every actual exposure has coverage/deadline; parent ack is never protection proof |
| Native child rejected or delayed | MV3 | Bounded compensation / intervention; no fictitious protected state |
| Native stop races local trailing | MV3 | One exit owner; KIS reservation/cancel terminality; HL reduce-only; no net short |
| Timeout after send / crash before ack | MV3 | Reconcile persisted UNKNOWN attempt; no blind duplicate submission |
| Gap below stop-limit / price band / market closed | MV2/MV3 | Triggered-open and residual exposure visible; permitted escalation only |
| Stop expiry / session change / DST | MV2/MV3 | Versioned calendar and per-order validity, coverage renewal or block |
| Worker dies / feed stale | MV3 | New entries blocked; native protection retained; local outage exposed |
| Two strategies enter one account/instrument | MV3/MV4 | Second entry rejected atomically; one cycle owns protection and journal |
| BTC and ETH concurrent on one account | MV3 | One supervisor owns lock and routes positions; no duplicate workers |
| Complete cycle with partials and fees | MV4 | One idempotent journal, correct weighted prices/net costs and snapshot |
| Missing fills/costs / duplicate reconnect events | MV4 | JOURNAL_PENDING or deduped existing record; no fake finalization |
| KRW/USD/USDC and stock split | MV1/MV4 | Explicit currency/corporate-action handling; no mixed-currency totals |
| Read-only/paper isolation | MV3/MV5 | No live mutation or realized journal from a paper intent |
| External HTS/web-only cycle | MV4 | Same actual-fill journal without local order intent, protection adoption or live-asset eligibility filtering |
| Manual trade mixes with managed position | MV3/MV4 | Actual net cycle retained as mixed; ambiguous strategy attribution never fabricated |
| Configurable three-hour schedule | MV4/MV5 | Default 3h; validated interval changes retain cursor; immediate manual run; restart coalesces missed ticks |
| Requested and scheduled sync overlap | MV4 | One account sync lease; overlap deduped; cursor and facts commit together |
| Missing opening history / exhausted retention | MV4 | Incomplete interval visible; statement import required; zero current balance does not imply no trades |
| Equal-timestamp page boundary / cumulative KIS row | MV4 | No skipped or double-counted fills; unsupported complete traversal remains pending |
| External reversal / fees / funding | MV4 | Quantity and fee conservation at zero crossing; total fees not double-counted |
| Late correction / legacy manual journal overlap | MV4 | Explicit linkage or audited supersession; only effective revision in current metrics; old snapshot retained |
| No harness session during journal schedule | MV4/MV5 | Same local sync service runs independently; no dependence on agent conversation history |
| Repeated strategy evaluation / expired signal | MV3/MV5 | One signal identity; expired or changed preview cannot execute |
| Manual request races automatic execution | MV3/MV5 | One atomic signal claim; one persisted order attempt |
| Notification timeout / duplicate message | MV3/MV5 | Delivery uncertainty recorded; no duplicate order; configured fresh-entry policy enforced |
| Unauthorized callback / missing grant | MV3/MV5 | No exchange mutation; acknowledgement is not execution authority |

Each implementation slice follows intended Red → Green → post-change regression →
a separate local functional smoke. Use stdlib unittest and fake transport for
behavior tests, recorded ticks/fills and temporary SQLite for integrated replay.
Run authorized read-only vendor probes separately; real order smoke is not part of
this planning authorization. Mock success is never labeled live verification.

Independent verification challenges state transitions, quantity reservation,
coverage gaps, restart idempotency, and journal accounting; it does not edit the
builder branch. Preserve a distinct report. A later PR/integration endpoint needs
its own authorization and SDLC gates.

## Risk, alternatives and rollback

Highest risk: ambiguous broker state causes an unprotected exposure or duplicate
sale. Prioritize venue-specific contracts and immutable attempts over automatic
retry. Protect data-model compatibility with additive versioned SQLite migrations.

Rejected alternatives: reuse index prices as ETF stops; claim all stop-limit orders
are protective stops; automate HTS UI instead of documented APIs; use one existing
trailing worker per position under the current account lock; auto-switch venue on
failure; journal on order acceptance; silently broaden stock-age policy to ETFs.

Rollback disables new entries and new code paths while retaining reconciliation,
existing protective orders and durable records. Never roll back by dropping fills,
revoking protection or deleting a journal. Before schema rollback export a local
backup without credentials; production data migrations require verified compatibility.

## Architecture deliverables

- [Component map](../docs/architecture/multi-venue-trading.html)
- [Protected execution and deferred journal workflow](../docs/architecture/protected-trade.html)
- [Harnesses, signals and account-wide journal path](../docs/architecture/signals-and-journal.html)
- [Notification recommendation](../docs/product/trading-notifications.md)

These are proposed views of the spec. Existing code owns the current behavior.
The component map shows the main analysis/state path and recovery inspection;
protective submissions use the same order coordinator even where secondary control
edges are omitted for readability. Workflow continuation past coverage verification
is permitted only on success; unknown/rejected coverage takes intervention.
