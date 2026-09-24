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
