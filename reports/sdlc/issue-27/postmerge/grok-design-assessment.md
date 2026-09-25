# Grok design review assessment

Executed actual Grok CLI with --model grok-4.7 --reasoning-effort high
--permission-mode auto --no-subagents --disable-web-search. Paseo catalog confirms
grok-4.7 and high are available, but its launch adapter rejects mode auto because
no Grok modes are advertised. Direct installed Grok CLI supports auto; no host
permissions/settings were changed. This first task inspected design and proposed
boundary probes only. Raw local stream: /tmp/issue27-grok-design-stream.jsonl.
No final candidate or independent test PASS is inferred from the design review.

Reviewer proposed sixteen probes and eight design/test concerns. Dispositions:
- F1/F2 legacy interval and time origin: accepted. New boundary table tests creation
  and first-cancel endpoints, outside values and absent owner clock; same-target
  deadline always initializes from earliest matching cancel when prior evidence
  exists, not from current time. Existing attempt clock takes precedence.
- F3 terminal-state coverage: accepted all FINISHED states in regression table.
  Overview CLOSED node shows the ordinary full-exit path; focused diagram explicitly
  lists CLOSED/REJECTED/PREVIEWED. This deliberate split is not a narrower cleanup rule.
- F4 state-read purity and signed-work preservation: accepted. Smoke reads legacy
  pending state without repairing it; only subsequent supervisor tick retires it.
  Tables preserve every non-QUEUED status; any matching durable attempt is protected.
- F5/F6 independent retry cap, unknown cancel and missing target: existing rejected
  cancel cap test retained; deadline/reopen/process-death assertions strengthened;
  unknown-target case asserts durable clock, zero cancel, no add retransmission.
- F7 transaction: cleanup reads owner/attempt/tranche state and updates candidates
  inside one BEGIN IMMEDIATE transaction. Final independent verification should
  challenge atomicity/failure paths.
- F8 simultaneous entry/add synthetic seed: not a supported admission state.
  Existing supervisor requires no active entry and the store allows one pending
  add. Retain fail-closed intervention instead of broadening multi-entry execution
  in this bug fix. Record this limitation in final reviewer context.

Final Grok verification/review will use frozen source and execute tests/probes.
