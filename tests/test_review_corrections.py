"""Regression contracts from independent Claude and Codex full PR reviews."""
from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kis_hl.data_store import DataStore
from kis_hl.data_ingestion import ingest_rows, statement, kis_overseas, domestic_bundle
from kis_hl.data_account_sync import sync_account
from kis_hl.journal_exports import journal
from kis_hl.journal_sync import Scope
from kis_hl.market_ingestion import backfill, snapshot
from kis_hl.market_series import store_bar
from kis_hl.analysis_store import run_analysis
from kis_hl.kis.client import KisHttpResponse
from tests.test_canonical_inventory import trade


def overseas(quantity='1'):
    amount=str(100*int(quantity))
    return dict(trad_dt='20260102',pdno='SPY',sll_buy_dvsn_cd='02',crcy_cd='USD',
                tr_frcr_amt2=amount,dmst_frcr_fee1='1',frcr_fee1='0',
                frcr_excc_amt_1=str(int(amount)+1),ccld_qty=quantity)


def bundle():
    return dict(days=[dict(trad_dt='20260102',pdno='069500',buy_qty='2',buy_amt='200',
                          sll_qty='0',sll_amt='0',hldg_qty='2',pchs_unpr='100',loan_int='0')],
        orders=[dict(ord_dt='20260102',pdno='069500',sll_buy_dvsn_cd='02',
                     tot_ccld_qty='1',tot_ccld_amt='100',odno=str(i),ord_gno_brno='x') for i in (1,2)],
        costs_by_day_symbol={'20260102:069500':dict(buy_fee_smtl='2',buy_tax_smtl='0',sll_fee_smtl='0',sll_tltx_smtl='0')})


class ReviewCorrections(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store=DataStore(Path(self.tmp.name)/'db.sqlite')
        self.aid=self.store.account('kis','live','synthetic')

    def test_statement_rejects_cost_and_settlement_contradictions(self):
        for row in [trade(1,'buy',1,cost_policy='components_complete') | {'costs':{'broker':'10'}},
                    trade(1,'buy',1,settlement='999')]:
            with self.subTest(row=row), self.assertRaisesRegex(ValueError,'reconcile'):
                statement(row)
        self.assertEqual(statement(trade(1,'buy',1,settlement='101'))[2]['total_cost'],'1')

    def test_nonpositive_overseas_quantity_is_validation_error(self):
        for qty in ['0','-1']:
            with self.assertRaises(ValueError):kis_overseas(overseas(qty))

    def test_duplicate_source_rows_are_not_silently_collapsed(self):
        with self.assertRaisesRegex(ValueError,'[Aa]mbiguous'):
            ingest_rows(self.store,self.aid,'kis_overseas_trans',[overseas(),overseas()])
        self.assertEqual(self.store.facts('trade'),[])
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM source_observations').fetchone()[0],1)
        ingest_rows(self.store,self.aid,'kis_overseas_trans',[overseas()])
        ingest_rows(self.store,self.aid,'kis_overseas_trans',[overseas()])
        self.assertEqual(len(self.store.facts('trade')),1)

    def test_daily_source_maturation_and_unrelated_collection(self):
        class Client:
            quantity='1'
            def account_pages(self,kind,**kw):
                rows=[overseas(self.quantity)] if kind=='overseas_transactions' and kw['exchange']=='AMEX' else []
                return dict(output1=rows,output2=[])
        client=Client();scope=Scope('kis','live','synthetic')
        for qty in ['1','2']:
            client.quantity=qty
            sync_account(self.store,'kis',None,start_ms=1767308400000,end_ms=1767394799999,client=client,scope=scope)
        self.assertEqual(self.store.facts('trade')[0]['payload']['quantity'],'2')
        self.assertEqual(self.store.facts('trade')[0]['revision'],2)
        client.quantity='1'
        result=sync_account(self.store,'kis',None,start_ms=1767308400000,end_ms=1767394799999,client=client,scope=scope)
        self.assertFalse(result['collection_complete'])
        self.assertEqual(self.store.facts('trade')[0]['payload']['quantity'],'2')

    def test_multiple_domestic_orders_remain_grouped_and_overseas_runs(self):
        b=bundle();calls=[]
        class Client:
            def account_pages(self,kind,**kw):
                calls.append(kind)
                if kind=='domestic_trade_profit':return dict(output1=b['days'],output2=list(b['costs_by_day_symbol'].values()))
                if kind=='domestic_history':return dict(output1=b['orders'])
                return dict(output1=[],output2=[])
        result=sync_account(self.store,'kis',None,start_ms=1767308400000,end_ms=1767394799999,client=Client(),scope=Scope('kis','live','synthetic'))
        self.assertIn('overseas_transactions',calls)
        facts=self.store.facts('trade');self.assertEqual(len(facts),1)
        self.assertEqual(facts[0]['payload']['quantity'],'2')
        self.assertIn('shared_order_cost_allocation',facts[0]['payload']['quality_reasons'])

    def test_hl_recovers_only_at_source_flat_anchor(self):
        aid=self.store.account('hyperliquid','testnet','hl')
        rows=[trade(1,'sell',1,instrument='hl:BTC',position_before='1'),
              trade(2,'buy',1,instrument='hl:BTC',position_before='0'),
              trade(3,'sell',1,110,instrument='hl:BTC',position_before='1')]
        ingest_rows(self.store,aid,'statement',rows)
        for ds in ['trade','cash']:self.store.coverage(ds,aid,0,1000,'complete',{})
        report=journal(self.store,[aid])
        self.assertEqual(len(report['cycles']),1)
        self.assertEqual(report['cycles'][0]['status'],'FINALIZED')
        self.assertEqual(report['summary_by_account_currency'][0]['trading_fee'],'3')
        self.assertTrue(report['quality_findings'])

    def test_journal_reads_only_selected_account_datasets(self):
        with patch.object(self.store,'facts',wraps=self.store.facts) as fetch:
            journal(self.store,[self.aid])
        self.assertTrue(fetch.call_args_list)
        for call in fetch.call_args_list:
            self.assertIn(call.args[0],('trade','cash'))
            self.assertEqual(call.kwargs['scope'],self.aid)

    def test_late_funding_marks_old_report_stale_but_not_other_accounts(self):
        rows=[trade(1,'buy',1,instrument='hl:BTC',position_before='0'),trade(2,'sell',1,110,instrument='hl:BTC',position_before='1')]
        for row in rows:row['currency']='USDC'
        ingest_rows(self.store,self.aid,'statement',rows)
        old=journal(self.store,[self.aid]);empty=self.store.account('kis','live','other');other=journal(self.store,[empty])
        ingest_rows(self.store,self.aid,'hl_funding',[dict(time=15,hash='late',delta=dict(coin='BTC',usdc='-2'))])
        stale=self.store.status()['stale_runs']
        self.assertIn(old['report_id'],stale);self.assertNotIn(other['report_id'],stale)

    def test_new_analysis_rejects_stale_weekly_dependency(self):
        obs=self.store.observe('bars','hyperliquid',b'{}')
        day=dict(event_start_ms=10,event_end_ms=20,open='10',high='20',low='5',close='10',volume='1',complete=True)
        source=store_bar(self.store,'hl:BTC','hyperliquid','1d',day,observation=obs)
        store_bar(self.store,'hl:BTC','hyperliquid','1w',{**day,'input_ids':[source]},observation=obs,variant='derived')
        store_bar(self.store,'hl:BTC','hyperliquid','1d',{**day,'close':'20'},observation=obs)
        spec=dict(instrument='hl:BTC',provider='hyperliquid',timeframe='1w',adjustment='raw',price_basis='trade',variant='derived',calendar='UTC',window=1)
        with self.assertRaisesRegex(ValueError,'[Ss]tale'):run_analysis(self.store,spec)

    def test_testnet_market_is_rejected_before_capture(self):
        client=SimpleNamespace(config=SimpleNamespace(base_url='https://api.hyperliquid-testnet.xyz'),
            candle_snapshot=lambda *a,**kw:[],l2_book=lambda *a:None)
        with self.assertRaisesRegex(ValueError,'mainnet'):backfill(self.store,'hl:BTC','1d',client,start=date(2024,1,1),end=date(2024,1,1))
        with self.assertRaisesRegex(ValueError,'mainnet'):snapshot(self.store,'hl:BTC',client)
        self.assertEqual(self.store.facts('bar'),[])

    def test_overseas_book_uses_price_block_and_keeps_clock(self):
        client=SimpleNamespace(order_book=lambda **kw:KisHttpResponse(200,dict(rt_cd='0',output1={'zdate':'20260102','ztime':'100000'},output2={'pbid1':'100','pask1':'101','vbid1':'2','vask1':'3'}),{}))
        snapshot(self.store,'kis:SPY',client)
        p=self.store.facts('book')[0]['payload']
        self.assertEqual((p['bid'],p['ask'],p['bid_size'],p['ask_size']),('100','101','2','3'))
        self.assertEqual(p['source_clock']['ztime'],'100000')

    def test_index_basis_is_explicit(self):
        class Client:
            count=0
            def inquire_overseas_daily_chartprice(self,**kw):
                self.count+=1
                return KisHttpResponse(200,dict(rt_cd='0',output2=[dict(stck_bsop_date='20240102',ovrs_nmix_oprc='10',ovrs_nmix_hgpr='12',ovrs_nmix_lwpr='9',ovrs_nmix_prpr='11',acml_vol='1')] if self.count==1 else []),{})
        backfill(self.store,'index:SPX','1d',Client(),start=date(2024,1,2),end=date(2024,1,2),delay_seconds=0)
        self.assertEqual(self.store.facts('bar')[0]['payload']['price_basis'],'index')

    def test_status_does_not_create_database(self):
        from kis_hl.data_cli import cmd_data
        path=Path(self.tmp.name)/'absent'/'db.sqlite'
        result=cmd_data(SimpleNamespace(data_action='status',db=str(path)))
        self.assertFalse(path.parent.exists())
        self.assertFalse(result['exists'])

    def test_overseas_minutes_page_by_source_local_clock(self):
        calls=[]
        class Client:
            def overseas_intraday_chart(self,**kw):
                calls.append(kw)
                times=['100100','100000'] if len(calls)==1 else ['095900']
                return KisHttpResponse(200,dict(rt_cd='0',output1={'next':'1' if len(calls)==1 else '0'},output2=[dict(xymd='20260102',xhms=t,open='100',high='102',low='99',last='101',evol='2') for t in times]),{})
        result=backfill(self.store,'kis:SPY','1m',Client(),start=date(2026,1,2),end=date(2026,1,2),delay_seconds=0)
        self.assertEqual(len(self.store.facts('bar')),3)
        self.assertEqual(calls[1]['cursor'],'20260102095900')
        self.assertEqual(self.store.facts('bar')[0]['payload']['calendar'],'America/New_York')
        self.assertEqual(self.store.status()['coverage'][0]['status'],'partial')

    def test_account_jobs_use_overlap_and_separate_audits(self):
        from kis_hl.data_cli import execute_job
        with patch('kis_hl.data_account_sync.sync_account',return_value={}) as sync:
            execute_job(self.store,dict(kind='account',venue='kis',start_ms=1000,_last_success_ms=1000000000,overlap_ms=10000))
            self.assertEqual(sync.call_args.kwargs['start_ms'],999990000)
            execute_job(self.store,dict(kind='account',venue='kis',start_ms=1000,_last_success_ms=1000000000,history_audit=True))
            self.assertEqual(sync.call_args.kwargs['start_ms'],1000)

    def test_partial_collection_does_not_advance_success_cursor(self):
        from kis_hl.data_jobs import configure,run_due
        configure(self.store,'account',dict(kind='account'))
        result=run_due(self.store,lambda c:dict(collection_complete=False),clock=1000)
        self.assertEqual(result['jobs'][0]['status'],'partial')
        self.assertIsNone(self.store.status()['jobs'][0]['last_success_ms'])

    def test_schema_preview_discovers_existing_version_and_rejects_drift(self):
        from kis_hl.data_cli import cmd_data
        args=SimpleNamespace(data_action='migrate',apply=False,db=str(self.store.path))
        result=cmd_data(args)
        self.assertEqual(result['pending_versions'],[])
        with self.store.connect() as db:db.execute("UPDATE schema_migrations SET checksum='bad'")
        with self.assertRaises(ValueError):cmd_data(args)

    def test_bounded_statement_reconciliation_and_later_invalidation(self):
        from kis_hl.data_reconciliation import reconcile
        import hashlib
        rows=[trade(1,'buy',1),trade(2,'sell',1,110)]
        ingest_rows(self.store,self.aid,'statement',rows)
        document=dict(schema_version=1,source='Synthetic broker statement',complete=True,
            account=dict(venue='kis',environment='live',native_id='synthetic'),dataset='trade',
            start_ms=0,end_ms=100,parser='statement',rows=rows,
            opening_inventory={'kis:X':'0'},closing_inventory={'kis:X':'0'})
        source=Path(self.tmp.name)/'statement.json';source.write_text(json.dumps(document))
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        preview=reconcile(self.store,source,digest,apply=False)
        self.assertFalse(preview['applied']);self.assertNotEqual(journal(self.store,[self.aid])['cycles'][0]['status'],'FINALIZED')
        reconcile(self.store,source,digest,apply=True)
        result=journal(self.store,[self.aid]);self.assertEqual(result['cycles'][0]['status'],'FINALIZED')
        self.assertEqual(result['cycles'][0]['net_pnl'],'8')
        ingest_rows(self.store,self.aid,'statement',[trade(3,'buy',1)])
        changed=journal(self.store,[self.aid]);self.assertNotEqual(changed['cycles'][0]['status'],'FINALIZED')
        self.assertIn(result['report_id'],self.store.status()['stale_runs'])

    def test_reconciliation_rejects_missing_economics_and_bad_digest(self):
        from kis_hl.data_reconciliation import reconcile
        import hashlib
        rows=[trade(1,'buy',1,position_before='0'),trade(2,'sell',1,110)]
        ingest_rows(self.store,self.aid,'statement',rows)
        doc=dict(schema_version=1,source='Synthetic broker statement',complete=True,account=dict(venue='kis',environment='live',native_id='synthetic'),dataset='trade',start_ms=0,end_ms=100,parser='statement',rows=rows[:1],opening_inventory={'kis:X':'0'},closing_inventory={'kis:X':'1'})
        source=Path(self.tmp.name)/'statement.json';source.write_text(json.dumps(doc));digest=hashlib.sha256(source.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'digest'):reconcile(self.store,source,'0'*64,apply=True)
        with self.assertRaisesRegex(ValueError,'match'):reconcile(self.store,source,digest,apply=True)

    def test_hl_gap_anchor_itself_starts_next_cycle(self):
        aid=self.store.account('hyperliquid','testnet','gap')
        rows=[trade(1,'buy',1,instrument='hl:BTC',position_before='0'),
              trade(2,'buy',1,instrument='hl:BTC',position_before='0'),
              trade(3,'sell',1,110,instrument='hl:BTC',position_before='1')]
        ingest_rows(self.store,aid,'statement',rows)
        for ds in ['trade','cash']:self.store.coverage(ds,aid,0,1000,'complete',{})
        result=journal(self.store,[aid])
        self.assertEqual(len(result['cycles']),2)
        self.assertEqual(result['cycles'][-1]['status'],'FINALIZED')
        self.assertIsNone(result['cycles'][0]['net_pnl'])

    def test_overseas_minute_repeated_page_fails_with_partial_evidence(self):
        client=SimpleNamespace(overseas_intraday_chart=lambda **kw:KisHttpResponse(200,dict(rt_cd='0',output1={'next':'1'},output2=[dict(xymd='20260102',xhms='100000',open='100',high='102',low='99',last='101',evol='2')]),{}))
        with self.assertRaisesRegex(ValueError,'progress'):
            backfill(self.store,'kis:SPY','1m',client,start=date(2026,1,2),end=date(2026,1,2),delay_seconds=0)
        self.assertEqual(len(self.store.facts('bar')),1)
        self.assertEqual(self.store.status()['coverage'][0]['status'],'failed')

    def test_failed_reconciliation_rolls_back_inventory_and_evidence(self):
        from kis_hl.data_reconciliation import reconcile
        import hashlib
        rows=[trade(1,'buy',1),trade(2,'sell',1,110)]
        ingest_rows(self.store,self.aid,'statement',rows)
        doc=dict(schema_version=1,source='Synthetic broker statement',complete=True,account=dict(venue='kis',environment='live',native_id='synthetic'),dataset='trade',start_ms=0,end_ms=100,parser='statement',rows=rows,opening_inventory={'kis:X':'0'},closing_inventory={'kis:X':'0'})
        source=Path(self.tmp.name)/'statement.json';source.write_text(json.dumps(doc));digest=hashlib.sha256(source.read_bytes()).hexdigest()
        with patch.object(self.store,'coverage',side_effect=RuntimeError('disk failure')):
            with self.assertRaises(RuntimeError):reconcile(self.store,source,digest,apply=True)
        self.assertNotIn('position_before',self.store.facts('trade')[0]['payload'])
        with self.store.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM source_observations WHERE dataset='reconciliation'").fetchone()[0],0)

    def test_reconciliation_matches_provider_realized_pnl(self):
        from kis_hl.data_reconciliation import reconcile
        import hashlib
        aid=self.store.account('hyperliquid','testnet','gross')
        rows=[trade(1,'buy',1,instrument='hl:BTC',position_before='0',gross_pnl='0'),
              trade(2,'sell',1,110,instrument='hl:BTC',position_before='1',gross_pnl='999')]
        ingest_rows(self.store,aid,'statement',rows)
        source=[rows[0],{**rows[1],'gross_pnl':'10'}]
        doc=dict(schema_version=1,source='Independent statement',complete=True,account=dict(venue='hyperliquid',environment='testnet',native_id='gross'),dataset='trade',start_ms=0,end_ms=100,parser='statement',rows=source,opening_inventory={'hl:BTC':'0'},closing_inventory={'hl:BTC':'0'})
        path=Path(self.tmp.name)/'pnl.json';path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError,'match'):
            reconcile(self.store,path,hashlib.sha256(path.read_bytes()).hexdigest(),apply=True)

    def test_recovery_bounds_invalid_segment_funding_exposure(self):
        aid=self.store.account('hyperliquid','testnet','recovery')
        rows=[trade(1,'buy',1,instrument='hl:BTC',position_before='0'),
              trade(2,'buy',1,instrument='hl:BTC',position_before='0'),
              trade(3,'sell',1,110,instrument='hl:BTC',position_before='1')]
        for row in rows:row['currency']='USDC'
        ingest_rows(self.store,aid,'statement',rows)
        ingest_rows(self.store,aid,'hl_funding',[dict(time=25,hash='f',delta=dict(coin='BTC',usdc='-1'))])
        for ds in ['trade','cash']:self.store.coverage(ds,aid,0,100,'complete',{})
        report=journal(self.store,[aid]);invalid,valid=report['cycles']
        self.assertEqual(valid['status'],'FINALIZED');self.assertEqual(valid['net_pnl'],'7')
        self.assertEqual(valid['funding_cashflow'],'-1');self.assertEqual(invalid['funding_cashflow'],'0')
        self.assertEqual(invalid['status'],'PENDING');self.assertIsNone(invalid['closed_ms'])

    def test_append_during_report_generation_is_stale(self):
        aid=self.store.account('hyperliquid','testnet','race')
        rows=[trade(1,'buy',1,instrument='hl:BTC',position_before='0'),trade(2,'sell',1,110,instrument='hl:BTC',position_before='1')]
        for row in rows:row['currency']='USDC'
        ingest_rows(self.store,aid,'statement',rows)
        pin=self.store.pin
        def interleave(*args,**kwargs):
            ingest_rows(self.store,aid,'hl_funding',[dict(time=15,hash='late',delta=dict(coin='BTC',usdc='-2'))])
            return pin(*args,**kwargs)
        with patch.object(self.store,'pin',side_effect=interleave):old=journal(self.store,[aid])
        self.assertIn(old['report_id'],self.store.status()['stale_runs'])
        fresh=journal(self.store,[aid]);self.assertNotIn(fresh['report_id'],self.store.status()['stale_runs'])

    def test_old_journal_without_watermarks_detects_late_facts(self):
        rows=[trade(1,'buy',1,instrument='hl:BTC',position_before='0'),trade(2,'sell',1,110,instrument='hl:BTC',position_before='1')]
        ingest_rows(self.store,self.aid,'statement',rows);old=journal(self.store,[self.aid])
        with self.store.connect() as db:
            parameters=json.loads(db.execute('SELECT parameters FROM analysis_runs WHERE id=?',(old['report_id'],)).fetchone()[0])
            parameters.pop('input_watermark',None);parameters.pop('coverage_watermark',None)
            db.execute('UPDATE analysis_runs SET parameters=? WHERE id=?',(json.dumps(parameters),old['report_id']))
        ingest_rows(self.store,self.aid,'hl_funding',[dict(time=15,hash='old-report',delta=dict(coin='BTC',usdc='-1'))])
        self.assertIn(old['report_id'],self.store.status()['stale_runs'])

    def test_known_after_historical_asof_but_before_report_read_is_stale(self):
        rows=[trade(1,'buy',1,instrument='hl:BTC',position_before='0'),trade(2,'sell',1,110,instrument='hl:BTC',position_before='1')]
        with patch('kis_hl.data_store.now_ms',return_value=100):
            ingest_rows(self.store,self.aid,'statement',rows)
        with patch('kis_hl.data_store.now_ms',return_value=201):
            ingest_rows(self.store,self.aid,'hl_funding',[dict(time=15,hash='asof-boundary',delta=dict(coin='BTC',usdc='-2'))])
        old=journal(self.store,[self.aid],as_of_ms=200)
        self.assertIn(old['report_id'],self.store.status()['stale_runs'])
        fresh=journal(self.store,[self.aid],as_of_ms=300)
        self.assertNotIn(fresh['report_id'],self.store.status()['stale_runs'])

    def test_old_superseded_versions_do_not_make_fresh_report_stale(self):
        rows=[trade(1,'buy',1,position_before='0'),trade(2,'sell',1,110)]
        ingest_rows(self.store,self.aid,'statement',rows)
        ingest_rows(self.store,self.aid,'statement',[{**rows[1],'total_cost':'2','costs':{'broker':'2'}}],allow_correction=True)
        fresh=journal(self.store,[self.aid])
        self.assertNotIn(fresh['report_id'],self.store.status()['stale_runs'])
