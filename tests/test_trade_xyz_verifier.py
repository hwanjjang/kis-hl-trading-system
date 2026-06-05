from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kis_hl.storage import get_latest_trade_xyz_asset_check
from kis_hl.trade_xyz_verifier import find_mid_for_coin, summarize_checks, verify_trade_xyz_assets


class TradeXyzVerifierTests(unittest.TestCase):
    def test_find_mid_accepts_prefixed_and_unprefixed_keys(self) -> None:
        self.assertEqual(find_mid_for_coin({"xyz:KR200": "350"}, "xyz:KR200"), ("350", "xyz:KR200"))
        self.assertEqual(find_mid_for_coin({"KR200": "351"}, "xyz:KR200"), ("351", "KR200"))

    def test_verify_trade_xyz_assets_persists_available_and_missing_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            checks = verify_trade_xyz_assets(
                db,
                mids={"xyz:KR200": "350.1", "XYZ100": "1000.2"},
                tradable_only=True,
                asset_class="equity_index",
                checked_at_ms=100,
            )
            by_symbol = {check["trade_symbol"]: check for check in checks}
            self.assertTrue(by_symbol["KR200"]["available"])
            self.assertTrue(by_symbol["XYZ100"]["available"])
            self.assertFalse(by_symbol["JP225"]["available"])
            self.assertEqual(summarize_checks(checks), {"checked": 4, "available": 2, "unavailable": 2})

            latest = get_latest_trade_xyz_asset_check(db, hyperliquid_coin="xyz:KR200")
            self.assertTrue(latest["available"])
            self.assertEqual(latest["mid_source_key"], "xyz:KR200")

    def test_verify_trade_xyz_commodities_uses_hyperliquid_market_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            checks = verify_trade_xyz_assets(
                db,
                mids={"xyz:CL": "61.2", "xyz:GOLD": "3325.0"},
                tradable_only=True,
                asset_class="commodity",
                checked_at_ms=100,
            )
            by_symbol = {check["trade_symbol"]: check for check in checks}
            self.assertTrue(by_symbol["WTIOIL"]["available"])
            self.assertEqual(by_symbol["WTIOIL"]["mid_source_key"], "xyz:CL")
            self.assertTrue(by_symbol["GOLD"]["available"])
            self.assertFalse(by_symbol["BRENTOIL"]["available"])


if __name__ == "__main__":
    unittest.main()
