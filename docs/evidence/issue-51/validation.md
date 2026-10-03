# Issue 51 validation evidence

Builder: root/OpenAI. Date: 2026-10-03. Base: c8d0400.
Scope: local single-position short trailing; no live operations or new assets.

- Test-first import on unchanged main, Python 3.14: 41 tests, 1 failure and 17
  errors (missing short API/CLI direction and mismatch guard). These were intended
  requirement failures. Initial system Python 3.9 import error is setup evidence,
  not TDD Red.
- Additional safety Red: flat short with wrong-side stop entered FLAT_CLEANUP.
  Fix: gateway rejects mismatched stop semantics as generation evidence, including flatness.
- Focused final policy/gateway/runner/CLI: 44 passed. Extended storage/stream: 52 passed.
- Full repository: 894 passed with `TMPDIR=/private/tmp .venv/bin/python -m
  unittest discover -s tests -t . -q`. Initial sandbox run had two environment
  errors: macOS symlinked temp path comparison and forbidden localhost bind.
  Both initial failures were retained; canonical temp path and allowed localhost
  rerun passed without test/source edits.
- Separate smoke: `python scripts/smoke_short_trailing.py` runs replay and status
  in separate real CLI processes with actual temporary SQLite. Observed low 92,
  threshold 96 from initial 104, PAPER_EXIT, durable trailing intent, zero attempts.
- Protection, opposite exposure, coverage, filled-entry, foreign ownership and
  increased-quantity tests reject without exchange mutation. Flat wrong-side stop
  and flat foreign generation perform neither submit nor cancel.
- Buy IOC inward rounding: price 105.6789, 1% budget -> 106.73; size 0.4567 -> 0.456.
  Unknown submit restart never resends; terminal partial fill retries residual;
  flat cleanup cancels only stop ID 7 after reconciliation.
- Existing long and managed regression coverage remains in the full suite.
- Manual: editable Markdown, two actual CLI output captures, two-page PDF.
  Both rendered pages inspected: no clipping/overlap; captures legible; source
  distinguishes executed offline replay/help from unexecuted account enrollment.

No live short lifecycle was exercised. Unknown/truncated fill history and existing
single-entry/position limits remain. Old binaries must not manage short snapshots.
No repository read-only staged/outgoing artifact checker is wired; this is an
existing enforcement gap. `git diff --check` and explicit staged/outgoing scope
inspection supplement actual tests and CI; no checker PASS is claimed.

Reproduction requires Python >=3.10 and requirements.txt; PDF authoring uses local
reportlab/Pillow/PyMuPDF, which are not product dependencies. On macOS use the
canonical temporary path for existing deployment tests. CI runs on Ubuntu.
