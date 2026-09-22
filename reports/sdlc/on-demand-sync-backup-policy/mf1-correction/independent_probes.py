"""Independent MF1 behavior probes; synthetic fixtures and temporary SQLite only."""
import copy
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from kis_hl.data_account_audit import compare_bundles, apply_report, write_private
from kis_hl.data_audit_capture import collect_bundle
from kis_hl.data_ingestion import domestic_bundle
from kis_hl.data_store import DataStore
from kis_hl.journal_sync import Scope

START = int(datetime.fromisoformat('2026-09-21T00:00:00+09:00').timestamp() * 1000)
END = START + 86400000
ACCOUNT = '1234567801'
MISSING = object()
BAD_SIDES = ['99', '', None, 1, True, [], {}, MISSING]


def order(oid='one', side='02', qty='1', amount='100', day='20260921', symbol='005930'):
    row = dict(ord_dt=day, pdno=symbol, odno=oid, ord_gno_brno='001',
               tot_ccld_qty=qty, tot_ccld_amt=amount)
    if side is not MISSING:
        row['sll_buy_dvsn_cd'] = side
    return row


def daily(buy='1', sell='0', day='20260921', symbol='005930'):
    return dict(trad_dt=day, pdno=symbol, buy_qty=buy,
                buy_amt=str(Decimal(buy) * 100), sll_qty=sell,
                sll_amt=str(Decimal(sell) * 100),
                hldg_qty=str(Decimal(buy)-Decimal(sell)),
                pchs_unpr='100', loan_int='0')


def source(days=None, orders=None):
    days = [daily()] if days is None else days
    return dict(days=days, orders=[order()] if orders is None else orders,
                costs_by_day_symbol={d['trad_dt']+':'+d['pdno']:
                    dict(buy_fee_smtl='0', buy_tax_smtl='0', sll_fee_smtl='0', sll_tltx_smtl='0')
                    for d in days})


def bundle(domestic):
    return dict(schema_version=1, kind='account-audit-bundle',
                account=dict(venue='kis', environment='live', native_id=ACCOUNT),
                start_ms=START, end_ms=END+86400000, collected_ms=END,
                collection_complete=True, inventory_complete=False,
                positions=[], findings=[], evidence=[], sources=[
                    dict(parser='kis_domestic_bundle', data=domestic),
                    dict(parser='kis_overseas_trans', data=[])])


class SyntheticKis:
    def __init__(self, domestic):
        self.source = copy.deepcopy(domestic)
        self.config = SimpleNamespace(account_id=ACCOUNT, mode='live')
        self.calls = []

    def account_pages(self, kind, **kwargs):
        self.calls.append(kind)
        body = dict(rt_cd='0', output1=[], output2=[])
        if kind == 'domestic_trade_profit':
            body['output1'] = [r for r in self.source['days']
                if kwargs['date_from'] <= r['trad_dt'] <= kwargs['date_to']
                and (not kwargs.get('symbol') or r['pdno'] == kwargs['symbol'])]
            if kwargs.get('symbol'):
                key = kwargs['date_from'] + ':' + kwargs['symbol']
                body['output2'] = [self.source['costs_by_day_symbol'][key]]
        elif kind == 'domestic_history':
            body['output1'] = self.source['orders']
        elif kind == 'domestic_balance':
            body['output1'] = []
        elif kind not in {'overseas_transactions', 'overseas_balance'}:
            raise AssertionError('Unexpected synthetic request '+kind)
        kwargs['page_observer'](SimpleNamespace(body=body, raw_body=json.dumps(body).encode()))
        return dict(body, complete=True, pages=1)


class IndependentMF1(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = DataStore(self.root/'synthetic.sqlite')

    def counts(self):
        with self.store.connect() as db:
            return {t: db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in
                    ['accounts', 'fact_revisions', 'source_observations', 'dataset_coverage', 'analysis_runs', 'collection_runs']}

    def reject(self, fn):
        # Invalid input may reject at parsing or explicit validation; no successful
        # return or partial applied state is permitted by the behavioral contract.
        with self.assertRaises((ValueError, KeyError, TypeError)):
            fn()

    def test_unknown_side_cannot_disappear_from_zero_day(self):
        for side in BAD_SIDES:
            with self.subTest(side=repr(side)):
                native = source(days=[daily('0')], orders=[order(side=side)])
                self.reject(lambda: domestic_bundle(native))
                before = self.counts()
                self.reject(lambda: compare_bundles(self.store, [bundle(native)]))
                self.assertEqual(self.counts(), before)

    def test_bad_executed_side_cannot_hide_beside_valid_execution(self):
        for side in BAD_SIDES:
            with self.subTest(side=repr(side)):
                native = source(orders=[order(), order('bad', side, '3', '300')])
                self.reject(lambda: domestic_bundle(native))
                before = self.counts()
                self.reject(lambda: compare_bundles(self.store, [bundle(native)]))
                self.assertEqual(self.counts(), before)

    def test_capture_rejects_every_invalid_executed_side(self):
        for side in BAD_SIDES:
            with self.subTest(side=repr(side)):
                native = source(orders=[order(), order('bad', side, '3', '300')])
                client = SyntheticKis(native)
                self.reject(lambda: collect_bundle('kis', ACCOUNT, start_ms=START, end_ms=END,
                                                   client=client, scope=Scope('kis', 'live', ACCOUNT)))

    def test_zero_quantity_unknown_or_missing_side_remains_unexecuted(self):
        for side in BAD_SIDES:
            with self.subTest(side=repr(side)):
                native = source(orders=[order(), order('unfilled', side, '0', '0')])
                rows = domestic_bundle(native)
                self.assertEqual([r['order_ids'] for r in rows], [['one']])
                client = SyntheticKis(native)
                captured = collect_bundle('kis', ACCOUNT, start_ms=START, end_ms=END,
                                          client=client, scope=Scope('kis', 'live', ACCOUNT))
                self.assertTrue(captured['collection_complete'])
                report = compare_bundles(self.store, [captured])
                self.assertEqual(report['blockers'], [])
                self.assertEqual(len(report['changes']), 1)

    def test_all_positive_executions_appear_once_in_their_daily_side_facts(self):
        days = [daily('3', '1'), daily('2', '0', '20260922', '000660')]
        orders = [order('buy-a'), order('buy-b', qty='2', amount='200'),
                  order('sell-a', side='01'),
                  order('other-day', qty='2', amount='200', day='20260922', symbol='000660'),
                  order('unfilled', side='99', qty='0', amount='0', day='20260923', symbol='000000')]
        native = source(days, orders)
        rows = domestic_bundle(native)
        represented = [(r['symbol'], r['side'], oid) for r in rows for oid in r['order_ids']]
        expected = [(r['pdno'], {'01':'sell','02':'buy'}[r['sll_buy_dvsn_cd']], r['odno'])
                    for r in orders if Decimal(r['tot_ccld_qty']) > 0]
        self.assertCountEqual(represented, expected)
        self.assertEqual(sum(Decimal(r['quantity']) for r in rows), Decimal('6'))
        report = compare_bundles(self.store, [bundle(native)])
        self.assertEqual(report['blockers'], [])
        path = self.root/'review.json'
        receipt = write_private(path, report)
        apply_report(self.store, path, receipt['sha256'], journals=True)
        self.assertEqual(len(self.store.facts('trade')), 3)

    def test_duplicate_daily_representation_cannot_represent_execution_twice(self):
        native=source(); native['days'].append(copy.deepcopy(native['days'][0]))
        self.reject(lambda: domestic_bundle(native))
        self.reject(lambda: compare_bundles(self.store, [bundle(native)]))

    def test_rehashed_report_cannot_apply_invalid_executed_source(self):
        original=compare_bundles(self.store, [bundle(source())])
        for i,side in enumerate(BAD_SIDES):
            with self.subTest(side=repr(side)):
                report=copy.deepcopy(original)
                report['bundles'][0]['sources'][0]['data']['orders'].append(order('bad',side,'3','300'))
                path=self.root/('invalid-'+str(i)+'.json')
                receipt=write_private(path,report)
                before=self.counts()
                self.reject(lambda: apply_report(self.store,path,receipt['sha256'],journals=True))
                self.assertEqual(self.counts(),before)

    def test_supported_positive_side_still_requires_corresponding_daily_evidence(self):
        for native in [source(days=[], orders=[order()]), source(orders=[order(symbol='000660')])]:
            with self.subTest(native=native):
                self.reject(lambda: domestic_bundle(native))
                self.reject(lambda: compare_bundles(self.store, [bundle(native)]))

    def test_supported_positive_side_still_requires_daily_cost_source(self):
        native = source(); native['costs_by_day_symbol'] = {}
        self.reject(lambda: domestic_bundle(native))
        self.reject(lambda: compare_bundles(self.store, [bundle(native)]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
