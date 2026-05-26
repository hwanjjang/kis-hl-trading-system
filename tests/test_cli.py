from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from kis_hl.cli import main


class CliTests(unittest.TestCase):
    def test_resolve_symbol_outputs_json(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["resolve-symbol", "--symbol", "BTCUSDC"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["coin"], "UBTC/USDC")


if __name__ == "__main__":
    unittest.main()
