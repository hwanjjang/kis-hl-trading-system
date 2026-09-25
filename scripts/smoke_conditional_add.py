"""Offline CLI/SQLite smoke; all venue calls replaced by the issue-27 stub."""
import contextlib
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kis_hl.cli import main
from kis_hl.managed_execution import ExecutionStore
from kis_hl.strategy_signals import Signals
from tests.test_conditional_add import AddGateway, add_plan, add_signal, capital, protected, NOW


def run():
    with tempfile.TemporaryDirectory(prefix="conditional-add-smoke-") as directory:
        root = Path(directory)
        store = ExecutionStore(root/"state.sqlite")
        gateway = AddGateway()
        row, _ = protected(store, gateway, native=True)
        signals = Signals(store)
        signal = add_signal(signals, row)
        plan = add_plan(row)
        path = root/"add.json"
        path.write_text(json.dumps(plan))
        clock = [NOW+5]
        scope = SimpleNamespace(key="scope", environment="testnet")
        info = SimpleNamespace(config=None, user_abstraction=lambda: "unifiedAccount",
                               spot_clearinghouse_state=lambda: capital()["spot"])
        commands = []

        def cli(*argv):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["--db", str(store.path), *argv])
            assert code == 0, output.getvalue()
            data = json.loads(output.getvalue())
            commands.append("kis-hl --db TEMP/state.sqlite " + " ".join(str(a).replace(str(root), "TEMP") for a in argv))
            return data

        with patch("kis_hl.cli.load_env_file"), \
             patch("kis_hl.operations_cli.time.time", side_effect=lambda: clock[0]/1000), \
             patch("kis_hl.operations_cli.scope_client", return_value=(scope, info)), \
             patch("kis_hl.operations_cli.HyperliquidTradingClient"), \
             patch("kis_hl.managed_gateways.ManagedHyperliquidGateway", return_value=gateway), \
             patch.object(socket, "socket", side_effect=AssertionError("Offline smoke forbids network")):
            captured = cli("account", "capital", "--venue", "hyperliquid")
            assert captured["reconciliation"]["total_balance"] == "1000"
            preview = cli("order", "preview", "--input", str(path))
            assert preview["dry_run"] and preview["authority_required"]
            assert preview["sizing"]["max_expires_ms"] == NOW+50000
            assert preview["sizing"]["expiry_within_bounds"]
            initial = len(gateway.sent)
            tranche = cli("signal", "execute", "--id", signal["id"], "--input", str(path), "--manual", "--live")
            assert tranche["status"] == "QUEUED" and len(gateway.sent) == initial
            cli("supervisor", "run", "--venue", "hyperliquid", "--live", "--once")
            add = [a for a in gateway.sent if a["kind"] == "add"][-1]
            gateway.fill(add, "0.2", terminal=False)
            for tick in (10, 11):
                clock[0] = NOW+tick
                cli("supervisor", "run", "--venue", "hyperliquid", "--live", "--once")
            assert float(store.get(row["id"])["covered_size"]) == 1.2
            gateway.fill(add, "0.5")
            for tick in (12, 13, 14):
                clock[0] = NOW+tick
                cli("supervisor", "run", "--venue", "hyperliquid", "--live", "--once")
            replay = cli("signal", "execute", "--id", signal["id"], "--input", str(path), "--manual", "--live")
            status = cli("order", "status", "--id", row["id"])
            assert replay["id"] == tranche["id"]
            assert status["state"] == "PROTECTED"
            assert float(status["covered_size"]) == float(status["trailing_covered_size"]) == 1.5
            assert float(status["tranches"][0]["filled"]) == 0.5
            assert len([a for a in gateway.sent if a["kind"] == "add"]) == 1
        print(json.dumps({"result": "passed", "network": "forbidden", "gateway": "stub",
            "sqlite": "temporary, reopened by every CLI invocation", "commands": commands,
            "total_balance": "1000", "operating_capital": preview["sizing"]["operating_capital"],
            "add_attempts": 1, "tranche_filled": "0.5", "remaining": "1.5",
            "sl_coverage": status["covered_size"], "native_ts_coverage": status["trailing_covered_size"],
            "state": status["state"]}, indent=2))


if __name__ == "__main__":
    run()
