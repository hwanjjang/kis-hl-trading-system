"""Append-only decision notes linked to position activity and strategy decisions.

Notes capture who thought what, when, and why (AK, the agent, the Jev model or
another source) so the next decision can review earlier reasoning next to the
actual executions. They are advisory records: they never authorize, size or
change orders, and they never edit trade facts or statistics.
"""
from decimal import Decimal

from kis_hl.data_store import encode, now_ms

POLICY_VERSION = 'decision-note-v1'
AUTHORS = {'ak', 'agent', 'jev', 'other'}
PHASES = {'pre_trade', 'entry', 'add', 'hold', 'reduce', 'exit', 'post_trade', 'review'}
STANCES = {'long', 'add', 'hold', 'reduce', 'exit', 'wait', 'avoid', 'short', 'neutral'}
MAX_TEXT = 4000


def _text(value, name, *, limit=MAX_TEXT, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{name} must be non-empty text of at most {limit} characters')
    return value.strip()


def validate_note(note, *, recorded_ms=None):
    if not isinstance(note, dict):
        raise ValueError('A note must be a JSON object')
    unknown = set(note) - {'account', 'instrument', 'author', 'phase', 'stance', 'text',
                           'observed_ms', 'journal_id', 'fact_id', 'decision_id', 'context',
                           'supersedes_note_id', 'jev'}
    if unknown:
        raise ValueError(f'Unknown note fields: {sorted(unknown)}')
    recorded = now_ms() if recorded_ms is None else recorded_ms
    author = note.get('author')
    if author not in AUTHORS:
        raise ValueError(f'author must be one of {sorted(AUTHORS)}')
    phase = note.get('phase')
    if phase not in PHASES:
        raise ValueError(f'phase must be one of {sorted(PHASES)}')
    stance = note.get('stance')
    if stance is not None and stance not in STANCES:
        raise ValueError(f'stance must be one of {sorted(STANCES)}')
    observed = note.get('observed_ms', recorded)
    if type(observed) is not int or not 0 < observed <= recorded:
        raise ValueError('observed_ms must be a positive past UTC millisecond timestamp')
    for key in ('journal_id', 'fact_id', 'supersedes_note_id'):
        if note.get(key) is not None and (type(note[key]) is not int or note[key] <= 0):
            raise ValueError(f'{key} must be a positive integer')
    context = note.get('context', {})
    if not isinstance(context, dict) or len(encode(context)) > 8000:
        raise ValueError('context must be a JSON object of at most 8000 encoded characters')
    jev = note.get('jev')
    if jev is not None:
        # Keep the unchanged `strategy opinion` output; it must stay advisory.
        if (not isinstance(jev, dict) or jev.get('tool') != 'timing_opinion'
                or jev.get('advisory') is not True or jev.get('order_authorized') is not False):
            raise ValueError('jev must be an unchanged advisory strategy opinion output')
        if author != 'jev':
            raise ValueError('Only a jev-authored note may carry a Jev opinion')
        for key in ('confidence', 'min_confidence'):
            if jev.get(key) is not None and not isinstance(jev[key], str):
                raise ValueError('Jev decimals must stay decimal strings')
        if jev.get('confidence') is not None:
            Decimal(jev['confidence'])
    elif author == 'jev':
        raise ValueError('A jev-authored note requires the unchanged Jev opinion output')
    text = _text(note.get('text'), 'text') if author != 'jev' or note.get('text') else None
    return {
        'policy_version': POLICY_VERSION,
        'account': _text(note.get('account'), 'account', limit=200),
        'instrument': _text(note.get('instrument'), 'instrument', limit=100),
        'author': author, 'phase': phase, 'stance': stance, 'text': text,
        'observed_ms': observed, 'recorded_ms': recorded,
        'journal_id': note.get('journal_id'), 'fact_id': note.get('fact_id'),
        'decision_id': _text(note.get('decision_id'), 'decision_id', limit=200, required=False),
        'supersedes_note_id': note.get('supersedes_note_id'),
        'context': context, 'jev': jev,
        'advisory': True, 'order_authorized': False,
    }


def add_note(store, note):
    """Append one note. Existing notes are never edited; corrections supersede."""
    entry = validate_note(note)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if entry['journal_id'] is not None:
            row = db.execute("SELECT kind FROM analysis_runs WHERE id=?", (entry['journal_id'],)).fetchone()
            if row is None or row['kind'] != 'position_change':
                raise ValueError('journal_id must reference an automatic position-change journal')
        if entry['fact_id'] is not None and db.execute(
                "SELECT 1 FROM fact_revisions WHERE id=? AND dataset='trade'", (entry['fact_id'],)).fetchone() is None:
            raise ValueError('fact_id must reference a trade fact')
        if entry['supersedes_note_id'] is not None:
            row = db.execute("SELECT kind FROM analysis_runs WHERE id=?", (entry['supersedes_note_id'],)).fetchone()
            if row is None or row['kind'] != 'decision_note':
                raise ValueError('supersedes_note_id must reference a decision note')
        run = db.execute(
            'INSERT INTO analysis_runs(kind,created_ms,as_of_ms,parameters,result) VALUES(?,?,?,?,?)',
            ('decision_note', entry['recorded_ms'], entry['observed_ms'],
             encode({'accounts': [entry['account']], 'policy_version': POLICY_VERSION}),
             encode(entry))).lastrowid
        if entry['fact_id'] is not None:
            db.execute('INSERT INTO analysis_inputs VALUES(?,?)', (run, entry['fact_id']))
    return {'note_id': run, **entry}


def list_notes(store, *, accounts=None, instrument=None, since_ms=None, limit=200):
    import json
    with store.connect() as db:
        rows = db.execute("SELECT id,result FROM analysis_runs WHERE kind='decision_note' ORDER BY as_of_ms,id").fetchall()
    notes = [{'note_id': r['id'], **json.loads(r['result'])} for r in rows]
    superseded = {n['supersedes_note_id'] for n in notes if n.get('supersedes_note_id')}
    out = []
    for n in notes:
        if accounts and n['account'] not in accounts:
            continue
        if instrument and n['instrument'] != instrument:
            continue
        if since_ms is not None and n['observed_ms'] < since_ms:
            continue
        out.append({**n, 'superseded': n['note_id'] in superseded})
    return out[-limit:] if limit else out


def attach_notes(changes, notes):
    """Group effective notes next to position activity by journal/fact link or instrument."""
    effective = [n for n in notes if not n['superseded']]
    linked = set()
    for change in changes:
        own = [n for n in effective
               if (n['journal_id'] is not None and n['journal_id'] == change.get('journal_id'))
               or (n['fact_id'] is not None and n['fact_id'] == change.get('fact_id'))]
        linked.update(n['note_id'] for n in own)
        change['notes'] = own
    return [n for n in effective if n['note_id'] not in linked]
