from pathlib import Path
from tempfile import TemporaryDirectory
import json, subprocess, sys
from kis_hl.data_store import DataStore
from kis_hl.data_ingestion import ingest_rows
from kis_hl.journal_exports import journal
from kis_hl.execution_lock import account_lock


def row(i,side,qty,price,ms,**extra):
    return dict(source_id=str(i),instrument='kis:X',currency='USD',event_start_ms=ms,event_end_ms=ms+1,time_precision='MILLISECOND',grain='EXECUTION',side=side,quantity=str(qty),price=str(price),notional=str(qty*price),total_cost='1',costs={'broker':'1'},**extra)

results={}
with TemporaryDirectory() as d:
    root=Path(d)
    store=DataStore(root/'oversell.sqlite')
    aid=store.account('kis','sim','synthetic-oversell')
    ingest_rows(store,aid,'statement',[row(1,'buy',3,100,100),row(2,'sell',10,120,110),row(3,'buy',7,110,120)])
    store.coverage('trade',aid,0,1000,'complete',{})
    report=journal(store,[aid])
    results['F-1']={'cycles':[{k:c[k] for k in ['side','status','gross_pnl','net_pnl','net_return_pct']} for c in report['cycles']],'quality_findings':report['quality_findings'],'coverage':report['summary_by_account_currency'][0]['coverage_status']}
    assert any(c['side']=='short' and c['status']=='FINALIZED' for c in report['cycles'])

    store=DataStore(root/'anchoring.sqlite')
    aid=store.account('kis','sim','synthetic-inventory')
    rows=[row(1,'buy',3,100,86400000,day_end_quantity='10'),row(2,'sell',3,110,172800000,day_end_quantity='7')]
    for r in rows:
        r.update(time_precision='DAY',grain='ORDER_CUMULATIVE_RECONCILED',event_end_ms=r['event_start_ms']+86400000)
    ingest_rows(store,aid,'statement',rows)
    store.coverage('trade',aid,0,259200000,'complete',{})
    report=journal(store,[aid])
    results['F-2']={'end_inventory_known':'7','cycle_status':report['cycles'][0]['status'],'cycle_return_pct':report['cycles'][0]['net_return_pct'],'quality_findings':report['quality_findings'],'coverage':report['summary_by_account_currency'][0]['coverage_status']}
    assert report['cycles'][0]['status']=='FINALIZED'

    with account_lock('data-jobs',str(store.path)):
        script="from kis_hl.data_store import DataStore; from kis_hl.data_jobs import run_due; import sys; run_due(DataStore(sys.argv[1]), lambda _: {})"
        out=subprocess.run([sys.executable,'-c',script,str(store.path)],capture_output=True,text=True,timeout=10)
    results['F-3']={'exit_code':out.returncode,'lock_contention_rejected':'Account has another execution owner' in out.stderr,'correct_location':'kis_hl/data_jobs.py:20'}
    assert out.returncode!=0 and results['F-3']['lock_contention_rejected']

    fresh=root/'typo.sqlite'
    assert not fresh.exists()
    out=subprocess.run([sys.executable,'-m','kis_hl.cli','--db',str(fresh),'data','status'],capture_output=True,text=True,timeout=10)
    results['F-4']={'exit_code':out.returncode,'created_database':fresh.exists(),'schema_version':json.loads(out.stdout)['schema_version']}
    assert out.returncode==0 and fresh.exists()
print(json.dumps(results,indent=2))
