"""Read-only account comparison and digest-bound, atomic local adjustments."""
from collections import defaultdict
from contextlib import contextmanager
from decimal import Decimal as D
import hashlib
import json
import os
from pathlib import Path

from kis_hl.data_ingestion import domestic_bundle, normalize_rows, cost_quality
from kis_hl.data_quality import effective_funding
from kis_hl.data_store import encode, now_ms, number, reject_secrets
from kis_hl.journal_sync import Scope


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def write_private(path, value):
    """Create an owner-only artifact, never replace an existing path."""
    reject_secrets(value)
    path=Path(path).expanduser()
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    data=(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data);f.flush();os.fsync(f.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return {'path':str(path),'sha256':hashlib.sha256(data).hexdigest()}


@contextmanager
def read_snapshot(store):
    if getattr(store,'_transaction',None) is not None:
        yield
        return
    with store.connect() as db:
        db.execute('BEGIN')
        store._transaction=db
        try:yield
        finally:store._transaction=None


def normalize_bundle(bundle):
    reject_secrets(bundle)
    if bundle.get('schema_version')!=1 or bundle.get('kind')!='account-audit-bundle':
        raise ValueError('Unsupported account audit bundle')
    a=bundle['account'];venue=a['venue'];environment=a['environment'];native=a['native_id']
    if venue not in {'kis','hyperliquid'} or not isinstance(native,str) or not native.strip():
        raise ValueError('Explicit supported account required')
    if environment not in ({'live'} if venue=='kis' else {'mainnet','testnet'}):
        raise ValueError('Unsupported account environment')
    start,end=bundle['start_ms'],bundle['end_ms']
    if type(start) is not int or type(end) is not int or not 0<=start<end:
        raise ValueError('Invalid audit interval')
    if type(bundle.get('collection_complete')) is not bool or type(bundle.get('inventory_complete')) is not bool:
        raise ValueError('Explicit collection and inventory status required')
    required={'hl_fills','hl_funding'} if venue=='hyperliquid' else {'kis_domestic_bundle','kis_overseas_trans'}
    if {s['parser'] for s in bundle['sources']}!=required or len(bundle['sources'])!=2:
        raise ValueError('Bundle must contain each venue source exactly once')
    verify_source_evidence(bundle)
    scope=Scope(venue,environment,native).key;facts={}
    for source in bundle['sources']:
        parser=source['parser'];rows=source['data']
        if parser=='kis_domestic_bundle':
            day_keys={d['trad_dt']+':'+d['pdno'] for d in rows['days']}
            for order in rows['orders']:
                key=order['ord_dt']+':'+order['pdno']
                if D(number(order['tot_ccld_qty']))>0 and (key not in day_keys or key not in rows['costs_by_day_symbol']):
                    raise ValueError('Executed order lacks corroborating daily source/cost evidence')
            rows=domestic_bundle(rows);parser='statement'
        if not isinstance(rows,list):raise ValueError('Invalid source rows')
        for dataset,key,payload in normalize_rows(parser,rows):
            if not start<=payload['event_start_ms']<end:
                raise ValueError('Source row outside audit interval')
            expected='hl:' if venue=='hyperliquid' else 'kis:'
            if not payload['instrument'].startswith(expected):raise ValueError('Source venue mismatch')
            identity=(dataset,key)
            if identity in facts and facts[identity]['payload']!=payload:raise ValueError('Conflicting duplicate source identity')
            facts[identity]={'dataset':dataset,'scope':scope,'business_key':key,'payload':payload}
    for evidence in bundle.get('evidence',[]):
        if 'raw' in evidence and json.loads(evidence['raw'])!=evidence['body']:
            raise ValueError('Raw source bytes disagree with decoded evidence')
    positions={}
    for row in bundle['positions']:
        instrument=row['instrument'];quantity=number(row['quantity'])
        if not instrument.startswith('hl:' if venue=='hyperliquid' else 'kis:') or instrument in positions:
            raise ValueError('Invalid or duplicate source position')
        positions[instrument]=quantity
    return scope,list(facts.values()),positions


def verify_source_evidence(bundle):
    """Bind decoded adapter inputs to captured native rows, not just raw/body pairs."""
    evidence=bundle.get('evidence',[])
    if not evidence:return  # Explicit operator input; never label it broker-authenticated.
    def rows(dataset,field=None):
        entries=[e for e in evidence if e['dataset']==dataset]
        if not entries:raise ValueError('Missing captured source evidence: '+dataset)
        return {encode(r) for e in entries for r in (e['body'][field] if field else e['body'])}
    sources={s['parser']:s['data'] for s in bundle['sources']}
    if bundle['account']['venue']=='hyperliquid':
        for parser,data in sources.items():
            if {encode(r) for r in data}!=rows(parser):raise ValueError('Adapter input differs from captured evidence')
    else:
        domestic=sources['kis_domestic_bundle']
        for data,dataset in [(domestic['days'],'kis_domestic_trade_profit'),(domestic['orders'],'kis_domestic_history'),
                             (sources['kis_overseas_trans'],'kis_overseas_transactions')]:
            if {encode(r) for r in data}!=rows(dataset,'output1'):
                raise ValueError('Adapter input differs from captured evidence')
        for key,cost in domestic['costs_by_day_symbol'].items():
            day,symbol=key.split(':')
            matches=[e for e in evidence if e['dataset']=='kis_domestic_trade_profit'
                     and e.get('parameters',{}).get('date_from')==day
                     and e.get('parameters',{}).get('date_to')==day
                     and e.get('parameters',{}).get('symbol')==symbol]
            if not any(e['body']['output2']==[cost] for e in matches):
                raise ValueError('Daily cost differs from captured evidence')
    native_positions={};position_evidence=False
    for entry in evidence:
        dataset=entry['dataset']
        if dataset.startswith('hl_positions:'):
            position_evidence=True
            pairs=[('hl:'+r['position']['coin'],r['position']['szi']) for r in entry['body']['assetPositions']]
        elif dataset in {'kis_domestic_balance','kis_overseas_balance'}:
            position_evidence=True;domestic=dataset=='kis_domestic_balance'
            pairs=[('kis:'+r['pdno' if domestic else 'ovrs_pdno'],r['hldg_qty' if domestic else 'ovrs_cblc_qty'])
                   for r in entry['body']['output1']]
        else:continue
        for instrument,quantity in pairs:
            quantity=D(number(quantity))
            if instrument in native_positions and native_positions[instrument]!=quantity:
                raise ValueError('Conflicting captured inventory evidence')
            native_positions[instrument]=quantity
    positions={r['instrument']:D(number(r['quantity'])) for r in bundle['positions']}
    if position_evidence or positions or bundle['inventory_complete']:
        if not position_evidence or positions!=native_positions:
            raise ValueError('Adapter inventory differs from captured evidence')


def state_token(store, scopes):
    with store.connect() as db:
        state={}
        for table,column,order in [('accounts','id','id'),('fact_revisions','scope','id'),('dataset_coverage','scope','id')]:
            state[table]=[dict(r) for r in db.execute(
                f'SELECT * FROM {table} WHERE {column} IN ({",".join("?" for _ in scopes)}) ORDER BY {order}',scopes)]
    return digest(state)


def day_key(fact):
    p=fact['payload']
    if fact['dataset']=='trade' and p['time_precision']=='DAY':
        return (fact['scope'],p['instrument'],p['currency'],p['event_start_ms'],p['event_end_ms'],p['side'])
    return None


def funding_equivalent(old, fresh):
    """A different grain covers an old fact only with exact samples and cash sum."""
    p=old['payload'];day_ms=86400000;t=p['event_start_ms']//day_ms*day_ms
    peers=[r for r in fresh if r['dataset']=='cash' and r['scope']==old['scope']
           and r['payload']['instrument']==p['instrument'] and r['payload']['currency']==p['currency']
           and r['payload']['event_start_ms']//day_ms*day_ms==t]
    if p['grain']=='DAY':
        return (len(peers)==p.get('samples') and all(r['payload']['grain']=='POINT' for r in peers)
                and len({r['payload']['event_start_ms'] for r in peers})==len(peers)
                and sum((D(r['payload']['amount']) for r in peers),D(0))==D(p['amount']))
    return False


def fact_view(fact, identifier):
    p=fact['payload']
    return {**fact,'id':identifier,'instrument':p['instrument'],
            'event_start_ms':p['event_start_ms'],'event_end_ms':p['event_end_ms']}


def source_totals(facts):
    totals={}
    for row in facts:
        p=row['payload'];key=(row['scope'],p['currency'])
        t=totals.setdefault(key,{'scope':key[0],'currency':key[1],'trading_fees':D(0),
                                 'signed_funding':D(0),'cost_components':{},'unknown_components':set()})
        if row['dataset']=='cash':t['signed_funding']+=D(p['amount'])
        else:
            t['trading_fees']+=D(p['total_cost'])
            for name,value in p['costs'].items():
                if value is None:t['unknown_components'].add(name)
                else:t['cost_components'][name]=t['cost_components'].get(name,D(0))+D(value)
    return [{**t,'trading_fees':number(t['trading_fees']),'signed_funding':number(t['signed_funding']),
             'cost_components':{k:number(v) for k,v in t['cost_components'].items()},
             'unknown_components':sorted(t['unknown_components'])} for _,t in sorted(totals.items())]


def inventory_findings(facts,positions,complete):
    """Follow native inventory evidence; unknown openings remain explicit."""
    by_instrument=defaultdict(list);findings=[]
    for f in facts:
        if f['dataset']=='trade':by_instrument[f['payload']['instrument']].append(f['payload'])
    for instrument,rows in by_instrument.items():
        qty=None;pending=sorted(rows,key=lambda p:p['event_start_ms'])
        while pending:
            t=pending[0]['event_start_ms'];same=[p for p in pending if p['event_start_ms']==t]
            if qty is None:
                roots={D(p['position_before']) for p in same if p.get('position_before') is not None}
                ends={D(p['position_before'])+D(p['quantity'])*(1 if p['side']=='buy' else -1)
                      for p in same if p.get('position_before') is not None}
                roots-=ends
                # A closed same-timestamp cycle has no graph root. An explicit
                # zero position-before is still a valid starting anchor.
                if not roots and sum(p.get('position_before') is not None and D(p['position_before'])==0 for p in same)==1:
                    roots={D(0)}
                if len(roots)!=1:
                    native=any(p.get('position_before') is not None for p in same)
                    findings.append({'code':'ambiguous_inventory_anchor' if native else 'inventory_unanchored',
                                     'instrument':instrument,'severity':'blocker' if native else 'warning'})
                    if native:break
                    # Unknown opening history cannot establish quantity, but a
                    # later native anchor can still validate its own segment.
                    pending=[p for p in pending if p['event_start_ms']!=t]
                    continue
                qty=next(iter(roots))
                if qty!=0:findings.append({'code':'opening_inventory_partial','instrument':instrument,'severity':'warning'})
            candidates=[p for p in same if p.get('position_before') is not None and D(p['position_before'])==qty]
            if len(candidates)==1:p=candidates[0]
            elif len(same)==1 and same[0].get('position_before') is None:p=same[0]
            else:
                findings.append({'code':'inventory_discontinuity','instrument':instrument,'severity':'blocker'});break
            qty+=D(p['quantity'])*(1 if p['side']=='buy' else -1);pending.remove(p)
            if instrument.startswith('kis:') and qty<0:
                findings.append({'code':'negative_kis_inventory','instrument':instrument,'severity':'blocker'});break
            if p.get('day_end_quantity') is not None and not any(r['event_start_ms']==t for r in pending):
                if qty!=D(p['day_end_quantity']):
                    findings.append({'code':'day_end_inventory_mismatch','instrument':instrument,'severity':'blocker'})
        else:
            if complete and qty is not None and qty!=D(positions.get(instrument,'0')):
                findings.append({'code':'current_inventory_mismatch','instrument':instrument,'severity':'blocker'})
    if complete:
        for instrument,quantity in positions.items():
            if instrument not in by_instrument and D(quantity)!=0:
                findings.append({'code':'position_without_history','instrument':instrument,'severity':'blocker'})
    return findings


def _compare(store,bundles):
    if not bundles:raise ValueError('At least one account bundle required')
    fresh=[];accounts=[];scopes=[];ranges={};source_findings=[];positions={};inventory_complete={}
    for b in bundles:
        scope,rows,position=normalize_bundle(b)
        if scope in scopes:raise ValueError('Duplicate audit account')
        scopes.append(scope);accounts.append(b['account']);fresh.extend(rows)
        ranges[scope]=(b['start_ms'],b['end_ms']);positions[scope]=position;inventory_complete[scope]=b['inventory_complete']
        source_findings.extend({**f,'scope':scope} for f in b.get('findings',[]))
        if not b.get('evidence'):
            source_findings.append({'code':'operator_supplied_source','scope':scope,'severity':'warning'})
        if not b['collection_complete']:source_findings.append({'code':'collection_incomplete','scope':scope,'severity':'blocker'})
    old=[r for scope in scopes for r in store.facts(scope=scope,as_of_ms=2**63-1) if r['dataset'] in {'trade','cash'}]
    by_key={(r['scope'],r['dataset'],r['business_key']):r for r in old}
    days=defaultdict(list)
    for r in old:
        if day_key(r):days[day_key(r)].append(r)
    used=set();changes=[];unchanged=0;normalized=[]
    for row in fresh:
        ident=(row['scope'],row['dataset'],row['business_key']);previous=by_key.get(ident)
        matches=days.get(day_key(row),[]) if previous is None and day_key(row) else []
        if len(matches)>1:source_findings.append({'code':'ambiguous_daily_identity','scope':row['scope'],'severity':'blocker'})
        elif matches:previous=matches[0];row={**row,'business_key':previous['business_key']}
        if previous:
            if previous['id'] in used:raise ValueError('Multiple source rows map to one saved fact')
            used.add(previous['id'])
        normalized.append(row)
        if previous and previous['payload']==row['payload']:unchanged+=1
        else:changes.append({**row,'action':'correct' if previous else 'add','previous_digest':previous['digest'] if previous else None})
        if row['dataset']=='trade':
            source_findings.extend({'code':reason,'scope':row['scope'],'instrument':row['payload']['instrument'],'severity':'blocker'} for reason in cost_quality(row['payload']))
    missing=[];equivalent=[]
    for row in old:
        a,b=ranges[row['scope']];p=row['payload']
        if row['id'] in used or not a<=p['event_start_ms']<b:continue
        equivalent_cash=False
        if row['dataset']=='cash':
            equivalent_cash=funding_equivalent(row,normalized)
            if p['grain']=='POINT':
                # Match a new daily aggregate to the entire saved point population.
                for daily in normalized:
                    if daily['dataset']=='cash' and daily['scope']==row['scope'] and daily['payload']['grain']=='DAY' and daily['payload']['instrument']==p['instrument'] and daily['payload']['event_start_ms']<=p['event_start_ms']<daily['payload']['event_end_ms']:
                        equivalent_cash=funding_equivalent(daily,old)
                        if equivalent_cash:break
        if equivalent_cash:equivalent.append({'scope':row['scope'],'dataset':row['dataset'],'business_key':row['business_key']})
        else:missing.append({'scope':row['scope'],'dataset':row['dataset'],'business_key':row['business_key']})
    if missing:source_findings.append({'code':'saved_records_absent_from_source','severity':'blocker','count':len(missing)})
    merged={(r['scope'],r['dataset'],r['business_key']):r for r in old}
    for r in normalized:merged[(r['scope'],r['dataset'],r['business_key'])]=r
    views=[fact_view(r,i+1) for i,r in enumerate(merged.values())]
    cash_intervals=set()
    for r in views:
        if r['dataset']!='cash':continue
        p=r['payload'];identity=(r['scope'],p['instrument'],p['currency'],p['event_start_ms'],p['event_end_ms'],p['grain'])
        if identity in cash_intervals:
            source_findings.append({'code':'duplicate_funding_interval','scope':r['scope'],'instrument':p['instrument'],'severity':'blocker'})
        cash_intervals.add(identity)
    _,funding_issues=effective_funding([r for r in views if r['dataset']=='cash'])
    source_findings.extend({**f,'code':f['kind'],'severity':'blocker'} for f in funding_issues)
    for scope,bundle in zip(scopes,bundles):
        # Bounded polling can contain funding but no fills for an existing
        # position. Carry forward recorded inventory rather than inventing zero.
        relevant=[r for r in merged.values() if r['scope']==scope and r['payload']['event_start_ms']<bundle['end_ms']]
        complete=inventory_complete[scope]
        if bundle['account']['venue']=='kis':
            observed=bundle.get('inventory_observed_ms');requested=bundle.get('requested_end_ms')
            markets=bundle.get('inventory_scope',{}).get('markets',[])
            # KIS native sources here cover domestic/US shares only. Check that
            # explicit population without asserting other overseas holdings are zero.
            complete=(type(observed) is int and type(requested) is int and 0<=observed-requested<=60000
                      and set(markets)=={'domestic','NASD','NYSE','AMEX'})
        source_findings.extend({**f,'scope':scope} for f in inventory_findings(relevant,positions[scope],complete))
    return {'schema_version':1,'kind':'account-audit-report','database':str(store.path),'baseline':state_token(store,scopes),
            'bundles':bundles,'bundle_digests':[digest(b) for b in bundles],'accounts':accounts,'scopes':scopes,
            'changes':changes,'unchanged':unchanged,'missing':missing,'funding_equivalent':equivalent,
            'source_totals':source_totals(normalized),
            'findings':source_findings,'blockers':[f for f in source_findings if f.get('severity')=='blocker'],
            'coverage_certified':False}


def compare_bundles(store,bundles):
    with read_snapshot(store):return _compare(store,bundles)


def apply_report(store,path,sha256,*,allow_corrections=False,journals=False):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha256:raise ValueError('Audit report digest mismatch')
    report=json.loads(raw);reject_secrets(report)
    if report.get('schema_version')!=1 or report.get('kind')!='account-audit-report':raise ValueError('Unsupported audit report')
    if str(store.path)!=report['database']:raise ValueError('Audit report targets a different database')
    job='account-audit:'+sha256
    with store.atomic():
        with store.connect() as db:
            previous=db.execute("SELECT details FROM collection_runs WHERE job_id=? AND status='success' ORDER BY id DESC LIMIT 1",(job,)).fetchone()
        if previous:
            result=json.loads(previous['details'])
            if result['journals_requested']!=journals:
                raise ValueError('Replayed audit has different journal options; use data journal separately')
            return {**result,'already_applied':True}
        current=_compare(store,report['bundles'])
        if current['baseline']!=report['baseline']:raise ValueError('Database changed; audit report is stale')
        if current!=report:raise ValueError('Audit report plan does not match source reconstruction')
        if current['blockers']:raise ValueError('Audit has unresolved findings; no changes applied')
        if any(c['action']=='correct' for c in current['changes']) and not allow_corrections:
            raise ValueError('Existing fact corrections require --allow-corrections')
        observations={}
        for scope,b in zip(current['scopes'],current['bundles']):
            a=b['account'];store.account(a['venue'],a['environment'],a['native_id'],label=a.get('label',''))
            observations[scope]=store.observe('account_audit_bundle',scope,encode(b).encode(),capture_format='decoded_json',metadata={'report_sha256':sha256})
            for evidence in b.get('evidence',[]):
                body=evidence['raw'].encode() if 'raw' in evidence else encode(evidence['body']).encode()
                store.observe(evidence['dataset'],scope,body,capture_format='http_json' if 'raw' in evidence else 'decoded_json',metadata={'audit_bundle_observation':observations[scope]})
        fact_ids=[]
        for c in current['changes']:
            fact_ids.append(store.fact(c['dataset'],c['scope'],c['business_key'],c['payload'],observation=observations[c['scope']],allow_correction=c['action']=='correct'))
        for scope,b in zip(current['scopes'],current['bundles']):
            for dataset in ['trade','cash'] if b['account']['venue']=='hyperliquid' else ['trade']:
                store.coverage(dataset,scope,b['start_ms'],b['end_ms'],'partial',{'source':'account-audit','report_sha256':sha256,'reason':'API comparison does not certify independent statement completeness'})
        runs=[]
        if journals:
            from kis_hl.journal_exports import journal
            groups=[[a] for a in current['scopes']]
            if len(current['scopes'])>1:groups.append(current['scopes'])
            for group in groups:runs.append(journal(store,group)['report_id'])
        result={'applied':True,'already_applied':False,'accounts':current['scopes'],'fact_ids':fact_ids,'journal_ids':runs,'journals_requested':journals,'report_sha256':sha256,'coverage_certified':False}
        with store.connect() as db:
            t=now_ms();db.execute("INSERT INTO collection_runs(job_id,started_ms,finished_ms,status,details) VALUES(?,?,?,'success',?)",(job,t,t,encode(result)))
        return result
