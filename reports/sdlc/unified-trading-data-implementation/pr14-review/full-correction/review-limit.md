# PR-review iteration limit

The stable task's native route was originally local and its native PR-review stage
is excluded. Supplementary PR-review records tracked actual later authorized
reviews, including interrupted execution. Seven historical attempts preceded the
three additional Codex full passes (8, 9, 10). Those counts and original reports
remain in pr14-review/codex-three-pass/execution.json and earlier ledgers.

The SDLC SKILL.md and shared subagent contract cap a stable task stage at ten total
attempts, explicitly including changed input and downstream re-entry. This
correction does not rename the task, reset the counters, or launch PR-review 11.
Independent implementation verification uses its own existing stage allowance and
must not masquerade as an additional PR-review PASS or reviewer resolution.

Authorized implementation, tests, independent verification, commit/push and CI can
continue. PR readiness and formal closure of mandatory review findings remain
unclaimed until the user resolves the iteration-policy boundary. No merge or
auto-merge is authorized. Record the limit in the final durable PR/task receipt.
