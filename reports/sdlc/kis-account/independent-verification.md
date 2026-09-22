Verifier /root/verify_kis_account independently read intent/spec/plan and candidate code.
python3 -m unittest tests.test_kis_account tests.test_kis_client tests.test_config -q: 13 tests passed. Additional malformed amount probes rejected nonfinite, blank, nonnumeric, None, integer and boolean values.
Initial finding: secret-only rotation reused token directory. Fixed with digest of JSON [app_key, app_secret] and regression. Endpoint test moved to prescribed client test file. Rechecked by verifier: PASS AC1-AC3, no blocking findings.
Limit: independent verification offline; real KIS smoke executed by builder only.
