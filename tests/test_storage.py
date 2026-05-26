from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from kis_hl.storage import store_market_payload, store_order_submission


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


if __name__ == "__main__":
    unittest.main()

