"""Read-only nine-minute trailing-stop advisory observations.

The supervisor owns execution. This module writes only its separate alert database.
"""
from __future__ import annotations

import json
import sqlite3
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

BUCKET = 540_000
MINUTE = 60_000
REASONS = {
    'coverage_gap': 'Required one-minute candles are missing or not finalized.',
    'retention_limit': 'Pending history exceeds the verified one-minute retention limit.',
    'exposure_mismatch': 'Local owner and exchange long exposure do not match.',
    'entry_evidence_missing': 'First entry fill time could not be verified.',
    'invalid_bid': 'Best bid is missing, malformed or not finite and positive.',
    'invalid_schema': 'Required observation fields are malformed or inconsistent.',
    'owner_missing': 'The configured local owner was not found.',
    'owner_identity_mismatch': 'Local owner identity or mode does not match the monitor.',
    'configuration_mismatch': 'The expected mainnet execution account is not configured.',
    'read_unavailable': 'A required read could not be completed; transport text is omitted.',
    'unexpected_failure': 'Observation failed unexpectedly; exception text is omitted.',
}
OPERATIONS = {'configuration', 'owner', 'positions', 'protection', 'entry',
              'history', 'aggregation', 'bid', 'state'}


class ObservationError(ValueError):
    """An allowlisted failure with no arbitrary exception text or account payload."""
    def __init__(self, reason, *, bucket_start_ms=None, missing_minutes_ms=()):
        if reason not in REASONS:
            raise ValueError('Unknown observation reason')
        super().__init__(REASONS[reason])
        self.reason = reason
        self.bucket_start_ms = bucket_start_ms
        self.missing_minutes_ms = list(missing_minutes_ms)


def positive(value, reason='invalid_schema'):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0:
            raise ObservationError(reason)
        return number
    except (InvalidOperation, ValueError, TypeError):
        raise ObservationError(reason) from None


def timestamp(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ObservationError('invalid_schema')
    return value


def aggregate(raw, start, end):
    """Return complete contiguous (bucket start, high, close) trade bars.

    Boundary-invalid constituent minutes are gaps, never forward-filled.
    """
    if not isinstance(raw, list) or start % BUCKET or end % BUCKET or end < start:
        raise ObservationError('invalid_schema')
    by_start = {}
    for bar in raw:
        if not isinstance(bar, dict):
            raise ObservationError('invalid_schema')
        t = timestamp(bar.get('t'))
        if not start <= t < end:
            continue
        if t % MINUTE:
            raise ObservationError('invalid_schema')
        if timestamp(bar.get('T')) + 1 != t + MINUTE:
            continue
        high, close = positive(bar.get('h')), positive(bar.get('c'))
        if high < close or t in by_start:
            raise ObservationError('invalid_schema')
        by_start[t] = high, close
    result = []
    for t in range(start, end, BUCKET):
        missing = [t + i * MINUTE for i in range(9) if t + i * MINUTE not in by_start]
        if missing:
            raise ObservationError('coverage_gap', bucket_start_ms=t, missing_minutes_ms=missing)
        bars = [by_start[t + i * MINUTE] for i in range(9)]
        result.append((t, max(b[0] for b in bars), bars[-1][1]))
    return result


def initialize(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS bars (coin TEXT PRIMARY KEY, generation INTEGER NOT NULL, last_end INTEGER NOT NULL, high TEXT NOT NULL, threshold TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS alerts (coin TEXT NOT NULL, kind TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(coin,kind))')
    conn.execute('CREATE TABLE IF NOT EXISTS diagnostics (coin TEXT PRIMARY KEY, payload TEXT NOT NULL)')


def status(conn, coin, kind):
    row = conn.execute('SELECT value FROM alerts WHERE coin=? AND kind=?', (coin, kind)).fetchone()
    return row[0] if row else None


def set_status(conn, coin, kind, value):
    conn.execute('INSERT INTO alerts VALUES(?,?,?) ON CONFLICT(coin,kind) DO UPDATE SET value=excluded.value', (coin, kind, value))


def load_owner(db_path, owner_id):
    with sqlite3.connect(f'file:{Path(db_path).resolve()}?mode=ro', uri=True) as db:
        row = db.execute('SELECT state,snapshot FROM managed_positions WHERE id=?', (owner_id,)).fetchone()
    if row is None:
        raise ObservationError('owner_missing')
    return row[0], json.loads(row[1])


def load_entry_ids(db_path, owner_id):
    with sqlite3.connect(f'file:{Path(db_path).resolve()}?mode=ro', uri=True) as db:
        rows = db.execute('SELECT snapshot FROM managed_attempts WHERE position_id=? AND kind=?', (owner_id, 'entry')).fetchall()
    return {str(json.loads(row[0])['order_id']) for row in rows}


class Monitor:
    """Each symbol validates evidence before committing reconstructed bar state."""
    def __init__(self, conn, info, owner_reader, entry_reader):
        self.conn, self.info = conn, info
        self.owner_reader, self.entry_reader = owner_reader, entry_reader
        initialize(conn)

    def tick(self, owner_ids, now, *, configuration_error=False):
        messages, diagnostics, shared = [], {}, {}

        def read(key, callback):
            # Cache shared reads including failures; no duplicated account requests.
            if key not in shared:
                try:
                    shared[key] = callback()
                except Exception:
                    shared[key] = ObservationError('read_unavailable')
            value = shared[key]
            if isinstance(value, ObservationError):
                raise value
            return value

        for coin, owner_id in owner_ids.items():
            operation = 'configuration'
            pending_messages, savepoint_open = [], False
            prior = self.conn.execute('SELECT generation,last_end,high,threshold FROM bars WHERE coin=?', (coin,)).fetchone()
            saved = self.conn.execute('SELECT payload FROM diagnostics WHERE coin=?', (coin,)).fetchone()
            previous = json.loads(saved[0]) if saved else {}
            diagnostic = dict(operation=operation, reason='verified', explanation='Observation verified.',
                              bucket_start_ms=None, missing_minutes_ms=[], observed_ms=now,
                              last_success_ms=previous.get('last_success_ms'),
                              prior_watermark_ms=prior[1] if prior else None,
                              covered_through_ms=prior[1] if prior else None,
                              protection={'fixed_sl': 'unknown', 'native_ts': 'unknown'})
            try:
                if configuration_error:
                    raise ObservationError('configuration_mismatch')
                operation = 'owner'
                owner_state, owner = self.owner_reader(owner_id)
                plan = owner['plan']
                if owner['id'] != owner_id or plan['instrument'] != 'hl:' + coin or owner['mode'] != 'live':
                    raise ObservationError('owner_identity_mismatch')
                owner_qty = Decimal(str(owner['observed_size']))
                if not owner_qty.is_finite() or owner_qty < 0:
                    raise ObservationError('invalid_schema')
                operation = 'positions'
                account = read('positions', lambda: self.info.clearinghouse_state(dex='xyz'))
                positions = account['assetPositions']
                if not isinstance(positions, list):
                    raise ObservationError('invalid_schema')
                matches = [p['position'] for p in positions if p['position']['coin'] == coin]
                if len(matches) > 1:
                    raise ObservationError('invalid_schema')
                if not matches:
                    # Preserve advisory history; absence cannot certify a verified recovery.
                    self.conn.execute('SAVEPOINT advisory_observation')
                    savepoint_open = True
                    if status(self.conn, coin, 'closed') != 'yes':
                        pending_messages.append(f'{coin}: position closed; nine-minute observation stopped. Verify remaining protection orders separately. observed_ms={now}.')
                    set_status(self.conn, coin, 'closed', 'yes')
                    diagnostic.update(reason='closed', explanation='Exchange exposure is absent; observation stopped.')
                else:
                    position = matches[0]
                    qty = positive(position['szi'], 'exposure_mismatch')
                    if qty != owner_qty:
                        raise ObservationError('exposure_mismatch')
                    set_status(self.conn, coin, 'closed', 'no')
                    operation = 'protection'
                    orders = read('orders', lambda: self.info.frontend_open_orders(dex='xyz'))
                    if not isinstance(orders, list):
                        raise ObservationError('invalid_schema')
                    protection = [o for o in orders if o['coin'] == coin and o.get('reduceOnly') is True
                                  and o.get('side') == 'A' and positive(o.get('sz')) >= qty]
                    for kind, label in [('Stop Market', 'fixed_sl'), ('Trailing Stop Market', 'native_ts')]:
                        flag = 'yes' if any(o['orderType'] == kind for o in protection) else 'no'
                        diagnostic['protection'][label] = flag
                        if flag == 'no' and status(self.conn, coin, kind) != 'no':
                            messages.append(f'Urgent {coin}: full-size {label} was not verified. Check the exchange. observed_ms={now}.')
                        set_status(self.conn, coin, kind, flag)
                    if owner_state == 'INTERVENTION' and status(self.conn, coin, 'owner') != owner_state:
                        messages.append(f'{coin}: local owner is INTERVENTION; native protection and advisory monitoring are separate. observed_ms={now}.')
                    set_status(self.conn, coin, 'owner', owner_state)
                    distance = positive(plan['atr']) * positive(plan.get('local_atr_multiple', plan['atr_multiple']))
                    operation = 'entry'
                    generation = owner.get('first_fill_ms')
                    if generation is None:
                        ids = self.entry_reader(owner_id)
                        fills = read(('fills', coin), lambda: self.info.user_fills_by_time(
                            start_time_ms=timestamp(owner['created_ms']), end_time_ms=now))
                        if not isinstance(fills, list):
                            raise ObservationError('invalid_schema')
                        times = [timestamp(f['time']) for f in fills if f.get('coin') == coin
                                 and f.get('side') == 'B' and str(f.get('oid')) in ids]
                        if not times:
                            raise ObservationError('entry_evidence_missing')
                        generation = min(times)
                    generation = timestamp(generation)
                    if generation > now:
                        raise ObservationError('entry_evidence_missing')
                    same = prior is not None and prior[0] == generation
                    start = prior[1] if same else ((generation // BUCKET) + 1) * BUCKET
                    end = ((now - 15_000) // BUCKET) * BUCKET
                    operation = 'history'
                    if end > start and (end - start) // MINUTE > 4900:
                        raise ObservationError('retention_limit')
                    bars = []
                    if end > start:
                        raw = read(('candles', coin), lambda: self.info.candle_snapshot(
                            coin, interval='1m', start_time_ms=start, end_time_ms=end))
                        operation = 'aggregation'
                        bars = aggregate(raw, start, end)
                    high = positive(prior[2]) if same else positive(position['entryPx'])
                    threshold = Decimal(prior[3]) if same else high - distance
                    if not threshold.is_finite():
                        raise ObservationError('invalid_schema')
                    for _, bar_high, _ in bars:
                        high = max(high, bar_high)
                        threshold = max(threshold, high - distance)
                    operation = 'bid'
                    book = read(('bid', coin), lambda: self.info.l2_book(coin))
                    try:
                        bid = positive(book['levels'][0][0]['px'], 'invalid_bid')
                    except (KeyError, TypeError, IndexError):
                        raise ObservationError('invalid_bid') from None
                    covered = end if bars else start
                    operation = 'state'
                    self.conn.execute('SAVEPOINT advisory_observation')
                    savepoint_open = True
                    if bars or not same:
                        self.conn.execute('INSERT INTO bars VALUES(?,?,?,?,?) ON CONFLICT(coin) DO UPDATE SET generation=excluded.generation,last_end=excluded.last_end,high=excluded.high,threshold=excluded.threshold',
                                          (coin, generation, covered, str(high), str(threshold)))
                    breached = bid <= threshold
                    if breached and status(self.conn, coin, 'breach') != str(threshold):
                        pending_messages.append(f'{coin}: nine-minute TS advisory: best bid {bid} <= reference threshold {threshold}; trade-candle high {high}, entry ATR distance {distance}. Proxy differs from supervisor bid watermark. No automatic order. observed_ms={now}.')
                    set_status(self.conn, coin, 'breach', str(threshold) if breached else 'clear')
                    if status(self.conn, coin, 'error') not in {None, 'ok'}:
                        pending_messages.append(f'{coin}: nine-minute TS observation recovered; covered_through_ms={covered}, observed_ms={now}. Protection status is separate; no automatic order.')
                    set_status(self.conn, coin, 'error', 'ok')
                    diagnostic.update(last_success_ms=now, covered_through_ms=covered)
                diagnostic['operation'] = operation
                self.conn.execute('INSERT INTO diagnostics VALUES(?,?) ON CONFLICT(coin) DO UPDATE SET payload=excluded.payload',
                                  (coin, json.dumps(diagnostic, sort_keys=True)))
                self.conn.execute('RELEASE advisory_observation')
                savepoint_open = False
                messages.extend(pending_messages)
            except Exception as exc:
                if savepoint_open:
                    self.conn.execute('ROLLBACK TO advisory_observation')
                    self.conn.execute('RELEASE advisory_observation')
                    # Discard any candidate coverage/success evidence before degradation.
                    diagnostic.update(last_success_ms=previous.get('last_success_ms'),
                                      covered_through_ms=prior[1] if prior else None)
                if isinstance(exc, ObservationError):
                    reason = exc.reason
                    diagnostic.update(bucket_start_ms=exc.bucket_start_ms, missing_minutes_ms=exc.missing_minutes_ms)
                elif isinstance(exc, (KeyError, TypeError, IndexError, ValueError, InvalidOperation)):
                    reason = 'invalid_schema'
                elif isinstance(exc, sqlite3.Error):
                    reason = 'read_unavailable'
                else:
                    reason = 'unexpected_failure'
                diagnostic.update(reason=reason, explanation=REASONS[reason])
                if status(self.conn, coin, 'error') != reason:
                    messages.append(f'{coin}: nine-minute TS observation degraded: operation={operation}, reason={reason}. {REASONS[reason]} bucket_start_ms={diagnostic["bucket_start_ms"]}, missing_minutes_ms={diagnostic["missing_minutes_ms"]}, prior_watermark_ms={diagnostic["prior_watermark_ms"]}, last_success_ms={diagnostic["last_success_ms"]}, observed_ms={now}. This advisory is not exchange protection.')
                set_status(self.conn, coin, 'error', reason)
                diagnostic['operation'] = operation
                self.conn.execute('INSERT INTO diagnostics VALUES(?,?) ON CONFLICT(coin) DO UPDATE SET payload=excluded.payload',
                                  (coin, json.dumps(diagnostic, sort_keys=True)))
            diagnostics[coin] = diagnostic
        self.conn.commit()
        return {'messages': messages, 'diagnostics': diagnostics}


def run_monitor(root, expected_account, owner_ids, *, state_path=None, now=None):
    """Load the existing account locally; expose only its unsigned info reader."""
    from kis_hl.config import load_env_file, load_hyperliquid_config
    from kis_hl.hyperliquid.client import HyperliquidInfoClient

    root = Path(root)
    state_path = Path(state_path) if state_path else root / 'data/analysis/hl-9m-ts-alert/state.sqlite'
    now = int(time.time() * 1000) if now is None else now
    info, bad_config = None, False
    try:
        load_env_file(root / '.env')
        config = load_hyperliquid_config()
        if config.base_url != 'https://api.hyperliquid.xyz' or config.account_address.lower() != expected_account.lower():
            bad_config = True
        else:
            info = HyperliquidInfoClient(config)
    except Exception:
        bad_config = True
    state_path.parent.mkdir(parents=True, exist_ok=True)
    db_path = root / 'data/kis_hl.sqlite'
    with sqlite3.connect(state_path) as conn:
        return Monitor(conn, info, lambda oid: load_owner(db_path, oid),
                       lambda oid: load_entry_ids(db_path, oid)).tick(owner_ids, now, configuration_error=bad_config)
