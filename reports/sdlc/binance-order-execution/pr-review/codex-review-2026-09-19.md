조건부 주문 API 경로와 주문 결과 판정에 문제가 있으며, 정상적인 청산·보호 주문을 로컬 검증이 차단할 수 있습니다. 오류 처리와 검증 문제는 mock으로 재현했으며, 전체 테스트 완료와 공식 문서 재조회는 읽기 전용 파일시스템 및 네트워크 제한으로 불가능했습니다.

Full review comments:

- [P1] 조건부 주문을 Algo Order API로 전송하세요 — /root/.paseo/worktrees/1epgz72k/sulky-dragonfly/kis_hl/binance/trading.py:169-169
  `STOP_MARKET`과 `TRAILING_STOP_MARKET`을 일반 `/fapi/v1/order`로 전송하지만, Binance USDⓈ-M의 조건부 주문은 Algo Order API로 이전되어 이 경로에서는 `-4120`으로 거절됩니다. 따라서 새 `binance-stop --live` 명령은 실제 보호 주문을 설치하지 못합니다. 두 메서드를 `/fapi/v1/algoOrder`와 해당 파라미터 스키마로 전환하고, 반환되는 algo ID의 저장·조회·취소도 함께 처리해야 합니다. 현재 테스트는 일반 주문 경로의 성공 응답만 모킹하므로 이 문제를 검출하지 못합니다.

- [P1] 실행 여부가 불명확한 응답을 확정 거절과 구분하세요 — /root/.paseo/worktrees/1epgz72k/sulky-dragonfly/kis_hl/binance/trading.py:281-283
  거래소가 HTTP 503 `Unknown error`를 반환하면 주문이 이미 실행되었을 수 있는데, 모든 `RuntimeError`를 `rejected`로 반환하고 저장합니다. 모킹으로 확인한 결과 주문 상태 조회 없이 즉시 거절로 종료합니다. 사용자가 이를 믿고 재시도하면 새 client order ID로 중복 진입할 수 있습니다. 불명확한 결과를 별도 상태로 보존하고 기존 client order ID로 조회하거나 사용자 스트림으로 확인해야 합니다. 이는 [Binance 스킬의 503 처리 규칙](.agents/skills/binance-api/SKILL.md#L130-L132)에도 명시되어 있습니다.

- [P1] Reduce-only 청산에는 최소 주문금액 검사를 제외하세요 — /root/.paseo/worktrees/1epgz72k/sulky-dragonfly/kis_hl/binance/trading.py:119-122
  `reduce_only=True`여도 MARKET과 LIMIT 모두 `_require_notional`을 먼저 적용합니다. Binance는 reduce-only 주문을 최소 주문금액 제한에서 제외하므로, 이 검사는 정상적인 소액 잔여 포지션 청산을 막습니다. 예를 들어 BTCUSDT 가격이 49,000이고 남은 수량이 0.001이면 49 USDT라는 이유로 거래소에 보내기도 전에 거절됩니다. 일반 진입 주문에는 검사를 유지하되 reduce-only 청산에는 적용하지 않아야 합니다.

- [P2] 선택한 workingType의 가격으로 스톱 방향을 검증하세요 — /root/.paseo/worktrees/1epgz72k/sulky-dragonfly/kis_hl/binance/trading.py:151-153
  `working_type="CONTRACT_PRICE"`를 선택해도 스톱 방향은 항상 mark price와 비교합니다. 예를 들어 mark가 76,000이고 최근 체결가가 76,010일 때 SELL 스톱 76,005는 유효하지만 로컬 검사에서 거절됩니다. 반대로 mark 기준으로만 유효한 주문은 통과한 뒤 거래소에서 즉시 트리거 오류로 거절될 수 있습니다. `CONTRACT_PRICE`일 때는 최근 체결가를 조회하여 비교하고, `MARK_PRICE`일 때만 현재 검사를 사용해야 합니다.
