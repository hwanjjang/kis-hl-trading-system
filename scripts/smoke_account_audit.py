"""Offline account audit acceptance: real CLI processes, synthetic provider I/O.

Run from any directory: python3 scripts/smoke_account_audit.py
No user environment, credentials, live network or operational DB is accessed.
"""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
ADDRESS='0x'+'1'*40
START=1789862400000  # 2026-09-20 UTC
END=START+2*86400000


def fixture_process():
    """Replace only provider I/O; use real clients, collectors, CLI and SQLite."""
    from kis_hl.kis.client import KisHttpResponse
    from kis_hl.cli import main
    fills=[dict(coin='BTC',tid=i,time=START+i*1000,side=side,sz='1',px=price,
                fee='0.1',feeToken='USDC',oid=i,startPosition=before,closedPnl=pnl)
           for i,side,price,before,pnl in [(1,'B','10','0','0'),(2,'A','12','1','2')]]
    funding=[{'time':START+1500,'hash':'synthetic','delta':{'coin':'BTC','usdc':'-0.2'}}]
    def hl(self,payload):
        kind=payload['type']
        if 'user' in payload:assert payload['user']==ADDRESS
        if kind in {'userFillsByTime','userFunding'}:
            source=fills if kind=='userFillsByTime' else funding
            body=[r for r in source if payload['startTime']<=r['time']<=payload['endTime']]
        elif kind=='userFills':body=fills
        elif kind=='perpDexs':body=[None,{'name':'xyz'}]
        elif kind=='clearinghouseState':body={'assetPositions':[]}
        elif kind=='spotClearinghouseState':body={'balances':[]}
        else:raise AssertionError('Unexpected synthetic HL request '+kind)
        self.last_raw_body=json.dumps(body).encode();return body
    days=[dict(trad_dt=day,pdno='069500',buy_qty=buy,buy_amt=ba,sll_qty=sell,sll_amt=sa,
               hldg_qty=held,pchs_unpr='10',loan_int='0')
          for day,buy,ba,sell,sa,held in [('20260920','2','20','0','0','2'),('20260921','0','0','2','24','0')]]
    orders=[dict(ord_dt=d['trad_dt'],pdno='069500',odno=str(i),ord_gno_brno='synthetic',
                 sll_buy_dvsn_cd='02' if i==1 else '01',tot_ccld_qty='2',tot_ccld_amt='20' if i==1 else '24')
            for i,d in enumerate(days,1)]
    def kis(self,method,path,*,query,**kwargs):
        assert method=='GET'
        body={'rt_cd':'0','output1':[],'output2':[]}
        if path.endswith('inquire-period-trade-profit'):
            body['output1']=[d for d in days if query['INQR_STRT_DT']<=d['trad_dt']<=query['INQR_END_DT']]
            day=query['INQR_STRT_DT']
            body['output2']=[{'buy_fee_smtl':'1' if day=='20260920' else '0','sll_fee_smtl':'1' if day=='20260921' else '0','buy_tax_smtl':'0','sll_tltx_smtl':'0'}]
        elif path.endswith('inquire-daily-ccld'):body['output1']=orders
        elif path.endswith('inquire-period-trans'):pass
        elif path.endswith('inquire-balance'):pass
        else:raise AssertionError('Unexpected synthetic KIS request '+path)
        return KisHttpResponse(200,body,{},json.dumps(body).encode())
    with ExitStack() as stack:
        stack.enter_context(patch('kis_hl.hyperliquid.client.HyperliquidInfoClient.post_info',hl))
        stack.enter_context(patch('kis_hl.kis.client.KisClient._request_with_auth',kis))
        stack.enter_context(patch('socket.socket.connect',side_effect=AssertionError('Network forbidden in offline smoke')))
        raise SystemExit(main(sys.argv[2:]))


def main():
    calls=0
    with TemporaryDirectory(prefix='account-audit-smoke-') as tmp:
        root=Path(tmp);db=root/'state.sqlite'
        env={'PATH':os.environ.get('PATH',''),'PYTHONPATH':str(ROOT),'PYTHONDONTWRITEBYTECODE':'1',
             'SANDBOX':'false','KIS_API_KEY':'synthetic','KIS_API_SECRET':'synthetic',
             'KIS_STOCK_ACCOUNT':'1234567801','KIS_TOKEN_DIR':str(root/'tokens')}
        def cli(*args,error=None):
            nonlocal calls
            calls+=1
            result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--fixture-process','--db',str(db),*args],
                                  cwd=root,env=env,capture_output=True,text=True,timeout=30)
            if error:
                assert result.returncode!=0 and error in result.stderr,(args,result.stdout,result.stderr)
                return None
            assert result.returncode==0,(args,result.stdout,result.stderr)
            return json.loads(result.stdout)
        def counts():
            with sqlite3.connect(db) as conn:
                return {t:conn.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in
                        ['fact_revisions','source_observations','analysis_runs','dataset_coverage','collection_runs']}
        hl=root/'hl.json';kis=root/'kis.json'
        cli('data','audit-collect','--venue','hyperliquid','--account',ADDRESS,'--start-ms',str(START),'--end-ms',str(END),'--output',str(hl))
        cli('data','audit-collect','--venue','kis','--account','1234567801','--start-ms',str(START),'--end-ms',str(END),'--output',str(kis))
        assert not db.exists(),'Collection created operational DB'
        cli('data','migrate','--apply')
        before=counts();report=root/'report.json'
        preview=cli('data','audit-compare','--bundle',str(hl),str(kis),'--output',str(report))
        assert preview['changes']==5 and preview['blockers']==0,preview
        assert counts()==before,'Comparison changed operational state'
        cli('data','audit-apply','--report',str(report),'--sha256','0'*64,error='digest')
        assert counts()==before
        applied=cli('data','audit-apply','--report',str(report),'--sha256',preview['sha256'],'--journals')
        assert len(applied['journal_ids'])==3
        after=counts();again=cli('data','audit-apply','--report',str(report),'--sha256',preview['sha256'],'--journals')
        assert again['already_applied'] and again['journal_ids']==applied['journal_ids'] and counts()==after
        export=root/'combined.json'
        cli('data','export','--report-id',str(applied['journal_ids'][-1]),'--output',str(export))
        old_bytes=export.read_bytes();journal=json.loads(old_bytes)
        totals={r['currency']:r for r in journal['summary_by_account_currency']}
        assert totals['USDC']['net_booked_pnl']=='1.6',totals
        assert totals['KRW']['net_booked_pnl']=='2',totals
        assert all(r['coverage_status']!='verified' for r in totals.values())
        # Review a changed source commission, then exercise explicit correction and stale rejection.
        source=json.loads(hl.read_text());source['sources'][0]['data'][0]['fee']='0.2'
        # A standalone operator source revision must not pretend the old raw response backs new rows.
        source['evidence']=[];corrected=root/'corrected.json';corrected.write_text(json.dumps(source))
        change=root/'change.json';c=cli('data','audit-compare','--bundle',str(corrected),str(kis),'--output',str(change))
        stale=root/'stale.json';s=cli('data','audit-compare','--bundle',str(hl),str(kis),'--output',str(stale))
        cli('data','audit-apply','--report',str(change),'--sha256',c['sha256'],error='correction')
        cli('data','audit-apply','--report',str(change),'--sha256',c['sha256'],'--allow-corrections','--journals')
        assert export.read_bytes()==old_bytes,'Old journal export changed'
        cli('data','audit-apply','--report',str(stale),'--sha256',s['sha256'],error='stale')
        with sqlite3.connect(db) as conn:
            assert conn.execute('SELECT count(*) FROM fact_revisions').fetchone()[0]==6
            assert conn.execute('SELECT count(*) FROM analysis_runs').fetchone()[0]==6
        missing=json.loads(kis.read_text());missing['sources'][0]['data']={'days':[],'orders':[],'costs_by_day_symbol':{}}
        missing['evidence']=[];bad=root/'missing.json';bad.write_text(json.dumps(missing))
        blocked=root/'blocked.json';b=cli('data','audit-compare','--bundle',str(bad),'--output',str(blocked))
        assert b['blockers']>0 and b['missing']==2
        before=counts();cli('data','audit-apply','--report',str(blocked),'--sha256',b['sha256'],error='unresolved');assert counts()==before
        assert hl.stat().st_mode&0o777==0o600 and report.stat().st_mode&0o777==0o600
        print(json.dumps({'status':'PASS','cli_subprocesses':calls,'scenarios':['isolated native capture','read-only compare','digest guard','atomic apply and three journals','idempotent replay','net fee/funding totals','explicit correction','stale report rejection','immutable old export','missing-source rejection'],'network':'forbidden','operational_data':'not accessed'}))


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--fixture-process':fixture_process()
    else:main()
