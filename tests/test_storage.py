from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from kis_hl.storage import list_trade_xyz_assets, seed_trade_xyz_assets, store_market_payload, store_order_submission


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
            with sqlite3.connect(db) as conn:
                row = conn.execute("SELECT last_price FROM market_ticks").fetchone()
            self.assertEqual(row[0], "189.50")

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
            with sqlite3.connect(db) as conn:
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

    def test_list_trade_xyz_assets_tradable_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            seed_trade_xyz_assets(db, updated_at_ms=1)
            symbols = {asset["trade_symbol"] for asset in list_trade_xyz_assets(db, tradable_only=True)}
            self.assertIn("KR200", symbols)
            self.assertNotIn("EWY", symbols)


if __name__ == "__main__":
    unittest.main()
