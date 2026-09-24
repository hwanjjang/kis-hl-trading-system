# Main integration review: PR 26

Verdict: PASS; no required fixes identified in the scoped interaction review.

Reviewed incoming `a156b69` via `6d9cd13^1..6d9cd13`, concentrating on configuration identity, `scope_client`, strategy grant/signal commands, account-local advisory sizing and corresponding documentation. This is not an audit of all incoming changes. Candle timestamp work was excluded as assigned.

## Findings and reasoning

- Configured execution account now resolves to the subaccount while retaining master identity separately. Existing strategy grant creation and `signal execute` both use `scope_client`, as does the supervisor, so their scope keys remain aligned after the merge.
- Existing account-scoped grants are not silently moved. Scope equality remains enforced before reserving or enqueueing a signal, and the new operations documentation explicitly requires reconciling prior account state/grants when routing changes.
- Advisory sizing remains an explicit account snapshot calculation, without reading or pooling master/subaccount funds. It does not instantiate a signer or automatically populate order quantities. Existing `accountValue * 10` and explicit scope/source policy are compatible with the effective execution-account change.
- A distinct public-read override clears credentials and subaccount routing; signal/grant commands use the configured execution route rather than accepting such a read override as authorization.
- Existing PR26 non-entry setup restrictions remain present; the upstream merge does not remove the shared authority guard or change strategy quantity semantics.

## Offline evidence

`python3 -m unittest tests.test_subaccount_routing.SubaccountConfigTests tests.test_subaccount_routing.SubaccountScopeTests tests.test_strategy_signals tests.test_operations_cli`

Result: 21 tests passed in 1.193 seconds, exit 0. All scope/config and signal tests were offline; no SDK signing or vendor API execution was needed.

Separate temporary-SQLite integration probe invoked actual `cmd_strategy`/`cmd_signal` handlers under a synthetic subaccount configuration and fixed clock. An existing master-scoped grant was rejected with `Grant scope does not authorize this plan`. A newly created CLI grant adopted the configured subaccount scope, and a paper signal using that grant reached QUEUED in the same scope. No supervisor/gateway was run and no order was placed.

README and operations additions accurately explain execution-account changes, nonmigration of old scope records and advisory-versus-execution boundaries. No live routing, external action or candle timestamp claim was made by this review.

## Reviewed identity

HEAD: `6d9cd131acf26f19bcdbce412ef2c1c9dc6bf17a`.

- `kis_hl/config.py`: `4199b0afa3e5c68300d685ee9c8860b3cbae1e70a7f2d5833b63d1e1623c3dbf`
- `kis_hl/operations_cli.py`: `1a60a800435dd27df63842fa59b20851efd4b98cca3aa2a439691d0fdd731d52`
- `kis_hl/strategy_signals.py`: `1fe607a5a4ecb18a0b45a8acdea7292535c30868fabcc436f831fd1b7c0ee8d6`
- `README.md`: `169f800ff093692c9b99f2108983d8893ed9b2a9a0f62fa4ec98b13ddd19d0e4`
- `docs/trading-operations.md`: `d776660f54bf200bf2201df2fee969d425c63812b643166e48036be8e6a86094`
- `docs/strategy-tools.md`: `52774c63de4a9ecc8b47d6f58ba022a451bd58a253533be5cd98f5b19810e600`
