"""Independent synthetic verifier probes; no environment or operational data."""
import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
import unittest
from kis_hl.data_account_audit import compare_bundles, apply_report, write_private
from kis_hl.data_store import DataStore


def fill(tid=1, **kw):
    d=dict(coin='BTC',tid=tid,time=100+tid,side='B',sz='1',px='10',fee='0.1',feeToken='USDC',oid=tid,startPosition='0',closedPnl='0')
    d.update(kw)
    return d


def bundle(rows, complete=False, positions=None):
    return dict(schema_version=1,kind='account-audit-bundle', account=dict(venue='hyperliquid',environment='testnet',native_id='synthetic-verifier'),start_ms=0,end_ms=1000,collected_ms=1000, collection_complete=True,inventory_complete=complete,positions=positions or [],findings=[],sources=[dict(parser='hl_fills',data=rows),dict(parser='hl_funding',data=[])],evidence=[])


class Probes(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=DataStore(self.root/'synthetic.sqlite')
    def report(self,b):
        r=compare_bundles(self.store,[b]);p=self.root/'report.json';write_private(p,r)
        return r,p,hashlib.sha256(p.read_bytes()).hexdigest()
    def test_raw_source_contradiction_rejected(self):
        b=bundle([fill()]);original=copy.deepcopy(b['sources'][0]['data'])
        b['evidence']=[dict(dataset='hl_fills',body=original,raw=json.dumps(original))]
        b['sources'][0]['data'][0]['fee']='9.9'
        try:r=compare_bundles(self.store,[b])
        except ValueError:return
        self.assertTrue(r['blockers'],'Changed normalization input remains falsely backed by old raw source')
    def test_inventory_adapter_cannot_disagree_with_captured_inventory(self):
        b=bundle([fill()],True,[dict(instrument='hl:BTC',quantity='1')])
        native=dict(assetPositions=[dict(position=dict(coin='BTC',szi='99'))])
        b['evidence']=[dict(dataset='hl_fills',body=copy.deepcopy(b['sources'][0]['data'])),dict(dataset='hl_funding',body=[]),dict(dataset='hl_positions:',body=native,raw=json.dumps(native))]
        try:r=compare_bundles(self.store,[b])
        except ValueError:return
        self.assertTrue(r['blockers'],'Adapter position1 masks captured native position99')

    def test_same_timestamp_closed_cycle_does_not_hide_later_inventory_break(self):
        rows=[fill(1,time=100),fill(2,time=100,side='A',startPosition='1',closedPnl='2'),fill(3,time=200,startPosition='50')]
        r=compare_bundles(self.store,[bundle(rows)])
        self.assertTrue(r['blockers'],r['findings'])
    def test_executed_kis_order_without_daily_source_blocks(self):
        b=bundle([])
        b['account']=dict(venue='kis',environment='live',native_id='synthetic-verifier')
        b['end_ms']=2000000000000
        b['sources']=[dict(parser='kis_domestic_bundle',data=dict(days=[],orders=[dict(ord_dt='20260921',pdno='005930',odno='1',ord_gno_brno='001',tot_ccld_qty='1',tot_ccld_amt='100',sll_buy_dvsn_cd='02')],costs_by_day_symbol={})),dict(parser='kis_overseas_trans',data=[])]
        try:r=compare_bundles(self.store,[b])
        except ValueError:return
        self.assertTrue(r['blockers'],'Executed order silently ignored because daily corroboration is absent')

    def test_kis_daily_order_maturation_reuses_one_fact_identity(self):
        b=bundle([])
        b['account']=dict(venue='kis',environment='live',native_id='synthetic-verifier')
        b['end_ms']=2000000000000
        day=dict(trad_dt='20260921',pdno='005930',buy_qty='1',buy_amt='100',sll_qty='0',sll_amt='0',hldg_qty='1',pchs_unpr='100',loan_int='0')
        order=dict(ord_dt='20260921',pdno='005930',odno='1',ord_gno_brno='001',tot_ccld_qty='1',tot_ccld_amt='100',sll_buy_dvsn_cd='02')
        costs={'20260921:005930':dict(buy_fee_smtl='1',buy_tax_smtl='0',sll_fee_smtl='0',sll_tltx_smtl='0')}
        domestic=dict(days=[day],orders=[order],costs_by_day_symbol=costs)
        b['sources']=[dict(parser='kis_domestic_bundle',data=domestic),dict(parser='kis_overseas_trans',data=[])]
        r,p,d=self.report(b);self.assertEqual(r['blockers'],[]);apply_report(self.store,p,d)
        day.update(buy_qty='2',buy_amt='200',hldg_qty='2')
        domestic['orders'].append({**order,'odno':'2'})
        r=compare_bundles(self.store,[b]);self.assertEqual(r['blockers'],[]);self.assertEqual(r['missing'],[])
        self.assertEqual([c['action'] for c in r['changes']],['correct'])
        q=self.root/'mature.json';receipt=write_private(q,r)
        apply_report(self.store,q,receipt['sha256'],allow_corrections=True)
        facts=self.store.facts('trade');self.assertEqual(len(facts),1);self.assertEqual(facts[0]['revision'],2)
        self.assertEqual(facts[0]['payload']['quantity'],'2')

    def test_daily_to_point_funding_equivalence_is_not_double_counted(self):
        from decimal import Decimal
        from kis_hl.data_quality import effective_funding
        day=86400000
        b=bundle([]);b['end_ms']=day*3
        b['sources'][1]['data']=[dict(time=day,hash='daily',delta=dict(coin='BTC',usdc='-2',nSamples=2))]
        r,p,d=self.report(b);self.assertEqual(r['blockers'],[]);apply_report(self.store,p,d)
        b['sources'][1]['data']=[dict(time=day+i*3600000,hash=str(i),delta=dict(coin='BTC',usdc='-1')) for i in [1,2]]
        r=compare_bundles(self.store,[b]);self.assertEqual(r['blockers'],[]);self.assertEqual(r['missing'],[])
        q=self.root/'points.json';receipt=write_private(q,r);apply_report(self.store,q,receipt['sha256'])
        facts,issues=effective_funding(self.store.facts('cash'));self.assertEqual(issues,[])
        self.assertEqual(sum(Decimal(f['payload']['amount']) for f in facts),Decimal('-2'))

    def test_old_report_reexport_is_byte_identical_after_revision(self):
        from kis_hl.journal_exports import export_report
        b=bundle([fill()]);r,p,d=self.report(b)
        first=apply_report(self.store,p,d,journals=True)
        old=self.root/'old.json';export_report(self.store,first['journal_ids'][0],old)
        original=old.read_bytes()
        b['sources'][0]['data'][0]['fee']='0.2'
        r=compare_bundles(self.store,[b]);q=self.root/'revision.json';receipt=write_private(q,r)
        new=apply_report(self.store,q,receipt['sha256'],allow_corrections=True,journals=True)
        self.assertNotEqual(new['journal_ids'],first['journal_ids'])
        reexport=self.root/'old-reexport.json';export_report(self.store,first['journal_ids'][0],reexport)
        self.assertEqual(reexport.read_bytes(),original)

    def bounded_bundle(self, initial_rows=None):
        from kis_hl.data_ingestion import ingest_rows
        aid=self.store.account('hyperliquid','testnet','synthetic-verifier')
        ingest_rows(self.store,aid,'hl_fills',initial_rows or [fill(time=100)])
        b=bundle([],True,[dict(instrument='hl:BTC',quantity='1')])
        b['start_ms']=500
        b['sources'][1]['data']=[dict(time=600,hash='bounded',delta=dict(coin='BTC',usdc='-0.1'))]
        return aid,b

    def test_bounded_funding_capture_applies_with_earlier_anchored_inventory(self):
        aid,b=self.bounded_bundle();r,p,d=self.report(b)
        self.assertEqual(r['blockers'],[]);self.assertEqual(r['missing'],[])
        self.assertEqual(len(r['changes']),1);self.assertEqual(r['changes'][0]['dataset'],'cash')
        out=apply_report(self.store,p,d,journals=True)
        self.assertEqual(len(self.store.facts('trade')),1);self.assertEqual(len(self.store.facts('cash')),1)
        self.assertFalse(out['coverage_certified'])

    def test_bounded_capture_still_blocks_missing_fills_inside_interval(self):
        aid,b=self.bounded_bundle([fill(time=100),fill(2,time=600,startPosition='1')])
        b['positions'][0]['quantity']='2'
        r=compare_bundles(self.store,[b])
        self.assertEqual(len(r['missing']),1)
        self.assertIn('saved_records_absent_from_source',{x['code'] for x in r['blockers']})

    def test_bounded_capture_prior_canonical_discontinuity_still_blocks(self):
        aid,b=self.bounded_bundle([fill(time=100),fill(2,time=200,startPosition='50')])
        b['positions'][0]['quantity']='2'
        r=compare_bundles(self.store,[b])
        self.assertIn('inventory_discontinuity',{x['code'] for x in r['blockers']})

    def test_bounded_capture_prior_history_change_stales_review(self):
        from kis_hl.data_ingestion import ingest_rows
        aid,b=self.bounded_bundle();r,p,d=self.report(b)
        ingest_rows(self.store,aid,'hl_fills',[fill(2,time=200,startPosition='1')])
        with self.assertRaisesRegex(ValueError,'stale'):apply_report(self.store,p,d)
        self.assertEqual(self.store.facts('cash'),[])

    def test_bounded_capture_excludes_canonical_fills_after_end(self):
        aid,b=self.bounded_bundle([fill(time=100),fill(2,time=1200,startPosition='99')])
        r=compare_bundles(self.store,[b])
        self.assertEqual(r['blockers'],[]);self.assertEqual(r['missing'],[])

    def test_unknown_old_inventory_cannot_hide_new_native_discontinuity(self):
        from kis_hl.data_ingestion import hl_fill,ingest_rows
        aid=self.store.account('hyperliquid','testnet','synthetic-verifier')
        _,_,old=hl_fill(fill(time=100));old.pop('position_before');old['source_id']='old-portable'
        ingest_rows(self.store,aid,'statement',[old])
        b=bundle([fill(2,time=600),fill(3,time=700,startPosition='50')])
        b['start_ms']=500
        r=compare_bundles(self.store,[b])
        self.assertTrue(r['blockers'],r['findings'])

    def test_unknown_old_inventory_cannot_hide_later_canonical_discontinuity(self):
        from kis_hl.data_ingestion import hl_fill,ingest_rows
        aid=self.store.account('hyperliquid','testnet','synthetic-verifier')
        _,_,old=hl_fill(fill(time=100));old.pop('position_before');old['source_id']='old-portable'
        ingest_rows(self.store,aid,'statement',[old])
        ingest_rows(self.store,aid,'hl_fills',[fill(2,time=200),fill(3,time=300,startPosition='50')])
        b=bundle([]);b['start_ms']=500
        r=compare_bundles(self.store,[b])
        self.assertTrue(r['blockers'],r['findings'])

    def test_unknown_prefix_can_resume_at_native_anchor_without_certifying_gap(self):
        from kis_hl.data_ingestion import hl_fill,ingest_rows
        aid=self.store.account('hyperliquid','testnet','synthetic-verifier')
        _,_,old=hl_fill(fill(time=100));old.pop('position_before');old['source_id']='old-portable'
        ingest_rows(self.store,aid,'statement',[old])
        b=bundle([fill(2,time=600)],True,[dict(instrument='hl:BTC',quantity='1')]);b['start_ms']=500
        r=compare_bundles(self.store,[b])
        self.assertEqual(r['blockers'],[])
        self.assertIn('inventory_unanchored',{f['code'] for f in r['findings']})
        self.assertFalse(r['coverage_certified'])

    def test_unknown_prefix_cannot_hide_native_anchor_snapshot_mismatch(self):
        from kis_hl.data_ingestion import hl_fill,ingest_rows
        aid=self.store.account('hyperliquid','testnet','synthetic-verifier')
        _,_,old=hl_fill(fill(time=100));old.pop('position_before');old['source_id']='old-portable'
        ingest_rows(self.store,aid,'statement',[old])
        b=bundle([fill(2,time=600)],True,[dict(instrument='hl:BTC',quantity='99')]);b['start_ms']=500
        r=compare_bundles(self.store,[b])
        self.assertIn('current_inventory_mismatch',{f['code'] for f in r['blockers']})

    def test_two_concurrent_apply_calls_have_one_receipt(self):
        r,p,d=self.report(bundle([fill()]))
        def run():return apply_report(DataStore(self.store.path),p,d,journals=True)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:run(),range(2)))
        self.assertEqual(sorted(x['already_applied'] for x in results),[False,True])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM fact_revisions').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM analysis_runs').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM collection_runs').fetchone()[0],1)
    def test_unrelated_account_mutation_does_not_stale_selected_scope(self):
        r,p,d=self.report(bundle([fill()]))
        self.store.account('kis','live','unrelated')
        out=apply_report(self.store,p,d)
        self.assertTrue(out['applied'])
    def test_same_timestamp_closed_cycle_current_inventory_disagreement_blocks(self):
        rows=[fill(1,time=100),fill(2,time=100,side='A',startPosition='1',closedPnl='2')]
        r=compare_bundles(self.store,[bundle(rows,True,[dict(instrument='hl:BTC',quantity='99')])])
        self.assertTrue(r['blockers'],r['findings'])

if __name__=='__main__':unittest.main(verbosity=2)
