# Plan — binance-order-execution (r1)

Files: add `kis_hl/binance/trading.py`, `tests/test_binance_trading.py`, `.agents/skills/binance-api/references/orders.md`; change `kis_hl/config.py`, `kis_hl/cli.py`, `tests/test_config.py`, `tests/test_cli.py`, `README.md`, `docs/architecture.md`, `.env.example`, `.agents/skills/binance-api/SKILL.md`, `docs/architecture/binance-order-roundtrip-sequence.json` (+ delivered html).

Order: config tests (Red) → config; trading tests (Red) → trading.py (Green); CLI tests (Red) → CLI; docs/skill/diagram; full suite; smoke (dry-run CLI, exchange-test with real keys); QA subagent; Codex PR review; commit/push/PR.

Boundaries: no change to Hyperliquid modules or existing tables; no leverage/margin/hedge features; `--live` never executed by the agent.
Riskiest part: guard ordering and rounding semantics; covered by ordered guard tests and rounding tests with BTCUSDT filters.
Rollback: delete trading.py and the three CLI commands; config additions are additive.
Rejected alternative: exchange-side validation as the dry-run (rejected: dry-run must stay network-free for signed paths; exchange test is a separate explicit flag).
