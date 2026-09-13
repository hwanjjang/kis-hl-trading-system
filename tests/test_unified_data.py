import unittest
from kis_hl.cli import build_parser


class CommandContractTests(unittest.TestCase):
    def test_canonical_data_cli_is_registered(self):
        help_text = build_parser().format_help()
        self.assertIn('data', help_text)
        self.assertIn('market', help_text)
        self.assertIn('analysis', help_text)

import hashlib
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date


class CanonicalTests(unittest.TestCase):
    def setUp(self):
        from kis_hl.data_store import DataStore
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = DataStore(Path(self.temp.name)/'test.sqlite')
        self.account = self.store.account('hyperliquid','testnet','synthetic',label='tradefi')

    def test_evidence_revisions_and_asof(self):
        from kis_hl.data_store import number
        p = {'instrument':'hl:BTC','event_start_ms':1,'event_end_ms':2,'price':'10'}
        a = self.store.observe('fixture',self.account,b'{"value":1}')
        b = self.store.observe('fixture',self.account,b'{"value":1}')
        one = self.store.fact('fill',self.account,'x',p,observation=a,known_ms=10)
        self.assertEqual(one,self.store.fact('fill',self.account,'x',p,observation=b,known_ms=11))
        with self.assertRaises(ValueError):
            self.store.fact('fill',self.account,'x',{**p,'price':'11'},observation=b,known_ms=20)
        self.store.fact('fill',self.account,'x',{**p,'price':'11'},observation=b,known_ms=20,allow_correction=True)
        self.assertEqual(self.store.facts('fill',as_of_ms=15)[0]['payload']['price'],'10')
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM raw_payloads').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM source_observations').fetchone()[0],2)
        for v in [1.2,'NaN','Infinity',True]:
            with self.assertRaises(ValueError): number(v)
        with self.assertRaises(ValueError): self.store.observe('x','x',b'{"access_token":"secret"}')

    def test_funding_identity_and_overlapping_grains(self):
        from kis_hl.data_ingestion import ingest_rows
        from kis_hl.data_quality import effective_funding
        day = 86400000
        rows = [{'hash':'0x0','time':day*d,'delta':{'coin':'BTC','usdc':'-1','nSamples':24}} for d in [1,2]]
        ingest_rows(self.store,self.account,'hl_funding',rows)
        ingest_rows(self.store,self.account,'hl_funding',rows)
        self.assertEqual(len(self.store.facts('cash')),2)
        ingest_rows(self.store,self.account,'hl_funding',[{'hash':'hour','time':day+1000,'delta':{'coin':'BTC','usdc':'-0.1'}}])
        active, issues = effective_funding(self.store.facts('cash'))
        self.assertEqual(len(active),1)
        self.assertEqual(len(issues),1)

    def test_import_manifest_digest_and_repeat(self):
        from kis_hl.data_import import import_manifest
        raw = Path(self.temp.name)/'fills.json'
        raw.write_text('[{"coin":"BTC","tid":1,"time":100,"side":"B","sz":"1","px":"10","fee":"0.1","feeToken":"USDC","oid":1,"startPosition":"0","closedPnl":"0"}]')
        manifest={'schema_version':1,'accounts':[{'alias':'t','venue':'hyperliquid','environment':'testnet','native_id':'synthetic','label':'tradefi'}], 'files':[{'path':'fills.json','sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'account':'t','role':'raw','parser':'hl_fills'}]}
        p=Path(self.temp.name)/'manifest.json';p.write_text(json.dumps(manifest))
        self.assertEqual(import_manifest(self.store,p,apply=False)['raw_files'],1)
        import_manifest(self.store,p,apply=True);import_manifest(self.store,p,apply=True)
        self.assertEqual(len(self.store.facts('trade')),1)
        raw.write_text('[]')
        with self.assertRaises(ValueError):import_manifest(self.store,p,apply=True)

    def test_backup_preserves_legacy_state(self):
        from kis_hl.data_maintenance import backup, restore
        with self.store.connect() as db:
            db.execute('CREATE TABLE operational_owner(id TEXT)')
            db.execute("INSERT INTO operational_owner VALUES('sentinel')")
        dest=Path(self.temp.name)/'backup.sqlite';backup(self.store,dest)
        target=Path(self.temp.name)/'restored.sqlite';restore(dest,target)
        with sqlite3.connect(target) as db:
            self.assertEqual(db.execute('SELECT id FROM operational_owner').fetchone()[0],'sentinel')
        with self.assertRaises(ValueError):restore(dest,self.store.path)


class MarketTests(unittest.TestCase):
    def test_ten_calendar_years_and_incomplete_week(self):
        from kis_hl.market_series import history_start, derive_weekly
        self.assertEqual(history_start(date(2024,2,29),10),date(2014,2,28))
        days=[{'date':d,'open':'1','high':'3','low':'1','close':'2','volume':'1','id':i} for i,d in enumerate(['2024-03-04','2024-03-05','2024-03-06','2024-03-07'])]
        result=derive_weekly(days,timezone='America/New_York',expected_sessions=['2024-03-04','2024-03-05','2024-03-06','2024-03-07','2024-03-08'],now_ms=1710200000000)
        self.assertFalse(result[0]['complete'])
        self.assertEqual(result[0]['missing_sessions'],['2024-03-08'])
        self.assertEqual(result[0]['volume'],'4')

class KisPeriodTests(unittest.TestCase):
    def test_weekly_request_is_explicit(self):
        from kis_hl.kis.client import KisClient
        client=object.__new__(KisClient)
        calls=[]
        client._request_with_auth=lambda *args,**kwargs:calls.append(kwargs)
        client.domestic_chart(symbol='069500',date_from='20160101',date_to='20260101',period='W')
        self.assertEqual(calls[-1]['query']['FID_PERIOD_DIV_CODE'],'W')
        client.overseas_stock_chart(symbol='SPY',exchange='AMS',period='W')
        self.assertEqual(calls[-1]['query']['GUBN'],'1')
        with self.assertRaises(ValueError):client.overseas_stock_chart(symbol='SPY',exchange='AMS',period='bad')

class AccountRouteTests(unittest.TestCase):
    def test_statement_routes_use_distinct_ids_and_live_only(self):
        from kis_hl.kis.routes import account_route
        kwargs=dict(exchange='NASD',symbol='',date_from='20260101',date_to='20260131',price='0',paper=False,older_history=False)
        domestic=account_route('domestic_trade_profit',**kwargs)
        overseas=account_route('overseas_transactions',**kwargs)
        self.assertEqual(domestic[1],'TTTC8715R');self.assertEqual(overseas[1],'CTOS4001R')
        self.assertIsNone(domestic[2]);self.assertIsNone(overseas[2]);self.assertEqual(overseas[4],100)

class JournalContractTests(CanonicalTests):
    def test_partial_exit_then_add_conserves_cashflow(self):
        from kis_hl.data_ingestion import ingest_rows
        from kis_hl.journal_exports import journal
        rows=[]
        for i,(side,q,p) in enumerate([('buy','10','100'),('sell','5','200'),('buy','5','300'),('sell','10','200')]):
            rows.append(dict(source_id=str(i),instrument='kis:X',currency='USD',event_start_ms=100+i*10,event_end_ms=101+i*10,time_precision='MILLISECOND',grain='EXECUTION',side=side,quantity=q,price=p,notional=str(int(q)*int(p)),total_cost='0',costs={}))
        rows[0]['position_before']='0'
        ingest_rows(self.store,self.account,'statement',rows)
        self.store.coverage('trade',self.account,0,1000,'complete',{})
        report=journal(self.store,[self.account])
        self.assertEqual(report['cycles'][0]['gross_pnl'],'500')
        self.assertEqual(report['cycles'][0]['status'],'FINALIZED')

    def test_report_export_rejects_database_target(self):
        from kis_hl.journal_exports import export_report
        run=self.store.pin('journal',{},[],{})
        with self.assertRaises(ValueError):export_report(self.store,run,self.store.path)
        self.assertEqual(self.store.status()['schema_version'],1)

    def test_preview_validates_all_source_rows_without_partial_facts(self):
        from kis_hl.data_import import import_manifest
        good={'coin':'BTC','tid':1,'time':100,'side':'B','sz':'1','px':'10','fee':'0','feeToken':'USDC','oid':1,'startPosition':'0','closedPnl':'0'}
        raw=Path(self.temp.name)/'bad.json';raw.write_text(json.dumps([good,{**good,'tid':2,'feeToken':'OTHER'}]))
        manifest={'schema_version':1,'accounts':[{'alias':'a','venue':'hyperliquid','environment':'testnet','native_id':'synthetic'}],'files':[{'path':'bad.json','sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'account':'a','role':'raw','parser':'hl_fills'}]}
        p=Path(self.temp.name)/'manifest.json';p.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):import_manifest(self.store,p,apply=False)
        with self.assertRaises(ValueError):import_manifest(self.store,p,apply=True)
        self.assertEqual(self.store.facts('trade'),[])

class LineageTests(CanonicalTests):
    def test_transitive_stale_analysis(self):
        obs=self.store.observe('fixture',self.account,b'{}')
        p={'instrument':'hl:BTC','event_start_ms':1,'event_end_ms':2,'price':'10'}
        first=self.store.fact('bar',self.account,'day',p,observation=obs)
        weekly=self.store.fact('bar',self.account,'week',{**p,'input_ids':[first]},observation=obs)
        run=self.store.pin('analysis',{},[weekly],{})
        self.store.fact('bar',self.account,'day',{**p,'price':'11'},observation=obs,allow_correction=True)
        self.assertIn(run,self.store.status()['stale_runs'])


class CollectorTests(CanonicalTests):
    def test_hyperliquid_weekly_partial_coverage_and_repeat(self):
        from kis_hl.market_ingestion import backfill
        from types import SimpleNamespace
        rows=[dict(t=1704067200000,T=1704671999999,i='1w',s='BTC',o='10',h='12',l='9',c='11',v='100')]
        client=SimpleNamespace(candle_snapshot=lambda *a,**kw:rows)
        for _ in range(2):backfill(self.store,'hl:BTC','1w',client,start=date(2024,1,1),end=date(2024,1,7))
        self.assertEqual(len(self.store.facts('bar')),1)
        self.assertEqual(self.store.status()['coverage'][0]['status'],'partial')

    def test_kis_backfill_moves_date_cursor(self):
        from kis_hl.market_ingestion import backfill
        from kis_hl.kis.client import KisHttpResponse
        calls=[]
        class Client:
            def domestic_chart(self,**kw):
                calls.append(kw)
                day='20240105' if len(calls)==1 else '20231229'
                rows=[] if len(calls)>2 else [dict(stck_bsop_date=day,stck_oprc='10',stck_hgpr='12',stck_lwpr='9',stck_clpr='11',acml_vol='100')]
                return KisHttpResponse(200,dict(rt_cd='0',output2=rows),{})
        result=backfill(self.store,'kis:069500','1w',Client(),start=date(2023,12,25),end=date(2024,1,7),delay_seconds=0)
        self.assertEqual(result['rows'],2)
        self.assertEqual(calls[1]['date_to'],'20240104')
        self.assertEqual(calls[0]['period'],'W')

    def test_job_failures_do_not_advance_success_clock(self):
        from kis_hl.data_jobs import configure,run_due
        configure(self.store,'one',{'kind':'book','instrument':'hl:BTC'},60)
        def fail(_):raise ValueError('fixture')
        self.assertEqual(run_due(self.store,fail,clock=100)['jobs'][0]['status'],'failed')
        status=self.store.status()['jobs'][0]
        self.assertIsNone(status['last_success_ms']);self.assertEqual(status['last_attempt_ms'],100)
        self.assertEqual(run_due(self.store,lambda _: {},clock=200)['jobs'],[])

    def test_complete_daily_funding_replaced_by_equal_hourly_set(self):
        from kis_hl.data_ingestion import ingest_rows
        from kis_hl.data_quality import effective_funding
        day=86400000
        ingest_rows(self.store,self.account,'hl_funding',[{'hash':'d','time':day,'delta':{'coin':'BTC','usdc':'-2','nSamples':2}},
            {'hash':'a','time':day+1,'delta':{'coin':'BTC','usdc':'-1'}},{'hash':'b','time':day+2,'delta':{'coin':'BTC','usdc':'-1'}}])
        active,issues=effective_funding(self.store.facts('cash'))
        self.assertEqual(len(active),2);self.assertEqual(issues,[])

class DomesticChronologyTests(unittest.TestCase):
    def test_daily_cost_basis_can_disambiguate_sell_and_reentry_without_fake_time(self):
        from kis_hl.data_ingestion import domestic_bundle
        day=lambda d,bq,ba,sq,sa,h,p:dict(trad_dt=d,pdno='X',buy_qty=bq,buy_amt=ba,sll_qty=sq,sll_amt=sa,hldg_qty=h,pchs_unpr=p,loan_int='0')
        order=lambda d,side,q,a,oid:dict(ord_dt=d,pdno='X',sll_buy_dvsn_cd=side,tot_ccld_qty=q,tot_ccld_amt=a,odno=oid)
        zero=dict(buy_fee_smtl='0',sll_fee_smtl='0',buy_tax_smtl='0',sll_tltx_smtl='0')
        bundle={'days':[day('20260101','2','20','0','0','2','10'),day('20260102','1','20','2','30','1','10')],
          'orders':[order('20260101','02','2','20','1'),order('20260102','01','2','30','2'),order('20260102','02','1','20','3')],
          'costs_by_day_symbol':{'20260101:X':zero,'20260102:X':zero}}
        result=domestic_bundle(bundle)
        sold=next(r for r in result if r['side']=='sell')
        rebuy=next(r for r in result if r['source_id'].endswith('"3"]'))
        self.assertEqual(sold['position_before'],'2');self.assertEqual(rebuy['position_before'],'0')
        self.assertEqual(rebuy['time_precision'],'DAY')

class ImportCoverageTests(CanonicalTests):
    def test_invalid_coverage_is_rejected_before_mutation(self):
        from kis_hl.data_import import import_manifest
        manifest={'schema_version':1,'accounts':[{'alias':'a','venue':'hyperliquid','environment':'testnet','native_id':'synthetic'}],'files':[],
            'coverage':[{'account':'a','dataset':'trade','start_ms':20,'end_ms':10,'status':'complete'}]}
        p=Path(self.temp.name)/'coverage.json';p.write_text(json.dumps(manifest))
        for apply in [False,True]:
            with self.assertRaises(ValueError):import_manifest(self.store,p,apply=apply)
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM collection_runs').fetchone()[0],0)

class FinancialInputTests(unittest.TestCase):
    def test_nonfinite_optional_statement_amounts_are_rejected(self):
        from kis_hl.data_ingestion import statement
        base=dict(source_id='x',instrument='kis:X',currency='USD',event_start_ms=1,event_end_ms=2,time_precision='MILLISECOND',grain='EXECUTION',side='buy',quantity='1',price='10',notional='10',total_cost='0',costs={})
        for key in ['gross_pnl','position_before','settlement','day_end_quantity']:
            with self.assertRaises(ValueError):statement({**base,key:'NaN'})

class NativeWeekBoundaryTests(CanonicalTests):
    def test_hyperliquid_thursday_weeks_are_not_reported_missing(self):
        from types import SimpleNamespace
        from kis_hl.market_ingestion import backfill
        # Native Hyperliquid weeks follow the epoch-aligned Thursday boundary.
        rows=[dict(t=1704326400000,T=1704931199999,i='1w',s='BTC',o='10',h='12',l='9',c='11',v='1')]
        client=SimpleNamespace(candle_snapshot=lambda *a,**kw:rows)
        result=backfill(self.store,'hl:BTC','1w',client,start=date(2024,1,4),end=date(2024,1,10))
        self.assertEqual(result['missing_completed_weeks'],[])

    def test_empty_native_response_has_unknown_week_anchor(self):
        from types import SimpleNamespace
        from kis_hl.market_ingestion import backfill
        result=backfill(self.store,'hl:BTC','1w',SimpleNamespace(candle_snapshot=lambda *a,**kw:[]),start=date(2024,1,4),end=date(2024,1,10))
        self.assertEqual(result['native_week_anchor_status'],'unknown')

    def test_weekly_native_interval_must_be_seven_days(self):
        from types import SimpleNamespace
        from kis_hl.market_ingestion import backfill
        rows=[dict(t=1704326400000,T=1704412799999,i='1w',s='BTC',o='10',h='12',l='9',c='11',v='1')]
        with self.assertRaises(ValueError):backfill(self.store,'hl:BTC','1w',SimpleNamespace(candle_snapshot=lambda *a,**kw:rows),start=date(2024,1,4),end=date(2024,1,10))

class IncrementalPollingTests(CanonicalTests):
    def test_runner_passes_only_last_success_to_executor(self):
        from kis_hl.data_jobs import configure,run_due
        configure(self.store,'minute',{'kind':'bar','instrument':'hl:BTC','timeframe':'1m'},60)
        seen=[]
        run_due(self.store,lambda c:seen.append(c.copy()) or {},clock=100)
        run_due(self.store,lambda c:seen.append(c.copy()) or {},clock=60100)
        self.assertIsNone(seen[0]['_last_success_ms']);self.assertEqual(seen[1]['_last_success_ms'],100)

    def test_minute_executor_uses_incremental_window(self):
        from unittest.mock import patch
        from kis_hl.data_cli import execute_job
        with patch('kis_hl.data_cli.client_for'),patch('kis_hl.market_ingestion.backfill',return_value={}) as backfill:
            execute_job(self.store,{'kind':'bar','instrument':'hl:BTC','timeframe':'1m','_last_success_ms':1000000})
            self.assertEqual(backfill.call_args.kwargs['start_ms'],700000)
