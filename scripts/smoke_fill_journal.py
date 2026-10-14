"""Offline smoke for issue 58: fill-triggered journal sync through real CLI processes.

An in-process scripted supervisor observes a fill and records a sync request in a
temporary SQLite state. Separate CLI processes then run `market collect --once`,
list and acknowledge the journal notification as Hermes would, journal a manual
(unowned) fill through a fallback account job, sync a KIS DAY statement, report
`data journal-status` and enqueue the daily summary. Exchange reads come from a local fills file; sockets are
blocked and no credential, signed action or --live flag is used.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kis_hl.journal_sync import Scope  # noqa: E402
from kis_hl.managed_execution import ExecutionStore, Supervisor  # noqa: E402

ADDRESS = "0x" + "2" * 40
SCOPE = Scope("hyperliquid", "testnet", ADDRESS)
PLAN = dict(
    intent_id="smoke-fill-journal", instrument="hl:BTC", signal_instrument="hl:BTC", strategy="smoke",
    strategy_version="1", quantity="1", limit_price="100", atr="2", atr_multiple="2", max_notional="101",
    max_loss="5", max_quote_age_ms=1000, protection_grace_ms=5000, max_exit_attempts=3,
    exit_deadline_ms=60000, slippage="0.01", allow_local_sl=True, expires_ms=10**13,
    exit_reprice_ms=5000, max_portfolio_notional="1000", max_correlated_notional="500",
    max_spread_bps="20", max_entry_deviation_bps="100", trailing_provider="local",
)

# Runs inside each CLI process: block sockets, read fills from FILLS, then call the real CLI.
BOOTSTRAP = r"""
import json, os, socket, sys
from unittest.mock import patch
def blocked(*a, **k):
    raise OSError("network disabled in smoke")
socket.socket = blocked
socket.create_connection = blocked
sys.path.insert(0, os.environ["SMOKE_ROOT"])
from kis_hl.journal_sync import Scope
class Fills:
    last_raw_body = None
    def _rows(self):
        if os.environ.get("SMOKE_FAIL"):
            raise TimeoutError("smoke exchange timeout")
        return json.load(open(os.environ["SMOKE_FILLS"]))
    def user_fills_by_time(self, *, start_time_ms, end_time_ms):
        return [f for f in self._rows() if start_time_ms <= f["time"] <= end_time_ms]
    def user_funding(self, **kwargs):
        return []
    def user_fills(self):
        return self._rows()
    def clearinghouse_state(self, dex=None):
        return {"assetPositions": []}
class Statements:
    # KIS overseas DAY statement for one execution on SMOKE_KIS_DATE (AMEX only).
    def account_pages(self, kind, **kwargs):
        rows = []
        if kind == "overseas_transactions" and kwargs["exchange"] == "AMEX":
            rows = [dict(trad_dt=os.environ["SMOKE_KIS_DATE"], pdno="SPY", sll_buy_dvsn_cd="02", crcy_cd="USD",
                         tr_frcr_amt2="500", dmst_frcr_fee1="1", frcr_fee1="0", frcr_excc_amt_1="501", ccld_qty="1")]
        return dict(output1=rows, output2=[])
if os.environ.get("SMOKE_VENUE") == "kis":
    scope, client = Scope("kis", "live", "smoke-kis"), Statements()
else:
    scope, client = Scope("hyperliquid", "testnet", os.environ["SMOKE_ACCOUNT"]), Fills()
from kis_hl.cli import main
with patch("kis_hl.cli.load_env_file"), patch("kis_hl.operations_cli.scope_client", return_value=(scope, client)):
    raise SystemExit(main(sys.argv[1:]))
"""


class ScriptedGateway:
    network, account, scope = "smoke", ADDRESS, SCOPE.key
    native_sl, native_trailing = True, False

    def __init__(self):
        self.sent, self.orders, self.size, self.filled = [], {}, "0", "0"

    def preflight(self, p, now):
        return dict(price="100", ask="100.1", entry_order_type="market", time_ms=now,
                    available_notional="1000", position="0", open_orders=[], eligible=True,
                    session_open=True, quantity_step="0.01", price_step="0.01", trailing_price_step="0.01",
                    portfolio_notional="0", correlated_notional="0", atr="2",
                    atr_source={"instrument": p["instrument"], "basis": "smoke"})

    def snapshot(self, row, attempts, now):
        return dict(size=self.size, entry_price="100", entry_filled=self.filled, price="100", time_ms=now,
                    sellable=self.size, session_open=True, foreign_add=False, orders=dict(self.orders),
                    consistent=True, price_step="0.01", trailing_price_step="0.01", quantity_step="0.01")

    def submit(self, row, attempt):
        self.sent.append(attempt["kind"])
        self.orders[attempt["id"]] = dict(status="open", size=attempt["quantity"], kind=attempt["kind"],
                                          trigger_price=attempt.get("trigger_price"), side="sell",
                                          reduce_only=True, trigger_type="sl")
        return {"status": "submitted", "order_id": attempt["id"]}

    def cancel(self, row, attempt):
        self.orders[attempt["target_id"]]["status"] = "canceled"
        return {"status": "submitted"}


def fill(tid, before, side, at):
    return dict(coin="BTC", tid=tid, time=at, side=side, sz="1", px="100", fee="0.05", feeToken="USDC",
                oid=tid, startPosition=before, closedPnl="0")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        db, fills_path = tmp / "state.sqlite", tmp / "fills.json"
        env = {**os.environ, "SMOKE_ROOT": str(ROOT), "SMOKE_FILLS": str(fills_path), "SMOKE_ACCOUNT": ADDRESS}
        env.pop("SMOKE_FAIL", None)

        def cli(*args, fail=False, venue="hyperliquid"):
            run_env = {**env, "SMOKE_VENUE": venue, **({"SMOKE_FAIL": "1"} if fail else {})}
            done = subprocess.run([sys.executable, "-c", BOOTSTRAP, "--db", str(db), *args], cwd=tmp,
                                  env=run_env, capture_output=True, text=True, timeout=120)
            if done.returncode:
                raise SystemExit(f"CLI {' '.join(args)} failed: {done.stderr[-800:]}")
            return json.loads(done.stdout)

        now = int(time.time() * 1000)
        cli("data", "migrate", "--apply")
        store = ExecutionStore(db)
        gateway = ScriptedGateway()
        worker = Supervisor(store, gateway, live=True)
        pid = store.enqueue(SCOPE.key, PLAN, live=True, now_ms=now - 5000)["id"]
        worker.step(pid, now - 4000)
        gateway.size = gateway.filled = "1"
        gateway.orders[next(iter(gateway.orders))]["status"] = "filled"
        worker.step(pid, now - 3000)
        requests = [r for r in __import__("kis_hl.fill_journal", fromlist=["x"]).sync_requests(db)]
        assert len(requests) == 1 and requests[0]["pending_since_ms"] is not None, requests

        fills_path.write_text(json.dumps([fill(1, "0", "B", now - 3500)]))
        collect = cli("market", "collect", "--once")
        notes = cli("supervisor", "notifications", "--venue", "hyperliquid")["notifications"]
        assert [n["kind"] for n in notes] == ["journal_batch"], notes
        batch = notes[0]
        ack = cli("supervisor", "notification-result", "--venue", "hyperliquid",
                  "--notification-id", str(batch["id"]), "--result", "delivered")

        # A manual exchange-app trade, journaled by the fallback account job.
        fills_path.write_text(json.dumps([fill(1, "0", "B", now - 3500), fill(2, "1", "A", now - 1000)]))
        (tmp / "job.json").write_text(json.dumps({"kind": "account", "venue": "hyperliquid",
                                                  "account": ADDRESS, "start_ms": now - 86_400_000}))
        cli("data", "configure", "--job-id", "hl-fallback", "--config", str(tmp / "job.json"),
            "--interval-seconds", "300")
        fallback = cli("market", "collect", "--once")
        manual = cli("supervisor", "notifications", "--venue", "hyperliquid")["notifications"]
        assert [e["change"] for n in manual for e in n["payload"]["entries"]] == ["close"], manual
        again = cli("data", "sync", "--venue", "hyperliquid", "--account", ADDRESS, "--start-ms", str(now - 86_400_000))
        assert again["notification_id"] is None, again  # No duplicate journal or notification.
        cli("supervisor", "notification-result", "--venue", "hyperliquid",
            "--notification-id", str(manual[0]["id"]), "--result", "delivered")

        # A KIS DAY statement keeps its precision; no time of day is invented.
        kst = __import__("datetime").datetime.now(__import__("zoneinfo").ZoneInfo("Asia/Seoul"))
        env["SMOKE_KIS_DATE"] = kst.strftime("%Y%m%d")
        midnight = int(kst.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        kis_sync = cli("data", "sync", "--venue", "kis", "--start-ms", str(midnight), venue="kis")
        [kis_note] = cli("supervisor", "notifications", "--venue", "kis", venue="kis")["notifications"]
        assert "(DAY precision)" in kis_note["message"], kis_note
        assert not __import__("re").search(r"\d\d:\d\d:\d\d", kis_note["message"]), kis_note

        # A failing exchange read backs off and stays visible.
        gateway.size = "0.5"  # A later partial exit is observed; its sync will fail.
        worker.step(pid, int(time.time() * 1000))
        assert __import__("kis_hl.fill_journal", fromlist=["x"]).sync_requests(db)[0]["pending_since_ms"] is not None
        failed = cli("market", "collect", "--once", fail=True)
        before = db.read_bytes()
        status = cli("data", "journal-status", "--accounts", SCOPE.key)
        assert db.read_bytes() == before, "journal-status must not write"
        summary = cli("data", "journal-status", "--accounts", SCOPE.key, "--enqueue-summary")
        repeat = cli("data", "journal-status", "--accounts", SCOPE.key, "--enqueue-summary")
        daily = [n for n in cli("supervisor", "notifications", "--venue", "hyperliquid")["notifications"]
                 if n["kind"] == "journal_daily"]
        assert len(summary["enqueued"]) == 1 and repeat["enqueued"] == [] and len(daily) == 1, (summary, daily)
        account = status["accounts"][0]
        request = account["sync"]["request"]
        assert request["attempts"] == 1 and request["last_error"] == "TimeoutError", request
        assert ADDRESS not in json.dumps([notes, manual, status, daily])
        print(json.dumps({
            "supervisor_request": {k: requests[0][k] for k in ("venue", "request_count")},
            "collect_outcomes": [j["status"] for j in collect["jobs"]],
            "journal_batch_message": batch["message"],
            "ack": {k: ack[k] for k in ("kind", "delivery_attempts")} | {"delivered": ack["delivered_ms"] is not None},
            "fallback_outcomes": [j["status"] for j in fallback["jobs"]],
            "manual_fill_message": manual[0]["message"],
            "repeat_sync_notification_id": again["notification_id"],
            "kis_day_message": kis_note["message"],
            "kis_sync_complete": kis_sync["collection_complete"],
            "failed_request": failed["jobs"][0]["result"],
            "status_account": {k: account[k] for k in ("venue", "open_positions", "today", "cycles", "pending")}
            | {"sync_request": request},
            "daily_message": daily[0]["message"],
        }, indent=2))


if __name__ == "__main__":
    main()
