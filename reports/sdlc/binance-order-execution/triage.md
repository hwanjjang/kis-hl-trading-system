# Triage — binance-order-execution

| Field | Recorded value |
| --- | --- |
| Task / stage / owner | binance-order-execution / triage / main agent (Claude Fable 5.1) |
| Date / revision | 2026-09-16 r1 |
| Source / authority | AK chat 2026-09-16: implement Binance order execution per SDLC; decisions: dry-run default with explicit `--live` (current repo rule kept), scope = entry + STOP_MARKET (closePosition) + TRAILING_STOP_MARKET + cancel; commit and open a PR (endpoint pr, no merge). |
| Consumed inputs | PR #17 (data plane), issue #16, issue #15 (unit sizing, not in scope), reports/sdlc/binance-usdm-ws/* |
| Acceptance criteria | AC1–AC8 (intent.md) |
| Candidate / base | branch binance-order-execution from 1b2a337 (head of review-binance-mcp-issue, PR #17) |
| Status / decision | PROCEED |

- Requested: signed order placement on Binance USDⓈ-M futures with server-side protective orders and cancel, following the Hyperliquid trading-client shape and the repo trading-safety rules.
- Mode implementation, change kind behavior, endpoint pr (stacked on PR #17; base `review-binance-mcp-issue`).
- Excluded: leverage/margin-type changes, hedge (dual-side) position mode support, strategy daemon wiring, unit-based sizing (#15), spot.
- Facts: BTCUSDT filters tick 0.10 / step 0.001 / MIN_NOTIONAL 50; order types include STOP_MARKET and TRAILING_STOP_MARKET; only mainnet key names exist in `.env` (demo keys are separate and not present).
- Constraints: agent never runs `--live`; smoke uses dry-run and the exchange test endpoint (`POST /fapi/v1/order/test`, validates without placing) only; never print secrets.
- Stages: all implementation stages; design = update the planned order round-trip diagram to the implemented flow; pr-review via a different provider (Codex CLI is installed) at medium effort; merge not applicable.
- Artifact mapping: reports/sdlc/binance-order-execution/ (ignored by git); planning notebook .planning/2026-09-16-binance-order-execution.
