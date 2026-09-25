# Second review correction build — 2026-09-25

AK accepted the three recommendations from review5311414779 and requested that
work proceed. Scope: implement bounded expiry admission, defer temporary account
activity, verify, push existing PR30, and refresh its body. No PR merge or live
activation. Reuse issue27's existing main-owned plan and build iteration3.

Implemented changes:
- Approval rejects expiry beyond the earliest snapshot, completed-confirmation,
  position, daily/weekly history, original capital (including quote-age cap) or
  signal deadline. Grant expiry remains independently enforced. Current-time
  source validation and fresh execution reads remain mandatory.
- Add preview loads a registered signal_id and exposes expiry_deadlines_ms,
  max_expires_ms and expiry_within_bounds. A currently valid but overlong plan can
  be previewed without mutating it; it cannot be authorized. This is a dry run,
  with no implicit grant or admission bypass.
- Same-account/mode QUEUED/ENTERING/PROTECTING work defers an unsent add while
  checking expiry, revocation, source validity and the entry kill switch first.
  Hard states still reject. Recovery revalidates preflight and sends at most once;
  successful preflight clears the obsolete wait/error reason. Signed UNKNOWN
  handling and all full-position SL/TS behavior are unchanged.

Regression evidence: the first 26-test run failed with 10 assertion failures and
two errors. Snapshot expiry admission and temporary-wait failures were reproduced;
some later table failures were consequences of the first unexpected admission,
and one error was the missing preview field. These are not 12 distinct defects.
Initial focused Green passed 39 tests. Final tests add an explicit kill-switch
case and evidence-deadline equality; see round2-verification.md for final results.

Main advanced during this work to30758e7 with capital/exit-policy documentation.
Integrating it produced four documentation conflicts. Resolution retains the
main account-total clarification and exit-quantity policy, updates statements
about implemented add/reconciliation support, and keeps half-position execution
deferred to#28. No runtime file was stashed or altered during the verifier's tests.
The temporary owner-doc stash was restored into resolved content and dropped.
The final commit includes main as a parent; this is branch synchronization, not
PR integration into main. Main-only Weinstein instructions/skill files retain
their upstream content and both CLI links resolve to canonical skills.

Existing architecture/flow artifacts remain applicable: these are admission and
wait guards in the existing supervisor/CLI, with no schema or framework changes.
Source identity: round2-candidate.json; the optional integration_base records the
incoming main parent. Its 27-file source snapshot covers the feature candidate;
unmodified main-only imports are accounted for by that parent, not new features.
Diff: round2-changes.diff. Old review assessment probes target their documented
historical commits and are not tests of this corrected behavior.
