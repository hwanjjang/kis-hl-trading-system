보호 주문 취소 후 로컬 활성 상태가 실제 거래소 상태와 불일치합니다. 관련 테스트를 실행했으나 읽기 전용 환경의 임시 파일 생성 제한으로 전체 통과 여부는 확인하지 못했습니다.

Review comment:

- [P2] 취소 성공 시 보호 주문의 활성 상태를 갱신하세요 — /root/.paseo/worktrees/1epgz72k/sulky-dragonfly/kis_hl/cli.py:925-927
  `binance-stop --live`로 저장한 주문을 `binance-cancel --algo-id ... --live`로 취소해도 취소 제출 기록만 추가되고 기존 `protective_orders` 행은 계속 `active=1`, `status=submitted`로 남습니다. 따라서 `list_protective_orders(active_only=True)`는 이미 취소된 주문을 유효한 보호 주문으로 반환합니다. 현재 사용자 스트림도 `ALGO_UPDATE`를 저장하지 않아 이 상태를 나중에 보정하지 않습니다. 취소가 확정된 경우 해당 algo ID 또는 client algo ID의 보호 주문을 비활성화하고, 실패·unknown·dry-run에서는 기존 상태를 유지해야 합니다.
