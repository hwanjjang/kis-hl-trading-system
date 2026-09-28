"""Immutable source-backed position activity, separate from realized statistics."""
import json
from decimal import Decimal

from kis_hl.data_store import encode, now_ms, number

POLICY_VERSION = 'position-change-v1'


def change_entry(fact):
    """Describe one source revision without inventing an inventory anchor."""
    payload = fact['payload']
    quantity = Decimal(number(payload['quantity']))
    if quantity <= 0 or payload['side'] not in {'buy', 'sell'}:
        raise ValueError('Position activity requires a positive executed quantity and side')
    signed = quantity if payload['side'] == 'buy' else -quantity
    before = payload.get('position_before')
    after = None
    change = 'unclassified'
    if before is not None:
        before = Decimal(number(before))
        after = before + signed
        if fact['instrument'].startswith('kis:') and (before < 0 or after < 0):
            # An equity inventory gap is not evidence of an authorized short.
            change = 'inventory_gap'
        elif before == 0:
            change = 'entry'
        elif after == 0:
            change = 'close'
        elif before * after < 0:
            change = 'reversal'
        elif abs(after) > abs(before):
            change = 'increase'
        else:
            change = 'reduction'
    return dict(policy_version=POLICY_VERSION, fact_id=fact['id'],
                supersedes_fact_id=fact['supersedes'], revision=fact['revision'],
                record_type='revision' if fact['supersedes'] is not None else 'execution',
                account=fact['scope'], instrument=fact['instrument'],
                currency=payload['currency'], source_key=fact['business_key'],
                known_ms=fact['known_ms'], event_start_ms=fact['event_start_ms'],
                event_end_ms=fact['event_end_ms'], time_precision=payload['time_precision'],
                grain=payload.get('grain'), side=payload['side'],
                signed_quantity=number(signed),
                position_before=None if before is None else number(before),
                position_after=None if after is None else number(after), change=change,
                price=payload.get('price'), notional=payload.get('notional'),
                total_cost=payload.get('total_cost'), costs=payload.get('costs', {}),
                strategy=payload.get('strategy', 'unassigned'),
                origin=payload.get('origin', 'unknown'), order_id=payload.get('order_id'))


def record_change(db, fact_id):
    """Write within the caller's fact transaction; failure must roll back both."""
    row = db.execute('SELECT * FROM fact_revisions WHERE id=?', (fact_id,)).fetchone()
    fact = dict(row, payload=json.loads(row['payload']))
    entry = change_entry(fact)
    run = db.execute(
        'INSERT INTO analysis_runs(kind,created_ms,as_of_ms,parameters,result) VALUES(?,?,?,?,?)',
        ('position_change', now_ms(), fact['known_ms'],
         encode({'accounts': [fact['scope']], 'policy_version': POLICY_VERSION}),
         encode(entry))).lastrowid
    db.execute('INSERT INTO analysis_inputs VALUES(?,?)', (run, fact_id))


def report_changes(store, trades):
    """Project only the report's effective inputs; old revisions remain exportable."""
    if not trades:
        return []
    accounts = sorted({f['scope'] for f in trades})
    placeholders = ','.join('?' for _ in accounts)
    with store.connect() as db:
        recorded = {r['fact_id']: r['run_id'] for r in db.execute(
            f"""SELECT i.fact_id,i.run_id FROM analysis_inputs i
                JOIN analysis_runs r ON r.id=i.run_id
                JOIN fact_revisions f ON f.id=i.fact_id
                WHERE r.kind='position_change' AND f.scope IN ({placeholders})""", accounts)}
    return [{**change_entry(fact), 'journal_id': recorded.get(fact['id']),
             'recording': 'automatic' if fact['id'] in recorded else 'historical_projection'}
            for fact in sorted(trades, key=lambda f: (f['event_start_ms'], f['id']))]
