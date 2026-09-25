# AGENTS.md

## Core Rules

- Prefer minimal, safe, and incremental changes.
- Preserve the current CLI-first architecture unless a broader service shape is explicitly required.
- Keep all documentation, code comments, commit messages, schema descriptions, and user-facing CLI text in English.
- Do not commit secrets. `.env` is ignored and must remain untracked.
- Use SQLite for local project state unless the user explicitly asks for another store.
- Keep behavior traceable with tests, schema fields, and documentation close to the code.
- Manage strategies as shared skills and implement deterministic calculations and predicates as Python tools. Follow `docs/strategy-authoring.md`; Hermes owns scheduling, briefings and notifications.

## Documentation

- This file is the single source of truth for shared agent rules. `CLAUDE.md` imports it and adds only Claude Code specific workflow rules; keep shared rules here instead of duplicating them.
- `CLAUDE.md` also holds the ownership table that says which file owns which knowledge. Update the owner file in the same change as the code.
- For any KIS Open API work (new endpoint, TR ID, token/rate-limit issue, KIS route for a trade.xyz asset), read `.agents/skills/kis-open-api/SKILL.md` first and keep its endpoint tables in sync when `kis_hl/kis/client.py` changes.
- For any Hyperliquid work (new `/info` request, signed action, symbol or asset-id resolution, tick/lot sizing, websocket subscription), read `.agents/skills/hyperliquid-api/SKILL.md` first and keep its tables in sync when `kis_hl/hyperliquid/` changes.
- For any Binance work (new `/fapi` request, signed read, listenKey or user-data-stream handling, market stream subscription, symbol filter or rate-limit question), read `.agents/skills/binance-api/SKILL.md` first and keep its tables in sync when `kis_hl/binance/` changes. Never attach a vendor trading MCP server or order-capable tool to an agent session with live keys; this applies to every venue.
- For completed-trade journal records, statistics, CLI output, or storage semantics, read `.agents/skills/trade-journal/SKILL.md` first and keep its formula references in sync with `kis_hl/trade_journal.py`.
- When writing, reviewing, or refactoring code, follow `.agents/skills/karpathy-guidelines/SKILL.md`: surface assumptions, keep changes minimal and surgical, and define verifiable success criteria before implementing.
- For Weinstein book-method questions, chart reviews, investor/trader distinctions, exits or short-setup analysis, use `.agents/skills/weinstein-stage-analysis/SKILL.md`. Keep book principles, later interpretations and local calculation choices distinct.
- For the repository's operational trend strategy and breakout/pullback/rebreakout decisions, use `.agents/skills/trend-strategy/SKILL.md` with its deterministic CLI tools. A skill decision does not authorize an order.
- At the start of any multi-step work session, read `.agents/skills/task-observer/SKILL.md` and follow its observation workflow; it captures repeating patterns, user corrections, and skill-improvement opportunities. This line is its activation trigger for all agents.
- Skills live in `.agents/skills/<name>/` as the single copy, with relative symlinks at `.codex/skills/<name>` and `.claude/skills/<name>`. When installing a new skill, create these links, add a usage rule here, and add a row to the ownership table in `CLAUDE.md`. Hermes discovery must point to that same canonical directory; see `docs/strategy-authoring.md`.
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

## Testing

- Run tests relevant to the changed scope.
- Add or update tests when behavior changes.
- Prefer behavior-focused tests over tests coupled to implementation details.
