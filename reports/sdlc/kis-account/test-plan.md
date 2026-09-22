AC1: offline live/paper endpoint request tests. AC2: CLI JSON whitelist and masked-account assertions. AC3: HTTP/business/malformed response and network failures, credential cache separation.
Red: python3 -m unittest tests.test_kis_account -q; missing endpoint/command is intended failure.
Green/post-refactor: account, KIS client, config and CLI suites without network.
Additional real smoke: python3 -m kis_hl.cli kis-account using authorized .env; assert expected schema and mask, retain only pass/fail evidence. No orders or account state mutation; token caching only. No test cleanup needed beyond temporary test fixtures.
