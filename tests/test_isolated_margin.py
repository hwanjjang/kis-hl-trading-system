"""Advisory margin at the fixed stop; no execution or account transfers."""
import copy
import unittest
from decimal import Decimal as D

from kis_hl import risk
from kis_hl.strategy_tools import size_position
from tests.test_conditional_add import sizing
from tests.test_strategy_tools import NOW


def evidence(**changes):
    result = dict(scope="scope", instrument="hl:ETH", currency="USDC", asof_ms=NOW,
                max_age_ms=60000, mode="isolated", leverage="10",
                allocated_margin="100", allocation_basis="proposed_tranche_at_entry",
                meta={"universe": [{"name": "ETH", "maxLeverage": 10}]})
    result.update(changes)
    return result


class MarginTests(unittest.TestCase):
    def calculate(self, **changes):
        args = dict(quantity="10", entry="100", stop="90", leverage="10",
                    allocated_margin="100", margin_tiers=[{"lowerBound": "0", "maxLeverage": 10}])
        args.update(changes)
        return risk.calculate_isolated_margin(**args)

    def test_loss_plus_maintenance_and_initial_margin_are_separate(self):
        result = self.calculate()
        self.assertEqual(result["initial_margin"], D("100"))
        self.assertEqual(result["maintenance_at_stop"], D("45"))
        self.assertEqual(result["required_margin"], D("145"))
        self.assertEqual(result["shortfall"], D("45"))
        self.assertEqual(self.calculate(allocated_margin="200")["shortfall"], 0)
        # A tight stop still needs initial margin; operating capital is not leverage.
        self.assertEqual(self.calculate(stop="99")["required_margin"], D("100"))

    def test_short_stop_and_explicit_buffer(self):
        result = self.calculate(side="short", stop="110", buffer="5")
        self.assertEqual(result["maintenance_at_stop"], D("55"))
        self.assertEqual(result["required_margin"], D("160"))
        self.assertEqual(result["shortfall"], D("60"))

    def test_tiers_are_continuous_and_selected_at_stop_notional(self):
        tiers = [{"lowerBound": "0", "maxLeverage": 20},
                 {"lowerBound": "1000", "maxLeverage": 10}]
        result = self.calculate(side="short", stop="110", margin_tiers=tiers)
        self.assertEqual(result["maintenance_at_stop"], D("30"))
        self.assertEqual(result["required_margin"], D("130"))
        result = self.calculate(entry="110", stop="100", margin_tiers=tiers)
        self.assertEqual(result["maintenance_at_stop"], D("25"))

    def test_invalid_inputs_cannot_produce_a_margin_requirement(self):
        bad = [{"quantity": "0"}, {"entry": None}, {"stop": "101"},
               {"side": "short", "stop": "99"}, {"side": "other"},
               {"allocated_margin": "-1"}, {"buffer": "NaN"}, {"buffer": "-1"},
               {"leverage": "0"}, {"leverage": "1.5"},
               {"margin_tiers": []},
               {"margin_tiers": [{"lowerBound": "1", "maxLeverage": 10}]},
               {"margin_tiers": [{"lowerBound": "0", "maxLeverage": 0}]},
               {"margin_tiers": [{"lowerBound": "0", "maxLeverage": 10},
                                  {"lowerBound": "100", "maxLeverage": 20}]}]
        for changes in bad:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.calculate(**changes)


class MarginSizingTests(unittest.TestCase):
    def test_sizing_reports_shortfall_without_changing_quantity_or_authority(self):
        request = sizing()
        request["stop"] = "90"
        plain = size_position(request, now_ms=NOW)
        request["margin_evidence"] = evidence()
        result = size_position(request, now_ms=NOW)
        report = result["isolated_margin"]
        self.assertEqual(report["status"], "available")
        self.assertEqual(D(report["required_margin"]), D("145"))
        self.assertEqual(D(report["shortfall"]), D("45"))
        self.assertEqual(result["quantity"], plain["quantity"])
        self.assertFalse(result["order_authorized"])

    def test_explicit_metadata_table_overrides_asset_max_leverage(self):
        request = sizing()
        request.update(stop="110", side="short")
        request["margin_evidence"] = evidence()
        request["margin_evidence"]["meta"] = {
            "universe": [{"name": "ETH", "maxLeverage": 20, "marginTableId": 51}],
            "marginTables": [[51, {"marginTiers": [
                {"lowerBound": "0", "maxLeverage": 20},
                {"lowerBound": "1000", "maxLeverage": 10}]}]]}
        self.assertEqual(D(size_position(request, now_ms=NOW)["isolated_margin"]["maintenance_at_stop"]), D("30"))

    def test_unavailable_or_mismatched_evidence_does_not_invent_a_report(self):
        variants = [None, {}, evidence(scope="other"), evidence(instrument="hl:BTC"),
                    evidence(currency="KRW"), evidence(asof_ms=NOW-60001),
                    evidence(allocation_basis="existing_position"), evidence(meta={}),
                    evidence(meta={"universe": [{"name": "ETH", "maxLeverage": 20, "marginTableId": 51}]}),
                    evidence(meta={"universe": [{"name": "ETH", "maxLeverage": 20, "marginTableId": 50}]}),
                    evidence(meta={"universe": [{"name": "ETH", "maxLeverage": 20, "marginTableId": 10}]}),
                    evidence(meta={"universe": [{"name": "ETH", "maxLeverage": 20, "marginTableId": 51}],
                                   "marginTables": [[51, {"marginTiers": [{"lowerBound": "0", "maxLeverage": 10}]}]]}),
                    evidence(allocated_margin="NaN")]
        for variant in variants:
            with self.subTest(evidence=variant):
                request = sizing()
                request["margin_evidence"] = copy.deepcopy(variant)
                result = size_position(request, now_ms=NOW)
                self.assertEqual(result["isolated_margin"]["status"], "unavailable")
                self.assertTrue(result["isolated_margin"]["reasons"])
                self.assertFalse(result["order_authorized"])

    def test_btc_exception_reports_margin_for_actual_fixed_notional_quantity(self):
        request = sizing()
        request.update(instrument="hl:BTC", sizing="btc_fixed_80", stop="90")
        del request["units"]
        request["margin_evidence"] = evidence(instrument="hl:BTC", allocated_margin="8",
            meta={"universe": [{"name": "BTC", "maxLeverage": 10}]})
        report = size_position(request, now_ms=NOW)["isolated_margin"]
        self.assertEqual(D(report["entry_notional"]), D("80"))
        self.assertEqual(D(report["required_margin"]), D("11.6"))

    def test_missing_margin_does_not_hide_valid_size_and_zero_size_is_unavailable(self):
        result = size_position(sizing(), now_ms=NOW)
        self.assertEqual(result["isolated_margin"]["status"], "unavailable")
        request = sizing(margin_evidence=evidence())
        request["quantity_step"] = "1000"
        result = size_position(request, now_ms=NOW)
        self.assertTrue(result["below_minimum"])
        self.assertEqual(result["isolated_margin"]["status"], "unavailable")

    def test_cross_margin_is_explicitly_not_applicable(self):
        result = size_position(sizing(margin_evidence=evidence(mode="cross")), now_ms=NOW)
        self.assertEqual(result["isolated_margin"]["status"], "not_applicable")

    def test_selected_leverage_is_reported_without_a_new_execution_guard(self):
        result = size_position(sizing(margin_evidence=evidence(leverage="20")), now_ms=NOW)
        self.assertEqual(result["isolated_margin"]["status"], "available")
        self.assertTrue(result["isolated_margin"]["leverage_exceeds_market_max"])
