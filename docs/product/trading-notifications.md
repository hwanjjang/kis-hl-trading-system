# Trading notifications and deferred journals

Status: proposed, 2026-09-12. No channel, scheduler or automatic execution enabled.
Contract: [multi-venue specification](../../specs/multi-venue-protection.md), sections 6–7.

## Recommendation

Start with a private Telegram bot chat for prompt notifications and a SQLite inbox
for durable local inspection. Keep the first adapter outbound-only: read the alert,
then request execution in Codex, Claude Code or Hermes using its signal ID. This is
an implementation recommendation, not a claim about measured notification latency.
Add automatic execution per explicit strategy policy after replay and risk checks.

| Channel | Documented facility | Suitability and tradeoff |
| --- | --- | --- |
| Telegram | Bot `sendMessage`, inline keyboards and incoming updates via long polling or webhook | Recommended personal workflow; bidirectional interaction can be added without making it part of the first release |
| ntfy | HTTP publishing, priorities and notification actions; self-host configuration | Alternative for dedicated push and operator-controlled hosting; adds server/authentication and mobile delivery setup if self-hosted |
| Slack | Incoming webhook channel messages | Good when an existing workspace is already the operator's notification destination; interactive execution needs a separate authenticated integration |

Sources: [Telegram Bot API](https://core.telegram.org/bots/api#sendmessage),
[Telegram updates](https://core.telegram.org/bots/api#getupdates),
[ntfy publishing](https://docs.ntfy.sh/publish/),
[ntfy configuration](https://docs.ntfy.sh/config/),
[Slack incoming webhooks](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/).
These facilities were checked on 2026-09-12; no delivery experiment was performed.

Telegram setup later needs a bot token and an allowed private chat ID. Slack uses
a secret webhook URL; ntfy needs a configured endpoint/topic and access controls.
Keep these outside SQLite event payloads and logs. Notification adapters do not
receive exchange signing credentials. Provider success confirms API acceptance,
not human reading. Do not describe retry as guaranteed exactly-once delivery.

## Event policy

- Strategy opportunity: prompt alert with signal ID, expiry, analysis instrument,
  execution candidate, reason and manual/automatic mode.
- Protection failure, unknown orders or external interference: prompt operational
  alert; already-authorized protection does not wait for notification delivery.
- Journal refresh: summary of imported fills, completed/pending cycles and gaps.
- Daily review: effective realized metrics, unassigned/mixed attribution and sync
  health, with currencies separate.

User-selected default: history ingestion and journal reconciliation every three
hours (`journal.sync_interval = 3h`), adjustable in settings, plus on-demand
refresh. An optional daily review digest is separate. This is independent of real-time protection and strategy evaluation.
Tune to actual activity and retention: Hyperliquid documents up to 2,000 fills per
`userFillsByTime` response and availability of only the latest 10,000 fills. Long
outages or high activity can therefore require statement backfill. See the
[official info API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint).

No cadence guarantees completeness without observed coverage. A missing opening
history/cost or exhausted retention produces a visible pending journal interval.
An agent-generated account narrative cannot replace those missing source records.
