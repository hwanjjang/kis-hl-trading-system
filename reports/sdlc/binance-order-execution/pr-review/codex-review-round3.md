잘못된 API 경로로 실제 주문 조회가 실패하며, 계정 전체 조건부 주문 조회에도 누락이 발생합니다. 쓰기가 필요 없는 관련 테스트 14개는 통과했지만, 임시 파일을 사용하는 테스트는 읽기 전용 환경에서 실행이 제한되었습니다.

Full review comments:

- [P1] 미체결 Algo 주문 조회 경로를 수정하세요 — /root/.paseo/worktrees/1epgz72k/sulky-dragonfly/kis_hl/binance/client.py:202-202
  Binance의 미체결 조건부 주문 조회 경로는 `/fapi/v1/openAlgoOrders`인데, 현재 `/fapi/v1/algoOpenOrders`를 호출합니다. 따라서 실제 환경에서 `binance-orders`가 이 호출에서 실패하여 기존 일반 주문과 포지션 결과까지 출력하지 못합니다. 경로를 수정하고 정확한 요청 URL을 검증하는 테스트를 추가하세요. 저장소의 [신규 REST 경로 확인 규칙](.agents/skills/binance-api/SKILL.md#L168-L173)도 적용됩니다.

- [P2] 계정 전체 조회에서 조건부 주문만 있는 심볼도 포함하세요 — /root/.paseo/worktrees/1epgz72k/sulky-dragonfly/kis_hl/cli.py:733-738
  `--symbol` 없이 조회할 때 일반 주문·포지션·현재 allowlist에 없는 심볼은 조회 대상에서 빠집니다. 예를 들어 ETHUSDT 조건부 주문을 남긴 채 포지션을 종료하고 allowlist에서 ETHUSDT를 제거하면, 살아 있는 주문이 결과에서 조용히 누락됩니다. 올바른 `/fapi/v1/openAlgoOrders`는 symbol을 생략한 계정 전체 조회를 지원하므로, 추정한 심볼 목록 대신 해당 조회를 사용하세요.
