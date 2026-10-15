"""Selected KIS legs and HL XLE resolve as order-catalog instruments."""
from pathlib import Path
import tempfile
import unittest

from kis_hl.instruments import instrument, list_instruments
from kis_hl.storage import (
    list_trade_xyz_assets,
    list_trade_xyz_kis_mappings,
    seed_trade_xyz_assets,
    seed_trade_xyz_kis_mappings,
)
from kis_hl.trade_xyz_assets import is_trade_xyz_symbol_tradable


KIS_LEGS = {
    "UGL": "gold",
    "XLE": "energy",
    "NRGU": "energy",
    "XLV": "health care",
    "CURE": "health care",
    "XLP": "consumer staples",
    "URAA": "uranium",
}


class SelectedOrderCatalogTests(unittest.TestCase):
    def test_kis_legs_use_the_observed_amex_route(self):
        catalog = {row["id"]: row for row in list_instruments()}
        for symbol, underlying in KIS_LEGS.items():
            key = "kis:" + symbol
            self.assertIn(key, catalog)
            asset = instrument(key)
            self.assertEqual(asset.venue, "kis")
            self.assertEqual(asset.market, "overseas")
            self.assertEqual(asset.symbol, symbol)
            self.assertEqual(asset.currency, "USD")
            self.assertEqual(asset.quote_exchange, "AMS")
            self.assertEqual(asset.order_exchange, "AMEX")
            self.assertEqual(asset.underlying, underlying)
            self.assertEqual(asset.status, "broker_metadata_observed")

    def test_hl_xle_is_a_tradable_etf_with_arca_quote_route(self):
        asset = instrument("hl:xyz:XLE")
        self.assertEqual(asset.symbol, "xyz:XLE")
        self.assertEqual(asset.currency, "USDC")
        self.assertTrue(is_trade_xyz_symbol_tradable("xyz:XLE"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.sqlite"
            seed_trade_xyz_assets(path)
            seed_trade_xyz_kis_mappings(path)
            rows = {row["trade_symbol"]: row for row in list_trade_xyz_assets(path)}
            mappings = {row["trade_symbol"]: row for row in list_trade_xyz_kis_mappings(path)}
        row = rows["XLE"]
        self.assertEqual(row["hyperliquid_coin"], "xyz:XLE")
        self.assertEqual(row["asset_class"], "etf")
        self.assertEqual(row["underlying_symbol"], "XLE")
        self.assertTrue(row["tradable"])
        mapping = mappings["XLE"]
        self.assertEqual(mapping["status"], "active")
        self.assertEqual(mapping["kis_market"], "overseas")
        self.assertEqual(mapping["kis_symbol"], "XLE")
        self.assertEqual(mapping["kis_exchange_code"], "AMS")
