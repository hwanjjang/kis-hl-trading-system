# Self-verification
Builder /root. Local implementation only. Acceptance AC1-AC4 checked using code, regression tests, source-contract inspection and an additional offline functional smoke.

- Intended red: absent native adapter/policy/readback (red.log); fractional ATR unsafe precision (precision-red.log); use of SDK read instead of public repository info client (public-read-red.log).
- Green: 90 relevant tests, exit 0 (green.log).
- Post-refactor regression: full suite, 433 tests, exit 0 (post-refactor.log).
- Additional smoke: actual CLI subprocess + SQLite paper lifecycle + actual hyperliquid-python-sdk 0.24.0 L1 signature creation/recovery; exit 0, no network, no persisted secret (smoke.log).
- git diff --check passed. No commit/push or live trading.
- Dependency setup: ensurepip unavailable, so uv installed declared dependencies into /tmp/hl-trailing-venv; no project dependency change.

These establish offline implementation behavior. Exchange acceptance, native response shapes, mark-price activation/partial fills and live cancellation are not integration-tested. Unexpected formats or unknown outcomes fail closed and retain fixed SL. Independent verification remains a separate report.
