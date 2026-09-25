# Third review correction handoff

Both recommendations from PR30 review5311943048 are implemented on source
candidate `0247846f212180b236cf803371254661bbcd6490ba95d58b45146be66d3d8f47` based on `cb0baa6ab0eb7c73910387ee2fe6eec2863ebcb5`.

1. Transient DEGRADED/ADOPTING peers wait within existing authority. Exit/cancel
   and recovery/intervention flags still reject, including stale PROTECTED snapshots.
2. Supervisor status/run --once expose pending_adds without rewriting protection
   state. UNKNOWN is visible and cannot resend. SL/TS continues for observed exposure.

Main focused37 and final210tests pass. Expanded real CLI/temporary SQLite smoke
with a stub exchange and forbidden sockets passes: lost acknowledgement, one send,
partial/complete reconciliation, full1.5SL/native TS. Independent local verification
passes203tests and15boundary probes, the smoke, source hashes and diff checks; see
round3-independent.md. No new Must Fix finding was reported. AC1–AC5 remain covered
by the regression scope and existing issue27 implementation; no live behavior is proved.

Authority: AK requested these fixes and previously authorized correction/push to
PR30. The publication amendment and previous round reports preserve that history.
This handoff prepares the verified candidate for commit/push and PR-body update.
The post-commit PR body binds the resulting commit to this source digest. The
historical local SDLC route is not a cross-provider PR-review or merge-ready claim.

No real account/protection, credentials, activation, capital mode, native migration
path or discretionary half-exit support changed. Earlier ETH add stays unarmed;
#28 remains deferred. Reviewer reassessment of the new head is separate; merge,
auto-merge and live trading are not authorized. Rollback affects new pending-add
reporting/wait guards only and must not cancel existing verified protection.
