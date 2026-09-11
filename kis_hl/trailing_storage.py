"""Transactional trailing state. The JSON snapshot and exit decision commit together."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from kis_hl.logging_utils import get_logger

logger = get_logger(__name__)


class TrailStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS trailing_positions (
                    id TEXT PRIMARY KEY, network TEXT NOT NULL, account TEXT NOT NULL,
                    coin TEXT NOT NULL, mode TEXT NOT NULL CHECK(mode IN ('live','paper')),
                    state TEXT NOT NULL, version INTEGER NOT NULL, snapshot TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS trailing_active_position
                    ON trailing_positions(network, account, coin, mode) WHERE state NOT IN ('CLOSED','PAPER_EXIT');
                CREATE TABLE IF NOT EXISTS trailing_exit_intents (
                    position_id TEXT PRIMARY KEY, reason TEXT NOT NULL, created_ms INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS trailing_exit_attempts (
                    id INTEGER PRIMARY KEY, position_id TEXT NOT NULL, cloid TEXT NOT NULL UNIQUE,
                    size TEXT NOT NULL, limit_price TEXT NOT NULL, status TEXT NOT NULL,
                    created_ms INTEGER NOT NULL, response TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS trailing_events (
                    id INTEGER PRIMARY KEY, position_id TEXT NOT NULL, time_ms INTEGER NOT NULL,
                    cause TEXT NOT NULL, snapshot TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def enroll(self, values: dict) -> dict:
        row = {**values, 'id': uuid4().hex, 'version': 0}
        with self.connect() as db:
            try:
                db.execute('INSERT INTO trailing_positions VALUES (?,?,?,?,?,?,?,?)',
                           (row['id'], row['network'], row['account'], row['coin'], row['mode'],
                            row['state'], 0, json.dumps(row)))
            except sqlite3.IntegrityError as exc:
                raise RuntimeError('Position is already managed; resume its existing generation') from exc
        return row

    def get(self, position_id: str) -> dict:
        with self.connect() as db:
            r = db.execute('SELECT snapshot FROM trailing_positions WHERE id=?', (position_id,)).fetchone()
        if r is None:
            raise ValueError('Unknown trailing position ID')
        return json.loads(r[0])

    def list(self) -> list[dict]:
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT snapshot FROM trailing_positions ORDER BY rowid')]

    def _save(self, db, row: dict, cause: str):
        new = {**row, 'version': row['version'] + 1}
        updated = db.execute('UPDATE trailing_positions SET state=?, version=?, snapshot=? WHERE id=? AND version=?',
                             (new['state'], new['version'], json.dumps(new), row['id'], row['version']))
        if updated.rowcount != 1:
            raise RuntimeError('Trailing state changed; reload before writing')
        db.execute('INSERT INTO trailing_events(position_id,time_ms,cause,snapshot) VALUES (?,?,?,?)',
                   (row['id'], int(time.time()*1000), cause, json.dumps(new)))
        return new

    def save(self, row: dict, cause: str):
        with self.connect() as db:
            new = self._save(db, row, cause)
        row.update(new)
        logger.info('trailing_state_saved', extra={'position_id': row['id'], 'state': row['state'],
                                                 'cause': cause, 'action': 'persist', 'result': 'committed'})

    def decide_exit(self, row: dict, *, now_ms: int, reason: str = 'trailing'):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO trailing_exit_intents VALUES (?,?,?)', (row['id'], reason, now_ms))
            new = self._save(db, {**row, 'state': 'EXIT_PENDING'}, reason)
        row.update(new)
        logger.info('trailing_exit_intent', extra={'position_id': row['id'], 'cause': reason,
                                                 'action': 'persist_exit', 'result': 'committed'})

    def intent(self, position_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM trailing_exit_intents WHERE position_id=?', (position_id,)).fetchone()
            return dict(row) if row else None

    def attempts(self, position_id):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM trailing_exit_attempts WHERE position_id=? ORDER BY id', (position_id,))]

    def prepare_attempt(self, position_id, *, size, limit, now_ms):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM trailing_exit_attempts WHERE position_id=? AND status NOT IN ('TERMINAL','REJECTED')", (position_id,)).fetchone():
                raise RuntimeError('An unresolved attempt blocks resubmission')
            if not db.execute('SELECT 1 FROM trailing_exit_intents WHERE position_id=?', (position_id,)).fetchone():
                raise RuntimeError('A durable exit intent is required before an attempt')
            cloid = '0x' + uuid4().hex
            cur = db.execute("INSERT INTO trailing_exit_attempts(position_id,cloid,size,limit_price,status,created_ms) VALUES (?,?,?,?,'UNKNOWN',?)",
                             (position_id, cloid, size, limit, now_ms))
            row = dict(db.execute('SELECT * FROM trailing_exit_attempts WHERE id=?', (cur.lastrowid,)).fetchone())
        return row

    def finish_attempt(self, attempt_id, *, status: str, response):
        with self.connect() as db:
            db.execute('UPDATE trailing_exit_attempts SET status=?,response=? WHERE id=?',
                       (status, json.dumps(response, default=str), attempt_id))


def has_managed_position(path, *, network, account, coin):
    if not path or not Path(path).exists():
        return False
    db = sqlite3.connect(path)
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='trailing_positions'").fetchone():
            return False
        return db.execute("SELECT 1 FROM trailing_positions WHERE network=? AND account=? AND coin=? AND mode='live' AND state!='CLOSED'",
                          (network.rstrip('/'), account.lower(), coin)).fetchone() is not None
    finally:
        db.close()
