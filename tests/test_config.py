from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kis_hl.config import load_env_file, load_hyperliquid_config, load_kis_config, normalize_kis_account


class ConfigTests(unittest.TestCase):
    def test_normalize_kis_account_accepts_dash(self) -> None:
        self.assertEqual(normalize_kis_account("12345678-01"), ("12345678", "01"))

    def test_load_kis_config_uses_sim_keys_by_default(self) -> None:
        env = {
            "KIS_API_ST_KEY": "paper-key",
            "KIS_API_ST_SECRET": "paper-secret",
            "KIS_ST_STOCK_ACCOUNT": "1234567801",
        }
        config = load_kis_config(env)
        self.assertEqual(config.mode, "sim")
        self.assertEqual(config.app_key, "paper-key")
        self.assertEqual(config.account8, "12345678")

    def test_hyperliquid_production_profile_uses_pro_keys(self) -> None:
        env = {
            "HYPERLIQUID_KEY_PROFILE": "production",
            "PRO_HYPERLIQUID_WALLETADDRESS": "0xabc",
            "PRO_HYPERLIQUID_PRIVATEKEY": "abc123",
        }
        config = load_hyperliquid_config(env)
        self.assertEqual(config.account_address, "0xabc")
        self.assertEqual(config.private_key, "0xabc123")

    def test_hyperliquid_invalid_profile_fails_closed(self) -> None:
        with self.assertRaises(RuntimeError):
            load_hyperliquid_config({"HYPERLIQUID_KEY_PROFILE": "prod"})

    def test_load_env_file_does_not_override_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("K=value_from_file\n", encoding="utf-8")
            with patch.dict(os.environ, {"K": "existing"}, clear=False):
                load_env_file(env_file)
                self.assertEqual(os.environ["K"], "existing")




class BinanceConfigTests(unittest.TestCase):
    def test_default_profile_uses_plain_keys_and_mainnet_urls(self) -> None:
        from kis_hl.config import load_binance_config

        config = load_binance_config({"BINANCE_APIKEY": "k1", "BINANCE_SECRET": "s1"})
        self.assertEqual(config.api_key, "k1")
        self.assertEqual(config.api_secret, "s1")
        self.assertEqual(config.key_profile, "default")
        self.assertEqual(config.base_url, "https://fapi.binance.com")
        self.assertEqual(config.ws_market_url, "wss://fstream.binance.com/market")
        self.assertEqual(config.ws_public_url, "wss://fstream.binance.com/public")
        self.assertEqual(config.ws_user_url, "wss://fstream.binance.com/private")
        self.assertEqual(config.recv_window_ms, 5000)

    def test_production_profile_uses_pro_keys(self) -> None:
        from kis_hl.config import load_binance_config

        config = load_binance_config(
            {
                "BINANCE_KEY_PROFILE": "production",
                "BINANCE_APIKEY": "k1",
                "BINANCE_SECRET": "s1",
                "PRO_BINANCE_APIKEY": "k2",
                "PRO_BINANCE_SECRET": "s2",
            }
        )
        self.assertEqual(config.api_key, "k2")
        self.assertEqual(config.api_secret, "s2")
        self.assertEqual(config.key_profile, "production")

    def test_rejects_unknown_profile(self) -> None:
        from kis_hl.config import load_binance_config

        with self.assertRaises(RuntimeError):
            load_binance_config({"BINANCE_KEY_PROFILE": "pro"})

    def test_testnet_flag_and_overrides(self) -> None:
        from kis_hl.config import load_binance_config

        testnet = load_binance_config({"BINANCE_TESTNET": "true"})
        self.assertEqual(testnet.base_url, "https://demo-fapi.binance.com")
        self.assertEqual(testnet.ws_market_url, "wss://demo-fstream.binance.com/market")
        self.assertEqual(testnet.ws_public_url, "wss://demo-fstream.binance.com/public")
        self.assertEqual(testnet.ws_user_url, "wss://demo-fstream.binance.com/private")
        overridden = load_binance_config(
            {
                "BINANCE_BASE_URL": "https://alt.example.test/",
                "BINANCE_WS_MARKET_URL": "wss://alt.example.test/m",
                "BINANCE_WS_PUBLIC_URL": "wss://alt.example.test/pub",
                "BINANCE_WS_USER_URL": "wss://alt.example.test/p",
                "BINANCE_RECV_WINDOW_MS": "9000",
            }
        )
        self.assertEqual(overridden.base_url, "https://alt.example.test")
        self.assertEqual(overridden.ws_market_url, "wss://alt.example.test/m")
        self.assertEqual(overridden.ws_public_url, "wss://alt.example.test/pub")
        self.assertEqual(overridden.ws_user_url, "wss://alt.example.test/p")
        self.assertEqual(overridden.recv_window_ms, 9000)

    def test_missing_credentials_default_to_empty(self) -> None:
        from kis_hl.config import load_binance_config

        config = load_binance_config({})
        # Compare emptiness only so a failure never prints a real credential.
        self.assertFalse(config.api_key)
        self.assertFalse(config.api_secret)


class BinanceTradingConfigTests(unittest.TestCase):
    def test_live_symbols_default_and_parsing(self) -> None:
        from kis_hl.config import load_binance_config

        self.assertEqual(load_binance_config({}).live_symbols, ("BTCUSDT",))
        parsed = load_binance_config({"BINANCE_LIVE_SYMBOLS": " btcusdt, ethusdt ,, "})
        self.assertEqual(parsed.live_symbols, ("BTCUSDT", "ETHUSDT"))
        self.assertEqual(load_binance_config({"BINANCE_LIVE_SYMBOLS": ""}).live_symbols, ())

    def test_demo_profile_uses_demo_keys_and_demo_urls(self) -> None:
        from kis_hl.config import load_binance_config

        config = load_binance_config({"BINANCE_KEY_PROFILE": "demo", "DEMO_BINANCE_APIKEY": "dk", "DEMO_BINANCE_SECRET": "ds", "BINANCE_APIKEY": "k"})
        self.assertEqual(config.key_profile, "demo")
        self.assertEqual(config.api_key, "dk")
        self.assertEqual(config.api_secret, "ds")
        self.assertEqual(config.base_url, "https://demo-fapi.binance.com")
        self.assertEqual(config.ws_user_url, "wss://demo-fstream.binance.com/private")
        mainnet_override = load_binance_config({"BINANCE_KEY_PROFILE": "demo", "BINANCE_TESTNET": "false"})
        self.assertEqual(mainnet_override.base_url, "https://fapi.binance.com")


if __name__ == "__main__":
    unittest.main()
