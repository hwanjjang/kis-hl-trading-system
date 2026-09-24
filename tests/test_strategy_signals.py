import tempfile
import unittest
from pathlib import Path
from kis_hl.managed_execution import ExecutionStore
from kis_hl.strategy_signals import Signals
from tests.test_managed_execution import plan


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


if __name__ == "__main__":
    unittest.main()
