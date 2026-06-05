from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kis_hl.reference_collector import (
    collect_trade_xyz_reference_quotes,
    fetch_mapped_reference_response,
)
from kis_hl.storage import seed_trade_xyz_reference_mappings
from kis_hl.yahoo_finance.client import YahooFinanceQuote


class ReferenceCollectorTests(unittest.TestCase):
    def test_fetch_mapped_reference_response_routes_yahoo_chart_quote(self) -> None:
        calls = []

        class FakeClient:
            def chart_quote(
                self,
                *,
                ticker: str,
                range_name: str,
                interval: str,
            ) -> YahooFinanceQuote:
                calls.append((ticker, range_name, interval))
                return YahooFinanceQuote(
                    ticker=ticker,
                    status=200,
                    price="93.61",
                    observed_at_ms=100,
                    body={"price": "93.61"},
                )

        mapping = {
            "trade_symbol": "WTIOIL",
            "status": "active",
            "provider": "yahoo_finance",
            "provider_symbol": "CL=F",
            "provider_market": "NYM",
            "reason": None,
        }

        mapped = fetch_mapped_reference_response(FakeClient(), mapping)

        self.assertEqual(mapped.storage_market, "trade_xyz_reference_yahoo_finance")
        self.assertEqual(mapped.exchange_code, "NYM")
        self.assertEqual(mapped.response.price, "93.61")
        self.assertEqual(calls, [("CL=F", "1d", "1m")])

    def test_collect_trade_xyz_reference_quotes_stores_successes(self) -> None:
        class FakeClient:
            def chart_quote(
                self,
                *,
                ticker: str,
                range_name: str,
                interval: str,
            ) -> YahooFinanceQuote:
                return YahooFinanceQuote(
                    ticker=ticker,
                    status=200,
                    price="4507.0",
                    observed_at_ms=100,
                    body={"price": "4507.0", "ticker": ticker},
                )

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            seed_trade_xyz_reference_mappings(db, updated_at_ms=1)

            summary = collect_trade_xyz_reference_quotes(
                db,
                client=FakeClient(),
                symbols=["GOLD", "UNKNOWN"],
                store=True,
            )

            self.assertEqual(summary["succeeded"], 1)
            self.assertEqual(summary["skipped"], 1)
            self.assertEqual(summary["stored"], 1)
            self.assertEqual(summary["results"][0]["provider_symbol"], "GC=F")


if __name__ == "__main__":
    unittest.main()
