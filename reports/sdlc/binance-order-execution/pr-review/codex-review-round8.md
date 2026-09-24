취소 대상과 로컬 상태 갱신의 불일치, 종료된 보호 주문의 활성 기록, 예제 데모 설정의 서버 선택 오류를 격리된 재현으로 확인했습니다. 관련 테스트 121개 중 39개는 읽기 전용 환경의 임시 파일 생성 제한으로 완료하지 못했습니다.

Full review comments:

- [P2] 실제 취소된 주문의 식별자로만 로컬 상태를 갱신하세요 — /root/.paseo/worktrees/1epgz72k/sulky-dragonfly/kis_hl/cli.py:926-930
  `--algo-id 1 --client-algo-id stop-b`처럼 서로 다른 주문의 식별자를 함께 전달하면, 거래소 요청은 `clientAlgoId`만 사용하여 stop-b를 취소하지만 로컬 갱신은 두 식별자를 OR 조건으로 검색해 두 주문 모두 비활성화합니다. 거래소에 남아 있는 보호 주문까지 취소된 것으로 기록됩니다. 식별자를 상호 배타적으로 받거나, 확인된 취소 응답의 식별자만 사용하세요.

- [P2] 종료된 보호 주문을 활성 상태로 저장하지 마세요 — /root/.paseo/worktrees/1epgz72k/sulky-dragonfly/kis_hl/cli.py:895-896
  주문 전송이 503으로 끝난 뒤 재조회에서 `algoStatus=FINISHED`가 반환되면 `_resolve_unknown()`은 이를 `submitted`로 분류하고, 이 조건은 이미 종료된 보호 주문을 `active=True`로 저장합니다. 완료된 주문이 여전히 포지션을 보호하는 것처럼 로컬 상태에 남습니다. 제출 성공 여부와 별개로 거래소의 주문 상태를 확인하여 활성 여부를 결정하세요.

- [P2] 예제 환경에서도 demo 프로필이 데모 서버를 선택하도록 안내하세요 — /root/.paseo/worktrees/1epgz72k/sulky-dragonfly/.env.example:50-53
  이 예제를 복사하고 안내대로 `BINANCE_KEY_PROFILE=demo`와 데모 키를 설정해도, 위에 이미 지정된 `BINANCE_TESTNET=false` 때문에 실제 REST 주소는 `https://fapi.binance.com`이 됩니다. 따라서 문서화된 데모 설정으로는 인증이 실패합니다. 예제의 명시적 false 설정을 제거하거나, demo 프로필 선택 시 `BINANCE_TESTNET=true`도 설정해야 한다고 안내하세요.
