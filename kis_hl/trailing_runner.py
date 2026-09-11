"""Single-position trailing manager. Exchange acceptance never implies flatness."""
from decimal import Decimal
import time

from kis_hl.hyperliquid.client import prepare_perp_exit
from kis_hl.logging_utils import get_logger
from kis_hl.trailing import Trail, positive

logger = get_logger(__name__)


def terminal(status: str) -> bool:
    return status in {'filled', 'canceled', 'rejected', 'scheduledCancel'} or status.endswith(('Canceled', 'Rejected'))


class TrailingRunner:
    def __init__(self, store, position_id, gateway):
        self.store, self.gateway = store, gateway
        self.row = store.get(position_id)
        self.trail = Trail.from_dict(self.row['trail'])
        self.trail.disconnect()
        self.last_sync = None
        self.observation = None

    def state(self, state, cause):
        if self.row['state'] != state or self.row.get('reason') != cause:
            self.row.update(state=state, reason=cause, trail=self.trail.to_dict())
            self.store.save(self.row, cause)

    def reconcile(self, now_ms):
        if self.row["state"] in {"MANUAL_INTERVENTION", "CLOSED", "PAPER_EXIT"}:
            return False
        attempts = self.store.attempts(self.row['id'])
        self.last_sync = now_ms
        try:
            observed = self.gateway.snapshot(self.row, attempts, now_ms)
            size = Decimal(observed['size'])
            entry = Decimal(observed['entry'])
            if not size.is_finite() or not entry.is_finite():
                raise ValueError('non-finite position')
        except Exception as exc:
            self.observation = None
            self.trail.disconnect()
            self.state('RECONCILING', f'snapshot unavailable: {exc}')
            return False
        self.last_sync = now_ms
        self.observation = observed
        if (not observed['generation_ok'] or size < 0 or size > Decimal(self.row['size'])
                or (size > 0 and entry != Decimal(self.row['entry']))):
            self.state('MANUAL_INTERVENTION', 'position generation changed')
            return False
        self.row.update(size=str(size), last_reconciled_ms=now_ms,
                        protection_verified_ms=now_ms if observed['protection'] else None,
                        verified_covered_size=str(size) if observed['protection'] else '0',
                        trail=self.trail.to_dict())
        self.store.save(self.row, 'exchange snapshot reconciled')
        unresolved = False
        for attempt in attempts:
            if attempt['status'] in {'TERMINAL', 'REJECTED'}:
                continue
            status = observed['order_states'].get(attempt['cloid'], 'unknownOid')
            if terminal(status):
                self.store.finish_attempt(attempt['id'], status='TERMINAL', response={'order_status': status})
            else:
                unresolved = True
        if size == 0:
            # Even reduce-only leftovers can affect a later position generation.
            self.state('FLAT_CLEANUP', 'position flat; verify managed order cleanup')
            if unresolved:
                return False
            if observed['stop_open']:
                if self.row['mode'] == 'live':
                    try:
                        self.gateway.cancel_stop(self.row)
                    except Exception as exc:
                        self.state('FLAT_CLEANUP', f'cancel unknown: {exc}')
                return False
            self.state('CLOSED', 'flat and managed orders terminal')
            return False
        if not observed['protection']:
            self.state('MANUAL_INTERVENTION', 'native stop missing or insufficient; operator must protect or close')
            return False
        intent = self.store.intent(self.row['id'])
        if intent:
            if now_ms - intent['created_ms'] >= self.row['exit_timeout_ms']:
                self.state('MANUAL_INTERVENTION', 'exit deadline reached; protection retained')
                return False
            self.state('RECONCILING' if unresolved else 'EXIT_PENDING',
                       'order acceptance unresolved' if unresolved else 'exit intent remains active')
            return not unresolved
        self.state('PROTECTED', 'native stop verified')
        return True

    def on_tick(self, time_ms: int, price: Decimal, *, age_ms: int = 0):
        tick_started = time.monotonic()
        positive(price, 'price')
        if self.row['state'] in {'CLOSED', 'MANUAL_INTERVENTION', 'PAPER_EXIT'}:
            return
        if age_ms < 0 or age_ms > self.row['max_gap_ms']:
            self.trail.disconnect()
            self.state('DEGRADED', 'stale per-symbol price; no trailing action')
            return
        if self.last_sync is None or time_ms - self.last_sync >= 10_000:
            if not self.reconcile(time_ms):
                return
        if self.observation is None or self.row['state'] not in {'PROTECTED', 'EXIT_PENDING', 'DEGRADED'}:
            return
        if age_ms + (time.monotonic() - tick_started)*1000 > self.row['max_gap_ms']:
            self.trail.disconnect()
            self.state('DEGRADED', 'price aged during initial reconciliation')
            return
        prior = (self.trail.high, self.trail.threshold)
        crossed = self.trail.tick(time_ms, price, max_gap_ms=self.row['max_gap_ms'])
        self.row['trail'] = self.trail.to_dict()
        if prior != (self.trail.high, self.trail.threshold):
            self.store.save(self.row, 'closed bar raised threshold')
        if crossed and not self.store.intent(self.row['id']):
            self.store.decide_exit(self.row, now_ms=time_ms)
        if not self.store.intent(self.row['id']):
            return
        if self.row['mode'] == 'paper':
            self.state('PAPER_EXIT', 'would submit reduce-only exit; no simulated fill assumption')
            return
        # Re-query immediately before each new attempt. All previous attempts must
        # have terminal evidence; a rebound never cancels the persisted intent.
        if not self.reconcile(time_ms):
            return
        if age_ms + (time.monotonic() - tick_started)*1000 > self.row['max_gap_ms']:
            self.state('DEGRADED', 'price aged during reconciliation')
            return
        attempts = self.store.attempts(self.row['id'])
        if len(attempts) >= self.row['max_attempts']:
            self.state('MANUAL_INTERVENTION', 'exit retry cap reached; protection retained')
            return
        try:
            limit, size = prepare_perp_exit(price=price, size=Decimal(self.row['size']),
                                            sz_decimals=self.row['sz_decimals'],
                                            slippage=Decimal(self.row['slippage']))
        except ValueError as exc:
            self.state('MANUAL_INTERVENTION', str(exc))
            return
        attempt = self.store.prepare_attempt(self.row['id'], size=str(size), limit=str(limit), now_ms=time_ms)
        logger.info('trailing_exit_attempt', extra={'position_id': self.row['id'], 'attempt_id': attempt['id'],
                    'cloid': attempt['cloid'], 'size': str(size), 'limit_price': str(limit),
                    'cause': 'threshold crossed', 'action': 'submit IOC', 'result': 'unknown until reconciled'})
        try:
            response = self.gateway.submit(self.row, attempt)
        except Exception as exc:
            self.store.finish_attempt(attempt['id'], status='UNKNOWN', response={'error':str(exc)})
            self.state('RECONCILING', 'submission outcome unknown; no blind resend')
            return
        statuses = response.get('response', {}).get('data', {}).get('statuses', []) if isinstance(response, dict) else []
        rejected = len(statuses) == 1 and isinstance(statuses[0], dict) and 'error' in statuses[0]
        self.store.finish_attempt(attempt['id'], status='REJECTED' if rejected else 'UNKNOWN', response=response)
        self.state('RECONCILING', 'submitted; verify fills and residual position')


def protection_matches(row, order, size):
    try:
        covered = Decimal(order['sz'])
        trigger = Decimal(order['triggerPx'])
        return (int(order['oid']) == row['stop_oid'] and order['coin'] == row['coin']
                and order['side'] == 'A' and order['reduceOnly'] is True
                and order['isTrigger'] is True and order['orderType'] == 'Stop Market'
                and covered.is_finite() and covered >= size
                and trigger.is_finite() and trigger == Decimal(row['native_trigger']))
    except (KeyError, ValueError, ArithmeticError, TypeError):
        return False


class HyperliquidGateway:
    def __init__(self, info, trading):
        self.info, self.trading = info, trading

    def snapshot(self, row, attempts, now_ms):
        states = {}
        valid_orders = True
        for attempt in attempts:
            if attempt['status'] in {'TERMINAL', 'REJECTED'}:
                continue
            response = self.info.order_status(oid=attempt['cloid'])
            status = response.get('order', {}).get('status', 'unknownOid')
            order = response.get('order', {}).get('order', {})
            if status != 'unknownOid' and (order.get('coin') != row['coin'] or order.get('reduceOnly') is not True
                                           or order.get('side') != 'A' or order.get('cloid') != attempt['cloid']):
                valid_orders = False
            states[attempt['cloid']] = status
        fills = self.info.user_fills_by_time(start_time_ms=row['opened_ms'], end_time_ms=now_ms)
        orders = self.info.frontend_open_orders(dex=row['dex'])
        stop = next((o for o in orders if int(o['oid']) == row['stop_oid']), None)
        stop_active = True
        if stop is None:
            status = self.info.order_status(oid=row['stop_oid'])
            stop_active = not terminal(status.get('order', {}).get('status', 'unknownOid'))
        # Position is fetched last, after status/fills: it must not predate a known fill.
        state = self.info.clearinghouse_state(dex=row['dex'])
        positions = state['assetPositions']
        if not isinstance(positions, list):
            raise ValueError('Invalid position snapshot')
        position = next((p['position'] for p in positions if p['position']['coin'] == row['coin']), None)
        size = Decimal(position['szi']) if position else Decimal(0)
        entry = Decimal(position['entryPx']) if position and size else Decimal(0)
        relevant = {str(f['tid']): f for f in fills if f['coin'] == row['coin']}
        entry_ids = set(row['entry_fill_ids'])
        generation_ok = valid_orders and len(fills) < 2000 and entry_ids.issubset(relevant)
        balance = Decimal(0)
        for fill in relevant.values():
            amount = positive(Decimal(fill['sz']), 'fill size')
            if fill['side'] == 'B':
                if int(fill['oid']) != row['entry_oid']:
                    generation_ok = False
                balance += amount
            elif fill['side'] == 'A':
                balance -= amount
            else:
                generation_ok = False
        # A missing/truncated ledger cannot prove position-generation continuity.
        if generation_ok and balance != size:
            raise RuntimeError('Position and fill snapshots are not yet consistent')
        known_oids = {row['stop_oid']}
        for order in orders:
            if order['coin'] != row['coin'] or int(order['oid']) in known_oids:
                continue
            if order.get('cloid') not in {a['cloid'] for a in attempts}:
                generation_ok = False
        return {'size':str(size), 'entry':str(entry), 'generation_ok':generation_ok,
                'protection':stop is not None and protection_matches(row, stop, size),
                'stop_open':stop_active, 'order_states':states}

    def submit(self, row, attempt):
        result = self.trading.place_order(symbol=row['symbol'], dex=row['dex'], side='sell',
            order_type='limit', size=Decimal(attempt['size']), price=Decimal(attempt['limit_price']),
            reduce_only=True, tif='Ioc', cloid=attempt['cloid'], dry_run=False,
            expires_after_ms=attempt['created_ms'] + row['max_gap_ms'])
        return result.response

    def cancel_stop(self, row):
        return self.trading.cancel_order(symbol=row['symbol'], dex=row['dex'], oid=row['stop_oid'], dry_run=False)


def fetch_trailing_atr(info, symbol, *, now_ms, dex=None):
    from kis_hl.assets import resolve_hyperliquid_symbol
    day = 86_400_000
    today = now_ms // day * day
    coin = resolve_hyperliquid_symbol(symbol, dex=dex).coin
    raw = info.candle_snapshot(symbol, dex=dex, interval='1d', start_time_ms=today-12*day, end_time_ms=today-1)
    if not isinstance(raw, list):
        raise ValueError('Missing Hyperliquid daily bars')
    bars = sorted((b for b in raw if int(b['t']) < today), key=lambda b: int(b['t']))[-11:]
    if len(bars) != 11 or [int(b['t']) for b in bars] != list(range(today-11*day, today, day)):
        raise ValueError('ATR needs 11 contiguous closed daily bars ending yesterday')
    normalized = []
    for bar in bars:
        if bar.get('s') != coin or int(bar['T']) != int(bar['t'])+day-1:
            raise ValueError('ATR bars must match the managed Hyperliquid instrument and daily boundaries')
        high, low, close = (positive(Decimal(bar[k]), k) for k in ['h', 'l', 'c'])
        if not low <= close <= high:
            raise ValueError('Invalid daily OHLC prices')
        from datetime import datetime, timezone
        normalized.append({'date':datetime.fromtimestamp(int(bar['t'])/1000, timezone.utc).date(),
                           'high':high, 'low':low, 'close':close})
    from kis_hl.risk import calculate_atr_10d
    atr = calculate_atr_10d(normalized)
    return positive(atr, 'ATR'), bars


def enroll_position(store, info, trading, *, symbol, entry_oid, stop_oid, multiple,
                    max_gap_ms, slippage, live=False, now_ms=None):
    from kis_hl.assets import resolve_hyperliquid_symbol
    from kis_hl.hyperliquid.client import is_supported_live_asset
    now_ms = int(time.time()*1000) if now_ms is None else now_ms
    resolved = resolve_hyperliquid_symbol(symbol)
    if resolved.kind != 'perp' or not is_supported_live_asset(resolved):
        raise ValueError('Trailing enrollment requires an eligible long perpetual')
    if not 0 < max_gap_ms <= 60_000:
        raise ValueError('max_gap_ms must be between 1 and 60000')
    positive(slippage, 'slippage')
    if slippage >= 1:
        raise ValueError('slippage must be less than one')
    if live:
        trading._require_recent_verification(resolved)
        trading._require_credentials()
    status = info.order_status(oid=entry_oid)
    order = status.get('order', {}).get('order', {})
    if (status.get('order', {}).get('status') != 'filled' or order.get('coin') != resolved.coin
            or order.get('side') != 'B' or order.get('reduceOnly') is not False):
        raise ValueError('Enrollment requires a confirmed filled long-entry order')
    opened_ms = int(order['timestamp'])
    fills = info.user_fills_by_time(start_time_ms=opened_ms, end_time_ms=now_ms)
    entry_fills = {str(f['tid']): f for f in fills if int(f['oid']) == entry_oid and f['coin'] == resolved.coin}
    if not entry_fills or len(fills) >= 2000:
        raise ValueError('Complete entry fills unavailable')
    size = sum((positive(Decimal(f['sz']), 'fill size') for f in entry_fills.values()), Decimal(0))
    entry = sum((Decimal(f['px'])*Decimal(f['sz']) for f in entry_fills.values()), Decimal(0))/size
    if size != Decimal(order['origSz']):
        raise ValueError('Entry fill quantity does not match terminal order size')
    atr, bars = fetch_trailing_atr(info, symbol, now_ms=now_ms)
    trail = Trail.create(entry=entry, atr=atr, multiple=multiple, opened_ms=opened_ms)
    meta = info.meta_and_asset_ctxs(dex=resolved.dex)[0]
    universe = [x for x in meta['universe'] if x['name'] == resolved.coin]
    if len(universe) != 1 or universe[0].get('isDelisted'):
        raise ValueError('Managed asset absent or delisted in metadata')
    decimals = int(universe[0]['szDecimals'])
    prepare_perp_exit(price=entry, size=size, sz_decimals=decimals, slippage=slippage)
    stops = info.frontend_open_orders(dex=resolved.dex)
    stop = next((o for o in stops if int(o['oid']) == stop_oid), None)
    if stop is None:
        raise ValueError('Enrollment requires an existing confirmed native stop')
    trigger = positive(Decimal(stop['triggerPx']), 'native trigger')
    if trigger < trail.threshold:
        raise ValueError('Existing native stop is below the configured initial risk floor')
    trail.threshold = trigger
    row = {'network':info.config.base_url.rstrip('/'), 'account':info.config.account_address.lower(),
        'coin':resolved.coin,'dex':resolved.dex,'symbol':symbol,'mode':'live' if live else 'paper',
        'state':'RECOVERING','size':str(size),'entry_size':str(size),'entry':str(entry),
        'opened_ms':opened_ms,'entry_oid':entry_oid,'entry_fill_ids':sorted(entry_fills),
        'stop_oid':stop_oid,'native_trigger':str(trigger),'atr':str(atr),'multiple':str(multiple),
        'atr_source':'hyperliquid:1d','atr_bars':bars,'price_basis':'hyperliquid:allMids:receive-time',
        'enrolled_ms':now_ms,'protection_verified_ms':now_ms,'verified_covered_size':str(size),'sz_decimals':decimals,'max_gap_ms':max_gap_ms,'slippage':str(slippage),
        'max_attempts':3,'exit_timeout_ms':120000,'trail':trail.to_dict()}
    observed = HyperliquidGateway(info, trading).snapshot(row, [], now_ms)
    if not observed['generation_ok'] or not observed['protection'] or Decimal(observed['size']) != size:
        raise ValueError('Position, entry ledger or native protection cannot be reconciled')
    # Enrollment starts a new management interval; past highs cannot be recovered
    # from daily bars. This explicit choice is recorded, never silently backfilled.
    row['state'] = 'PROTECTED'
    row['reason'] = 'explicit enrollment; no pre-enrollment intraday watermark'
    return store.enroll(row)


def run_trailing_stream(store, position_id, info, trading, *, live=False, recover=False,
                        max_messages=None, max_reconnects=None, transport_factory=None):
    import json
    from kis_hl.execution_lock import account_lock
    from kis_hl.hyperliquid.ws import all_mids_subscription, default_hyperliquid_ws_url
    from kis_hl.streaming import MaintainedWebSocketClient
    row = store.get(position_id)
    if row['mode'] != ('live' if live else 'paper'):
        raise ValueError('Run mode must match enrollment; live state requires explicit --live')
    if (row['network'] != info.config.base_url.rstrip('/')
            or row['account'] != info.config.account_address.lower()):
        raise ValueError('Configured account/network does not match enrolled position')
    with account_lock(row['network'] if live else row['network'] + '#paper', row['account']):
        runner = TrailingRunner(store, position_id, HyperliquidGateway(info, trading))
        if recover and runner.row['state'] == 'MANUAL_INTERVENTION':
            runner.state('RECOVERING', 'operator requested reconciliation; limits unchanged')
        runner.reconcile(int(time.time()*1000))
        if runner.row['state'] in {'CLOSED','MANUAL_INTERVENTION','PAPER_EXIT'}:
            return runner.row
        generation = None
        last_symbol_mono = None
        waiting_first = True

        def disconnect():
            nonlocal last_symbol_mono, waiting_first
            last_symbol_mono = None
            waiting_first = True
            runner.trail.disconnect()
            runner.observation = None
            runner.last_sync = None
            if runner.row['state'] not in {'CLOSED','MANUAL_INTERVENTION','PAPER_EXIT'}:
                runner.state('RECONCILING', 'stream disconnected; restore before trailing')

        def idle():
            now = int(time.time()*1000)
            if runner.last_sync is None or now - runner.last_sync >= 10_000:
                runner.reconcile(now)
            if runner.row['state'] in {'CLOSED','MANUAL_INTERVENTION','PAPER_EXIT'}:
                client.stop()
                return
            if last_symbol_mono is None or (time.monotonic()-last_symbol_mono)*1000 > row['max_gap_ms']:
                runner.trail.disconnect()
                if runner.observation is not None and runner.row['state'] == 'PROTECTED':
                    runner.state('DEGRADED', 'no fresh price for managed symbol')

        def message(raw, connection):
            nonlocal generation, last_symbol_mono, waiting_first
            received_mono = time.monotonic()
            received_ms = int(time.time()*1000)
            if generation != connection.status.connection_count:
                disconnect()
                generation = connection.status.connection_count
            payload = json.loads(raw)
            if payload.get('channel') != 'allMids':
                idle()
                return
            raw_price = payload.get('data', {}).get('mids', {}).get(row['coin'])
            if raw_price is None:
                idle()
                return
            price = positive(Decimal(str(raw_price)), 'mid price')
            if last_symbol_mono is not None and (received_mono-last_symbol_mono)*1000 > row['max_gap_ms']:
                runner.trail.disconnect()
            last_symbol_mono = received_mono
            if waiting_first:
                # allMids has no exchange timestamp. Quarantine reconnect's first
                # sample; it must not invent a high or be the only exit evidence.
                waiting_first = False
                idle()
                return
            runner.on_tick(received_ms, price, age_ms=int((time.monotonic()-received_mono)*1000))
            if runner.row['state'] in {'CLOSED','MANUAL_INTERVENTION','PAPER_EXIT'}:
                client.stop()

        client = MaintainedWebSocketClient(url=default_hyperliquid_ws_url(info.config),
            subscriptions=[all_mids_subscription(dex=row['dex'])], on_message=message,
            transport_factory=transport_factory, on_idle=idle, on_disconnect=disconnect,
            stale_after_ms=row['max_gap_ms'], heartbeat_payload={'method':'ping'})
        try:
            client.run(max_messages=max_messages, max_reconnects=max_reconnects)
        except KeyboardInterrupt:
            disconnect()
        return runner.row


def replay_trailing(store, input_path):
    """Replay receive-time JSONL with explicit paper initial conditions, no network."""
    import json
    from pathlib import Path
    from uuid import uuid4
    with Path(input_path).open() as source:
        header = json.loads(next(source))
        if header.get('type') != 'position':
            raise ValueError('Replay first line must be a position header')
        trail = Trail.create(entry=Decimal(header['entry']), atr=Decimal(header['atr']),
                             multiple=Decimal(header['multiple']), opened_ms=int(header['opened_ms']))
        gap = int(header['max_gap_ms'])
        if gap <= 0:
            raise ValueError('max_gap_ms must be positive')
        row = store.enroll({'network':'offline-replay','account':'paper-' + uuid4().hex,'coin':header['symbol'],
                           'mode':'paper','state':'PROTECTED','size':str(positive(Decimal(header['size']), 'size')),
                           'trail':trail.to_dict(),'price_basis':'hyperliquid:allMids:receive-time'})
        try:
            for line in source:
                event = json.loads(line)
                if event.get('type') == 'disconnect':
                    trail.disconnect()
                    continue
                age = int(event.get('age_ms', 0))
                if age < 0 or age > gap:
                    trail.disconnect()
                    continue
                crossed = trail.tick(int(event['time_ms']), Decimal(event['price']), max_gap_ms=gap)
                row['trail'] = trail.to_dict()
                if crossed:
                    store.decide_exit(row, now_ms=int(event['time_ms']))
                    row['state'] = 'PAPER_EXIT'
                    store.save(row, 'paper would exit; fill not assumed')
                    break
            else:
                row['state'] = 'CLOSED'
                store.save(row, 'replay input exhausted; paper run ended without exit')
        except Exception:
            row['state'] = 'CLOSED'
            store.save(row, 'invalid replay input; paper run aborted')
            raise
        return row
