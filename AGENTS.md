# AGENTS.md

Agent rules for the KIS Hyperliquid Trading System. This file is the single source of
truth for every coding agent (Claude Code, Codex and others), including the file
ownership table and the rules for what an agent session may execute. `CLAUDE.md` only
imports this file so Claude Code loads it; do not add rules there.

## Single Source of Truth

Every fact has exactly one owner file. Read the owner before answering, and update the
owner when behavior changes. Do not restate an owner's content in another file; link
to it instead.

| Knowledge | Owner | Notes |
| --- | --- | --- |
| Agent rules (core, documentation, trading safety, agent-session execution, testing) and this ownership table | `AGENTS.md` | Read directly by Codex; imported by `CLAUDE.md` for Claude Code |
| Setup, environment variables, CLI usage, safety notes | `README.md` | Keep usage-focused |
| Protected trade plans, supervisor controls, synchronization, signal/grant usage | `docs/trading-operations.md` | Actual implementation and rollout limits |
| Component responsibilities, data flow, storage design | `docs/architecture.md` | Update when a module's responsibility changes |
| Strategy skill/code ownership and authoring policy | `docs/strategy-authoring.md` | Hermes workflow versus deterministic tools |
| Trend setup selection, risk-unit semantics and management rationale | `.agents/skills/trend-strategy/` | Canonical rules shared by Hermes, Codex and Claude Code |
| Weinstein book-method analysis, source provenance and investor/trader distinctions | `.agents/skills/weinstein-stage-analysis/` | One shared skill; host discovery and installation belong to `docs/strategy-authoring.md` |
| Strategy tool input/output contract | `docs/strategy-tools.md` | Paired with `kis_hl/strategy_tools.py`, `kis_hl/risk.py` and `kis_hl/timing_opinion.py` |
| Strategy integration and execution status | `docs/strategy_execution_design.md` | Existing execution boundary and explicit limitations |
| Underlying market sessions and live-entry session policy | `docs/trading_hours.md` | Paired with `kis_hl/trading_hours.py` |
| trade.xyz asset universe, eligibility, exclusions | `docs/trade_xyz_assets.md` + `kis_hl/trade_xyz_assets.py` | Doc explains policy, code is the seed of record |
| KIS endpoints, TR IDs, auth, rate limits, websocket protocol | `.agents/skills/kis-open-api/` | Repository skill |
| Hyperliquid endpoints, order schema, asset ids, tick/lot rules, rate limits, websocket protocol | `.agents/skills/hyperliquid-api/` | Repository skill |
| Binance USDⓈ-M futures order/algo/cancel endpoints, signing, listenKey lifecycle, stream names, symbol filters, rate limits, error codes | `.agents/skills/binance-api/` | Repository skill |
| Completed-trade journal record contract, review-statistics formulas, and edge cases | `.agents/skills/trade-journal/` | Repository skill |
| Session observation, skill-improvement workflow, observation log | `.agents/skills/task-observer/` | Repository skill; activation rule is under Documentation |
| Coding behavior guidelines (assumptions, surgical changes, success criteria) | `.agents/skills/karpathy-guidelines/` | Repository skill; activation rule is under Documentation |
| Issue content, clarity, and objective acceptance criteria | `~/.agents/skills/issue-writing/` | User-scope skill outside this repository; activation rule is under Documentation |
| Non-secret env variable template | `.env.example` | `.env` stays untracked |
| Runtime eligibility and verification state | SQLite tables | Code and tests are the contract, not prose |

When a change touches one of these areas, update that owner in the same change as the
code. If two files disagree, the owner in this table wins and the other file must be
corrected.

## Core Rules

- Prefer minimal, safe, and incremental changes.
- Preserve the current CLI-first architecture unless a broader service shape is explicitly required. New behavior belongs in a focused module under `kis_hl/` with a matching test in `tests/`.
- Read the owner file from the table above before editing an area you have not loaded in this session. Prefer reading code over inferring behavior.
- Keep all code, documentation, code comments, commit messages, schema descriptions, and user-facing CLI text in English.
- Do not commit or push unless asked.
- Do not commit secrets. `.env` is ignored and must remain untracked. Never write secrets into code, logs, tests, or documentation, and do not print `.env`, tokens, `appkey`/`appsecret`, or private keys in tool output.
- Use SQLite for local project state unless the user explicitly asks for another store.
- Keep behavior traceable with tests, schema fields, and documentation close to the code.
- Manage strategies as shared skills and implement deterministic calculations and predicates as Python tools. Follow `docs/strategy-authoring.md`; Hermes owns scheduling, briefings and notifications.

## Documentation

- For any KIS Open API work (REST or WebSocket call, new endpoint, TR ID lookup, token/`approval_key`/`EGW00201` rate-limit issue, KIS route for a trade.xyz asset), read `.agents/skills/kis-open-api/SKILL.md` first and keep its endpoint tables in sync when `kis_hl/kis/client.py` changes.
- For any Hyperliquid work (REST or WebSocket call, `/info` type or `/exchange` action lookup, signed action, symbol-to-coin or asset-id resolution, tick/lot sizing, order rejection, websocket subscription), read `.agents/skills/hyperliquid-api/SKILL.md` first and keep its tables in sync when `kis_hl/hyperliquid/` changes.
- For any Binance work (REST or WebSocket call, `/fapi` path or signed request, listenKey or user-data-stream handling, stream name or market stream subscription, symbol filter or rate-limit question), read `.agents/skills/binance-api/SKILL.md` first and keep its tables in sync when `kis_hl/binance/` changes (`client.py`, `ws.py`, `trading.py`). Never attach a vendor trading MCP server or order-capable tool to an agent session with live keys; this applies to every venue.
- For completed-trade journal records, record boundaries, statistics, `journal add`/`journal stats` output, or storage semantics, read `.agents/skills/trade-journal/SKILL.md` first and keep its formula references in sync with `kis_hl/trade_journal.py` and its tests.
- When writing, reviewing, or refactoring code, follow `.agents/skills/karpathy-guidelines/SKILL.md`: surface assumptions, keep changes minimal and surgical, and define verifiable success criteria before implementing.
- For Weinstein book-method questions, chart reviews, investor/trader distinctions, exits or short-setup analysis, use `.agents/skills/weinstein-stage-analysis/SKILL.md`. Keep book principles, later interpretations and local calculation choices distinct.
- For the repository's operational trend strategy and breakout/pullback/rebreakout decisions, use `.agents/skills/trend-strategy/SKILL.md` with its deterministic CLI tools. A skill decision does not authorize an order.
- At the start of any multi-step work session, read `.agents/skills/task-observer/SKILL.md` and follow its observation workflow; it captures repeating patterns, user corrections, and skill-improvement opportunities. This line is its activation trigger for all agents.
- Skills live in `.agents/skills/<name>/` as the single copy, with relative symlinks at `.codex/skills/<name>` and `.claude/skills/<name>`. When installing a new skill, create these links, add a usage rule here, and add a row to the ownership table above. Hermes discovery must point to that same canonical directory; see `docs/strategy-authoring.md`.
- When drafting, editing, or reviewing issues, use the user-scope `issue-writing` skill (`~/.agents/skills/issue-writing/SKILL.md`) and follow its content and acceptance-criteria rules before delivery. It is not repository-specific, so it is maintained outside this repository; do not add a repository copy that would shadow or diverge from it.
- Update documentation whenever behavior, setup, schema, asset eligibility, trading safety, or operational assumptions change.
- Keep README focused on usage.
- Keep deeper design notes in `docs/`.
- Document unresolved risks when live exchange behavior has not been verified.

## Trading Safety

- Live Hyperliquid orders must fail closed.
- Do not broaden the supported live asset set without updating the asset mapping table and tests.
- When trade.xyz asset coverage changes, update both `trade_xyz_assets` and `trade_xyz_kis_mappings` behavior plus tests.
- For trade.xyz RWA assets, use the local SQLite-backed mapping table as the eligibility source.
- Live trade.xyz orders must also require recent successful Hyperliquid metadata verification.
- Exclude assets that have not completed a public listing or IPO.
- Exclude stock assets that have been publicly listed for less than 30 weeks.
- Cross-venue timing and KIS preferred/fallback instrument requirements are owned by `docs/trading-operations.md` ("Cross-venue timing and preferred execution policy"). Keep account-level management independent; shared signals are not shared funds or execution prices.
- Avoid duplicate country exposure within the Hyperliquid trade.xyz universe (this does not exclude independently managed KIS ETFs):
  - Use `KORU` for South Korea exposure and exclude `KR200` and `EWY`. KORU references a daily 3x leveraged US-listed ETF; it is not equivalent to the KOSPI 200 index.
  - Use `JP225` for Japan exposure and exclude `EWJ`.

## Agent Session Execution

The section above defines product-level trading rules. These rules limit what an agent
itself may execute.

- By default, never run a command with `--live`, and never run anything that can place, cancel, or modify a real order. Prepare the dry-run command and let the user run the live one after review.
- Exception: an agent may run a live action only after the user explicitly approves it in the current conversation. Before asking, run the dry-run where one exists, then state the exact commands, venue and account, instrument, side, order types, maximum size and notional, and the cleanup step. The approval covers only that stated scope. It does not carry over to later tasks or sessions, and general instructions such as "proceed" do not count as approval.
- During an approved live action, stop and report on any rejection, `UNKNOWN` outcome, unexpected fill, or price move that changes the approved size. Do not retry, resize, or add orders without new approval. Keep away from instruments that a running supervisor owns unless the user names them. Transfers, withdrawals and leverage or margin changes are live actions too. Finish by reporting order IDs, fills, and the remaining positions and open orders.
- Treat widening the tradable asset set and relaxing a verification freshness window as user decisions, not agent defaults. Hyperliquid session flags are compatibility-only; session policy is owned by `docs/trading_hours.md`.
- Live paths must fail closed. When adding a guard, add the rejecting test first and make sure the default (no flag) is the safe path.
- Read-only commands are fine to run when they help verify a change, for example `xyz-assets list`, `xyz-assets kis-list`, `hl-mids`, and `journal stats`. Collector commands hit vendor APIs and are rate-limited, so ask before running them.

## Testing

- Run tests relevant to the changed scope before reporting a task complete, and say plainly when a check was skipped.
- Add or update tests when behavior changes.
- Prefer behavior-focused tests over tests coupled to implementation details.
- Tests are `unittest`-based and must not require network access or real credentials.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# full test suite (unittest, no pytest dependency)
python3 -m unittest discover -s tests -t . -q

# a single module
python3 -m unittest tests.test_trading_hours -q
```

For CLI usage and operational sequences, see `README.md`.
