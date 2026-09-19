"""Bounded, operator-supplied broker statement reconciliation; no network calls."""
from collections import Counter
from contextlib import nullcontext
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path

from kis_hl.data_ingestion import normalize_rows
from kis_hl.data_store import encode, number, reject_secrets
from kis_hl.journal_sync import Scope


def signature(dataset, payload):
    fields=['instrument','currency','event_start_ms','event_end_ms']
    fields+=['side','quantity','notional','total_cost','gross_pnl'] if dataset=='trade' else ['kind','amount','grain']
    numeric={'quantity','notional','total_cost','amount','gross_pnl'}
    return encode({k:number(payload[k]) if k in numeric and payload.get(k) is not None else payload.get(k) for k in fields})


def _reconcile(store, path, sha256, *, apply=False):
    """Match complete bounded source rows; a checksum binds bytes, not authenticity.

    The operator must supply an independently obtained complete broker statement,
    not a report generated from this store. Unknown/partial sources cannot certify
    coverage. Existing economic facts are matched, never invented to make totals fit.
    """
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha256:raise ValueError('Statement digest mismatch')
    document=json.loads(raw);reject_secrets(document)
    if document.get('schema_version')!=1 or document.get('complete') is not True or not document.get('source'):
        raise ValueError('A complete, identified independent statement is required')
    account=document['account'];scope=Scope(account['venue'],account['environment'],account['native_id']).key
    with store.connect() as db:
        if not db.execute('SELECT 1 FROM accounts WHERE id=?',(scope,)).fetchone():raise ValueError('Unknown statement account')
    start,end=document['start_ms'],document['end_ms'];dataset=document['dataset']
    if type(start) is not int or type(end) is not int or not 0<=start<end or dataset not in {'trade','cash'}:
        raise ValueError('Invalid bounded reconciliation interval/dataset')
    parsers={'trade':{'statement','hl_fills','kis_overseas_trans'},'cash':{'hl_funding'}}
    if document.get('parser') not in parsers[dataset]:raise ValueError('Statement parser/dataset mismatch')
    parsed=normalize_rows(document['parser'],document['rows'])
    payloads=[p for ds,_,p in parsed if ds==dataset]
    if len(payloads)!=len(parsed):raise ValueError('Statement contains unrelated dataset')
    if any(not start<=p['event_start_ms']<p['event_end_ms']<=end for p in payloads):
        raise ValueError('Statement row is outside the complete interval')
    facts=[f for f in store.facts(dataset,scope=scope) if f['event_start_ms']<end and f['event_end_ms']>start]
    if any(f['event_start_ms']<start or f['event_end_ms']>end for f in facts):
        raise ValueError('Reconciliation interval splits a source fact')
    if Counter(signature(dataset,p) for p in payloads)!=Counter(signature(dataset,f['payload']) for f in facts):
        raise ValueError('Statement economics do not match canonical facts')
    if any(f['payload'].get('quality_reasons') for f in facts):
        raise ValueError('Unresolved allocation/quality requires source correction first')
    anchors=[]
    if dataset=='trade':
        if any(p.get('total_cost') is None for p in payloads):raise ValueError('Statement costs are incomplete')
        opening=document.get('opening_inventory',{});closing=document.get('closing_inventory',{})
        instruments={f['instrument'] for f in facts}
        if set(opening)!=instruments or set(closing)!=instruments:
            raise ValueError('Opening and closing inventory required for every statement instrument')
        for instrument in sorted(instruments):
            rows=[f for f in facts if f['instrument']==instrument]
            quantity=D(number(opening[instrument]));ending=D(number(closing[instrument]))
            first_time=rows[0]['event_start_ms'];first=[f for f in rows if f['event_start_ms']==first_time]
            if len(first)>1:
                candidates=[f for f in first if f['payload'].get('position_before') is not None and D(f['payload']['position_before'])==quantity]
                if len(candidates)!=1:raise ValueError('Statement cannot establish first same-day sequence')
                first=candidates
            anchor=first[0]
            if anchor['payload'].get('position_before') is not None and D(anchor['payload']['position_before'])!=quantity:
                raise ValueError('Statement opening inventory contradicts source position')
            ending_computed=quantity+sum((D(f['payload']['quantity'])*(1 if f['payload']['side']=='buy' else -1) for f in rows),D(0))
            if ending_computed!=ending:raise ValueError('Statement ending inventory does not reconcile')
            if account['venue']=='kis' and (quantity<0 or ending<0):raise ValueError('Cash stock inventory cannot be negative')
            # Only attach a supplied flat boundary. Nonzero retained inventory
            # requires a cost basis and remains pending in the cycle builder.
            if quantity==0 and anchor['payload'].get('position_before') is None:anchors.append(anchor)
    result={'account_id':scope,'dataset':dataset,'start_ms':start,'end_ms':end,
            'matched_facts':len(facts),'source_sha256':sha256,'applied':apply}
    if not apply:return result
    observation=store.observe('reconciliation',scope,raw,metadata={'sha256':sha256,'source':document['source']})
    for fact in anchors:
        store.fact(dataset,scope,fact['business_key'],{**fact['payload'],'position_before':'0',
            'sequence_evidence':'Independent bounded statement opening inventory'},observation=observation,allow_correction=True)
    current=[f for f in store.facts(dataset,scope=scope) if f['event_start_ms']<end and f['event_end_ms']>start]
    store.coverage(dataset,scope,start,end,'complete',{'method':'independent_statement_v1',
        'source_observation_id':observation,'source_sha256':sha256,
        'fact_ids':sorted(f['id'] for f in current),'source':document['source']})
    return result


def coverage_current(record, facts):
    """A certified fact population stops being complete after a revision/addition."""
    details=record['details']
    if isinstance(details,str):details=json.loads(details)
    if details.get('method')!='independent_statement_v1':return True
    ids=sorted(f['id'] for f in facts if f['scope']==record['scope'] and f['dataset']==record['dataset']
               and f['event_start_ms']<record['requested_end_ms'] and f['event_end_ms']>record['requested_start_ms'])
    return ids==details['fact_ids']


def reconcile(store, path, sha256, *, apply=False):
    # Apply rechecks current facts while holding one short SQLite write transaction.
    with store.atomic() if apply else nullcontext():
        return _reconcile(store,path,sha256,apply=apply)
