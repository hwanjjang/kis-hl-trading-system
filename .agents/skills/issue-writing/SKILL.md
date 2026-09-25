---
name: issue-writing
description: Use when drafting, editing, or reviewing issues.
version: 0.1.0
author: AK, Hermes Agent
platforms: [linux, macos, windows]
---

# Issue Writing

Internal skill capturing AK's issue-writing requirements. Write the minimum
information needed to begin implementation without sacrificing clarity.
This skill governs issue content, not authorization to publish or implement it.

## When to Use

- Drafting a new issue after discovering a problem or identifying a change.
- Editing, refining, or reviewing an existing issue.
- Turning findings into implementation-ready work items.

## Procedure

1. Read the relevant evidence and existing issue context. Separate observed facts
   from assumptions; resolve implementation-blocking unknowns rather than inventing
   requirements. Follow the repository's language rules.
2. Write a specific title and organize the body around three sections:
   **Problem / Goal**, **Required Changes**, and **Acceptance Criteria**.
3. Explain what must change and why. Include background, reproduction steps,
   affected files, constraints, or references only when directly needed to
   implement the change. Keep essential information in the issue rather than
   requiring the implementer to reconstruct the conversation.
4. Describe required changes precisely without prescribing unnecessary design
   details. Avoid both cryptic shorthand and long explanations that hide the point.
   Use technical terms, abbreviations, and internal expressions only when needed;
   briefly explain them if their meaning is not clear from context.
5. Keep the acceptance checklist limited to necessary completion conditions.
   Prefer checks an agent can execute directly, and give each item an observable
   outcome with an unambiguous pass/fail result. Exclude subjective judgments,
   human-only evaluations, duplicate conditions, and routine work steps.
6. Perform the final review below before presenting or publishing the issue.
   For remote operations, use the platform workflow for duplicate checks and
   read-back verification; this skill does not replace that workflow.

## Minimal Template

```markdown
# <Specific change and affected behavior>

## Problem / Goal
<Current problem, its relevant impact, and intended outcome.>

## Required Changes
- <Necessary behavior or contract change, including essential constraints.>

## Acceptance Criteria
- [ ] <Defined input or condition produces the specified observable result.>
```

Replace placeholders with actual requirements. Do not add sections or checklist
items merely to fill the template.

## Pitfalls

- "Improve reliability" does not identify the failing behavior or expected result.
- "Looks clear" and "User approves the design" are not objective acceptance items.
- "Read the code", "Implement the fix", and "Review the issue" are routine steps,
  not completion conditions. Keep authoring review out of the issue checklist.
- "All tests pass" alone does not define the required behavior. Name the relevant
  observable result, such as: "Given an expired token, the request returns the
  documented authentication error without submitting an order."
- Concision is not a word-count target: retain information necessary to start work.

## Final Review

Re-read the entire issue against these rules before delivery. Assess whether a
first-time reader can quickly understand what to do and why, and whether an
implementer can begin without additional explanation. Revise ambiguous shorthand,
unexplained terminology, excessive background, and missing essential context.

Then inspect every acceptance item: retain it only if it is necessary, distinct,
and objectively decidable; prefer direct agent verification. This readability
review is the author's responsibility, not a subjective checkbox in the issue.
