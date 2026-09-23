# Independent verification

Verdict: PASS. Proposed HOTL decision: PROCEED. No mandatory findings.

Reviewer: `/root/hermes_entry_verify`, fresh non-builder context. This is local independent QA, not a PR review or a cross-provider review eligibility claim. Candidate: `sha256:6f83f2b792df0c4fa1129ac7daf2ea098c284f446a24773c6e421ac8db7fd957`; base: `cc8f48e5a005239e9d397f3f6a7ae2a27300ee09`. All five candidate file hashes were independently recomputed and matched candidate.json. Consumed input digests are retained in delegations/hermes-entry-verify-1.json.

## Acceptance assessment

- AC1 PASS: actual diff and JSON accurately separate CLI preparation/validation, durable enqueue, independently running account worker, and exchange execution. `operations_cli.py:489` reads ATR and returns a plan; `operations_cli.py:514` previews or enqueues; `managed_execution.py:183` records mode and QUEUED; `operations_cli.py:584` acquires the account lock and filters matching live/paper rows; `managed_execution.py:475` completes paper rows as PREVIEWED before venue preflight. The text explicitly requires both live flags, same DB/account, and a persistent worker. Direct CLI authority is distinct from optional signal/grant authority (`strategy_signals.py:142`, `:176`, supervisor recheck at `managed_execution.py:562`).
- AC2 PASS: challenged the implied chronology against code, rather than accepting diagram arrows alone. Defaults are native plus local backup (`managed_execution.py:132`). Local Trail creation/tick is inside observed size > 0 (`:668`, `:688`), preceding the native eligibility branch; cards and prose correctly say local tracking may start earlier. Partial-fill SL coverage is checked and missing quantity sent (`:697`); native submission requires verified protection, freshness and terminal entry (`:801`). An existing trailing attempt prevents re-creation; active matching readback alone supplies coverage (`:789`). Residual exits wait for unresolved attempts and use current executable size (`:866`); gateway makes exits reduce-only (`managed_gateways.py:348`); CLOSED waits for flat exposure and terminal owned orders (`managed_execution.py:940`). `_send` persists row and attempt before transmission (`:378`).
- AC3 PASS: independently checked five new discovery links and heading targets, exact delivered artifact/spec/browser hashes, all four recorded browser containment results, and `git diff --check`. Independently visually inspected the exact candidate's 1440x900 light screenshot: all cards and labels fit, with no overlaps. Diagram is a simplified sequence whose cards carry concurrency/paper/authority qualifications. Existing final validation has nine passing checks, zero errors/warnings. Historical failed design evidence is not used as current acceptance evidence.

## Commands and evidence

- `git diff -- README.md docs/trading-operations.md docs/architecture.md`: inspected actual prose changes; new JSON read separately.
- Focused `rg` and `sed` source reads for operations_cli, managed_execution, managed_gateways and strategy_signals: claims checked against branches listed above.
- Independent Python 3 offline assertions: all five hashes, artifact/browser binding, four viewport results, five introduced links, empty runtime source diff, and `git diff --check` passed. Results: verifier-offline-checks.json.
- `view_image` on design-final/hermes-entry.visual-check.1440x900.light.png: visually inspected.
- Environment corrections: initial `python` command was unavailable (exit 127); repeated with `python3` passed. A speculative source search named absent order_policy.py; defaults were found and reviewed in managed_execution.py. Neither is a product failure.

## Limitations

No exchange requests, orders, code edits, runtime regression suite, commit, push or publication. Browser execution and other screenshot sizes reuse builder evidence after exact artifact hash verification; independent reviewer inspected one screenshot, not every theme. The 1440px sequence labels are compact and may require viewer zoom; they meet the recorded validation threshold. No live trailing-contract guarantee is inferred: the documentation explicitly marks that contract unverified. No task-observer improvement was identified; no shared observation state or planning files were modified.
