"""Issue 27 offline account-total and bounded add regression fixtures."""
import copy
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from kis_hl.managed_execution import ExecutionStore, Supervisor
from kis_hl.strategy_signals import Signals
from kis_hl.strategy_tools import size_position
from tests.test_managed_execution import Gateway, plan
from tests.test_strategy_tools import NOW, DAY, setup


def capital(scope="scope", total="1000", now=NOW):
    return dict(scope=scope, currency="USDC", asof_ms=now, max_age_ms=60000,
                account_mode="unifiedAccount", source="Hyperliquid account readback",
                spot={"balances": [{"coin": "USDC", "token": 0, "total": total, "hold": "0"}]},
                perp_segment={"marginSummary": {"accountValue": "123"}})


def sizing(**changes):
    return dict(venue="hyperliquid", scope="scope", currency="USDC", instrument="hl:ETH",
                asof_ms=NOW, max_age_ms=60000, entry="100", stop="96", units="1",
                quantity_step="0.01", minimum_quantity="0.01", minimum_notional="10",
                capital_evidence=capital(), **changes)


class AddGateway(Gateway):
    native_trailing = True

    def __init__(self):
        super().__init__()
        self.fill_sizes = {}
        self.balance = capital()
        self.available = "10000"
        self.price = "100"
        self.protective_filled = "0"

    def preflight(self, p, now, **kwargs):
        return {**super().preflight(p, now), "position": self.size,
                "open_orders": [{"oid": k} for k, v in self.orders.items() if v["status"] == "open"],
                "capital_evidence": self.balance, "available_notional": self.available,
                "trailing_price_step": "0.01"}

    def snapshot(self, row, attempts, now):
        return {**super().snapshot(row, attempts, now), "price": self.price,
                "fills_by_attempt": dict(self.fill_sizes), "trailing_price_step": "0.01",
                "protective_filled": self.protective_filled}

    def submit(self, row, attempt):
        result = super().submit(row, attempt)
        if attempt["kind"] == "trailing":
            self.orders[attempt["id"]].update(active=True, retracement_unit="quote",
                retracement=attempt["retracement"], best_price=self.price)
        return result

    def fill(self, attempt, quantity, *, terminal=True):
        previous = Decimal(self.fill_sizes.get(attempt["id"], "0"))
        delta = Decimal(quantity) - previous
        self.fill_sizes[attempt["id"]] = quantity
        self.filled = str(Decimal(self.filled) + delta)
        self.size = str(Decimal(self.size) + delta)
        order = self.orders[attempt["id"]]
        order.update(status="filled" if terminal else "open",
                     size=str(Decimal(attempt["quantity"]) - Decimal(quantity)))


def protected(store, gateway, *, native=False):
    p = plan()
    p.update(instrument="hl:ETH", signal_instrument="hl:ETH", fixed_stop_price="96",
             expires_ms=NOW+60000, max_quote_age_ms=60000,
             trailing_provider="native" if native else "local", local_trailing_backup=native,
             max_notional="10000", max_loss="100", max_portfolio_notional="20000",
             max_correlated_notional="20000")
    opened = NOW-3*DAY
    row = store.enqueue("scope", p, live=True, now_ms=opened-1000)
    worker = Supervisor(store, gateway, live=True)
    worker.step(row["id"], opened)
    gateway.fill(gateway.sent[0], "1")
    for i in range(1, 5):
        worker.step(row["id"], opened+i)
    return store.get(row["id"]), worker


def add_signal(signals, row):
    signals.register(dict(id="fixture", version="1", description="Fixture", instruments=["hl:ETH"]))
    evidence = setup("rebreakout")
    evidence["snapshot"]["instrument"] = "hl:ETH"
    evidence["position"] = dict(id=row["id"], scope="scope", instrument="hl:ETH", quantity="1",
                                stop="96", opened_ms=row["first_fill_ms"], asof_ms=NOW, max_age_ms=60000)
    signal = dict(id="add-once", strategy="fixture", strategy_version="1", signal_instrument="hl:ETH",
                  execution_instruments=["hl:ETH"], action="add", setup_input=evidence,
                  observed_ms=NOW, expires_ms=NOW+50000, rationale="Confirmed rebreakout")
    signals.ingest(signal, now_ms=NOW)
    return signal


def add_plan(row):
    return {**row["plan"], "action": "add", "position_id": row["id"], "quantity": "0.5",
            "units": "0.02", "quantity_step": "0.01", "expected_size": "1", "expected_entry_filled": "1",
            "capital_evidence": capital(), "condition_snapshot_id": "fixture-snapshot",
            "condition_bar_end_ms": NOW, "expires_ms": NOW+40000}


class CapitalTests(unittest.TestCase):
    def test_extra_collateral_and_liabilities_fail_closed(self):
        for field in ("borrowed", "supplied"):
            for value in ("1", "-1", None, "NaN", {}, "bad"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    request = sizing()
                    request["capital_evidence"]["spot"]["balances"][0][field] = value
                    size_position(request, now_ms=NOW)
        for escrows in (None, {}, [None], [{}],
                        [dict(coin="HYPE", token=150, total="1")],
                        [dict(coin="USDC", token=0, total="NaN")]):
            with self.subTest(escrows=escrows), self.assertRaises(ValueError):
                request = sizing()
                request["capital_evidence"]["spot"]["evmEscrows"] = escrows
                size_position(request, now_ms=NOW)
        for mode in (True, None, "false"):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                request = sizing()
                request["capital_evidence"]["spot"]["portfolioMarginEnabled"] = mode
                size_position(request, now_ms=NOW)

    def test_zero_optional_components_do_not_duplicate_capital(self):
        request = sizing()
        spot = request["capital_evidence"]["spot"]
        spot["balances"][0].update(borrowed="0", supplied="0.0")
        spot.update(portfolioMarginEnabled=False,
                    evmEscrows=[dict(coin="USDC", token=0, total="0")])
        self.assertEqual(size_position(request, now_ms=NOW)["risk_budget"], "100.00")

    def test_total_not_perp_segment_is_capital_source(self):
        result = size_position(sizing(equity="123"), now_ms=NOW)
        self.assertEqual(result["equity"], "1000")
        self.assertEqual(result["operating_capital"], "10000")
        self.assertEqual(result["risk_budget"], "100.00")

    def test_ambiguous_mode_overlap_unknown_asset_and_account_rejected(self):
        for change in ("mode", "overlap", "asset", "scope", "missing"):
            with self.subTest(change=change), self.assertRaises(ValueError):
                request = sizing(equity="1000")
                ev = request["capital_evidence"]
                if change == "mode": ev["account_mode"] = "default"
                if change == "overlap": ev["spot"]["balances"] *= 2
                if change == "asset": ev["spot"]["balances"].append(dict(coin="HYPE", token=150, total="1"))
                if change == "scope": ev["scope"] = "other"
                if change == "missing": del request["capital_evidence"]
                size_position(request, now_ms=NOW)


class ConditionalAddTests(unittest.TestCase):
    def test_terminated_old_trail_retains_full_overlay_across_reopen(self):
        for status in ("canceled", "rejected", "expired"):
            with self.subTest(status=status):
                # Reuse the complete partial-fill/overlay lifecycle fixture.
                case = ConditionalAddTests()
                case.setUp()
                try:
                    case.test_native_overlay_preserves_old_watermark_and_covers_combined_size()
                    trails = [a for a in case.g.sent if a["kind"] == "trailing"]
                    case.g.orders[trails[0]["id"]]["status"] = status
                    store = ExecutionStore(case.store.path)
                    worker = Supervisor(store, case.g, live=True)
                    for tick in (20, 21):
                        row = worker.step(case.row["id"], NOW+tick)
                        self.assertEqual(row["state"], "PROTECTED")
                        self.assertFalse(row["exit_requested_ms"])
                        self.assertEqual(Decimal(row["trailing_covered_size"]), Decimal("1.5"))
                    self.assertEqual(len([a for a in case.g.sent if a["kind"] == "trailing"]), 2)
                    self.assertFalse(any(a["kind"] in {"exit", "cancel"} for a in case.g.sent))
                finally:
                    case.doCleanups()

    def test_terminated_trail_without_verified_full_overlay_exits(self):
        for change in ({"size": "1"}, {"active": False},
                       {"trailing_readback_error": "Unverified condition"},
                       {"status": "canceled"}):
            with self.subTest(change=change):
                case = ConditionalAddTests()
                case.setUp()
                try:
                    case.test_native_overlay_preserves_old_watermark_and_covers_combined_size()
                    trails = [a for a in case.g.sent if a["kind"] == "trailing"]
                    case.g.orders[trails[0]["id"]]["status"] = "canceled"
                    case.g.orders[trails[1]["id"]].update(change)
                    case.worker.step(case.row["id"], NOW+20)
                    self.assertEqual(case.g.sent[-1]["kind"], "exit")
                    self.assertEqual(case.g.sent[-1]["quantity"], "1.5")
                finally:
                    case.doCleanups()

    def test_transient_read_recovers_once_after_reopen(self):
        from kis_hl.hyperliquid.client import TransientInfoError
        self.authorize()
        original = self.g.preflight
        def fail(*args, **kwargs):
            raise TransientInfoError("Temporary read unavailable")
        self.g.preflight = fail
        self.worker.step(self.row["id"], NOW+10)
        self.assertEqual(self.store.tranches(self.row["id"])[0]["status"], "QUEUED")
        self.assertFalse(any(a["kind"] == "add" for a in self.g.sent))
        self.g.preflight = original
        self.store = ExecutionStore(self.path)
        self.worker = Supervisor(self.store, self.g, live=True)
        for tick in (11, 12):
            self.worker.step(self.row["id"], NOW+tick)
        self.assertEqual(len([a for a in self.g.sent if a["kind"] == "add"]), 1)

    def test_transient_read_does_not_extend_authority(self):
        from kis_hl.hyperliquid.client import TransientInfoError
        self.authorize()
        calls = []
        def fail(*args, **kwargs):
            calls.append(1)
            raise TransientInfoError("Temporary read unavailable")
        self.g.preflight = fail
        self.worker.step(self.row["id"], NOW+10)
        self.worker.step(self.row["id"], self.plan["expires_ms"]+1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.store.tranches(self.row["id"])[0]["status"], "REJECTED")
        self.assertFalse(any(a["kind"] == "add" for a in self.g.sent))

    def test_identity_runtime_error_is_not_retried(self):
        self.authorize()
        def fail(*args, **kwargs):
            raise RuntimeError("Hyperliquid activeAssetData identity mismatch")
        self.g.preflight = fail
        for tick in (10, 11):
            self.worker.step(self.row["id"], NOW+tick)
        self.assertEqual(self.store.tranches(self.row["id"])[0]["status"], "REJECTED")
        self.assertFalse(any(a["kind"] == "add" for a in self.g.sent))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/"state.sqlite"
        self.store = ExecutionStore(self.path)
        self.g = AddGateway()
        self.row, self.worker = protected(self.store, self.g)
        self.signals = Signals(self.store)
        self.signal = add_signal(self.signals, self.row)
        self.plan = add_plan(self.row)

    def authorize(self):
        return self.signals.execute("add-once", "scope", self.plan, manual=True, live=True, now_ms=NOW+5)

    def test_partial_add_complete_and_reopen_replay(self):
        self.authorize()
        self.worker.step(self.row["id"], NOW+10)
        adds = [a for a in self.g.sent if a["kind"] == "add"]
        self.assertEqual(len(adds), 1)
        self.g.fill(adds[0], "0.2", terminal=False)
        for i in (11, 12): self.worker.step(self.row["id"], NOW+i)
        self.assertEqual(Decimal(self.store.get(self.row["id"])["covered_size"]), Decimal("1.2"))
        self.g.fill(adds[0], "0.5")
        for i in (13, 14): self.worker.step(self.row["id"], NOW+i)
        current = self.store.get(self.row["id"])
        self.assertEqual(current["state"], "PROTECTED")
        self.assertEqual(Decimal(current["covered_size"]), Decimal("1.5"))
        reopened = ExecutionStore(self.path)
        Signals(reopened).execute("add-once", "scope", self.plan, manual=True, live=True, now_ms=NOW+20)
        Supervisor(reopened, self.g, live=True).step(self.row["id"], NOW+21)
        self.assertEqual(len([a for a in self.g.sent if a["kind"] == "add"]), 1)
        tranche = reopened.tranches(self.row["id"])[0]
        self.assertEqual(Decimal(tranche["filled"]), Decimal("0.5"))
        self.assertEqual(tranche["plan"]["units"], "0.02")
        self.assertEqual(current["trail"]["distance"], self.row["trail"]["distance"])

    def test_authorization_table(self):
        for case in ("unfinished", "stale", "missing", "expired", "exposure", "fixed-stop", "bar-id",
                     "max_quote_age_ms", "protection_grace_ms", "max_exit_attempts", "slippage"):
            with self.subTest(case=case):
                p = copy.deepcopy(self.plan)
                signal = copy.deepcopy(self.signal)
                signal["id"] = "bad-"+case
                if case == "unfinished": signal["setup_input"]["snapshot"]["candles"][-1]["complete"] = False
                if case == "stale": signal["setup_input"]["snapshot"]["asof_ms"] = NOW-60001
                if case == "expired": p["expires_ms"] = NOW
                if case == "exposure": p["expected_size"] = "2"
                if case == "fixed-stop": p["fixed_stop_price"] = "95"
                if case == "bar-id": p["condition_bar_end_ms"] = NOW-1
                if case in {"max_quote_age_ms", "protection_grace_ms", "max_exit_attempts"}: p[case] = 1
                if case == "slippage": p[case] = "0.005"
                self.signals.ingest(signal, now_ms=NOW)
                before = len(self.g.sent)
                with self.assertRaises((ValueError, RuntimeError)):
                    self.signals.execute(signal["id"], "scope", p, manual=case != "missing", live=True, now_ms=NOW+5)
                self.assertEqual(len(self.g.sent), before)

    def test_expired_or_changed_fresh_state_preserves_existing_protection(self):
        self.authorize()
        original_stops = [a["id"] for a in self.g.sent if a["kind"] == "stop"]
        self.g.available = "1"
        self.worker.step(self.row["id"], NOW+10)
        self.assertFalse(any(a["kind"] == "add" for a in self.g.sent))
        self.assertTrue(all(self.g.orders[k]["status"] == "open" for k in original_stops))
        self.assertEqual(self.store.get(self.row["id"])["state"], "PROTECTED")

    def test_fresh_gates_reject_without_canceling_protection(self):
        for case in ("expired", "exposure", "balance", "stale-balance", "paused"):
            with self.subTest(case=case):
                self.setUp()
                self.authorize()
                if case == "exposure": self.g.size = "0.9"
                if case == "balance": self.g.balance = capital(total="900")
                if case == "stale-balance": self.g.balance = capital(now=NOW-60001)
                if case == "paused": self.store.set_entries("scope", False)
                self.worker.step(self.row["id"], NOW+(40001 if case == "expired" else 10))
                self.assertFalse(any(a["kind"] in {"add", "cancel"} for a in self.g.sent))
                self.assertEqual(self.store.tranches(self.row["id"])[0]["status"], "REJECTED")

    def test_unknown_add_outcome_is_never_resent_after_restart(self):
        self.authorize()
        original = self.g.submit
        def timeout(row, a):
            if a["kind"] == "add":
                self.g.sent.append(dict(a))
                raise TimeoutError("Unknown outcome")
            return original(row, a)
        self.g.submit = timeout
        self.worker.step(self.row["id"], NOW+10)
        reopened = ExecutionStore(self.path)
        for tick in (11, 12, 13): Supervisor(reopened, self.g, live=True).step(self.row["id"], NOW+tick)
        self.assertEqual(len([a for a in self.g.sent if a["kind"] == "add"]), 1)
        self.assertEqual(reopened.tranches(self.row["id"])[0]["status"], "UNKNOWN")

    def test_failed_incremental_sl_reaches_bounded_exit_retaining_existing_sl(self):
        self.authorize()
        self.worker.step(self.row["id"], NOW+10)
        add = self.g.sent[-1]
        self.g.fill(add, "0.5")
        old_stop = next(a for a in self.g.sent if a["kind"] == "stop")
        original = self.g.submit
        def reject(row, a):
            if a["kind"] == "stop":
                self.g.sent.append(dict(a))
                return {"status": "rejected"}
            return original(row, a)
        self.g.submit = reject
        for tick in (11, 12, 13, 14): self.worker.step(self.row["id"], NOW+tick)
        self.assertTrue(self.store.get(self.row["id"])["exit_requested_ms"])
        self.assertTrue(any(a["kind"] == "exit" for a in self.g.sent))
        self.assertEqual(self.g.orders[old_stop["id"]]["status"], "open")
        self.assertFalse(any(a["kind"] == "cancel" for a in self.g.sent))

    def native_fixture(self):
        self.store = ExecutionStore(Path(self.tmp.name)/"native.sqlite")
        self.g = AddGateway()
        self.row, self.worker = protected(self.store, self.g, native=True)
        self.signals = Signals(self.store)
        add_signal(self.signals, self.row)
        self.plan = add_plan(self.row)

    def test_native_overlay_preserves_old_watermark_and_covers_combined_size(self):
        self.native_fixture()
        old_trail = next(a for a in self.g.sent if a["kind"] == "trailing")
        self.g.orders[old_trail["id"]]["best_price"] = "103"
        self.authorize()
        self.worker.step(self.row["id"], NOW+10)
        add = self.g.sent[-1]
        self.assertEqual(add["kind"], "add")
        self.g.fill(add, "0.2", terminal=False)
        for tick in (11, 12): self.worker.step(self.row["id"], NOW+tick)
        current = self.store.get(self.row["id"])
        self.assertEqual(Decimal(current["covered_size"]), Decimal("1.2"))
        self.assertEqual(Decimal(current["local_trailing_covered_size"]), Decimal("1.2"))
        self.g.fill(add, "0.5")
        for tick in (13, 14, 15): self.worker.step(self.row["id"], NOW+tick)
        current = self.store.get(self.row["id"])
        self.assertEqual(current["state"], "PROTECTED")
        self.assertEqual(Decimal(current["trailing_covered_size"]), Decimal("1.5"))
        self.assertEqual(self.g.orders[old_trail["id"]]["best_price"], "103")
        self.assertEqual(self.g.orders[old_trail["id"]]["status"], "open")
        self.assertEqual([Decimal(a["quantity"]) for a in self.g.sent if a["kind"] == "trailing"], [Decimal(1), Decimal("1.5")])
        self.assertEqual(current["trail"]["distance"], self.row["trail"]["distance"])

    def test_partial_native_fill_then_partial_local_exit_closes_all_residual(self):
        self.test_native_overlay_preserves_old_watermark_and_covers_combined_size()
        self.g.size = "1.3"
        self.g.protective_filled = "0.2"
        self.worker.step(self.row["id"], NOW+20)
        first = [a for a in self.g.sent if a["kind"] == "exit"][-1]
        self.assertEqual(Decimal(first["quantity"]), Decimal("1.3"))
        self.g.orders[first["id"]]["status"] = "canceled"
        # A partial local fill of .5 and another native fill of .3 compete.
        self.g.size = "0.5"
        self.g.protective_filled = "0.5"
        self.worker.step(self.row["id"], NOW+21)
        second = [a for a in self.g.sent if a["kind"] == "exit"][-1]
        self.assertEqual(Decimal(second["quantity"]), Decimal("0.5"))
        self.g.orders[second["id"]]["status"] = "filled"
        self.g.size = "0"
        self.g.orders["unrelated"] = dict(status="open", size="1")
        for tick in (22, 23): self.worker.step(self.row["id"], NOW+tick)
        self.assertEqual(self.store.get(self.row["id"])["state"], "CLOSED")
        self.assertEqual(self.g.orders["unrelated"]["status"], "open")

    def test_failed_native_overlay_retains_sl_and_blocks_more_risk(self):
        self.native_fixture()
        self.authorize()
        self.worker.step(self.row["id"], NOW+10)
        self.g.fill(self.g.sent[-1], "0.5")
        original = self.g.submit
        def reject(row, a):
            if a["kind"] == "trailing":
                self.g.sent.append(dict(a))
                return {"status": "rejected"}
            return original(row, a)
        self.g.submit = reject
        for tick in (11, 12, 13): self.worker.step(self.row["id"], NOW+tick)
        row = self.store.get(self.row["id"])
        self.assertEqual(row["state"], "INTERVENTION")
        self.assertEqual(Decimal(row["covered_size"]), Decimal("1.5"))
        self.assertFalse(any(a["kind"] in {"cancel", "exit"} for a in self.g.sent))

    def test_partially_filled_initial_entry_can_add_without_old_grace_exit(self):
        self.native_fixture()
        # The initial approved entry was larger, but terminal cancellation left one unit.
        owner = self.store.get(self.row["id"])
        owner["plan"]["quantity"] = "2"
        self.store.save(owner, NOW)
        entry = next(a for a in self.store.attempts(owner["id"]) if a["kind"] == "entry")
        self.store.update_attempt(entry, quantity="2", status="CANCELED")
        self.g.orders[entry["id"]].update(status="canceled", size="1")
        self.authorize()
        self.worker.step(owner["id"], NOW+10)
        self.g.fill(self.g.sent[-1], "0.5")
        for tick in (11, 12, 13): self.worker.step(owner["id"], NOW+tick)
        result = self.store.get(owner["id"])
        self.assertEqual(result["state"], "PROTECTED")
        self.assertEqual(Decimal(result["trailing_covered_size"]), Decimal("1.5"))
        self.assertFalse(any(a["kind"] == "exit" for a in self.g.sent))

    def test_signal_and_grant_expiry_bound_add_lifecycle(self):
        self.plan["expires_ms"] = NOW+50001
        with self.assertRaisesRegex(ValueError, "expiry"):
            self.authorize()
        self.plan["expires_ms"] = NOW+40000
        base = dict(id="grant", scope="scope", strategy="fixture", strategy_version="1",
                    instruments=["hl:ETH"], max_notional="100", max_intents=1, live=True,
                    actions=["add"], signal_ids=["add-once"], position_ids=[self.row["id"]])
        for case, change in (("short", {"expires_ms": NOW+20}),
                             ("entry-only", {"expires_ms": NOW+50000, "actions": ["enter"]})):
            self.signals.grant({**base, "id": case, **change}, now_ms=NOW)
            with self.assertRaises(ValueError):
                self.signals.execute("add-once", "scope", self.plan, grant_id=case, live=True, now_ms=NOW+5)
        self.signals.grant({**base, "expires_ms": NOW+50000}, now_ms=NOW)
        self.signals.execute("add-once", "scope", self.plan, grant_id="grant", live=True, now_ms=NOW+5)
        self.signals.revoke("grant")
        self.worker.step(self.row["id"], NOW+10)
        self.assertFalse(any(a["kind"] == "add" for a in self.g.sent))
        self.assertEqual(self.store.tranches(self.row["id"])[0]["status"], "REJECTED")
