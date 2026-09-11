from pathlib import Path
import tempfile
import unittest

from kis_hl.trailing_storage import TrailStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = TrailStore(Path(self.tmp.name)/'state.sqlite')

    def row(self, mode='paper'):
        return self.store.enroll({'account':'acct','network':'test','coin':'BTC','mode':mode,'state':'PROTECTED','size':'1','trail':{}})

    def test_modes_isolated_and_active_generation_unique(self):
        a = self.row()
        self.row('live')
        with self.assertRaisesRegex(RuntimeError, 'already managed'):
            self.row()
        self.assertEqual(self.store.get(a['id'])['mode'], 'paper')

    def test_exit_decision_is_atomic_unique_and_survives_reopen(self):
        a = self.row()
        a['trail']={'threshold':'104'}
        self.store.decide_exit(a, now_ms=10)
        recovered=TrailStore(self.store.path).get(a['id'])
        self.assertEqual(recovered['state'], 'EXIT_PENDING')
        self.assertEqual(recovered['trail']['threshold'], '104')
        self.assertEqual(self.store.intent(a['id'])['created_ms'], 10)
        self.store.decide_exit(recovered, now_ms=20)
        self.assertEqual(self.store.intent(a['id'])['created_ms'], 10)

    def test_stale_writer_cannot_overwrite_state(self):
        a = self.row()
        stale = dict(a)
        self.store.save(a, 'first')
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            self.store.save(stale, 'stale')

    def test_attempt_is_unknown_before_send_and_blocks_duplicate(self):
        a = self.row()
        self.store.decide_exit(a, now_ms=10)
        attempt = self.store.prepare_attempt(a['id'], size='1', limit='100', now_ms=11)
        self.assertEqual(attempt['status'], 'UNKNOWN')
        self.assertTrue(attempt['cloid'].startswith('0x'))
        with self.assertRaisesRegex(RuntimeError, 'unresolved'):
            self.store.prepare_attempt(a['id'], size='1', limit='100', now_ms=12)

    def test_failed_state_update_rolls_back_exit_intent(self):
        a = self.row()
        stale = dict(a)
        self.store.save(a, 'new version')
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            self.store.decide_exit(stale, now_ms=10)
        self.assertIsNone(self.store.intent(a['id']))

    def test_attempt_requires_durable_intent(self):
        a = self.row()
        with self.assertRaisesRegex(RuntimeError, 'intent'):
            self.store.prepare_attempt(a['id'], size='1', limit='100', now_ms=10)

    def test_completed_paper_signal_can_be_enrolled_again(self):
        a = self.row()
        a['state'] = 'PAPER_EXIT'
        self.store.save(a, 'paper signal')
        self.row()
