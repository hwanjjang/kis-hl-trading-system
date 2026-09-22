"""Offline CLI, real managed lifecycle and SDK signing smoke; no network requests."""
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from eth_account import Account
from hyperliquid.utils.signing import action_hash, construct_phantom_agent, l1_payload
from eth_account.messages import encode_typed_data
from kis_hl.hyperliquid.trailing import send_trailing_action
from kis_hl.managed_execution import ExecutionStore, Supervisor
from kis_hl.managed_gateways import ManagedHyperliquidGateway
from tests.test_managed_execution import plan


class ReplayExchange:
    """Deterministic exchange boundary; gateway, parser, supervisor and SQLite are real."""

    def __init__(self, store, *, reject_trailing):
        self.store = store
        self.reject_trailing = reject_trailing
        self.config = SimpleNamespace(base_url="https://api.hyperliquid-testnet.xyz",
                                      account_address="offline-native-replay")
        self.now = 1_800_000_000_000
        self.orders, self.fills, self.sent = {}, [], []
        self.size = "0"
        self.reads = set()

    def meta_and_asset_ctxs(self, *, dex):
        self.reads.add("metadata")
        return [{"collateralToken": 0, "universe": [{"name": "BTC", "szDecimals": 5}]}, []]

    def _require_recent_verification(self, resolved):
        assert resolved.coin == "BTC" and resolved.dex is None

    def clearinghouse_state(self, *, dex):
        positions = [] if dex or self.size == "0" else [{"position": {
            "coin": "BTC", "szi": self.size, "entryPx": "100000", "positionValue": "100000"}}]
        return {"assetPositions": positions, "withdrawable": "1000000"}

    def l2_book(self, symbol):
        assert symbol == "BTC"
        return {"time": self.now, "levels": [[{"px": "100000"}], [{"px": "100000.1"}]]}

    def candle_snapshot(self, symbol, *, dex, interval, start_time_ms, end_time_ms):
        assert symbol == "BTC" and dex is None and interval == "1d"
        self.reads.add("closed_daily_bars")
        day = 86_400_000
        today = self.now // day * day
        return [{"t": t, "T": t + day - 1, "s": "BTC", "h": "100001",
                 "l": "99999", "c": "100000"}
                for t in range(today - 11 * day, today, day)]

    def frontend_open_orders(self, *, dex):
        return [] if dex else [r["order"] for r in self.orders.values() if r["status"] == "open"]

    def order_status(self, *, oid):
        self.reads.add("order_status")
        return {"status": "order", "order": self.orders[int(oid)]}

    def user_fills_by_time(self, *, start_time_ms, end_time_ms):
        self.reads.add("fills")
        return [f for f in self.fills if start_time_ms <= f["time"] <= end_time_ms]

    def _accept(self, kind, order):
        oid = 100 + len(self.orders)
        order.update(oid=oid, coin="BTC")
        self.orders[oid] = {"status": "open", "order": order}
        self.sent.append(kind)
        return SimpleNamespace(status="submitted", response={"status": "ok", "response": {
            "type": "order", "data": {"statuses": [{"resting": {"oid": oid}}]}}})

    def place_order(self, **request):
        assert request["dry_run"] is False
        kind = "entry" if request["side"] == "buy" else (
            "stop" if request["order_type"] == "stop-market" else "exit")
        if kind == "entry":
            # Read the durable value at the actual gateway transmission boundary.
            assert self.store.get(self.position_id)["native_trailing_distance"] == "4"
        if kind == "exit":
            assert request["reduce_only"] is True and request["tif"] == "Ioc"
        return self._accept(kind, {"side": "B" if kind == "entry" else "A",
            "sz": str(request["size"]), "limitPx": str(request["price"]),
            "cloid": request["cloid"], "reduceOnly": request["reduce_only"],
            "isTrigger": kind == "stop", "orderType": "Stop Market" if kind == "stop" else "Limit",
            "triggerPx": str(request["trigger_price"] or "0")})

    def place_trailing_stop_order(self, **request):
        assert request["retracement"] == Decimal("4")
        assert request["side"] == "sell" and request["dry_run"] is False
        if self.reject_trailing:
            self.sent.append("trailing")
            return SimpleNamespace(status="rejected", response={"status": "err", "response": "fixture rejection"})
        return self._accept("trailing", {"side": "A", "sz": str(request["size"]),
            "reduceOnly": True, "isTrigger": True, "orderType": "Trailing Stop Market",
            "triggerCondition": "retracement 4, best waiting", "triggerPx": "0"})

    def fill_entry(self):
        self.orders[100]["status"] = "filled"
        self.size = "1"
        self.fills.append({"time": self.now, "tid": 1, "oid": 100, "coin": "BTC", "side": "B", "sz": "1"})


def replay_managed_lifecycle(root, *, reject_trailing):
    path = root / ("rejected.sqlite" if reject_trailing else "waiting.sqlite")
    store = ExecutionStore(path)
    exchange = ReplayExchange(store, reject_trailing=reject_trailing)
    gateway = ManagedHyperliquidGateway(exchange, exchange)
    p = plan(trailing_provider="native")
    p.update(limit_price="100000", max_notional="100001", max_portfolio_notional="1000000",
             max_correlated_notional="500000", expires_ms=exchange.now + 100000)
    row = store.enqueue(gateway.scope, p, live=True, now_ms=exchange.now)
    exchange.position_id = row["id"]
    worker = Supervisor(store, gateway, live=True)
    start = exchange.now

    def step(offset, *, restart=False):
        nonlocal store, worker
        exchange.now = start + offset
        if restart:
            store = ExecutionStore(path)
            worker = Supervisor(store, ManagedHyperliquidGateway(exchange, exchange), live=True)
        # Freeze only wall time; all snapshots, persisted state and readback parsing run normally.
        with patch("kis_hl.managed_gateways.time.time", return_value=exchange.now / 1000):
            return worker.step(row["id"], exchange.now)

    assert step(1)["state"] == "ENTERING"
    assert exchange.sent == ["entry"]
    exchange.now = start + 2
    exchange.fill_entry()
    step(3)
    assert exchange.sent == ["entry", "stop"]
    step(4)
    assert exchange.sent == ["entry", "stop", "trailing"]
    for offset in (5, 6000, 7000):
        observed = step(offset, restart=True)
        assert observed["state"] == ("INTERVENTION" if reject_trailing else "PROTECTING"), observed
        assert Decimal(observed["covered_size"]) == 1
        assert Decimal(observed["trailing_covered_size"]) == 0
        assert observed["exit_requested_ms"] is None
        assert exchange.orders[101]["status"] == "open"
        assert exchange.sent == ["entry", "stop", "trailing"]
    if not reject_trailing:
        exchange.orders[102]["order"]["triggerCondition"] = "retracement 4, best 100004"
        observed = step(7001, restart=True)
        assert observed["state"] == "PROTECTED", observed
        assert Decimal(observed["trailing_covered_size"]) == 1
    exchange.orders[101]["status"] = "canceled"
    observed = step(7002, restart=True)
    assert exchange.sent == ["entry", "stop", "trailing", "exit"], observed
    assert observed["exit_requested_ms"] is not None
    assert exchange.reads == {"metadata", "closed_daily_bars", "order_status", "fills"}
    assert [a["kind"] for a in store.attempts(row["id"])] == exchange.sent
    return True


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        p = plan(trailing_provider="native")
        p["expires_ms"] = 9999999999999
        source = root / "plan.json"
        source.write_text(json.dumps(p))
        command = [sys.executable, "-m", "kis_hl.cli", "--db", str(root/"state.sqlite"), "order", "preview", "--input", str(source)]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        preview = json.loads(result.stdout)
        assert preview["dry_run"] is True
        assert preview["plan"]["trailing_provider"] == "native"
        assert preview["capabilities"]["native_trailing"] == "documented_requires_readback"
        store = ExecutionStore(root/"state.sqlite")
        row = store.enqueue("offline-smoke", p, now_ms=1)
        gateway = SimpleNamespace(scope="offline-smoke", network="offline", account="offline-smoke")
        observed = Supervisor(store, gateway).step(row["id"], 2)
        assert observed["state"] == "PREVIEWED"
        assert store.attempts(row["id"]) == []

        # Generate a throwaway key in memory; recover its signature with the actual SDK.
        wallet = Account.create()
        captured = []
        def capture(path, payload):
            assert path == "/exchange"
            captured.append(payload)
            return {"status": "ok", "response": {"type": "default"}}
        exchange = SimpleNamespace(wallet=wallet, vault_address=None,
            base_url="https://api.hyperliquid-testnet.xyz", post=capture)
        action = {"type": "trailingStop", "asset": 0, "isBuy": False, "sz": "1",
                  "reduceOnly": True, "retracement": {"px": "4"}, "activationPx": None}
        nonce, expiry = 1000000000000, 1000000010000
        send_trailing_action(exchange, action, nonce, expiry)
        sent = captured[0]
        typed = l1_payload(construct_phantom_agent(action_hash(action, None, nonce, expiry), False))
        sig = sent["signature"]
        recovered = Account.recover_message(encode_typed_data(full_message=typed),
            vrs=(sig["v"], int(sig["r"], 16), int(sig["s"], 16)))
        assert recovered == wallet.address
        assert sent["expiresAfter"] == expiry and sent["action"] == action
        waiting = replay_managed_lifecycle(root, reject_trailing=False)
        rejected = replay_managed_lifecycle(root, reject_trailing=True)
        print(json.dumps({"status": "passed", "cli_preview": True, "sqlite_paper_no_attempts": True,
            "sdk_signature_recovered": True, "real_gateway_waiting_restart_active": waiting,
            "real_gateway_rejection_retains_stop": rejected, "fixed_stop_loss_exits": True,
            "distance_persisted_before_entry": "4 at price 100000 / szDecimals 5 / ATR 2",
            "network_requests": 0, "live_exchange_verified": False}))


if __name__ == "__main__":
    main()
