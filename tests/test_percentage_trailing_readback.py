"""Percentage readback is opt-in; quote-distance callers remain strict."""
import unittest
from kis_hl.hyperliquid.trailing import trailing_readback


class PercentageTrailingReadbackTests(unittest.TestCase):
    def order(self, condition="retracement 8.35%, best 2800"):
        return {"orderType": "Trailing Stop Market", "isTrigger": True,
                "reduceOnly": True, "side": "A", "triggerCondition": condition}

    def test_exchange_float_artifact_preserves_policy_and_watermark(self):
        result = trailing_readback(self.order(
            "Activation immediate, retracement 3.1300000000000003%, best 2682.8"),
            retracement="3.13", retracement_unit="percent")
        self.assertEqual(result["retracement"], "3.13")
        self.assertEqual(result["best_price"], "2682.8")
        self.assertEqual(result["trigger_price"], "2598.82836")

    def test_percent_readback_truncates_without_rounding(self):
        result = trailing_readback(self.order("retracement 3.1399%, best 2800"),
            retracement="3.13", retracement_unit="percent")
        self.assertEqual(result["retracement"], "3.13")
        self.assertEqual(result["best_price"], "2800")

    def test_explicit_percent_policy_preserves_observed_best(self):
        result = trailing_readback(self.order(), retracement="8.35", retracement_unit="percent")
        self.assertEqual(result["best_price"], "2800")
        self.assertEqual(result["trigger_price"], "2566.2")

    def test_two_decimal_readback_does_not_accept_changed_policy(self):
        with self.assertRaises(ValueError):
            trailing_readback(self.order("retracement 3.14%, best 2800"),
                retracement="3.13", retracement_unit="percent")

    def test_truncation_does_not_accept_invalid_raw_bounds(self):
        for value in ("100.00000000000001", "0.0099", "NaN", "Infinity", "-3.13"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                trailing_readback(self.order(f"retracement {value}%, best 2800"),
                    retracement="3.13", retracement_unit="percent")

    def test_signed_input_does_not_gain_readback_truncation(self):
        from kis_hl.hyperliquid.trailing import retracement_wire
        self.assertEqual(retracement_wire("3.1399", "percent"), {"pct": "3.1399%"})
        with self.assertRaises(ValueError):
            retracement_wire("3.1300000000000003", "percent")

    def test_quote_readback_keeps_full_distance_precision(self):
        result = trailing_readback(self.order("retracement 3.1399, best 2800"),
            retracement="3.1399")
        self.assertEqual(result["retracement"], "3.1399")

    def test_default_quote_reader_still_rejects_percentage(self):
        with self.assertRaises(ValueError):
            trailing_readback(self.order(), retracement="8.35")

    def test_mismatched_percentage_rejected(self):
        with self.assertRaises(ValueError):
            trailing_readback(self.order(), retracement="9", retracement_unit="percent")

    def test_delayed_activation_remains_rejected(self):
        with self.assertRaises(ValueError):
            trailing_readback(self.order("retracement 8.35%, best 2800, activation above 2700"),
                              retracement="8.35", retracement_unit="percent")

    def test_waiting_percentage_does_not_assert_coverage(self):
        result = trailing_readback(self.order("retracement 8.35%, best waiting"),
                                   retracement="8.35", retracement_unit="percent")
        self.assertFalse(result["active"])
        self.assertNotIn("trigger_price", result)

    def test_invalid_policy_rejected(self):
        for unit, value in (("bogus", "8.35"), ("percent", "100"), ("percent", "0.00001")):
            with self.subTest(unit=unit, value=value), self.assertRaises(ValueError):
                trailing_readback(self.order(), retracement=value, retracement_unit=unit)
