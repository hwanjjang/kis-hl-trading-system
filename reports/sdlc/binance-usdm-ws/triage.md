# Triage — binance-usdm-ws

| Field | Recorded value |
| --- | --- |
| Task / stage / owner | binance-usdm-ws / triage / main agent (Claude Fable 5.1) |
| Date / revision | 2026-09-16 r1 |
| Source / authority | AK chat request 2026-09-16: "API를 사용하고, websocket를 사용해서 order 및 시세 현황을 가지고 올 수 있게 하자"; market = USDⓈ-M futures (AskUserQuestion answer). Endpoint local (no commit/push requested). |
| Consumed inputs | issue #16 + comments; .planning/2026-09-16-binance-usdm-ws-data-plane/findings.md |
| Acceptance criteria | AC1–AC7 (see intent.md) |
| Candidate / base | worktree sulky-dragonfly @ 9360b0c, clean before task |
| Status / decision | PROCEED |
| Reason / evidence / next action | Request is explicit; repo patterns identified; next: intent |

- Requested: Binance API (not MCP) integration with WebSocket for order status and market prices. Inferred and stated: order placement is the next iteration, not this one.
- Repository: hwanjjang/kis-hl-trading-system, branch sulky-dragonfly (worktree), base main. No existing Binance code.
- Mode implementation, change kind behavior, endpoint local. Excluded: signed order placement/cancel, spot market, MCP config, commits.
- Facts: see findings.md (live public probes, docs). Unknown: user-data-stream cannot be smoke-tested without exposing account activity; verified by unit tests with recorded payload shapes only.
- Stricter local rules: AGENTS.md/CLAUDE.md trading safety; never print secrets.
- Stages: triage, intent, investigation, spec, design (archify sequence diagram of the two WS flows if feasible; otherwise reasoned skip), plan, test-design, build, self-verification, independent-verification (qa subagent), completion. pr-review/correction/merge not applicable at local endpoint.
- Artifact mapping: all canonical docs under reports/sdlc/binance-usdm-ws/ (intent.md, spec.md, plan.md) because the repo has no intent/specs/plans dirs. Planning notebook: .planning/2026-09-16-binance-usdm-ws-data-plane (PLAN_ID), owner main agent.
