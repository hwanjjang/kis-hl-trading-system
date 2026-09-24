# Weinstein skill validation

Date: 2026-09-24. Scope: one shared analytical skill and host discovery adapters.
Base: `adb71fa5b1713164ab4aff1d5916d26c47f96950`.

## Source and scope

The canonical source is `.agents/skills/weinstein-stage-analysis/`: one entrypoint
and three references. Codex and Claude Code repository links resolve to that same
directory. Hermes uses a profile-local directory link to the canonical checkout;
that machine-specific link is not committed. Installation and worktree lifecycle
are documented in `docs/strategy-authoring.md`.

The skill separates investor/trader modes, stage versus entry eligibility,
management and bearish analysis. It distinguishes sampled book principles,
secondary interpretations and local calculation conventions. The source register
discloses OCR limitations and incomplete coverage of advanced topics. This is not
a complete-book fidelity audit or a backtested trading system.

## Executed validation

| Layer | Result |
| --- | --- |
| Skill frontmatter and relative references | PASS; standard validator and local reference checks |
| Shared source integrity | PASS; all four installed files match the approved package; all three local host paths resolve to the same physical files |
| Codex 0.153.4 native `skills/list` | PASS; one enabled repository-scoped skill |
| Claude Code 2.1.280 native initialization | PASS; one project skill command |
| Hermes native `skills_list` / `skill_view` | PASS; entrypoint and all three references returned in full |
| Hermes default profile outside repository cwd | PASS; discovery and reference content still resolve to the canonical checkout |
| Native Codex skill application | PASS; independent agent loaded installed references and evaluated synthetic investor/trader and protective-stop cases |
| Hermes CLI skill application | PASS; configured `gpt-6-astra` read all three references through `skill_view` and answered the supplied synthetic case |
| Claude Code model application | BLOCKED by existing account session quota; command discovery succeeded, but no model answer was verified |
| Post-main-update source integrity and whitespace | PASS; approved skill bytes and links preserved; `git diff --check` passed |

The source-level independent evaluation also covered eight cases: early investor
versus trader continuation, an extended Stage 2 entry, unknown preceding history,
a protective-stop breach, bearish analysis in a long-only host, incomplete-week
volume, and attribution of EMA/volume-baseline adaptations. No live market or
order tools were used.

Detailed local execution records include native catalog responses, file hashes,
same-file checks, independent reports and the newly generated Hermes test's tool
trace. Raw session output, machine-specific helpers and third-party research
snapshots are intentionally outside this published change.

## Limits

Model behavior and host discovery are distinct checks. Claude's account limit
does not support a claim of successful model execution. Hermes can emit an
outside-skill-root warning for a directory link; successful reads were verified
without changing trust or permissions. Its link must be retargeted before the
referenced worktree is removed. Other Hermes profiles are not implicitly installed.

Existing strategy semantics, Python execution tools, order authority, account
configuration and schedules are unchanged. No product code changed, so the
application test suite was not rerun locally for this documentation/skill change;
the repository's pull-request workflow supplies its normal regression checks.
