"""Offline CLI/SQLite KIS handoff and restart smoke; no network or real orders."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from kis_hl.cli import main
from kis_hl.journal_sync import Scope
from tests.test_kis_adoption import FixtureKisGateway, ms, plan


def run():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        gateway = FixtureKisGateway()
        scope = Scope("kis", "live", "fixture")
        start = ms("2026-09-28T15:29:57+09:00")
        reopen = ms("2026-09-29T09:00:00+09:00")
        source = root / "plan.json"
        source.write_text(json.dumps(plan(expires_ms=start + 600_000)))

        def cli(at, *args):
            gateway._clock = at
            output = io.StringIO()
            # Only environment/account construction and the external venue boundary
            # are replaced; parsing, persistence, locking and supervision are real.
            with patch("kis_hl.cli.load_env_file"), patch(
                "kis_hl.operations_cli.scope_client", return_value=(scope, gateway.client)
            ), patch("kis_hl.operations_cli.time.time", return_value=at / 1000), patch(
                "kis_hl.managed_gateways.ManagedKisGateway", return_value=gateway
            ), contextlib.redirect_stdout(output):
                code = main(["--db", str(root / "state.sqlite"), *args])
            assert code == 0, output.getvalue()
            return json.loads(output.getvalue())

        adopted = cli(start, "order", "adopt", "--input", str(source),
                      "--entry-order-id", "0017865300", "--entry-since-ms", str(start - 3600000), "--live")
        assert adopted["state"] == "ADOPTING"

        def tick(at):
            return cli(at, "supervisor", "run", "--venue", "kis", "--once", "--live")["positions"][0]

        assert tick(start + 1000)["state"] == "PROTECTING"
        assert tick(start + 2000)["state"] == "PROTECTED"
        gateway.session = False
        assert tick(start + 3000)["exit_requested_ms"] is None
        assert tick(start + 192000)["exit_requested_ms"] is None
        gateway.session = True
        recovered = tick(reopen)
        assert recovered["state"] == "PROTECTED", recovered
        assert recovered["exit_requested_ms"] is None and not gateway.sent
        # Every CLI invocation constructed a new store/supervisor instance.
        tick(reopen + 120000)
        assert len(gateway.sent) == 1 and gateway.sent[0]["quantity"] == "3"
        status = cli(reopen + 120001, "supervisor", "status", "--venue", "kis")
        assert status["positions"][0]["exit_requested_ms"] is not None
        print("PASS: CLI KIS adoption, SQLite restart, closed/overnight gap suppression, same-session exit")


if __name__ == "__main__":
    run()
