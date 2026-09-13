"""Additive canonical-data schema; existing execution tables are untouched."""
import hashlib

DDL = [
    "CREATE TABLE accounts(id TEXT PRIMARY KEY, venue TEXT NOT NULL, environment TEXT NOT NULL, native_id TEXT NOT NULL, label TEXT NOT NULL, parent_id TEXT REFERENCES accounts(id), UNIQUE(venue,environment,native_id))",
    "CREATE TABLE data_instruments(id TEXT PRIMARY KEY, payload TEXT NOT NULL)",
    "CREATE TABLE raw_payloads(id TEXT PRIMARY KEY, body BLOB NOT NULL, codec TEXT NOT NULL, byte_length INTEGER NOT NULL, capture_format TEXT NOT NULL)",
    "CREATE TABLE source_observations(id INTEGER PRIMARY KEY, payload_id TEXT NOT NULL REFERENCES raw_payloads(id), dataset TEXT NOT NULL, scope TEXT NOT NULL, received_ms INTEGER NOT NULL, metadata TEXT NOT NULL)",
    "CREATE TABLE fact_revisions(id INTEGER PRIMARY KEY, dataset TEXT NOT NULL, scope TEXT NOT NULL, business_key TEXT NOT NULL, revision INTEGER NOT NULL, instrument TEXT NOT NULL, event_start_ms INTEGER NOT NULL, event_end_ms INTEGER NOT NULL, known_ms INTEGER NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL, supersedes INTEGER REFERENCES fact_revisions(id), UNIQUE(dataset,scope,business_key,revision), CHECK(event_end_ms>=event_start_ms))",
    "CREATE TABLE fact_sources(fact_id INTEGER REFERENCES fact_revisions(id), observation_id INTEGER REFERENCES source_observations(id), locator TEXT NOT NULL, PRIMARY KEY(fact_id,observation_id,locator))",
    "CREATE INDEX facts_query ON fact_revisions(dataset,scope,instrument,event_start_ms,known_ms)",
    "CREATE TABLE dataset_coverage(id INTEGER PRIMARY KEY, dataset TEXT NOT NULL, scope TEXT NOT NULL, requested_start_ms INTEGER NOT NULL, requested_end_ms INTEGER NOT NULL, status TEXT NOT NULL, details TEXT NOT NULL, observed_ms INTEGER NOT NULL)",
    "CREATE TABLE analysis_runs(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, created_ms INTEGER NOT NULL, as_of_ms INTEGER NOT NULL, parameters TEXT NOT NULL, result TEXT NOT NULL)",
    "CREATE TABLE analysis_inputs(run_id INTEGER REFERENCES analysis_runs(id), fact_id INTEGER REFERENCES fact_revisions(id), PRIMARY KEY(run_id,fact_id))",
    "CREATE TABLE report_artifacts(id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES analysis_runs(id), path TEXT NOT NULL, status TEXT NOT NULL, digest TEXT)",
    "CREATE TABLE import_manifests(id TEXT PRIMARY KEY, body TEXT NOT NULL, applied_ms INTEGER NOT NULL)",
    "CREATE TABLE ingestion_jobs(id TEXT PRIMARY KEY, config TEXT NOT NULL, interval_seconds INTEGER NOT NULL CHECK(interval_seconds>0), next_due_ms INTEGER NOT NULL, last_attempt_ms INTEGER, last_success_ms INTEGER, lease_until_ms INTEGER, last_reason TEXT NOT NULL DEFAULT '')",
    "CREATE TABLE collection_runs(id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, started_ms INTEGER NOT NULL, finished_ms INTEGER, status TEXT NOT NULL, details TEXT NOT NULL)",
]


def migrate(db):
    db.execute('BEGIN IMMEDIATE')
    db.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, checksum TEXT NOT NULL, applied_at INTEGER NOT NULL)')
    checksum = hashlib.sha256('\n'.join(DDL).encode()).hexdigest()
    rows = db.execute('SELECT version,checksum FROM schema_migrations').fetchall()
    if any(r[0] != 1 or r[1] != checksum for r in rows):
        raise ValueError('Unsupported or changed canonical schema migration')
    if not rows:
        for statement in DDL:
            db.execute(statement)
        db.execute("INSERT INTO schema_migrations VALUES(1,?,CAST(strftime('%s','now') AS INTEGER)*1000)", (checksum,))
    db.commit()
