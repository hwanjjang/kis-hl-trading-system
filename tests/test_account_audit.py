"""Behavioral contracts for source-backed account audit and explicit adjustment."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from kis_hl.data_store import DataStore, encode
from kis_hl.data_ingestion import ingest_rows


def fill(tid=1, **changes):
    return dict(coin='BTC',tid=tid,time=100+tid,side='B',sz='1',px='10',fee='0.1',
                feeToken='USDC',oid=tid,startPosition='0',closedPnl='0',**changes)


def bundle(rows=None, *, account='synthetic', funding=None):
    return {'schema_version':1,'kind':'account-audit-bundle',
            'account':{'venue':'hyperliquid','environment':'testnet','native_id':account},
            'start_ms':0,'end_ms':1000,'collected_ms':1000,'collection_complete':True,
            'findings':[], 'inventory_complete':False,'positions':[], 'evidence':[],
            'sources':[{'parser':'hl_fills','data':rows if rows is not None else [fill()]},
                       {'parser':'hl_funding','data':funding or []}]}


class AccountAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name);self.store=DataStore(self.path/'state.sqlite')
        self.aid=self.store.account('hyperliquid','testnet','synthetic',label='tradefi')

    def api(self):
        from kis_hl.data_account_audit import compare_bundles,apply_report,write_private
        return compare_bundles,apply_report,write_private

    def report(self, inputs):
        compare,_,write=self.api();result=compare(DataStore(self.store.path,readonly=True),inputs)
        p=self.path/f'report-{len(list(self.path.glob("report-*.json")))}.json'
        write(p,result);return p,hashlib.sha256(p.read_bytes()).hexdigest(),result

    def counts(self):
        with self.store.connect() as db:
            return {t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in
                    ['fact_revisions','source_observations','analysis_runs','dataset_coverage','collection_runs']}

    def test_compare_does_not_write_and_apply_replays_without_duplicates(self):
        before=self.counts();p,d,r=self.report([bundle()]);self.assertEqual(before,self.counts())
        self.assertEqual(len(r['changes']),1);self.assertEqual(r['blockers'],[])
        out=self.api()[1](self.store,p,d,journals=True);self.assertEqual(len(out['journal_ids']),1)
        after=self.counts();again=self.api()[1](self.store,p,d,journals=True)
        self.assertTrue(again['already_applied']);self.assertEqual(after,self.counts())
        self.assertEqual(out['journal_ids'],again['journal_ids'])
        self.assertEqual(len(self.store.facts('trade')),1)
        self.assertTrue(all(c['status']!='complete' for c in self.store.status()['coverage']))

    def test_digest_and_stale_state_fail_before_mutation(self):
        p,d,_=self.report([bundle()]);before=self.counts()
        with self.assertRaisesRegex(ValueError,'digest'):self.api()[1](self.store,p,'0'*64)
        self.assertEqual(before,self.counts())
        ingest_rows(self.store,self.aid,'hl_fills',[fill(2)])
        before=self.counts()
        with self.assertRaisesRegex(ValueError,'changed|stale'):self.api()[1](self.store,p,d)
        self.assertEqual(before,self.counts())

    def test_revision_requires_correction_flag_and_preserves_old_report(self):
        ingest_rows(self.store,self.aid,'hl_fills',[fill()])
        from kis_hl.journal_exports import journal
        old=journal(self.store,[self.aid]);before=self.counts()
        revised={**fill(),'fee':'0.2'};p,d,r=self.report([bundle([revised])])
        self.assertEqual(r['changes'][0]['action'],'correct')
        with self.assertRaisesRegex(ValueError,'correction'):self.api()[1](self.store,p,d)
        self.assertEqual(before,self.counts())
        self.api()[1](self.store,p,d,allow_corrections=True,journals=True)
        self.assertEqual(self.store.facts('trade')[0]['revision'],2)
        with self.store.connect() as db:
            saved=json.loads(db.execute('SELECT result FROM analysis_runs WHERE id=?',(old['report_id'],)).fetchone()[0])
        self.assertEqual(saved['accounts'],old['accounts'])

    def test_missing_saved_records_and_partial_collection_block(self):
        ingest_rows(self.store,self.aid,'hl_fills',[fill()])
        p,d,r=self.report([bundle([])]);self.assertTrue(r['missing']);self.assertTrue(r['blockers'])
        with self.assertRaisesRegex(ValueError,'unresolved'):self.api()[1](self.store,p,d)
        b=bundle();b['collection_complete']=False
        self.assertTrue(self.report([b])[2]['blockers'])

    def test_scope_isolation_and_combined_journals(self):
        other=bundle(account='second');p,d,_=self.report([bundle(),other])
        out=self.api()[1](self.store,p,d,journals=True)
        self.assertEqual(len(out['journal_ids']),3)
        self.assertEqual(len(self.store.facts('trade')),2)
        self.assertEqual({f['scope'] for f in self.store.facts('trade')},set(out['accounts']))

    def test_funding_equivalence_not_missing_or_double_charged(self):
        day=86400000
        points=[{'time':day+i*3600000,'hash':str(i),'delta':{'coin':'BTC','usdc':'-1'}} for i in [1,2]]
        ingest_rows(self.store,self.aid,'hl_funding',points)
        daily={'time':day,'hash':'daily','delta':{'coin':'BTC','usdc':'-2','nSamples':2}}
        b=bundle([],funding=[daily]);b['end_ms']=day*3
        p,d,r=self.report([b]);self.assertEqual(r['blockers'],[]);self.assertEqual(r['missing'],[])
        self.api()[1](self.store,p,d)
        from kis_hl.data_quality import effective_funding
        facts,issues=effective_funding(self.store.facts('cash'))
        self.assertEqual(issues,[]);self.assertEqual(sum(Decimal(f['payload']['amount']) for f in facts),-2)
        daily['delta']['usdc']='-3';b=bundle([],funding=[daily]);b['end_ms']=day*3
        self.assertTrue(self.report([b])[2]['blockers'])

    def test_atomic_rollback_on_journal_failure(self):
        p,d,_=self.report([bundle()]);before=self.counts()
        with patch('kis_hl.journal_exports.journal',side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):self.api()[1](self.store,p,d,journals=True)
        self.assertEqual(before,self.counts())

    def test_reject_secret_and_duplicate_account_bundles(self):
        b=bundle();b['access_token']='synthetic-secret'
        with self.assertRaises(ValueError):self.report([b])
        with self.assertRaises(ValueError):self.report([bundle(),bundle()])

    def test_private_new_path_only(self):
        _,_,write=self.api();p=self.path/'private.json';write(p,{'safe':True})
        self.assertEqual(p.stat().st_mode&0o777,0o600)
        with self.assertRaises(FileExistsError):write(p,{'changed':True})
        self.assertEqual(json.loads(p.read_text()),{'safe':True})

    def test_report_tampering_even_with_new_digest_is_rederived(self):
        p,_,r=self.report([bundle()]);r['changes'][0]['payload']['quantity']='999'
        p.write_text(encode(r));d=hashlib.sha256(p.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'report|plan'):self.api()[1](self.store,p,d)
        self.assertEqual(self.store.facts('trade'),[])

    def test_source_inventory_mismatch_blocks(self):
        b=bundle();b['inventory_complete']=True;b['positions']=[{'instrument':'hl:BTC','quantity':'2'}]
        p,d,r=self.report([b]);self.assertTrue(r['blockers'])
        with self.assertRaises(ValueError):self.api()[1](self.store,p,d)

    def test_fee_breakdown_difference_and_coverage_drift_are_detected(self):
        p,d,_=self.report([bundle()])
        self.store.coverage('trade',self.aid,0,1000,'partial',{'reason':'concurrent audit'})
        with self.assertRaisesRegex(ValueError,'stale'):self.api()[1](self.store,p,d)

    def test_half_open_range_does_not_flag_older_saved_history(self):
        ingest_rows(self.store,self.aid,'hl_fills',[fill()])
        b=bundle([]);b['start_ms']=500
        self.assertEqual(self.report([b])[2]['missing'],[])

    def test_malformed_or_cross_venue_sources_rejected(self):
        b=bundle();b['sources'][0]['parser']='statement'
        with self.assertRaises(ValueError):self.report([b])
        b=bundle();b['sources'][0]['data'][0]['time']=1000
        with self.assertRaisesRegex(ValueError,'outside'):self.report([b])

    def test_existing_report_ids_and_exports_are_immutable_after_new_activity(self):
        from kis_hl.journal_exports import journal,export_report
        ingest_rows(self.store,self.aid,'hl_fills',[fill()])
        old=journal(self.store,[self.aid]);export=self.path/'old.json';export_report(self.store,old['report_id'],export)
        before=export.read_bytes()
        exit_fill={**fill(2),'side':'A','startPosition':'1','px':'12','closedPnl':'2'}
        p,d,_=self.report([bundle([fill(),exit_fill])]);out=self.api()[1](self.store,p,d,journals=True)
        self.assertNotIn(old['report_id'],out['journal_ids']);self.assertEqual(export.read_bytes(),before)

    def test_unknown_inventory_is_visible_not_fabricated(self):
        b=bundle([{**fill(),'startPosition':'5'}]);r=self.report([b])[2]
        self.assertIn('opening_inventory_partial',{f['code'] for f in r['findings']})
        self.assertFalse(r['coverage_certified'])

    def test_replay_with_different_journal_option_is_explicit(self):
        p,d,_=self.report([bundle()]);self.api()[1](self.store,p,d)
        with self.assertRaisesRegex(ValueError,'journal'):self.api()[1](self.store,p,d,journals=True)

    def test_same_time_funding_with_distinct_ids_is_ambiguous(self):
        funding=[{'time':500,'hash':h,'delta':{'coin':'BTC','usdc':'-1'}} for h in ['one','two']]
        self.assertTrue(self.report([bundle(funding=funding)])[2]['blockers'])

    def test_current_kis_scoped_holdings_mismatch_blocks_without_global_completeness(self):
        day={'trad_dt':'20260920','pdno':'069500','buy_qty':'1','buy_amt':'10','sll_qty':'0','sll_amt':'0','hldg_qty':'1','pchs_unpr':'10','loan_int':'0'}
        order={'ord_dt':'20260920','pdno':'069500','odno':'one','sll_buy_dvsn_cd':'02','tot_ccld_qty':'1','tot_ccld_amt':'10'}
        costs={'buy_fee_smtl':'0','sll_fee_smtl':'0','buy_tax_smtl':'0','sll_tltx_smtl':'0'}
        b={'schema_version':1,'kind':'account-audit-bundle','account':{'venue':'kis','environment':'live','native_id':'synthetic-kis'},
           'start_ms':1789830000000,'end_ms':1789916400000,'requested_end_ms':1789916399000,
           'collected_ms':1789916399500,'inventory_observed_ms':1789916399500,
           'collection_complete':True,'findings':[],'inventory_complete':False,
           'inventory_scope':{'markets':['domestic','NASD','NYSE','AMEX'],'currency_overseas':'USD'},
           'positions':[{'instrument':'kis:069500','quantity':'0'}],'evidence':[],
           'sources':[{'parser':'kis_domestic_bundle','data':{'days':[day],'orders':[order],'costs_by_day_symbol':{'20260920:069500':costs}}},
                      {'parser':'kis_overseas_trans','data':[]}]}
        r=self.report([b])[2]
        self.assertIn('current_inventory_mismatch',{f['code'] for f in r['blockers']})
        b['inventory_observed_ms']=b['requested_end_ms']+86400000
        self.assertNotIn('current_inventory_mismatch',{f['code'] for f in self.report([b])[2]['blockers']})

    def test_same_millisecond_flat_cycle_still_checks_later_inventory(self):
        buy={**fill(),'time':100};sell={**fill(2),'time':100,'side':'A','startPosition':'1'}
        bad={**fill(3),'time':200,'startPosition':'50'}
        r=self.report([bundle([buy,sell,bad])])[2]
        self.assertIn('inventory_discontinuity',{f['code'] for f in r['blockers']})
        b=bundle([buy,sell]);b['inventory_complete']=True;b['positions']=[{'instrument':'hl:BTC','quantity':'99'}]
        self.assertIn('current_inventory_mismatch',{f['code'] for f in self.report([b])[2]['blockers']})

    def test_native_adapter_input_must_match_retained_evidence(self):
        b=bundle();b['evidence']=[{'dataset':'hl_fills','body':[fill()],'raw':json.dumps([fill()])},
                                  {'dataset':'hl_funding','body':[],'raw':'[]'}]
        self.assertEqual(self.report([b])[2]['blockers'],[])
        b['sources'][0]['data'][0]['fee']='9.9'
        with self.assertRaisesRegex(ValueError,'evidence'):self.report([b])

    def test_orphan_positive_kis_order_cannot_disappear(self):
        b={'schema_version':1,'kind':'account-audit-bundle','account':{'venue':'kis','environment':'live','native_id':'synthetic-kis'},
           'start_ms':1789830000000,'end_ms':1789916400000,'collection_complete':True,'findings':[],
           'inventory_complete':False,'positions':[],'evidence':[],
           'sources':[{'parser':'kis_domestic_bundle','data':{'days':[],
               'orders':[{'ord_dt':'20260920','pdno':'069500','tot_ccld_qty':'1','tot_ccld_amt':'10'}],
               'costs_by_day_symbol':{}}},{'parser':'kis_overseas_trans','data':[]}]}
        with self.assertRaisesRegex(ValueError,'daily'):self.report([b])

    def test_inventory_adapter_input_must_match_retained_evidence(self):
        b=bundle();b['inventory_complete']=True;b['positions']=[{'instrument':'hl:BTC','quantity':'1'}]
        b['evidence']=[{'dataset':'hl_fills','body':[fill()]},{'dataset':'hl_funding','body':[]},
                       {'dataset':'hl_positions:','body':{'assetPositions':[{'position':{'coin':'BTC','szi':'99'}}]}}]
        with self.assertRaisesRegex(ValueError,'inventory.*evidence'):self.report([b])

    def test_bounded_funding_only_capture_uses_existing_inventory_history(self):
        ingest_rows(self.store,self.aid,'hl_fills',[fill()])
        b=bundle([],funding=[{'time':600,'hash':'later','delta':{'coin':'BTC','usdc':'-0.1'}}])
        b['start_ms']=500;b['inventory_complete']=True
        b['positions']=[{'instrument':'hl:BTC','quantity':'1'}]
        r=self.report([b])[2]
        self.assertEqual(r['blockers'],[])
        self.assertEqual(len(r['changes']),1)

    def test_unknown_prefix_does_not_skip_later_native_inventory_checks(self):
        from kis_hl.data_ingestion import hl_fill
        _,_,old=hl_fill(fill());old.pop('position_before');old['source_id']='old-portable'
        ingest_rows(self.store,self.aid,'statement',[old])
        b=bundle([{**fill(2),'time':600},{**fill(3),'time':700,'startPosition':'50'}])
        b['start_ms']=500
        r=self.report([b])[2]
        self.assertIn('inventory_unanchored',{f['code'] for f in r['findings']})
        self.assertIn('inventory_discontinuity',{f['code'] for f in r['blockers']})
        b['sources'][0]['data'].pop();b['inventory_complete']=True
        b['positions']=[{'instrument':'hl:BTC','quantity':'99'}]
        self.assertIn('current_inventory_mismatch',{f['code'] for f in self.report([b])[2]['blockers']})
        b['positions'][0]['quantity']='1'
        r=self.report([b])[2]
        self.assertEqual(r['blockers'],[])
        self.assertFalse(r['coverage_certified'])
