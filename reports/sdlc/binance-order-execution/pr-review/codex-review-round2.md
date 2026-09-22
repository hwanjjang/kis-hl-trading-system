주문 타임아웃 오분류, 알고 주문 취소 대상 검증 누락, 전체 조회에서의 보호 주문 누락이 있습니다. 잠금 파일 생성을 대체한 관련 테스트 61개 중 60개는 통과했으며, 1개는 읽기 전용 환경의 임시 디렉터리 생성 제한으로 실행되지 못했습니다.

Full review comments:

- [P1] 실행 결과가 불명확한 타임아웃을 rejected로 분류하지 마세요 — /root/.paseo/worktrees/1epgz72k/sulky-dragonfly/kis_hl/binance/trading.py:306-310
  Binance가 HTTP 408과 코드 `-1007`(`execution status unknown`)을 반환하면 현재 정규식에 일치하지 않아 조회 없이 `rejected`로 반환됩니다. 실제로 체결되었을 수 있는 주문을 실패로 판단하여 재주문하면 포지션이 중복될 수 있습니다. HTTP 상태뿐 아니라 Binance 오류 코드도 확인하여 이 경우에는 `unknown` 처리와 클라이언트 ID 기반 조회를 수행해야 합니다. 스텁 응답으로 해당 오분류를 재현했습니다.

- [P1] 알고 주문 취소 전에 실제 주문의 심볼을 검증하세요 — /root/.paseo/worktrees/1epgz72k/sulky-dragonfly/kis_hl/binance/trading.py:250-254
  `algoId`가 ETHUSDT 주문을 가리키더라도 호출자가 `symbol="BTCUSDT"`를 넘기면 BTCUSDT 허용 목록 검사를 통과하여 ETHUSDT 보호 주문을 취소할 수 있습니다. 취소 요청에는 심볼이 포함되지 않으므로 거래소도 이 불일치를 차단하지 않으며, CLI의 기본 심볼 때문에 실수로도 발생합니다. 실거래 취소 전에 ID로 주문을 조회하여 실제 심볼과 요청 심볼의 일치 및 허용 여부를 검증해야 합니다. 이는 [Binance 스킬의 허용 목록 가드 규칙](.agents/skills/binance-api/SKILL.md#L22-L25)을 실제 취소 대상에도 적용하는 데 필요합니다.

- [P2] 심볼 없는 주문 조회에서도 알고 주문을 반환하세요 — /root/.paseo/worktrees/1epgz72k/sulky-dragonfly/kis_hl/cli.py:722-722
  `binance-orders`를 `--symbol` 없이 실행하면 일반 주문과 포지션은 계정 전체를 조회하지만 알고 주문은 조회하지 않고 항상 빈 목록을 반환합니다. 따라서 실제 STOP_MARKET 또는 trailing 주문이 있어도 없는 것처럼 표시되며, 불명확한 주문 결과를 확인하는 용도로도 신뢰할 수 없습니다. `open_algo_orders`가 선택적 심볼을 받아 계정 전체 조회를 수행하도록 하고 이 분기에서도 호출해야 합니다.
