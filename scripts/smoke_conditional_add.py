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
            queued = cli("supervisor", "status", "--venue", "hyperliquid")["positions"][0]
            assert queued["pending_adds"][0]["status"] == "QUEUED"
            submit = gateway.submit

            def lost_ack(owner, attempt):
                result = submit(owner, attempt)
                if attempt["kind"] == "add":
                    raise TimeoutError("Stub accepted add but acknowledgement was lost")
                return result

            gateway.submit = lost_ack
            unknown_run = cli("supervisor", "run", "--venue", "hyperliquid", "--live", "--once")["positions"][0]
            unknown = cli("supervisor", "status", "--venue", "hyperliquid")["positions"][0]
            assert unknown_run["pending_adds"] == unknown["pending_adds"]
            assert unknown["state"] == "PROTECTED" and unknown["pending_adds"][0]["status"] == "UNKNOWN"
            gateway.submit = submit
            add = [a for a in gateway.sent if a["kind"] == "add"][-1]
            gateway.fill(add, "0.2", terminal=False)
            for tick in (10, 11):
                clock[0] = NOW+tick
                cli("supervisor", "run", "--venue", "hyperliquid", "--live", "--once")
            assert float(store.get(row["id"])["covered_size"]) == 1.2
            partial = cli("supervisor", "status", "--venue", "hyperliquid")["positions"][0]
            assert partial["pending_adds"][0]["status"] == "SUBMITTED"
            assert float(partial["pending_adds"][0]["filled"]) == 0.2
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
            complete = cli("supervisor", "status", "--venue", "hyperliquid")["positions"][0]
            assert complete["pending_adds"] == []
        print(json.dumps({"result": "passed", "network": "forbidden", "gateway": "stub",
            "sqlite": "temporary, reopened by every CLI invocation", "commands": commands,
            "total_balance": "1000", "operating_capital": preview["sizing"]["operating_capital"],
            "add_attempts": 1, "tranche_filled": "0.5", "remaining": "1.5",
            "pending_add_statuses": ["QUEUED", "UNKNOWN", "SUBMITTED", "none after terminal fill"],
            "sl_coverage": status["covered_size"], "native_ts_coverage": status["trailing_covered_size"],
            "state": status["state"], "lifecycle": lifecycle_smoke()}, indent=2))


def lifecycle_smoke():
    """Use the real CLI for expiry cancellation and terminal-owner repair."""
    from tests.test_add_lifecycle import AddLifecycleTests

    results = []
    for scenario in ("cancel-after-historical-entry", "terminal-unsent-retirement"):
        case = AddLifecycleTests()
        case.setUp()
        try:
            if scenario == "cancel-after-historical-entry": case.historical_entry_cancel()
            root = Path(case.tmp.name)
            path = root/"add.json"
            path.write_text(json.dumps(case.plan))
            clock, commands = [NOW+5], []

            def cli(*argv):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(["--db", str(case.store.path), *argv])
                assert code == 0, output.getvalue()
                commands.append("kis-hl --db TEMP/state.sqlite " + " ".join(str(a).replace(str(root), "TEMP") for a in argv))
                return json.loads(output.getvalue())

            def tick(now):
                clock[0] = now
                return cli("supervisor", "run", "--venue", "hyperliquid", "--live", "--once")["positions"][0]

            with patch("kis_hl.cli.load_env_file"), \
                 patch("kis_hl.operations_cli.time.time", side_effect=lambda: clock[0]/1000), \
                 patch("kis_hl.operations_cli.scope_client", return_value=(SimpleNamespace(key="scope"), SimpleNamespace(config=None))), \
                 patch("kis_hl.operations_cli.HyperliquidTradingClient"), \
                 patch("kis_hl.managed_gateways.ManagedHyperliquidGateway", return_value=case.g), \
                 patch.object(socket, "socket", side_effect=AssertionError("Offline smoke forbids network")):
                queued = cli("signal", "execute", "--id", "add-once", "--input", str(path), "--manual", "--live")
                if scenario == "cancel-after-historical-entry":
                    tick(NOW+10)
                    add = next(a for a in case.g.sent if a["kind"] == "add")
                    case.g.cancel = lambda *args: {"status": "submitted"}
                    expiry = case.plan["expires_ms"]
                    tick(expiry)
                    status = cli("order", "status", "--id", case.row["id"])
                    target_cancels = [a for a in status["attempts"] if a["kind"] == "cancel" and a.get("target_id") == add["id"]]
                    assert len(target_cancels) == 1
                    target = next(a for a in status["attempts"] if a["id"] == add["id"])
                    assert target["cancel_started_ms"] == expiry
                    case.g.fill(add, "0.2", terminal=False)
                    tick(expiry+1)
                    pending = tick(expiry+2)
                    assert float(pending["covered_size"]) == 1.2
                    case.g.orders[add["id"]]["status"] = "canceled"
                    complete = tick(expiry+3)
                    assert complete["state"] == "PROTECTED" and not complete["pending_adds"]
                    assert len(case.cancels(add["id"])) == 1
                    results.append(dict(scenario=scenario, result="passed", target_cancel_attempts=1,
                        remaining="1.2", sl_coverage=complete["covered_size"], state=complete["state"], commands=commands))
                else:
                    cli("order", "exit", "--id", case.row["id"])
                    tick(NOW+10)
                    exit_attempt = next(a for a in case.g.sent if a["kind"] == "exit")
                    case.g.size = "0"
                    case.g.orders[exit_attempt["id"]].update(status="filled", size="0")
                    for now in (NOW+11, NOW+12, NOW+13): complete = tick(now)
                    assert complete["state"] == "CLOSED" and not complete["pending_adds"]
                    status = cli("order", "status", "--id", case.row["id"])
                    assert status["tranches"][0]["status"] == "CANCELED"
                    case.store.save_tranche(queued)  # Older DB: closed owner, unsent queue.
                    before = cli("supervisor", "status", "--venue", "hyperliquid")["positions"][0]
                    assert before["pending_adds"][0]["status"] == "QUEUED"
                    repaired = tick(NOW+14)
                    assert repaired["state"] == "CLOSED" and not repaired["pending_adds"]
                    assert not any(a["kind"] == "add" for a in case.g.sent)
                    results.append(dict(scenario=scenario, result="passed", add_attempts=0,
                        legacy_queue_repaired=True, state=repaired["state"], commands=commands))
        finally:
            case.doCleanups()
    return results


if __name__ == "__main__":
    run()
