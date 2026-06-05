from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kis_hl.storage import (
    list_latest_trade_xyz_universe_assets,
    list_market_funding_rates,
    list_market_spread_snapshots,
)
from kis_hl.xyz_market_collector import (
    collect_xyz_funding_rates,
    collect_xyz_spreads,
    collect_xyz_universe,
)


class FakeHyperliquidInfoClient:
    def __init__(self) -> None:
        self.funding_requests: list[dict[str, object]] = []
        self.books: list[str] = []

    def all_mids(self, *, dex: str | None = None) -> dict[str, str]:
        self.requested_dex = dex
        return {"xyz:SP500": "7600", "xyz:NEW": "12.3"}

    def meta_and_asset_ctxs(self, *, dex: str | None = None) -> list[object]:
        self.requested_meta_dex = dex
        return [
            {
                "universe": [
                    {"name": "xyz:SP500", "szDecimals": 2, "maxLeverage": 20},
                    {"name": "xyz:NEW", "szDecimals": 3, "maxLeverage": 10},
                ]
            },
            [
                {
                    "dayBaseVlm": "23444.746",
                    "dayNtlVlm": "178144435.4205000103",
                    "markPx": "7600",
                    "openInterest": "67434.546",
                },
                {
                    "dayBaseVlm": "100",
                    "dayNtlVlm": "1230",
                    "markPx": "12.3",
                    "openInterest": "50",
                },
            ],
        ]

    def funding_history(
        self,
        symbol: str,
        *,
        start_time_ms: int,
        end_time_ms: int,
        dex: str | None = None,
    ) -> list[dict[str, object]]:
        self.funding_requests.append(
            {
                "symbol": symbol,
                "start_time_ms": start_time_ms,
                "end_time_ms": end_time_ms,
                "dex": dex,
            }
        )
        return [
            {
                "coin": symbol,
                "fundingRate": "0.0001",
                "premium": "0.0002",
                "time": 1000,
            }
        ]

    def l2_book(self, symbol: str, *, dex: str | None = None) -> dict[str, object]:
        self.books.append(symbol)
        return {
            "coin": "xyz:" + symbol,
            "time": 2000,
            "levels": [
                [{"px": "99.9", "sz": "10"}],
                [{"px": "100.1", "sz": "12"}],
            ],
        }


class XyzMarketCollectorTests(unittest.TestCase):
    def test_collect_xyz_universe_stores_snapshot_and_detects_new_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            client = FakeHyperliquidInfoClient()

            summary = collect_xyz_universe(
                db,
                client=client,
                previous_symbols={"xyz:SP500"},
                observed_at_ms=3000,
            )

            self.assertEqual(summary["asset_count"], 2)
            self.assertEqual(summary["new_symbols"], ["xyz:NEW"])
            self.assertEqual(summary["assets_with_open_interest"], 2)
            self.assertEqual(summary["assets_with_day_notional_volume"], 2)
            rows = list_latest_trade_xyz_universe_assets(db, dex="xyz")
            self.assertEqual({row["symbol"] for row in rows}, {"xyz:SP500", "xyz:NEW"})
            sp500 = next(row for row in rows if row["symbol"] == "xyz:SP500")
            self.assertEqual(sp500["day_base_volume"], "23444.746")
            self.assertEqual(sp500["day_notional_volume"], "178144435.4205000103")
            self.assertEqual(sp500["open_interest"], "67434.546")

    def test_collect_xyz_funding_rates_stores_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            client = FakeHyperliquidInfoClient()

            summary = collect_xyz_funding_rates(
                db,
                client=client,
                symbols=["SP500"],
                lookback_hours=24,
                end_time_ms=2000,
            )

            self.assertEqual(summary["succeeded"], 1)
            self.assertEqual(summary["stored_rows"], 1)
            rows = list_market_funding_rates(db, symbol="xyz:SP500")
            self.assertEqual(rows[0]["funding_rate"], "0.0001")
            self.assertEqual(client.funding_requests[0]["symbol"], "xyz:SP500")

    def test_collect_xyz_spreads_stores_best_bid_ask_spread(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            client = FakeHyperliquidInfoClient()

            summary = collect_xyz_spreads(
                db,
                client=client,
                symbols=["SP500"],
                observed_at_ms=3000,
            )

            self.assertEqual(summary["succeeded"], 1)
            self.assertEqual(summary["stored"], 1)
            rows = list_market_spread_snapshots(db, symbol="xyz:SP500")
            self.assertEqual(rows[0]["best_bid"], "99.9")
            self.assertEqual(rows[0]["best_ask"], "100.1")
            self.assertEqual(rows[0]["spread_abs"], "0.2")


if __name__ == "__main__":
    unittest.main()
