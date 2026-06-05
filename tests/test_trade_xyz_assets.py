from __future__ import annotations

from datetime import date
import unittest

from kis_hl.trade_xyz_assets import (
    TradeXyzAsset,
    get_trade_xyz_asset,
    has_minimum_listing_age,
    is_trade_xyz_symbol_tradable,
)


class TradeXyzAssetTests(unittest.TestCase):
    def test_aliases_resolve_to_canonical_assets(self) -> None:
        self.assertEqual(get_trade_xyz_asset("SMSN").trade_symbol, "SAMSUNG")
        self.assertEqual(get_trade_xyz_asset("SKHX").trade_symbol, "SKHYNIX")
        self.assertEqual(get_trade_xyz_asset("CL").trade_symbol, "WTIOIL")
        self.assertEqual(get_trade_xyz_asset("SAMSUNG").hyperliquid_coin, "xyz:SMSN")
        self.assertEqual(get_trade_xyz_asset("SKHYNIX").hyperliquid_coin, "xyz:SKHX")
        self.assertEqual(get_trade_xyz_asset("WTIOIL").hyperliquid_coin, "xyz:CL")

    def test_duplicate_etf_exposures_are_not_tradable(self) -> None:
        self.assertTrue(is_trade_xyz_symbol_tradable("KR200"))
        self.assertFalse(is_trade_xyz_symbol_tradable("EWY"))
        self.assertTrue(is_trade_xyz_symbol_tradable("JP225"))
        self.assertFalse(is_trade_xyz_symbol_tradable("EWJ"))

    def test_unknown_and_pre_ipo_assets_are_not_tradable_by_default(self) -> None:
        self.assertFalse(is_trade_xyz_symbol_tradable("OPENAI"))
        self.assertFalse(is_trade_xyz_symbol_tradable("SPACE_X"))

    def test_non_stock_reference_assets_do_not_need_listing_dates(self) -> None:
        self.assertTrue(is_trade_xyz_symbol_tradable("GOLD"))
        self.assertTrue(is_trade_xyz_symbol_tradable("JPY"))
        self.assertEqual(get_trade_xyz_asset("XYZ100").underlying_symbol, "NDX")

    def test_stock_requires_thirty_weeks_since_listing(self) -> None:
        recent = TradeXyzAsset(
            "RECENT",
            "xyz:RECENT",
            "stock",
            "Recent Listing Inc.",
            "RECENT",
            "NASDAQ",
            "listed",
            True,
            "2026-01-01",
        )
        self.assertFalse(has_minimum_listing_age(recent, as_of=date(2026, 5, 26)))
        self.assertTrue(has_minimum_listing_age(recent, as_of=date(2026, 8, 1)))

    def test_seed_recent_listings_are_old_enough_as_of_project_date(self) -> None:
        self.assertTrue(is_trade_xyz_symbol_tradable("CRCL", as_of=date(2026, 5, 26)))
        self.assertTrue(is_trade_xyz_symbol_tradable("CRWV", as_of=date(2026, 5, 26)))


if __name__ == "__main__":
    unittest.main()
