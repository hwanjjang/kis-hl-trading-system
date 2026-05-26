from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from kis_hl.storage import (
    get_trade_xyz_kis_mapping,
    get_latest_trade_xyz_asset_check,
    has_recent_successful_trade_xyz_check,
    list_trade_xyz_kis_mappings,
    list_trade_xyz_assets,
    seed_trade_xyz_kis_mappings,
    seed_trade_xyz_assets,
    store_market_payload,
    store_order_submission,
    store_trade_xyz_asset_check,
)


class StorageTests(unittest.TestCase):
    def test_store_market_payload_extracts_last_price(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            row_id = store_market_payload(
                db,
                source="kis",
                market="overseas",
                symbol="AAPL",
                exchange_code="NAS",
                payload={"output": {"last": "189.50"}},
                observed_at_ms=1,
            )
            self.assertEqual(row_id, 1)
            with closing(sqlite3.connect(db)) as conn:
                row = conn.execute("SELECT last_price FROM market_ticks").fetchone()
            self.assertEqual(row[0], "189.50")

    def test_store_market_payload_extracts_index_prices(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            row_id = store_market_payload(
                db,
                source="kis",
                market="trade_xyz_domestic_index",
                symbol="KR200",
                exchange_code="U",
                payload={"output": {"bstp_nmix_prpr": "400.12"}},
                observed_at_ms=1,
            )
            self.assertEqual(row_id, 1)
            with closing(sqlite3.connect(db)) as conn:
                row = conn.execute("SELECT last_price FROM market_ticks").fetchone()
            self.assertEqual(row[0], "400.12")

    def test_store_order_submission_records_dry_run_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            store_order_submission(
                db,
                venue="hyperliquid",
                symbol="BTCUSDC",
                resolved_symbol="UBTC/USDC",
                side="buy",
                order_type="limit",
                size="0.1",
                price="100000",
                dry_run=True,
                status="dry_run",
                response={"ok": True},
                submitted_at_ms=1,
            )
            with closing(sqlite3.connect(db)) as conn:
                row = conn.execute("SELECT dry_run, resolved_symbol FROM order_submissions").fetchone()
            self.assertEqual(row, (1, "UBTC/USDC"))

    def test_seed_trade_xyz_assets_excludes_duplicate_etf_exposures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            count = seed_trade_xyz_assets(db, updated_at_ms=1)
            self.assertGreater(count, 0)
            assets = list_trade_xyz_assets(db)
            by_symbol = {asset["trade_symbol"]: asset for asset in assets}
            self.assertTrue(by_symbol["KR200"]["tradable"])
            self.assertFalse(by_symbol["EWY"]["tradable"])
            self.assertEqual(by_symbol["EWY"]["preferred_symbol"], "KR200")
            self.assertTrue(by_symbol["JP225"]["tradable"])
            self.assertFalse(by_symbol["EWJ"]["tradable"])
            self.assertEqual(by_symbol["EWJ"]["preferred_symbol"], "JP225")
            self.assertEqual(by_symbol["CRCL"]["listing_date"], "2025-06-05")
            self.assertEqual(by_symbol["CRCL"]["min_listing_age_weeks"], 30)

    def test_list_trade_xyz_assets_tradable_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            seed_trade_xyz_assets(db, updated_at_ms=1)
            symbols = {asset["trade_symbol"] for asset in list_trade_xyz_assets(db, tradable_only=True)}
            self.assertIn("KR200", symbols)
            self.assertNotIn("EWY", symbols)

    def test_trade_xyz_asset_check_tracks_latest_availability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            store_trade_xyz_asset_check(
                db,
                trade_symbol="KR200",
                hyperliquid_coin="xyz:KR200",
                dex="xyz",
                available=True,
                last_mid="350.5",
                mid_source_key="xyz:KR200",
                checked_at_ms=100,
                raw={"source_key": "xyz:KR200"},
            )
            latest = get_latest_trade_xyz_asset_check(db, hyperliquid_coin="xyz:KR200")
            self.assertTrue(latest["available"])
            self.assertEqual(latest["last_mid"], "350.5")
            self.assertTrue(
                has_recent_successful_trade_xyz_check(
                    db,
                    hyperliquid_coin="xyz:KR200",
                    max_age_ms=50,
                    now_ms=125,
                )
            )
            self.assertFalse(
                has_recent_successful_trade_xyz_check(
                    db,
                    hyperliquid_coin="xyz:KR200",
                    max_age_ms=10,
                    now_ms=125,
                )
            )

    def test_seed_trade_xyz_kis_mappings_lists_active_and_unsupported_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            count = seed_trade_xyz_kis_mappings(db, updated_at_ms=1)
            self.assertGreater(count, 0)

            active = list_trade_xyz_kis_mappings(db, status="active")
            active_symbols = {item["trade_symbol"] for item in active}
            self.assertIn("AAPL", active_symbols)
            self.assertIn("SAMSUNG", active_symbols)
            self.assertIn("KR200", active_symbols)

            unsupported = list_trade_xyz_kis_mappings(db, status="unsupported")
            unsupported_symbols = {item["trade_symbol"] for item in unsupported}
            self.assertIn("XYZ100", unsupported_symbols)

    def test_get_trade_xyz_kis_mapping_resolves_aliases_and_hyperliquid_coins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            seed_trade_xyz_kis_mappings(db, updated_at_ms=1)

            by_alias = get_trade_xyz_kis_mapping(db, "SMSN")
            by_coin = get_trade_xyz_kis_mapping(db, "xyz:SKHX")

            self.assertEqual(by_alias["trade_symbol"], "SAMSUNG")
            self.assertEqual(by_alias["kis_symbol"], "005930")
            self.assertEqual(by_coin["trade_symbol"], "SKHYNIX")
            self.assertEqual(by_coin["kis_symbol"], "000660")


if __name__ == "__main__":
    unittest.main()
