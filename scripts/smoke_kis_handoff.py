"""Offline CLI/SQLite KIS handoff and restart smoke; no network or real orders."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from kis_hl.cli import main
from kis_hl.journal_sync import Scope
from tests.test_kis_adoption import FixtureKisGateway, NOW, plan


def run():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        gateway = FixtureKisGateway()
        scope = Scope("kis", "live", "fixture")
        source = root / "plan.json"
        source.write_text(json.dumps(plan()))

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

        adopted = cli(NOW, "order", "adopt", "--input", str(source),
                      "--entry-order-id", "0017865300", "--entry-since-ms", str(NOW - 3600000), "--live")
        assert adopted["state"] == "ADOPTING"

        def tick(at):
            return cli(at, "supervisor", "run", "--venue", "kis", "--once", "--live")["positions"][0]

        assert tick(NOW + 1000)["state"] == "PROTECTING"
        assert tick(NOW + 2000)["state"] == "PROTECTED"
        gateway.session = False
        assert tick(NOW + 192000)["exit_requested_ms"] is None
        gateway.session = True
        recovered = tick(NOW + 86400000)
        assert recovered["state"] == "PROTECTED", recovered
        assert recovered["exit_requested_ms"] is None and not gateway.sent
        # Every CLI invocation constructed a new store/supervisor instance.
        tick(NOW + 86520000)
        assert len(gateway.sent) == 1 and gateway.sent[0]["quantity"] == "3"
        status = cli(NOW + 86520001, "supervisor", "status", "--venue", "kis")
        assert status["positions"][0]["exit_requested_ms"] is not None
        print("PASS: CLI KIS adoption, SQLite restart, closed/overnight gap suppression, same-session exit")


if __name__ == "__main__":
    run()
