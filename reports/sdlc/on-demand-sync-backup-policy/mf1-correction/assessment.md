# MF1 correction assessment

Source: [PR19 review MF1](https://github.com/hwanjjang/kis-hl-trading-system/pull/19#issuecomment-5757258291), reviewed head `1343e90f2bfc44007c9a878b2f805cd6dd9a612c`.

Accepted: positive KIS orders with an unknown side could disappear while comparison and application succeeded. The shared `validate_domestic_orders` now rejects unknown/missing side and missing daily/cost corroboration. Capture calls the shared validator; comparison/application use it through `domestic_bundle`. The duplicated weaker audit guard was removed. Normalization verifies a multiset of date/symbol/side/order identities so all executed orders are represented exactly once. Zero-executed rows remain outside trades.

Author tests first reproduced the defect, then passed after correction. The real CLI smoke adds capture rejection (no output/DB), comparison rejection (no report/DB writes), and rehashed apply rejection (no writes). Normal capture/apply, journals, fees/funding, revisions and replay still pass. Source data is synthetic; no live account or private fixture was used.

Final checks: 55 focused tests, 415 full regression tests, 18 real CLI smoke subprocesses; separate verifier ran 9 new independent cases and 19 prior independent probes. See [validation](validation.json), [distinct verification report](independent-verification.md) and [reproducible probes](independent_probes.py). Run the probes with `PYTHONPATH=. python3 reports/sdlc/on-demand-sync-backup-policy/mf1-correction/independent_probes.py`.

No schema, API route or diagram flow changed. Existing Archify JSON/HTML remain valid. Rollback is a code revert; no operational DB was adjusted. Original reviewer findings and counters are preserved. Independent implementation verification passed; this author correction does not close the original reviewer's Must Fix or assert merge readiness. The current host exposes no reachable original xAI reviewer: native collaboration is OpenAI-only, and Paseo agent discovery could not reach its daemon; no service or permission setting was changed to create a reviewer.
