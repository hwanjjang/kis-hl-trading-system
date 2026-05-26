from __future__ import annotations

from decimal import Decimal
import unittest

from kis_hl.config import HyperliquidConfig
from kis_hl.hyperliquid.client import (
    HyperliquidTradingClient,
    is_supported_live_asset,
    resolve_spot_order_coin,
    submission_to_dict,
)
from kis_hl.assets import resolve_hyperliquid_symbol


class HyperliquidClientTests(unittest.TestCase):
    def test_dry_run_order_does_not_require_credentials_or_sdk(self) -> None:
        client = HyperliquidTradingClient(
            HyperliquidConfig(
                base_url="https://api.hyperliquid.xyz",
                account_address="",
                private_key="",
                key_profile="default",
            )
        )
        submission = client.place_order(
            symbol="BTCUSDC",
            side="buy",
            order_type="limit",
            size=Decimal("0.001"),
            price=Decimal("100000"),
        )
        result = submission_to_dict(submission)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["resolved"]["coin"], "UBTC/USDC")
        self.assertEqual(result["status"], "dry_run")

    def test_limit_order_requires_price(self) -> None:
        client = HyperliquidTradingClient(
            HyperliquidConfig(
                base_url="https://api.hyperliquid.xyz",
                account_address="",
                private_key="",
                key_profile="default",
            )
        )
        with self.assertRaises(ValueError):
            client.place_order(
                symbol="xyz:XYZ100",
                side="buy",
                order_type="limit",
                size=Decimal("1"),
            )

    def test_spot_order_coin_resolves_to_index_from_spot_meta(self) -> None:
        spot_meta = {
            "tokens": [
                {"name": "USDC", "index": 0},
                {"name": "UBTC", "index": 150},
            ],
            "universe": [
                {"index": 107, "tokens": [150, 0]},
            ],
        }
        self.assertEqual(resolve_spot_order_coin(spot_meta, "UBTC/USDC"), "@107")

    def test_live_asset_allowlist_rejects_unknown_perp(self) -> None:
        self.assertFalse(is_supported_live_asset(resolve_hyperliquid_symbol("ETH")))
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("BTCUSDC")))
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("xyz:XYZ100")))
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("xyz:KR200")))
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("xyz:JP225")))
        self.assertFalse(is_supported_live_asset(resolve_hyperliquid_symbol("xyz:EWY")))
        self.assertFalse(is_supported_live_asset(resolve_hyperliquid_symbol("xyz:EWJ")))

    def test_live_order_rejects_unsupported_symbol_before_credentials(self) -> None:
        client = HyperliquidTradingClient(
            HyperliquidConfig(
                base_url="https://api.hyperliquid.xyz",
                account_address="",
                private_key="",
                key_profile="default",
            )
        )
        with self.assertRaises(RuntimeError):
            client.place_order(
                symbol="ETH",
                side="buy",
                order_type="limit",
                size=Decimal("1"),
                price=Decimal("1000"),
                dry_run=False,
            )


if __name__ == "__main__":
    unittest.main()
