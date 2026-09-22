# PR review — binance-order-execution (2026-09-16)

| Field | Recorded value |
| --- | --- |
| Task / stage / owner | binance-order-execution / pr-review / main agent (launcher only; reviewer is a different provider) |
| PR | https://github.com/hwanjjang/kis-hl-trading-system/pull/18 — head 2a46b02 (`binance-order-execution`), base `review-binance-mcp-issue` (1b2a337) |
| Author provider / context | Anthropic (Claude Fable 5.1), main session 6f2136d6 |
| Reviewer selection | Provider OpenAI via installed Codex CLI 0.153.4 (`~/.codex/auth.json` present). Model `gpt-6-astra`: highest-priority listed, `supported_in_api: true`, per `codex debug models` on 2026-09-16 (catalog does not label GA/preview; it is the newest listed model and priority 1). Requested effort `medium` (model default is medium). Sandbox `read-only`, approval `never` (non-interactive exec). |
| Observed configuration | Codex stderr: `model: gpt-6-astra`, `reasoning effort: medium`, `sandbox: read-only`, `approval: never`, session id 01a0ac21-c452-74e2-8c23-5ffe415eb872 |
| Execution result | **Not executed.** `codex exec review --base review-binance-mcp-issue …` exited 1 with `ERROR: You've hit your usage limit … try again at Sep 19th, 2026 1:18 PM` (`pr-review/codex-stderr.log`). Two earlier attempts failed on CLI usage (`-s/--json/-o` are `exec`-only; `--base` cannot be combined with a custom prompt). |
| Status / decision | **BLOCKED** — eligible cross-provider review unavailable until the Codex usage window resets; no self-review substituted. |
| Next action | Re-run `codex exec review --base review-binance-mcp-issue -c model='"gpt-6-astra"' -c model_reasoning_effort='"medium"' -c sandbox_mode='"read-only"' -c approval_policy='"never"'` after 2026-09-19 13:18 (or after credits are added), record the verdict here, then run correction if findings exist. |


## Execution 2026-09-19 13:23 CEST (iteration 2)

- Command: `codex exec review --base review-binance-mcp-issue -c model='"gpt-6-astra"' -c model_reasoning_effort='"medium"' -c sandbox_mode='"read-only"' -c approval_policy='"never"'` from the worktree at head 2a46b02 (PR #18 head confirmed via GitHub API before the run).
- Observed (stderr): `model: gpt-6-astra`, `reasoning effort: medium`, `sandbox: read-only`, `approval: never`; exit 0. Full text: `pr-review/codex-review-2026-09-19.md`.
- Reviewer verdict: CHANGES_REQUIRED (three P1, one P2). Findings (reviewer wording summarized; author disposition recorded in correction.md):
  1. P1 `trading.py:169` — STOP_MARKET / TRAILING_STOP_MARKET should go to the Algo Order API (`/fapi/v1/algoOrder`); the regular `/fapi/v1/order` path rejects conditional types with `-4120`, so `binance-stop --live` would not install protection.
  2. P1 `trading.py:281-283` — HTTP 503 "Unknown error" (order may have executed) is recorded as `rejected`; needs a distinct unknown state and reconciliation by client order id / user stream before any retry.
  3. P1 `trading.py:119-122` — reduce-only orders are exempt from MIN_NOTIONAL on Binance; the local check blocks legitimate small position exits.
  4. P2 `trading.py:151-153` — stop direction is always checked against mark price even when `workingType=CONTRACT_PRICE`; should compare with the last price in that case.
- Reviewer limitations stated: read-only filesystem and no network, so it could not run the full suite or re-read the official docs.

## Rounds 2–10 (2026-09-19 → 2026-09-20), same command and observed configuration each time (gpt-6-astra, medium, read-only, approval never; stderr logs `pr-review/codex-stderr-round*.log`, outputs `pr-review/codex-review-round*.md`)

| Round | Head | Findings | Disposition |
| --- | --- | --- | --- |
| 1 | 2a46b02 | P1 algo API for conditional orders; P1 unknown outcome vs rejected; P1 reduce-only MIN_NOTIONAL; P2 CONTRACT_PRICE direction | all fixed in 3bd980d |
| 2 | 3bd980d | P1 HTTP 408 / -1007 unknown; P1 algo cancel symbol guard; P2 account-wide algo listing | fixed in 8b95376 |
| 3 | 8b95376 | P1 wrong path /fapi/v1/algoOpenOrders → /fapi/v1/openAlgoOrders (verified by unauthenticated probe); P2 account-wide listing gaps | fixed in ae22acd |
| 4 | ae22acd | P2 ALGO_UPDATE user-stream events not parsed; P2 `\b-1007/` regex never matched | regex fixed in 097f353; ALGO_UPDATE parsing **deferred** (Recommended): exact event schema not available offline; recorded as an open risk in docs/architecture.md and completion.md |
| 5 | 097f353 | P2 reconciled terminal algo stored active | fixed in 683c35b |
| 6 | 683c35b | P1 partially filled terminal order classified rejected; P2 incomplete algo listing returned silently | fixed in a4510f7 |
| 7 | a4510f7 | P2 confirmed cancel leaves protective_orders active | fixed in ca59dae |
| 8 | ca59dae | P2 cancel by both identifiers; P2 FINISHED algo stored active; P2 .env.example demo profile pinned mainnet | fixed in 1d7d3a4 |
| 9 | 1d7d3a4 | P2 cancel outcome reconciliation; P2 deactivation not scoped by environment/account | fixed in bc454f4 |
| 10 | bc454f4 | none ("no reproducible must-fix defects"; 45 trading tests passed in the reviewer's sandbox; real exchange not exercised) | **PASS** |

Every fix was written test-first (red logs `logs/unittest-red-correction*.log`) and re-reviewed by the next round. Reviewer resolution for each Must Fix = the following round raised no repeat of it.

## Round 11 (2026-09-20, head 7ffb790)

After QA iteration 2's two Should Fix items (skill wording on 5xx/408/-1007, `binance-stop --exchange-test` removed, mixed cancel ids rejected): "no new defects worth pointing out" (88 related tests run in the reviewer's read-only sandbox; 19 could not complete there because temp/lock files cannot be created). **Final verdict: PASS.** Published record: PR #18 readiness comment (see receipt `record_url`).
