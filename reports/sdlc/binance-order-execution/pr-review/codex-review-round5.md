불확실한 주문 결과를 재조회하는 경로에서 종료된 보호 주문이 활성으로 기록되는 문제를 재현했습니다. 파일 쓰기가 필요한 테스트는 읽기 전용 환경으로 제한되었으며, 계정 잠금을 모킹한 관련 테스트 42개는 통과했습니다.

Review comment:

- [P2] 재조회된 조건부 주문의 상태를 확인한 뒤 활성화하세요 — /root/.paseo/worktrees/1epgz72k/sulky-dragonfly/kis_hl/cli.py:888-889
  조건부 주문 전송이 타임아웃된 뒤 재조회에서 `algoStatus=REJECTED`, `CANCELED` 또는 `EXPIRED`가 반환되어도 `_resolve_unknown()`은 ID가 있다는 이유만으로 `submitted`를 반환합니다. 따라서 이 조건은 이미 비활성인 보호 주문을 `active=1`로 저장하여 `list_protective_orders(active_only=True)`에도 포함시킵니다. 재조회 응답의 실제 주문 상태를 확인하고, 종료되거나 거절된 주문은 비활성으로 저장해야 합니다.
