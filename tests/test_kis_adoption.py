"""KIS domestic holding handoff into local SL/trailing supervision (offline fixtures)."""
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from kis_hl.managed_execution import ExecutionStore, Supervisor
from kis_hl.managed_gateways import KisSessionClosed, ManagedKisGateway
from kis_hl.manual_adoption import verify_kis_adoption

NOW = 1_790_700_000_000
BUY = {"pdno": "069500", "odno": "0017865300", "sll_buy_dvsn_cd": "02", "ord_qty": "3",
       "tot_ccld_qty": "3", "cncl_yn": ""}


def plan(**changes):
    return {
        "intent_id": "kis-handoff-fixture", "instrument": "kis:069500",
        "signal_instrument": "index:KOSPI", "strategy": "manual", "strategy_version": "1",
        "quantity": "3", "limit_price": "109990", "atr": "2901", "atr_multiple": "2.5",
        "local_atr_multiple": "2.5", "fixed_stop_price": "102700", "trailing_provider": "local",
        "verified_price_step": "5", "max_notional": "340000", "max_loss": "22000",
        "max_portfolio_notional": "400000", "max_correlated_notional": "400000",
        "max_spread_bps": "30", "max_entry_deviation_bps": "30", "max_quote_age_ms": 30000,
        "protection_grace_ms": 120000, "max_exit_attempts": 3, "exit_deadline_ms": 120000,
        "exit_reprice_ms": 5000, "slippage": "0.005", "allow_local_sl": True,
        "expires_ms": NOW + 600_000, **changes,
    }


class FixtureKisGateway(ManagedKisGateway):
    def __init__(self):
        client = Mock()
        client.config = SimpleNamespace(base_url="https://fixture", account_id="fixture", mode="live")
        client.account_pages.return_value = {"output": []}
        super().__init__(client)
        self.history = [dict(BUY)]
        self.holding = {"pdno": "069500", "hldg_qty": "3", "pchs_avg_pric": "109990.0000",
                        "ord_psbl_qty": "3", "evlu_amt": "329970"}
        self.quote = (Decimal("109985"), Decimal("109990"))
        self.session = True
        self.sent = []
        self._clock = NOW

    def _history(self, asset, created, now):
        return self.history

    def _rows(self, asset):
        return [self.holding] if self.holding else []

    def _atr(self, asset, now):
        return "2901", {"instrument": asset.id, "basis": "fixture"}

    def _session(self, asset, now):
        return self.session

    def _quote(self, asset):
        if not self.session:
            raise KisSessionClosed("closed")
        return self.quote[0], self.quote[1], int(self._clock)

    def snapshot(self, row, attempts, now):
        # Owned entry order status comes from history; keep the fixture clock consistent.
        return {**super().snapshot(row, attempts, now), "observed_now_ms": int(self._clock)}

    def submit(self, row, a):
        self.sent.append(dict(a))
        return {"status": "submitted", "order_id": "9" + str(len(self.sent)).zfill(9)}


class KisAdoptionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = ExecutionStore(Path(tmp.name) / "t.sqlite")
        self.g = FixtureKisGateway()
        self.worker = Supervisor(self.store, self.g, live=True)

    def adopt(self, p=None):
        return self.store.enqueue_adoption(self.g.scope, p or plan(), entry_order_id="0017865300",
                                           stop_order_id=None, live=True, now_ms=NOW,
                                           entry_since_ms=NOW - 3_600_000)

    def step(self, at):
        self.g._clock = at
        return self.worker.step(self.row["id"], at)

    def test_admits_single_filled_buy_and_protects_locally_in_session(self):
        self.row = self.adopt()
        self.assertEqual(self.step(NOW + 1_000)["state"], "PROTECTING")
        result = self.step(NOW + 2_000)
        self.assertEqual(result["state"], "PROTECTED")
        self.assertEqual(result["covered_size"], "3")
        self.assertEqual(self.g.sent, [])

    def test_fixed_stop_breach_sends_bounded_sell(self):
        self.row = self.adopt()
        self.step(NOW + 1_000)
        self.step(NOW + 2_000)
        self.g.quote = (Decimal("102650"), Decimal("102660"))
        self.step(NOW + 3_000)
        self.assertEqual(self.g.sent[-1]["kind"], "exit")
        self.assertEqual(self.g.sent[-1]["quantity"], "3")

    def test_closed_session_is_not_forced_to_exit_at_next_open(self):
        self.row = self.adopt()
        self.step(NOW + 1_000)
        self.g.session = False
        # Poll every 5 s (supervisor cadence) for far longer than the protection grace.
        for offset in range(10_000, 400_000, 5_000):
            result = self.step(NOW + offset)
        self.assertEqual(result["covered_size"], "0")
        self.assertIsNone(result["exit_requested_ms"])
        self.g.session = True
        self.assertEqual(self.step(NOW + 400_000)["state"], "PROTECTED")
        self.assertEqual(self.g.sent, [])

    def test_closed_session_observation_gap_survives_restart(self):
        self.row = self.adopt()
        self.step(NOW + 1_000)
        self.g.session = False
        self.step(NOW + 2_000)
        result = self.step(NOW + 192_000)
        self.assertIsNone(result["exit_requested_ms"])
        # New supervisor instance must use persisted availability evidence.
        self.worker = Supervisor(ExecutionStore(self.store.path), self.g, live=True)
        self.g.session = True
        result = self.step(NOW + 400_000)
        self.assertEqual(result["state"], "PROTECTED")
        self.assertIsNone(result["exit_requested_ms"])
        self.assertEqual(self.g.sent, [])

    def test_overnight_open_to_open_gap_does_not_exit(self):
        for days in (1, 3):
            with self.subTest(days=days):
                self.setUp()
                self.row = self.adopt()
                self.step(NOW + 1_000)
                self.step(NOW + 2_000)
                result = self.step(NOW + days * 86_400_000)
                self.assertEqual(result["state"], "PROTECTED")
                self.assertIsNone(result["exit_requested_ms"])
                self.assertEqual(self.g.sent, [])

    def test_same_session_gap_still_exits(self):
        self.row = self.adopt()
        self.step(NOW + 1_000)
        self.step(NOW + 2_000)
        self.step(NOW + 122_000)
        self.assertEqual(len(self.g.sent), 1)
        self.assertEqual(self.g.sent[0]["quantity"], "3")

    def test_stale_quotes_in_session_still_exhaust_grace(self):
        self.row = self.adopt()
        self.step(NOW + 1_000)
        self.step(NOW + 2_000)
        with patch.object(self.g, "_quote", return_value=(*self.g.quote, NOW - 60_000)):
            for offset in range(3_000, 124_000, 10_000):
                result = self.step(NOW + offset)
        self.assertIsNotNone(result["exit_requested_ms"])
        self.step(NOW + 124_000)
        self.assertEqual(len(self.g.sent), 1)
        self.assertEqual(self.g.sent[0]["kind"], "exit")

    def test_prior_session_stale_budget_does_not_leak_into_next_session(self):
        self.row = self.adopt()
        self.step(NOW + 1_000)
        self.step(NOW + 2_000)
        with patch.object(self.g, "_quote", return_value=(*self.g.quote, NOW - 60_000)):
            self.step(NOW + 3_000)
            result = self.step(NOW + 86_400_000)
        self.assertIsNone(result["exit_requested_ms"])
        self.assertEqual(result["unprotected_since_ms"], NOW + 86_400_000)

    def test_reopen_below_stop_still_exits(self):
        self.row = self.adopt()
        self.step(NOW + 1_000)
        self.step(NOW + 2_000)
        self.g.quote = (Decimal("102650"), Decimal("102660"))
        self.step(NOW + 86_400_000)
        self.assertEqual(len(self.g.sent), 1)
        self.assertEqual(self.g.sent[0]["quantity"], "3")

    def test_missing_current_date_quote_has_explicit_diagnostic_and_recovers(self):
        self.row = self.adopt()
        self.step(NOW + 1_000)
        self.g.client.order_book.return_value = SimpleNamespace(status=200, body={
            "rt_cd": "0", "output1": {"aspr_acpt_hour": "100000", "bidp1": "109985", "askp1": "109990"}})
        self.g.client.domestic_intraday_chart.return_value = SimpleNamespace(status=200, body={
            "rt_cd": "0", "output2": [{"stck_bsop_date": "20000101"}]})
        # Exercise production date parsing, not the fixture's _quote override.
        with patch.object(self.g, "_quote", side_effect=lambda asset: ManagedKisGateway._quote(self.g, asset)):
            result = self.step(NOW + 2_000)
        self.assertEqual(result["state"], "DEGRADED")
        self.assertEqual(result["covered_size"], "0")
        self.assertIn("current-session", result["reason"])
        self.assertIn("unverified", result["reason"])
        self.assertIsNone(result["exit_requested_ms"])
        self.assertEqual(self.step(NOW + 400_000)["state"], "PROTECTED")
        self.assertEqual(self.g.sent, [])

    def test_real_calendar_session_continuity(self):
        def ms(value):
            return int(datetime.fromisoformat(value).timestamp() * 1000)
        asset = self.g._asset("kis:069500")
        gateway = ManagedKisGateway(self.g.client)
        for start, end, expected in (
            ("2026-09-28T10:00:00+09:00", "2026-09-28T10:03:00+09:00", True),
            ("2026-09-28T15:20:00+09:00", "2026-09-29T09:01:00+09:00", False),
            ("2026-09-25T15:20:00+09:00", "2026-09-28T09:01:00+09:00", False),
            ("2026-09-28T08:00:00+09:00", "2026-09-28T09:01:00+09:00", False),
        ):
            with self.subTest(start=start, end=end):
                self.assertEqual(gateway._same_execution_session(asset, ms(start), ms(end)), expected)

    def test_rejects_mismatched_or_ambiguous_holdings(self):
        cases = {
            "second buy": lambda g: g.history.append(dict(BUY, odno="0017865399")),
            "partial fill": lambda g: g.history.__setitem__(0, dict(BUY, tot_ccld_qty="2")),
            "quantity drift": lambda g: g.holding.update(hldg_qty="4", ord_psbl_qty="4"),
            "open order": lambda g: g.client.account_pages.__setattr__(
                "return_value", {"output": [{"pdno": "069500", "odno": "1"}]}),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                g = FixtureKisGateway()
                mutate(g)
                row = {"id": "x", "plan": plan(), "adoption": {
                    "venue": "kis", "entry_order_id": "0017865300", "entry_since_ms": NOW - 1}}
                with self.assertRaises(ValueError):
                    verify_kis_adoption(g, row, NOW)

    def test_enqueue_validates_kis_identity(self):
        with self.assertRaises(ValueError):
            self.store.enqueue_adoption("scope", plan(), entry_order_id="0017865300",
                                        stop_order_id=5, live=True, now_ms=NOW,
                                        entry_since_ms=NOW - 1)
        with self.assertRaises(ValueError):
            self.store.enqueue_adoption("scope", plan(), entry_order_id="0017865300",
                                        stop_order_id=None, live=True, now_ms=NOW)


if __name__ == "__main__":
    unittest.main()
