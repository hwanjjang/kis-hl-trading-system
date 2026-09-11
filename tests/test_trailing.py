from decimal import Decimal as D
import unittest

from kis_hl.trailing import Trail, NINE_MINUTES_MS as B


class TrailTests(unittest.TestCase):
    def make(self):
        return Trail.create(entry=D('100'), atr=D('2'), multiple=D('2'), opened_ms=0)

    def test_closed_bars_only_and_equality_crossing(self):
        t = self.make()
        # First observed bucket is incomplete; it cannot raise the watermark.
        self.assertFalse(t.tick(1, D('120'), max_gap_ms=B))
        t.tick(B, D('105'), max_gap_ms=B)
        t.tick(B + 1, D('108'), max_gap_ms=B)
        self.assertEqual(t.threshold, D('96'))
        self.assertTrue(t.tick(2 * B, D('104'), max_gap_ms=B))
        self.assertEqual((t.high, t.threshold), (D('108'), D('104')))

    def test_gap_does_not_promote_incomplete_bar(self):
        t = self.make()
        t.tick(1, D('100'), max_gap_ms=1000)
        t.tick(B, D('120'), max_gap_ms=1000)
        t.tick(2 * B, D('110'), max_gap_ms=1000)
        self.assertEqual(t.threshold, D('96'))

    def test_duplicate_late_and_invalid_ticks_cannot_raise_watermark(self):
        t = self.make()
        t.tick(100, D('100'), max_gap_ms=B)
        for time in [100, 99]:
            self.assertFalse(t.tick(time, D('1000'), max_gap_ms=B))
        for bad in ['NaN', 'Infinity', '0', '-1']:
            with self.assertRaises(ValueError):
                t.tick(101, D(bad), max_gap_ms=B)
        self.assertEqual(t.high, D('100'))

    def test_restart_keeps_threshold_but_discards_partial_bucket(self):
        t = self.make()
        t.tick(1, D('100'), max_gap_ms=B)
        t.tick(B, D('108'), max_gap_ms=B)
        t.tick(2*B, D('105'), max_gap_ms=B)
        restored = Trail.from_dict(t.to_dict())
        restored.disconnect()
        self.assertEqual(restored.threshold, D('104'))
        self.assertTrue(restored.tick(2*B+1, D('104'), max_gap_ms=B))

    def test_bad_initial_risk_rejected(self):
        for atr in ['0', 'NaN', 'Infinity', '60']:
            with self.assertRaises(ValueError):
                Trail.create(entry=D('100'), atr=D(atr), multiple=D('2'), opened_ms=0)
