# Issue 49: observable nine-minute advisory monitoring

Source: https://github.com/hwanjjang/kis-hl-trading-system/issues/49 and AK's explicit pre-merge request on 2026-10-03.
Owner: Codex. Route: implementation / behavior / pre-merge.

Operators need sanitized failure causes, safe pending-bucket retries and one verified recovery notification. The original KORU incident cause remains unknown; synthetic gaps reproduce a failure path only.

## Scope and authority

Extract the profile-local monitor into tested repository code, install the scoped advisory implementation and thin profile wrapper, verify with read-only exchange calls against a scratch alert database, commit/push and open/update a PR, run CI and independent review/corrections. Use existing authenticated GitHub and configured reviewer contexts. Preserve unrelated deployment edits. No signed exchange call, order/cancel/transfer, automatic exit, native protection or position change, ATR/TS parameter change, merge, auto-merge, queue enrollment or permission-setting change is authorized. Operational and exchange state are read-only; deployment changes only the explicitly requested notification monitor.

## Acceptance criteria

- AC1: Complete buckets aggregate; gaps retain the prior watermark/high/threshold and retry successfully at a later tick.
- AC2: Distinct failures have distinct allowlisted reason codes; repeated reasons deduplicate; degraded-to-verified emits one recovery with covered-through time.
- AC3: Symbols remain independent, and transport never uses a signed/mutation path.
- AC4: Deployed cron wrapper calls the tested implementation; read-only scratch-state invocation reports verified evidence or a specific degraded diagnostic.
- AC5: Diagnostics omit secrets/account payloads; native protection, quantity and frozen TS parameters remain unchanged.

Risks: Publication delay is unconfirmed, retention is finite, cron can fail independently of monitor/protection, and stdout delivery is controlled by the existing scheduler. Do not reset existing bars. Merge stays disabled.
