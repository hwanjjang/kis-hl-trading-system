from __future__ import annotations

import unittest

from kis_hl.assets import resolve_hyperliquid_symbol


class AssetResolutionTests(unittest.TestCase):
    def test_btcusdc_resolves_to_hyperliquid_spot_l1_name(self) -> None:
        resolved = resolve_hyperliquid_symbol("BTCUSDC")
        self.assertEqual(resolved.coin, "UBTC/USDC")
        self.assertEqual(resolved.kind, "spot")

    def test_xyz_asset_resolves_to_hip3_namespace(self) -> None:
        resolved = resolve_hyperliquid_symbol("XYZ100", dex="xyz")
        self.assertEqual(resolved.coin, "xyz:XYZ100")
        self.assertEqual(resolved.kind, "perp")
        self.assertEqual(resolved.dex, "xyz")

    def test_explicit_dex_symbol_wins(self) -> None:
        resolved = resolve_hyperliquid_symbol("xyz:samsung")
        self.assertEqual(resolved.coin, "xyz:SMSN")

    def test_trade_xyz_alias_resolves_to_actual_hyperliquid_coin(self) -> None:
        self.assertEqual(resolve_hyperliquid_symbol("xyz:SKHYNIX").coin, "xyz:SKHX")
        self.assertEqual(resolve_hyperliquid_symbol("xyz:SKHX").coin, "xyz:SKHX")


if __name__ == "__main__":
    unittest.main()
