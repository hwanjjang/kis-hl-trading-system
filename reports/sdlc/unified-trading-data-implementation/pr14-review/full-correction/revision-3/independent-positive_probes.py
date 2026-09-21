from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
from datetime import date
import json,hashlib
from kis_hl.data_store import DataStore
from kis_hl.data_cli import cmd_data
from kis_hl.data_jobs import run_due
from kis_hl.market_ingestion import snapshot
from kis_hl.analysis_store import run_analysis
from kis_hl.market_series import store_bar
out={}
with TemporaryDirectory() as tmp:
 p=Path(tmp);missing=p/'missing'/'state.sqlite'
 for action in ['status','migrate']:
  r=cmd_data(SimpleNamespace(data_action=action,db=str(missing),apply=False));assert r['exists'] is False
 assert not missing.parent.exists();out['missing_previews']='PASS'
 s=DataStore(p/'state.sqlite');before=hashlib.sha256(s.path.read_bytes()).hexdigest();mode=s.path.stat().st_mode
 r=cmd_data(SimpleNamespace(data_action='status',db=str(s.path)));after=hashlib.sha256(s.path.read_bytes()).hexdigest()
 assert before==after and s.path.stat().st_mode==mode;out['existing_status_no_db_mutation']='PASS'
 run_due(s,lambda c:{},clock=1000);run_due(s,lambda c:{},clock=2000)
 assert s.status()['worker_last_seen_ms']==2000;out['idle_worker_heartbeat']='PASS'
 for endpoint in ['https://api.hyperliquid-testnet.xyz','https://example.invalid']:
  client=SimpleNamespace(config=SimpleNamespace(base_url=endpoint),l2_book=lambda *a:(_ for _ in ()).throw(AssertionError('network')))
  try:snapshot(s,'hl:BTC',client)
  except ValueError:pass
  else:raise AssertionError('unsupported network accepted')
 assert not s.facts('book');out['endpoint_rejection_before_request']='PASS'
 obs=s.observe('bars','hyperliquid',b'{}')
 bar=dict(event_start_ms=10,event_end_ms=20,open='10',high='20',low='5',close='10',volume='1',complete=True)
 with patch('kis_hl.data_store.now_ms',return_value=100):
  d=store_bar(s,'hl:BTC','hyperliquid','1d',bar,observation=obs)
  w=store_bar(s,'hl:BTC','hyperliquid','1w',{**bar,'input_ids':[d]},observation=obs,variant='derived')
 with patch('kis_hl.data_store.now_ms',return_value=200):
  store_bar(s,'hl:BTC','hyperliquid','1d',{**bar,'close':'20'},observation=obs)
 spec=dict(instrument='hl:BTC',provider='hyperliquid',timeframe='1w',adjustment='raw',price_basis='trade',variant='derived',calendar='UTC',window=1)
 assert run_analysis(s,spec,as_of_ms=150)['last_close']=='10'
 try:run_analysis(s,spec,as_of_ms=250)
 except ValueError:pass
 else:raise AssertionError('stale derived inputs accepted')
 out['historical_asof_preserved_current_dependency_rejected']='PASS'
print(json.dumps(out,indent=2))
