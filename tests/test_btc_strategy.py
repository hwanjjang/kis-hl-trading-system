from __future__ import annotations

from decimal import Decimal
import unittest

from kis_hl.assets import resolve_hyperliquid_symbol
from kis_hl.btc_strategy import (
    DEFAULT_BTC_ENTRY_NOTIONAL_USDC,
    THREE_HOURS_MS,
    BtcSpotBreakoutPerpStrategy,
    create_btc_perp_entry_plan,
    execute_btc_perp_entry_plan,
)
from kis_hl.hyperliquid.client import OrderSubmission
from kis_hl.signals import evaluate_btcusdc_futures_3h_breakout
from kis_hl.streaming import PriceTick


class BtcStrategyTests(unittest.TestCase):
    def test_spot_ticks_create_entry_plan_when_closed_3h_candle_breaks_previous_high(self) -> None:
        strategy = BtcSpotBreakoutPerpStrategy(atr_10d=Decimal("500"))

        ticks = [
            _tick(0, "95000"),
            _tick(1_000, "100000"),
            _tick(THREE_HOURS_MS, "98000"),
            _tick(THREE_HOURS_MS + 1_000, "101000"),
            _tick(THREE_HOURS_MS * 2, "100500"),
        ]
        plans = [plan for tick in ticks if (plan := strategy.on_tick(tick)) is not None]

        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertEqual(plan.entry_notional_usdc, DEFAULT_BTC_ENTRY_NOTIONAL_USDC)
        self.assertEqual(plan.entry_price, Decimal("101000"))
        self.assertEqual(plan.entry_size, Decimal("80") / Decimal("101000"))
        self.assertEqual(plan.stop_distance, Decimal("1000"))
        self.assertEqual(plan.stop_loss_price, Decimal("100000"))
        self.assertEqual(plan.perp_coin, "BTC")

    def test_strategy_does_not_emit_duplicate_entry_after_first_plan(self) -> None:
        strategy = BtcSpotBreakoutPerpStrategy(atr_10d=Decimal("500"))
        ticks = [
            _tick(0, "95000"),
            _tick(1_000, "100000"),
            _tick(THREE_HOURS_MS, "98000"),
            _tick(THREE_HOURS_MS + 1_000, "101000"),
            _tick(THREE_HOURS_MS * 2, "100500"),
            _tick(THREE_HOURS_MS * 2 + 1_000, "102000"),
            _tick(THREE_HOURS_MS * 3, "102500"),
        ]

        plans = [plan for tick in ticks if (plan := strategy.on_tick(tick)) is not None]

        self.assertEqual(len(plans), 1)

    def test_create_entry_plan_uses_80_usdc_notional_and_atr_stop(self) -> None:
        signal = evaluate_btcusdc_futures_3h_breakout(
            [
                {"t": 1, "T": 2, "h": "100000", "c": "99000"},
                {"t": 2, "T": 3, "h": "101000", "c": "100500"},
            ]
        )

        plan = create_btc_perp_entry_plan(signal, atr_10d=Decimal("250"))

        self.assertEqual(plan.entry_size, Decimal("80") / Decimal("100500"))
        self.assertEqual(plan.stop_loss_price, Decimal("100000"))
        self.assertEqual(plan.stop_atr_multiple, Decimal("2"))

    def test_execute_plan_submits_market_entry_and_reduce_only_stop(self) -> None:
        class FakeTradingClient:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def place_order(self, **kwargs: object) -> OrderSubmission:
                self.calls.append(kwargs)
                return OrderSubmission(
                    "dry_run",
                    True,
                    resolve_hyperliquid_symbol(str(kwargs["symbol"])),
                    {"symbol": kwargs["symbol"], **kwargs},
                    {"skipped": "dry_run"},
                )

            def place_stop_loss_order(self, **kwargs: object) -> OrderSubmission:
                self.calls.append({"order_type": "stop-market", **kwargs})
                return OrderSubmission(
                    "dry_run",
                    True,
                    resolve_hyperliquid_symbol(str(kwargs["symbol"])),
                    {"symbol": kwargs["symbol"], "order_type": "stop-market", **kwargs},
                    {"skipped": "dry_run"},
                )

        signal = evaluate_btcusdc_futures_3h_breakout(
            [
                {"t": 1, "T": 2, "h": "100000", "c": "99000"},
                {"t": 2, "T": 3, "h": "101000", "c": "100500"},
            ]
        )
        plan = create_btc_perp_entry_plan(signal, atr_10d=Decimal("250"))
        client = FakeTradingClient()

        execution = execute_btc_perp_entry_plan(client, plan)

        self.assertEqual(client.calls[0]["symbol"], "BTCUSDC-PERP")
        self.assertEqual(client.calls[0]["side"], "buy")
        self.assertEqual(client.calls[0]["order_type"], "market")
        self.assertEqual(client.calls[1]["side"], "sell")
        self.assertEqual(client.calls[1]["trigger_price"], Decimal("100000"))
        self.assertEqual(execution["entry_order"]["status"], "dry_run")
        self.assertEqual(execution["stop_loss_order"]["status"], "dry_run")


def _tick(received_at_ms: int, price: str) -> PriceTick:
    return PriceTick(
        source="hyperliquid",
        symbol="UBTC/USDC",
        price=Decimal(price),
        received_at_ms=received_at_ms,
    )


if __name__ == "__main__":
    unittest.main()
