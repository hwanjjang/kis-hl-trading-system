from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
from kis_hl.data_store import DataStore
from kis_hl.data_ingestion import ingest_rows
from kis_hl.journal_exports import journal

def row(sid,t,side,price,**extra):return dict(source_id=sid,instrument='kis:X',currency='USD',event_start_ms=t,event_end_ms=t+1,time_precision='MILLISECOND',grain='EXECUTION',side=side,quantity='1',price=str(price),notional=str(price),total_cost='0',costs={},**extra)
results={}
with TemporaryDirectory() as tmp:
 s=DataStore(Path(tmp)/'state.sqlite');a=s.account('kis','live','a');b=s.account('kis','live','b')
 rows=[row('buy',10,'buy',100,position_before='0'),row('sell',20,'sell',110)]
 with patch('kis_hl.data_store.now_ms',return_value=100):ingest_rows(s,a,'statement',rows)
 old=journal(s,[a],as_of_ms=150)
 with patch('kis_hl.data_store.now_ms',return_value=200):
  ingest_rows(s,b,'statement',[row('unrelated',30,'buy',100)])
  ingest_rows(s,a,'statement',[row('future',1000,'buy',100)])
 assert old['report_id'] not in s.status()['stale_runs'];results['unrelated_account_and_future_event_excluded']=True
 with patch('kis_hl.data_store.now_ms',return_value=200):
  s.coverage('trade',a,0,100,'complete',{'source':'synthetic'})
 assert old['report_id'] in s.status()['stale_runs'];results['late_coverage_detected']=True
 fresh=journal(s,[a],as_of_ms=300)
 assert fresh['report_id'] not in s.status()['stale_runs'];results['captured_coverage_not_false_stale']=True
 with patch('kis_hl.data_store.now_ms',return_value=400):
  ingest_rows(s,a,'statement',[{**rows[1],'total_cost':'1','costs':{'broker':'1'}}],allow_correction=True)
 assert fresh['report_id'] in s.status()['stale_runs']
 latest=journal(s,[a],as_of_ms=500)
 assert latest['report_id'] not in s.status()['stale_runs'];results['old_revision_stale_new_revision_fresh']=True
 # Simulate a legacy serialized report carrying obsolete watermark fields.
 with s.connect() as db:
  p=json.loads(db.execute('SELECT parameters FROM analysis_runs WHERE id=?',(old['report_id'],)).fetchone()[0]);p.update(input_watermark=10**12,coverage_watermark=10**12)
  db.execute('UPDATE analysis_runs SET parameters=? WHERE id=?',(json.dumps(p),old['report_id']))
 assert old['report_id'] in s.status()['stale_runs'];results['legacy_watermark_values_ignored']=True
print(json.dumps(results,indent=2))
