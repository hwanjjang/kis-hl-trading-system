# Bounded conditional add contract

Extend existing Signals, ExecutionStore and Supervisor. A signal's add plan explicitly identifies its existing position, units, fixed stop, expiry, unchanged protection parameters, expected size and entry-fill total, source setup snapshot and completed condition bar. Persist an immutable tranche on the same owner with a unique (scope, mode, signal intent) reservation before any submission. Unknown submission outcomes are reconciled, never retransmitted. Direct raw entry paths cannot submit add plans.

Automated Hyperliquid sizing requires account-total source evidence, not caller equity. Initially reconcile unified USDC-only balances from spotClearinghouseState and verified userAbstraction; reject unknown/legacy/portfolio modes and unvalued nonzero assets. Individual dex accountValue is diagnostic only. The execution gateway rereads the selected account and recomputes sizing with current lot rules; any sizing change requires a new approval. Buying power is checked independently; no transfers or new unit caps.

Reconcile all owned buy attempts and retain per-tranche actual fills. Incremental fixed stops cover the current uncovered quantity at the confirmed common fixed SL. Existing verified stops and native trails stay untouched. Local trail ratchets and frozen ATR remain on the owner. After terminal adds, native coverage can be enhanced with a full-current-size reduce-only overlay while retaining prior native watermarks; local backup is mandatory for this path. Any protective execution latches a full residual exit. Native-only plans or external percentage trails require an explicit supported migration before adding. Native overlay failure retains verified SL and blocks further risk.

Admission rejection/expiry changes only tranche state; existing management continues. Add fill protection uses its own grace clock. The account entry switch is never enabled by add authorization. Ordinary exits remain full residual, reduce-only and bounded; cleanup targets only persisted owned order IDs.

Sources: issue 27; official Hyperliquid account abstraction modes and info endpoint (2026-09-24). Unsupported capital modes are explicit fail-closed limitations, not segment fallbacks.

## Post-merge lifecycle corrections

Persist cancel_started_ms on each target entry/add attempt before cancellation
side effects. Retries/restarts reuse it. For legacy attempts, matching-target cancel
history establishes the prior budget; a compatible legacy owner timestamp may
preserve an earlier start only when bounded by target creation and known matching
cancel. Unmatched owner clocks never constrain a later order. Existing retry caps,
unknown-target intervention and full-position protection/exit semantics stay intact.

When an owner is CLOSED/REJECTED/PREVIEWED, retire QUEUED tranches only when no
durable matching attempt exists. Record CANCELED, reason and retired_ms; preserve
all sizing/history and any signed/UNKNOWN/SUBMITTED attempts. Apply after terminal
save and on the supervisor's finished-owner path to repair older rows. Status
remains read-only. Serialize the cleanup check and updates in SQLite.
