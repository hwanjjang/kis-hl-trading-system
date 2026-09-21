import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from kis_hl.cli import main
from kis_hl.journal_sync import JournalLedger, Scope


class OperationsCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "state.sqlite"

    def run_cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch("kis_hl.cli.load_env_file"),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = main(["--db", str(self.db), *args])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_idle_scheduler_releases_real_account_lock(self):
        import subprocess
        import sys
        import time
        from kis_hl.journal_sync import SyncSchedule

        scope = Scope("hyperliquid", "testnet", "idle-fixture")
        SyncSchedule(JournalLedger(self.db), scope).success(int(time.time() * 1000))

        def idle(_):
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from kis_hl.execution_lock import account_lock; "
                    "import sys; "
                    "\nwith account_lock('journal:testnet', sys.argv[1]): pass",
                    scope.key,
                ],
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            raise KeyboardInterrupt

        with (
            patch("kis_hl.operations_cli.scope_client", return_value=(scope, None)),
            patch("kis_hl.operations_cli.time.sleep", side_effect=idle),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.run_cli("journal", "run", "--venue", "hyperliquid")

    def test_incomplete_persistent_sync_waits_for_configured_interval(self):
        from unittest.mock import Mock

        scope = Scope("hyperliquid", "testnet", "pace-fixture")
        sleeps = []

        def idle(_):
            sleeps.append(1)
            if len(sleeps) == 2:
                raise KeyboardInterrupt

        sync = Mock(return_value={"run_complete": False, "run_reason": "Retention gap"})
        with (
            patch("kis_hl.operations_cli.scope_client", return_value=(scope, None)),
            patch("kis_hl.operations_cli.sync_hyperliquid", sync),
            patch("kis_hl.operations_cli.time.sleep", side_effect=idle),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.run_cli("journal", "run", "--venue", "hyperliquid", "--start-ms", "0")
        self.assertEqual(sync.call_count, 1)
        from kis_hl.journal_sync import SyncSchedule

        settings = SyncSchedule(JournalLedger(self.db), scope).settings()
        self.assertIsNone(settings["last_success_ms"])
        self.assertEqual(settings["last_reason"], "Retention gap")

    def test_import_actual_history_without_credentials_and_deduplicate(self):
        raw = {
            "schema_version": 1,
            "source": "fixture broker statement",
            "start_ms": 0,
            "end_ms": 100,
            "complete": True,
            "costs_complete": True,
            "fills": [
                {
                    "execution_id": "1",
                    "symbol": "SPY",
                    "time_ms": 10,
                    "side": "buy",
                    "quantity": "1",
                    "price": "100",
                    "currency": "USD",
                    "fee": "1",
                    "position_before": "0",
                },
                {
                    "execution_id": "2",
                    "symbol": "SPY",
                    "time_ms": 20,
                    "side": "sell",
                    "quantity": "1",
                    "price": "110",
                    "currency": "USD",
                    "fee": "1",
                },
            ],
        }
        p = self.root / "statement.json"
        p.write_text(json.dumps(raw))
        cmd = [
            "journal",
            "import",
            "--venue",
            "kis",
            "--account",
            "fixture",
            "--environment",
            "sim",
            "--input",
            str(p),
        ]
        self.assertEqual(self.run_cli(*cmd)[0], 0)
        self.assertEqual(self.run_cli(*cmd)[0], 0)
        rows = JournalLedger(self.db).entries(Scope("kis", "sim", "fixture"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["realized_pnl"], "8")

    def test_explicit_instrument_mapping_preserves_kospi_and_kospi200(self):
        code, out, err = self.run_cli("instrument", "list")
        self.assertEqual(code, 0)
        rows = {r["id"]: r for r in json.loads(out)["instruments"]}
        self.assertEqual(rows["index:KOSPI"]["symbol"], "0001")
        self.assertEqual(rows["kis:069500"]["underlying"], "KOSPI200")
        self.assertEqual(rows["kis:GLD"]["symbol"], "GLD")
        self.assertEqual(rows["kis:DRAM"]["order_exchange"], "AMEX")
        self.assertEqual(rows["kis:DRAM"]["status"], "broker_metadata_observed")

    def test_native_kis_stop_capability_is_not_inferred(self):
        code, out, err = self.run_cli(
            "instrument", "capabilities", "--instrument", "kis:SPY"
        )
        self.assertEqual(json.loads(out)["native_stop_loss"], "unverified")

    def test_order_preview_requires_no_account_or_network(self):
        from tests.test_managed_execution import plan

        p = self.root / "plan.json"
        data = plan()
        data["expires_ms"] = 9999999999999
        p.write_text(json.dumps(data))
        code, out, err = self.run_cli("order", "preview", "--input", str(p))
        self.assertEqual(code, 0, err)
        self.assertTrue(json.loads(out)["dry_run"])


if __name__ == "__main__":
    unittest.main()
