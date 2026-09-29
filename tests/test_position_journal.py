"""Position activity is durable evidence, not a completed-trade statistic."""
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from kis_hl.data_ingestion import ingest_rows
from kis_hl.data_store import DataStore
from kis_hl.journal_exports import journal


class PositionJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = DataStore(Path(self.temp.name) / 'test.sqlite')
        self.account = self.store.account('hyperliquid', 'testnet', 'fixture')

    def fill(self, key, before, side='B', quantity='1'):
        return dict(coin='BTC', tid=key, time=100 + key, side=side,
                    sz=quantity, px='10', fee='0', feeToken='USDC', oid=key,
                    startPosition=before, closedPnl='0')

    def ingest(self, *rows, **kwargs):
        return ingest_rows(self.store, self.account, 'hl_fills', list(rows), **kwargs)

    def entries(self):
        with self.store.connect() as db:
            return [dict(r, result=json.loads(r['result'])) for r in db.execute(
                "SELECT * FROM analysis_runs WHERE kind='position_change' ORDER BY id")]

    def test_every_long_and_short_transition_is_recorded_before_report(self):
        rows = [self.fill(1, '0'), self.fill(2, '1'),
                self.fill(3, '2', 'A'), self.fill(4, '1', 'A'),
                self.fill(5, '0', 'A'), self.fill(6, '-1', 'A'),
                self.fill(7, '-2'), self.fill(8, '-1', 'B', '2')]
        ids = self.ingest(*rows)
        entries = self.entries()
        self.assertEqual([r['result']['change'] for r in entries],
                         ['entry', 'increase', 'reduction', 'close',
                          'entry', 'increase', 'reduction', 'reversal'])
        self.assertEqual([r['result']['fact_id'] for r in entries], ids)
        self.assertEqual(entries[-1]['result']['position_after'], '1')
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM analysis_inputs').fetchone()[0], 8)

    def test_duplicate_and_correction_preserve_history(self):
        row = self.fill(1, '0')
        first = self.ingest(row)[0]
        frozen = self.entries()[0]
        self.assertEqual(self.ingest(row), [first])
        self.assertEqual(len(self.entries()), 1)
        with self.assertRaises(ValueError):
            self.ingest({**row, 'sz': '2'})
        second = self.ingest({**row, 'sz': '2'}, allow_correction=True)[0]
        self.assertEqual(self.entries()[0], frozen)
        revised = self.entries()[1]['result']
        self.assertEqual(revised['supersedes_fact_id'], first)
        self.assertEqual(revised['record_type'], 'revision')
        report = journal(self.store, [self.account])
        self.assertEqual([e['fact_id'] for e in report['position_changes']], [second])
        self.assertEqual(report['position_changes'][0]['signed_quantity'], '2')

    def test_unknown_inventory_and_day_precision_remain_unknown(self):
        account = self.store.account('kis', 'sim', 'fixture')
        row = dict(source_id='day', instrument='kis:005930', currency='KRW',
                   event_start_ms=100, event_end_ms=86400100, time_precision='DAY',
                   grain='DAY_SYMBOL_SIDE', side='buy', quantity='2', price='10',
                   notional='20', total_cost=None)
        ingest_rows(self.store, account, 'statement', [row])
        entry = self.entries()[0]['result']
        self.assertIsNone(entry['position_before'])
        self.assertIsNone(entry['position_after'])
        self.assertEqual(entry['change'], 'unclassified')
        self.assertEqual(entry['time_precision'], 'DAY')
        self.assertEqual(entry['grain'], 'DAY_SYMBOL_SIDE')
        self.assertEqual(entry['signed_quantity'], '2')

    def test_journal_failure_rolls_back_fact_and_source_link(self):
        with patch('kis_hl.position_journal.record_change', side_effect=sqlite3.OperationalError('disk failure')):
            with self.assertRaises(sqlite3.OperationalError):
                self.ingest(self.fill(1, '0'))
        self.assertEqual(self.store.facts('trade'), [])
        self.assertEqual(self.entries(), [])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM fact_sources').fetchone()[0], 0)
        self.ingest(self.fill(1, '0'))
        self.assertEqual(len(self.entries()), 1)

    def test_outer_transaction_rolls_back_activity(self):
        with self.assertRaisesRegex(ValueError, 'abort'):
            with self.store.atomic():
                self.ingest(self.fill(1, '0'))
                raise ValueError('abort')
        self.assertEqual(self.entries(), [])
        self.assertEqual(self.store.facts('trade'), [])

    def test_non_execution_updates_do_not_create_activity(self):
        obs = self.store.observe('fixture', self.account, b'{}')
        self.store.fact('position', self.account, 'snapshot', dict(
            instrument='hl:BTC', event_start_ms=1, event_end_ms=2,
            quantity='1', unrealized_pnl='100'), observation=obs)
        ingest_rows(self.store, self.account, 'hl_funding', [dict(
            time=100, hash='funding', delta=dict(coin='BTC', usdc='-1'))])
        self.assertEqual(self.entries(), [])

    def test_account_isolation_open_statistics_and_frozen_report(self):
        self.ingest(self.fill(1, '0'))
        old = journal(self.store, [self.account])
        other = self.store.account('hyperliquid', 'mainnet', 'fixture')
        ingest_rows(self.store, other, 'hl_fills', [self.fill(1, '0')])
        self.ingest(self.fill(2, '1'))
        new = journal(self.store, [self.account])
        self.assertEqual(len(old['position_changes']), 1)
        self.assertEqual(len(new['position_changes']), 2)
        self.assertTrue(all(e['account'] == self.account for e in new['position_changes']))
        self.assertEqual(new['summary_by_account_currency'][0]['statistics_by_strategy']['unassigned']['trade_count'], 0)
        with self.store.connect() as db:
            saved = json.loads(db.execute('SELECT result FROM analysis_runs WHERE id=?', (old['report_id'],)).fetchone()[0])
        self.assertEqual(saved['position_changes'], old['position_changes'])

    def test_asof_and_legacy_projection_do_not_rewrite_history(self):
        from kis_hl.data_ingestion import hl_fill
        dataset, key, payload = hl_fill(self.fill(1, '0'))
        obs = self.store.observe('fixture', self.account, b'{}')
        first = self.store.fact(dataset, self.account, key, payload, observation=obs, known_ms=200)
        self.store.fact(dataset, self.account, key, {**payload, 'quantity': '2', 'notional': '20'},
                        observation=obs, known_ms=300, allow_correction=True)
        self.assertEqual(journal(self.store, [self.account], as_of_ms=250)['position_changes'][0]['fact_id'], first)
        self.assertEqual(journal(self.store, [self.account], as_of_ms=99)['position_changes'], [])
        # Model a database written before automatic journals were introduced.
        with self.store.connect() as db:
            db.execute("DELETE FROM analysis_inputs WHERE run_id IN (SELECT id FROM analysis_runs WHERE kind='position_change')")
            db.execute("DELETE FROM analysis_runs WHERE kind='position_change'")
        projected = journal(self.store, [self.account])['position_changes'][0]
        self.assertEqual(projected['recording'], 'historical_projection')
        self.assertIsNone(projected['journal_id'])
        self.assertEqual(self.entries(), [])

    def test_cumulative_quantity_and_fee_revisions_are_not_extra_executions(self):
        account = self.store.account('kis', 'sim', 'daily')
        from kis_hl.data_ingestion import ingest_maturing_rows
        row = dict(source_id='day', instrument='kis:005930', currency='KRW',
                   event_start_ms=100, event_end_ms=86400100, time_precision='DAY',
                   grain='DAY_SYMBOL_SIDE', side='buy', quantity='1', price='10',
                   notional='10', total_cost='0')
        obs = self.store.observe('fixture', account, b'{}')
        ingest_maturing_rows(self.store, account, 'statement', [row], observation=obs)
        updated = {**row, 'quantity': '2', 'notional': '20'}
        ingest_maturing_rows(self.store, account, 'statement', [updated], observation=obs)
        ingest_maturing_rows(self.store, account, 'statement', [{**updated, 'total_cost': '1'}], observation=obs)
        report = journal(self.store, [account])
        self.assertEqual(len(self.entries()), 3)
        self.assertEqual(len(report['position_changes']), 1)
        self.assertEqual(report['position_changes'][0]['signed_quantity'], '2')
        self.assertEqual(report['position_changes'][0]['record_type'], 'revision')
        self.assertEqual(report['position_changes'][0]['total_cost'], '1')

    def test_restart_is_idempotent_and_record_is_independently_exportable(self):
        from kis_hl.journal_exports import export_report
        row = self.fill(1, '0')
        self.ingest(row)
        self.store = DataStore(self.store.path)
        self.ingest(row)
        entry = self.entries()[0]
        target = Path(self.temp.name) / 'activity.json'
        export_report(self.store, entry['id'], target)
        self.assertEqual(json.loads(target.read_text()), entry['result'])
        self.assertEqual(len(self.entries()), 1)

    def test_completed_trade_statistics_still_count_one_cycle(self):
        self.ingest(self.fill(1, '0'), self.fill(2, '1'),
                    self.fill(3, '2', 'A'), self.fill(4, '1', 'A'))
        for dataset in ['trade', 'cash']:
            self.store.coverage(dataset, self.account, 0, 1000, 'complete', {})
        report = journal(self.store, [self.account])
        self.assertEqual(len(report['position_changes']), 4)
        self.assertEqual(len(report['cycles']), 1)
        stats = report['summary_by_account_currency'][0]['statistics_by_strategy']['unassigned']
        self.assertEqual(stats['trade_count'], 1)


    def test_superseded_activity_is_history_but_reports_and_analyses_are_stale(self):
        row = self.fill(1, '0')
        fact_id = self.ingest(row)[0]
        old_report = journal(self.store, [self.account])['report_id']
        analysis = self.store.pin('analysis', {}, [fact_id], {})
        self.assertEqual(self.store.status()['stale_runs'], [])
        self.ingest({**row, 'sz': '2'}, allow_correction=True)
        self.assertEqual(self.store.status()['stale_runs'], sorted([old_report, analysis]))
        self.assertEqual(len(self.entries()), 2)
        fresh = journal(self.store, [self.account])['report_id']
        self.assertNotIn(fresh, self.store.status()['stale_runs'])

    def test_kis_reconciled_order_ids_survive_record_and_report(self):
        account = self.store.account('kis', 'sim', 'orders')
        row = dict(source_id='grouped', instrument='kis:005930', currency='KRW',
                   event_start_ms=100, event_end_ms=86400100, time_precision='DAY',
                   grain='DAY_SYMBOL_SIDE_RECONCILED', side='buy', quantity='2',
                   price='10', notional='20', total_cost='0', order_ids=['001', '002'])
        ingest_rows(self.store, account, 'statement', [row])
        entry = self.entries()[0]['result']
        self.assertEqual(entry['order_ids'], ['001', '002'])
        self.assertIsNone(entry['order_id'])
        self.assertEqual(journal(self.store, [account])['position_changes'][0]['order_ids'], ['001', '002'])
        self.ingest(self.fill(1, '0'))
        native = self.entries()[-1]['result']
        self.assertEqual(native['order_id'], '1')
        self.assertIsNone(native['order_ids'])
