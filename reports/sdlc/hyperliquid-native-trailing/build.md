# Build
Implemented AC1-AC3 via a separate app-observed trailing action with SDK L1 signing, strict immediate quote-distance readback, explicit native plan selection, fixed-SL-first management, terminal-entry sequencing, durable attempts and fail-closed unknown outcomes. Low-level adapter supports percentage/delayed activation; managed mode deliberately selects immediate frozen ATR distance only. This does not alter default local nine-minute policy.

Changed source/test set and content identity: candidate.json. Local changes remain uncommitted. Independent verification identified raw ATR precision risk; added intended-failure regression, then rounded distance down to the observed tick and bound readback to persisted distance. Added CLI/SQLite/real SDK signing smoke. Shared account locks caused two transient test errors during parallel suites; isolated TMPDIRs resolved the fixture collision without changing product locks.

Research: official app action, standard signer, readback parser and generic cancel. Live exchange responses were never fabricated as observed evidence. Opaque acknowledgements deliberately remain unknown. No cloid was added to the undocumented action. No automatic matching or resubmission.

Skill reference updates use the repository canonical .agents path with the existing .claude relative symlink; Codex discovers the canonical skill via AGENTS.md/session catalog. No new hooks or installation was required.
