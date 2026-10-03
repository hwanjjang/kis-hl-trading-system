"""Explicit intraday authority is separate from weekly strategy predicates."""
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from kis_hl.managed_execution import ExecutionStore, Supervisor
from tests.test_conditional_add import AddGateway, protected, capital, NOW


class IntradayGateway(AddGateway):
    bars = []

    def snapshot(self, row, attempts, now):
        return super().snapshot(row, attempts, now) | {"fixed_stop_filled": "0"}

    def completed_nine_minute_bars(self, instrument_id, now):
        return self.bars

    def submit(self, row, a):
        result = super().submit(row, a)
        if a["kind"] == "trailing":
            self.orders[a["id"]]["retracement_unit"] = a.get("retracement_unit", "quote")
        return result


class IntradayPercentageAddTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = ExecutionStore(Path(tmp.name)/"offline.sqlite")
        self.g = IntradayGateway()
        self.row, self.worker = protected(self.store, self.g, native=True)
        self.row["plan"].update(native_trailing_percent="8.35", local_trailing_backup=False)
        self.store.save(self.row, NOW)
        for a in self.store.attempts(self.row["id"]):
            if a["kind"] == "trailing":
                self.store.update_attempt(a, retracement="8.35", retracement_unit="percent")
                self.g.orders[a["id"]].update(retracement="8.35", retracement_unit="percent")
        self.end = NOW // 540000 * 540000
        self.g.bars = [dict(start_ms=self.end-1080000, end_ms=self.end-540000,
                           high="100", close="99"),
                       dict(start_ms=self.end-540000, end_ms=self.end, high="101", close="100.2")]

    def queue(self, **kw):
        return self.store.enqueue_intraday_add(self.row["id"],
            intent_id="explicit-add", units="0.02", expires_ms=NOW+40000,
            authorized_ms=self.end-1, now_ms=NOW, manual=True, **kw)

    def test_waits_for_new_completed_breakout_then_hard_capped_send(self):
        self.g.bars[-1]["close"] = "99"
        tranche = self.queue()
        self.worker.step(self.row["id"], NOW+1)
        self.assertEqual(self.store.tranches(self.row["id"])[0]["status"], "QUEUED")
        self.assertFalse(any(a["kind"] == "add" for a in self.g.sent))
        self.g.bars[-1]["close"] = "100.2"
        self.worker.step(self.row["id"], NOW+2)
        add = self.g.sent[-1]
        self.assertEqual(add["kind"], "add")
        self.assertLessEqual(Decimal(add["price"]), Decimal("100.2")*Decimal("1.003"))
        self.assertEqual(add["price"], "100.50")
        self.assertEqual(add["tranche_id"], tranche["id"])
        old_trail = next(a for a in self.g.sent if a["kind"] == "trailing")
        before = dict(old_trail)
        self.g.fill(add, "0.2", terminal=False)
        for now in (NOW+3, NOW+4, NOW+5):
            self.worker.step(self.row["id"], now)
        trails = [a for a in self.g.sent if a["kind"] == "trailing"]
        self.assertEqual(len(trails), 2)
        self.assertEqual(trails[-1]["quantity"], "0.2")
        self.assertEqual(trails[-1]["retracement_unit"], "percent")
        self.assertEqual(old_trail, before)
        self.assertIsNone(self.store.get(self.row["id"])["exit_requested_ms"])
        self.assertEqual(self.store.get(self.row["id"])["local_trailing_covered_size"], "0")
        self.worker = Supervisor(self.store, self.g, live=True)
        self.worker.step(self.row["id"], NOW+6)
        self.assertEqual(len([a for a in self.g.sent if a["kind"] == "add"]), 1)

    def test_percentage_tranche_fill_does_not_liquidate_other_tranche(self):
        self.queue(); self.worker.step(self.row["id"], NOW+1)
        add = self.g.sent[-1]; self.g.fill(add, "0.2", terminal=True)
        for now in (NOW+2, NOW+3, NOW+4): self.worker.step(self.row["id"], now)
        trail = self.g.sent[-1]
        self.assertEqual(trail["kind"], "trailing")
        self.g.orders[trail["id"]].update(status="filled", size="0")
        self.g.size = "1"; self.g.protective_filled = "0.2"
        result = self.worker.step(self.row["id"], NOW+5)
        self.assertIsNone(result["exit_requested_ms"])
        self.assertFalse(any(a["kind"] == "exit" for a in self.g.sent))
        self.assertEqual(result["state"], "PROTECTED")

    def test_expiry_and_account_kill_switch_never_send(self):
        self.queue(); self.store.set_entries("scope", False)
        self.worker.step(self.row["id"], NOW+1)
        self.assertFalse(any(a["kind"] == "add" for a in self.g.sent))
        self.assertEqual(self.store.tranches(self.row["id"])[0]["status"], "REJECTED")

    def test_rejects_authority_without_explicit_approval_or_percentage_coverage(self):
        with self.assertRaises(ValueError):
            self.store.enqueue_intraday_add(self.row["id"], intent_id="no", units="0.2",
                expires_ms=NOW+1000, authorized_ms=NOW, now_ms=NOW, manual=False)
        self.row["plan"].pop("native_trailing_percent")
        self.store.save(self.row, NOW)
        with self.assertRaises(ValueError): self.queue()

    def test_account_intervention_peer_blocks_intraday_exception(self):
        from tests.test_managed_execution import plan
        peer = self.store.enqueue("scope", plan() | {"expires_ms": NOW+60000, "intent_id":"peer"}, live=True, now_ms=NOW)
        peer["state"] = "INTERVENTION"; self.store.save(peer, NOW)
        self.queue(); self.worker.step(self.row["id"], NOW+1)
        self.assertEqual(self.store.tranches(self.row["id"])[0]["status"], "REJECTED")
        self.assertFalse(any(a["kind"] == "add" for a in self.g.sent))

    def test_unknown_tranche_trail_is_not_resent_after_restart(self):
        self.queue(); self.worker.step(self.row["id"], NOW+1)
        add = self.g.sent[-1]; self.g.fill(add, "0.2", terminal=True)
        self.worker.step(self.row["id"], NOW+2)  # fixed SL for added size
        submit = self.g.submit
        def unknown(row, attempt):
            if attempt["kind"] == "trailing":
                self.g.sent.append(attempt.copy()); raise OSError("lost acknowledgement")
            return submit(row, attempt)
        self.g.submit = unknown
        self.worker.step(self.row["id"], NOW+3)
        self.worker = Supervisor(self.store, self.g, live=True)
        result = self.worker.step(self.row["id"], NOW+4)
        self.assertEqual(result["state"], "INTERVENTION")
        self.assertEqual(len([a for a in self.g.sent if a["kind"] == "trailing"]), 2)
        self.assertIsNone(result["exit_requested_ms"])

    def test_expired_direct_approval_is_retired_without_send(self):
        self.queue(); self.worker.step(self.row["id"], NOW+40000)
        self.assertIn(self.store.tranches(self.row["id"])[0]["status"], {"EXPIRED", "REJECTED"})
        self.assertFalse(any(a["kind"] == "add" for a in self.g.sent))

    def test_partial_add_waiting_trail_timeout_is_not_renewed_by_later_fill(self):
        self.queue(); self.worker.step(self.row['id'], NOW+1)
        add = self.g.sent[-1]; self.g.fill(add, '0.2', terminal=False)
        self.worker.step(self.row['id'], NOW+2)
        self.worker.step(self.row['id'], NOW+3)
        first = self.g.sent[-1]
        self.assertEqual(first['kind'], 'trailing')
        self.g.orders[first['id']]['active'] = False
        self.g.fill(add, '0.3', terminal=True)
        self.worker.step(self.row['id'], NOW+4000)
        self.worker.step(self.row['id'], NOW+4001)
        second = self.g.sent[-1]
        self.assertEqual(second['kind'], 'trailing')
        self.worker = Supervisor(self.store, self.g, live=True)
        result = self.worker.step(self.row['id'], NOW+5003)
        self.assertIsNotNone(result['exit_requested_ms'])
        self.assertEqual(self.g.sent[-1]['kind'], 'exit')
        self.assertEqual(len([a for a in self.g.sent if a['kind']=='trailing']), 3)

    def test_waiting_percentage_timeout_cancels_partial_add_before_exit(self):
        self.queue(); self.worker.step(self.row['id'], NOW+1)
        add = self.g.sent[-1]; self.g.fill(add, '0.2', terminal=False)
        self.worker.step(self.row['id'], NOW+2)
        self.worker.step(self.row['id'], NOW+3)
        trail = self.g.sent[-1]; self.g.orders[trail['id']]['active'] = False
        result = self.worker.step(self.row['id'], NOW+5003)
        self.assertIsNotNone(result['exit_requested_ms'])
        self.assertEqual(self.g.orders[add['id']]['status'], 'canceled')
        self.worker.step(self.row['id'], NOW+5004)
        self.assertEqual(self.g.sent[-1]['kind'], 'exit')
        self.assertEqual(len([a for a in self.g.sent if a['kind']=='trailing']), 2)

    def test_old_nonadjacent_or_unfinished_bars_never_send(self):
        for change in ("old", "gap", "future"):
            with self.subTest(change=change):
                if change == "old": self.g.bars[-1]["end_ms"] = self.end-540000
                if change == "gap": self.g.bars[-1]["start_ms"] += 60000
                if change == "future": self.g.bars[-1]["end_ms"] = NOW+540000
                if not self.store.tranches(self.row["id"]): self.queue()
                self.worker.step(self.row["id"], NOW+1)
                self.assertFalse(any(a["kind"] == "add" for a in self.g.sent))


class NineMinuteReadTests(unittest.TestCase):
    def test_native_minutes_aggregate_with_gaps_and_duplicates_rejected(self):
        from tests import test_managed_gateways
        g, info, _, _, _ = test_managed_gateways.ManagedGatewayTests().hl()
        end = 2*540000
        minutes = [dict(t=t, T=t+59999, s="BTC", i="1m", o="100", h="101", l="99", c="100")
                   for t in range(0, end, 60000)]
        info.candle_snapshot.return_value = minutes
        bars = g.completed_nine_minute_bars("hl:BTC", end+1)
        self.assertEqual([b["end_ms"] for b in bars], [540000,1080000])
        info.candle_snapshot.assert_called_once_with("BTC", interval="1m", start_time_ms=0, end_time_ms=end)
        info.candle_snapshot.return_value = minutes[:-1]
        self.assertEqual(g.completed_nine_minute_bars("hl:BTC", end+1), [])
        info.candle_snapshot.return_value = minutes+[minutes[0]]
        with self.assertRaises(ValueError): g.completed_nine_minute_bars("hl:BTC", end+1)


if __name__ == "__main__": unittest.main()
