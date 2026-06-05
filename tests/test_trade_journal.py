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

    def test_trade_journal_stats_match_required_report_fields(self) -> None:
        win = create_trade_journal_record(
            venue="hyperliquid",
            symbol="xyz:SP500",
            strategy="breakout",
            side="long",
            opened_at_ms=0,
            closed_at_ms=DAY_MS,
            entry_price="100",
            exit_price="110",
            quantity="2",
        )
        loss = create_trade_journal_record(
            venue="hyperliquid",
            symbol="xyz:TSM",
            strategy="breakout",
            side="long",
            opened_at_ms=0,
            closed_at_ms=DAY_MS * 2,
            entry_price="100",
            exit_price="95",
            quantity="2",
            adjusted_outcome="success",
        )

        stats = calculate_trade_journal_stats([win, loss])

        self.assertEqual(stats.average_profit, Decimal("20"))
        self.assertEqual(stats.average_loss, Decimal("-10"))
        self.assertEqual(stats.success_failure_ratio, "1:1")
        self.assertEqual(stats.adjusted_success_failure_ratio, "2:0")
        self.assertEqual(stats.win_rate_pct, Decimal("50.0"))
        self.assertEqual(stats.max_profit, Decimal("20"))
        self.assertEqual(stats.max_loss, Decimal("-10"))
        self.assertEqual(stats.average_profit_holding_days, Decimal("1"))
        self.assertEqual(stats.average_loss_holding_days, Decimal("2"))


if __name__ == "__main__":
    unittest.main()
