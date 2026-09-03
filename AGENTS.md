# AGENTS.md

## Core Rules

- Prefer minimal, safe, and incremental changes.
- Preserve the current CLI-first architecture unless a broader service shape is explicitly required.
- Keep all documentation, code comments, commit messages, schema descriptions, and user-facing CLI text in English.
- Do not commit secrets. `.env` is ignored and must remain untracked.
- Use SQLite for local project state unless the user explicitly asks for another store.
- Keep behavior traceable with tests, schema fields, and documentation close to the code.

## Documentation

- This file is the single source of truth for shared agent rules. `CLAUDE.md` imports it and adds only Claude Code specific workflow rules; keep shared rules here instead of duplicating them.
- `CLAUDE.md` also holds the ownership table that says which file owns which knowledge. Update the owner file in the same change as the code.
- For any KIS Open API work (new endpoint, TR ID, token/rate-limit issue, KIS route for a trade.xyz asset), read `.agents/skills/kis-open-api/SKILL.md` first and keep its endpoint tables in sync when `kis_hl/kis/client.py` changes.
- For any Hyperliquid work (new `/info` request, signed action, symbol or asset-id resolution, tick/lot sizing, websocket subscription), read `.agents/skills/hyperliquid-api/SKILL.md` first and keep its tables in sync when `kis_hl/hyperliquid/` changes.
- For completed-trade journal records, statistics, CLI output, or storage semantics, read `.agents/skills/trade-journal/SKILL.md` first and keep its formula references in sync with `kis_hl/trade_journal.py`.
- When writing, reviewing, or refactoring code, follow `.agents/skills/karpathy-guidelines/SKILL.md`: surface assumptions, keep changes minimal and surgical, and define verifiable success criteria before implementing.
- At the start of any multi-step work session, read `.agents/skills/task-observer/SKILL.md` and follow its observation workflow; it captures repeating patterns, user corrections, and skill-improvement opportunities. This line is its activation trigger for all agents.
- Skills live in `.agents/skills/<name>/` as the single copy, with a relative symlink at `.claude/skills/<name>` so both Claude Code and Codex use the same files. When installing a new skill, create both, add a usage rule here, and add a row to the ownership table in `CLAUDE.md`.
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
- Avoid duplicate country exposure:
  - Use `KR200` for South Korea exposure and exclude `EWY`.
  - Use `JP225` for Japan exposure and exclude `EWJ`.

## Testing

- Run tests relevant to the changed scope.
- Add or update tests when behavior changes.
- Prefer behavior-focused tests over tests coupled to implementation details.
