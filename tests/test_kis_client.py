from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path

from kis_hl.config import KisConfig
from kis_hl.kis.client import KisClient, TokenCache


class KisClientTests(unittest.TestCase):
    def test_token_cache_is_written_private(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = KisConfig(
                mode="sim",
                base_url="https://example.test",
                app_key="key",
                app_secret="secret",
                account_id="1234567801",
                account8="12345678",
                product_code2="01",
                hts_id="",
                token_dir=Path(tmp),
                http_timeout_seconds=1,
                min_request_interval_ms=0,
                rate_limit_retries=0,
                rate_limit_delay_ms=0,
            )
            client = KisClient(config)
            client._write_token_cache(  # noqa: SLF001
                TokenCache(access_token="token", expires_at_ms=9999999999999, last_issued_at_ms=1)
            )
            mode = stat.S_IMODE((Path(tmp) / "kis-token-sim.json").stat().st_mode)
            self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
