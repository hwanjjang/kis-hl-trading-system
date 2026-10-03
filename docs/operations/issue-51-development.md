# Issue 51: intent
Owner: root/OpenAI builder. Date: 2026-10-03. Revision: 1. Decision: PROCEED.
Source: [issue 51](https://github.com/hwanjjang/kis-hl-trading-system/issues/51).
AK requested implementation through pre-merge and a pull of origin/main.

The local single-position manager must support explicit enrollment of an already
filled, natively protected Hyperliquid short. Managed strategy entries and adds
remain long-only. Preserve legacy long snapshots and existing exit safety.

Acceptance criteria:
- AC1: Short completed-bucket lows tighten downward; equality/gaps/restart and legacy long behavior work.
- AC2: Filled sell entry, directional ledger/exposure and exact buy reduce-only Stop Market protection are verified; unsafe enrollment performs no mutation.
- AC3: Buy IOC exits round inward; partial fills, unknown restart and owned flat cleanup retain existing safety.
- AC4: Real offline short replay persists a downward threshold and durable exit intent; long/managed regressions pass.
- AC5: README, operations and a captured CLI manual explain explicit short enrollment and managed boundary.

Authority covers scoped code/tests/docs/evidence, commits, push, PR/issue updates,
CI and independent review/corrections using configured GitHub hwanjjang and Paseo
Claude/Codex review agents. It excludes secrets, new accounts, permission changes,
merge/auto-merge/queue and any live trading or production execution.

Risks: direction normalization, foreign entry evidence, stop-side verification and
unknown submission safety. All live short behavior remains unverified by offline
checks. Existing single-entry/position limits and fill-history cap remain.
