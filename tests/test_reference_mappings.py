from __future__ import annotations

import unittest

from kis_hl.reference_mappings import (
    build_trade_xyz_reference_mappings,
    get_trade_xyz_reference_mapping,
)


class ReferenceMappingsTests(unittest.TestCase):
    def test_builds_yahoo_reference_mappings_for_commodity_fx_and_indexes(self) -> None:
        mappings = {item.trade_symbol: item for item in build_trade_xyz_reference_mappings()}

        self.assertEqual(mappings["WTIOIL"].provider_symbol, "CL=F")
        self.assertEqual(mappings["WTIOIL"].hyperliquid_coin, "xyz:CL")
        self.assertEqual(mappings["GOLD"].provider_symbol, "GC=F")
        self.assertEqual(mappings["EUR"].provider_symbol, "EURUSD=X")
        self.assertEqual(mappings["JPY"].provider_symbol, "JPY=X")
        self.assertEqual(mappings["XYZ100"].provider_symbol, "^NDX")
        self.assertEqual(mappings["SP500"].provider_symbol, "^GSPC")

    def test_aliases_resolve_to_reference_mapping(self) -> None:
        mapping = get_trade_xyz_reference_mapping("CL")

        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.trade_symbol, "WTIOIL")
        self.assertEqual(mapping.provider_symbol, "CL=F")


if __name__ == "__main__":
    unittest.main()
