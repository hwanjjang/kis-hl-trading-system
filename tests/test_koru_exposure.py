"""Regression contract for the selected South Korea execution exposure."""
import tempfile
import unittest
from pathlib import Path

from kis_hl.instruments import instrument, capabilities
from kis_hl.storage import (
    seed_trade_xyz_assets, list_trade_xyz_assets,
    seed_trade_xyz_kis_mappings, list_trade_xyz_kis_mappings,
)


class KoruExposureTests(unittest.TestCase):
    def test_koru_replaces_kr200_in_execution_catalog_and_sqlite_mappings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.sqlite'
            seed_trade_xyz_assets(path)
            seed_trade_xyz_kis_mappings(path)
            assets = {r['trade_symbol']: r for r in list_trade_xyz_assets(path)}
            mappings = {r['trade_symbol']: r for r in list_trade_xyz_kis_mappings(path)}
            self.assertIn('KORU', assets)
            self.assertTrue(assets['KORU']['tradable'])
            self.assertEqual(assets['KORU']['hyperliquid_coin'], 'xyz:KORU')
            for symbol in ('KR200', 'EWY'):
                self.assertFalse(assets[symbol]['tradable'])
                self.assertEqual(assets[symbol]['preferred_symbol'], 'KORU')
                self.assertEqual(mappings[symbol]['status'], 'excluded')
            self.assertEqual(mappings['KORU']['status'], 'active')
            self.assertEqual(mappings['KORU']['kis_symbol'], 'KORU')
            self.assertEqual(mappings['KORU']['kis_market'], 'overseas')
            self.assertEqual(mappings['KORU']['kis_exchange_code'], 'AMS')
            asset = instrument('hl:xyz:KORU')
            self.assertEqual(asset.symbol, 'xyz:KORU')
            self.assertEqual(asset.currency, 'USDC')
            self.assertTrue(capabilities(asset.id)['local_trailing'])
            self.assertEqual(capabilities(asset.id)['native_trailing'], 'documented_requires_readback')
