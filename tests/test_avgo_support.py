"""AVGO eligibility and quote routing use the exact Broadcom common stock."""
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest

from kis_hl.instruments import capabilities, instrument, list_instruments
from kis_hl.kis_mappings import get_trade_xyz_kis_mapping
from kis_hl.storage import (
    list_trade_xyz_assets,
    list_trade_xyz_kis_mappings,
    seed_trade_xyz_assets,
    seed_trade_xyz_kis_mappings,
)
from kis_hl.trade_xyz_assets import is_trade_xyz_symbol_tradable


class AvgoSupportTests(unittest.TestCase):
    def test_managed_catalog_supports_only_hl_avgo_with_readback_capabilities(self):
        catalog = {row["id"]: row for row in list_instruments()}
        self.assertIn("hl:xyz:AVGO", catalog)
        self.assertNotIn("kis:AVGO", catalog)
        asset = instrument("hl:xyz:AVGO")
        self.assertEqual(asset.venue, "hyperliquid")
        self.assertEqual(asset.market, "perp")
        self.assertEqual(asset.symbol, "xyz:AVGO")
        self.assertEqual(asset.currency, "USDC")
        self.assertEqual(asset.underlying, "Broadcom Inc.")
        caps = capabilities(asset.id)
        self.assertEqual(caps["execution"], "documented")
        self.assertEqual(caps["native_stop_loss"], "documented_requires_readback")
        self.assertEqual(caps["native_trailing"], "documented_requires_readback")
        self.assertEqual(caps["native_trailing_policy"], "continuous_mark")
        self.assertTrue(caps["local_trailing"])
        self.assertTrue(caps["session_and_account_verification_required"])
        with self.assertRaises(ValueError):
            instrument("kis:AVGO")

    def test_sqlite_seed_eligible_broadcom_generates_nasdaq_quote_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.sqlite"
            seed_trade_xyz_assets(path)
            seed_trade_xyz_kis_mappings(path)
            assets = {r["trade_symbol"]: r for r in list_trade_xyz_assets(path)}
            mappings = {r["trade_symbol"]: r for r in list_trade_xyz_kis_mappings(path)}
            self.assertIn("AVGO", assets)
            asset = assets["AVGO"]
            self.assertEqual(asset["hyperliquid_coin"], "xyz:AVGO")
            self.assertEqual(asset["asset_class"], "stock")
            self.assertEqual(asset["underlying_name"], "Broadcom Inc.")
            self.assertEqual(asset["underlying_symbol"], "AVGO")
            self.assertEqual(asset["underlying_exchange"], "NASDAQ")
            self.assertEqual(asset["listing_status"], "listed")
            self.assertEqual(asset["listing_date"], "2018-04-05")
            self.assertEqual(asset["min_listing_age_weeks"], 30)
            self.assertTrue(asset["tradable"])
            mapping = mappings["AVGO"]
            self.assertEqual(mapping["hyperliquid_coin"], "xyz:AVGO")
            self.assertEqual(mapping["status"], "active")
            self.assertEqual(mapping["kis_market"], "overseas")
            self.assertEqual(mapping["kis_symbol"], "AVGO")
            self.assertEqual(mapping["kis_exchange_code"], "NAS")
            self.assertEqual(mapping["source"], "kis_overseas_price")
            # Seed eligibility must not invent successful exchange verification.
            with sqlite3.connect(path) as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM trade_xyz_asset_checks WHERE trade_symbol = ?",
                    ("AVGO",),
                ).fetchone()[0], 0)
        listed_on = date(2018, 4, 5)
        eligible_on = listed_on + timedelta(weeks=30)
        self.assertFalse(is_trade_xyz_symbol_tradable("AVGO", as_of=eligible_on - timedelta(days=1)))
        self.assertTrue(is_trade_xyz_symbol_tradable("xyz:AVGO", as_of=eligible_on))
        self.assertTrue(is_trade_xyz_symbol_tradable("AVGO", as_of=date(2026, 10, 7)))
        excluded = get_trade_xyz_kis_mapping("AVGO", as_of=eligible_on - timedelta(days=1))
        active = get_trade_xyz_kis_mapping("xyz:AVGO", as_of=eligible_on)
        assert excluded is not None and active is not None
        self.assertEqual(excluded.status, "excluded")
        self.assertEqual(active.status, "active")
