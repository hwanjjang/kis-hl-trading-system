# Plan — binance-usdm-ws (r1)

Inputs: intent r1, spec r1, investigation.

Files:
- add `kis_hl/binance/__init__.py`, `kis_hl/binance/client.py`, `kis_hl/binance/ws.py`
- change `kis_hl/config.py` (BinanceConfig/load), `kis_hl/storage.py` (order_events), `kis_hl/cli.py` (7 commands)
- add `tests/test_binance_client.py`, `tests/test_binance_ws.py`; extend `tests/test_config.py`, `tests/test_storage.py` (or new test), `tests/test_cli.py`
- docs: `.env.example`, `README.md`, `docs/architecture.md`, `AGENTS.md`, `CLAUDE.md`, `.agents/skills/binance-api/{SKILL.md,references/*.md}`, symlink `.claude/skills/binance-api`

Order: tests first for config/client signing (Red) -> config -> client (Green) -> ws tests (Red) -> ws -> storage + tests -> cli + tests -> docs/skill -> full suite -> smoke -> qa.

Boundaries intact: no change to Hyperliquid/KIS modules; no order placement path; `--live` not introduced.

Riskiest part: user-stream lifecycle (listenKey refresh per connect, expiry handling) — covered by fake-transport tests simulating expiry and reconnect.
Rollback: delete the three new modules and revert the five edited files; additive table is harmless.
Rejected alternative: SDK dependency (see spec).
Proof: tests assert exact query strings/signatures against a known HMAC vector and reconnection counters.
