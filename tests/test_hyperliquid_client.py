from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from kis_hl.config import HyperliquidConfig
from kis_hl.hyperliquid.client import (
    HyperliquidInfoClient,
    HyperliquidTradingClient,
    extract_hyperliquid_order_id,
    is_supported_live_asset,
    resolve_spot_order_coin,
    submission_to_dict,
)
from kis_hl.assets import resolve_hyperliquid_symbol
from kis_hl.storage import store_trade_xyz_asset_check


class HyperliquidClientTests(unittest.TestCase):
    def test_account_asset_info_uses_public_wallet_state_endpoints(self) -> None:
        class RecordingInfoClient(HyperliquidInfoClient):
            def __init__(self) -> None:
                super().__init__(
                    HyperliquidConfig(
                        base_url="https://api.hyperliquid.xyz",
                        account_address="0xabc",
                        private_key="",
                        key_profile="default",
                    )
                )
                self.payloads: list[dict[str, object]] = []

            def post_info(self, payload: dict[str, object]) -> object:
                self.payloads.append(payload)
                return {"type": payload["type"]}

        client = RecordingInfoClient()

        info = client.account_asset_info()

        self.assertEqual(info["user"], "0xabc")
        self.assertEqual(
            client.payloads,
            [
                {"type": "clearinghouseState", "user": "0xabc"},
                {"type": "spotClearinghouseState", "user": "0xabc"},
            ],
        )
        self.assertEqual(info["perp"]["type"], "clearinghouseState")
        self.assertEqual(info["spot"]["type"], "spotClearinghouseState")

    def test_account_asset_info_can_query_named_hip3_dexes(self) -> None:
        class RecordingInfoClient(HyperliquidInfoClient):
            def __init__(self) -> None:
                super().__init__(
                    HyperliquidConfig(
                        base_url="https://api.hyperliquid.xyz",
                        account_address="0xabc",
                        private_key="",
                        key_profile="default",
                    )
                )
                self.payloads: list[dict[str, object]] = []

            def post_info(self, payload: dict[str, object]) -> object:
                self.payloads.append(payload)
                return {"type": payload["type"], "dex": payload.get("dex")}

        client = RecordingInfoClient()

        info = client.account_asset_info(include_spot=False, dexes=["xyz"])

        self.assertEqual(
            client.payloads,
            [
                {"type": "clearinghouseState", "user": "0xabc"},
                {"type": "clearinghouseState", "user": "0xabc", "dex": "xyz"},
            ],
        )
        self.assertEqual(info["dexes"]["xyz"]["dex"], "xyz")

    def test_account_asset_info_requires_wallet_address(self) -> None:
        client = HyperliquidInfoClient(
            HyperliquidConfig(
                base_url="https://api.hyperliquid.xyz",
                account_address="",
                private_key="",
                key_profile="default",
            )
        )
        with self.assertRaisesRegex(RuntimeError, "wallet address"):
            client.account_asset_info()

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

    def test_stop_market_order_requires_trigger_price_and_reduce_only(self) -> None:
        client = HyperliquidTradingClient(
            HyperliquidConfig(
                base_url="https://api.hyperliquid.xyz",
                account_address="",
                private_key="",
                key_profile="default",
            )
        )
        with self.assertRaisesRegex(ValueError, "trigger_price"):
            client.place_order(
                symbol="xyz:KR200",
                side="sell",
                order_type="stop-market",
                size=Decimal("1"),
                reduce_only=True,
            )
        with self.assertRaisesRegex(ValueError, "reduce_only"):
            client.place_order(
                symbol="xyz:KR200",
                side="sell",
                order_type="stop-market",
                size=Decimal("1"),
                trigger_price=Decimal("340"),
            )

    def test_stop_market_dry_run_records_trigger_details(self) -> None:
        client = HyperliquidTradingClient(
            HyperliquidConfig(
                base_url="https://api.hyperliquid.xyz",
                account_address="",
                private_key="",
                key_profile="default",
            )
        )
        submission = client.place_order(
            symbol="xyz:KR200",
            side="sell",
            order_type="stop-market",
            size=Decimal("1"),
            trigger_price=Decimal("340"),
            reduce_only=True,
        )
        self.assertEqual(submission.request["order_type"], "stop-market")
        self.assertEqual(submission.request["trigger_price"], "340")
        self.assertEqual(submission.request["tpsl"], "sl")
        self.assertTrue(submission.request["trigger_is_market"])

    def test_live_stop_market_uses_hyperliquid_trigger_payload(self) -> None:
        class FakeExchange:
            def __init__(self) -> None:
                self.calls: list[tuple[object, ...]] = []

            def order(self, *args: object) -> dict[str, object]:
                self.calls.append(args)
                return {"status": "ok"}

        fake_exchange = FakeExchange()
        client = HyperliquidTradingClient(
            HyperliquidConfig(
                base_url="https://api.hyperliquid.xyz",
                account_address="0x0000000000000000000000000000000000000001",
                private_key="0x" + "1" * 64,
                key_profile="default",
            )
        )
        client._sdk = (object(), fake_exchange)  # noqa: SLF001
        client._resolve_live_order_coin = lambda resolved: resolved.coin  # type: ignore[method-assign]
        client._require_recent_verification = lambda resolved: None  # type: ignore[method-assign]

        submission = client.place_order(
            symbol="xyz:KR200",
            side="sell",
            order_type="stop-market",
            size=Decimal("0.01"),
            trigger_price=Decimal("95000"),
            reduce_only=True,
            dry_run=False,
        )

        self.assertEqual(submission.status, "submitted")
        self.assertEqual(len(fake_exchange.calls), 1)
        call = fake_exchange.calls[0]
        self.assertEqual(call[0], "xyz:KR200")
        self.assertEqual(call[1], False)
        self.assertEqual(call[2], 0.01)
        self.assertEqual(call[3], 95000.0)
        self.assertEqual(
            call[4],
            {"trigger": {"isMarket": True, "triggerPx": "95000", "tpsl": "sl"}},
        )
        self.assertEqual(call[5], True)

    def test_live_non_reduce_only_order_rejects_closed_underlying_session(self) -> None:
        client = HyperliquidTradingClient(
            HyperliquidConfig(
                base_url="https://api.hyperliquid.xyz",
                account_address="0x0000000000000000000000000000000000000001",
                private_key="0x" + "1" * 64,
                key_profile="default",
            ),
            now=lambda: datetime(
                2026,
                5,
                26,
                20,
                0,
                tzinfo=ZoneInfo("America/New_York"),
            ),
        )
        client._require_recent_verification = lambda resolved: None  # type: ignore[method-assign]

        with self.assertRaisesRegex(RuntimeError, "Underlying market session is closed"):
            client.place_order(
                symbol="xyz:AAPL",
                side="buy",
                order_type="limit",
                size=Decimal("1"),
                price=Decimal("180"),
                dry_run=False,
            )

    def test_live_order_can_explicitly_override_closed_underlying_session(self) -> None:
        class FakeExchange:
            def __init__(self) -> None:
                self.calls: list[tuple[object, ...]] = []

            def order(self, *args: object) -> dict[str, object]:
                self.calls.append(args)
                return {"status": "ok", "response": {"data": {"statuses": [{"resting": {"oid": 7}}]}}}

        fake_exchange = FakeExchange()
        client = HyperliquidTradingClient(
            HyperliquidConfig(
                base_url="https://api.hyperliquid.xyz",
                account_address="0x0000000000000000000000000000000000000001",
                private_key="0x" + "1" * 64,
                key_profile="default",
            ),
            now=lambda: datetime(
                2026,
                5,
                26,
                20,
                0,
                tzinfo=ZoneInfo("America/New_York"),
            ),
        )
        client._sdk = (object(), fake_exchange)  # noqa: SLF001
        client._resolve_live_order_coin = lambda resolved: resolved.coin  # type: ignore[method-assign]
        client._require_recent_verification = lambda resolved: None  # type: ignore[method-assign]

        submission = client.place_order(
            symbol="xyz:AAPL",
            side="buy",
            order_type="limit",
            size=Decimal("1"),
            price=Decimal("180"),
            dry_run=False,
            allow_outside_session=True,
        )

        self.assertEqual(submission.status, "submitted")
        self.assertEqual(len(fake_exchange.calls), 1)
        self.assertEqual(submission.request["session"]["reason"], "outside_regular_session")

    def test_extract_hyperliquid_order_id_finds_nested_status_oid(self) -> None:
        response = {
            "status": "ok",
            "response": {"data": {"statuses": [{"resting": {"oid": 123}}]}},
        }

        self.assertEqual(extract_hyperliquid_order_id(response), "123")

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
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("BTCUSDC-PERP")))
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("xyz:XYZ100")))
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("xyz:KR200")))
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("xyz:JP225")))
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("xyz:WTIOIL")))
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

    def test_live_xyz_order_requires_recent_metadata_verification_before_credentials(self) -> None:
        client = HyperliquidTradingClient(
            HyperliquidConfig(
                base_url="https://api.hyperliquid.xyz",
                account_address="",
                private_key="",
                key_profile="default",
            )
        )
        with self.assertRaisesRegex(RuntimeError, "verification database path"):
            client.place_order(
                symbol="xyz:KR200",
                side="buy",
                order_type="limit",
                size=Decimal("1"),
                price=Decimal("350"),
                dry_run=False,
            )

    def test_live_xyz_order_with_recent_verification_reaches_credential_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite"
            store_trade_xyz_asset_check(
                db,
                trade_symbol="KR200",
                hyperliquid_coin="xyz:KR200",
                dex="xyz",
                available=True,
                last_mid="350",
                mid_source_key="xyz:KR200",
                raw={},
            )
            client = HyperliquidTradingClient(
                HyperliquidConfig(
                    base_url="https://api.hyperliquid.xyz",
                    account_address="",
                    private_key="",
                    key_profile="default",
                ),
                verification_db_path=db,
            )
            with self.assertRaisesRegex(RuntimeError, "Missing Hyperliquid"):
                client.place_order(
                    symbol="xyz:KR200",
                    side="buy",
                    order_type="limit",
                    size=Decimal("1"),
                    price=Decimal("350"),
                    dry_run=False,
                )


if __name__ == "__main__":
    unittest.main()
