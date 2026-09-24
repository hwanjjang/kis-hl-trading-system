"""Offline routing regressions; all addresses are synthetic fixtures."""
from dataclasses import replace
from decimal import Decimal
import unittest
from unittest.mock import patch

from kis_hl.config import load_hyperliquid_config
from kis_hl.hyperliquid.client import HyperliquidInfoClient, HyperliquidTradingClient
from types import SimpleNamespace
from contextlib import ExitStack


class SubaccountSdkTests(unittest.TestCase):
    def sdk_stubs(self, signer=None):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch("eth_account.Account.from_key", return_value=SimpleNamespace(address=signer or MASTER)))
        info = stack.enter_context(patch("hyperliquid.info.Info"))
        exchange = stack.enter_context(patch("hyperliquid.exchange.Exchange"))
        public = stack.enter_context(patch.object(HyperliquidInfoClient, "post_info"))
        public.side_effect = lambda payload: ({"role": "subAccount", "data": {"master": MASTER}}
                                              if payload["user"] == SUB else {"role": "user"})
        return info, exchange, public

    def test_sdk_routes_execution_and_signing_to_subaccount(self):
        info, exchange, public = self.sdk_stubs()
        HyperliquidTradingClient(config())._load_sdk()
        self.assertEqual(exchange.call_args.kwargs.get("vault_address"), SUB)
        self.assertEqual(exchange.call_args.kwargs["account_address"], SUB)
        self.assertEqual(public.call_args_list[0].args[0], {"type": "userRole", "user": SUB})
        self.assertEqual(public.call_args_list[1].args[0], {"type": "userRole", "user": MASTER})

    def test_role_failures_block_sdk_construction_and_cancel(self):
        info, exchange, public = self.sdk_stubs()
        for role in [None, [], {}, {"role": "vault"}, {"role": "user"}, {"role": "missing"},
                     {"role": "subAccount"}, {"role": "subAccount", "data": []},
                     {"role": "subAccount", "data": {"master": OTHER}}]:
            public.side_effect = None
            public.return_value = role
            with self.subTest(role=role), self.assertRaises(RuntimeError):
                HyperliquidTradingClient(config()).cancel_order(symbol="BTC-PERP", oid=1, dry_run=False)
        info.assert_not_called()
        exchange.assert_not_called()

    def test_api_agent_signer_rejected_without_fallback(self):
        info, exchange, public = self.sdk_stubs(signer=OTHER)
        with self.assertRaisesRegex(RuntimeError, "master signer"):
            HyperliquidTradingClient(config())._load_sdk()
        exchange.assert_not_called()

    def test_master_role_must_be_user(self):
        info, exchange, public = self.sdk_stubs()
        for role in ["missing", "agent", "vault", "subAccount"]:
            public.side_effect = [{"role": "subAccount", "data": {"master": MASTER}}, {"role": role}]
            with self.subTest(role=role), self.assertRaises(RuntimeError):
                HyperliquidTradingClient(config())._load_sdk()
        exchange.assert_not_called()

    def test_cached_sdk_does_not_cache_role_authorization(self):
        info, exchange, public = self.sdk_stubs()
        client = HyperliquidTradingClient(config())
        client._load_sdk()
        public.side_effect = RuntimeError("public evidence unavailable")
        with self.assertRaises(RuntimeError):
            client._load_sdk()
        self.assertEqual(exchange.call_count, 1)

    def test_non_subaccount_sdk_keeps_legacy_routing(self):
        info, exchange, public = self.sdk_stubs()
        client = HyperliquidTradingClient(config(HYPERLIQUID_SUBACCOUNT_ADDRESS=""))
        client._load_sdk()
        self.assertEqual(exchange.call_args.kwargs["account_address"], MASTER)
        self.assertIsNone(exchange.call_args.kwargs.get("vault_address"))
        public.assert_not_called()

    def test_successful_mock_cancel_reports_verified_route(self):
        info, exchange, public = self.sdk_stubs()
        exchange.return_value.cancel.return_value = {"status": "ok"}
        result = HyperliquidTradingClient(config()).cancel_order(symbol="BTC-PERP", oid=1, dry_run=False)
        self.assertIs(result.request["routing_verified"], True)

    def test_role_guard_precedes_each_signed_operation(self):
        info, exchange, public = self.sdk_stubs()
        public.side_effect = None
        public.return_value = {"role": "missing"}
        client = HyperliquidTradingClient(config())
        calls = [lambda: client.place_order(symbol="BTC-PERP", side="sell", order_type="limit", size=Decimal(1), price=Decimal(100), reduce_only=True, dry_run=False),
                 lambda: client.place_stop_loss_order(symbol="BTC-PERP", side="sell", size=Decimal(1), trigger_price=Decimal(100), dry_run=False),
                 lambda: client.place_trailing_stop_order(symbol="BTC-PERP", side="sell", size=Decimal(1), retracement=Decimal(10), dry_run=False)]
        for call in calls:
            with self.assertRaisesRegex(RuntimeError, "target role"):
                call()
        exchange.assert_not_called()

    def test_real_sdk_constructor_retains_route_without_network(self):
        with patch("eth_account.Account.from_key", return_value=SimpleNamespace(address=MASTER)), \
             patch("hyperliquid.info.Info"), patch("hyperliquid.exchange.Info"), \
             patch("requests.Session.request", side_effect=AssertionError("network forbidden")), \
             patch.object(HyperliquidInfoClient, "post_info", side_effect=[
                 {"role": "subAccount", "data": {"master": MASTER}}, {"role": "user"}]):
            _, exchange = HyperliquidTradingClient(config())._load_sdk()
        self.assertEqual(exchange.vault_address, SUB)
        self.assertEqual(exchange.account_address, SUB)
        self.assertEqual(exchange.wallet.address, MASTER)

    def test_dry_runs_display_route_without_sdk_or_public_reads(self):
        info, exchange, public = self.sdk_stubs()
        client = HyperliquidTradingClient(config())
        submissions = [client.place_order(symbol="BTC-PERP", side="buy", order_type="limit", size=Decimal(1), price=Decimal(100)),
                       client.cancel_order(symbol="BTC-PERP", oid=1),
                       client.place_trailing_stop_order(symbol="BTC-PERP", side="sell", size=Decimal(1), retracement=Decimal(10))]
        for submission in submissions:
            self.assertEqual(submission.request.get("account_address"), SUB)
            self.assertEqual(submission.request.get("master_account_address"), MASTER)
            self.assertEqual(submission.request.get("vault_address"), SUB)
            self.assertEqual(submission.request.get("key_profile"), "default")
            self.assertIs(submission.request.get("routing_verified"), False)
        info.assert_not_called()
        exchange.assert_not_called()
        public.assert_not_called()

MASTER = "0x" + "11" * 20
SUB = "0x" + "22" * 20
OTHER = "0x" + "33" * 20


def config(**overrides):
    env = {"HYPERLIQUID_WALLETADDRESS": MASTER,
           "HYPERLIQUID_PRIVATEKEY": "fixture-not-a-key",
           "HYPERLIQUID_SUBACCOUNT_ADDRESS": SUB}
    env.update(overrides)
    return load_hyperliquid_config(env)


class SubaccountScopeTests(unittest.TestCase):
    def test_read_override_clears_execution_credentials_and_routing(self):
        from kis_hl.operations_cli import scope_client
        with patch("kis_hl.operations_cli.load_hyperliquid_config", return_value=config()):
            scope, info = scope_client("hyperliquid", OTHER)
        self.assertEqual(scope.account, OTHER)
        self.assertEqual(info.config.account_address, OTHER)
        self.assertEqual(info.config.subaccount_address, "")
        self.assertEqual(info.config.master_account_address, "")
        self.assertEqual(info.config.private_key, "")
        with self.assertRaisesRegex(RuntimeError, "private key"):
            HyperliquidTradingClient(info.config)._require_credentials()

    def test_default_info_reads_and_explicit_override(self):
        info = HyperliquidInfoClient(config())
        payloads = []
        def transport(payload):
            payloads.append(payload)
            if payload["type"] == "orderStatus":
                return {"status": "unknownOid"}
            if payload["type"] == "userRole":
                return {"role": "subAccount", "data": {"master": MASTER}}
            return []
        with patch.object(info, "post_info", side_effect=transport):
            info.account_asset_info(include_all_dexs=True, dexes=["xyz"])
            info.frontend_open_orders()
            info.user_fills()
            info.user_fills_by_time(start_time_ms=1, end_time_ms=2)
            info.user_funding(start_time_ms=1, end_time_ms=2)
            info.order_status(oid=1)
            info.user_role()
            self.assertTrue(payloads)
            self.assertTrue(all(p["user"] == SUB for p in payloads))
            info.clearinghouse_state(user=OTHER)
            self.assertEqual(payloads[-1]["user"], OTHER)
        self.assertEqual(info.config.account_address, SUB)

    def test_locks_gateway_and_journal_scope_use_execution_account(self):
        from kis_hl.operations_cli import scope_client
        from kis_hl.managed_gateways import ManagedHyperliquidGateway
        from kis_hl.journal_sync import Scope
        with patch("kis_hl.operations_cli.load_hyperliquid_config", return_value=config()):
            scope, info = scope_client("hyperliquid")
        trading = HyperliquidTradingClient(info.config)
        gateway = ManagedHyperliquidGateway(info, trading)
        self.assertEqual(gateway.account, SUB)
        self.assertEqual(scope.account, SUB)
        self.assertEqual(gateway.scope, Scope("hyperliquid", "mainnet", SUB).key)
        self.assertNotEqual(gateway.scope, Scope("hyperliquid", "mainnet", MASTER).key)
        with patch("kis_hl.execution_lock.account_lock") as lock, patch.object(trading, "_load_sdk", side_effect=RuntimeError("blocked offline")):
            with self.assertRaisesRegex(RuntimeError, "blocked offline"):
                trading.cancel_order(symbol="BTC-PERP", oid=1, dry_run=False)
        lock.assert_called_once_with(info.config.base_url, SUB)


class SubaccountConfigTests(unittest.TestCase):
    def test_effective_account_and_master_are_separate(self):
        c = config()
        self.assertEqual(c.account_address, SUB)
        self.assertEqual(c.master_account_address, MASTER)
        self.assertEqual(c.subaccount_address, SUB)

    def test_invalid_subaccount_configuration_fails_closed(self):
        for target, master in [("0x123", MASTER), (MASTER.upper().replace("0X", "0x"), MASTER),
                               (SUB, ""), (SUB, "0x123"), ("0x" + "gg" * 20, MASTER)]:
            with self.subTest(target=target, master=master), self.assertRaises(ValueError):
                config(HYPERLIQUID_SUBACCOUNT_ADDRESS=target, HYPERLIQUID_WALLETADDRESS=master)

    def test_profiles_do_not_share_routes_or_credentials(self):
        c = config(HYPERLIQUID_KEY_PROFILE="production",
                   PRO_HYPERLIQUID_WALLETADDRESS=OTHER,
                   PRO_HYPERLIQUID_PRIVATEKEY="production-fixture")
        self.assertEqual(c.account_address, OTHER)
        self.assertEqual(c.subaccount_address, "")
        self.assertEqual(c.private_key, "0xproduction-fixture")
        c = config(HYPERLIQUID_KEY_PROFILE="production",
                   PRO_HYPERLIQUID_WALLETADDRESS=OTHER,
                   PRO_HYPERLIQUID_SUBACCOUNT_ADDRESS=SUB)
        self.assertEqual(c.account_address, SUB)
        self.assertEqual(c.master_account_address, OTHER)
        self.assertEqual(c.private_key, "")
        with self.assertRaises(ValueError):
            config(HYPERLIQUID_KEY_PROFILE="production", PRO_HYPERLIQUID_SUBACCOUNT_ADDRESS=SUB)

    def test_replace_cannot_desynchronize_execution_identity(self):
        c = config()
        with self.assertRaises(ValueError):
            replace(c, account_address=OTHER)
        self.assertEqual(replace(c, ws_url="wss://example.invalid").account_address, SUB)

    def test_empty_explicit_environment_has_no_ambient_fallback(self):
        with patch.dict("os.environ", {"HYPERLIQUID_WALLETADDRESS": MASTER}, clear=True):
            self.assertEqual(load_hyperliquid_config({}).account_address, "")
