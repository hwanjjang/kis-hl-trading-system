# Design evidence

Source: docs/architecture/conditional-add.workflow.json. Delivered standalone HTML:
docs/architecture/conditional-add.html. Existing-owner flow derived from specs/issue-27.md
and actual Signals/ExecutionStore/Supervisor boundaries. Unlabeled sequential edges
are redundant with adjacent state/node names; SL/TS/strategy cause remains labeled.

Archify: /root/.codex/skills/archify (canonical shared user skill), 2.17.
Deterministic delivery: 9/9 showcase checks, zero composition errors/warnings.
Browser evidence: passed with cached Chromium, four desktop viewports, no overflow.
Perceptual review: main inspected actual 1440x900 light and 2048x1320 dark screenshots;
labels and nodes fit, route direction is clear, no crossing/masking or clipped content.
Correction rounds: 2 (node text width, then projected readability).
Receipts: diagram-validation.json, diagram-browser.json, and the HTML's sidecars.

Local commands required escalation because renderer subprocess creation was blocked
by the sandbox. Automatic review allowed the narrowly scoped local renderer/browser
operations; no permission settings or installed skill code were changed.
