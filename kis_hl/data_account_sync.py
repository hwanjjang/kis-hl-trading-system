"""Read-only account polling into canonical evidence and normalized facts."""
from datetime import datetime
import json
from zoneinfo import ZoneInfo
from kis_hl.data_store import encode, now_ms
from kis_hl.data_ingestion import ingest_rows, domestic_bundle
from kis_hl.journal_history import fetch_time_pages


def sync_account(store,venue,account,*,start_ms,end_ms=None,client=None,scope=None):
    if client is None:
        from kis_hl.operations_cli import scope_client
        scope,client=scope_client(venue,account)
    end_ms=now_ms() if end_ms is None else end_ms
    if type(start_ms) is not int or not 0<=start_ms<=end_ms:raise ValueError('Invalid account range')
    aid=store.account(scope.venue,scope.environment,scope.account)
    observations=[]
    def observe(dataset,body,raw=None):
        candidate=getattr(client,'last_raw_body',None)
        if raw is None and candidate and json.loads(candidate)==body:raw=candidate
        obs=store.observe(dataset,aid,raw or encode(body).encode(),capture_format='http_json' if raw else 'decoded_json')
        observations.append(obs);return obs
    def page(response):observe('kis_account_page',response.body,response.raw_body)
    try:
        if venue=='hyperliquid':
            def fetch(kind,a,b):
                rows=(client.user_fills_by_time if kind=='hl_fills' else client.user_funding)(start_time_ms=a,end_time_ms=b)
                obs=observe(kind,rows)
                # Normalize only unsaturated pages; capped parents remain evidence.
                if len(rows)<(2000 if kind=='hl_fills' else 500):ingest_rows(store,aid,kind,rows,observation=obs)
                return rows
            fills=fetch_time_pages(lambda a,b:fetch('hl_fills',a,b),start_ms,end_ms,limit=2000)
            fetch_time_pages(lambda a,b:fetch('hl_funding',a,b),start_ms,end_ms,limit=500)
            tail=client.user_fills();observe('hl_retained_tail',tail)
            complete=bool(tail) and start_ms>=min(r['time'] for r in tail)
            store.coverage('trade',aid,start_ms,end_ms+1,'complete' if complete else 'partial',{'retention_anchor_ms':min((r['time'] for r in tail),default=None)})
            store.coverage('cash',aid,start_ms,end_ms+1,'partial',{'reason':'Pagination succeeded; historical funding retention is not independently certified'})
            for dex in [None,'xyz']:
                body=client.clearinghouse_state(dex=dex);obs=observe('positions',body)
                for row in body['assetPositions']:
                    p=row['position'];t=now_ms()
                    store.fact('position',aid,encode([dex,p['coin'],t]),{'instrument':'hl:'+p['coin'],'event_start_ms':t,'event_end_ms':t+1,'quantity':p['szi'],'unrealized_pnl':p['unrealizedPnl'],'currency':'USDC'},observation=obs)
            return {'account_id':aid,'fills':len(fills),'observations':len(observations),'collection_complete':True,'coverage_complete':complete}
        zone=ZoneInfo('Asia/Seoul');start=datetime.fromtimestamp(start_ms/1000,zone).strftime('%Y%m%d');end=datetime.fromtimestamp(end_ms/1000,zone).strftime('%Y%m%d')
        profit=client.account_pages('domestic_trade_profit',date_from=start,date_to=end,page_observer=page)
        orders=[]
        for older in [False,True]:
            orders.extend(client.account_pages('domestic_history',date_from=start,date_to=end,older_history=older,page_observer=page)['output1'])
        # Same order may appear in overlapping recent/old retention routes.
        unique={encode([r.get('ord_dt'),r.get('pdno'),r.get('odno'),r.get('ord_gno_brno')]):r for r in orders}
        summaries={}
        for day in profit['output1']:
            data=client.account_pages('domestic_trade_profit',symbol=day['pdno'],date_from=day['trad_dt'],date_to=day['trad_dt'],page_observer=page)
            if len(data['output2'])!=1:raise ValueError('Ambiguous daily cost summary')
            summaries[day['trad_dt']+':'+day['pdno']]=data['output2'][0]
        bundle={'days':profit['output1'],'orders':list(unique.values()),'costs_by_day_symbol':summaries,'source_observation_ids':list(observations)}
        obs=observe('kis_domestic_bundle',bundle)
        domestic=ingest_rows(store,aid,'statement',domestic_bundle(bundle),observation=obs)
        overseas=[]
        for exchange in ['NASD','NYSE','AMEX']:
            data=client.account_pages('overseas_transactions',exchange=exchange,date_from=start,date_to=end,page_observer=page)
            obs=observe('kis_overseas_trans',data)
            overseas.extend(ingest_rows(store,aid,'kis_overseas_trans',data['output1'],observation=obs))
        store.coverage('trade',aid,start_ms,end_ms+1,'partial',{'reason':'KIS DAY statements collected for domestic and US listings; exact chronology, other markets and retention require reconciliation'})
        return {'account_id':aid,'domestic_trades':len(domestic),'overseas_trades':len(set(overseas)),'observations':len(observations),'collection_complete':True,'coverage_complete':False}
    except Exception as exc:
        store.coverage('trade',aid,start_ms,end_ms+1,'failed',{'reason':type(exc).__name__,'observations':len(observations)})
        raise
