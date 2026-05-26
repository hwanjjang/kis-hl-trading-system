from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kis_hl.kis.client import KisHttpResponse
from kis_hl.kis_collector import collect_trade_xyz_kis_quotes, fetch_mapped_kis_response
from kis_hl.storage import seed_trade_xyz_kis_mappings


class KisCollectorTests(unittest.TestCase):
    def test_fetch_mapped_kis_response_routes_overseas_index_time(self) -> None:
        calls = []

        class FakeClient:
            def inquire_overseas_time_indexchartprice(
                self,
                *,
                symbol: str,
                market_code: str,
                hour_cls_code: str,
                include_past_data: bool,
            ) -> KisHttpResponse:
                calls.append((symbol, market_code, hour_cls_code, include_past_data))
                return KisHttpResponse(200, {"rt_cd": "0", "output2": [{"last": "6123.4"}]}, {})

        mapping = {
            "trade_symbol": "SP500",
            "status": "active",
            "kis_market": "overseas_index_time",
            "kis_symbol": "SPX",
            "kis_market_code": "N",
            "kis_exchange_code": None,
            "reason": None,
        }

        mapped = fetch_mapped_kis_response(FakeClient(), mapping)

        self.assertEqual(mapped.storage_market, "trade_xyz_overseas_index_time")
        self.assertEqual(mapped.exchange_code, "N")
        self.assertEqual(calls, [("SPX", "N", "0", True)])

    def test_collect_trade_xyz_kis_quotes_continues_after_failures(self) -> None:
        class FakeClient:
            def inquire_domestic_price(self, *, symbol: str, market_code: str) -> KisHttpResponse:
                return KisHttpResponse(200, {"rt_cd": "0", "output": {"stck_prpr": "75000"}}, {})

            def inquire_overseas_price(self, *, exchange_code: str, symbol: str) -> KisHttpResponse:
                return KisHttpResponse(200, {"rt_cd": "1", "msg_cd": "EGW", "msg1": "bad"}, {})

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            seed_trade_xyz_kis_mappings(db, updated_at_ms=1)

            summary = collect_trade_xyz_kis_quotes(
                db,
                client=FakeClient(),
                symbols=["SAMSUNG", "AAPL", "XYZ100"],
                store=True,
            )

            self.assertEqual(summary["succeeded"], 1)
            self.assertEqual(summary["failed"], 1)
            self.assertEqual(summary["skipped"], 1)
            self.assertEqual(summary["stored"], 1)


if __name__ == "__main__":
    unittest.main()
