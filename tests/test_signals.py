from __future__ import annotations

from decimal import Decimal
import unittest

from kis_hl.signals import evaluate_btcusdc_futures_3h_breakout


class SignalTests(unittest.TestCase):
    def test_btc_3h_breakout_enters_when_close_breaks_previous_high(self) -> None:
        signal = evaluate_btcusdc_futures_3h_breakout(
            [
                {"t": 1, "T": 2, "h": "100", "c": "95"},
                {"t": 2, "T": 3, "h": "103", "c": "101"},
            ]
        )

        self.assertTrue(signal.should_enter)
        self.assertEqual(signal.resolved_coin, "BTC")
        self.assertEqual(signal.side, "buy")
        self.assertEqual(signal.reason, "close_above_previous_high")
        self.assertEqual(signal.breakout_level, Decimal("100"))
        self.assertEqual(signal.entry_price, Decimal("101"))

    def test_btc_3h_breakout_does_not_enter_when_close_is_at_previous_high(self) -> None:
        signal = evaluate_btcusdc_futures_3h_breakout(
            [
                {"t": 1, "T": 2, "h": "100", "c": "95"},
                {"t": 2, "T": 3, "h": "101", "c": "100"},
            ]
        )

        self.assertFalse(signal.should_enter)
        self.assertEqual(signal.reason, "close_not_above_previous_high")
        self.assertIsNone(signal.entry_price)

    def test_btc_3h_breakout_uses_highest_prior_candle_for_lookback(self) -> None:
        signal = evaluate_btcusdc_futures_3h_breakout(
            [
                {"t": 1, "T": 2, "h": "100", "c": "99"},
                {"t": 2, "T": 3, "h": "110", "c": "101"},
                {"t": 3, "T": 4, "h": "105", "c": "109"},
                {"t": 4, "T": 5, "h": "112", "c": "111"},
            ],
            lookback_candles=3,
        )

        self.assertTrue(signal.should_enter)
        self.assertEqual(signal.breakout_level, Decimal("110"))
        self.assertEqual(signal.reference_candle_start_ms, 2)

    def test_btc_3h_breakout_requires_enough_closed_candles(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires at least 3 closed candles"):
            evaluate_btcusdc_futures_3h_breakout(
                [
                    {"t": 1, "T": 2, "h": "100", "c": "95"},
                    {"t": 2, "T": 3, "h": "101", "c": "102"},
                ],
                lookback_candles=2,
            )


if __name__ == "__main__":
    unittest.main()
