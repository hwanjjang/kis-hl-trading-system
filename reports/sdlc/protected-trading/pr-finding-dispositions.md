# Author response to PR review 1

F1 accepted: snapshot RuntimeError/OSError failures retain readback in DEGRADED.
Three consecutive failures or the protection grace period latches exit; the
read-outage intervention automatically continues cancellation/exit when valid
readback returns. Identity/ownership interventions remain manual. Original clocks
and UNKNOWN attempts are retained; failed snapshot type/count are persisted
without transport payloads. Regressions cover transient recovery, repeated failure
and preservation of an existing identity intervention.

F2 accepted: ETH native perpetual now has an explicit 24/7 session mapping and a
weekend regression; trading-hours owner documentation is updated.

F3 accepted: last_attempt_ms/last_reason are migrated into the existing SQLite
schedule, separate from successful collection and actual coverage. Every incomplete
or failed collection defers the next scheduled attempt by the configured interval.
Historical successful queries schedule from completion time. The real CLI handler
with fixture transport is exercised across two polls and invokes collection once.

F4 recommendation deferred: an operator attestation or arbitrary native-ID binding
would create new authority to resolve UNKNOWN submissions. This PR retains the
conservative reservation and forbids blind resend. Operations now explicitly say
recover retries readback only, specify broker-side exposure management, prohibit
SQLite retry edits and identify audited evidence binding as a prerequisite for
unattended KIS entry reliance after ambiguous acknowledgments. No live execution
or unattended installation is part of this PR. Reviewer should assess this deferral.

F5 accepted documentation: max_quote_age_ms also bounds action expiresAfter, with
local-expiry/UNKNOWN limitations stated.

F6 recommendation deferred: conservative pending records preserve correctness;
source correction/backfill is required until a separately tested flat re-anchor
workflow is implemented. The operations limitation is explicit.

F7 partly accepted: KIS verified_price_step is now required and positive in preview.
Read-outage events retain operation/class/count. Copying raw exception payloads is
intentionally avoided because vendor exceptions may contain sensitive identifiers;
broader safe error-code classification is a follow-up.

F8 accepted: KIS preflight records baseline_start_ms and snapshots reuse that date
window, including intents queued across a day boundary. Older stored rows retain
their previous created_ms behavior until recovered.

F9 recommendation deferred: the delivered views are the validated target design;
the implementation mapping and fidelity report explicitly identify future
notification components. Operations reiterate this boundary. The canonical plans
are tracked; gitignored execution notebooks are agent temporaries requested by the
user. A node-level future/implemented legend can be added in a later visual update.
