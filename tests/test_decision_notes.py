"""Advisory decision notes sit beside actual position activity and never alter it."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

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

    def test_historical_reports_ignore_future_corrections(self):
        with self.store.connect() as db:
            known = db.execute('SELECT known_ms FROM fact_revisions WHERE id=?',
                               (self.fact,)).fetchone()[0]
        for link in (None, self.journal_id):
            with self.subTest(journal_id=link):
                with patch('kis_hl.decision_notes.now_ms', return_value=known + 1000):
                    first = self.note(journal_id=link, text='Original reason')
                with patch('kis_hl.decision_notes.now_ms', return_value=known + 2000):
                    second = self.note(journal_id=link, text='Corrected reason',
                                       supersedes_note_id=first['note_id'])
                for offset, expected in ((999, []), (1000, [first['note_id']]),
                                         (1500, [first['note_id']]), (2000, [second['note_id']])):
                    report = journal(self.store, [self.account], as_of_ms=known + offset)
                    notes = (report['decision_notes'] if link is None
                             else report['position_changes'][0]['notes'])
                    self.assertEqual([n['note_id'] for n in notes
                                      if n['note_id'] in {first['note_id'], second['note_id']}], expected)
        self.assertEqual([n['superseded'] for n in list_notes(self.store, limit=0)],
                         [True, False, True, False])

    def test_mismatched_links_are_rejected_atomically(self):
        other = self.store.account('hyperliquid', 'testnet', 'other')
        fill = dict(coin='BTC', tid=2, time=102, side='B', sz='1', px='10', fee='0',
                    feeToken='USDC', oid=2, startPosition='1', closedPnl='0')
        second_fact = ingest_rows(self.store, self.account, 'hl_fills', [fill])[0]
        first = self.note()
        bad = [dict(account=other), dict(instrument='hl:ETH'),
               dict(account=other, journal_id=None, fact_id=self.fact),
               dict(instrument='hl:ETH', journal_id=None, fact_id=self.fact),
               dict(fact_id=second_fact),
               dict(account=other, journal_id=None, supersedes_note_id=first['note_id']),
               dict(instrument='hl:ETH', journal_id=None, supersedes_note_id=first['note_id']),
               dict(account='unknown', journal_id=None)]
        with self.store.connect() as db:
            counts = [db.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                      for t in ('analysis_runs', 'analysis_inputs')]
        for changes in bad:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.note(**changes)
                with self.store.connect() as db:
                    self.assertEqual([db.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                                      for t in ('analysis_runs', 'analysis_inputs')], counts)
                self.assertFalse(list_notes(self.store, limit=0)[0]['superseded'])
        valid = self.note(fact_id=self.fact, supersedes_note_id=first['note_id'])
        self.assertEqual(journal(self.store, [self.account])['position_changes'][0]['notes'][0]['note_id'],
                         valid['note_id'])

    def test_corrected_facts_do_not_make_note_history_stale(self):
        fact_note = self.note(journal_id=None, fact_id=self.fact)
        journal_note = self.note()
        frozen = list_notes(self.store, limit=0)
        report = journal(self.store, [self.account])['report_id']
        analysis = self.store.pin('analysis', {}, [self.fact], {})
        fill = dict(coin='BTC', tid=1, time=101, side='B', sz='2', px='10', fee='0',
                    feeToken='USDC', oid=1, startPosition='0', closedPnl='0')
        ingest_rows(self.store, self.account, 'hl_fills', [fill], allow_correction=True)
        stale = self.store.status()['stale_runs']
        self.assertNotIn(fact_note['note_id'], stale)
        self.assertNotIn(journal_note['note_id'], stale)
        self.assertIn(report, stale)
        self.assertIn(analysis, stale)
        self.assertEqual(list_notes(self.store, limit=0), frozen)


if __name__ == '__main__':
    unittest.main()
