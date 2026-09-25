from __future__ import annotations

import io
import urllib.error
from datetime import datetime
from decimal import Decimal
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from zoneinfo import ZoneInfo

from kis_hl.config import HyperliquidConfig
from kis_hl.hyperliquid.client import (
    HyperliquidInfoClient,
    HyperliquidTradingClient,
    TransientInfoError,
    extract_hyperliquid_order_id,
    is_supported_live_asset,
    resolve_spot_order_coin,
    submission_to_dict,
)
from kis_hl.assets import resolve_hyperliquid_symbol
from kis_hl.storage import store_trade_xyz_asset_check


class HyperliquidClientTests(unittest.TestCase):
    def test_info_transient_errors_are_distinct_from_permanent_http_failures(self):
        client = HyperliquidInfoClient(HyperliquidConfig(
            base_url="https://api.hyperliquid.xyz", account_address="fixture-account",
            private_key="", key_profile="default"))
        for status in (408, 429, 500, 502, 503, 504, 400, 401, 403, 404):
            error = urllib.error.HTTPError("https://fixture/info", status, "fixture", {}, io.BytesIO(b'{}'))
            with self.subTest(status=status), patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(RuntimeError) as raised:
                    client.post_info({"type": "userAbstraction"})
                self.assertEqual(isinstance(raised.exception, TransientInfoError),
                                 status in {408, 429, 500, 502, 503, 504})
        for error in (TimeoutError(), ConnectionResetError(), urllib.error.URLError("offline")):
            with self.subTest(error=type(error).__name__), patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(TransientInfoError):
                    client.post_info({"type": "userAbstraction"})

    def test_user_abstraction_uses_effective_account_and_rejects_unknown_shape(self):
        client = HyperliquidInfoClient(HyperliquidConfig(
            base_url="https://api.hyperliquid.xyz", account_address="fixture-account",
            private_key="", key_profile="default"))
        with patch.object(client, "post_info", return_value="unifiedAccount") as post:
            self.assertEqual(client.user_abstraction(), "unifiedAccount")
            post.assert_called_once_with({"type": "userAbstraction", "user": "fixture-account"})
        for body in ({}, None, "unknown"):
            with patch.object(client, "post_info", return_value=body), self.assertRaises(RuntimeError):
                client.user_abstraction()

    def test_active_asset_data_is_bound_to_effective_account_and_resolved_coin(self):
        client = HyperliquidInfoClient(HyperliquidConfig(
            base_url="https://api.hyperliquid.xyz", account_address="fixture-account",
            private_key="", key_profile="default"))
        body = dict(user="fixture-account", coin="ETH", maxTradeSzs=["2", "3"], availableToTrade=["200", "300"])
        with patch.object(client, "post_info", return_value=body) as post:
            self.assertEqual(client.active_asset_data("ETH-PERP"), body)
            post.assert_called_once_with({"type": "activeAssetData", "user": "fixture-account", "coin": "ETH"})
        for changed in ({"user": "other"}, {"coin": "BTC"}):
            with patch.object(client, "post_info", return_value={**body, **changed}), self.assertRaises(RuntimeError):
                client.active_asset_data("ETH-PERP")

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
                symbol="xyz:KORU",
                side="sell",
                order_type="stop-market",
                size=Decimal("1"),
                reduce_only=True,
            )
        with self.assertRaisesRegex(ValueError, "reduce_only"):
            client.place_order(
                symbol="xyz:KORU",
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
            symbol="xyz:KORU",
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
        from hyperliquid.utils.signing import order_type_to_wire

        class FakeExchange:
            def __init__(self) -> None:
                self.calls: list[tuple[object, ...]] = []

            def order(self, *args: object) -> dict[str, object]:
                order_type_to_wire(args[4])
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
            symbol="xyz:KORU",
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
        self.assertEqual(call[0], "xyz:KORU")
        self.assertEqual(call[1], False)
        self.assertEqual(call[2], 0.01)
        self.assertEqual(call[3], 95000.0)
        self.assertEqual(
            call[4],
            {"trigger": {"isMarket": True, "triggerPx": 95000.0, "tpsl": "sl"}},
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

    def test_user_funding_request_is_account_scoped(self):
        from unittest.mock import patch
        client=HyperliquidInfoClient(HyperliquidConfig(base_url='https://example.test',
            account_address='0xabc',private_key='',key_profile='default'))
        with patch.object(client,'post_info',return_value=[]) as send:
            client.user_funding(start_time_ms=1,end_time_ms=2)
        send.assert_called_once_with({'type':'userFunding','user':'0xabc','startTime':1,'endTime':2})

    def test_recent_fill_anchor_uses_unaggregated_account_history(self):
        client=HyperliquidInfoClient(HyperliquidConfig(base_url='https://example.test',
            account_address='0xabc',private_key='',key_profile='default'))
        with patch.object(client,'post_info',return_value=[]) as send:
            client.user_fills()
        send.assert_called_once_with({'type':'userFills','user':'0xabc','aggregateByTime':False})

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
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("ETH")))
        self.assertFalse(is_supported_live_asset(resolve_hyperliquid_symbol("SOL")))
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("BTCUSDC")))
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("BTCUSDC-PERP")))
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("xyz:XYZ100")))
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("xyz:KORU")))
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("xyz:JP225")))
        self.assertTrue(is_supported_live_asset(resolve_hyperliquid_symbol("xyz:WTIOIL")))
        self.assertFalse(is_supported_live_asset(resolve_hyperliquid_symbol("xyz:KR200")))
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
                symbol="SOL",
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
                symbol="xyz:KORU",
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
                trade_symbol="KORU",
                hyperliquid_coin="xyz:KORU",
                dex="xyz",
                available=True,
                last_mid="350",
                mid_source_key="xyz:KORU",
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
                    symbol="xyz:KORU",
                    side="buy",
                    order_type="limit",
                    size=Decimal("1"),
                    price=Decimal("350"),
                    dry_run=False,
                )


class ExchangeSafetyTests(unittest.TestCase):
    def client(self):
        c = HyperliquidTradingClient(HyperliquidConfig('https://api.hyperliquid.xyz', '0xabc', 'unused', 'default'))
        c._sdk = (MagicMock(), MagicMock())
        return c

    def test_market_reduce_only_never_uses_market_open(self):
        c = self.client()
        with patch.object(HyperliquidInfoClient, 'clearinghouse_state', return_value={'assetPositions':[{'position':{'coin':'BTC','szi':'1'}}]}), patch.object(HyperliquidInfoClient, 'all_mids', return_value={'BTC':'100'}), patch.object(HyperliquidInfoClient, 'meta_and_asset_ctxs', return_value=[{'universe':[{'name':'BTC','szDecimals':3}]},[]]):
            c.place_order(symbol='BTC-PERP', side='sell', order_type='market', size=Decimal('1'), reduce_only=True, dry_run=False)
        c._sdk[1].market_open.assert_not_called()
        c._sdk[1].market_close.assert_not_called()
        self.assertTrue(c._sdk[1].order.call_args.args[5])

    def test_reduce_only_spot_market_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'perpetual'):
            self.client().place_order(symbol='BTCUSDC', side='sell', order_type='market', size=Decimal('1'), reduce_only=True)

    def test_explicit_exit_dry_run_rounds_price_and_size_without_sdk(self):
        from kis_hl.hyperliquid.client import prepare_perp_exit
        p, sz = prepare_perp_exit(price=Decimal('123.456'), size=Decimal('1.234567'), sz_decimals=4, slippage=Decimal('0.01'))
        self.assertEqual(p, Decimal('122.23'))  # Sell floor rounds UP to keep slippage bounded.
        self.assertEqual(sz, Decimal('1.2345'))
        for bad in ['0', '1', 'NaN']:
            with self.assertRaises(ValueError):
                prepare_perp_exit(price=Decimal('100'), size=Decimal('1'), sz_decimals=2, slippage=Decimal(bad))

    def test_cloid_is_in_signed_ioc_call(self):
        c = self.client()
        cloid = '0x' + 'a'*32
        with patch('kis_hl.hyperliquid.client.sdk_cloid', side_effect=lambda x: x):
            c.place_order(symbol='BTC-PERP', side='sell', order_type='limit', size=Decimal('1'), price=Decimal('100'), tif='Ioc', reduce_only=True, cloid=cloid, dry_run=False)
        args, kw = c._sdk[1].order.call_args
        self.assertTrue(args[5])
        self.assertEqual(args[4], {'limit': {'tif': 'Ioc'}})
        self.assertEqual(kw['cloid'], cloid)

    def test_new_info_payloads(self):
        c = HyperliquidInfoClient(self.client().config)
        c.post_info = MagicMock(return_value=[])
        c.frontend_open_orders(dex='xyz')
        c.post_info.assert_called_with({'type':'frontendOpenOrders','user':'0xabc','dex':'xyz'})
        c.user_fills_by_time(start_time_ms=12, end_time_ms=34)
        c.post_info.assert_called_with({'type':'userFillsByTime','user':'0xabc','startTime':12,'endTime':34,'aggregateByTime':False})
        c.post_info.return_value={'status':'unknownOid'}
        c.order_status(oid='0x'+'a'*32)
        c.post_info.assert_called_with({'type':'orderStatus','user':'0xabc','oid':'0x'+'a'*32})

    def test_cancel_dry_run_never_loads_sdk(self):
        c = self.client()
        result = c.cancel_order(symbol='BTC-PERP', oid=123)
        self.assertTrue(result.dry_run)
        c._sdk[1].cancel.assert_not_called()

    def test_live_entry_is_blocked_for_managed_position(self):
        with patch('kis_hl.hyperliquid.client.has_managed_position', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'blocks entries'):
                self.client().place_order(symbol='BTC-PERP', side='buy', order_type='limit', size=Decimal('1'), price=Decimal('100'), dry_run=False)

    def test_per_order_rejection_is_not_reported_as_submitted(self):
        c=self.client()
        c._sdk[1].order.return_value={'status':'ok','response':{'data':{'statuses':[{'error':'rejected'}]}}}
        result=c.place_order(symbol='BTC-PERP',side='sell',order_type='limit',size=Decimal('1'),price=Decimal('100'),reduce_only=True,dry_run=False)
        self.assertEqual(result.status,'rejected')

    def test_integer_price_exception_and_unrepresentable_slippage(self):
        from kis_hl.hyperliquid.client import prepare_perp_exit
        p,_=prepare_perp_exit(price=Decimal('123456'),size=Decimal('1'),sz_decimals=0,slippage=Decimal('0.01'))
        self.assertEqual(p,Decimal('122222'))
        with self.assertRaisesRegex(ValueError,'slippage'):
            prepare_perp_exit(price=Decimal('0.1'),size=Decimal('1'),sz_decimals=6,slippage=Decimal('0.01'))

    def test_reduce_only_market_cannot_reverse_the_requested_side(self):
        c=self.client()
        with patch.object(HyperliquidInfoClient, 'clearinghouse_state', return_value={'assetPositions':[{'position':{'coin':'BTC','szi':'-1'}}]}):
            with self.assertRaisesRegex(ValueError, 'side'):
                c.place_order(symbol='BTC-PERP', side='sell', order_type='market', size=Decimal('1'), reduce_only=True, dry_run=False)
        c._sdk[1].market_close.assert_not_called()

    def test_cancel_live_preserves_guard_and_calls_sdk_by_oid(self):
        c = self.client()
        c.cancel_order(symbol='BTC-PERP', oid=123, dry_run=False)
        c._sdk[1].cancel.assert_called_once_with('BTC', 123)
        with patch.object(c, '_require_recent_verification', side_effect=RuntimeError('stale metadata')):
            with self.assertRaisesRegex(RuntimeError, 'stale metadata'):
                c.cancel_order(symbol='xyz:KORU', oid=456, dry_run=False)
        self.assertEqual(c._sdk[1].cancel.call_count, 1)


    def test_expiry_is_forwarded_and_reset_after_signed_action(self):
        c = self.client()
        with patch('kis_hl.hyperliquid.client.time.time', return_value=1):
            c.place_order(symbol='BTC-PERP', side='sell', order_type='limit', size=Decimal('1'),
                          price=Decimal('100'), reduce_only=True, dry_run=False, expires_after_ms=2000)
        self.assertEqual(c._sdk[1].set_expires_after.call_args_list,
                         [unittest.mock.call(2000), unittest.mock.call(None)])

    def test_expired_quote_cannot_reach_exchange(self):
        c = self.client()
        with patch('kis_hl.hyperliquid.client.time.time', return_value=3):
            with self.assertRaisesRegex(TimeoutError, 'expired'):
                c.place_order(symbol='BTC-PERP', side='sell', order_type='limit', size=Decimal('1'),
                              price=Decimal('100'), reduce_only=True, dry_run=False, expires_after_ms=2000)
        c._sdk[1].order.assert_not_called()


if __name__ == "__main__":
    unittest.main()
