# AGENTS.md

## Core Rules

- Prefer minimal, safe, and incremental changes.
- Preserve the current CLI-first architecture unless a broader service shape is explicitly required.
- Keep all documentation, code comments, commit messages, schema descriptions, and user-facing CLI text in English.
- Do not commit secrets. `.env` is ignored and must remain untracked.
- Use SQLite for local project state unless the user explicitly asks for another store.
- Keep behavior traceable with tests, schema fields, and documentation close to the code.

## Documentation

- For any KIS Open API work (new endpoint, TR ID, token/rate-limit issue, KIS route for a trade.xyz asset), read `.agents/skills/kis-open-api/SKILL.md` first and keep its endpoint tables in sync when `kis_hl/kis/client.py` changes.
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
