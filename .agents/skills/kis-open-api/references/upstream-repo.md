# Upstream: `koreainvestment/open-trading-api`

Official sample repository (MIT-style disclaimer, updated without notice). ~1.6k stars.
`llms.txt` at the root is the intended LLM entry point.

## Layout

```
examples_llm/            # atomic, one folder per API (LLM-oriented)
  kis_auth.py            # auth + _url_fetch + KISWebSocket helpers (requests/pandas/yaml/pycryptodome)
  auth/{auth_token,auth_ws_token}
  domestic_stock/<endpoint>/{<endpoint>.py, chk_<endpoint>.py}   # 156 endpoints
  overseas_stock/...        # 50
  domestic_futureoption/... # 43
  overseas_futureoption/... # 35
  elw/...                   # 24
  domestic_bond/...         # 18
  etfetn/...                # 6
examples_user/           # same APIs merged per category: <cat>_functions.py, <cat>_examples.py, *_ws.py
stocks_info/             # .mst master-file parsers (KOSPI/KOSDAQ/KONEX, overseas stock/index/futures, sectors, themes)
MCP/                     # KIS Code Assistant MCP (API search) and KIS Trading MCP (API execution)
strategy_builder/        # visual strategy designer -> .kis.yaml + signals
backtester/              # QuantConnect Lean (Docker) backtests of .kis.yaml
legacy/                  # old REST/websocket samples and Postman collection
docs/convention.md       # naming: folder = URL segment (snake_case), file <endpoint>.py, test chk_<endpoint>.py
kis_devlp.yaml           # config template (~/KIS/config/kis_devlp.yaml): my_app/my_sec, paper_app/paper_sec, my_htsid, accounts, prod/vps/ops/vops URLs
```

Each `examples_llm` sample has: a header comment with the portal title and ID
(e.g. `[v1_해외주식-009]`), `API_URL`, typed function args mirroring the request
fields, `tr_id` selection (including paper variants), the `params` dict with the
exact upper-case names, `tr_cont` pagination, and the response `columns`.

## Searching locally

```bash
# clone once (shallow), then grep
.agents/skills/kis-open-api/scripts/find_kis_endpoint.sh 분봉          # by Korean title
.agents/skills/kis-open-api/scripts/find_kis_endpoint.sh HHDFS76240000  # by TR ID
.agents/skills/kis-open-api/scripts/find_kis_endpoint.sh dailyprice     # by path/folder
```

Set `KIS_UPSTREAM_DIR` to reuse an existing checkout.

## Portal

- https://apiportal.koreainvestment.com — API 문서 (per-endpoint request/response
  specs), 에러코드, FAQ, 종목정보 다운로드, testbed. It is a JS single-page app; plain
  HTTP fetches return little, so prefer the GitHub samples for machine reading and
  the portal for field-level semantics.
- Service application: https://apiportal.koreainvestment.com/about-howto
  (account → Open API 신청 → App Key/Secret; paper and live keys are separate).

## Official AI tooling (alternatives, not used by this repo)

- **KIS Code Assistant MCP** (`npx -y @koreainvestment/kis-code-assistant-mcp`): natural-
  language search over the 334 endpoint samples; returns sample code. Read-only.
- **KIS Trading MCP** (`MCP/Kis Trading MCP`, `uv run python server.py` with
  `KIS_APP_KEY/KIS_APP_SECRET`, `ENV=live|paper`, `MCP_TYPE=stdio`): executes KIS APIs as
  MCP tools. It can place orders; do not connect it to a live key from an agent session
  without the same guardrails this repo applies to Hyperliquid.
- **kis-ai-extensions** (`npx @koreainvestment/kis-quant-plugin init --agent claude|codex|cursor|gemini|all`):
  installs `kis-strategy-builder`, `kis-backtester`, `kis-order-executor`, `kis-team`,
  `kis-cs` skills plus `/auth`, `/my-status`, `/kis-setup`, `/kis-help` commands into
  `.claude/` (or the agent's dir). It targets the strategy_builder/backtester pipeline,
  requires `kis_devlp.yaml`, Node 18+, Docker, and is separate from this repo's
  `.env`-based `KisClient`. Evaluate before installing; it adds hooks and scripts.

## Behavioral rules from upstream `llms.txt`

- Prefer `examples_llm/` for endpoint-level implementation.
- Use `examples_user/` for end-to-end workflows.
- Reuse existing auth helpers (in this repo: `KisClient`).
- Follow the request structures and parameter conventions shown in the samples.
