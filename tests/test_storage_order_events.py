from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kis_hl.storage import list_order_events, store_order_event


class OrderEventStorageTests(unittest.TestCase):
    def test_store_and_list_order_events_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.sqlite"
            row_id = store_order_event(
                db,
                venue="binance",
                symbol="BTCUSDT",
                order_id="1",
                client_order_id="c1",
                side="BUY",
                order_type="LIMIT",
                execution_type="NEW",
                status="NEW",
                price="75000",
                avg_price="0",
                orig_qty="0.01",
                last_filled_qty="0",
                cum_filled_qty="0",
                stop_price=None,
                reduce_only=False,
                event_time_ms=10,
                received_at_ms=11,
                payload={"e": "ORDER_TRADE_UPDATE"},
            )
            self.assertGreater(row_id, 0)
            store_order_event(
                db,
                venue="binance",
                symbol="ETHUSDT",
                order_id="2",
                client_order_id=None,
                side="SELL",
                order_type="MARKET",
                execution_type="TRADE",
                status="FILLED",
                price="0",
                avg_price="3000",
                orig_qty="1",
                last_filled_qty="1",
                cum_filled_qty="1",
                stop_price=None,
                reduce_only=True,
                event_time_ms=20,
                received_at_ms=21,
                payload={"e": "ORDER_TRADE_UPDATE"},
            )
            rows = list_order_events(db, venue="binance")
            self.assertEqual([r["symbol"] for r in rows], ["ETHUSDT", "BTCUSDT"])
            only_btc = list_order_events(db, venue="binance", symbol="BTCUSDT")
            self.assertEqual(len(only_btc), 1)
            self.assertEqual(only_btc[0]["status"], "NEW")
            self.assertEqual(only_btc[0]["reduce_only"], False)
            self.assertEqual(only_btc[0]["payload"]["e"], "ORDER_TRADE_UPDATE")
            self.assertEqual(list_order_events(db, venue="binance", limit=1)[0]["symbol"], "ETHUSDT")


if __name__ == "__main__":
    unittest.main()
