from __future__ import annotations

import unittest
from datetime import date, timedelta
from decimal import Decimal

from kis_hl.risk import (
    calculate_30w_ema_status,
    calculate_atr_10d,
    calculate_operating_capital,
    calculate_position_size,
    n_multiplier_for_asset_class,
)


class RiskTests(unittest.TestCase):
    def test_operating_capital_floors_portfolio_to_thousands_and_applies_multiple(self) -> None:
        self.assertEqual(calculate_operating_capital(Decimal("2372.90")), Decimal("40000"))
        self.assertEqual(calculate_operating_capital(Decimal("999.99")), Decimal("0"))

    def test_position_size_uses_one_percent_risk_budget_and_atr_stop_distance(self) -> None:
        size = calculate_position_size(
            operating_capital_usdc=Decimal("40000"),
            atr=Decimal("5"),
            n=Decimal("2"),
            entry_price=Decimal("100"),
        )

        self.assertEqual(size.risk_budget_usdc, Decimal("400.00"))
        self.assertEqual(size.stop_distance, Decimal("10"))
        self.assertEqual(size.amount, Decimal("40.00"))
        self.assertEqual(size.entry_notional_usdc, Decimal("4000.00"))

    def test_asset_class_n_defaults_match_strategy_design(self) -> None:
        self.assertEqual(n_multiplier_for_asset_class("equity_index"), Decimal("2.0"))
        self.assertEqual(n_multiplier_for_asset_class("stock"), Decimal("3.0"))
        with self.assertRaisesRegex(ValueError, "unsupported asset_class"):
            n_multiplier_for_asset_class("unknown")

    def test_atr_10d_uses_true_range_and_requires_previous_close(self) -> None:
        start = date(2026, 1, 1)
        bars = [
            {
                "date": start + timedelta(days=idx),
                "high": Decimal(101 + idx),
                "low": Decimal(99 + idx),
                "close": Decimal(100 + idx),
            }
            for idx in range(11)
        ]

        self.assertEqual(calculate_atr_10d(bars), Decimal("2"))

    def test_30w_ema_status_groups_daily_bars_by_iso_week(self) -> None:
        start = date(2025, 1, 6)
        bars = [
            {
                "date": start + timedelta(weeks=idx),
                "high": Decimal(100 + idx),
                "low": Decimal(98 + idx),
                "close": Decimal(99 + idx),
            }
            for idx in range(31)
        ]

        status = calculate_30w_ema_status(bars)

        self.assertEqual(status.weekly_close_count, 31)
        self.assertTrue(status.above)
        self.assertGreater(status.latest_close, status.ema)


if __name__ == "__main__":
    unittest.main()
