from __future__ import annotations

from datetime import date
import unittest

from kis_hl.yahoo_finance.client import YahooFinanceClient


class YahooFinanceClientTests(unittest.TestCase):
    def test_chart_quote_prefers_regular_market_price(self) -> None:
        client = RecordingYahooFinanceClient(
            {
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "regularMarketPrice": 93.61,
                                "regularMarketTime": 1779826992,
                                "currency": "USD",
                                "exchangeName": "NYM",
                                "instrumentType": "FUTURE",
                                "timezone": "EDT",
                            },
                            "indicators": {"quote": [{"close": [93.55, 93.6]}]},
                        }
                    ],
                    "error": None,
                }
            }
        )

        quote = client.chart_quote(ticker="CL=F", range_name="1d", interval="1m")

        self.assertEqual(quote.price, "93.61")
        self.assertEqual(quote.observed_at_ms, 1779826992000)
        self.assertEqual(quote.body["ticker"], "CL=F")
        self.assertEqual(client.calls, [("/v8/finance/chart/CL%3DF", {"range": "1d", "interval": "1m"})])

    def test_chart_quote_falls_back_to_last_close(self) -> None:
        client = RecordingYahooFinanceClient(
            {
                "chart": {
                    "result": [
                        {
                            "meta": {},
                            "indicators": {"quote": [{"close": [None, 10.1, 10.2]}]},
                        }
                    ],
                    "error": None,
                }
            }
        )

        quote = client.chart_quote(ticker="TEST")

        self.assertEqual(quote.price, "10.2")
        self.assertEqual(quote.body["chart_last_close"], "10.2")

    def test_chart_daily_bars_parses_ohlcv_rows(self) -> None:
        client = RecordingYahooFinanceClient(
            {
                "chart": {
                    "result": [
                        {
                            "meta": {"symbol": "CL=F"},
                            "timestamp": [1779753600, 1779840000],
                            "indicators": {
                                "quote": [
                                    {
                                        "open": [93.1, 93.2],
                                        "high": [94.1, 94.2],
                                        "low": [92.1, 92.2],
                                        "close": [93.6, None],
                                        "volume": [1000, 2000],
                                    }
                                ],
                                "adjclose": [{"adjclose": [93.6, 93.7]}],
                            },
                        }
                    ],
                    "error": None,
                }
            }
        )

        response = client.chart_daily_bars(
            ticker="CL=F",
            date_from=date(2026, 5, 1),
            date_to=date(2026, 5, 27),
        )

        self.assertEqual(len(response.bars), 1)
        self.assertEqual(response.bars[0]["close"], 93.6)
        self.assertEqual(response.bars[0]["adj_close"], 93.6)
        self.assertEqual(response.body["bar_count"], 1)


class RecordingYahooFinanceClient(YahooFinanceClient):
    def __init__(self, body: dict[str, object]) -> None:
        super().__init__(base_url="https://example.test")
        self.body = body
        self.calls: list[tuple[str, dict[str, str]]] = []

    def _request_json(self, path: str, *, query: dict[str, str]) -> dict[str, object]:
        self.calls.append((path, query))
        return self.body


if __name__ == "__main__":
    unittest.main()
