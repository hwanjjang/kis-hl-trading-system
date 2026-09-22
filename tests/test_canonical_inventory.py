"""KIS position boundaries require inventory evidence, independently of coverage."""
import json
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from kis_hl.data_ingestion import ingest_rows
from kis_hl.data_store import DataStore
from kis_hl.journal_exports import journal


def trade(index, side, quantity, price=100, *, instrument='kis:X', **evidence):
    return dict(source_id=str(index), instrument=instrument, currency='USD',
                event_start_ms=index * 10, event_end_ms=index * 10 + 1,
                time_precision='MILLISECOND', grain='EXECUTION', side=side,
                quantity=str(quantity), price=str(price), notional=str(quantity * price),
                total_cost='1', costs={'broker': '1'}, **evidence)


class InventoryBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = DataStore(Path(self.temp.name) / 'journal.sqlite')
        self.account = self.store.account('kis', 'sim', 'synthetic')

    def report(self, rows, account=None):
        account = account or self.account
        ingest_rows(self.store, account, 'statement', rows)
        for dataset in ['trade', 'cash']:
            self.store.coverage(dataset, account, 0, 10**15, 'complete', {})
        return journal(self.store, [account])

    def test_oversell_is_rejected_before_closing_the_tracked_long(self):
        result = self.report([trade(1, 'buy', 3, position_before='0'),
                              trade(2, 'sell', 10, 120), trade(3, 'buy', 7, 110)])
        self.assertEqual(len(result['cycles']), 1)
        cycle = result['cycles'][0]
        self.assertEqual(cycle['side'], 'long')
        self.assertIsNone(cycle['closed_ms'])
        self.assertIn('opening_inventory_gap', cycle['reasons'])
        self.assertIsNone(cycle['net_return_pct'])
        summary = result['summary_by_account_currency'][0]
        self.assertEqual(summary['statistics_by_strategy']['unassigned']['trade_count'], 0)
        self.assertEqual(summary['trading_fee'], '3')
        self.assertIsNone(summary['net_booked_pnl'])
        self.assertEqual(len(self.store.facts('trade')), 3)

    def test_coverage_does_not_anchor_first_buy_or_subsequent_inferred_flat(self):
        result = self.report([trade(1, 'buy', 3), trade(2, 'sell', 3, 110),
                              trade(3, 'buy', 1), trade(4, 'sell', 1, 110)])
        for cycle in result['cycles']:
            self.assertEqual(cycle['status'], 'PENDING')
            self.assertIn('inventory_unanchored', cycle['reasons'])
            self.assertIsNone(cycle['net_pnl'])
        self.assertIsNone(result['summary_by_account_currency'][0]['net_booked_pnl'])

    def test_explicit_flat_anchor_can_start_a_later_valid_cycle(self):
        result = self.report([trade(1, 'buy', 1), trade(2, 'sell', 1),
                              trade(3, 'buy', 2, position_before='0'), trade(4, 'sell', 2, 110)])
        self.assertEqual([c['status'] for c in result['cycles']], ['PENDING', 'FINALIZED'])
        self.assertEqual(result['summary_by_account_currency'][0]['statistics_by_strategy']['unassigned']['trade_count'], 1)

    def test_verified_prior_cycle_survives_later_oversell(self):
        result = self.report([trade(1, 'buy', 1, position_before='0'), trade(2, 'sell', 1),
                              trade(3, 'buy', 3), trade(4, 'sell', 10)])
        self.assertEqual(result['cycles'][0]['status'], 'FINALIZED')
        self.assertIsNone(result['cycles'][1]['net_pnl'])
        self.assertTrue(all(c['side'] == 'long' for c in result['cycles']))

    def test_prior_closed_cycle_survives_a_later_position_before_gap(self):
        result = self.report([trade(1, 'buy', 1, position_before='0'), trade(2, 'sell', 1),
                              trade(3, 'sell', 2, position_before='2')])
        self.assertEqual(result['cycles'][0]['status'], 'FINALIZED')
        self.assertTrue(result['quality_findings'])
        self.assertEqual(result['summary_by_account_currency'][0]['coverage_status'], 'partial_or_unverified')

    @staticmethod
    def daily(row, day, ending):
        return {**row, 'event_start_ms': day * 86400000,
                'event_end_ms': (day + 1) * 86400000, 'time_precision': 'DAY',
                'grain': 'ORDER_CUMULATIVE_RECONCILED', 'day_end_quantity': str(ending)}

    def test_nonzero_day_end_holdings_cannot_finalize_a_false_flat_cycle(self):
        result = self.report([self.daily(trade(1, 'buy', 3, position_before='0'), 1, 3),
                              self.daily(trade(2, 'sell', 3, 110), 2, 7)])
        cycle = result['cycles'][0]
        self.assertEqual(cycle['status'], 'PENDING')
        self.assertIn('ending_inventory_mismatch', cycle['reasons'])
        self.assertIsNone(cycle['net_return_pct'])

    def test_day_end_is_checked_after_sell_and_reentry_not_each_fill(self):
        rows = [self.daily(trade(1, 'buy', 2, position_before='0'), 1, 2),
                self.daily(trade(2, 'sell', 2, 110, position_before='2'), 2, 1),
                self.daily(trade(3, 'buy', 1, position_before='0'), 2, 1),
                self.daily(trade(4, 'sell', 1, 120), 3, 0)]
        result = self.report(rows)
        self.assertEqual([c['status'] for c in result['cycles']], ['FINALIZED', 'FINALIZED'])
        self.assertEqual(result['quality_findings'], [])

    def test_inconsistent_day_end_evidence_invalidates_all_same_day_cycles(self):
        rows = [self.daily(trade(1, 'buy', 1, position_before='0'), 1, 0),
                self.daily(trade(2, 'sell', 1, position_before='1'), 1, 2)]
        result = self.report(rows)
        self.assertNotEqual(result['cycles'][0]['status'], 'FINALIZED')
        self.assertTrue(result['quality_findings'])

    def test_same_day_oversell_cannot_skip_invalidation_of_a_closed_candidate(self):
        rows = [self.daily(trade(1, 'buy', 1, position_before='0'), 1, 1),
                self.daily(trade(2, 'sell', 1, position_before='1'), 2, 7),
                self.daily(trade(3, 'sell', 2), 2, 7)]
        result = self.report(rows)
        self.assertEqual(result['cycles'][0]['status'], 'PENDING')
        self.assertIsNone(result['cycles'][0]['net_return_pct'])

    def test_later_day_ambiguity_preserves_a_prior_day_completed_cycle(self):
        rows = [self.daily(trade(1, 'buy', 1, position_before='0'), 1, 1),
                self.daily(trade(2, 'sell', 1, position_before='1'), 2, 0),
                self.daily(trade(3, 'buy', 1), 3, 2),
                self.daily(trade(4, 'buy', 1), 3, 2)]
        result = self.report(rows)
        self.assertEqual(result['cycles'][0]['status'], 'FINALIZED')
        self.assertEqual(result['quality_findings'][0]['kind'], 'ambiguous_chronology')

    def test_anchored_partial_exit_then_add_and_next_cycle_stay_valid(self):
        rows = [trade(1, 'buy', 10, position_before='0'), trade(2, 'sell', 5, 200),
                trade(3, 'buy', 5, 300), trade(4, 'sell', 10, 200),
                trade(5, 'buy', 1), trade(6, 'sell', 1, 110)]
        result = self.report(rows)
        self.assertEqual(result['cycles'][0]['net_pnl'], '496')
        self.assertEqual([c['status'] for c in result['cycles']], ['FINALIZED', 'FINALIZED'])

    def test_hyperliquid_reversal_conserves_fees_and_funding(self):
        account = self.store.account('hyperliquid', 'testnet', 'synthetic-hl')
        rows = [trade(1, 'buy', 3, instrument='hl:BTC', position_before='0'),
                trade(2, 'sell', 10, 120, instrument='hl:BTC', position_before='3'),
                trade(3, 'buy', 7, 110, instrument='hl:BTC', position_before='-7')]
        ingest_rows(self.store, account, 'hl_funding', [dict(time=25, hash='synthetic',
                    delta=dict(coin='BTC', usdc='-2'))])
        # Funding and fills must share units.
        for row in rows: row['currency'] = 'USDC'
        result = self.report(rows, account)
        self.assertEqual([c['status'] for c in result['cycles']], ['FINALIZED', 'FINALIZED'])
        self.assertEqual([c['side'] for c in result['cycles']], ['long', 'short'])
        self.assertEqual(sum(Decimal(c['trading_fee']) for c in result['cycles']), 3)
        self.assertEqual(sum(Decimal(c['funding_cashflow']) for c in result['cycles']), -2)

    def test_old_report_is_immutable_and_new_report_records_policy_version(self):
        old = self.store.pin('journal', {'metric_version': 'canonical-v1'}, [], {'old': True})
        self.report([trade(1, 'buy', 1), trade(2, 'sell', 1)])
        with self.store.connect() as db:
            self.assertEqual(json.loads(db.execute('SELECT result FROM analysis_runs WHERE id=?', (old,)).fetchone()[0]), {'old': True})
            parameters = json.loads(db.execute('SELECT parameters FROM analysis_runs ORDER BY id DESC LIMIT 1').fetchone()[0])
        self.assertEqual(parameters['inventory_policy_version'], 'kis-inventory-v1')
