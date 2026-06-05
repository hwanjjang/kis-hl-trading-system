from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path
from typing import Any

from kis_hl.config import KisConfig
from kis_hl.kis.client import KisClient, KisHttpResponse, TokenCache


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

    def test_domestic_index_price_uses_kis_index_endpoint(self) -> None:
        client = RecordingKisClient()
        client.inquire_domestic_index_price(index_code="2001", market_code="U")

        self.assertEqual(client.calls[0]["path"], "/uapi/domestic-stock/v1/quotations/inquire-index-price")
        self.assertEqual(client.calls[0]["tr_id"], "FHPUP02100000")
        self.assertEqual(
            client.calls[0]["query"],
            {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": "2001"},
        )

    def test_overseas_time_indexchartprice_uses_kis_index_endpoint(self) -> None:
        client = RecordingKisClient()
        client.inquire_overseas_time_indexchartprice(symbol="SPX", market_code="N")

        self.assertEqual(
            client.calls[0]["path"],
            "/uapi/overseas-price/v1/quotations/inquire-time-indexchartprice",
        )
        self.assertEqual(client.calls[0]["tr_id"], "FHKST03030200")
        self.assertEqual(
            client.calls[0]["query"],
            {
                "FID_COND_MRKT_DIV_CODE": "N",
                "FID_INPUT_ISCD": "SPX",
                "FID_HOUR_CLS_CODE": "0",
                "FID_PW_DATA_INCU_YN": "Y",
            },
        )

    def test_websocket_approval_key_uses_approval_endpoint(self) -> None:
        client = RecordingKisClient()

        approval_key = client.get_websocket_approval_key()

        self.assertEqual(approval_key, "approval")
        self.assertEqual(client.json_calls[0]["path"], "/oauth2/Approval")
        self.assertEqual(
            client.json_calls[0]["body"],
            {
                "grant_type": "client_credentials",
                "appkey": "key",
                "secretkey": "secret",
            },
        )


class RecordingKisClient(KisClient):
    def __init__(self) -> None:
        super().__init__(
            KisConfig(
                mode="sim",
                base_url="https://example.test",
                app_key="key",
                app_secret="secret",
                account_id="1234567801",
                account8="12345678",
                product_code2="01",
                hts_id="",
                token_dir=Path("/tmp"),
                http_timeout_seconds=1,
                min_request_interval_ms=0,
                rate_limit_retries=0,
                rate_limit_delay_ms=0,
            )
        )
        self.calls: list[dict[str, Any]] = []
        self.json_calls: list[dict[str, Any]] = []

    def _request_with_auth(
        self,
        method: str,
        path: str,
        *,
        tr_id: str,
        query: dict[str, str | int | float | None] | None = None,
        body: dict[str, Any] | None = None,
    ) -> KisHttpResponse:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "tr_id": tr_id,
                "query": query,
                "body": body,
            }
        )
        return KisHttpResponse(200, {"rt_cd": "0"}, {})

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        query: dict[str, str | int | float | None] | None = None,
        body: dict[str, Any] | None = None,
    ) -> KisHttpResponse:
        self.json_calls.append(
            {
                "method": method,
                "path": path,
                "headers": headers,
                "query": query,
                "body": body,
            }
        )
        return KisHttpResponse(200, {"approval_key": "approval"}, {})


if __name__ == "__main__":
    unittest.main()
