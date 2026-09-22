"""Executed KIS orders must survive normalization or reject the whole audit."""
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from kis_hl.data_account_audit import compare_bundles, apply_report, write_private
from kis_hl.data_audit_capture import collect_bundle
from kis_hl.data_ingestion import domestic_bundle
from kis_hl.data_store import DataStore
from tests.test_audit_capture import KIS, KIS_SCOPE, ms


def domestic():
    return {'days':[{'trad_dt':'20260921','pdno':'069500','buy_qty':'1','buy_amt':'10',
                     'sll_qty':'0','sll_amt':'0','hldg_qty':'1','pchs_unpr':'10','loan_int':'0'}],
            'orders':[{'ord_dt':'20260921','pdno':'069500','odno':'one','ord_gno_brno':'001',
                       'sll_buy_dvsn_cd':'02','tot_ccld_qty':'1','tot_ccld_amt':'10'}],
            'costs_by_day_symbol':{'20260921:069500':{'buy_fee_smtl':'0','sll_fee_smtl':'0',
                                                   'buy_tax_smtl':'0','sll_tltx_smtl':'0'}}}


def bundle(data):
    return {'schema_version':1,'kind':'account-audit-bundle',
            'account':{'venue':'kis','environment':'live','native_id':KIS_SCOPE.account},
            'start_ms':ms('2026-09-20T15:00:00+00:00'),'end_ms':ms('2026-09-21T15:00:00+00:00'),
            'collection_complete':True,'inventory_complete':False,'findings':[],'positions':[],'evidence':[],
            'sources':[{'parser':'kis_domestic_bundle','data':data},{'parser':'kis_overseas_trans','data':[]}]}


class KISOrderCoverageTests(unittest.TestCase):
    def test_unknown_executed_side_rejects_empty_and_mixed_daily_totals(self):
        for mixed in [False,True]:
            for side in ['99','',None,2]:
                with self.subTest(mixed=mixed,side=side):
                    data=domestic();bad={**data['orders'][0],'odno':'unknown','sll_buy_dvsn_cd':side}
                    if mixed:data['orders'].append(bad)
                    else:
                        data['orders']=[bad]
                        data['days'][0].update(buy_qty='0',buy_amt='0',hldg_qty='0')
                    with self.assertRaisesRegex(ValueError,'side'):domestic_bundle(data)

    def test_missing_executed_side_rejected_explicitly(self):
        data=domestic();data['orders'][0].pop('sll_buy_dvsn_cd')
        with self.assertRaisesRegex(ValueError,'side'):domestic_bundle(data)

    def test_positive_orphan_rejected_by_shared_normalizer(self):
        data=domestic();data['orders'].append({**data['orders'][0],'ord_dt':'20260920','odno':'orphan'})
        with self.assertRaisesRegex(ValueError,'corroboration'):domestic_bundle(data)

    def test_zero_quantity_unknown_side_is_ignored(self):
        data=domestic();data['orders'].append({**data['orders'][0],'odno':'unfilled','sll_buy_dvsn_cd':'99','tot_ccld_qty':'0'})
        rows=domestic_bundle(data)
        self.assertEqual(rows[0]['order_ids'],['one'])
        self.assertEqual(rows[0]['quantity'],'1')

    def test_multiple_executed_orders_each_preserved_once(self):
        data=domestic();data['orders'].append({**data['orders'][0],'odno':'two'})
        data['days'][0].update(buy_qty='2',buy_amt='20',hldg_qty='2')
        rows=domestic_bundle(data)
        self.assertEqual(rows[0]['order_ids'],['one','two'])
        self.assertEqual(rows[0]['quantity'],'2')
        data['days'].append(copy.deepcopy(data['days'][0]))
        with self.assertRaisesRegex(ValueError,'represented'):domestic_bundle(data)

    def test_capture_rejects_unknown_executed_side(self):
        data=domestic();data['orders'].append({**data['orders'][0],'odno':'unknown','sll_buy_dvsn_cd':'99'})
        client=KIS();original=client.account_pages
        def pages(kind,**kwargs):
            result=original(kind,**kwargs)
            if kind=='domestic_history':result['output1']=data['orders']
            if kind=='domestic_trade_profit':
                result['output1']=data['days']
                if kwargs.get('symbol'):result['output2']=list(data['costs_by_day_symbol'].values())
            return result
        client.account_pages=pages
        with self.assertRaisesRegex(ValueError,'side'):
            collect_bundle('kis',KIS_SCOPE.account,start_ms=ms('2026-09-21T00:00:00+00:00'),
                           end_ms=ms('2026-09-21T01:00:00+00:00'),client=client,scope=KIS_SCOPE)

    def test_compare_and_rederived_apply_reject_without_writes(self):
        with TemporaryDirectory() as tmp:
            store=DataStore(Path(tmp)/'synthetic.sqlite');good=bundle(domestic())
            report=compare_bundles(store,[good]);before=store.path.read_bytes()
            bad={**good['sources'][0]['data']['orders'][0],'odno':'bad','sll_buy_dvsn_cd':'99'}
            good['sources'][0]['data']['orders'].append(bad)
            with self.assertRaisesRegex(ValueError,'side'):compare_bundles(store,[good])
            # Even a saved plan with a recomputed file hash must recheck its sources.
            report['bundles']=[good];path=Path(tmp)/'report.json';saved=write_private(path,report)
            with self.assertRaisesRegex(ValueError,'side'):apply_report(store,path,saved['sha256'])
            self.assertEqual(store.path.read_bytes(),before)
