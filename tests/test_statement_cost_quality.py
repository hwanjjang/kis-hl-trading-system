"""Incomplete fee detail must never silently certify a favorable return."""
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from kis_hl.data_cli import cmd_data
from kis_hl.data_ingestion import ingest_rows, statement
from kis_hl.data_reconciliation import reconcile
from kis_hl.data_store import DataStore
from kis_hl.journal_exports import journal, export_report
from tests.test_canonical_inventory import trade


class StatementCostQualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = DataStore(self.root / 'state.sqlite')
        self.account = self.store.account('kis', 'sim', 'synthetic')

    def rows(self, costs, total='1', side='buy'):
        rows = [trade(1, 'buy', 1, position_before='0'), trade(2, 'sell', 1, 110)]
        index = 0 if side == 'buy' else 1
        rows[index] |= {'costs': costs, 'total_cost': total}
        return rows

    def report(self, rows):
        ingest_rows(self.store, self.account, 'statement', rows, allow_correction=True)
        self.store.coverage('trade', self.account, 0, 100, 'complete', {})
        return journal(self.store, [self.account])

    def assert_pending(self, result):
        cycle = result['cycles'][0]
        self.assertEqual(cycle['status'], 'PENDING')
        self.assertIn('cost_components_unreconciled', cycle['reasons'])
        self.assertIsNone(cycle['net_pnl'])
        self.assertIsNone(cycle['net_return_pct'])
        summary = result['summary_by_account_currency'][0]
        self.assertIsNone(summary['net_booked_pnl'])
        self.assertEqual(summary['coverage_status'], 'partial_or_unverified')
        stats = summary['statistics_by_strategy']['unassigned']
        self.assertEqual(stats['trade_count'], 0)
        self.assertEqual(stats['excluded_count'], 1)

    def test_mixed_components_never_finalize_buy_or_sell(self):
        for side in ['buy', 'sell']:
            for total in ['1', '11', '-1', '0']:
                with self.subTest(side=side, total=total):
                    result = self.report(self.rows({'broker': '10', 'tax': None}, total, side))
                    self.assert_pending(result)
                    self.assertEqual(result['cycles'][0]['cost_components'], {'broker': '11'})

    def test_plausible_remainder_is_retained_pending_even_with_settlement(self):
        rows = self.rows({'broker': '1', 'tax': None}, '2')
        rows[0]['settlement'] = '102'
        self.assertEqual(statement(rows[0])[2]['total_cost'], '2')
        self.assert_pending(self.report(rows))
        self.assertEqual(self.store.facts('trade', scope=self.account)[0]['payload']['costs']['tax'], None)

    def test_equal_known_sum_and_explicit_rebates_remain_eligible(self):
        for costs, total in [({'broker': '1', 'tax': None}, '1'),
                             ({'broker': '10', 'rebate': '-9'}, '1'),
                             ({'rebate': '-1'}, '-1'), ({'broker': '0', 'tax': None}, '0'),
                             ({}, '1')]:
            with self.subTest(costs=costs):
                result = self.report(self.rows(costs, total))
                self.assertEqual(result['cycles'][0]['status'], 'FINALIZED')
                self.assertIsNotNone(result['summary_by_account_currency'][0]['net_booked_pnl'])
        self.assertEqual(self.report(self.rows({'broker': '10', 'rebate': '-9'}))['cycles'][0]['net_pnl'], '8')

    def test_known_contradictions_still_reject_before_facts(self):
        for patch in [{'costs': {'broker': '10'}},
                      {'costs': {'broker': '10', 'tax': None}, 'settlement': '999'}]:
            with self.subTest(patch=patch), self.assertRaisesRegex(ValueError, 'reconcile'):
                ingest_rows(self.store, self.account, 'statement', [trade(1, 'buy', 1) | patch])
        self.assertEqual(self.store.facts('trade', scope=self.account), [])

    def test_old_facts_are_rechecked_without_source_rewrite(self):
        observation = self.store.observe('statement', self.account, b'[]')
        for row in self.rows({'broker': '10', 'tax': None}):
            payload = {k: v for k, v in row.items() if k != 'source_id'}
            self.store.fact('trade', self.account, row['source_id'], payload, observation=observation)
        before = self.store.facts('trade', scope=self.account)
        self.store.coverage('trade', self.account, 0, 100, 'complete', {})
        self.assert_pending(journal(self.store, [self.account]))
        self.assertEqual(self.store.facts('trade', scope=self.account), before)

    def test_unresolved_account_does_not_hide_healthy_account_return(self):
        self.report(self.rows({'broker': '10', 'tax': None}))
        healthy = self.store.account('kis', 'sim', 'healthy')
        ingest_rows(self.store, healthy, 'statement', self.rows({'broker': '1'}))
        self.store.coverage('trade', healthy, 0, 100, 'complete', {})
        result = journal(self.store, [self.account, healthy])
        summaries = {r['account']: r for r in result['summary_by_account_currency']}
        self.assertIsNone(summaries[self.account]['net_booked_pnl'])
        self.assertEqual(summaries[healthy]['net_booked_pnl'], '8')

    def test_reconciliation_checks_both_evidence_sets_without_writes(self):
        for unresolved_side in ['source', 'stored']:
            with self.subTest(unresolved_side=unresolved_side):
                good = self.rows({'broker': '1'})
                bad = self.rows({'broker': '10', 'tax': None})
                stored, source = (good, bad) if unresolved_side == 'source' else (bad, good)
                ingest_rows(self.store, self.account, 'statement', stored, allow_correction=True)
                doc = dict(schema_version=1, source='Synthetic independent statement', complete=True,
                           account=dict(venue='kis', environment='sim', native_id='synthetic'),
                           dataset='trade', start_ms=0, end_ms=100, parser='statement', rows=source,
                           opening_inventory={'kis:X': '0'}, closing_inventory={'kis:X': '0'})
                path = self.root / 'statement.json'
                path.write_text(json.dumps(doc))
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                with self.store.connect() as db:
                    before = '\n'.join(db.iterdump())
                for apply in [False, True]:
                    with self.assertRaisesRegex(ValueError, '[Cc]ost.*unresolved|[Uu]nresolved.*cost'):
                        reconcile(self.store, path, digest, apply=apply)
                with self.store.connect() as db:
                    self.assertEqual('\n'.join(db.iterdump()), before)

    def test_source_correction_changes_new_report_only(self):
        before = self.report(self.rows({'broker': '10', 'tax': None}))
        self.assert_pending(before)
        path = self.root / 'before.json'
        export_report(self.store, before['report_id'], path)
        frozen = path.read_bytes()
        after = self.report(self.rows({'broker': '10', 'tax': '0'}, '10'))
        self.assertEqual(after['cycles'][0]['status'], 'FINALIZED')
        self.assertEqual(after['cycles'][0]['net_pnl'], '-1')
        self.assertEqual(path.read_bytes(), frozen)
        self.assertIn(before['report_id'], self.store.status()['stale_runs'])
        self.assertEqual(len(self.store.facts('trade', scope=self.account)), 2)

    def test_backup_missing_source_creates_nothing(self):
        source = self.root / 'missing' / 'db.sqlite'
        target = self.root / 'backups' / 'backup.sqlite'
        with self.assertRaisesRegex(ValueError, '[Nn]ot initialized'):
            cmd_data(SimpleNamespace(db=source, data_action='backup', target=target))
        self.assertFalse(source.parent.exists())
        self.assertFalse(target.parent.exists())

    def test_backup_uninitialized_source_is_unchanged(self):
        source = self.root / 'empty.sqlite'
        with sqlite3.connect(source) as db:
            db.execute('CREATE TABLE unrelated (id INTEGER)')
        before = source.read_bytes()
        target = self.root / 'backup.sqlite'
        with self.assertRaisesRegex(ValueError, '[Nn]ot initialized'):
            cmd_data(SimpleNamespace(db=source, data_action='backup', target=target))
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse(target.exists())
