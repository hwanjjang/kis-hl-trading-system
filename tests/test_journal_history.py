import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from kis_hl.journal_history import fetch_time_pages, hyperliquid_fill
from kis_hl.journal_history import sync_hyperliquid
from kis_hl.journal_sync import JournalLedger, Scope


class HistoryTests(unittest.TestCase):
    def test_evicted_old_window_does_not_claim_empty_complete_history(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = JournalLedger(Path(temp) / "test.sqlite")
            scope = Scope("hyperliquid", "mainnet", "fixture")
            info = SimpleNamespace(
                user_fills=lambda: [{"time": 1000}],
                user_fills_by_time=lambda **kw: [],
                user_funding=lambda **kw: [],
            )
            result = sync_hyperliquid(ledger, scope, info, start_ms=0, end_ms=100)
            self.assertFalse(result["run_complete"])
            self.assertIsNone(result["covered_until_ms"])
            self.assertIn("retention", result["run_reason"].lower())

    def test_saturated_window_is_split_without_skipping_equal_times(self):
        calls = []
        rows = [{"time": 1, "id": 1}, {"time": 2, "id": 2}, {"time": 3, "id": 3}]

        def fetch(start, end):
            calls.append((start, end))
            return [r for r in rows if start <= r["time"] <= end][:2]

        result = fetch_time_pages(fetch, 0, 4, limit=2)
        self.assertEqual(result, rows)
        self.assertGreater(len(calls), 1)

    def test_saturated_single_timestamp_is_not_complete(self):
        with self.assertRaisesRegex(RuntimeError, "timestamp"):
            fetch_time_pages(lambda a, b: [{"time": 1}, {"time": 1}], 1, 1, limit=2)

    def test_fill_fee_is_not_added_to_builder_fee_twice(self):
        row = {
            "tid": 1,
            "hash": "abc",
            "oid": 2,
            "coin": "BTC",
            "time": 10,
            "side": "B",
            "sz": "1",
            "px": "100",
            "fee": "2",
            "builderFee": "1",
            "feeToken": "USDC",
            "startPosition": "0",
        }
        fill = hyperliquid_fill(row)
        self.assertEqual(fill.fee, "2")
        self.assertEqual(fill.position_before, "0")
        self.assertEqual(fill.strategy, "unassigned")

    def test_spot_asset_identity_requires_metadata(self):
        row = {
            "tid": 1,
            "hash": "abc",
            "oid": 2,
            "coin": "@123",
            "time": 10,
            "side": "B",
            "sz": "1",
            "px": "100",
            "fee": "2",
            "feeToken": "UBTC",
            "startPosition": "0",
        }
        with self.assertRaisesRegex(ValueError, "spot"):
            hyperliquid_fill(row)


if __name__ == "__main__":
    unittest.main()
