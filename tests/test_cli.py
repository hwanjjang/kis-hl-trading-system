from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from contextlib import redirect_stdout
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from kis_hl.cli import main
from kis_hl.config import HyperliquidConfig
from kis_hl.kis.client import KisHttpResponse
from kis_hl.streaming import WebSocketStatus
from kis_hl.yahoo_finance.client import YahooFinanceDailyBars, YahooFinanceQuote


class CliTests(unittest.TestCase):
    def test_resolve_symbol_outputs_json(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["resolve-symbol", "--symbol", "BTCUSDC"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["coin"], "UBTC/USDC")

    def test_hl_account_uses_configured_wallet_address(self) -> None:
        calls = []

        class FakeHyperliquidInfoClient:
            def __init__(self, config: HyperliquidConfig) -> None:
                self.config = config

            def account_asset_info(
                self,
                *,
                user: str | None = None,
                include_spot: bool = True,
                include_all_dexs: bool = True,
                dexes: list[str] | None = None,
            ) -> dict[str, object]:
                calls.append(
                    {
                        "configured_user": self.config.account_address,
                        "user": user,
                        "include_spot": include_spot,
                        "include_all_dexs": include_all_dexs,
                        "dexes": dexes,
                    }
                )
                return {"user": user or self.config.account_address, "perp": {"assetPositions": []}}

        config = HyperliquidConfig(
            base_url="https://api.hyperliquid.xyz",
            account_address="0xabc",
            private_key="",
            key_profile="default",
        )
        stdout = io.StringIO()
        with (
            patch("kis_hl.cli.load_hyperliquid_config", return_value=config),
            patch("kis_hl.cli.HyperliquidInfoClient", FakeHyperliquidInfoClient),
            redirect_stdout(stdout),
        ):
            exit_code = main(["hl-account"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["user"], "0xabc")
        self.assertEqual(calls[0]["configured_user"], "0xabc")
        self.assertTrue(calls[0]["include_spot"])
        self.assertFalse(calls[0]["include_all_dexs"])
        self.assertEqual(calls[0]["dexes"], [])

    def test_btc_3h_breakout_fetches_candles_and_returns_entry_signal(self) -> None:
        calls = []

        class FakeHyperliquidInfoClient:
            def __init__(self, _config: object) -> None:
                pass

            def candle_snapshot(
                self,
                symbol: str,
                *,
                interval: str,
                start_time_ms: int,
                end_time_ms: int,
                dex: str | None = None,
            ) -> list[dict[str, str | int]]:
                calls.append(
                    {
                        "symbol": symbol,
                        "interval": interval,
                        "start_time_ms": start_time_ms,
                        "end_time_ms": end_time_ms,
                        "dex": dex,
                    }
                )
                return [
                    {"t": 1, "T": 2, "h": "100", "c": "95"},
                    {"t": 2, "T": 3, "h": "103", "c": "101"},
                ]

        stdout = io.StringIO()
        with (
            patch("kis_hl.cli.load_hyperliquid_config", return_value=object()),
            patch("kis_hl.cli.HyperliquidInfoClient", FakeHyperliquidInfoClient),
            redirect_stdout(stdout),
        ):
            exit_code = main(
                [
                    "btc-3h-breakout",
                    "--start-ms",
                    "1",
                    "--end-ms",
                    "3",
                ]
            )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["should_enter"])
        self.assertEqual(payload["resolved_coin"], "BTC")
        self.assertEqual(payload["interval"], "3h")
        self.assertEqual(calls[0]["symbol"], "BTCUSDC-PERP")
        self.assertEqual(calls[0]["interval"], "3h")

    def test_btc_3h_monitor_uses_spot_websocket_runner_with_80_usdc_defaults(self) -> None:
        calls = []

        def fake_run_monitor(**kwargs: object) -> WebSocketStatus:
            calls.append(kwargs)
            return WebSocketStatus(url="wss://example.test/ws", state="stopped")

        config = HyperliquidConfig(
            base_url="https://api.hyperliquid.xyz",
            account_address="",
            private_key="",
            key_profile="default",
        )
        stdout = io.StringIO()
        with (
            patch("kis_hl.cli.load_hyperliquid_config", return_value=config),
            patch("kis_hl.cli.run_btc_spot_breakout_monitor", fake_run_monitor),
            redirect_stdout(stdout),
        ):
            exit_code = main(
                [
                    "btc-3h-monitor",
                    "--atr-10d",
                    "500",
                    "--max-messages",
                    "1",
                    "--no-store",
                ]
            )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["atr_10d"], "500")
        self.assertEqual(payload["entry_notional_usdc"], "80")
        self.assertEqual(payload["stop_atr_multiple"], "2")
        self.assertEqual(calls[0]["atr_10d"], Decimal("500"))
        self.assertEqual(calls[0]["entry_notional_usdc"], Decimal("80"))
        self.assertEqual(calls[0]["stop_atr_multiple"], Decimal("2"))
        self.assertTrue(calls[0]["dry_run"])

    def test_trade_stop_market_passes_trigger_price(self) -> None:
        calls = []

        class FakeTradingClient:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                pass

            def place_order(self, **kwargs: object) -> object:
                calls.append(kwargs)

                class Submission:
                    status = "dry_run"
                    dry_run = True
                    resolved = object()
                    request = {"order_type": kwargs["order_type"]}
                    response = {"skipped": "dry_run"}

                return Submission()

        stdout = io.StringIO()
        with (
            patch("kis_hl.cli.load_hyperliquid_config", return_value=object()),
            patch("kis_hl.cli.HyperliquidTradingClient", FakeTradingClient),
            patch("kis_hl.cli.submission_to_dict", return_value={"status": "dry_run"}),
            redirect_stdout(stdout),
        ):
            exit_code = main(
                [
                    "trade",
                    "--symbol",
                    "xyz:KR200",
                    "--side",
                    "sell",
                    "--order-type",
                    "stop-market",
                    "--size",
                    "1",
                    "--trigger-price",
                    "340",
                    "--reduce-only",
                    "--allow-outside-session",
                    "--no-store",
                ]
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(calls[0]["order_type"], "stop-market")
        self.assertEqual(str(calls[0]["trigger_price"]), "340")
        self.assertTrue(calls[0]["reduce_only"])
        self.assertTrue(calls[0]["allow_outside_session"])

    def test_trade_stop_market_stores_trigger_price_and_protective_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            config = HyperliquidConfig(
                base_url="https://api.hyperliquid.xyz",
                account_address="",
                private_key="",
                key_profile="default",
            )
            with (
                patch("kis_hl.cli.load_hyperliquid_config", return_value=config),
                redirect_stdout(io.StringIO()),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "trade",
                        "--symbol",
                        "xyz:KR200",
                        "--side",
                        "sell",
                        "--order-type",
                        "stop-market",
                        "--size",
                        "1",
                        "--trigger-price",
                        "340",
                        "--reduce-only",
                    ]
                )

            self.assertEqual(exit_code, 0)
            with closing(sqlite3.connect(db_path)) as conn:
                row = conn.execute(
                    "SELECT order_type, price FROM order_submissions"
                ).fetchone()
                protective = conn.execute(
                    """
                    SELECT trigger_price, covered_size, dry_run, active, source_order_submission_id
                    FROM protective_orders
                    """
                ).fetchone()
            self.assertEqual(row, ("stop-market", "340"))
            self.assertEqual(protective, ("340", "1", 1, 0, 1))

    def test_journal_add_records_completed_trade_and_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "journal",
                        "add",
                        "--symbol",
                        "xyz:SP500",
                        "--strategy",
                        "breakout",
                        "--side",
                        "long",
                        "--opened-at-ms",
                        "0",
                        "--closed-at-ms",
                        "86400000",
                        "--entry-price",
                        "100",
                        "--exit-price",
                        "110",
                        "--quantity",
                        "1",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["stored_id"], 1)
            self.assertEqual(payload["entry"]["outcome"], "success")
            self.assertEqual(payload["statistics"]["success_failure_ratio"], "1:0")
            self.assertIn("average_profit", payload["required_statistics"])

    def test_journal_stats_lists_existing_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            with redirect_stdout(io.StringIO()):
                main(
                    [
                        "--db",
                        str(db_path),
                        "journal",
                        "add",
                        "--symbol",
                        "xyz:SP500",
                        "--side",
                        "long",
                        "--opened-at-ms",
                        "0",
                        "--closed-at-ms",
                        "86400000",
                        "--entry-price",
                        "100",
                        "--exit-price",
                        "90",
                        "--quantity",
                        "1",
                    ]
                )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["--db", str(db_path), "journal", "stats"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["statistics"]["average_loss"], "-10")
            self.assertEqual(len(payload["entries"]), 1)

    def test_kis_http_failure_exits_nonzero_without_storing(self) -> None:
        class FakeKisClient:
            def __init__(self, _config: object) -> None:
                pass

            def inquire_overseas_price(self, *, exchange_code: str, symbol: str) -> KisHttpResponse:
                return KisHttpResponse(500, {"msg1": "rate limit"}, {})

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            stderr = io.StringIO()
            with (
                patch("kis_hl.cli.load_kis_config", return_value=object()),
                patch("kis_hl.cli.KisClient", FakeKisClient),
                redirect_stdout(io.StringIO()),
                patch("sys.stderr", stderr),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "kis-price",
                        "--market",
                        "overseas",
                        "--symbol",
                        "AAPL",
                        "--store",
                    ]
                )
            self.assertEqual(exit_code, 1)
            self.assertFalse(db_path.exists())

    def test_xyz_assets_seed_and_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            with redirect_stdout(io.StringIO()):
                seed_exit = main(["--db", str(db_path), "xyz-assets", "seed"])
            self.assertEqual(seed_exit, 0)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                list_exit = main(
                    ["--db", str(db_path), "xyz-assets", "list", "--tradable-only"]
                )
            self.assertEqual(list_exit, 0)
            payload = json.loads(stdout.getvalue())
            symbols = {asset["trade_symbol"] for asset in payload["assets"]}
            self.assertIn("KR200", symbols)
            self.assertNotIn("EWY", symbols)

    def test_xyz_assets_verify_uses_hyperliquid_mids(self) -> None:
        class FakeHyperliquidInfoClient:
            def __init__(self, _config: object) -> None:
                pass

            def all_mids(self, *, dex: str | None = None) -> dict[str, str]:
                assert dex == "xyz"
                return {"xyz:KR200": "350.1", "XYZ100": "1000.2"}

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            stdout = io.StringIO()
            with (
                patch("kis_hl.cli.load_hyperliquid_config", return_value=object()),
                patch("kis_hl.cli.HyperliquidInfoClient", FakeHyperliquidInfoClient),
                redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "xyz-assets",
                        "verify",
                        "--asset-class",
                        "equity_index",
                    ]
                )
            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["checked"], 4)
            self.assertEqual(payload["available"], 2)
            symbols = {check["trade_symbol"] for check in payload["checks"] if check["available"]}
            self.assertEqual(symbols, {"KR200", "XYZ100"})

    def test_xyz_assets_verify_accepts_commodity_asset_class(self) -> None:
        class FakeHyperliquidInfoClient:
            def __init__(self, _config: object) -> None:
                pass

            def all_mids(self, *, dex: str | None = None) -> dict[str, str]:
                assert dex == "xyz"
                return {"xyz:CL": "61.2", "xyz:GOLD": "3325.0"}

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            stdout = io.StringIO()
            with (
                patch("kis_hl.cli.load_hyperliquid_config", return_value=object()),
                patch("kis_hl.cli.HyperliquidInfoClient", FakeHyperliquidInfoClient),
                redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "xyz-assets",
                        "verify",
                        "--asset-class",
                        "commodity",
                    ]
                )
            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["checked"], 8)
            self.assertEqual(payload["available"], 2)
            symbols = {check["trade_symbol"] for check in payload["checks"] if check["available"]}
            self.assertEqual(symbols, {"GOLD", "WTIOIL"})

    def test_xyz_assets_seed_kis_and_fetch_uses_mapping(self) -> None:
        calls = []

        class FakeKisClient:
            def __init__(self, _config: object) -> None:
                pass

            def inquire_domestic_price(self, *, symbol: str, market_code: str) -> KisHttpResponse:
                calls.append((symbol, market_code))
                return KisHttpResponse(200, {"rt_cd": "0", "output": {"stck_prpr": "75000"}}, {})

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            with redirect_stdout(io.StringIO()):
                seed_exit = main(["--db", str(db_path), "xyz-assets", "seed-kis"])
            self.assertEqual(seed_exit, 0)

            stdout = io.StringIO()
            with (
                patch("kis_hl.cli.load_kis_config", return_value=object()),
                patch("kis_hl.cli.KisClient", FakeKisClient),
                redirect_stdout(stdout),
            ):
                fetch_exit = main(
                    [
                        "--db",
                        str(db_path),
                        "xyz-assets",
                        "kis-fetch",
                        "--symbol",
                        "SMSN",
                        "--store",
                    ]
                )
            self.assertEqual(fetch_exit, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["mapping"]["trade_symbol"], "SAMSUNG")
            self.assertEqual(payload["mapping"]["kis_symbol"], "005930")
            self.assertEqual(payload["stored_id"], 1)
            self.assertEqual(calls, [("005930", "J")])

    def test_xyz_assets_kis_fetch_rejects_excluded_mapping(self) -> None:
        class FakeKisClient:
            def __init__(self, _config: object) -> None:
                raise AssertionError("excluded assets must not call KIS")

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            with redirect_stdout(io.StringIO()):
                seed_exit = main(["--db", str(db_path), "xyz-assets", "seed-kis"])
            self.assertEqual(seed_exit, 0)

            stderr = io.StringIO()
            with (
                patch("kis_hl.cli.load_kis_config", return_value=object()),
                patch("kis_hl.cli.KisClient", FakeKisClient),
                redirect_stdout(io.StringIO()),
                patch("sys.stderr", stderr),
            ):
                fetch_exit = main(
                    ["--db", str(db_path), "xyz-assets", "kis-fetch", "--symbol", "EWY"]
                )
            self.assertEqual(fetch_exit, 1)
            payload = json.loads(stderr.getvalue().strip().splitlines()[-1])
            self.assertIn("excluded", payload["error"])

    def test_xyz_assets_kis_collect_fetches_batch_and_skips_unsupported(self) -> None:
        calls = []

        class FakeKisClient:
            def __init__(self, _config: object) -> None:
                pass

            def inquire_domestic_price(self, *, symbol: str, market_code: str) -> KisHttpResponse:
                calls.append(("domestic", symbol, market_code))
                return KisHttpResponse(200, {"rt_cd": "0", "output": {"stck_prpr": "75000"}}, {})

            def inquire_domestic_index_price(
                self,
                *,
                index_code: str,
                market_code: str,
            ) -> KisHttpResponse:
                calls.append(("domestic_index", index_code, market_code))
                return KisHttpResponse(200, {"rt_cd": "0", "output": {"bstp_nmix_prpr": "400.12"}}, {})

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            with redirect_stdout(io.StringIO()):
                seed_exit = main(["--db", str(db_path), "xyz-assets", "seed-kis"])
            self.assertEqual(seed_exit, 0)

            stdout = io.StringIO()
            with (
                patch("kis_hl.cli.load_kis_config", return_value=object()),
                patch("kis_hl.cli.KisClient", FakeKisClient),
                redirect_stdout(stdout),
            ):
                collect_exit = main(
                    [
                        "--db",
                        str(db_path),
                        "xyz-assets",
                        "kis-collect",
                        "--symbols",
                        "SAMSUNG",
                        "KR200",
                        "EWY",
                    ]
                )
            self.assertEqual(collect_exit, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["succeeded"], 2)
            self.assertEqual(payload["skipped"], 1)
            self.assertEqual(payload["stored"], 2)
            self.assertEqual(
                calls,
                [("domestic", "005930", "J"), ("domestic_index", "2001", "U")],
            )

    def test_xyz_assets_seed_ref_and_fetch_uses_yahoo_mapping(self) -> None:
        calls = []

        class FakeYahooFinanceClient:
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
                    body={"price": "93.61", "ticker": ticker},
                )

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            with redirect_stdout(io.StringIO()):
                seed_exit = main(["--db", str(db_path), "xyz-assets", "seed-ref"])
            self.assertEqual(seed_exit, 0)

            stdout = io.StringIO()
            with (
                patch("kis_hl.cli.YahooFinanceClient", FakeYahooFinanceClient),
                redirect_stdout(stdout),
            ):
                fetch_exit = main(
                    [
                        "--db",
                        str(db_path),
                        "xyz-assets",
                        "ref-fetch",
                        "--symbol",
                        "WTIOIL",
                        "--store",
                    ]
                )
            self.assertEqual(fetch_exit, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["mapping"]["provider_symbol"], "CL=F")
            self.assertEqual(payload["stored_id"], 1)
            self.assertEqual(calls, [("CL=F", "1d", "1m")])

    def test_xyz_assets_ref_collect_filters_asset_class(self) -> None:
        calls = []

        class FakeYahooFinanceClient:
            def chart_quote(
                self,
                *,
                ticker: str,
                range_name: str,
                interval: str,
            ) -> YahooFinanceQuote:
                calls.append(ticker)
                return YahooFinanceQuote(
                    ticker=ticker,
                    status=200,
                    price="1.1635",
                    observed_at_ms=100,
                    body={"price": "1.1635", "ticker": ticker},
                )

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            with redirect_stdout(io.StringIO()):
                seed_exit = main(["--db", str(db_path), "xyz-assets", "seed-ref"])
            self.assertEqual(seed_exit, 0)

            stdout = io.StringIO()
            with (
                patch("kis_hl.cli.YahooFinanceClient", FakeYahooFinanceClient),
                redirect_stdout(stdout),
            ):
                collect_exit = main(
                    [
                        "--db",
                        str(db_path),
                        "xyz-assets",
                        "ref-collect",
                        "--asset-class",
                        "fx",
                    ]
                )
            self.assertEqual(collect_exit, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["succeeded"], 2)
            self.assertEqual(payload["stored"], 2)
            self.assertEqual(set(calls), {"EURUSD=X", "JPY=X"})

    def test_xyz_assets_daily_collect_fetches_365_day_bars(self) -> None:
        calls = []

        class FakeYahooFinanceClient:
            def chart_daily_bars(
                self,
                *,
                ticker: str,
                date_from: date,
                date_to: date,
            ) -> YahooFinanceDailyBars:
                calls.append((ticker, date_from.isoformat(), date_to.isoformat()))
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
            db_path = Path(tmp) / "test.sqlite"
            stdout = io.StringIO()
            with (
                patch("kis_hl.cli.YahooFinanceClient", FakeYahooFinanceClient),
                redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "xyz-assets",
                        "daily-collect",
                        "--symbols",
                        "WTIOIL",
                        "AAPL",
                        "--to",
                        "2026-05-27",
                    ]
                )
            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["succeeded"], 2)
            self.assertEqual(payload["stored_bars"], 2)
            self.assertEqual(
                calls,
                [
                    ("CL=F", "2025-05-27", "2026-05-27"),
                    ("AAPL", "2025-05-27", "2026-05-27"),
                ],
            )

    def test_xyz_assets_universe_collect_stores_new_symbols(self) -> None:
        class FakeHyperliquidInfoClient:
            def __init__(self, _config: object) -> None:
                pass

            def meta_and_asset_ctxs(self, *, dex: str | None = None) -> list[object]:
                self.dex = dex
                return [
                    {"universe": [{"name": "xyz:SP500"}, {"name": "xyz:NEW"}]},
                    [{"markPx": "7600"}, {"markPx": "12.3"}],
                ]

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            stdout = io.StringIO()
            with (
                patch("kis_hl.cli.load_hyperliquid_config", return_value=object()),
                patch("kis_hl.cli.HyperliquidInfoClient", FakeHyperliquidInfoClient),
                redirect_stdout(stdout),
            ):
                exit_code = main(["--db", str(db_path), "xyz-assets", "universe-collect"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["asset_count"], 2)
            self.assertIn("xyz:NEW", payload["new_symbols"])

    def test_xyz_assets_funding_collect_stores_history(self) -> None:
        class FakeHyperliquidInfoClient:
            def __init__(self, _config: object) -> None:
                pass

            def funding_history(
                self,
                symbol: str,
                *,
                start_time_ms: int,
                end_time_ms: int,
                dex: str | None = None,
            ) -> list[dict[str, object]]:
                return [
                    {
                        "coin": symbol,
                        "fundingRate": "0.0001",
                        "premium": "0.0002",
                        "time": 1000,
                    }
                ]

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            stdout = io.StringIO()
            with (
                patch("kis_hl.cli.load_hyperliquid_config", return_value=object()),
                patch("kis_hl.cli.HyperliquidInfoClient", FakeHyperliquidInfoClient),
                redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "xyz-assets",
                        "funding-collect",
                        "--symbols",
                        "SP500",
                        "--end-ms",
                        "2000",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["succeeded"], 1)
            self.assertEqual(payload["stored_rows"], 1)

    def test_xyz_assets_spread_collect_stores_best_book_spread(self) -> None:
        class FakeHyperliquidInfoClient:
            def __init__(self, _config: object) -> None:
                pass

            def l2_book(self, symbol: str, *, dex: str | None = None) -> dict[str, object]:
                return {
                    "coin": "xyz:" + symbol,
                    "time": 2000,
                    "levels": [
                        [{"px": "99.9", "sz": "10"}],
                        [{"px": "100.1", "sz": "12"}],
                    ],
                }

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            stdout = io.StringIO()
            with (
                patch("kis_hl.cli.load_hyperliquid_config", return_value=object()),
                patch("kis_hl.cli.HyperliquidInfoClient", FakeHyperliquidInfoClient),
                redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "xyz-assets",
                        "spread-collect",
                        "--symbols",
                        "SP500",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["succeeded"], 1)
            self.assertEqual(payload["stored"], 1)


if __name__ == "__main__":
    unittest.main()
