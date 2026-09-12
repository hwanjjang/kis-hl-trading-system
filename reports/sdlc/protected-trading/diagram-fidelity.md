# Implementation and target-diagram fidelity

All three previously validated Archify target views are retained unchanged. Their
source and HTML digests therefore preserve the earlier artifact/browser/perceptual
checks in reports/sdlc/multi-venue-protection. The code-to-target mapping is now in
docs/architecture.md, and operational limits are in docs/trading-operations.md.

The implementation directly reuses the Trail policy inside an account supervisor;
it does not enroll partial entries into the legacy single-position worker. Local
journal publication is transactional in the same SQLite database, without a
separate outbox process. Strategy-code evaluation and notifications remain future
edges. These differences are explicit and do not imply deployed future services.
KIS cumulative summaries remain pending until sourced execution/cost imports.

Curated desktop previews are retained here as diagram-*.png; disposable browser
sidecars and skill staging files are ignored by .gitignore.
