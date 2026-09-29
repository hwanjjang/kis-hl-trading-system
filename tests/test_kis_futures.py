from __future__ import annotations

import unittest
from datetime import date

from kis_hl.kis.futures import kospi200_front_future_code, second_thursday
from tests.test_kis_client import RecordingKisClient


class Kospi200FuturesTests(unittest.TestCase):
    def test_front_contract_uses_verified_kis_short_code_format(self) -> None:
        self.assertEqual(kospi200_front_future_code(date(2026, 9, 29)), "A01612")

    def test_contract_rolls_after_second_thursday_expiry(self) -> None:
        self.assertEqual(second_thursday(2026, 12), date(2026, 12, 10))
        self.assertEqual(kospi200_front_future_code(date(2026, 12, 10)), "A01612")
        self.assertEqual(kospi200_front_future_code(date(2026, 12, 11)), "A01703")

    def test_futures_quote_uses_read_only_price_route(self) -> None:
        client = RecordingKisClient()
        client.inquire_domestic_futures_price(symbol="A01612")
        call = client.calls[-1]
        self.assertEqual(call["method"], "GET")
        self.assertEqual(call["path"], "/uapi/domestic-futureoption/v1/quotations/inquire-price")
        self.assertEqual(call["tr_id"], "FHMIF10000000")
        self.assertEqual(call["query"], {"FID_COND_MRKT_DIV_CODE": "F", "FID_INPUT_ISCD": "A01612"})


if __name__ == "__main__":
    unittest.main()
