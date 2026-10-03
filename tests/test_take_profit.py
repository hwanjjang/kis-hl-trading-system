import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from kis_hl.managed_execution import ExecutionStore, Supervisor
from tests.test_managed_execution import Gateway, plan


class TakeProfitGateway(Gateway):
    """Stub HL gateway with per-attempt sell fills and a movable quote."""

    def __init__(self):
        super().__init__()
        self.fills = {}
        self.price = "100"

    def snapshot(self, row, attempts, now):
        snap = super().snapshot(row, attempts, now)
        snap["price"] = self.price
        snap["fills_by_attempt"] = {a["id"]: self.fills.get(a["id"], "0") for a in attempts
                                    if a["kind"] in {"entry", "add", "take_profit"}}
        return snap

    def sell(self, attempt_id, quantity, *, status="filled"):
        """Fill an owned IOC take-profit order on the stub exchange."""
        self.fills[attempt_id] = str(float(self.fills.get(attempt_id, "0")) + float(quantity))
        self.size = _fmt(float(self.size) - float(quantity))
        self.orders[attempt_id]["status"] = status


def _fmt(value):
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


class TakeProfitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "test.sqlite"
        self.store = ExecutionStore(self.path)
        self.g = TakeProfitGateway()
        self.worker = Supervisor(self.store, self.g, live=True)
        preflight = self.g.preflight
        self.g.preflight = lambda p, now: {**preflight(p, now), "available_notional": "3000"}

    def protected(self, quantity="10"):
        p = plan()
        p.update(quantity=quantity, max_notional="2000", max_loss="50",
                 max_portfolio_notional="2000", max_correlated_notional="2000")
        row = self.store.enqueue("scope", p, live=True, now_ms=1)
        self.worker.step(row["id"], 10)
        self.g.size = self.g.filled = quantity
        entry = self.g.sent[0]["id"]
        self.g.orders[entry]["status"] = "filled"
        self.g.fills[entry] = quantity
        self.worker.step(row["id"], 20)
        self.assertEqual(self.worker.step(row["id"], 30)["state"], "PROTECTED")
        return row["id"]

    def tp_sent(self):
        return [a for a in self.g.sent if a["kind"] == "take_profit"]

    # AC1: quantity and reason semantics.
    def test_half_of_remaining_position_rounded_down_to_lot(self):
        for size, expected in (("10", "5"), ("0.35", "0.17"), ("1.01", "0.5")):
            with self.subTest(size=size):
                self.setUp()
                pid = self.protected(size)
                self.store.request_take_profit(pid, 40, decision_id="top-1", rationale="Judged top")
                row = self.worker.step(pid, 50)
                self.assertEqual(row["take_profit"]["status"], "EXECUTING")
                self.assertEqual(row["take_profit"]["basis_size"], size)
                self.assertEqual(row["take_profit"]["target_quantity"], expected)
                sent = self.tp_sent()
                self.assertEqual([a["quantity"] for a in sent], [expected])
                self.assertIsNone(row["exit_requested_ms"])

    def test_below_minimum_target_is_reported_without_any_order(self):
        pid = self.protected("0.19")  # 0.09 at 100 is below the USD 10 minimum.
        self.store.request_take_profit(pid, 40, decision_id="top-1", rationale="Judged top")
        row = self.worker.step(pid, 50)
        self.assertEqual(row["take_profit"]["status"], "BELOW_MINIMUM")
        self.assertEqual(self.tp_sent(), [])
        self.assertIsNone(row["exit_requested_ms"])
        self.assertEqual(row["state"], "PROTECTED")

    def test_profitable_trailing_stop_is_still_a_full_position_exit(self):
        pid = self.protected("10")
        row = self.store.get(pid)
        row["trail"].update(high="120", threshold="110")
        self.store.save(row, 35)
        self.g.price = "109"  # Above the 100 entry: a profitable TS trigger.
        self.worker.step(pid, 40)
        exits = [a for a in self.g.sent if a["kind"] == "exit"]
        self.assertEqual([a["quantity"] for a in exits], ["10"])
        self.assertEqual(self.tp_sent(), [])

    # AC2: deduplication, restart and UNKNOWN outcomes.
    def test_one_decision_never_produces_a_second_reduction(self):
        pid = self.protected("10")
        first = self.store.request_take_profit(pid, 40, decision_id="top-1", rationale="Judged top")
        again = self.store.request_take_profit(pid, 41, decision_id="top-1", rationale="Judged top")
        self.assertEqual(first["take_profit"], again["take_profit"])
        with self.assertRaisesRegex(ValueError, "active"):
            self.store.request_take_profit(pid, 42, decision_id="top-2", rationale="Another top")
        self.worker.step(pid, 50)
        self.g.sell(self.tp_sent()[0]["id"], "5")
        row = self.worker.step(pid, 60)
        self.assertEqual(row["take_profit"]["status"], "COMPLETED")
        for now in (70, 80):
            self.worker.step(pid, now)
        self.assertEqual(len(self.tp_sent()), 1)
        with self.assertRaisesRegex(ValueError, "already used"):
            self.store.request_take_profit(pid, 90, decision_id="top-1", rationale="Judged top")
        self.assertEqual(self.g.size, "5")

    def test_unknown_take_profit_outcome_is_not_resent_after_restart(self):
        pid = self.protected("10")
        self.store.request_take_profit(pid, 40, decision_id="top-1", rationale="Judged top")
        submit = self.g.submit

        def lost_ack(row, attempt):
            if attempt["kind"] == "take_profit":
                raise TimeoutError("acknowledgement lost")
            return submit(row, attempt)

        self.g.submit = lost_ack
        self.worker.step(pid, 50)
        attempts = [a for a in self.store.attempts(pid) if a["kind"] == "take_profit"]
        self.assertEqual([a["status"] for a in attempts], ["UNKNOWN"])
        restarted = Supervisor(ExecutionStore(self.path), self.g, live=True)
        for now in (60, 70, 80):
            restarted.step(pid, now)
        self.assertEqual(len([a for a in self.store.attempts(pid) if a["kind"] == "take_profit"]), 1)
        self.assertEqual(self.g.size, "10")
        row = restarted.step(pid, 70000)  # Past the exit deadline: still no resend or forced exit.
        self.assertEqual(row["take_profit"]["status"], "EXECUTING")
        self.assertIn("reconcile manually", row["reason"])
        self.assertIsNone(row["exit_requested_ms"])
        self.assertEqual(len([a for a in self.store.attempts(pid) if a["kind"] == "take_profit"]), 1)

    # AC2 + AC3: partial fill, SQLite reopen and residual coverage.
    def test_partial_fill_reopen_then_remaining_fill_keeps_residual_protected(self):
        pid = self.protected("10")
        trail_before = dict(self.store.get(pid)["trail"])
        stops_before = [a["id"] for a in self.g.sent if a["kind"] in {"stop", "trailing"}]
        self.store.request_take_profit(pid, 40, decision_id="top-1", rationale="Judged top")
        self.worker.step(pid, 50)
        self.g.sell(self.tp_sent()[0]["id"], "2", status="canceled")  # IOC partial fill.
        reopened = ExecutionStore(self.path)
        worker = Supervisor(reopened, self.g, live=True)
        row = worker.step(pid, 60)
        self.assertEqual([a["quantity"] for a in self.tp_sent()], ["5", "3"])
        self.assertEqual(row["take_profit"]["status"], "EXECUTING")
        self.g.sell(self.tp_sent()[1]["id"], "3")
        row = worker.step(pid, 70)
        self.assertEqual(row["take_profit"]["status"], "COMPLETED")
        self.assertEqual(row["take_profit"]["residual_size"], "5")
        self.assertEqual(row["state"], "PROTECTED")
        self.assertEqual(row["covered_size"], "5")
        self.assertIsNone(row["exit_requested_ms"])
        for key in ("entry", "distance", "high", "threshold", "opened_ms"):
            self.assertEqual(row["trail"][key], trail_before[key])
        self.assertEqual([a["id"] for a in self.g.sent if a["kind"] in {"stop", "trailing"}],
                         stops_before)
        self.assertTrue(all(self.g.orders[i]["status"] == "open" for i in stops_before))

    def test_successive_decisions_do_not_inherit_prior_fills_or_budget(self):
        pid = self.protected("10")
        self.store.request_take_profit(pid, 40, decision_id="first", rationale="First top")
        self.worker.step(pid, 50)
        self.g.sell(self.tp_sent()[0]["id"], "5")
        self.assertEqual(self.worker.step(pid, 60)["take_profit"]["status"], "COMPLETED")
        self.store.request_take_profit(pid, 70, decision_id="second", rationale="Second top")
        row = self.worker.step(pid, 80)
        self.assertEqual(row["take_profit"]["filled_quantity"], "0")
        self.assertEqual([a["quantity"] for a in self.tp_sent()], ["5", "2.5"])
        self.g.sell(self.tp_sent()[1]["id"], "2.5")
        row = self.worker.step(pid, 90)
        self.assertEqual((row["take_profit"]["status"], row["take_profit"]["residual_size"]), ("COMPLETED", "2.5"))

    def test_exhausted_decision_attempts_do_not_consume_next_decision_budget(self):
        pid = self.protected("10")
        self.store.request_take_profit(pid, 40, decision_id="first", rationale="First top")
        for now in (50, 60, 70, 80):
            self.worker.step(pid, now)
            for a in self.tp_sent():
                self.g.orders[a["id"]]["status"] = "canceled"  # IOC without any fill.
        self.assertEqual(self.store.get(pid)["take_profit"]["status"], "EXHAUSTED")
        self.assertEqual(len(self.tp_sent()), 3)
        self.store.request_take_profit(pid, 90, decision_id="second", rationale="Second top")
        self.worker.step(pid, 100)
        self.assertEqual(len(self.tp_sent()), 4)
        self.assertEqual(self.tp_sent()[-1]["decision_id"], "second")

    def native_protected(self):
        self.g.native_trailing = True
        p = plan(trailing_provider="native", local_trailing_backup=True)
        p.update(quantity="10", max_notional="2000", max_loss="50",
                 max_portfolio_notional="2000", max_correlated_notional="2000")
        row = self.store.enqueue("scope", p, live=True, now_ms=1)
        submit = self.g.submit

        def native_submit(owner, attempt):
            result = submit(owner, attempt)
            if attempt["kind"] == "trailing":
                self.g.orders[attempt["id"]].update(active=True, retracement_unit="quote",
                                                    retracement=attempt["retracement"])
            return result

        self.g.submit = native_submit
        self.worker.step(row["id"], 10)
        self.g.size = self.g.filled = "10"
        self.g.orders[self.g.sent[0]["id"]]["status"] = "filled"
        for now in (20, 30, 40):
            state = self.worker.step(row["id"], now)["state"]
        self.assertEqual(state, "PROTECTED")
        return row["id"]

    def test_native_trailing_is_retained_and_covers_residual(self):
        pid = self.native_protected()
        before = self.store.get(pid)
        protection = {a["id"]: dict(self.g.orders[a["id"]]) for a in self.g.sent if a["kind"] in {"stop", "trailing"}}
        self.assertEqual(sorted(o["kind"] for o in protection.values()), ["stop", "trailing"])
        self.store.request_take_profit(pid, 45, decision_id="top-1", rationale="Judged top")
        self.worker.step(pid, 50)
        self.g.sell(self.tp_sent()[0]["id"], "5")
        row = self.worker.step(pid, 60)
        self.assertEqual(row["take_profit"]["status"], "COMPLETED")
        self.assertEqual((row["covered_size"], row["trailing_covered_size"]), ("5", "5"))
        self.assertEqual(row["native_trailing_distance"], before["native_trailing_distance"])
        self.assertEqual({a["id"]: self.g.orders[a["id"]] for a in self.g.sent if a["kind"] in {"stop", "trailing"}},
                         protection)
        for key in ("high", "threshold", "distance"):
            self.assertEqual(row["trail"][key], before["trail"][key])

    def test_native_trailing_fill_during_take_profit_supersedes_it(self):
        pid = self.native_protected()
        self.store.request_take_profit(pid, 45, decision_id="top-1", rationale="Judged top")
        submit = self.g.submit

        def resting(owner, attempt):
            result = submit(owner, attempt)
            if attempt["kind"] == "take_profit":
                self.g.orders[attempt["id"]]["status"] = "open"  # Unresolved TP outcome.
            return result

        self.g.submit = resting
        self.worker.step(pid, 50)
        trail = next(a["id"] for a in self.g.sent if a["kind"] == "trailing")
        self.g.orders[trail]["status"] = "filled"
        self.g.size = "4"  # The trail sold six before the TP resolved.
        row = self.worker.step(pid, 60)
        self.assertEqual(row["take_profit"]["status"], "SUPERSEDED")
        self.assertEqual([a for a in self.g.sent if a["kind"] == "exit"], [])
        self.g.orders[self.tp_sent()[0]["id"]]["status"] = "canceled"
        self.worker.step(pid, 70)
        self.assertEqual([a["quantity"] for a in self.g.sent if a["kind"] == "exit"], ["4"])
        self.assertEqual(len(self.tp_sent()), 1)
        self.assertEqual(len([a for a in self.g.sent if a["kind"] == "trailing"]), 1)

    # AC4: a competing full exit takes precedence.
    def test_stop_fill_during_take_profit_supersedes_without_oversell(self):
        pid = self.protected("10")
        self.store.request_take_profit(pid, 40, decision_id="top-1", rationale="Judged top")
        self.worker.step(pid, 50)
        tp = self.tp_sent()[0]["id"]
        self.g.fills[tp] = "2"  # Partially filled TP still resting on the exchange.
        stop = next(a["id"] for a in self.g.sent if a["kind"] == "stop")
        self.g.orders[stop]["status"] = "filled"
        self.g.size = "0"  # The stop sold the remaining eight.
        row = self.worker.step(pid, 60)
        self.assertEqual(row["take_profit"]["status"], "SUPERSEDED")
        for now in (70, 80, 90):
            row = self.worker.step(pid, now)
        self.assertEqual(self.g.orders[tp]["status"], "canceled")
        self.assertEqual(row["state"], "CLOSED")
        self.assertEqual(len(self.tp_sent()), 1)
        self.assertEqual([a for a in self.g.sent if a["kind"] == "exit"], [])
        self.assertEqual(len([a for a in self.g.sent if a["kind"] == "stop"]), 1)

    def test_exit_latch_waits_for_unresolved_take_profit_before_full_exit(self):
        pid = self.protected("10")
        self.store.request_take_profit(pid, 40, decision_id="top-1", rationale="Judged top")
        self.worker.step(pid, 50)
        tp = self.tp_sent()[0]["id"]
        self.store.request_exit(pid, 55)
        self.worker.step(pid, 60)
        self.assertEqual([a for a in self.g.sent if a["kind"] == "exit"], [])
        self.assertEqual(self.store.get(pid)["take_profit"]["status"], "SUPERSEDED")
        self.g.sell(tp, "5")
        self.worker.step(pid, 70)
        exits = [a for a in self.g.sent if a["kind"] == "exit"]
        self.assertEqual([a["quantity"] for a in exits], ["5"])

    # AC3 + AC5: guards fail closed.
    def test_add_is_blocked_while_take_profit_is_active(self):
        pid = self.protected("10")
        self.store.request_take_profit(pid, 40, decision_id="top-1", rationale="Judged top")
        owner = self.store.get(pid)
        with self.assertRaisesRegex(ValueError, "take profit"):
            self.store.enqueue_add(owner, {"intent_id": "add-1"}, now_ms=45, sizing={})

    def test_pending_add_blocks_take_profit_request(self):
        pid = self.protected("10")
        owner = self.store.get(pid)
        self.store.enqueue_add(owner, {"intent_id": "add-1"}, now_ms=35, sizing={})
        with self.assertRaisesRegex(ValueError, "add"):
            self.store.request_take_profit(pid, 40, decision_id="top-1", rationale="Judged top")

    def test_add_committing_during_take_profit_admission_cannot_both_succeed(self):
        import sqlite3
        from unittest.mock import patch

        pid = self.protected("10")
        tranches = self.store.tranches
        connect = sqlite3.connect
        outcome = {}

        def interleaved(position_id, *db):
            seen = tranches(position_id, *db)
            # Another process tries to admit an add after TP admission read the tranches.
            with patch("kis_hl.managed_execution.sqlite3.connect",
                       lambda path, timeout: connect(path, timeout=0.2)):
                try:
                    other = ExecutionStore(self.path)
                    other.enqueue_add(other.get(pid), {"intent_id": "add-race"}, now_ms=41, sizing={})
                    outcome["add"] = "committed"
                except sqlite3.OperationalError:
                    outcome["add"] = "blocked"
            return seen

        with patch.object(self.store, "tranches", side_effect=interleaved):
            self.store.request_take_profit(pid, 40, decision_id="top-1", rationale="Judged top")
        self.assertEqual(outcome["add"], "blocked")
        self.assertEqual(self.store.tranches(pid), [])
        self.assertEqual(self.store.get(pid)["take_profit"]["status"], "REQUESTED")

    def test_add_authorized_from_owner_read_before_take_profit_is_rejected(self):
        pid = self.protected("10")
        stale_owner = self.store.get(pid)
        self.store.request_take_profit(pid, 40, decision_id="top-1", rationale="Judged top")
        with self.assertRaisesRegex(RuntimeError, "changed"):
            self.store.enqueue_add(stale_owner, {"intent_id": "add-1"}, now_ms=45, sizing={})
        self.assertEqual(self.store.tranches(pid), [])

    def test_unsupported_owners_and_requests_fail_closed(self):
        pid = self.protected("10")
        for kwargs in ({"decision_id": "", "rationale": "r"}, {"decision_id": "d", "rationale": " "}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.store.request_take_profit(pid, 40, **kwargs)
        row = self.store.get(pid)
        row["state"] = "PROTECTING"
        self.store.save(row, 41)
        with self.assertRaisesRegex(ValueError, "PROTECTED"):
            self.store.request_take_profit(pid, 42, decision_id="top-1", rationale="r")
        row = self.store.get(pid)
        row["state"] = "PROTECTED"
        self.store.save(row, 43)
        self.store.request_exit(pid, 44)
        with self.assertRaisesRegex(ValueError, "exit"):
            self.store.request_take_profit(pid, 45, decision_id="top-1", rationale="r")
        row = self.store.get(pid)
        row["exit_requested_ms"] = None
        row["plan"]["instrument"] = "kis:SPY"
        self.store.save(row, 46)
        with self.assertRaisesRegex(ValueError, "Hyperliquid"):
            self.store.request_take_profit(pid, 47, decision_id="top-1", rationale="r")
        self.assertNotIn("take_profit", self.store.get(pid))


class TakeProfitCliTests(unittest.TestCase):
    setUp, protected = TakeProfitTests.setUp, TakeProfitTests.protected

    def run_cli(self, *args):
        import contextlib
        import io
        from unittest.mock import patch
        from kis_hl.cli import main

        out, err = io.StringIO(), io.StringIO()
        with patch("kis_hl.cli.load_env_file"), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--db", str(self.path), *args])
        return code, out.getvalue(), err.getvalue()

    def test_cli_records_request_once_and_never_sends(self):
        import json

        pid = self.protected("10")
        sent = len(self.g.sent)
        args = ("order", "take-profit", "--id", pid, "--decision-id", "top-1", "--rationale", "Judged top")
        code, out, err = self.run_cli(*args)
        self.assertEqual(code, 0, err)
        first = json.loads(out)["take_profit"]
        self.assertEqual((first["status"], first["decision_id"]), ("REQUESTED", "top-1"))
        code, out, err = self.run_cli(*args)
        self.assertEqual((code, json.loads(out)["take_profit"]), (0, first))
        code, out, err = self.run_cli("order", "take-profit", "--id", pid, "--decision-id", "top-2",
                                      "--rationale", "Another top")
        self.assertNotEqual(code, 0)
        self.assertEqual(len(self.g.sent), sent)


class TakeProfitTransportTests(unittest.TestCase):
    def test_kis_gateway_rejects_take_profit_before_any_call(self):
        from kis_hl.managed_gateways import ManagedKisGateway

        client = Mock()
        client.config = SimpleNamespace(base_url="https://fixture", account_id="fixture", mode="live")
        g = ManagedKisGateway(client)
        with self.assertRaisesRegex(ValueError, "take profit"):
            g.submit({"plan": {**plan(), "instrument": "kis:SPY"}}, {"kind": "take_profit", "quantity": "1", "price": "1"})
        client.cash_order.assert_not_called()

    def test_hyperliquid_take_profit_is_reduce_only_ioc_with_attributed_fills(self):
        from tests.test_managed_gateways import ManagedGatewayTests

        g, info, row, attempts, order = ManagedGatewayTests.hl(None)
        row["plan"]["max_quote_age_ms"] = 1000
        g.trading.place_order.return_value = SimpleNamespace(status="submitted", response={})
        g.submit(row, dict(id="0xtp", kind="take_profit", quantity="0.5", price="99", created_ms=10))
        call = g.trading.place_order.call_args.kwargs
        self.assertEqual((call["side"], call["reduce_only"], call["tif"]), ("sell", True, "Ioc"))
        tp = dict(order, oid=44, cloid="0xtp", side="A", reduceOnly=True, sz="0", origSz="0.5")
        attempts.append(dict(id="0xtp", kind="take_profit", order_id="44", status="SUBMITTED"))
        info.order_status.side_effect = lambda *, oid: {"status": "order", "order": {
            "status": "filled", "order": tp if str(oid) == "44" else order}}
        info.user_fills_by_time.return_value.append(dict(tid=2, coin="BTC", side="A",
            sz="0.5", px="99", time=11, oid=44))
        info.clearinghouse_state.return_value["assetPositions"][0]["position"]["szi"] = "0.5"
        snap = g.snapshot(row, attempts, 20)
        self.assertTrue(snap["consistent"])
        self.assertEqual(snap["fills_by_attempt"]["0xtp"], "0.5")
        self.assertEqual(snap["protective_filled"], "0")


if __name__ == "__main__":
    unittest.main()
