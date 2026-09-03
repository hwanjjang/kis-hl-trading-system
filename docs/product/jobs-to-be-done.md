# Jobs to Be Done

## Job map

| ID | Job statement | Desired outcome | Main surfaces |
| --- | --- | --- | --- |
| JTBD-01 | When I begin an operating session, I want to confirm the available commands and local state target so that I do not act against the wrong database or environment. | Known command, database, key profile, and dry-run/live intent | CORE-001, CORE-002, CORE-003 |
| JTBD-02 | When I need a market observation, I want to fetch it from the intended source and symbol route so that I can compare like with like. | Source-labelled current or historical response | MARKET-001 through MARKET-004, KISMAP-003, REFMAP-003 |
| JTBD-03 | When trade.xyz changes its live markets, I want to detect additions, removals, and unmapped symbols without automatically approving them. | Observed-universe delta separated from curated eligibility | ASSET-005 |
| JTBD-04 | When I review an RWA asset, I want to see its curated eligibility and symbol resolution so that an alias or new listing cannot silently become live-tradable. | Explicit trade symbol, Hyperliquid coin, dex, class, and tradable state | ASSET-001, ASSET-002, ASSET-003 |
| JTBD-05 | When I may trade a trade.xyz asset, I want recent Hyperliquid metadata verification so that stale local mappings do not authorize a live action. | Timestamped success/failure check in the same SQLite database used by the order | ASSET-004, ORDER-001 |
| JTBD-06 | When I assess liquidity and carry, I want recent funding and spread evidence so that I can manually reject unsuitable exposure. | Per-symbol results with timestamps, values, and partial failures | ASSET-006, ASSET-007 |
| JTBD-07 | When KIS can cover an underlying, I want a curated KIS route and fetch result so that I do not guess market codes or symbols. | Active mapping plus KIS response and optional stored evidence | KISMAP-001 through KISMAP-004 |
| JTBD-08 | When KIS is unavailable or unsupported, I want a declared secondary reference route so that fallback data remains distinguishable from production market data. | Provider-labelled mapping and response | REFMAP-001 through REFMAP-004 |
| JTBD-09 | When I calculate ATR or trend context, I want a sufficient daily OHLCV history so that incomplete inputs do not appear valid. | Idempotently stored daily bars and visible per-symbol outcomes | HISTORY-001 |
| JTBD-10 | When I inspect an account, I want the requested main, spot, and HIP-3 state in one response so that I can review balances and positions before acting. | Address-labelled composite account response | ACCOUNT-001 |
| JTBD-11 | When a BTC 3-hour candle closes, I want the deterministic breakout result so that the signal can be reviewed independently from execution. | Resolved coin, breakout level, latest close, and `should_enter` | STRATEGY-001 |
| JTBD-12 | When I monitor BTC spot, I want any generated BTC perpetual entry and stop plan to remain dry-run unless I explicitly choose live mode. | Monitor status and zero or more traceable execution payloads | STRATEGY-002 |
| JTBD-13 | When I consider an order, I want to resolve, validate, and preview the exact request before signing so that unintended instruments or parameters are blocked early. | Dry-run payload with resolved asset and request | ORDER-001, ASSET-001 |
| JTBD-14 | When I submit a supported live order, I want eligibility, verification, credential, and session guards to run first so that failure is safer than unsupported exposure. | Submitted result only after applicable guards pass | ORDER-001 |
| JTBD-15 | When I create a protective stop, I want it to be reduce-only and stored with coverage and identifiers so that the intended protection is auditable. | Stop submission plus protective-order record | ORDER-001, STRATEGY-002 |
| JTBD-16 | When a position is fully closed, I want one completed-trade record so that performance review has a stable flat-to-flat boundary. | Stored record with prices, quantity, costs, return, outcome, and duration | JOURNAL-001 |
| JTBD-17 | When I review performance, I want return-based statistics filtered by strategy or symbol so that position size or mixed edges do not distort conclusions. | Nine contract-compliant metrics and underlying entries | JOURNAL-002 |
| JTBD-18 | When a batch partially fails, I want successful, skipped, and failed symbols reported separately so that I can retry only what needs attention. | Summary counts plus per-symbol cause/action/result | ASSET-006, ASSET-007, KISMAP-004, REFMAP-004, HISTORY-001 |

## Functional job sequence

1. **Orient:** JTBD-01.
2. **Build the eligible universe:** JTBD-03 through JTBD-05.
3. **Refresh evidence:** JTBD-02 and JTBD-06 through JTBD-09.
4. **Inspect exposure:** JTBD-10.
5. **Evaluate an opportunity:** JTBD-11 or a manually reviewed setup.
6. **Prepare and guard execution:** JTBD-12 through JTBD-15.
7. **Close and review:** JTBD-16 and JTBD-17.
8. **Recover partial operations:** JTBD-18 at any batch stage.

## Outcome criteria

- Instrument identity is explicit at every execution boundary.
- Data source, freshness, and storage status are visible rather than implied.
- Public reads and signed writes remain distinguishable.
- Batch failures preserve successful results by default.
- Live mode requires an affirmative flag and never follows automatically from a signal.
- Review metrics can be reproduced from stored completed-trade fields.

## Assumptions

- **A-009:** Jobs describe the current manual operating model; they do not imply a scheduler, workflow engine, or GUI.
- **A-010:** Suitability review uses funding and spread data manually because no automatic threshold contract exists.
- **A-011:** A “fresh” observation uses the command-specific policy. Only trade.xyz metadata verification currently has an enforced maximum age in order flow.

## Unresolved risks

- No persisted trade-plan object connects the original rationale, account snapshot, ATR input, dry-run, live submission, fills, and journal entry end to end.
- The product does not currently expose list/detail commands for all SQLite tables, so some audit jobs require direct database access.
