"""Reproducible account/currency journals from canonical facts, without orders."""
from collections import defaultdict
from decimal import Decimal as D
import hashlib
import html
import json
import os
from pathlib import Path
import tempfile
from kis_hl.data_quality import effective_funding
from kis_hl.data_store import encode, now_ms

Z=D(0)
INVENTORY_POLICY_VERSION='kis-inventory-v1'


def serial(value):
    if isinstance(value,D):return str(value)
    if isinstance(value,dict):return {k:serial(v) for k,v in value.items()}
    if isinstance(value,list):return [serial(v) for v in value]
    return value


def statistics(cycles):
    rows=[c for c in cycles if c['status']=='FINALIZED'];wins=[c for c in rows if c['net_pnl']>0];losses=[c for c in rows if c['net_pnl']<0]
    avg=lambda xs,key:sum((x[key] for x in xs),Z)/len(xs) if xs else None
    aw,al=avg(wins,'net_return_pct'),avg(losses,'net_return_pct')
    holding=lambda xs:avg(xs,'holding_days') if xs and all(c['holding_days'] is not None for c in xs) else None
    return dict(trade_count=len(rows),success_count=len(wins),failure_count=len(losses),breakeven_count=len(rows)-len(wins)-len(losses),
        average_profit=aw,average_loss=al,success_failure_ratio=aw/abs(al) if wins and losses else None,
        win_rate_pct=D(len(wins))*100/(len(wins)+len(losses)) if wins or losses else None,
        adjusted_success_failure_ratio=aw*len(wins)/(abs(al)*len(losses)) if wins and losses else None,
        max_profit=max((c['net_return_pct'] for c in wins),default=None),max_loss=min((c['net_return_pct'] for c in losses),default=None),
        average_profit_holding_days=holding(wins),average_loss_holding_days=holding(losses))


def account_cycles(trades):
    groups=defaultdict(list)
    for fact in trades:groups[(fact['instrument'],fact['payload']['currency'])].append(fact)
    cycles=[];issues=[]
    for (instrument,currency),rows in groups.items():
        conflicts=[(a,b) for i,a in enumerate(rows) for b in rows[i+1:] if a['payload'].get('grain')!=b['payload'].get('grain') and a['event_start_ms']<b['event_end_ms'] and b['event_start_ms']<a['event_end_ms']]
        if conflicts:
            issues.append({'kind':'overlapping_trade_grains','instrument':instrument,'fact_ids':sorted({f['id'] for pair in conflicts for f in pair})})
            continue
        position=Z;inventory_cost=Z;active=None;queue=list(rows)
        is_kis=instrument.startswith('kis:')
        anchored=not is_kis
        instrument_cycles=[]
        ending_by_time=defaultdict(list)
        if is_kis:
            for row in rows:
                if row['payload']['time_precision']=='DAY' and row['payload'].get('day_end_quantity') is not None:
                    ending_by_time[row['event_start_ms']].append(row)

        def invalidate_overlapping(reason, timestamp):
            # Exact earlier exits survive later gaps. DAY exits remain ambiguous
            # until all same-day activity has been reconciled, even on early errors.
            for cycle in instrument_cycles:
                if cycle['opened_ms']<=timestamp and (cycle['closed_end_ms'] is None or cycle['closed_end_ms']>timestamp):
                    cycle['reasons'].append(reason)

        while queue:
            t=queue[0]['event_start_ms'];same=[f for f in queue if f['event_start_ms']==t]
            # Native position-before is usable order evidence. Arbitrary order IDs are not.
            candidates=[f for f in same if f['payload'].get('position_before') is not None and D(f['payload']['position_before'])==position]
            if len(same)>1 and len(candidates)!=1:
                issues.append({'kind':'ambiguous_chronology','instrument':instrument,'fact_ids':[f['id'] for f in same]})
                invalidate_overlapping('ambiguous_chronology',t)
                break
            fact=candidates[0] if len(candidates)==1 else same[0];queue.remove(fact);p=fact['payload']
            if p.get('position_before') is not None and D(p['position_before'])!=position:
                issues.append({'kind':'opening_inventory_gap','instrument':instrument,'fact_ids':[fact['id']]})
                invalidate_overlapping('opening_inventory_gap',t)
                break
            q=D(p['quantity']);signed=q*(1 if p['side']=='buy' else -1)
            # A cash-stock oversell is missing inventory evidence, never a short
            # reversal. Reject the entire row before closing the tracked segment.
            if is_kis and position+signed<0:
                issues.append({'kind':'opening_inventory_gap','scope':fact['scope'],
                               'currency':currency,'instrument':instrument,'fact_ids':[fact['id']]})
                invalidate_overlapping('opening_inventory_gap',t)
                break
            if position==0 and p.get('position_before') is not None:
                anchored=True
            remaining=signed
            while remaining:
                if position==0:
                    active=dict(id=f'{fact["scope"][:10]}:{fact["id"]}:{len(cycles)}',account=fact['scope'],instrument=instrument,currency=currency,
                        side='long' if remaining>0 else 'short',opened_ms=p['event_start_ms'],closed_ms=None,closed_end_ms=None,
                        entry_notional=Z,entry_quantity=Z,exit_notional=Z,exit_quantity=Z,gross_pnl=Z,
                        trading_fee=Z,funding_cashflow=Z,cost_components={},fact_ids=[],shared_funding_ids=[],reasons=[],
                        strategy=p.get('strategy','unassigned'),time_precision=p['time_precision'])
                    cycles.append(active)
                    instrument_cycles.append(active)
                    if not anchored:
                        active['reasons'].append('inventory_unanchored')
                        issues.append({'kind':'inventory_unanchored','scope':fact['scope'],
                                       'currency':currency,'instrument':instrument,'fact_ids':[fact['id']]})
                adding=position==0 or position*remaining>0
                take=abs(remaining) if adding else min(abs(position),abs(remaining))
                fraction=take/q;notional=D(p['notional'])*fraction;prefix='entry' if adding else 'exit'
                active[prefix+'_quantity']+=take;active[prefix+'_notional']+=notional
                closing_basis=inventory_cost/abs(position) if not adding else Z
                if adding:inventory_cost+=notional
                else:inventory_cost-=closing_basis*take
                if p.get('gross_pnl') is not None:
                    # Venue closedPnl belongs to the closing segment, including a reversal.
                    if not adding:active['gross_pnl']+=D(p['gross_pnl'])
                elif not adding:
                    active['gross_pnl']+=(notional-closing_basis*take)*(1 if active['side']=='long' else -1)
                if p.get('total_cost') is None:active['reasons'].append('unknown_cost')
                else:active['trading_fee']+=D(p['total_cost'])*fraction
                for kind,amount in p.get('costs',{}).items():
                    if amount is not None:active['cost_components'][kind]=active['cost_components'].get(kind,Z)+D(amount)*fraction
                if p['time_precision']!='MILLISECOND':active['time_precision']='DAY'
                if p.get('strategy','unassigned')!=active['strategy']:active['strategy']='mixed'
                active['fact_ids'].append(fact['id'])
                change=take*(1 if remaining>0 else -1);position+=change;remaining-=change
                if position==0:
                    inventory_cost=Z
                    active['closed_ms']=p['event_start_ms'];active['closed_end_ms']=p['event_end_ms']
            # A DAY balance describes all activity that day, including re-entry.
            # Validate only after the last event; conflicting snapshots are not
            # permission to choose whichever balance matches the reconstruction.
            if is_kis and t in ending_by_time and not any(f['event_start_ms']==t for f in queue):
                evidence=ending_by_time[t]
                endings={D(f['payload']['day_end_quantity']) for f in evidence}
                if endings!={position}:
                    issues.append({'kind':'ending_inventory_mismatch','scope':fact['scope'],
                                   'currency':currency,'instrument':instrument,
                                   'fact_ids':[f['id'] for f in evidence]})
                    invalidate_overlapping('ending_inventory_mismatch',t)
                    break
    return cycles,issues


def journal(store, accounts, *, as_of_ms=None):
    if not accounts or len(set(accounts))!=len(accounts):raise ValueError('Explicit unique account selection required')
    asof=now_ms() if as_of_ms is None else as_of_ms
    allfacts=[f for f in store.facts(as_of_ms=asof) if f['scope'] in accounts and f['event_start_ms']<=asof]
    trades=[f for f in allfacts if f['dataset']=='trade'];cash=[f for f in allfacts if f['dataset']=='cash']
    funding,issues=effective_funding(cash);cycles=[];summaries=[]
    with store.connect() as db:
        labels={r['id']:r['label'] for r in db.execute('SELECT id,label FROM accounts')}
        coverage=[dict(r) for r in db.execute('SELECT * FROM dataset_coverage WHERE observed_ms<=?',(asof,)) if r['scope'] in accounts]
    if any(a not in labels for a in accounts):raise ValueError('Unknown report account')
    for account in accounts:
        current,problems=account_cycles([f for f in trades if f['scope']==account]);cycles.extend(current);issues.extend(problems)
        for c in current:
            end=c['closed_end_ms'] or asof+1
            for dataset in ['trade','cash']:
                if dataset=='cash' and c['instrument'].startswith('kis:'):continue
                intervals=sorted((r['requested_start_ms'],r['requested_end_ms']) for r in coverage if r['scope']==account and r['dataset']==dataset and r['status']=='complete')
                covered=c['opened_ms']
                for a,b in intervals:
                    if a<=covered:covered=max(covered,b)
                if covered<end:c['reasons'].append(dataset+'_coverage_unverified')
        for f in [f for f in funding if f['scope']==account]:
            candidates=[c for c in current if c['instrument']==f['instrument'] and c['currency']==f['payload']['currency'] and c['opened_ms']<f['event_end_ms'] and (c['closed_end_ms'] or asof+1)>f['event_start_ms']]
            if len(candidates)==1:
                candidates[0]['funding_cashflow']+=D(f['payload']['amount']);candidates[0]['fact_ids'].append(f['id'])
            else:
                issues.append({'kind':'funding_allocation_pending','fact_ids':[f['id']],'cycle_ids':[c['id'] for c in candidates]})
                for c in candidates:c['shared_funding_ids'].append(f['id'])
        for c in current:
            if any(i.get('kind')=='funding_representation_conflict' and i.get('scope')==account and i.get('instrument')==c['instrument'] for i in issues):c['reasons'].append('funding_representation_conflict')
            c['status']='OPEN' if c['closed_ms'] is None else ('PENDING' if c['reasons'] or c['shared_funding_ids'] else 'FINALIZED')
            c['net_before_shared_funding']=c['gross_pnl']-c['trading_fee']+c['funding_cashflow']
            c['net_pnl']=c['net_before_shared_funding'] if not c['reasons'] and not c['shared_funding_ids'] else None
            c['net_return_pct']=c['net_pnl']/c['entry_notional']*100 if c['net_pnl'] is not None else None
            c['holding_days']=D(c['closed_ms']-c['opened_ms'])/86400000 if c['closed_ms'] is not None and c['time_precision']=='MILLISECOND' else None
        currencies={f['payload']['currency'] for f in [*trades,*cash] if f['scope']==account}
        for currency in sorted(currencies):
            ts=[f for f in trades if f['scope']==account and f['payload']['currency']==currency]
            cs=[c for c in current if c['currency']==currency]
            fs=[f for f in funding if f['scope']==account and f['payload']['currency']==currency]
            gross=sum((D(f['payload']['gross_pnl']) for f in ts),Z) if ts and all(f['payload'].get('gross_pnl') is not None for f in ts) else sum((c['gross_pnl'] for c in cs),Z)
            fee=sum((D(f['payload']['total_cost']) for f in ts if f['payload'].get('total_cost') is not None),Z)
            cashflow=sum((D(f['payload']['amount']) for f in fs),Z)
            incomplete=any(f['payload'].get('total_cost') is None for f in ts) or any(i.get('scope')==account and i.get('currency')==currency for i in issues) or bool(problems)
            components=defaultdict(lambda:Z)
            for f in ts:
                for k,v in f['payload'].get('costs',{}).items():
                    if v is not None:components[k]+=D(v)
            summaries.append(dict(account=account,label=labels[account],currency=currency,gross_booked_pnl=gross,trading_fee=fee,cost_components=dict(components),funding_cashflow=cashflow,
                net_booked_pnl=None if incomplete else gross-fee+cashflow,closed_cycles=sum(c['closed_ms'] is not None for c in cs),open_cycles=sum(c['closed_ms'] is None for c in cs),
                coverage_status='verified' if cs and not problems and all(not c['reasons'] for c in cs) else 'partial_or_unverified',
                statistics_by_strategy={s:statistics([c for c in cs if c['strategy']==s]) for s in {c['strategy'] for c in cs}}))
    result=serial(dict(accounts=accounts,as_of_ms=asof,summary_by_account_currency=summaries,cycles=cycles,quality_findings=issues,
                       currency_conversion=None,capital_return=None,metric_version='canonical-v1',
                       inventory_policy_version=INVENTORY_POLICY_VERSION,coverage_evidence=coverage))
    run=store.pin('journal',{'accounts':accounts,'metric_version':'canonical-v1',
                           'inventory_policy_version':INVENTORY_POLICY_VERSION},[f['id'] for f in allfacts],result,as_of_ms=asof)
    return {'report_id':run,**result}


def export_report(store, run_id, path):
    path=Path(path).expanduser().resolve()
    if path.suffix not in {'.json','.html'} or path in {store.path,Path(str(store.path)+'-wal'),Path(str(store.path)+'-shm')}:
        raise ValueError('Export requires a JSON/HTML report path outside database files')
    if path.exists():
        raise ValueError('Export target must be a new file; choose a versioned report path')
    path.parent.mkdir(parents=True,exist_ok=True)
    with store.connect() as db:
        row=db.execute('SELECT result FROM analysis_runs WHERE id=?',(run_id,)).fetchone()
        if not row:raise ValueError('Unknown report ID')
        content=row['result']
        if path.suffix=='.html':
            content='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Investment journal</title><style>body{max-width:1000px;margin:3rem auto;font:15px system-ui;padding:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>Investment journal</h1><p>Amounts remain separated by account and currency. Null values are unavailable or pending.</p><pre>'+html.escape(json.dumps(json.loads(content),indent=2))+'</pre></html>'
        artifact=db.execute("INSERT INTO report_artifacts(run_id,path,status) VALUES(?,?,'pending')",(run_id,str(path))).lastrowid
    raw=content.encode();digest=hashlib.sha256(raw).hexdigest()
    fd,temp=tempfile.mkstemp(dir=path.parent,prefix='.export-')
    try:
        with os.fdopen(fd,'wb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())
        os.replace(temp,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    with store.connect() as db:db.execute("UPDATE report_artifacts SET status='ready',digest=? WHERE id=?",(digest,artifact))
    return {'report_id':run_id,'path':str(path),'sha256':digest}
