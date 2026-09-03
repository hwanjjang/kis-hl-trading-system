from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from kis_hl.storage import (
    get_trade_xyz_kis_mapping,
    get_trade_xyz_reference_mapping,
    get_latest_trade_xyz_asset_check,
    has_recent_successful_trade_xyz_check,
    list_latest_trade_xyz_universe_assets,
    list_market_funding_rates,
    list_market_spread_snapshots,
    list_protective_orders,
    list_trade_journal_entries,
    list_trade_xyz_kis_mappings,
    list_trade_xyz_reference_mappings,
    list_trade_xyz_assets,
    seed_trade_xyz_kis_mappings,
    seed_trade_xyz_reference_mappings,
    seed_trade_xyz_assets,
    store_market_daily_bars,
    store_market_payload,
    store_order_submission,
    store_protective_order,
    store_trade_journal_entry,
    store_trade_xyz_asset_check,
    store_trade_xyz_universe_snapshot,
    upsert_market_funding_rates,
    store_market_spread_snapshot,
)
from kis_hl.trade_journal import calculate_trade_journal_stats, create_trade_journal_record


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

    def test_store_market_payload_extracts_yahoo_prices(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            row_id = store_market_payload(
                db,
                source="yahoo_finance",
                market="trade_xyz_reference_yahoo_finance",
                symbol="GOLD",
                exchange_code="CMX",
                payload={"regular_market_price": "4507.0"},
                observed_at_ms=1,
            )
            self.assertEqual(row_id, 1)
            with closing(sqlite3.connect(db)) as conn:
                row = conn.execute("SELECT last_price FROM market_ticks").fetchone()
            self.assertEqual(row[0], "4507.0")

    def test_store_market_daily_bars_upserts_by_source_symbol_and_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            count = store_market_daily_bars(
                db,
                source="yahoo_finance",
                market="trade_xyz_daily_yahoo_finance",
                symbol="WTIOIL",
                exchange_code="NYM",
                bars=[
                    {
                        "date": "2026-05-26",
                        "open": "93.1",
                        "high": "94.1",
                        "low": "92.1",
                        "close": "93.6",
                        "adj_close": "93.6",
                        "volume": "1000",
                    }
                ],
                observed_at_ms=1,
            )
            self.assertEqual(count, 1)
            store_market_daily_bars(
                db,
                source="yahoo_finance",
                market="trade_xyz_daily_yahoo_finance",
                symbol="WTIOIL",
                exchange_code="NYM",
                bars=[
                    {
                        "date": "2026-05-26",
                        "open": "93.2",
                        "high": "94.2",
                        "low": "92.2",
                        "close": "93.7",
                        "adj_close": "93.7",
                        "volume": "2000",
                    }
                ],
                observed_at_ms=2,
            )
            with closing(sqlite3.connect(db)) as conn:
                rows = conn.execute(
                    "SELECT close_price, volume FROM market_daily_bars"
                ).fetchall()
            self.assertEqual(rows, [("93.7", "2000")])

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

    def test_store_and_list_protective_orders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            row_id = store_protective_order(
                db,
                venue="hyperliquid",
                symbol="xyz:KR200",
                resolved_symbol="xyz:KR200",
                side="sell",
                order_type="stop-market",
                trigger_price="340",
                covered_size="1",
                order_id="123",
                client_request_id="abc",
                source_order_submission_id=7,
                dry_run=False,
                active=True,
                status="submitted",
                response={"ok": True},
                submitted_at_ms=1,
            )

            orders = list_protective_orders(db, active_only=True, resolved_symbol="xyz:KR200")

            self.assertEqual(row_id, 1)
            self.assertEqual(len(orders), 1)
            self.assertTrue(orders[0]["active"])
            self.assertFalse(orders[0]["dry_run"])
            self.assertEqual(orders[0]["order_id"], "123")
            self.assertEqual(orders[0]["response"], {"ok": True})

    def test_upsert_and_list_market_funding_rates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            count = upsert_market_funding_rates(
                db,
                dex="xyz",
                symbol="xyz:SP500",
                rows=[
                    {
                        "time": 1000,
                        "fundingRate": "0.0001",
                        "premium": "0.0002",
                    }
                ],
                observed_at_ms=2000,
            )
            upsert_market_funding_rates(
                db,
                dex="xyz",
                symbol="xyz:SP500",
                rows=[
                    {
                        "time": 1000,
                        "fundingRate": "0.0003",
                        "premium": "0.0004",
                    }
                ],
                observed_at_ms=3000,
            )

            rows = list_market_funding_rates(db, symbol="xyz:SP500")

            self.assertEqual(count, 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["funding_rate"], "0.0003")
            self.assertEqual(rows[0]["premium"], "0.0004")
            self.assertEqual(rows[0]["observed_at_ms"], 3000)

    def test_store_and_list_market_spread_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            row_id = store_market_spread_snapshot(
                db,
                dex="xyz",
                symbol="xyz:DRAM",
                observed_at_ms=1000,
                best_bid="68.900",
                best_ask="68.920",
                mid_price="68.910",
                spread_abs="0.020",
                spread_bps="2.9023",
                bid_size="10",
                ask_size="12",
                raw={"levels": []},
            )

            rows = list_market_spread_snapshots(db, symbol="xyz:DRAM")

            self.assertEqual(row_id, 1)
            self.assertEqual(rows[0]["spread_abs"], "0.020")
            self.assertEqual(rows[0]["spread_bps"], "2.9023")
            self.assertEqual(rows[0]["raw"], {"levels": []})

    def test_store_trade_xyz_universe_snapshot_tracks_new_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            snapshot_id = store_trade_xyz_universe_snapshot(
                db,
                dex="xyz",
                observed_at_ms=1000,
                assets=[
                    {
                        "name": "xyz:SP500",
                        "szDecimals": 2,
                        "maxLeverage": 20,
                        "marginTableId": 20,
                    },
                    {
                        "name": "xyz:NEW",
                        "szDecimals": 3,
                        "maxLeverage": 10,
                        "marginTableId": 10,
                    },
                ],
                asset_contexts=[
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
                new_symbols=["xyz:NEW"],
                missing_symbols=["xyz:OLD"],
                raw={"universe": "raw"},
            )

            rows = list_latest_trade_xyz_universe_assets(db, dex="xyz")

            self.assertEqual(snapshot_id, 1)
            self.assertEqual({row["symbol"] for row in rows}, {"xyz:SP500", "xyz:NEW"})
            new_row = next(row for row in rows if row["symbol"] == "xyz:NEW")
            self.assertEqual(new_row["asset_context"]["markPx"], "12.3")
            self.assertEqual(new_row["day_base_volume"], "100")
            self.assertEqual(new_row["day_notional_volume"], "1230")
            self.assertEqual(new_row["open_interest"], "50")

    def test_store_and_list_trade_journal_entries_with_stats_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            record = create_trade_journal_record(
                venue="hyperliquid",
                symbol="xyz:SP500",
                strategy="breakout",
                side="long",
                opened_at_ms=0,
                closed_at_ms=86_400_000,
                entry_price="100",
                exit_price="110",
                quantity="1",
            )
            stats = calculate_trade_journal_stats([record])

            row_id = store_trade_journal_entry(db, record=record, stats=stats, created_at_ms=2)
            entries = list_trade_journal_entries(db, symbol="xyz:SP500")

            self.assertEqual(row_id, 1)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["symbol"], "xyz:SP500")
            self.assertEqual(entries[0]["realized_pnl"], "10")
            self.assertIsNone(entries[0]["stats"]["success_failure_ratio"])

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
            self.assertTrue(by_symbol["WTIOIL"]["tradable"])
            self.assertEqual(by_symbol["WTIOIL"]["hyperliquid_coin"], "xyz:CL")
            self.assertEqual(by_symbol["GOLD"]["underlying_symbol"], "XAUUSD")
            self.assertTrue(by_symbol["JPY"]["tradable"])

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
            self.assertIn("XYZ100", active_symbols)

            unsupported = list_trade_xyz_kis_mappings(db, status="unsupported")
            unsupported_symbols = {item["trade_symbol"] for item in unsupported}
            self.assertNotIn("XYZ100", unsupported_symbols)
            self.assertIn("WTIOIL", unsupported_symbols)
            self.assertIn("GOLD", unsupported_symbols)
            self.assertIn("JPY", unsupported_symbols)

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

    def test_seed_trade_xyz_reference_mappings_lists_yahoo_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            count = seed_trade_xyz_reference_mappings(db, updated_at_ms=1)
            self.assertGreater(count, 0)

            commodities = list_trade_xyz_reference_mappings(
                db,
                provider="yahoo_finance",
                status="active",
                asset_class="commodity",
            )
            commodity_symbols = {item["trade_symbol"] for item in commodities}
            self.assertIn("WTIOIL", commodity_symbols)
            self.assertIn("GOLD", commodity_symbols)

            by_alias = get_trade_xyz_reference_mapping(db, "CL")
            by_provider_symbol = get_trade_xyz_reference_mapping(db, "GC=F")

            self.assertEqual(by_alias["trade_symbol"], "WTIOIL")
            self.assertEqual(by_alias["provider_symbol"], "CL=F")
            self.assertEqual(by_provider_symbol["trade_symbol"], "GOLD")


if __name__ == "__main__":
    unittest.main()
