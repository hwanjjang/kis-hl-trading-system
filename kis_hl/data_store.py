"""Local immutable evidence, revisioned facts and reproducible input manifests."""
from contextlib import contextmanager
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import zlib

from kis_hl.data_migrations import migrate
from kis_hl.instruments import INSTRUMENTS
from kis_hl.journal_sync import Scope


def now_ms():
    return time.time_ns() // 1_000_000


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def number(value):
    if isinstance(value, (float, bool)):
        raise ValueError('Financial values must be decimal strings, not float/bool')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('Invalid decimal') from None
    if not result.is_finite():
        raise ValueError('Nonfinite financial value')
    return format(result, 'f') if result else '0'


def reject_secrets(value):
    """Reject credential-bearing structures rather than silently altering raw evidence."""
    forbidden = {'authorization', 'appkey', 'appsecret', 'access_token', 'refresh_token',
                 'privatekey', 'private_key', 'approval_key', 'secretkey'}
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in forbidden:
                raise ValueError('Credential-bearing payload is not a data source')
            reject_secrets(item)
    elif isinstance(value, list):
        for item in value:
            reject_secrets(item)


class DataStore:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            mode = db.execute('PRAGMA journal_mode=WAL').fetchone()[0]
            if mode != 'wal':
                raise RuntimeError('Canonical store requires local WAL support')
            migrate(db)
            for item in INSTRUMENTS:
                db.execute('INSERT OR IGNORE INTO data_instruments VALUES(?,?)', (item.id, encode(asdict(item))))
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def account(self, venue, environment, native_id, *, label='', parent_id=None):
        scope = Scope(venue, environment, native_id)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO accounts VALUES(?,?,?,?,?,?)',
                       (scope.key, venue, environment, native_id.lower(), label or venue, parent_id))
            row = db.execute('SELECT * FROM accounts WHERE id=?', (scope.key,)).fetchone()
            if parent_id and row['parent_id'] != parent_id:
                raise ValueError('Account parent mismatch')
        return scope.key

    def observe(self, dataset, scope, body, *, capture_format='legacy_json', metadata=None, received_ms=None):
        if not isinstance(body, bytes):
            raise ValueError('Raw evidence must be bytes')
        parsed = json.loads(body)
        reject_secrets(parsed)
        reject_secrets(metadata or {})
        digest = hashlib.sha256(body).hexdigest()
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO raw_payloads VALUES(?,?,?,?,?)',
                       (digest, zlib.compress(body), 'zlib', len(body), capture_format))
            cursor = db.execute('INSERT INTO source_observations(payload_id,dataset,scope,received_ms,metadata) VALUES(?,?,?,?,?)',
                                (digest, dataset, scope, now_ms() if received_ms is None else received_ms, encode(metadata or {})))
            return cursor.lastrowid

    def fact(self, dataset, scope, key, payload, *, observation, locator='', known_ms=None, allow_correction=False):
        start, end = payload['event_start_ms'], payload['event_end_ms']
        if type(start) is not int or type(end) is not int or not 0 <= start <= end:
            raise ValueError('Invalid fact interval')
        reject_secrets(payload)
        body = encode(payload)
        digest = hashlib.sha256(body.encode()).hexdigest()
        known = now_ms() if known_ms is None else known_ms
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            source = db.execute('SELECT scope FROM source_observations WHERE id=?', (observation,)).fetchone()
            if source is None or source['scope'] != scope:
                raise ValueError('Fact source scope mismatch')
            old = db.execute('SELECT * FROM fact_revisions WHERE dataset=? AND scope=? AND business_key=? ORDER BY revision DESC LIMIT 1', (dataset, scope, key)).fetchone()
            if old and old['digest'] == digest:
                fact_id = old['id']
            else:
                if old and not allow_correction:
                    raise ValueError('Conflicting fact requires explicit correction')
                if old and known < old['known_ms']:
                    raise ValueError('Correction knowledge time cannot move backwards')
                cursor = db.execute('INSERT INTO fact_revisions(dataset,scope,business_key,revision,instrument,event_start_ms,event_end_ms,known_ms,payload,digest,supersedes) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (dataset, scope, key, old['revision']+1 if old else 1, payload.get('instrument',''), start, end, known, body, digest, old['id'] if old else None))
                fact_id = cursor.lastrowid
            db.execute('INSERT OR IGNORE INTO fact_sources VALUES(?,?,?)', (fact_id, observation, str(locator)))
            return fact_id

    def facts(self, dataset=None, *, scope=None, as_of_ms=None):
        clauses = ['known_ms<=?'];values = [now_ms() if as_of_ms is None else as_of_ms]
        if dataset:
            clauses.append('dataset=?');values.append(dataset)
        if scope:
            clauses.append('scope=?');values.append(scope)
        with self.connect() as db:
            rows = db.execute('SELECT * FROM (SELECT *,row_number() OVER(PARTITION BY dataset,scope,business_key ORDER BY revision DESC) n FROM fact_revisions WHERE '+ ' AND '.join(clauses)+') WHERE n=1 ORDER BY event_start_ms,id', values).fetchall()
        return [{**dict(r), 'payload':json.loads(r['payload'])} for r in rows]

    def coverage(self, dataset, scope, start, end, status, details):
        if not 0 <= start <= end or status not in {'complete','partial','unknown','failed'}:
            raise ValueError('Invalid coverage')
        with self.connect() as db:
            db.execute('INSERT INTO dataset_coverage(dataset,scope,requested_start_ms,requested_end_ms,status,details,observed_ms) VALUES(?,?,?,?,?,?,?)',
                       (dataset,scope,start,end,status,encode(details),now_ms()))

    def pin(self, kind, parameters, inputs, result, *, as_of_ms=None):
        asof = now_ms() if as_of_ms is None else as_of_ms
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            pending=list(set(inputs)); pinned=set()
            while pending:
                fact_id=pending.pop()
                if fact_id in pinned:continue
                row = db.execute('SELECT known_ms,payload FROM fact_revisions WHERE id=?', (fact_id,)).fetchone()
                if row is None or row[0] > asof:
                    raise ValueError('Analysis input unknown at as-of time')
                pinned.add(fact_id)
                pending.extend(json.loads(row['payload']).get('input_ids',[]))
            run = db.execute('INSERT INTO analysis_runs(kind,created_ms,as_of_ms,parameters,result) VALUES(?,?,?,?,?)',
                             (kind,now_ms(),asof,encode(parameters),encode(result))).lastrowid
            db.executemany('INSERT INTO analysis_inputs VALUES(?,?)', [(run,i) for i in pinned])
            return run

    def status(self):
        with self.connect() as db:
            counts = {r['dataset']:r['n'] for r in db.execute('SELECT dataset,count(*) n FROM fact_revisions GROUP BY dataset')}
            dependencies = {r['id']: json.loads(r['payload']).get('input_ids', []) for r in db.execute('SELECT id,payload FROM fact_revisions')}
            stale = {r[0] for r in db.execute('SELECT supersedes FROM fact_revisions WHERE supersedes IS NOT NULL')}
            while True:
                derived = {key for key, inputs in dependencies.items() if stale.intersection(inputs)}
                if derived <= stale: break
                stale.update(derived)
            stale_runs = sorted({r['run_id'] for r in db.execute('SELECT run_id,fact_id FROM analysis_inputs') if r['fact_id'] in stale})
            return {'path':str(self.path), 'schema_version':1, 'revision_counts':counts,
                    'accounts':[dict(r) for r in db.execute('SELECT id,venue,environment,label,parent_id FROM accounts')],
                    'coverage':[{**dict(r),'details':json.loads(r['details'])} for r in db.execute('SELECT * FROM dataset_coverage ORDER BY id DESC LIMIT 100')],
                    'jobs':[dict(r) for r in db.execute('SELECT id,interval_seconds,next_due_ms,last_attempt_ms,last_success_ms,last_reason FROM ingestion_jobs')],
                    'stale_runs':stale_runs,
                    'bytes':self.path.stat().st_size}
