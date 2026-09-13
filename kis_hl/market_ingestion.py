"""Read-only market collectors with explicit provider coverage and bounded pages."""
from datetime import date, datetime, timedelta, timezone
import json
import time
from zoneinfo import ZoneInfo
from kis_hl.data_store import encode, number, now_ms
from kis_hl.instruments import instrument
from kis_hl.market_series import history_start, bounds, store_bar


def capture(store, provider, dataset, response, client=None):
    body=getattr(response,'body',response)
    raw=getattr(response,'raw_body',None)
    candidate=getattr(client,'last_raw_body',None)
    if raw is None and candidate and json.loads(candidate)==body:raw=candidate
    return store.observe(dataset,provider,raw or encode(body).encode(),capture_format='http_json' if raw else 'decoded_json')


def kis_ok(response):
    if response.status>=400 or response.body.get('rt_cd')!='0':raise RuntimeError('KIS market request failed')
    return response.body


def backfill(store, key, timeframe, client, *, years=10, end=None, start=None, start_ms=None, max_pages=256, delay_seconds=0.12):
    asset=instrument(key)
    if timeframe not in {'1w','1d','1m'}:raise ValueError('Supported stored bars: 1w, 1d, 1m')
    zone='UTC' if asset.venue=='hyperliquid' else ('Asia/Seoul' if asset.market.startswith('domestic') else 'America/New_York')
    end=end or datetime.now(ZoneInfo(zone)).date()
    start=start or (end-timedelta(days=30) if timeframe=='1m' else history_start(end,years if timeframe=='1w' else 2))
    a=bounds(start,'1d',zone)[0];b=bounds(end,'1d',zone)[1]
    if start_ms is not None:
        if timeframe!='1m' or type(start_ms) is not int or start_ms<0:raise ValueError('Incremental timestamp bound requires minute bars')
        a=start_ms
    if a>=b:raise ValueError('Reversed history range')
    observed=now_ms();ids=[];seen=set();labels=[];pages=0
    try:
        if asset.venue=='hyperliquid':
            rows=client.candle_snapshot(asset.symbol if asset.symbol.startswith('xyz:') else asset.symbol+'-PERP',interval=timeframe,start_time_ms=a,end_time_ms=b-1)
            obs=capture(store,'hyperliquid','bars',rows,client);pages=1
            if not isinstance(rows,list):raise ValueError('Malformed candle response')
            for i,r in enumerate(rows):
                if r['i']!=timeframe or r['s']!=asset.symbol:raise ValueError('Candle identity mismatch')
                t=int(r['t']);end_ms=int(r['T'])+1
                duration={'1m':60000,'1d':86400000,'1w':7*86400000}[timeframe]
                if end_ms-t!=duration:raise ValueError('Invalid native candle duration')
                if not a<=t<b:continue
                ids.append(store_bar(store,key,'hyperliquid',timeframe,dict(event_start_ms=t,event_end_ms=end_ms,
                    open=r['o'],high=r['h'],low=r['l'],close=r['c'],volume=r['v'],complete=end_ms<=observed),observation=obs))
                labels.append(t)
            limitation='Hyperliquid retains only the latest 5000 candles per interval; listing history may be shorter.'
        elif timeframe=='1m':
            if asset.market!='domestic':raise ValueError('KIS minute backfill is not available for this route')
            # This endpoint provides current-day bars only. Historical request stays partial.
            hour=datetime.now(ZoneInfo(zone)).strftime('%H%M%S')
            while pages<max_pages:
                response=client.domestic_intraday_chart(symbol=asset.symbol,hour=hour);body=kis_ok(response)
                obs=capture(store,'kis','bars',response);rows=body.get('output2',[]);pages+=1
                if not rows:break
                new=[]
                for r in rows:
                    dt=datetime.strptime(r['stck_bsop_date']+r['stck_cntg_hour'],'%Y%m%d%H%M%S').replace(tzinfo=ZoneInfo(zone))
                    t=int(dt.timestamp()*1000)
                    if t in seen or not a<=t<b:continue
                    seen.add(t);new.append(dt)
                    ids.append(store_bar(store,key,'kis','1m',dict(event_start_ms=t,event_end_ms=t+60000,open=r['stck_oprc'],high=r['stck_hgpr'],low=r['stck_lwpr'],close=r['stck_prpr'],volume=r.get('cntg_vol'),complete=t+60000<=observed),observation=obs,calendar=zone))
                    labels.append(t)
                if not new:break
                hour=(min(new)-timedelta(seconds=1)).strftime('%H%M%S');time.sleep(delay_seconds)
            limitation='KIS domestic minute route covers current trading day only; older requested sessions unavailable.'
        else:
            cursor=end
            while pages<max_pages and cursor>=start:
                period='W' if timeframe=='1w' else 'D'
                if asset.market in {'domestic','domestic_index'}:
                    response=client.domestic_chart(symbol=asset.symbol,date_from=start.strftime('%Y%m%d'),date_to=cursor.strftime('%Y%m%d'),index=asset.market=='domestic_index',period=period)
                elif asset.market=='overseas':
                    response=client.overseas_stock_chart(symbol=asset.symbol,exchange=asset.quote_exchange,end_date=cursor.strftime('%Y%m%d'),period=period)
                else:
                    response=client.inquire_overseas_daily_chartprice(symbol=asset.symbol,date_from=start.strftime('%Y%m%d'),date_to=cursor.strftime('%Y%m%d'),period=period)
                body=kis_ok(response);obs=capture(store,'kis','bars',response);rows=body.get('output2',[]);pages+=1
                if not rows:break
                dates=[]
                for r in rows:
                    label=r.get('stck_bsop_date') or r.get('xymd')
                    if not label:continue
                    day=datetime.strptime(label,'%Y%m%d').date();dates.append(day)
                    if not start<=day<=end:continue
                    t,stop=bounds(day,timeframe,zone)
                    if t in seen:continue
                    seen.add(t)
                    if 'xymd' in r:keys=['open','high','low','clos','tvol']
                    elif asset.market=='domestic_index':keys=['bstp_nmix_oprc','bstp_nmix_hgpr','bstp_nmix_lwpr','bstp_nmix_prpr','acml_vol']
                    elif asset.market=='overseas_index':keys=['ovrs_nmix_oprc','ovrs_nmix_hgpr','ovrs_nmix_lwpr','ovrs_nmix_prpr','acml_vol']
                    else:keys=['stck_oprc','stck_hgpr','stck_lwpr','stck_clpr','acml_vol']
                    bar={k:r.get(v) for k,v in zip(['open','high','low','close','volume'],keys)}
                    bar.update(event_start_ms=t,event_end_ms=stop,complete=stop<=observed,source_date=day.isoformat())
                    ids.append(store_bar(store,key,'kis',timeframe,bar,observation=obs,adjustment='provider_adjusted' if 'index' not in asset.market else 'index',calendar=zone));labels.append(t)
                if not dates or min(dates)>cursor:raise ValueError('KIS candle pagination did not progress')
                next_cursor=min(dates)-timedelta(days=1)
                if next_cursor>=cursor:raise ValueError('KIS candle cursor repeated')
                cursor=next_cursor;time.sleep(delay_seconds)
            limitation='Provider-native bars; listing/session completeness is not independently certified.'
        missing=[]
        if timeframe=='1w' and asset.venue=='hyperliquid' and labels:
            duration=7*86400000
            # Native periods need not match ISO weeks. Preserve the source anchor.
            anchor=labels[0]%duration
            if any(t%duration!=anchor for t in labels):raise ValueError('Inconsistent native weekly anchor')
            x=a+(anchor-a)%duration
            while x+duration<=min(b,observed):
                if x not in labels:missing.append({'start_ms':x,'end_ms':x+duration})
                x+=duration
        elif timeframe=='1w' and asset.venue!='hyperliquid':
            week=start-timedelta(days=start.weekday())
            while week<=end:
                x,y=bounds(week,'1w',zone)
                if x>=a and y<=min(b,observed) and x not in labels:missing.append({'start_ms':x,'end_ms':y})
                week+=timedelta(days=7)
        details={'instrument':key,'timeframe':timeframe,'rows':len(set(ids)),'pages':pages,'available_start_ms':min(labels) if labels else None,'available_end_ms':max(labels) if labels else None,'limitation':limitation,'page_limit_reached':pages>=max_pages,
                 'missing_completed_weeks':missing,'missing_week_reason':'Listing/provider/session boundaries need corroboration' if missing else None,'listing_start_ms':None,
                 'native_week_anchor_ms':labels[0]%(7*86400000) if timeframe=='1w' and asset.venue=='hyperliquid' and labels else None,
                 'native_week_anchor_status':'observed' if timeframe=='1w' and asset.venue=='hyperliquid' and labels else 'unknown' if timeframe=='1w' and asset.venue=='hyperliquid' else 'calendar'}
        store.coverage('bar:'+timeframe,key,a,b,'partial',details)
        return details
    except Exception as exc:
        store.coverage('bar:'+timeframe,key,a,b,'failed',{'reason':type(exc).__name__,'persisted_bars':len(set(ids))})
        raise


def snapshot(store,key,client,*,kind='book'):
    asset=instrument(key);t=now_ms();provider=asset.venue
    if provider=='hyperliquid':
        symbol=asset.symbol if asset.symbol.startswith('xyz:') else asset.symbol+'-PERP'
        if kind=='funding':
            rows=client.funding_history(symbol,start_time_ms=t-2*86400000,end_time_ms=t)
            obs=capture(store,provider,kind,rows,client);ids=[]
            for r in rows:
                ts=int(r['time']);p=dict(instrument=key,event_start_ms=ts,event_end_ms=ts+1,rate=number(r['fundingRate']),classification='realized')
                ids.append(store.fact('market_funding',provider,encode([key,ts,'realized']),p,observation=obs,allow_correction=True))
            return {'stored':len(ids)}
        response=client.l2_book(symbol);obs=capture(store,provider,kind,response,client)
        levels=response['levels'];ts=int(response['time'])
        if not levels[0] or not levels[1]:raise ValueError('Empty book sides')
        p=dict(instrument=key,event_start_ms=ts,event_end_ms=ts+1,received_ms=t,bid=number(levels[0][0]['px']),ask=number(levels[1][0]['px']),bid_size=number(levels[0][0]['sz']),ask_size=number(levels[1][0]['sz']),price_basis='top_of_book')
    else:
        if kind=='funding':raise ValueError('Equities have no perpetual funding rate')
        if kind=='quote':
            if asset.market=='domestic_index':response=client.inquire_domestic_index_price(index_code=asset.symbol)
            elif asset.market=='domestic':response=client.inquire_domestic_price(symbol=asset.symbol)
            elif asset.market=='overseas':response=client.inquire_overseas_price(exchange_code=asset.quote_exchange,symbol=asset.symbol)
            else:raise ValueError('Use chart collection for overseas index observations')
            body=kis_ok(response);obs=capture(store,provider,kind,response);r=body['output']
            price=r.get('stck_prpr') or r.get('bstp_nmix_prpr') or r.get('last')
            p=dict(instrument=key,event_start_ms=t,event_end_ms=t+1,received_ms=t,price=number(price),time_precision='RECEIVE_TIME',price_basis='last')
        else:
            response=client.order_book(market=asset.market,symbol=asset.symbol,exchange=asset.quote_exchange)
            body=kis_ok(response);obs=capture(store,provider,kind,response);r=body.get('output1',body.get('output',{}))
            p=dict(instrument=key,event_start_ms=t,event_end_ms=t+1,received_ms=t,bid=number(r.get('bidp1',r.get('pbid1'))),ask=number(r.get('askp1',r.get('pask1'))),time_precision='RECEIVE_TIME',price_basis='top_of_book')
    store.fact(kind,provider,encode([key,t]),p,observation=obs)
    return {'stored':1,'instrument':key,'kind':kind}
