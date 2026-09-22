"""Explicit bar variants and calendar-aware weekly derivation."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal as D
from zoneinfo import ZoneInfo
from kis_hl.data_store import encode, number


def history_start(end: date, years=10):
    if type(years) is not int or not 1<=years<=100:raise ValueError('History years must be 1..100')
    try:return end.replace(year=end.year-years)
    except ValueError:return end.replace(year=end.year-years,day=28)


def bounds(day, timeframe, zone):
    dt=datetime.combine(day,datetime.min.time(),tzinfo=ZoneInfo(zone))
    if timeframe=='1w':dt-=timedelta(days=dt.weekday())
    if timeframe not in {'1w','1d'}:raise ValueError('Calendar bounds require day/week bars')
    end=dt+timedelta(days=7 if timeframe=='1w' else 1)
    return int(dt.timestamp()*1000),int(end.timestamp()*1000)


def derive_weekly(days, *, timezone, expected_sessions, now_ms):
    """Caller supplies an authoritative session list; weekdays are not a calendar."""
    expected=set(expected_sessions);groups=defaultdict(list)
    seen=set()
    for row in days:
        if row['date'] in seen:raise ValueError('Duplicate daily input')
        seen.add(row['date']);groups[bounds(date.fromisoformat(row['date']),'1w',timezone)].append(row)
    for session in expected:
        groups[bounds(date.fromisoformat(session),'1w',timezone)]
    result=[]
    for (start,end),rows in sorted(groups.items()):
        required={s for s in expected if bounds(date.fromisoformat(s),'1w',timezone)==(start,end)}
        dates={r['date'] for r in rows}
        missing=sorted(required-dates)
        if not rows:continue
        variants={(r.get('provider'),r.get('instrument'),r.get('adjustment'),r.get('price_basis')) for r in rows}
        if len(variants)>1:raise ValueError('Cannot aggregate heterogeneous daily variants')
        rows.sort(key=lambda r:r['date'])
        complete=bool(required) and dates==required and not missing and end<=now_ms and all(r.get('complete',True) for r in rows)
        volume=None if any(r.get('volume') is None for r in rows) else number(sum((D(number(r['volume'])) for r in rows),D(0)))
        result.append(dict(event_start_ms=start,event_end_ms=end,open=number(rows[0]['open']),
            high=number(max(D(number(r['high'])) for r in rows)),low=number(min(D(number(r['low'])) for r in rows)),
            close=number(rows[-1]['close']),volume=volume,complete=complete,missing_sessions=missing,
            input_ids=[r['id'] for r in rows],calendar=timezone,timeframe='1w',variant='derived'))
    return result


def store_bar(store, instrument, provider, timeframe, row, *, observation, adjustment='raw', price_basis='trade', variant='native', calendar='UTC'):
    p={**row,'instrument':instrument,'provider':provider,'timeframe':timeframe,'adjustment':adjustment,
       'price_basis':price_basis,'variant':variant,'calendar':calendar}
    for key in ['open','high','low','close','volume']:
        p[key]=None if row.get(key) is None else number(row[key])
    if any(p[k] is None or D(p[k])<=0 for k in ['open','high','low','close']):raise ValueError('Missing/nonpositive OHLC')
    if D(p['low'])>min(D(p['open']),D(p['close'])) or D(p['high'])<max(D(p['open']),D(p['close'])) or D(p['low'])>D(p['high']):
        raise ValueError('Inconsistent OHLC')
    if p['volume'] is not None and D(p['volume'])<0:raise ValueError('Negative volume')
    if type(p.get('complete')) is not bool:raise ValueError('Explicit bar completion required')
    key=encode([instrument,provider,timeframe,p['event_start_ms'],calendar,adjustment,price_basis,variant])
    return store.fact('bar',provider,key,p,observation=observation,allow_correction=True)
