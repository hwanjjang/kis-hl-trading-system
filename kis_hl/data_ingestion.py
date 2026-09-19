"""Validated account source adapters. Dates never become exact execution times."""
from datetime import datetime, timedelta
from decimal import Decimal as D
from itertools import permutations
from zoneinfo import ZoneInfo

from kis_hl.data_store import encode, number

DAY = 86400000


def day_interval(value, zone):
    dt = datetime.strptime(value.replace('-',''), '%Y%m%d').replace(tzinfo=ZoneInfo(zone))
    return int(dt.timestamp()*1000), int((dt+timedelta(days=1)).timestamp()*1000)


def hl_fill(row):
    if row['side'] not in {'B','A'} or row['feeToken'].strip() != 'USDC':
        raise ValueError('Unsupported fill side or unverified collateral')
    coin = row['coin']
    if coin.startswith('@') or '/' in coin:
        raise ValueError('Spot identity requires an explicit instrument mapping')
    t = row['time']
    if type(t) is not int or t < 0 or D(number(row['sz']))<=0 or D(number(row['px']))<=0:
        raise ValueError('Invalid execution timestamp/size/price')
    total = number(row['fee']);builder = number(row.get('builderFee','0'))
    return 'trade', str(row['tid'])+':'+coin, dict(instrument='hl:'+coin, symbol=coin, currency='USDC',
        event_start_ms=t,event_end_ms=t+1,time_precision='MILLISECOND',grain='EXECUTION',
        side='buy' if row['side']=='B' else 'sell',quantity=number(row['sz']),price=number(row['px']),
        notional=number(D(row['sz'])*D(row['px'])),position_before=number(row['startPosition']),
        gross_pnl=number(row['closedPnl']),costs={'exchange':number(D(total)-D(builder)),'builder':builder},
        total_cost=total,order_id=str(row['oid']),strategy='unassigned',origin='unknown')


def hl_funding(row):
    delta=row['delta'];t=row['time'];samples=delta.get('nSamples')
    if samples is not None and (type(samples) is not int or not 1<=samples<=24 or t % DAY):
        raise ValueError('Unverified funding aggregation interval')
    grain='DAY' if samples is not None else 'POINT'
    end=t+DAY if samples is not None else t+1
    key=encode([delta['coin'],t,end,grain,row['hash']])
    return 'cash',key,dict(instrument='hl:'+delta['coin'],symbol=delta['coin'],currency='USDC',
        event_start_ms=t,event_end_ms=end,time_precision='INTERVAL' if samples else 'MILLISECOND',
        grain=grain,kind='funding',amount=number(delta['usdc']),samples=samples)


def kis_overseas(row):
    side={'01':'sell','02':'buy'}.get(row['sll_buy_dvsn_cd'])
    if side is None or not row['crcy_cd'].strip():
        raise ValueError('Unsupported statement side/currency')
    amount=D(number(row['tr_frcr_amt2']));broker=D(number(row['dmst_frcr_fee1']));foreign=D(number(row['frcr_fee1']))
    settlement=D(number(row['frcr_excc_amt_1']))
    if settlement != amount+(broker+foreign)*(1 if side=='buy' else -1):
        raise ValueError('Settlement does not reconcile both-side charges')
    quantity=D(number(row['ccld_qty']))
    if quantity<=0 or amount<=0:
        raise ValueError('Positive statement quantity/notional required')
    start,end=day_interval(row['trad_dt'],'America/New_York')
    # Contract is one daily symbol/side/currency row. Duplicates with differing economics conflict.
    key=encode([row['trad_dt'],row['pdno'],side,row['crcy_cd'],row.get('loan_dvsn_cd','')])
    return 'trade',key,dict(instrument='kis:'+row['pdno'],symbol=row['pdno'],currency=row['crcy_cd'],
        event_start_ms=start,event_end_ms=end,time_precision='DAY',grain='DAY_SYMBOL_SIDE',
        side=side,quantity=number(row['ccld_qty']),notional=number(amount),
        price=number(amount/quantity),costs={'broker':number(broker),'overseas':number(foreign),'tax':None,'interest':None},
        total_cost=number(broker+foreign),settlement=number(settlement),strategy='unassigned',origin='unknown')


def statement(row):
    """Explicit portable statement contract for exact or DAY precision sources."""
    p=dict(row)
    key=p.pop('source_id')
    if not isinstance(key,str) or not key.strip():raise ValueError('Explicit source identity required')
    if p.get('time_precision') not in {'MILLISECOND','DAY'} or p.get('side') not in {'buy','sell'}:
        raise ValueError('Explicit chronology and side required')
    for field in ['quantity','notional','price']:
        p[field]=number(p[field])
        if D(p[field])<=0:raise ValueError('Positive trade amounts required')
    if p.get('total_cost') is not None:p['total_cost']=number(p['total_cost'])
    for field in ['gross_pnl','position_before','settlement','day_end_quantity']:
        if p.get(field) is not None:p[field]=number(p[field])
    p['costs']={k:None if v is None else number(v) for k,v in p.get('costs',{}).items()}
    if p.get('total_cost') is not None:
        total=D(p['total_cost'])
        components=p['costs']
        # Components are disjoint included costs. None means unavailable detail.
        if components and all(v is not None for v in components.values()) and sum((D(v) for v in components.values()),D(0))!=total:
            raise ValueError('Cost components do not reconcile total_cost')
        if p.get('settlement') is not None:
            expected=D(p['notional'])+total*(1 if p['side']=='buy' else -1)
            if D(p['settlement'])!=expected:
                raise ValueError('Settlement does not reconcile total_cost')
    if not p.get('currency') or not p.get('instrument'):raise ValueError('Explicit units required')
    start,end=p['event_start_ms'],p['event_end_ms']
    if type(start) is not int or type(end) is not int or not 0<=start<end:raise ValueError('Invalid statement interval')
    if p['time_precision']=='MILLISECOND' and end!=start+1:raise ValueError('Exact execution must be a point interval')
    return 'trade',key,p


PARSERS={'hl_fills':hl_fill,'hl_funding':hl_funding,'kis_overseas_trans':kis_overseas,'statement':statement}


def ingest_rows(store, account, parser, rows, *, observation=None, allow_correction=False, metadata=None):
    if parser not in PARSERS:raise ValueError('Unsupported source parser')
    if not isinstance(rows,list):raise ValueError('Source rows must be a list')
    # Capture before normalization so a rejected row remains recoverable evidence.
    if observation is None:
        observation=store.observe(parser,account,encode(rows).encode(),capture_format='decoded_json',metadata=metadata)
    parsed=normalize_rows(parser, rows)
    result=[]
    for i,(dataset,key,payload) in enumerate(parsed):
        result.append(store.fact(dataset,account,key,payload,observation=observation,locator=str(i),allow_correction=allow_correction))
    return result


def normalize_rows(parser, rows):
    """Validate the whole observation before writing economic facts."""
    parsed=[PARSERS[parser](row) for row in rows]
    if parser=='kis_overseas_trans':
        keys=[(dataset,key) for dataset,key,_ in parsed]
        if len(set(keys))!=len(keys):
            raise ValueError('Ambiguous repeated daily source identity')
    return parsed


def ingest_maturing_rows(store, account, parser, rows, *, observation):
    """Only reconciled KIS day snapshots may evolve without a manual correction."""
    parsed=normalize_rows(parser,rows)
    old_rows=store.facts('trade',scope=account)
    result=[]
    for i,(dataset,key,payload) in enumerate(parsed):
        eligible={'DAY_SYMBOL_SIDE','ORDER_CUMULATIVE_RECONCILED','DAY_SYMBOL_SIDE_RECONCILED'}
        if payload.get('grain') not in eligible:
            raise ValueError('Unverified cumulative source grain')
        matches=[f for f in old_rows if f['instrument']==payload['instrument']
                 and f['event_start_ms']==payload['event_start_ms']
                 and f['payload'].get('side')==payload['side']
                 and f['payload'].get('currency')==payload['currency']]
        if len(matches)>1:
            raise ValueError('Ambiguous existing daily representation')
        if matches:
            old=matches[0];p=old['payload']
            if p.get('grain') not in eligible or D(payload['quantity'])<D(p['quantity']) or D(payload['notional'])<D(p['notional']):
                raise ValueError('Decreasing or incompatible source requires explicit correction')
            # Reuse the old key across single-order -> grouped-day maturation.
            # Prior raw evidence and revisions remain intact; never count both.
            key=old['business_key']
        result.append(store.fact(dataset,account,key,payload,observation=observation,locator=str(i),allow_correction=True))
    return result


def domestic_bundle(bundle):
    """Match daily profit quantities, cumulative orders and symbol-scoped daily fees."""
    result=[]
    for day in bundle['days']:
        if D(number(day.get('loan_int','0'))) != 0:raise ValueError('Loan interest allocation requires source evidence')
        matched=[r for r in bundle['orders'] if r['ord_dt']==day['trad_dt'] and r['pdno']==day['pdno'] and D(r['tot_ccld_qty'])>0]
        summary=bundle['costs_by_day_symbol'][day['trad_dt']+':'+day['pdno']]
        for code,prefix in [('02','buy'),('01','sll')]:
            rows=[r for r in matched if r['sll_buy_dvsn_cd']==code]
            if sum((D(r['tot_ccld_qty']) for r in rows),D(0))!=D(day[prefix+'_qty']) or sum((D(r['tot_ccld_amt']) for r in rows),D(0))!=D(day[prefix+'_amt']):raise ValueError('Daily quantities/notional do not reconcile')
            if not rows:continue
            r=rows[0];fee=D(number(summary[prefix+'_fee_smtl']));tax=D(number(summary['buy_tax_smtl' if code=='02' else 'sll_tltx_smtl']))
            start,end=day_interval(day['trad_dt'],'Asia/Seoul');amount=D(number(day[prefix+'_amt']));quantity=D(number(day[prefix+'_qty']))
            result.append(dict(source_id=encode([r['ord_dt'],r['pdno'],code,r['odno'] if len(rows)==1 else 'day']),instrument='kis:'+r['pdno'],symbol=r['pdno'],currency='KRW',
                event_start_ms=start,event_end_ms=end,time_precision='DAY',grain='DAY_SYMBOL_SIDE_RECONCILED',side='buy' if code=='02' else 'sell',
                quantity=number(quantity),notional=number(amount),price=number(amount/quantity),total_cost=number(fee+tax),costs={'broker':number(fee),'tax':number(tax),'interest':'0'},
                settlement=number(amount+(fee+tax)*(1 if code=='02' else -1)),order_ids=sorted(str(item['odno']) for item in rows),quality_reasons=['shared_order_cost_allocation'] if len(rows)>1 else [],day_end_quantity=number(day['hldg_qty']),strategy='unassigned',origin='unknown'))
    # A dated sell cost basis plus day-end inventory can establish sequence without
    # treating order time as execution time. Unresolved paths keep DAY ambiguity.
    balances={};basis={}
    for day in sorted(bundle['days'],key=lambda r:(r['trad_dt'],r['pdno'])):
        symbol=day['pdno'];start,_=day_interval(day['trad_dt'],'Asia/Seoul')
        events=[r for r in result if r['symbol']==symbol and r['event_start_ms']==start]
        opening=D(day['hldg_qty'])-D(day['buy_qty'])+D(day['sll_qty'])
        if opening!=balances.get(symbol,D(0)) or (opening and symbol not in basis):
            continue
        candidates=[]
        for sequence in permutations(events):
            qty=opening;cost=basis.get(symbol,D(0));sold_qty=D(0);sold_cost=D(0);steps=[]
            for event in sequence:
                steps.append((event,qty));size=D(event['quantity']);amount=D(event['notional'])
                if event['side']=='buy':qty+=size;cost+=amount
                else:
                    if size>qty:break
                    allocated=cost/qty*size;cost-=allocated;qty-=size;sold_qty+=size;sold_cost+=allocated
            else:
                reported=D(day['pchs_unpr'])
                basis_matches=not sold_qty or (sold_cost/sold_qty).quantize(D(1).scaleb(reported.as_tuple().exponent))==reported
                if qty==D(day['hldg_qty']) and basis_matches:candidates.append((steps,qty,cost))
        if len(candidates)==1:
            steps,qty,cost=candidates[0]
            for event,before in steps:
                event['position_before']=number(before)
                event['sequence_evidence']='Daily sell cost basis and ending inventory'
            balances[symbol]=qty;basis[symbol]=cost
    return result
