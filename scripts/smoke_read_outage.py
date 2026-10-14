"""Offline smoke for issue 59: warning-only read outages through real CLI processes.

A scripted in-process supervisor writes a temporary SQLite state; separate CLI
processes list/acknowledge notifications, read diagnostics, refuse and withdraw a
legacy latch. No network, credentials, signed action or --live flag is used.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kis_hl.journal_sync import Scope  # noqa: E402
from kis_hl.managed_execution import ExecutionStore, Supervisor  # noqa: E402

ADDRESS = "0x" + "1" * 40
SCOPE = Scope("hyperliquid", "testnet", ADDRESS)
PLAN = dict(
    intent_id="smoke-read-outage", instrument="hl:BTC", signal_instrument="hl:BTC", strategy="smoke",
    strategy_version="1", quantity="1", limit_price="100", atr="2", atr_multiple="2", max_notional="101",
    max_loss="5", max_quote_age_ms=1000, protection_grace_ms=5000, max_exit_attempts=3,
    exit_deadline_ms=60000, slippage="0.01", allow_local_sl=True, expires_ms=10_000_000,
    exit_reprice_ms=5000, max_portfolio_notional="1000", max_correlated_notional="500",
    max_spread_bps="20", max_entry_deviation_bps="100", trailing_provider="local",
)


class ScriptedGateway:
    """Native-SL venue double: records every send; reads can be made to fail."""

    network, account, scope = "smoke", "smoke-account", SCOPE.key
    native_sl, native_trailing = True, False

    def __init__(self):
        self.sent, self.orders, self.size, self.failing = [], {}, "0", False

    def preflight(self, p, now):
        return dict(price="100", ask="100.1", entry_order_type="market", time_ms=now,
                    available_notional="1000", position="0", open_orders=[], eligible=True,
                    session_open=True, quantity_step="0.01", price_step="0.01", trailing_price_step="0.01",
                    portfolio_notional="0", correlated_notional="0", atr="2",
                    atr_source={"instrument": p["instrument"], "basis": "smoke"})

    def snapshot(self, row, attempts, now):
        if self.failing:
            from kis_hl.hyperliquid.client import TransientInfoError
            raise TransientInfoError("Hyperliquid info temporarily unavailable: HTTP 502 token=SMOKE-SECRET",
                                     kind="http", http_status=502)
        return dict(size=self.size, entry_price="100", entry_filled=self.size, price="100", time_ms=now,
                    sellable=self.size, session_open=True, foreign_add=False, orders=dict(self.orders),
                    consistent=True, price_step="0.01", trailing_price_step="0.01", quantity_step="0.01")

    def submit(self, row, attempt):
        self.sent.append(attempt["kind"])
        self.orders[attempt["id"]] = dict(status="open", size=attempt["quantity"], kind=attempt["kind"],
                                          trigger_price=attempt.get("trigger_price"), side="sell",
                                          reduce_only=True, trigger_type="sl")
        return {"status": "submitted", "order_id": attempt["id"]}

    def cancel(self, row, attempt):
        raise AssertionError("No cancellation is expected in this smoke")


def main():
    env = dict(os.environ, HYPERLIQUID_WALLETADDRESS=ADDRESS, HYPERLIQUID_PRIVATEKEY="",
               HYPERLIQUID_KEY_PROFILE="default", HYPERLIQUID_BASE_URL="https://api.hyperliquid-testnet.xyz")
    evidence = []
    with tempfile.TemporaryDirectory(prefix="read-outage-smoke-") as temp:
        db = Path(temp) / "state.sqlite"

        def cli(*args, expect=0):
            run = subprocess.run([sys.executable, "-m", "kis_hl.cli", "--db", str(db), *args], cwd=ROOT,
                                 env=env, capture_output=True, text=True, timeout=60)
            assert run.returncode == expect, (args, run.returncode, run.stderr)
            assert "SMOKE-SECRET" not in run.stdout + run.stderr and ADDRESS not in run.stdout
            evidence.append({"args": list(args), "exit": run.returncode})
            return json.loads(run.stdout) if run.stdout.strip() else json.loads(run.stderr.strip().splitlines()[-1])

        gateway = ScriptedGateway()
        store = ExecutionStore(db)
        pid = store.enqueue(SCOPE.key, PLAN, live=True, now_ms=1)["id"]
        worker = Supervisor(store, gateway, live=True)
        worker.step(pid, 10)
        gateway.size = "1"
        gateway.orders[next(iter(gateway.orders))]["status"] = "filled"
        worker.step(pid, 20)
        assert worker.step(pid, 30)["state"] == "PROTECTED" and gateway.sent == ["entry", "stop"]

        # S1/S3: outage longer than grace + deadline, polled every second, restart midway.
        gateway.failing = True
        for now in range(1_000, 70_000, 1_000):
            if now == 35_000:
                worker = Supervisor(ExecutionStore(db), gateway, live=True)
            row = worker.step(pid, now)
            assert row["state"] == "DEGRADED" and row["exit_requested_ms"] is None, row["state"]
        listed = cli("supervisor", "notifications", "--venue", "hyperliquid")["notifications"]
        assert [n["kind"] for n in listed] == ["read_outage"], listed
        assert "Warning only: no exit requested" in listed[0]["message"]
        failed = cli("supervisor", "notification-result", "--venue", "hyperliquid",
                     "--notification-id", str(listed[0]["id"]), "--result", "failed")
        assert failed["delivery_attempts"] == 1 and failed["delivered_ms"] is None
        assert len(cli("supervisor", "notifications", "--venue", "hyperliquid")["notifications"]) == 1
        cli("supervisor", "notification-result", "--venue", "hyperliquid",
            "--notification-id", str(listed[0]["id"]), "--result", "delivered")
        status = cli("order", "status", "--id", pid)
        diag = status["diagnostics"]
        assert diag["read_health"]["status"] == "unavailable"
        assert diag["read_health"]["error"] == {"category": "TransientInfoError", "kind": "http", "http_status": 502}
        assert diag["supervision"]["local_supervision"] == "paused" and status["exit_requested_ms"] is None

        gateway.failing = False
        assert worker.step(pid, 70_000)["state"] == "PROTECTED" and gateway.sent == ["entry", "stop"]
        recovered = cli("supervisor", "notifications", "--venue", "hyperliquid")["notifications"]
        assert [n["kind"] for n in recovered] == ["read_recovered"] and "PROTECTED" in recovered[0]["message"]

        # S4/S5: a legacy latch written by the old policy, now past its deadline.
        row = store.get(pid)
        row.update(exit_requested_ms=80_000, state="INTERVENTION",
                   reason="Account snapshot unavailable (TransientInfoError); consecutive failures=3; awaiting readback")
        store.save(row, 80_000)
        row = store.get(pid)
        row["state"] = "EXITING"
        store.save(row, 80_001)
        blocked = worker.step(pid, 141_000)
        assert blocked["reason"] == "Exit attempt or deadline budget exhausted", blocked["reason"]
        refusal = cli("order", "recover", "--id", pid, expect=1)["error"]
        assert "deadline" in refusal and f"--exit-requested-ms 80000" in refusal, refusal
        diag = cli("order", "status", "--id", pid)["diagnostics"]
        assert diag["exit"]["provenance"]["kind"] == "read_outage_latch" and diag["exit"]["deadline_exhausted"]
        assert diag["intervention"]["current_blocker"]["reason"] == "Exit attempt or deadline budget exhausted"
        cli("order", "withdraw-read-exit", "--id", pid, "--exit-requested-ms", "80001", expect=1)
        withdrawn = cli("order", "withdraw-read-exit", "--id", pid, "--exit-requested-ms", "80000")
        assert withdrawn["state"] == "INTERVENTION" and withdrawn["exit_requested_ms"] is None
        assert cli("order", "recover", "--id", pid)["state"] == "ENTERING"
        final = worker.step(pid, 142_000)
        assert final["state"] == "PROTECTED" and gateway.sent == ["entry", "stop"], (final["state"], gateway.sent)
    print(json.dumps({"ok": True, "cli_calls": evidence, "orders_sent": gateway.sent}, indent=2))


if __name__ == "__main__":
    main()
