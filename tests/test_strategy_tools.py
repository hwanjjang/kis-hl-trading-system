import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kis_hl.strategy_tools import evaluate_setup, size_position, ingest_decision, indicator_facts, initial_stop
from kis_hl.managed_execution import ExecutionStore
from kis_hl.strategy_signals import Signals


NOW = int(datetime(2026, 9, 21, tzinfo=timezone.utc).timestamp() * 1000)
DAY = 86_400_000


def bar(start, duration, price):
    return dict(start_ms=start, end_ms=start + duration, complete=True,
                open=str(price), high=str(price + 2), low=str(price - 2), close=str(price + 1))


def snapshot():
    return dict(id="fixture-snapshot", instrument="hl:BTC", source="fixture", currency="USDC",
                asof_ms=NOW, max_age_ms=60000, timeframe_ms=10800000,
                candles=[bar(NOW-21600000, 10800000, 100), bar(NOW-10800000, 10800000, 103)],
                daily_bars=[bar(NOW-DAY*(11-i), DAY, 100+i) for i in range(11)],
                weekly_bars=[bar(NOW-DAY*7*(31-i), DAY*7, 80+i) for i in range(31)],
                history_max_age_ms={"daily": 4*DAY, "weekly": 10*DAY})


def setup(kind="breakout"):
    return dict(setup=kind, snapshot=snapshot(), lookback=1)


class StrategyToolsTests(unittest.TestCase):
    def test_indicators_report_missing_weekly_data_without_losing_atr(self):
        data = snapshot()
        data["weekly_bars"] = []
        result = indicator_facts(data, now_ms=NOW)
        self.assertEqual(result["atr_10d"], "4")
        self.assertIsNone(result["ema_30w"])
        self.assertIn("ema_30w", result["unavailable"])

    def test_initial_stop_uses_asset_class_default_or_explicit_multiple(self):
        self.assertEqual(initial_stop(dict(entry="100", atr="2", asset_class="stock"))["stop"], "94.0")
        self.assertEqual(initial_stop(dict(entry="100", atr="2", multiple="2"))["stop"], "96")
        with self.assertRaises(ValueError):
            initial_stop(dict(entry="3", atr="2", multiple="2"))

    def test_breakout_is_reproducible_and_equality_is_not_a_breakout(self):
        request = setup()
        first = evaluate_setup(request, now_ms=NOW)
        self.assertEqual(first, evaluate_setup(request, now_ms=NOW))
        self.assertTrue(first["predicate_passed"])
        self.assertEqual(first["facts"]["atr_10d"], "4")
        self.assertTrue(first["facts"]["above_30w_ema"])
        request["snapshot"]["candles"][-1]["close"] = "102"
        self.assertFalse(evaluate_setup(request, now_ms=NOW)["predicate_passed"])

    def test_stale_and_unclosed_history_cannot_pass(self):
        for change in ("stale", "weekly", "future"):
            request = setup()
            if change == "stale":
                request["snapshot"]["asof_ms"] = NOW-60001
            elif change == "weekly":
                request["snapshot"]["weekly_bars"][-1]["complete"] = False
            else:
                request["snapshot"]["candles"][-1]["end_ms"] = NOW+1
            result = evaluate_setup(request, now_ms=NOW)
            self.assertFalse(result["predicate_passed"])
            self.assertEqual(result["status"], "unavailable")

    def test_pullback_requires_touch_then_closed_rebound_above_stop(self):
        request = setup("pullback")
        request.update(reference="100", tolerance="2", position=dict(
            id="p1", instrument="hl:BTC", quantity="1", stop="95", opened_ms=NOW-3*DAY,
            asof_ms=NOW, max_age_ms=60000, scope="test"))
        self.assertTrue(evaluate_setup(request, now_ms=NOW)["predicate_passed"])
        request["position"]["stop"] = "104"
        self.assertFalse(evaluate_setup(request, now_ms=NOW)["predicate_passed"])

    def test_rebreakout_uses_only_post_entry_bars(self):
        request = setup("rebreakout")
        request["position"] = dict(id="p1", instrument="hl:BTC", quantity="1", stop="95",
                                   opened_ms=NOW-10800000, asof_ms=NOW, max_age_ms=60000, scope="test")
        result = evaluate_setup(request, now_ms=NOW)
        self.assertFalse(result["predicate_passed"])
        self.assertIn("post-entry", " ".join(result["reasons"]))

    def test_btc_exception_requires_explicit_spot_3h_source(self):
        request = setup("btc_3h")
        request["snapshot"].update(instrument="hl:UBTC/USDC", currency="USDC")
        request["snapshot"]["weekly_bars"] = []
        self.assertTrue(evaluate_setup(request, now_ms=NOW)["predicate_passed"])
        request["snapshot"]["timeframe_ms"] = DAY
        self.assertFalse(evaluate_setup(request, now_ms=NOW)["predicate_passed"])

    def test_sizing_uses_execution_account_units_and_no_floor(self):
        result = size_position(dict(venue="hyperliquid", scope="mainnet:test", currency="USDC",
            capital_evidence=dict(scope="mainnet:test", currency="USDC", asof_ms=NOW, max_age_ms=60000,
                account_mode="unifiedAccount", spot={"balances": [{"coin": "USDC", "token": 0, "total": "999"}]}),
            asof_ms=NOW, max_age_ms=60000, instrument="hl:BTC",
            entry="100", stop="97", units="1", quantity_step="1",
            minimum_quantity="1", minimum_notional="10"), now_ms=NOW)
        self.assertEqual(result["operating_capital"], "9990")
        self.assertEqual(result["quantity"], "33")
        self.assertEqual(result["risk"], "99")
        self.assertFalse(result["order_authorized"])

    def test_btc_exception_keeps_fixed_notional_and_reports_actual_stop_risk(self):
        result = size_position(dict(venue="hyperliquid", scope="mainnet:test", currency="USDC",
            capital_evidence=dict(scope="mainnet:test", currency="USDC", asof_ms=NOW, max_age_ms=60000,
                account_mode="unifiedAccount", spot={"balances": [{"coin": "USDC", "token": 0, "total": "999"}]}),
            asof_ms=NOW, max_age_ms=60000, instrument="hl:BTC",
            entry="100", stop="97", sizing="btc_fixed_80", quantity_step="0.1",
            minimum_quantity="0.1", minimum_notional="10"), now_ms=NOW)
        self.assertEqual(result["quantity"], "0.8")
        self.assertEqual(result["notional"], "80.0")
        self.assertEqual(result["risk"], "2.4")

    def test_decision_links_recomputed_evidence_without_order_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            signals = Signals(ExecutionStore(Path(directory)/"test.sqlite"))
            signals.register(dict(id="trend", version="1", description="Fixture", instruments=["hl:BTC"]))
            record = dict(id="d1", strategy="trend", strategy_version="1", signal_instrument="hl:BTC",
                          execution_instruments=["hl:BTC"], observed_ms=NOW, expires_ms=NOW+1000,
                          rationale="Breakout supported by weekly trend", action="enter", setup_input=setup(),
                          confluence=["Weekly uptrend", "Prior high resistance"], management="Fixed SL and existing trailing")
            result = ingest_decision(signals, record, now_ms=NOW)
            self.assertEqual(result["evidence"]["snapshot_id"], "fixture-snapshot")
            self.assertEqual(signals.store.list(), [])
            self.assertEqual(result, ingest_decision(signals, record, now_ms=NOW))
            conflict = copy.deepcopy(record)
            conflict["setup_input"]["snapshot"]["candles"][-1]["close"] = "105"
            with self.assertRaisesRegex(ValueError, "immutable"):
                ingest_decision(signals, conflict, now_ms=NOW)
            record["id"] = "d2"
            record["setup_input"]["snapshot"]["candles"][-1]["close"] = "102"
            with self.assertRaisesRegex(ValueError, "predicate"):
                ingest_decision(signals, record, now_ms=NOW)

    def test_timing_opinion_is_bound_advisory_evidence(self):
        def opinion(choice="long", confidence="0.81", **overrides):
            return {"tool": "timing_opinion", "provider": "typesafe", "status": "available",
                    "instrument": "hl:BTC", "snapshot_id": "fixture-snapshot", "asof_ms": NOW,
                    "requested_model": "jev-1.13.0", "model": "jev-1.13.0", "input_sha256": "0" * 64,
                    "choice": choice, "probabilities": {k: "0.8" if k == choice else "0.1" for k in ["long", "short", "wait"]},
                    "confidence": confidence, "min_confidence": "0.5", "band": "high",
                    "effective_opinion": choice, "advisory": True, "order_authorized": False, **overrides}

        with tempfile.TemporaryDirectory() as directory:
            signals = Signals(ExecutionStore(Path(directory)/"test.sqlite"))
            signals.register(dict(id="trend", version="1", description="Fixture", instruments=["hl:BTC"]))
            base = dict(strategy="trend", strategy_version="1", signal_instrument="hl:BTC",
                        execution_instruments=["hl:BTC"], observed_ms=NOW, expires_ms=NOW+1000,
                        rationale="Breakout supported by weekly trend", action="enter", setup_input=setup(),
                        confluence=["Weekly uptrend", "Prior high resistance"], management="Fixed SL and existing trailing")
            stored = ingest_decision(signals, {**base, "id": "o1", "timing_opinion": opinion()}, now_ms=NOW)
            self.assertEqual(stored["timing_opinion"]["effective_opinion"], "long")
            self.assertEqual(signals.store.list(), [])
            for name, bad in {
                "instrument": opinion(instrument="hl:ETH"),
                "snapshot": opinion(snapshot_id="other"),
                "timestamp": opinion(asof_ms=NOW-1),
                "missing timestamp": opinion(asof_ms=None),
                "numeric timestamp": opinion(asof_ms=float(NOW)),
                "authority": opinion(order_authorized=True),
                "tool": opinion(tool="other"),
                "gate": opinion(confidence="0.2"),
                "float rounding": opinion(confidence="0.49999999999999999999"),
                "bool confidence": opinion(confidence=True),
                "band": opinion(band="low"),
                "advisory": opinion(advisory=False),
                "provider": opinion(provider="made-up"),
                "no probabilities": opinion(probabilities=None),
                "not argmax": opinion(probabilities={"long": "0", "short": "1", "wait": "0"}),
                "numeric confidence": opinion(confidence=json.loads('{"c": 0.49999999999999999999}')["c"]),
                "numeric probability": opinion(probabilities={"long": 0.8, "short": "0.1", "wait": "0.1"}),
                "numeric min_confidence": opinion(min_confidence=0.5),
                "inexact sum": opinion(probabilities={"long": "1", "short": "0.01000000000000000000000000001", "wait": "0"}),
            }.items():
                with self.subTest(name), self.assertRaisesRegex(ValueError, "[Tt]iming opinion"):
                    ingest_decision(signals, {**base, "id": "bad-" + name, "timing_opinion": bad}, now_ms=NOW)
            unavailable = opinion(status="unavailable", choice=None, probabilities=None, confidence=None,
                                  band=None, effective_opinion=None, model=None, reason="HTTP 529")
            for name, forged in {
                "timestamp": {"asof_ms": NOW-1},
                "provider": {"provider": "forged"}, "advisory": {"advisory": False},
                "choice": {"choice": "long"}, "probabilities": {"probabilities": {"long": "1"}},
                "confidence": {"confidence": "0.9"}, "band": {"band": "high"}, "reason": {"reason": ""},
            }.items():
                with self.subTest("unavailable " + name), self.assertRaisesRegex(ValueError, "[Tt]iming opinion"):
                    ingest_decision(signals, {**base, "id": "u-" + name, "opinion_note": "note",
                                              "timing_opinion": {**unavailable, **forged}}, now_ms=NOW)
            for i, disagreeing in enumerate([opinion("wait"), opinion("short"), unavailable,
                    opinion(confidence="0.1", min_confidence="0.01", band="medium"),
                    opinion(confidence="0.49999999999999999999", min_confidence="0.01", band="medium")]):
                record = {**base, "id": f"n{i}", "timing_opinion": disagreeing}
                with self.assertRaisesRegex(ValueError, "opinion_note"):
                    ingest_decision(signals, record, now_ms=NOW)
                accepted = ingest_decision(signals, {**record, "opinion_note": "Weekly breakout outweighs caution"}, now_ms=NOW)
                self.assertEqual(accepted["opinion_note"], "Weekly breakout outweighs caution")
            boundary = {**base, "id": "boundary", "timing_opinion":
                        opinion(confidence="0.5", min_confidence="0.01", band="medium")}
            self.assertEqual(ingest_decision(signals, boundary, now_ms=NOW)["action"], "enter")
            hold = {**base, "id": "h1", "action": "hold", "timing_opinion": opinion("short")}
            self.assertEqual(ingest_decision(signals, hold, now_ms=NOW)["action"], "hold")


if __name__ == "__main__":
    unittest.main()
