import tempfile
import unittest
from pathlib import Path
from kis_hl.managed_execution import ExecutionStore
from kis_hl.strategy_signals import Signals
from tests.test_managed_execution import plan
from tests.test_strategy_tools import DAY, NOW, setup
from kis_hl.strategy_tools import evaluate_setup


class SignalsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ExecutionStore(Path(self.tmp.name) / "test.sqlite")
        self.signals = Signals(self.store)
        self.signals.register(
            {
                "id": "fixture",
                "version": "1",
                "instruments": ["hl:BTC"],
                "description": "Fixture strategy",
            }
        )
        self.signals.ingest(
            {
                "id": "s1",
                "strategy": "fixture",
                "strategy_version": "1",
                "signal_instrument": "hl:BTC",
                "execution_instruments": ["hl:BTC"],
                "observed_ms": 1,
                "expires_ms": 1000,
                "rationale": "Fixture signal",
            },
            now_ms=2,
        )

    def test_signal_itself_has_no_order_authority(self):
        with self.assertRaisesRegex(ValueError, "authority"):
            self.signals.execute("s1", "scope", plan(), live=True, now_ms=3)
        self.assertEqual(self.store.list(), [])

    def test_manual_execution_is_idempotent_after_close(self):
        first = self.signals.execute(
            "s1", "scope", plan(), live=False, manual=True, now_ms=3
        )
        first["state"] = "CLOSED"
        self.store.save(first)
        again = self.signals.execute(
            "s1", "scope", plan(), live=False, manual=True, now_ms=4
        )
        self.assertEqual(first["id"], again["id"])

    def test_grant_is_bounded_revocable_and_account_specific(self):
        self.signals.grant(
            {
                "id": "g",
                "scope": "scope",
                "strategy": "fixture",
                "strategy_version": "1",
                "instruments": ["hl:BTC"],
                "expires_ms": 500,
                "max_intents": 1,
                "max_notional": "101",
                "live": True,
            },
            now_ms=2,
        )
        with self.assertRaisesRegex(ValueError, "scope"):
            self.signals.execute(
                "s1", "other", plan(), live=True, grant_id="g", now_ms=3
            )
        row = self.signals.execute(
            "s1", "scope", plan(), live=True, grant_id="g", now_ms=3
        )
        self.signals.revoke("g")
        with self.assertRaisesRegex(ValueError, "revoked"):
            self.signals.check_authority(row, now_ms=4)

    def test_expired_signal_cannot_execute(self):
        with self.assertRaisesRegex(ValueError, "expired"):
            self.signals.execute(
                "s1", "scope", plan(), live=True, manual=True, now_ms=1001
            )

    def test_hold_or_add_decision_cannot_be_used_as_a_new_entry(self):
        for action in ["hold", "no_trade", "exit", "reduce", "add"]:
            original = self.signals.list()[0]
            self.signals.ingest({**original, "id": action, "action": action}, now_ms=2)
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "entry"):
                self.signals.execute(action, "scope", plan(), manual=True, now_ms=3)
        self.assertEqual(self.store.list(), [])

    def test_raw_entry_rejects_non_entry_or_malformed_setup_evidence(self):
        for kind in ["pullback", "rebreakout", "management", None]:
            with self.subTest(setup=kind):
                request = setup(kind)
                request.update(reference="100", tolerance="2", position=dict(
                    id="p1", scope="scope", instrument="hl:BTC", quantity="1",
                    stop="95", opened_ms=NOW-3*DAY, asof_ms=NOW, max_age_ms=60000))
                request["snapshot"]["price"] = "94"
                if kind is not None:
                    self.assertTrue(evaluate_setup(request, now_ms=NOW)["predicate_passed"])
                record = {**self.signals.list()[0], "id": str(kind), "action": "enter",
                          "observed_ms": NOW, "expires_ms": NOW+60000,
                          "setup_input": request if kind is not None else None}
                self.signals.ingest(record, now_ms=NOW)
                execution_plan = plan()
                execution_plan["expires_ms"] = NOW+60000
                with self.assertRaisesRegex(ValueError, "entry setup"):
                    self.signals.execute(record["id"], str(kind), execution_plan,
                                         manual=True, now_ms=NOW)
                self.assertEqual(self.store.list(str(kind)), [])

    def test_raw_entry_accepts_breakout_and_btc_evidence(self):
        for kind in ["breakout", "btc_3h"]:
            with self.subTest(setup=kind):
                request = setup(kind)
                if kind == "btc_3h":
                    request["snapshot"]["instrument"] = "hl:UBTC/USDC"
                record = {**self.signals.list()[0], "id": kind, "action": "enter",
                          "observed_ms": NOW, "expires_ms": NOW+60000,
                          "setup_input": request}
                self.signals.ingest(record, now_ms=NOW)
                execution_plan = plan()
                execution_plan["expires_ms"] = NOW+60000
                row = self.signals.execute(kind, kind, execution_plan, manual=True, now_ms=NOW)
                self.assertEqual(row["state"], "QUEUED")


if __name__ == "__main__":
    unittest.main()
