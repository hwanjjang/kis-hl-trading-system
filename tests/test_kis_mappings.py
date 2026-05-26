from __future__ import annotations

from datetime import date
import unittest

from kis_hl.kis_mappings import build_trade_xyz_kis_mappings, get_trade_xyz_kis_mapping


class KisMappingsTests(unittest.TestCase):
    def test_builds_domestic_korean_stock_mappings(self) -> None:
        mappings = {item.trade_symbol: item for item in build_trade_xyz_kis_mappings()}

        self.assertEqual(mappings["SAMSUNG"].kis_market, "domestic")
        self.assertEqual(mappings["SAMSUNG"].kis_symbol, "005930")
        self.assertEqual(mappings["SAMSUNG"].kis_market_code, "J")
        self.assertEqual(mappings["SKHYNIX"].kis_symbol, "000660")

    def test_builds_overseas_stock_and_etf_price_mappings(self) -> None:
        mappings = {item.trade_symbol: item for item in build_trade_xyz_kis_mappings()}

        self.assertEqual(mappings["AAPL"].kis_market, "overseas")
        self.assertEqual(mappings["AAPL"].kis_exchange_code, "NAS")
        self.assertEqual(mappings["ORCL"].kis_exchange_code, "NYS")
        self.assertEqual(mappings["URNM"].kis_exchange_code, "AMS")

    def test_marks_indexes_without_implemented_kis_endpoint_as_unsupported(self) -> None:
        mappings = {item.trade_symbol: item for item in build_trade_xyz_kis_mappings()}

        self.assertEqual(mappings["KR200"].status, "unsupported")
        self.assertEqual(mappings["KR200"].kis_market, "unsupported")
        self.assertIn("not implemented", mappings["KR200"].reason)

    def test_keeps_duplicate_exposure_etfs_excluded(self) -> None:
        mappings = {item.trade_symbol: item for item in build_trade_xyz_kis_mappings()}

        self.assertEqual(mappings["EWY"].status, "excluded")
        self.assertEqual(mappings["EWY"].kis_market, "overseas")
        self.assertEqual(mappings["EWY"].kis_exchange_code, "AMS")
        self.assertIn("KR200", mappings["EWY"].reason)

    def test_recent_listing_is_excluded_even_when_quote_route_exists(self) -> None:
        mapping = get_trade_xyz_kis_mapping("CRCL", as_of=date(2025, 7, 1))

        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.status, "excluded")
        self.assertEqual(mapping.kis_market, "overseas")
        self.assertIn("less than 30 weeks", mapping.reason)


if __name__ == "__main__":
    unittest.main()
