from __future__ import annotations

from decimal import Decimal
import unittest

from kis_hl.config import HyperliquidConfig
from kis_hl.hyperliquid.client import HyperliquidTradingClient, submission_to_dict


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


if __name__ == "__main__":
    unittest.main()

