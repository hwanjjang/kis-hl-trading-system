from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from kis_hl.cli import main
from kis_hl.kis.client import KisHttpResponse


class CliTests(unittest.TestCase):
    def test_resolve_symbol_outputs_json(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["resolve-symbol", "--symbol", "BTCUSDC"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["coin"], "UBTC/USDC")

    def test_kis_http_failure_exits_nonzero_without_storing(self) -> None:
        class FakeKisClient:
            def __init__(self, _config: object) -> None:
                pass

            def inquire_overseas_price(self, *, exchange_code: str, symbol: str) -> KisHttpResponse:
                return KisHttpResponse(500, {"msg1": "rate limit"}, {})

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            stderr = io.StringIO()
            with (
                patch("kis_hl.cli.load_kis_config", return_value=object()),
                patch("kis_hl.cli.KisClient", FakeKisClient),
                redirect_stdout(io.StringIO()),
                patch("sys.stderr", stderr),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "kis-price",
                        "--market",
                        "overseas",
                        "--symbol",
                        "AAPL",
                        "--store",
                    ]
                )
            self.assertEqual(exit_code, 1)
            self.assertFalse(db_path.exists())

    def test_xyz_assets_seed_and_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            with redirect_stdout(io.StringIO()):
                seed_exit = main(["--db", str(db_path), "xyz-assets", "seed"])
            self.assertEqual(seed_exit, 0)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                list_exit = main(
                    ["--db", str(db_path), "xyz-assets", "list", "--tradable-only"]
                )
            self.assertEqual(list_exit, 0)
            payload = json.loads(stdout.getvalue())
            symbols = {asset["trade_symbol"] for asset in payload["assets"]}
            self.assertIn("KR200", symbols)
            self.assertNotIn("EWY", symbols)

    def test_xyz_assets_verify_uses_hyperliquid_mids(self) -> None:
        class FakeHyperliquidInfoClient:
            def __init__(self, _config: object) -> None:
                pass

            def all_mids(self, *, dex: str | None = None) -> dict[str, str]:
                assert dex == "xyz"
                return {"xyz:KR200": "350.1", "XYZ100": "1000.2"}

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            stdout = io.StringIO()
            with (
                patch("kis_hl.cli.load_hyperliquid_config", return_value=object()),
                patch("kis_hl.cli.HyperliquidInfoClient", FakeHyperliquidInfoClient),
                redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "--db",
                        str(db_path),
                        "xyz-assets",
                        "verify",
                        "--asset-class",
                        "equity_index",
                    ]
                )
            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["checked"], 4)
            self.assertEqual(payload["available"], 2)
            symbols = {check["trade_symbol"] for check in payload["checks"] if check["available"]}
            self.assertEqual(symbols, {"KR200", "XYZ100"})

    def test_xyz_assets_seed_kis_and_fetch_uses_mapping(self) -> None:
        calls = []

        class FakeKisClient:
            def __init__(self, _config: object) -> None:
                pass

            def inquire_domestic_price(self, *, symbol: str, market_code: str) -> KisHttpResponse:
                calls.append((symbol, market_code))
                return KisHttpResponse(200, {"rt_cd": "0", "output": {"stck_prpr": "75000"}}, {})

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            with redirect_stdout(io.StringIO()):
                seed_exit = main(["--db", str(db_path), "xyz-assets", "seed-kis"])
            self.assertEqual(seed_exit, 0)

            stdout = io.StringIO()
            with (
                patch("kis_hl.cli.load_kis_config", return_value=object()),
                patch("kis_hl.cli.KisClient", FakeKisClient),
                redirect_stdout(stdout),
            ):
                fetch_exit = main(
                    [
                        "--db",
                        str(db_path),
                        "xyz-assets",
                        "kis-fetch",
                        "--symbol",
                        "SMSN",
                        "--store",
                    ]
                )
            self.assertEqual(fetch_exit, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["mapping"]["trade_symbol"], "SAMSUNG")
            self.assertEqual(payload["mapping"]["kis_symbol"], "005930")
            self.assertEqual(payload["stored_id"], 1)
            self.assertEqual(calls, [("005930", "J")])

    def test_xyz_assets_kis_fetch_rejects_unsupported_mapping(self) -> None:
        class FakeKisClient:
            def __init__(self, _config: object) -> None:
                raise AssertionError("unsupported assets must not call KIS")

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite"
            with redirect_stdout(io.StringIO()):
                seed_exit = main(["--db", str(db_path), "xyz-assets", "seed-kis"])
            self.assertEqual(seed_exit, 0)

            stderr = io.StringIO()
            with (
                patch("kis_hl.cli.load_kis_config", return_value=object()),
                patch("kis_hl.cli.KisClient", FakeKisClient),
                redirect_stdout(io.StringIO()),
                patch("sys.stderr", stderr),
            ):
                fetch_exit = main(
                    ["--db", str(db_path), "xyz-assets", "kis-fetch", "--symbol", "KR200"]
                )
            self.assertEqual(fetch_exit, 1)
            payload = json.loads(stderr.getvalue().strip().splitlines()[-1])
            self.assertIn("unsupported", payload["error"])


if __name__ == "__main__":
    unittest.main()
