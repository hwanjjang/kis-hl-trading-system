# Independent verification: issue 24

Verdict: PASS for the reviewed deterministic code, canonical skill and local CLI behavior. A bounded refresh reviewed the rewritten design, operating policy, README and ownership instructions after the main agent updated them. This is a bounded local independent verification, not a different-provider PR review or a Hermes-host installation claim.

## Scope and authority

Reviewed the narrowed scope in `reports/sdlc/issue-24/scope-amendment.md`: strategy-authoring policy, Hermes-consumable skill, deterministic companion tools, strategy-document completion. No scheduler, Telegram transport, generic approval framework or live execution extension is required. No vendor API, issue mutation, commit, delegation or repository edit was performed. Temporary fixtures and this report are under `/tmp`.

## Checks and outcomes

- `python -m unittest ...`: not run because the host has no `python` alias (exit 127); reran with `python3`.
- `python3 -m unittest tests.test_strategy_tools tests.test_risk tests.test_strategy_signals tests.test_managed_execution tests.test_operations_cli`: 54 tests passed in 2.982 seconds, exit 0. This covers new calculations/predicates and existing execution/CLI integration.
- Generated raw offline fixtures from `tests.test_strategy_tools.setup()`, `snapshot()` and `NOW`, without importing expected test conclusions, in `/tmp/issue24-review-fixtures/`. Fixed replay time: `1789948800000`.
- `python3 -m kis_hl.cli strategy evaluate --input /tmp/issue24-review-fixtures/breakout.json --as-of-ms 1789948800000`: available, predicate passed, close 104 > prior high 102, weekly close 111 > EMA 96.5, ATR 4, no order authority.
- Same command with `missing-weekly.json`: unavailable, predicate false, reason `weekly history requires 30 closed bars`.
- Same command with `btc.json`: explicit `hl:UBTC/USDC` spot 3H evidence passes with weekly history absent; preserves the BTC exception and source identity.
- `python3 -m kis_hl.cli strategy indicators --input /tmp/issue24-review-fixtures/indicators.json --as-of-ms 1789948800000`: ATR 4, EMA 96.5, weekly close 111; no unavailable fields.
- `python3 -m kis_hl.cli strategy stop --input /tmp/issue24-review-fixtures/stop.json`: perpetual fixture entry 104, ATR 4, explicit N=2 produces stop 96 and distance 8.
- `python3 -m kis_hl.cli strategy size --input /tmp/issue24-review-fixtures/size.json --as-of-ms 1789948800000`: BTC fixed-80 path returns 0.769 BTC fixture units, notional 79.976, risk 6.152, operating capital 9990 from equity 999, below_minimum false, order_authorized false. This is synthetic arithmetic, not actual BTC market pricing or lot evidence.
- Additional temporary SQLite probe registered and ingested a synthetic decision, checked its authority at NOW, then checked NOW+60001 before signal expiry NOW+120000. It rejected stale setup evidence with `Strategy entry evidence is unavailable or no longer valid`; no execution rows existed. Thus the new guard is active beyond ingestion.
- Resolved all local links from canonical SKILL.md, its strategy reference, strategy-tools and strategy-authoring docs: all present. `.claude/skills/trend-strategy` and `.codex/skills/trend-strategy` both resolve to `.agents/skills/trend-strategy`.

## Independent skill forward review

Read the canonical skill and reference, then used the real tools above as a reviewer would. The raw fixtures supply market snapshots but do not establish actual holdings, pending orders, protection, buying power or user bounds.

1. Valid general breakout: numerical setup is supported by the two observed facts (closed prior-high break and weekly filter). I would return `no_trade` pending account and execution evidence, with the passing setup preserved as evidence. I would not fabricate a flat portfolio or translate `predicate_passed` into authorization.
2. Missing weekly evidence: `no_trade`; the general filter cannot be established. ATR can remain separately available, but that does not repair the absent weekly history. No signal entry should be ingested.
3. BTC exception: the spot 3H predicate can pass without the general weekly filter. Use the separate perpetual indicator snapshot for ATR and fixed-80 sizing, preserving spot/perp identities. The candidate SL/quantity above are internally consistent. Account/order evidence is still absent, so this raw fixture supports a conditional proposal only and `no_trade` as the current actionable outcome.

The skill explicitly forbids disguising add decisions as new entries, using the legacy BTC monitor, substituting trailing risk for fixed-SL sizing, or claiming unavailable live add/percentage trailing support. These instructions align with the reviewed guard and current bounded scope.

## Findings

No concrete mandatory correctness or authority findings in the reviewed candidate.

LOW / documentation accuracy / `docs/strategy_execution_design.md`: the sentence “Numeric tool outputs always carry order_authorized: false” overstates the actual schema: `strategy indicators` has no such field. Suggested narrow wording: “Setup, stop and sizing outputs carry ...”. This does not confer order authority or block correctness; sent to main for a small wording correction.

The final-document refresh confirms ×10 unrounded HL capital, ×1 KIS capital, removed old stop-risk/add-count caps, Hermes notification ownership and explicit unsupported live add-up/percentage-TS boundaries. The design does not claim automatic execution completion. Ownership entries and relative links agree with the canonical files. The inputs remain caller-asserted evidence; the code does not verify vendor provenance, actual portfolio flatness or real funds. This is explicitly documented and appropriate to advisory offline tools with existing preflight retained.

Documented limitations (not blockers for the narrowed scope): UTC normalized bar contract, no live add-up execution extension, no notification transport, no percentage-trailing extension, no Hermes runtime/discovery test in this environment. Shared filesystem discovery was verified; actual Hermes activation was not.

No reusable skill-observer observation arose from this bounded verification; no repository observation log was changed because the assignment was read-only.

## Candidate identity

HEAD: `758a511aefd37f89f9eec1bfcd3157484bc2566e` (uncommitted working candidate).

- `kis_hl/strategy_tools.py`: `a849846dc1da927dd1866910a2853c18e22dcfce43f4f74eb05166711b4b12a7`
- `kis_hl/risk.py`: `fb506289900442e3615cbc4f24ab451f40783ba5f275e6eae6b7c2fdea42503f`
- `kis_hl/strategy_signals.py`: `9942451d23a5c17ef53ac19d3b9a8cc0a90e5ee13b106ad833dbaf9f739563bb`
- `kis_hl/operations_cli.py`: `cbfb804710c1f363fa16ccd7ea419f38b06ee79574bcccc64316810676cbf1e5`
- `tests/test_strategy_tools.py`: `03f43107fae9e6d64586a0391158d06bd4bbae8ca812997edbae2def20569afd`
- `tests/test_risk.py`: `040cebc2e5de19c1e186fb5b5cdfbd6ae2cff682e6530805078e94f6615a7bc1`
- `tests/test_strategy_signals.py`: `53450bf2ea3209109f5a34980e79c83d36b5b270a88a3ea46193e30967f2d3ff`
- `.agents/skills/trend-strategy/SKILL.md`: `8bf6fed5824c60df852e982063fc2730c4128679028812bef9bc5e1b972f7b5e`
- `.agents/skills/trend-strategy/references/strategy.md`: `45bdd877156fc5c5c081c63ff59b6c9709b6cd6e0aee033e1808196abd94e43b`
- `docs/strategy-authoring.md`: `572c405baa34d7ca2a813c6b8e2ad618ea5e453b18f72c7254dc2401ab01da87`
- `docs/strategy-tools.md`: `6e9667d65af136c9dc5912fa981a55ac4a5271df814bde68f512a5b2222ace2f`
- `docs/strategy_execution_design.md`: `5f00acda43725005c1ba90c2fba086e03e1e29b21238fb6db046fa2aca1b8b96`
- `docs/trading-operations.md`: `7513fc48c2b795083d813904c5956266223cfc4384f2d3a92a54dac27d8153f3`
- `README.md`: `a49aeeccc927521be4fbd0bb167317160e9d5295a5c4b597c57b3dee1ea87de8`
- `AGENTS.md`: `7116a20ad81eb38bbe3686df803c2a033ab57f38786e03a00446a6019892dbbd`
- `CLAUDE.md`: `3e9508fef23fabf14f997868ee1b5ffc5ff1cc2eefdc9408c947d697c3f44f16`

## LOW finding resolution

Confirmed the wording now limits the `order_authorized: false` assertion to setup, stop and sizing outputs. The documented schema matches the reviewed tools. Finding resolved; no outstanding findings. No production-code changes or broad retest were needed for this documentation-only correction.

Current `docs/strategy_execution_design.md` SHA-256: `bd60450720f76c2b56206e96b6f37d63909982bef9e0bd2db7c085b1a806f74d`.
