# Issue 15: isolated margin at the fixed stop

The risk-unit sizing calculator already implements operating capital and fixed-stop
quantity. Operators still need an advisory isolated-margin requirement for the
proposed tranche, independently of quantity and execution authority.

- AC1: fresh matching Hyperliquid metadata and explicit allocation produce initial
  margin, stop maintenance, required allocation and nonnegative shortfall using
  rounded quantity; long, short, tier boundaries and BTC fixed notional are covered.
- AC2: absent, stale, malformed or mismatched evidence is unavailable; KIS and
  explicit cross margin are not applicable. Unit sizing remains independent.
- AC3: quantity, existing execution guards and order authority remain unchanged;
  documented offline CLI usage reproduces the report without live operations.

AK authorized implementation and pre-merge work, including tests, commits, push,
PR creation, configured independent reviewer and CI inspection. Merge, auto-merge,
queue entry, production deployment, credentials and account/permission changes
are excluded. Builder: OpenAI Codex /root; reviewer: configured AK Anthropic account
through Paseo, separate isolated context, latest catalog GA model, medium, native auto.

2026-10-03 amendment: AK selected issue 15 only for this PR. Issue 51 short trailing
is assigned to another workspace. Local short changes are preserved in the ignored
planning backup. The stable execution record remains issue-15-51 without resetting
stage counters. Base was updated to c8d0400 with git pull --autostash origin main.

The report assumes the fixed stop is a mark price. Fees, funding, gaps and slippage
are excluded. Zero buffer is the maintenance boundary, not an execution guarantee.
