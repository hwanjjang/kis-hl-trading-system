"""Offline smoke for issue 28: CLI take profit through the real Hyperliquid gateway.

The owner is protected with the unit-test stub, then handed to the CLI supervisor
running the real ManagedHyperliquidGateway over an in-memory exchange. No network.
"""
import contextlib
import io
import json
from decimal import Decimal
from pathlib import Path
import socket
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kis_hl.cli import main
from kis_hl.journal_sync import Scope
from kis_hl.managed_execution import ExecutionStore, Supervisor
from tests.test_managed_execution import plan
from tests.test_take_profit import TakeProfitGateway

ACCOUNT = "0xsmoke"
NETWORK = "https://api.hyperliquid-testnet.xyz"


class FakeHyperliquid:
    """Info and trading client for one BTC position; IOC sells fill against `ioc_fill`."""

    def __init__(self):
        self.config = SimpleNamespace(base_url=NETWORK, account_address=ACCOUNT)
        self.size, self.orders, self.fills, self.placed = Decimal(0), {}, [], []
        self.next_oid, self.next_tid, self.ioc_fill = 100, 1, None

    def now(self):
        return int(time.time() * 1000)

    def add_order(self, *, cloid, side, size, reduce_only, stop=False, trigger="0", status="open"):
        oid = self.next_oid
        self.next_oid += 1
        self.orders[str(oid)] = {"status": status, "order": {
            "oid": oid, "cloid": cloid, "coin": "BTC", "side": side, "sz": str(size),
            "origSz": str(size), "limitPx": "100", "reduceOnly": reduce_only, "isTrigger": stop,
            "orderType": "Stop Market" if stop else "Limit", "triggerPx": trigger,
            "isPositionTpsl": False}}
        return oid

    def fill(self, oid, quantity, price="100"):
        order = self.orders[str(oid)]["order"]
        quantity = Decimal(quantity)
        self.fills.append({"tid": self.next_tid, "coin": "BTC", "side": order["side"], "sz": str(quantity),
                           "px": price, "time": self.now(), "oid": oid, "startPosition": str(self.size)})
        self.next_tid += 1
        self.size += quantity if order["side"] == "B" else -quantity
        order["sz"] = str(Decimal(order["sz"]) - quantity)

    # Info surface used by snapshot().
    def meta_and_asset_ctxs(self, dex=None):
        return [{"universe": [{"name": "BTC", "szDecimals": 2}]}, []]

    def order_status(self, *, oid):
        found = self.orders.get(str(oid)) or next(
            (o for o in self.orders.values() if o["order"]["cloid"] == oid), None)
        if found is None:
            return {"status": "unknownOid"}
        return {"status": "order", "order": {"status": found["status"], "order": dict(found["order"])}}

    def user_fills_by_time(self, *, start_time_ms, end_time_ms):
        return [f for f in self.fills if start_time_ms <= f["time"] <= end_time_ms]

    def frontend_open_orders(self, dex=None):
        return [o["order"] for o in self.orders.values() if o["status"] == "open"]

    def clearinghouse_state(self, dex=None):
        position = [{"position": {"coin": "BTC", "szi": str(self.size), "entryPx": "100",
                                  "positionValue": str(self.size * 100)}}] if self.size else []
        return {"assetPositions": position, "withdrawable": "1000"}

    def l2_book(self, coin):
        return {"time": self.now(), "levels": [[{"px": "100", "sz": "100"}], [{"px": "100.1", "sz": "100"}]]}

    # Trading surface used by submit()/cancel().
    def place_order(self, **kw):
        self.placed.append(kw)
        assert kw["reduce_only"] and kw["side"] == "sell" and kw["tif"] == "Ioc", kw
        oid = self.add_order(cloid=kw["cloid"], side="A", size=kw["size"], reduce_only=True)
        quantity = min(Decimal(kw["size"]), self.size, self.ioc_fill or Decimal(kw["size"]))
        if quantity > 0:
            self.fill(oid, quantity, str(kw["price"]))
        self.orders[str(oid)]["status"] = "filled" if quantity == Decimal(kw["size"]) else "canceled"
        return SimpleNamespace(status="submitted", response={"oid": oid})

    def cancel_order(self, *, symbol, oid, dry_run):
        self.orders[str(oid)]["status"] = "canceled"
        return SimpleNamespace(status="submitted")


def protected_owner(store, scope_key, exchange):
    """Protect a 10 BTC owner with the unit stub, then mirror it on the fake exchange."""
    stub = TakeProfitGateway()
    stub.network, stub.account, stub.scope = NETWORK, ACCOUNT, scope_key
    stub.preflight = (lambda base: lambda p, now: {**base(p, now), "available_notional": "3000"})(stub.preflight)
    p = plan()
    p.update(quantity="10", max_notional="2000", max_loss="50", max_portfolio_notional="2000",
             max_correlated_notional="2000", max_quote_age_ms=5000, exit_deadline_ms=600000,
             expires_ms=exchange.now() + 3600000)
    start = exchange.now() - 1000
    row = store.enqueue(scope_key, p, live=True, now_ms=start)
    worker = Supervisor(store, stub, live=True)
    worker.step(row["id"], start + 10)
    stub.size = stub.filled = "10"
    stub.orders[stub.sent[0]["id"]]["status"] = "filled"
    worker.step(row["id"], start + 20)
    assert worker.step(row["id"], start + 30)["state"] == "PROTECTED"
    for attempt in store.attempts(row["id"]):
        if attempt["kind"] == "entry":
            oid = exchange.add_order(cloid=attempt["id"], side="B", size="10", reduce_only=False, status="filled")
            exchange.fill(oid, "10")
        else:
            oid = exchange.add_order(cloid=attempt["id"], side="A", size=attempt["quantity"],
                                     reduce_only=True, stop=True, trigger=attempt["trigger_price"])
        store.update_attempt(attempt, order_id=str(oid))
    return row["id"]


def run():
    with tempfile.TemporaryDirectory(prefix="take-profit-smoke-") as directory:
        root = Path(directory)
        db = root / "state.sqlite"
        exchange = FakeHyperliquid()
        scope = Scope("hyperliquid", "testnet", ACCOUNT)
        store = ExecutionStore(db)
        pid = protected_owner(store, scope.key, exchange)
        commands = []

        def cli(*argv, expect=0):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["--db", str(db), *argv])
            assert code == expect, (argv, code, out.getvalue(), err.getvalue())
            commands.append("kis-hl --db TEMP/state.sqlite " + " ".join(argv))
            return json.loads(out.getvalue()) if code == 0 else err.getvalue()

        def supervise():
            return next(r for r in cli("supervisor", "run", "--venue", "hyperliquid", "--live", "--once")["positions"]
                        if r["id"] == pid)

        with patch("kis_hl.cli.load_env_file"), \
             patch("kis_hl.operations_cli.scope_client", return_value=(scope, exchange)), \
             patch("kis_hl.operations_cli.HyperliquidTradingClient", return_value=exchange), \
             patch.object(socket, "socket", side_effect=AssertionError("Offline smoke forbids network")):
            owner = supervise()
            assert owner["state"] == "PROTECTED", owner["reason"]
            stop_oid = next(a["order_id"] for a in store.attempts(pid) if a["kind"] == "stop")

            # S1/S2: request once, partial IOC fill, retry only the remainder, verify the residual.
            request = ("order", "take-profit", "--id", pid, "--decision-id", "top-2026-10-04",
                       "--rationale", "Judged weekly top")
            assert cli(*request)["take_profit"]["status"] == "REQUESTED"
            assert cli(*request)["take_profit"]["status"] == "REQUESTED"
            assert exchange.placed == []
            exchange.ioc_fill = Decimal(2)
            first = supervise()
            assert first["take_profit"]["status"] == "EXECUTING", first
            assert first["take_profit"]["target_quantity"] == "5"
            exchange.ioc_fill = None
            second = supervise()
            done = supervise()
            assert [str(o["size"]) for o in exchange.placed] == ["5", "3"], exchange.placed
            assert done["take_profit"]["status"] == "COMPLETED", done
            assert done["take_profit"]["residual_size"] == "5" and exchange.size == Decimal(5)
            assert done["state"] == "PROTECTED" and done["covered_size"] == "5", done
            assert exchange.orders[stop_oid]["status"] == "open"
            assert len([a for a in store.attempts(pid) if a["kind"] == "stop"]) == 1
            supervise()
            assert len(exchange.placed) == 2
            reused = cli(*request, expect=1)
            assert "already used" in reused

            # S2: a second decision halves the current residual without inheriting earlier fills.
            cli("order", "take-profit", "--id", pid, "--decision-id", "top-2", "--rationale", "Second top")
            second_decision = supervise()["take_profit"]
            assert second_decision["status"] == "EXECUTING" and second_decision["target_quantity"] == "2.5"
            second_done = supervise()["take_profit"]
            assert second_done["status"] == "COMPLETED" and second_done["residual_size"] == "2.5", second_done
            assert [str(o["size"]) for o in exchange.placed] == ["5", "3", "2.5"]

            # S3: the fixed SL fills before the next decision is sized; no TP or new protection.
            cli("order", "take-profit", "--id", pid, "--decision-id", "top-3", "--rationale", "Third top")
            exchange.fill(int(stop_oid), "2.5", "95")
            exchange.orders[stop_oid]["status"] = "filled"
            superseded = supervise()
            assert superseded["take_profit"]["status"] == "SUPERSEDED", superseded
            closed = supervise()
            assert closed["state"] == "CLOSED", closed
            assert len(exchange.placed) == 3 and exchange.size == 0
            assert len([a for a in store.attempts(pid) if a["kind"] == "stop"]) == 1
            status = cli("order", "status", "--id", pid)
        return {"ok": True, "commands": commands,
                "take_profit_orders": [{k: str(o[k]) for k in ("side", "size", "reduce_only", "tif")}
                                       for o in exchange.placed],
                "first_decision": done["take_profit"], "second_decision": second_done,
                "final_state": status["state"],
                "final_take_profit": status["take_profit"]}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
