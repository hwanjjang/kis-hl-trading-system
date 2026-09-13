"""Digest-bound source manifests; derived reports never count as raw trades."""
import hashlib
import json
from pathlib import Path
import sqlite3
from kis_hl.journal_sync import Scope
from kis_hl.data_ingestion import ingest_rows, PARSERS, domestic_bundle
from kis_hl.data_store import encode, now_ms, reject_secrets


def import_manifest(store, path, *, apply=False, existing_path=None):
    path=Path(path).resolve();raw=path.read_bytes();manifest=json.loads(raw)
    reject_secrets(manifest)
    if manifest.get('schema_version')!=1:raise ValueError('Unsupported import manifest version')
    accounts={a['alias']:a for a in manifest['accounts']}
    if len(accounts)!=len(manifest['accounts']):raise ValueError('Duplicate account alias')
    scope_ids={alias:Scope(a['venue'],a['environment'],a['native_id']).key for alias,a in accounts.items()}
    for coverage in manifest.get('coverage',[]):
        start,end=coverage.get('start_ms'),coverage.get('end_ms')
        if coverage.get('account') not in accounts or coverage.get('dataset') not in {'trade','cash','position','balance'}:
            raise ValueError('Invalid coverage account/dataset')
        if type(start) is not int or type(end) is not int or not 0<=start<end or coverage.get('status') not in {'complete','partial','unknown','failed'}:
            raise ValueError('Invalid coverage interval/status')
        if not isinstance(coverage.get('details',{}),dict):raise ValueError('Coverage details must be an object')
    known={}
    db_path=store.path if store is not None else Path(existing_path).resolve() if existing_path else None
    if db_path is not None and db_path.exists():
        db=sqlite3.connect(db_path.as_uri()+'?mode=ro',uri=True)
        try:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='fact_revisions'").fetchone():
                for dataset,scope,key,body in db.execute('SELECT dataset,scope,business_key,payload FROM fact_revisions ORDER BY revision'):
                    known[(dataset,scope,key)]=body
        finally:db.close()
    loaded=[]
    for entry in manifest['files']:
        p=(path.parent/entry['path']).resolve()
        if not p.is_relative_to(path.parent):raise ValueError('Manifest source escapes its directory')
        body=p.read_bytes()
        if hashlib.sha256(body).hexdigest()!=entry['sha256']:raise ValueError('Source digest mismatch')
        if entry['role'] not in {'raw','baseline'}:raise ValueError('Explicit raw/baseline role required')
        if entry['role']=='raw':
            if entry['account'] not in accounts or entry['parser'] not in {*PARSERS,'evidence','kis_domestic_bundle'}:raise ValueError('Unknown account/parser')
            obj=json.loads(body);reject_secrets(obj)
            rows=domestic_bundle(obj) if entry['parser']=='kis_domestic_bundle' else obj if isinstance(obj,list) else obj.get(entry.get('rows_key','output1'),[])
            if entry['parser']!='evidence' and not isinstance(rows,list):raise ValueError('Invalid source rows')
            if entry['parser']!='evidence':
                parser='statement' if entry['parser']=='kis_domestic_bundle' else entry['parser']
                for row in rows:
                    dataset,key,payload=PARSERS[parser](row)
                    identity=(dataset,scope_ids[entry['account']],key);normalized=encode(payload)
                    if identity in known and known[identity]!=normalized and not entry.get('allow_correction',False):
                        raise ValueError('Manifest contains a conflicting fact; explicit correction required')
                    known[identity]=normalized
            loaded.append((entry,body,rows))
    result={'raw_files':len(loaded),'baseline_files':len(manifest['files'])-len(loaded),'applied':apply,'fact_ids':[]}
    if not apply:return result
    ids={alias:store.account(a['venue'],a['environment'],a['native_id'],label=a.get('label',alias),parent_id=a.get('parent_id')) for alias,a in accounts.items()}
    with store.connect() as db:
        run=db.execute("INSERT INTO collection_runs(job_id,started_ms,status,details) VALUES(?,?,'running',?)",('import:'+hashlib.sha256(raw).hexdigest(),now_ms(),encode({'files':len(loaded)}))).lastrowid
    try:
        for entry,body,rows in loaded:
            account=ids[entry['account']]
            observation=store.observe(entry['parser'],account,body,metadata={'manifest_sha256':hashlib.sha256(raw).hexdigest(),'source_path':entry['path']})
            if entry['parser']!='evidence':
                parser='statement' if entry['parser']=='kis_domestic_bundle' else entry['parser']
                result['fact_ids'].extend(ingest_rows(store,account,parser,rows,observation=observation,allow_correction=entry.get('allow_correction',False)))
        for coverage in manifest.get('coverage',[]):
            store.coverage(coverage['dataset'],ids[coverage['account']],coverage['start_ms'],coverage['end_ms'],coverage['status'],coverage.get('details',{}))
        with store.connect() as db:
            db.execute('INSERT OR IGNORE INTO import_manifests VALUES(?,?,?)',(hashlib.sha256(raw).hexdigest(),encode(manifest),now_ms()))
            db.execute("UPDATE collection_runs SET finished_ms=?,status='success',details=? WHERE id=?",(now_ms(),encode({'fact_count':len(set(result['fact_ids']))}),run))
    except BaseException as exc:
        with store.connect() as db:db.execute("UPDATE collection_runs SET finished_ms=?,status='failed',details=? WHERE id=?",(now_ms(),encode({'error_type':type(exc).__name__,'persisted_fact_ids':result['fact_ids']}),run))
        raise
    result['fact_ids']=sorted(set(result['fact_ids']))
    return result
