from __future__ import annotations

import unittest

from kis_hl.trade_xyz_assets import get_trade_xyz_asset, is_trade_xyz_symbol_tradable


class TradeXyzAssetTests(unittest.TestCase):
    def test_aliases_resolve_to_canonical_assets(self) -> None:
        self.assertEqual(get_trade_xyz_asset("SMSN").trade_symbol, "SAMSUNG")
        self.assertEqual(get_trade_xyz_asset("SKHX").trade_symbol, "SKHYNIX")

    def test_duplicate_etf_exposures_are_not_tradable(self) -> None:
        self.assertTrue(is_trade_xyz_symbol_tradable("KR200"))
        self.assertFalse(is_trade_xyz_symbol_tradable("EWY"))
        self.assertTrue(is_trade_xyz_symbol_tradable("JP225"))
        self.assertFalse(is_trade_xyz_symbol_tradable("EWJ"))

    def test_unknown_and_pre_ipo_assets_are_not_tradable_by_default(self) -> None:
        self.assertFalse(is_trade_xyz_symbol_tradable("OPENAI"))
        self.assertFalse(is_trade_xyz_symbol_tradable("SPACE_X"))


if __name__ == "__main__":
    unittest.main()
