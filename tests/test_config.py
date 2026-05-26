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

    def test_load_env_file_does_not_override_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("K=value_from_file\n", encoding="utf-8")
            with patch.dict(os.environ, {"K": "existing"}, clear=False):
                load_env_file(env_file)
                self.assertEqual(os.environ["K"], "existing")


if __name__ == "__main__":
    unittest.main()

