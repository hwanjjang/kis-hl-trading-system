from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path

from kis_hl.daily_collector import collect_trade_xyz_daily_bars
from kis_hl.yahoo_finance.client import YahooFinanceDailyBars


class DailyCollectorTests(unittest.TestCase):
    def test_collect_trade_xyz_daily_bars_uses_reference_and_underlying_tickers(self) -> None:
        calls = []

        class FakeClient:
            def chart_daily_bars(
                self,
                *,
                ticker: str,
                date_from: date,
                date_to: date,
            ) -> YahooFinanceDailyBars:
                calls.append((ticker, date_from, date_to))
                return YahooFinanceDailyBars(
                    ticker=ticker,
                    status=200,
                    observed_at_ms=100,
                    bars=[
                        {
                            "date": "2026-05-26",
                            "open": "1",
                            "high": "2",
                            "low": "0.5",
                            "close": "1.5",
                            "adj_close": "1.5",
                            "volume": "100",
                        }
                    ],
                    body={"ticker": ticker},
                )

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            summary = collect_trade_xyz_daily_bars(
                db,
                client=FakeClient(),
                symbols=["WTIOIL", "AAPL"],
                days=365,
                date_to=date(2026, 5, 27),
            )

            self.assertEqual(summary["succeeded"], 2)
            self.assertEqual(summary["stored_bars"], 2)
            self.assertEqual(
                calls,
                [
                    ("CL=F", date(2025, 5, 27), date(2026, 5, 27)),
                    ("AAPL", date(2025, 5, 27), date(2026, 5, 27)),
                ],
            )
            with closing(sqlite3.connect(db)) as conn:
                rows = conn.execute(
                    "SELECT symbol, close_price FROM market_daily_bars ORDER BY symbol"
                ).fetchall()
            self.assertEqual(rows, [("AAPL", "1.5"), ("WTIOIL", "1.5")])


if __name__ == "__main__":
    unittest.main()
