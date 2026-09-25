# Strategy skill and deterministic code policy

Hermes owns the strategy workflow: when to review markets, contextual judgment,
briefings, user conversation and notification delivery. Repository strategy skills
define how to make and explain those decisions. Python tools supply reproducible
facts and the existing execution system enforces trading authority and safety.

## Ownership

| Responsibility | Owner |
| --- | --- |
| Setup interpretation, confluence, reference-level selection, rationale, hold/add/reduce/exit recommendation | Strategy skill |
| Indicator arithmetic, precisely defined price predicates, ATR stop calculation, unit sizing, rounding, input validation | Python functions and CLI tools |
| Review timing, model invocation, briefing composition, notification transport | Hermes configuration outside this repository |
| Signal identity/expiry, account authority, funds, order submission, fill/protection/recovery | Existing signal registry and managed execution code |

A skill may define a numeric rule, but it calls code to calculate and test that
rule. It must not recalculate tool outputs in prose, invent missing prices, treat
an analysis proxy as an execution price, or turn a passing predicate into order
authority. Qualitative judgment remains a stated judgment with its supporting
evidence; do not invent a score to make it appear deterministic.

## Authoring a strategy

Keep one canonical skill in `.agents/skills/<name>/`, discoverable by Codex and
Claude Code. Hermes can load that same `SKILL.md` and its relative references;
do not maintain a separate Hermes copy of the rules. CLI directories contain
links/adapters only. State the strategy version, applicable universe/direction,
setup and invalidation rules, and which tools produce its facts. Link existing
execution and API contracts instead of duplicating them.

Use ordinary focused modules in `kis_hl/` for deterministic tools, exposed through
the existing CLI. Inputs identify instrument, source, currency, time and relevant
parameters. Outputs distinguish an unavailable fact from zero/false, and a
candidate setup from an authorized order. Numeric functions use Decimal, reject
non-finite values and round position quantity down. Identical input snapshots and
evaluation clocks produce identical numeric evidence; model prose need not repeat.

Version changed strategy semantics in the existing registry. Record the decision
with its input snapshot, predicate evidence, rationale and management basis using
`strategy decide`. A skill-produced `hold`, `add`, `reduce`, `exit` or `no_trade`
record cannot be replayed as a new-entry authorization. Entry still needs explicit
manual authority or an applicable bounded grant and the supervisor's preflight.

## Proportionate verification

Use a few representative strategy cases and tests for changed calculations and
their consequential failure cases. Reuse existing execution tests. Check shared
skill discovery and run its documented CLI tools offline. Exclude exhaustive
market/harness combinations, live fault injection and verification machinery whose
cost exceeds its value. Record material unsupported capabilities plainly; never
substitute an unverified live path for a missing tool.

The current implementation is [trend-strategy](../.agents/skills/trend-strategy/SKILL.md).
Its strategy rules own selection behavior; [execution design](strategy_execution_design.md)
owns the integration/status boundary and [operations](trading-operations.md) owns
the actual execution contract.

## Weinstein skill discovery

The [Weinstein skill](../.agents/skills/weinstein-stage-analysis/SKILL.md) is a
book-centered analytical companion, separate from the operational trend strategy.
Its canonical files live under `.agents/skills/weinstein-stage-analysis/`.
The repository's `.codex/skills/weinstein-stage-analysis` and
`.claude/skills/weinstein-stage-analysis` directory links both target
`../../.agents/skills/weinstein-stage-analysis`. References are internal resources
of the same skill, not separately invoked skills. No hooks, credentials or other
skills are required for supplied-data analysis.

For Hermes, link the intended profile's `skills/weinstein-stage-analysis` directory
to the absolute canonical directory in this checkout. The default profile uses
`~/.hermes/skills/`. Preserve an existing destination instead of overwriting it.
This installation route requires no project-trust or tool-permission changes.
Hermes may warn that a linked skill resolves outside its local skill root;
verify successful listing and reference reads rather than suppressing the warning.

The installed Hermes link is tied to this checkout. Before deleting or relocating
a worktree, retarget it to the canonical directory in the retained checkout and
repeat discovery checks. Do not make an independent Hermes copy of the rules.
Other Hermes profiles need their own link to that same directory. Codex/Claude
availability here is repository-scoped; it is not a user-wide installation.

Start a new session if an existing session has cached its skill catalog. Verify
Codex's native skill list, Claude Code's available `/weinstein-stage-analysis`
command, and Hermes `skills_list` plus `skill_view` for the entrypoint and all
three references. A successful loader check proves discovery and readable
content; a model's reasoning, current market data and order execution are separate
verification layers. Invocation never grants trading authority.
