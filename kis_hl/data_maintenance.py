"""Consistent online backup and isolated restore; retention is preview-only."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from kis_hl.data_store import now_ms


def backup(store, target):
    target=Path(target).expanduser().resolve()
    if target.exists() or target==store.path:raise ValueError('Backup target must be a new file')
    target.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    try:
        with store.connect() as source:
            destination=sqlite3.connect(target)
            try:
                source.backup(destination,pages=128)
                check=destination.execute('PRAGMA integrity_check').fetchone()[0]
                if check!='ok' or destination.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Backup integrity failure')
                destination.execute('PRAGMA journal_mode=DELETE')
            finally:destination.close()
        receipt={'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'created_ms':now_ms(),'integrity':'ok','schema_version':1}
        sidecar=target.with_suffix(target.suffix+'.json');sidecar.write_text(json.dumps(receipt,indent=2));os.chmod(sidecar,0o600)
        return {'path':str(target),**receipt}
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def restore(source,target):
    source=Path(source).resolve();target=Path(target).resolve()
    if target.exists() or any(Path(str(target)+suffix).exists() for suffix in ['-wal','-shm']):raise ValueError('Restore requires a new isolated target')
    receipt=json.loads(source.with_suffix(source.suffix+'.json').read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest()!=receipt['sha256']:raise ValueError('Backup digest mismatch')
    target.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    try:
        src=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);dest=sqlite3.connect(target)
        try:
            src.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or dest.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Restore integrity failure')
        finally:src.close();dest.close()
    except BaseException:
        target.unlink(missing_ok=True);raise
    return {'path':str(target),'integrity':'ok','active_database_replaced':False}


def retention_preview(store, *, snapshot_days=30, minute_days=180):
    if min(snapshot_days,minute_days)<=0:raise ValueError('Retention days must be positive')
    with store.connect() as db:
        pinned={r[0] for r in db.execute('SELECT fact_id FROM analysis_inputs')}
        # Recursive derived dependencies are pinned by their manifests too.
        facts=[dict(r) for r in db.execute('SELECT id,dataset,event_end_ms,payload FROM fact_revisions')]
        changed=True
        while changed:
            before=len(pinned)
            for row in facts:
                if row['id'] in pinned:pinned.update(json.loads(row['payload']).get('input_ids',[]))
            changed=len(pinned)!=before
        counts={}
        for row in facts:
            p=json.loads(row['payload'])
            days=minute_days if row['dataset']=='bar' and p.get('timeframe')=='1m' else snapshot_days if row['dataset'] in {'book','quote'} else None
            if days and row['event_end_ms']<now_ms()-days*86400000 and row['id'] not in pinned:
                counts[row['dataset']]=counts.get(row['dataset'],0)+1
    return {'preview_only':True,'deletion_enabled':False,'candidate_revisions':counts,'pinned_revision_count':len(pinned)}
