# Protected trading implementation intent

Source: user authorized all remaining planned functionality except notifications,
through PR creation. Endpoint: pr. No merge, deployment or real order execution.
Canonical product design: [multi-venue plan](multi-venue-protection.md).

- PT1: KIS domestic/US and HL account/quote/chart/history reads with explicit
  instrument identity, pagination, sanitized errors and environment separation.
- PT2: Actual-fill journals accept external HTS/web execution, are idempotent,
  cost-aware and gap-aware, retaining the existing nine metric contract.
- PT3: Journal synchronization defaults to 3h, configurable, runs on demand or
  independently of a harness, and recovers without duplicate jobs or records.
- PT4: Durable previews/orders and native-first independent SL/trailing selection
  fail closed on unknown capabilities, quantity, ownership or transmission outcome.
- PT5: Account supervision, partial-fill coverage, bounded exit/recovery and
  strategy-signal interfaces share risk gates and preserve existing HL safety.
- PT6: Tests, smoke, retained design, independent verification and PR review
  accurately distinguish exercised behavior from unverified exchange behavior.

Notification transport, destination choice and delivery are excluded. No new
trading strategy is invented. Future automation requires an explicit registered
strategy/risk grant; the user has not authorized placing actual orders in this task.
GitHub repo hwanjjang/kis-hl-trading-system is accessible via configured ak-ongyeol
account; local changes may be committed/pushed and a PR created, not merged.
