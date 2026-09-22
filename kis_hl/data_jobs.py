"""Local configurable polling jobs with attempt/success clocks and process locking."""
import json
from kis_hl.data_store import encode, now_ms
from kis_hl.execution_lock import account_lock


def configure(store, job_id, config, interval_seconds=10800):
    if not job_id or type(interval_seconds) is not int or interval_seconds<=0:raise ValueError('Positive job interval required')
    if config.get('kind') not in {'account','bar','book','quote','funding'}:raise ValueError('Unknown collection kind')
    with store.connect() as db:
        db.execute('INSERT INTO ingestion_jobs(id,config,interval_seconds,next_due_ms) VALUES(?,?,?,0) ON CONFLICT(id) DO UPDATE SET config=excluded.config,interval_seconds=excluded.interval_seconds',
                   (job_id,encode(config),interval_seconds))
    return {'job_id':job_id,'interval_seconds':interval_seconds}


def run_due(store, execute, *, clock=None):
    timestamp=now_ms() if clock is None else clock
    outcomes=[]
    # The lock covers network time, but SQLite transactions never do.
    with account_lock('data-jobs',str(store.path)):
        with store.connect() as db:
            # A dedicated row records liveness even when no jobs are due.
            heartbeat=db.execute("SELECT id FROM collection_runs WHERE job_id='worker-heartbeat' ORDER BY id DESC LIMIT 1").fetchone()
            if heartbeat:
                db.execute('UPDATE collection_runs SET finished_ms=? WHERE id=?',(timestamp,heartbeat[0]))
            else:
                db.execute("INSERT INTO collection_runs(job_id,started_ms,finished_ms,status,details) VALUES('worker-heartbeat',?,?, 'heartbeat','{}')",(timestamp,timestamp))
        with store.connect() as db:jobs=[dict(r) for r in db.execute('SELECT * FROM ingestion_jobs WHERE next_due_ms<=? ORDER BY id',(timestamp,))]
        for job in jobs:
            with store.connect() as db:
                db.execute('UPDATE ingestion_jobs SET last_attempt_ms=?,next_due_ms=? WHERE id=?',(timestamp,timestamp+job['interval_seconds']*1000,job['id']))
                run=db.execute("INSERT INTO collection_runs(job_id,started_ms,status,details) VALUES(?,?,'running','{}')",(job['id'],timestamp)).lastrowid
            try:
                config=json.loads(job['config'])
                config['_last_success_ms']=job['last_success_ms']
                result=execute(config)
                status='partial' if result.get('collection_complete') is False else 'success'
                reason='Unresolved collection evidence' if status=='partial' else ''
            except Exception as exc:
                result={'error_type':type(exc).__name__};status='failed';reason=type(exc).__name__
            with store.connect() as db:
                db.execute('UPDATE collection_runs SET finished_ms=?,status=?,details=? WHERE id=?',(now_ms(),status,encode(result),run))
                db.execute('UPDATE ingestion_jobs SET last_success_ms=CASE WHEN ? THEN ? ELSE last_success_ms END,last_reason=? WHERE id=?',(status=='success',timestamp,reason,job['id']))
            outcomes.append({'job_id':job['id'],'status':status,'result':result})
    return {'jobs':outcomes}
