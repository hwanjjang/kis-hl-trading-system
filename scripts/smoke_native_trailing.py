"""Offline CLI, SQLite and real SDK signing smoke; never sends a network request."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from eth_account import Account
from hyperliquid.utils.signing import action_hash, construct_phantom_agent, l1_payload
from eth_account.messages import encode_typed_data
from kis_hl.hyperliquid.trailing import send_trailing_action
from kis_hl.managed_execution import ExecutionStore, Supervisor
from tests.test_managed_execution import plan


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
        print(json.dumps({"status": "passed", "cli_preview": True, "sqlite_paper_no_attempts": True,
            "sdk_signature_recovered": True, "network_requests": 0, "live_exchange_verified": False}))


if __name__ == "__main__":
    main()
