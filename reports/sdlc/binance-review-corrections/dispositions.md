# Review finding dispositions

Source: local review-2026-09-24.md (original left untouched), [PR17 review](https://github.com/hwanjjang/kis-hl-trading-system/pull/17#issuecomment-5813171977), [PR18 review](https://github.com/hwanjjang/kis-hl-trading-system/pull/18#issuecomment-5813172166). Recommended follow-ups are not marked fixed.

| ID | PR | Disposition | Evidence / follow-up |
| --- | --- | --- | --- |
| F01 | 17 | Corrected | Idle Binance user stream is marked stale every 10 minutes: the 30-minute keepalive never runs and reconnect backoff grows to 30 s blind gaps that lose order events |
| F09 | 17 | Corrected | Binance CLI tests load the operator's real .env, and BinanceConfig's repr includes api_key/api_secret, so a failing mock assertion prints real secrets |
| F18 | 17 | Corrected | PR #17 does not merge cleanly into current main (GitHub reports CONFLICTING/DIRTY), which blocks the stacked merge |
| F45 | 17 | Corrected | architecture.md restates Binance websocket facts owned by the binance-api skill, so the wrong 30-minute renewal claim now appears in four places |
| F02 | 18 | Corrected | Binance live eligibility is only an env-string allowlist, so main's asset-exclusion, listing and session rules are never checked |
| F16 | 18 | Corrected | architecture.md says order placement was validated on the exchange test endpoint; it never was |
| F29 | 18 | Corrected | SKILL.md lets agents run signed --exchange-test calls on their own, a permission that belongs in CLAUDE.md's agent rules |
| F43 | 18 | Corrected | README outcome notes contradict the code, and the outcome rules are restated in four places that have drifted apart |
| F44 | 18 | Corrected | Binance diagrams, their index and .env.example still describe order placement as 'planned' or read-only after it was implemented |
| F52 | 18 | Corrected | No test pins the account lock or the cancel-algo check that the allowlist runs before the lookup |
| F15 | both | Corrected | binance-api skill references are stale against the new order path: rest-endpoints.md still documents conditional orders on POST /fapi/v1/order under 'NOT implemented', limits-and-errors.md keeps pre-order retry guidance, and new endpoints are missing |
| F10 | 17 | Corrected | binance-user-stream never exits on missing credentials or permanent auth/ban errors; listenKey failures are retried forever |
| F11 | 17 | Recommended follow-up | Needs stable account/environment schema and unknown legacy-row migration; separate DBs documented. |
| F13 | 17 | Recommended follow-up | Buffered writer needs shutdown/backpressure/crash semantics and sustained-rate tests; synchronous throughput limitation documented. |
| F12 | 17 | Documented / partially corrected | PR18 already has algo reads; PR17 read-only limitation explicitly documented. |
| F14 | 17 | Recommended follow-up | Canonical ingestion needs Binance instrument registration and input contracts; legacy observational exception documented. |
| F19 | 17 | Recommended follow-up | Historical receipt restoration is outside runtime correction scope; preserve prior explicit artifact cleanup. |
| F24 | 17 | Corrected | A failed keepalive on the message path drops the user-stream event that triggered it |
| F25 | 17 | Recommended follow-up | Event spool/replay and reconnect reconciliation need a durable recovery contract; storage-loss limitation documented. |
| F26 | 17 | Corrected | Environment selection can silently resolve to mainnet or split REST and WS across environments, and URL schemes are not validated |
| F37 | 17 | Corrected | stream_route() sends public-tier streams without a '@bookTicker'/'@depth' suffix (e.g. !bookTicker, @rpiDepth) to /market, where they never deliver frames |
| F39 | 17 | Corrected | Stored Binance tick payloads are a lossy normalized subset, not raw frames, even though the storage contract this PR edits says raw payloads are kept |
| F47 | 17 | Corrected | The mixed-route negative CLI test is not isolated: if the guard regresses, it opens a real mainnet websocket and hangs the suite |
| F48 | 17 | Corrected | New Binance test classes are appended after 'if __name__ == "__main__": unittest.main()' and are skipped when the file is run directly |
| F53 | 17 | Recommended follow-up | New lifecycle and guard regressions cover corrections; exhaustive endpoint/header mutation coverage is follow-up. |
| F27 | 17 | Documented / partially corrected | Corrected key reuse/close semantics; automatic shared-key deletion intentionally excluded. |
| F55 | 17 | Documented / partially corrected | Rejected nonfinite market ticks and bounded/redacted HTTP errors; optional order-event fields remain tolerant. |
| F61 | 17 | Documented / partially corrected | Split Binance provenance; legacy diagrams remain scoped to their historical revision. |
| F62 | 17 | Recommended follow-up | Cosmetic shared-rule placement; current rule already applies across venues. |
| F07 | 18 | Corrected | A 2xx ack whose RESULT body is already terminal (EXPIRED/EXPIRED_IN_MATCH) is reported as 'submitted', while the unknown-outcome lookup reports the same state as 'rejected' |
| F17 | 18 | Corrected | CLI protective-order state transitions for unknown and rejected outcomes are untested (mutations survive) |
| C01 | 18 | Corrected | Live binance-stop never reads the position, so a wrong-side closePosition stop or an undersized stop is accepted and recorded as active protection |
| F03 | 18 | Recommended follow-up | Needs durable pre-send attempt/recovery state, scoped deduplication and crash tests; post-send audit limitation documented. |
| F04 | 18 | Documented / partially corrected | Corrected retry guidance; durable request deduplication remains recovery work. |
| F08 | 18 | Recommended follow-up | Venue-aware protection schema and entry association require migration. Removed hard-coded source ID example; documented operator audit link. |
| F20 | 18 | Recommended follow-up | Identity reconciliation belongs with durable pre-send intent/account scope; one-shot lookup unchanged and manual investigation required. |
| F21 | 18 | Recommended follow-up | Protection recovery requires ALGO_UPDATE/child-order lifecycle and persisted attempts; unknown stays inactive, manual recovery documented. |
| F23 | 18 | Documented / partially corrected | Added live metadata and static min/max price validation; dynamic bands remain exchange-validated. |
| F28 | 18 | Recommended follow-up | API-key lock cannot infer account identity across keys; account ownership requires managed gateway integration. |
| F30 | 18 | Corrected | Stop and cancel ID flags do not match: a stop placed with binance-stop --client-order-id must be cancelled with --client-algo-id, and binance-cancel silently drops --order-id when --client-order-id is also given |
| F31 | 18 | Corrected | binance-stop and binance-trade silently ignore flags that do not apply to the chosen mode |
| F32 | 18 | Corrected | The README trailing-stop example always fails because the SELL activation price is below the mark price |
| F33 | 18 | Corrected | The demo key profile is missing from the credential error, from the skill's credential/environment guidance, and from the .env.example permission note |
| F34 | 18 | Documented / partially corrected | Corrected -1008 HTTP semantics; conservative unknown handling remains documented. |
| F41 | 18 | Recommended follow-up | Older algo cancellation needs verified alternative identity evidence; preserve fail-closed cancellation. |
| F42 | 18 | Corrected | The skill's route-existence probe ignores the HTTP method, and its example calls a real endpoint nonexistent |
| F46 | 18 | Corrected | Binance live-path tests take the real system-wide account flock with a fixed key, so concurrent test runs fail |
| F49 | 18 | Corrected | unittest.main() in the middle of test_binance_trading.py hides 24 of 45 tests when the file is run directly |
| F50 | 18 | Corrected | The 'hides_credentials' CLI test checks for a field name, not for a credential value |
| F51 | 18 | Corrected | Reconciliation test mocks answer any GET, so the algo lookup routing and some branches go unasserted |
| F54 | 18 | Corrected | Order CLIs turn an invalid decimal into an unreadable '[<class decimal.ConversionSyntax>]' error |
| F59 | 18 | Recommended follow-up | Preserve flat CLI/default BTCUSDT compatibility while adopting expressly requested --dry-run mode; unified CLI is separate integration. |
| C02 | 18 | Recommended follow-up | TRIGGERED may have a working child; remaining coverage needs child-fill reconciliation, documented separately from lifecycle. |
| F58 | 18 | Documented / partially corrected | Corrected response section and consolidated errors/outcomes. |
| F60 | 18 | Documented / partially corrected | Corrected explicit dry-run/no-signed-call wording; detailed lookup paths remain in the order reference. |
| C03 | 18 | Corrected | CLAUDE.md ownership row and sync rule for binance-api still cover only the read-only data plane (client.py/ws.py), not order placement in trading.py |
| F06 | both | Documented / partially corrected | Documented raw CLI boundary; managed trading integration is separate work. |
| F35 | both | Corrected | The skill's error-code tables map -4003/-4004/-4005 wrongly and give no correct codes for tick/step violations (-4014/-4023) |
| F36 | both | Documented / partially corrected | Corrected full-universe endpoint contract; bounded metadata cache deferred to avoid stale live filters. |
| F38 | 17 | Refuted in original review | Retain original verifier rationale. |
| F40 | 17 | Refuted in original review | Retain original verifier rationale. |
| F05 | 18 | Refuted in original review | Retain original verifier rationale. |
| F22 | 18 | Refuted in original review | Retain original verifier rationale. |
| F56 | 18 | Refuted in original review | Retain original verifier rationale. |
| F57 | 18 | Refuted in original review | Retain original verifier rationale. |
