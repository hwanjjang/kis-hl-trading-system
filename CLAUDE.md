# CLAUDE.md

Claude Code entry point for the KIS Hyperliquid Trading System.

This file is a routing layer, not a second copy of the project rules. Shared agent
rules live in `AGENTS.md` and are imported below, so Claude Code and Codex follow
the same rules from one source.

## Single Source of Truth

Every fact has exactly one owner file. Read the owner before answering, and update
the owner when behavior changes. Do not restate an owner's content in another file;
link to it instead.

| Knowledge | Owner | Notes |
| --- | --- | --- |
| Shared agent rules (safety, docs, testing) | `AGENTS.md` | Imported by this file; also read directly by Codex |
| Claude-specific workflow (skills, tools, session rules) | `CLAUDE.md` | This file only |
| Setup, environment variables, CLI usage, safety notes | `README.md` | Keep usage-focused |
| Component responsibilities, data flow, storage design | `docs/architecture.md` | Update when a module's responsibility changes |
| Strategy sizing, ATR stops, add-up flow, execution design | `docs/strategy_execution_design.md` | Planned daemon design plus what is implemented |
| Underlying market sessions and live-entry session policy | `docs/trading_hours.md` | Paired with `kis_hl/trading_hours.py` |
| trade.xyz asset universe, eligibility, exclusions | `docs/trade_xyz_assets.md` + `kis_hl/trade_xyz_assets.py` | Doc explains policy, code is the seed of record |
| KIS endpoints, TR IDs, auth, rate limits, websocket protocol | `.agents/skills/kis-open-api/` | Symlinked as `.claude/skills/kis-open-api/` |
| Non-secret env variable template | `.env.example` | `.env` stays untracked |
| Runtime eligibility and verification state | SQLite tables | Code and tests are the contract, not prose |

When a change touches one of these areas, update that owner in the same change as
the code. If two files disagree, the owner in this table wins and the other file
must be corrected.

@AGENTS.md

## Claude Working Rules

- Read the owner file from the table above before editing an area you have not
  loaded in this session. Prefer reading code over inferring behavior.
- Use the `kis-open-api` skill for any KIS REST or WebSocket work, TR ID lookup,
  token/`approval_key`/`EGW00201` rate-limit issue, or trade.xyz-to-KIS route
  question, and keep its endpoint tables in sync with `kis_hl/kis/client.py`.
- Keep changes minimal and incremental, and keep the CLI-first shape. New behavior
  belongs in a focused module under `kis_hl/` with a matching test in `tests/`.
- Write all code, comments, docs, CLI text, and commit messages in English.
- Do not commit or push unless asked. Never write secrets into code, logs, tests,
  or documentation, and do not print `.env`, tokens, `appkey`/`appsecret`, or
  private keys in tool output.

## Trading Safety For Agent Sessions

`AGENTS.md` defines the product-level trading rules. These are the additional rules
for what Claude itself may execute:

- Never run a command with `--live`, and never run anything that can place, cancel,
  or modify a real order. Prepare the dry-run command and let the user run the live
  one after review.
- Treat `--allow-outside-session`, widening the tradable asset set, and relaxing a
  verification freshness window as user decisions, not agent defaults.
- Live paths must fail closed. When adding a guard, add the rejecting test first and
  make sure the default (no flag) is the safe path.
- Read-only commands are fine to run when they help verify a change, for example
  `xyz-assets list`, `xyz-assets kis-list`, `hl-mids`, and `journal stats`.
  Collector commands hit vendor APIs and are rate-limited, so ask before running them.

## Commands

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# full test suite (unittest, no pytest dependency)
python3 -m unittest discover -s tests -t . -q

# a single module
python3 -m unittest tests.test_trading_hours -q
```

Tests are `unittest`-based and must not require network access or real credentials.
Run the tests relevant to the changed scope before reporting a task complete, and
say plainly when a check was skipped.

For CLI usage and operational sequences, see `README.md`.
