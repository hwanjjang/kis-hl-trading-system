from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from kis_hl.trading_hours import (
    SESSION_CRYPTO_PERP,
    SESSION_COMMODITY_REFERENCE,
    SESSION_CRYPTO_SPOT,
    SESSION_FX_REFERENCE,
    SESSION_KRX_CASH,
    SESSION_TSE_CASH,
    SESSION_US_CASH,
    trading_session_decision_for_symbol,
)


class TradingHoursTests(unittest.TestCase):
    def test_regular_cash_session_elapsed_time_excludes_closures(self):
        from kis_hl.trading_hours import regular_cash_session_elapsed_ms

        def ms(value):
            return int(datetime.fromisoformat(value).timestamp() * 1000)

        cases = (
            (SESSION_KRX_CASH, "2026-09-28T15:00:00+09:00", "2026-09-29T14:00:00+09:00", 330 * 60_000),
            (SESSION_KRX_CASH, "2026-09-25T15:00:00+09:00", "2026-09-28T14:00:00+09:00", 330 * 60_000),
            (SESSION_KRX_CASH, "2026-09-25T15:30:00+09:00", "2026-09-28T09:00:00+09:00", 0),
            (SESSION_KRX_CASH, "2026-09-25T16:00:00+09:00", "2026-09-28T16:00:00+09:00", 390 * 60_000),
            (SESSION_KRX_CASH, "2026-09-28T15:29:00+09:00", "2026-09-29T09:01:00+09:00", 120_000),
            (SESSION_KRX_CASH, "2026-09-28T15:30:00+09:00", "2026-09-29T09:00:00+09:00", 0),
            (SESSION_US_CASH, "2026-10-30T16:00:00-04:00", "2026-11-02T09:30:00-05:00", 0),
            (SESSION_US_CASH, "2026-10-30T15:59:00-04:00", "2026-11-02T09:31:00-05:00", 120_000),
            (SESSION_US_CASH, "2026-03-06T15:59:00-05:00", "2026-03-09T09:31:00-04:00", 120_000),
        )
        for group, start, end, expected in cases:
            with self.subTest(group=group, start=start, end=end):
                self.assertEqual(regular_cash_session_elapsed_ms(ms(start), ms(end), session_group=group), expected)
        self.assertEqual(regular_cash_session_elapsed_ms(100, 100, session_group=SESSION_KRX_CASH), 0)
        self.assertEqual(regular_cash_session_elapsed_ms(200, 100, session_group=SESSION_KRX_CASH), 0)

    def test_native_eth_perpetual_is_available_on_weekends(self):
        decision = trading_session_decision_for_symbol(
            "ETH", now=datetime(2026, 9, 12, 20, tzinfo=ZoneInfo("UTC"))
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.session_group, SESSION_CRYPTO_PERP)

    def test_us_cash_assets_follow_regular_equity_session(self) -> None:
        new_york = ZoneInfo("America/New_York")

        open_decision = trading_session_decision_for_symbol(
            "xyz:AAPL",
            now=datetime(2026, 5, 26, 10, 0, tzinfo=new_york),
        )
        closed_decision = trading_session_decision_for_symbol(
            "xyz:AAPL",
            now=datetime(2026, 5, 26, 20, 0, tzinfo=new_york),
        )

        self.assertTrue(open_decision.allowed)
        self.assertEqual(open_decision.session_group, SESSION_US_CASH)
        self.assertFalse(closed_decision.allowed)
        self.assertEqual(closed_decision.reason, "outside_regular_session")

    def test_koru_follows_us_cash_hours_not_korea_hours(self) -> None:
        open_decision = trading_session_decision_for_symbol(
            "xyz:KORU",
            now=datetime(2026, 5, 26, 10, tzinfo=ZoneInfo("America/New_York")),
        )
        korea_open_decision = trading_session_decision_for_symbol(
            "xyz:KORU",
            now=datetime(2026, 5, 27, 10, tzinfo=ZoneInfo("Asia/Seoul")),
        )
        self.assertTrue(open_decision.allowed)
        self.assertEqual(open_decision.session_group, SESSION_US_CASH)
        self.assertFalse(korea_open_decision.allowed)
        self.assertEqual(korea_open_decision.session_group, SESSION_US_CASH)

    def test_krx_assets_follow_korea_regular_session(self) -> None:
        seoul = ZoneInfo("Asia/Seoul")

        decision = trading_session_decision_for_symbol(
            "xyz:KR200",
            now=datetime(2026, 5, 27, 10, 0, tzinfo=seoul),
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.session_group, SESSION_KRX_CASH)

    def test_tse_assets_close_during_lunch_break(self) -> None:
        tokyo = ZoneInfo("Asia/Tokyo")

        decision = trading_session_decision_for_symbol(
            "xyz:JP225",
            now=datetime(2026, 5, 27, 12, 0, tzinfo=tokyo),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.session_group, SESSION_TSE_CASH)

    def test_commodity_reference_closes_for_daily_maintenance(self) -> None:
        new_york = ZoneInfo("America/New_York")

        decision = trading_session_decision_for_symbol(
            "xyz:WTIOIL",
            now=datetime(2026, 5, 26, 17, 30, tzinfo=new_york),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "daily_maintenance_break")
        self.assertEqual(decision.session_group, SESSION_COMMODITY_REFERENCE)

    def test_fx_reference_opens_after_sunday_new_york_open(self) -> None:
        new_york = ZoneInfo("America/New_York")

        before_open = trading_session_decision_for_symbol(
            "xyz:EUR",
            now=datetime(2026, 5, 24, 16, 30, tzinfo=new_york),
        )
        after_open = trading_session_decision_for_symbol(
            "xyz:EUR",
            now=datetime(2026, 5, 24, 17, 30, tzinfo=new_york),
        )

        self.assertFalse(before_open.allowed)
        self.assertTrue(after_open.allowed)
        self.assertEqual(after_open.session_group, SESSION_FX_REFERENCE)

    def test_btcusdc_spot_is_allowed_around_the_clock(self) -> None:
        decision = trading_session_decision_for_symbol(
            "BTCUSDC",
            now=datetime(2026, 5, 24, 4, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.session_group, SESSION_CRYPTO_SPOT)

    def test_btcusdc_futures_are_allowed_around_the_clock(self) -> None:
        decision = trading_session_decision_for_symbol(
            "BTCUSDC-PERP",
            now=datetime(2026, 5, 24, 4, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.session_group, SESSION_CRYPTO_PERP)


if __name__ == "__main__":
    unittest.main()
