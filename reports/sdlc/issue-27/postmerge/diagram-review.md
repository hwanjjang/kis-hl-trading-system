# Post-merge diagram review and delivery

## Scope and evidence

Reviewed the existing conditional-add workflow against the post-merge investigation,
`ExecutionStore`, `Supervisor._step`, its cancellation/terminal paths in
`kis_hl/managed_execution.py`, and `pending_adds` in `kis_hl/operations_cli.py`.
The previous overview represented only the successful add/protect/exit path; it
omitted cancellation scope and unsent tranche retirement, the exact boundaries
behind both reported regressions. Other architecture views cover entry/adoption,
data storage or venue routing and need no topology change for this local repair.

The main implementation owner confirmed the intended design before delivery.
Final source alignment remains pending until the implementation is written; this
receipt proves diagram delivery and agreed design semantics, not runtime tests.

## Changes

- Updated `docs/architecture/conditional-add.workflow.json` and its HTML: expired
  remainder cancellation, owner CLOSED after residual exit/scoped cleanup, and
  terminal retirement of unsent QUEUED adds are now explicit.
- Added `docs/architecture/add-termination.workflow.json` and its HTML: one lane
  follows an expired entry/add target through durable budget and bounded cancel to
  actual outcome reconciliation; the other lanes distinguish unsent retirement
  from preserved signed work.
- Updated `docs/architecture.md` links and the ownership explanation.

The focused flow intentionally distinguishes two triggers (order expiry/exit and
terminal owner) rather than drawing an invalid edge implying every canceled add
closes its owner. Straight unlabeled arrows express the adjacent named steps;
additional labels would repeat their endpoints. The two retirement branches retain
explicit `no attempt` / `attempt exists` guard labels. The overview retains explicit
expiry and SL/TS/strategy labels. These are implementation diagrams, not grants.

Confirmed detail behind the concise nodes: cancellation start is persisted on the
entry/add attempt before cancel effects and before missing-target intervention.
Matching-target legacy cancel history preserves an existing budget. An owner-level
legacy timestamp is usable only when it falls between target creation and that
target's matching historical cancel. Unknown targets and exhausted deadlines/caps
still fail closed; UNKNOWN cancel outcomes are not retried blindly. The diagram
shows the supported cancel path, not every intervention branch. FINISHED means
CLOSED, REJECTED or PREVIEWED. Retirement changes only QUEUED tranches without a
durable matching attempt to CANCELED with a reason/time, including already-finished
owners on supervisor repair. Status remains read-only. Signed/UNKNOWN records are
retained, never represented as unsent retirement.

## Deterministic and browser checks

For each `NAME` (`conditional-add`, `add-termination`):

```sh
node /root/.codex/skills/archify/bin/archify.mjs validate workflow docs/architecture/NAME.workflow.json --quality showcase --json
node /root/.codex/skills/archify/bin/archify.mjs deliver workflow docs/architecture/NAME.workflow.json docs/architecture/NAME.html --quality showcase --json
ARCHIFY_CHROME=/root/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome node /root/.codex/skills/archify/bin/archify.mjs visual-check docs/architecture/NAME.html --json
```

Both final validate/deliver commands exited 0: showcase 9/9 checks, 0 composition
errors, 0 warnings. No geometry repair was needed (correction_rounds: 0). Default
Chrome discovery initially returned skipped/exit 2; using the installed Chromium
through the documented `ARCHIFY_CHROME` setting completed both checks with exit 0.
This final successful artifact-bound evidence supersedes the environmental skip.

For each HTML, all four viewport checks (1440x900, 1600x1000, 1920x1080,
2048x1320) passed containment, node-text readability and viewer-chrome clearance.
Light/dark screenshots at 1440x900 and 2048x1320 were all inspected with the image
reader. Routes, labels, node/card fit, legend and navigation remain legible and
unobstructed; the larger compositions retain balanced height. Perceptual review:
passed. Interactive focus/search closure and actual export actions were not manually
exercised; screenshots do not establish those behaviors or live exchange semantics.

Canonical browser sidecars were moved without changing their bytes from the HTML
directory to `diagram-browser-evidence/`, preserving their names and relative
contact-sheet links. Receipts retain the absolute source HTML path and its exact
SHA-256. Exact specification/artifact hashes and byte counts are in
`diagram-handoff.json` and the two `diagram-*-deliver.json` receipts. Final source
and artifact byte identity were rechecked after capture. No HTML postprocessing,
renderer changes, live account calls, trading changes, commits or publication were
performed by this diagram subtask. No new skill observations arose from this work.
