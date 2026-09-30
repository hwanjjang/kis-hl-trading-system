"""Advisory decision notes sit beside actual position activity and never alter it."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from kis_hl.data_ingestion import ingest_rows
from kis_hl.data_store import DataStore
from kis_hl.decision_notes import add_note, list_notes
from kis_hl.journal_exports import journal

JEV = {"tool": "timing_opinion", "provider": "typesafe", "status": "available",
       "advisory": True, "order_authorized": False, "choice": "wait",
       "confidence": "0.41", "min_confidence": "0.5", "effective_opinion": "wait"}


class DecisionNoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = DataStore(Path(self.temp.name) / 'test.sqlite')
        self.account = self.store.account('hyperliquid', 'testnet', 'fixture')
        fill = dict(coin='BTC', tid=1, time=101, side='B', sz='1', px='10', fee='0',
                    feeToken='USDC', oid=1, startPosition='0', closedPnl='0')
        self.fact = ingest_rows(self.store, self.account, 'hl_fills', [fill])[0]
        with self.store.connect() as db:
            self.journal_id = db.execute(
                "SELECT id FROM analysis_runs WHERE kind='position_change'").fetchone()[0]

    def note(self, **changes):
        base = dict(account=self.account, instrument='hl:BTC', author='ak', phase='entry',
                    stance='long', text='Higher low on the pullback; slope flattening.',
                    observed_ms=150, journal_id=self.journal_id)
        return add_note(self.store, {**base, **changes})

    def test_ak_agent_and_jev_notes_appear_next_to_the_linked_execution(self):
        self.note()
        self.note(author='agent', stance='wait', text='No confirmed close above prior high.')
        self.note(author='jev', stance='wait', text=None, jev=JEV)
        report = journal(self.store, [self.account])
        change = report['position_changes'][0]
        self.assertEqual([n['author'] for n in change['notes']], ['ak', 'agent', 'jev'])
        self.assertEqual(change['notes'][2]['jev']['confidence'], '0.41')
        self.assertTrue(all(n['order_authorized'] is False for n in change['notes']))
        # Notes are separate records: the activity entry itself is unchanged.
        with self.store.connect() as db:
            entry = json.loads(db.execute('SELECT result FROM analysis_runs WHERE id=?',
                                          (self.journal_id,)).fetchone()[0])
        self.assertNotIn('notes', entry)

    def test_unlinked_notes_are_kept_and_corrections_supersede(self):
        first = self.note(journal_id=None, phase='pre_trade', text='Watch 6,966 close.')
        self.note(journal_id=None, phase='pre_trade', text='Watch 6,966 daily close above.',
                  supersedes_note_id=first['note_id'])
        report = journal(self.store, [self.account])
        self.assertEqual([n['text'] for n in report['decision_notes']],
                         ['Watch 6,966 daily close above.'])
        listed = list_notes(self.store, instrument='hl:BTC', limit=0)
        self.assertEqual([n['superseded'] for n in listed], [True, False])

    def test_invalid_notes_are_rejected_without_writing(self):
        bad = [dict(author='someone'), dict(phase='later'), dict(text=''),
               dict(journal_id=self.journal_id + 999), dict(author='jev', jev=None),
               dict(author='jev', jev={**JEV, 'order_authorized': True}),
               dict(author='ak', jev=JEV), dict(observed_ms=10**15), dict(extra=1)]
        for change in bad:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.note(**change)
        self.assertEqual(list_notes(self.store, limit=0), [])


if __name__ == '__main__':
    unittest.main()
