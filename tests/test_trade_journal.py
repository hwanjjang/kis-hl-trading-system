from __future__ import annotations

from decimal import Decimal
import unittest

from kis_hl.trade_journal import calculate_trade_journal_stats, create_trade_journal_record


DAY_MS = 86_400_000


class TradeJournalTests(unittest.TestCase):
    def test_create_trade_journal_record_calculates_long_pnl_and_holding_days(self) -> None:
        record = create_trade_journal_record(
            venue="hyperliquid",
            symbol="xyz:SP500",
            strategy="breakout",
            side="long",
            opened_at_ms=0,
            closed_at_ms=DAY_MS,
            entry_price=Decimal("100"),
            exit_price=Decimal("110"),
            quantity=Decimal("2"),
            fees=Decimal("1"),
        )

        self.assertEqual(record.realized_pnl, Decimal("19"))
        self.assertEqual(record.realized_pnl_pct, Decimal("9.500"))
        self.assertEqual(record.holding_days, Decimal("1"))
        self.assertEqual(record.outcome, "success")

    def test_create_trade_journal_record_calculates_short_return_after_fees(self) -> None:
        record = create_trade_journal_record(
            venue="hyperliquid",
            symbol="BTC",
            strategy="breakdown",
            side="short",
            opened_at_ms=0,
            closed_at_ms=DAY_MS * 2,
            entry_price="100",
            exit_price="90",
            quantity="2",
            fees="2",
        )

        self.assertEqual(record.realized_pnl, Decimal("18"))
        self.assertEqual(record.realized_pnl_pct, Decimal("9.00"))
        self.assertEqual(record.holding_days, Decimal("2"))
        self.assertEqual(record.outcome, "success")

    def test_trade_journal_stats_use_return_percentages_not_currency_pnl(self) -> None:
        small_win = create_trade_journal_record(
            venue="hyperliquid",
            symbol="xyz:SP500",
            strategy="breakout",
            side="long",
            opened_at_ms=0,
            closed_at_ms=DAY_MS,
            entry_price="100",
            exit_price="110",
            quantity="1",
        )
        large_loss = create_trade_journal_record(
            venue="hyperliquid",
            symbol="xyz:TSM",
            strategy="breakout",
            side="long",
            opened_at_ms=0,
            closed_at_ms=DAY_MS * 2,
            entry_price="100",
            exit_price="95",
            quantity="10",
        )

        stats = calculate_trade_journal_stats([small_win, large_loss])

        self.assertEqual(stats.average_profit, Decimal("10"))
        self.assertEqual(stats.average_loss, Decimal("-5"))
        self.assertEqual(stats.success_failure_ratio, "2:1")
        self.assertEqual(stats.adjusted_success_failure_ratio, "2:1")
        self.assertEqual(stats.win_rate_pct, Decimal("50.0"))
        self.assertEqual(stats.max_profit, Decimal("10"))
        self.assertEqual(stats.max_loss, Decimal("-5"))
        self.assertEqual(stats.average_profit_holding_days, Decimal("1"))
        self.assertEqual(stats.average_loss_holding_days, Decimal("2"))

    def test_adjusted_ratio_weights_average_returns_by_win_and_loss_frequency(self) -> None:
        records = [
            create_trade_journal_record(
                venue="hyperliquid",
                symbol="xyz:SP500",
                strategy="breakout",
                side="long",
                opened_at_ms=0,
                closed_at_ms=DAY_MS,
                entry_price="100",
                exit_price=exit_price,
                quantity="1",
            )
            for exit_price in ("110", "120", "95")
        ]

        stats = calculate_trade_journal_stats(records)

        self.assertEqual(stats.average_profit, Decimal("15"))
        self.assertEqual(stats.average_loss, Decimal("-5"))
        self.assertEqual(stats.success_failure_ratio, "3:1")
        self.assertEqual(stats.adjusted_success_failure_ratio, "6:1")
        self.assertEqual(stats.win_rate_pct, Decimal("66.66666666666666666666666667"))

    def test_breakeven_is_counted_but_excluded_from_win_rate_and_ratios(self) -> None:
        records = [
            create_trade_journal_record(
                venue="hyperliquid",
                symbol="xyz:SP500",
                strategy="breakout",
                side="long",
                opened_at_ms=0,
                closed_at_ms=DAY_MS,
                entry_price="100",
                exit_price=exit_price,
                quantity="1",
            )
            for exit_price in ("110", "95", "100")
        ]

        stats = calculate_trade_journal_stats(records)

        self.assertEqual(stats.trade_count, 3)
        self.assertEqual(stats.success_count, 1)
        self.assertEqual(stats.failure_count, 1)
        self.assertEqual(stats.breakeven_count, 1)
        self.assertEqual(stats.win_rate_pct, Decimal("50.0"))
        self.assertEqual(stats.success_failure_ratio, "2:1")
        self.assertEqual(stats.adjusted_success_failure_ratio, "2:1")

    def test_manual_adjusted_outcome_does_not_change_required_statistics(self) -> None:
        loss = create_trade_journal_record(
            venue="hyperliquid",
            symbol="xyz:SP500",
            strategy="breakout",
            side="long",
            opened_at_ms=0,
            closed_at_ms=DAY_MS,
            entry_price="100",
            exit_price="95",
            quantity="1",
            adjusted_outcome="success",
        )

        stats = calculate_trade_journal_stats([loss])

        self.assertEqual(stats.success_count, 0)
        self.assertEqual(stats.failure_count, 1)
        self.assertIsNone(stats.success_failure_ratio)
        self.assertIsNone(stats.adjusted_success_failure_ratio)

    def test_empty_and_one_sided_samples_do_not_invent_ratios(self) -> None:
        empty = calculate_trade_journal_stats([])
        self.assertIsNone(empty.average_profit)
        self.assertIsNone(empty.average_loss)
        self.assertIsNone(empty.win_rate_pct)
        self.assertIsNone(empty.success_failure_ratio)
        self.assertIsNone(empty.adjusted_success_failure_ratio)

        winner = create_trade_journal_record(
            venue="hyperliquid",
            symbol="xyz:SP500",
            strategy="breakout",
            side="long",
            opened_at_ms=0,
            closed_at_ms=DAY_MS,
            entry_price="100",
            exit_price="110",
            quantity="1",
        )
        wins_only = calculate_trade_journal_stats([winner])
        self.assertEqual(wins_only.average_profit, Decimal("10"))
        self.assertIsNone(wins_only.average_loss)
        self.assertEqual(wins_only.win_rate_pct, Decimal("100"))
        self.assertIsNone(wins_only.success_failure_ratio)
        self.assertIsNone(wins_only.adjusted_success_failure_ratio)


if __name__ == "__main__":
    unittest.main()
