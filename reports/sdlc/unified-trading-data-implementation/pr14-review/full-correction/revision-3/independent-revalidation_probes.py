import hashlib,json
from pathlib import Path
from tempfile import TemporaryDirectory
from kis_hl.data_store import DataStore
from kis_hl.data_ingestion import ingest_rows
from kis_hl.data_reconciliation import reconcile
from kis_hl.journal_exports import journal

def fill(t,side,pos,price,pnl,tid):return dict(time=t,side=side,startPosition=str(pos),px=str(price),closedPnl=str(pnl),tid=tid,coin='BTC',fee='0',feeToken='USDC',sz='1',oid=tid)
out={}
with TemporaryDirectory() as tmp:
 p=Path(tmp);s=DataStore(p/'state.sqlite');aid=s.account('hyperliquid','testnet','synthetic')
 actual=[fill(10,'B',0,100,0,1),fill(20,'A',1,110,999,2)]
 source=[actual[0],{**actual[1],'closedPnl':'10'}]
 ingest_rows(s,aid,'hl_fills',actual)
 doc=dict(schema_version=1,source='Independent synthetic statement',complete=True,account=dict(venue='hyperliquid',environment='testnet',native_id='synthetic'),dataset='trade',start_ms=0,end_ms=100,parser='hl_fills',rows=source,opening_inventory={'hl:BTC':'0'},closing_inventory={'hl:BTC':'0'})
 path=p/'statement.json';path.write_text(json.dumps(doc));digest=hashlib.sha256(path.read_bytes()).hexdigest()
 try:
  reconcile(s,path,digest,apply=True)
 except ValueError as exc:r={'applied':False,'rejection':str(exc)}
 else:raise AssertionError('Contradictory realized PnL accepted')
 s.coverage('cash',aid,0,100,'complete',{})
 report=journal(s,[aid]);out['gross_pnl_reconciliation']={'applied':r['applied'],'rejection':r.get('rejection'),'statement_gross':'10','canonical_net':report['cycles'][0]['net_pnl'],'status':report['cycles'][0]['status']}
 s=DataStore(p/'recover.sqlite');aid=s.account('hyperliquid','testnet','synthetic')
 rows=[fill(10,'B',0,100,0,1),fill(20,'B',0,100,0,2),fill(30,'A',1,110,10,3)]
 ingest_rows(s,aid,'hl_fills',rows);ingest_rows(s,aid,'hl_funding',[dict(time=25,hash='f',delta=dict(coin='BTC',usdc='-1'))])
 for ds in ['trade','cash']:s.coverage(ds,aid,0,100,'complete',{})
 report=journal(s,[aid]);out['funding_after_recovery']={'cycles':[{'opened_ms':c['opened_ms'],'closed_ms':c['closed_ms'],'status':c['status'],'reasons':c['reasons'],'shared_funding_ids':c['shared_funding_ids']} for c in report['cycles']],'issues':report['quality_findings']}
print(json.dumps(out,indent=2))
# Deterministically interleave a collector append after journal reads, before pin.
with TemporaryDirectory() as tmp:
 s=DataStore(Path(tmp)/'race.sqlite');a=s.account('hyperliquid','testnet','synthetic')
 ingest_rows(s,a,'hl_fills',[fill(10,'B',0,100,0,1),fill(20,'A',1,110,10,2)])
 for ds in ['trade','cash']:s.coverage(ds,a,0,100,'complete',{})
 original=s.pin
 def interleaved(*args,**kwargs):
  ingest_rows(s,a,'hl_funding',[dict(time=15,hash='late',delta=dict(coin='BTC',usdc='-2'))])
  return original(*args,**kwargs)
 s.pin=interleaved
 old=journal(s,[a]);s.pin=original;fresh=journal(s,[a])
 print(json.dumps({'append_before_pin':{'before_net':old['cycles'][0]['net_pnl'],'after_net':fresh['cycles'][0]['net_pnl'],'stale_runs':s.status()['stale_runs']}},indent=2))
