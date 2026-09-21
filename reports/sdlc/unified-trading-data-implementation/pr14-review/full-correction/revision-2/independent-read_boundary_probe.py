from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
from kis_hl.data_store import DataStore
from kis_hl.data_ingestion import ingest_rows
from kis_hl.journal_exports import journal

def fill(t,side,pos,price,pnl,tid):return dict(time=t,side=side,startPosition=str(pos),px=str(price),closedPnl=str(pnl),tid=tid,coin='BTC',fee='0',feeToken='USDC',sz='1',oid=tid)
with TemporaryDirectory() as tmp:
 s=DataStore(Path(tmp)/'state.sqlite');a=s.account('hyperliquid','testnet','synthetic')
 with patch('kis_hl.data_store.now_ms',return_value=100):
  ingest_rows(s,a,'hl_fills',[fill(10,'B',0,100,0,1),fill(20,'A',1,110,10,2)])
  for ds in ['trade','cash']:s.coverage(ds,a,0,100,'complete',{})
 connect=s.connect;inserted=False
 @contextmanager
 def interleave():
  global inserted
  if not inserted:
   inserted=True
   # Collector commits after the journal's as-of is captured but before its max-ID query.
   with patch('kis_hl.data_store.now_ms',return_value=201):
    ingest_rows(s,a,'hl_funding',[dict(time=15,hash='between-asof-and-watermark',delta=dict(coin='BTC',usdc='-2'))])
  with connect() as db:yield db
 with patch.object(s,'connect',side_effect=interleave),patch('kis_hl.journal_exports.now_ms',return_value=200):
  old=journal(s,[a])
 fresh=journal(s,[a],as_of_ms=300)
 print(json.dumps({'old_report_id':old['report_id'],'before_net':old['cycles'][0]['net_pnl'],'after_net':fresh['cycles'][0]['net_pnl'],'stale_runs':s.status()['stale_runs']},indent=2))
