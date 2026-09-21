"""Bounded, read-only native account capture without opening canonical state."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from zoneinfo import ZoneInfo

from kis_hl.data_store import encode, now_ms, number
from kis_hl.data_ingestion import validate_domestic_orders
from kis_hl.journal_history import fetch_time_pages
from kis_hl.journal_sync import Scope


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_HL_URLS = {'https://api.hyperliquid.xyz': 'mainnet',
            'https://api.hyperliquid-testnet.xyz': 'testnet'}


def _millis(value):
    delta = value - _EPOCH
    return delta.days * 86400000 + delta.seconds * 1000 + delta.microseconds // 1000


def _client_scope(venue, account, client, scope):
    if client is None:
        if venue == 'hyperliquid':
            from kis_hl.config import HyperliquidConfig
            from kis_hl.hyperliquid.client import HyperliquidInfoClient
            base = os.environ.get('HYPERLIQUID_BASE_URL') or (
                'https://api.hyperliquid-testnet.xyz'
                if os.environ.get('HYPERLIQUID_TESTNET', '').lower() == 'true'
                else 'https://api.hyperliquid.xyz')
            if base.rstrip('/') not in _HL_URLS:
                raise ValueError('An official Hyperliquid environment is required')
            client = HyperliquidInfoClient(HyperliquidConfig(base, account, '', 'default'))
        else:
            from kis_hl.operations_cli import kis_client
            client = kis_client()
    config = getattr(client, 'config', None)
    inferred = None
    if config is not None:
        if venue == 'kis':
            if config.account_id != account:
                raise ValueError('Requested KIS account differs from configured account')
            inferred = Scope(venue, config.mode, account)
        else:
            environment = _HL_URLS.get(config.base_url.rstrip('/'))
            if environment is None:
                raise ValueError('An official Hyperliquid environment is required')
            # Every account read receives the explicit user; configured wallets are irrelevant.
            inferred = Scope(venue, environment, account)
    scope = scope or inferred
    if scope is None or (scope.venue, scope.account) != (venue, account):
        raise ValueError('Explicit matching account scope required')
    validated = Scope(scope.venue, scope.environment, scope.account)
    if inferred is not None and inferred != validated:
        raise ValueError('Client environment differs from requested scope')
    return client, validated


def collect_bundle(venue, account, *, start_ms, end_ms, client=None, scope=None):
    """Capture an explicit half-open range; pagination success is not certification.

    KIS expands the interval to full Seoul dates and limits scope to domestic/US
    equities. Inventory snapshots are current observations, never historical facts.
    Errors abort collection, so no partial success bundle can escape this adapter.
    """
    if venue not in {'kis', 'hyperliquid'} or not isinstance(account, str) or not account.strip():
        raise ValueError('Explicit supported venue and account required')
    if (type(start_ms) is not int or type(end_ms) is not int
            or not 0 <= start_ms < end_ms):
        raise ValueError('Invalid account range')
    client, scope = _client_scope(venue, account, client, scope)
    if venue == 'kis' and scope.environment != 'live':
        raise ValueError('KIS audit profit and transaction routes require a live account')
    requested_end = end_ms
    bundle = dict(schema_version=1, kind='account-audit-bundle',
                  account={'venue': venue, 'environment': scope.environment, 'native_id': account},
                  start_ms=start_ms, end_ms=end_ms, collected_ms=now_ms(),
                  collection_complete=False, findings=[], sources=[], evidence=[],
                  positions=[], inventory_complete=False)

    def finding(code, message):
        bundle['findings'].append({'code': code, 'severity': 'warning', 'message': message})

    def observe(dataset, body, raw=None, parameters=None):
        entry = {'dataset': dataset, 'body': body}
        if parameters is not None:
            entry['parameters'] = dict(parameters)
        candidate = raw if raw is not None else getattr(client, 'last_raw_body', None)
        if candidate is not None:
            try:
                text = candidate.decode('utf-8') if isinstance(candidate, bytes) else candidate
                if json.loads(text) == body:
                    entry['raw'] = text
                elif raw is not None:
                    raise ValueError('Raw response differs from decoded evidence')
            except (UnicodeError, json.JSONDecodeError, TypeError):
                if raw is not None:
                    raise ValueError('Invalid raw response evidence') from None
        bundle['evidence'].append(entry)

    if venue == 'hyperliquid':
        for parser, method, limit in [('hl_fills', client.user_fills_by_time, 2000),
                                      ('hl_funding', client.user_funding, 500)]:
            def fetch(a, b):
                rows = method(start_time_ms=a, end_time_ms=b, user=account)
                observe(parser, rows)
                return rows
            rows = fetch_time_pages(fetch, start_ms, end_ms - 1, limit=limit)
            bundle['sources'].append({'parser': parser, 'data': rows})
        tail = client.user_fills(user=account)
        observe('hl_retained_tail', tail)
        if not isinstance(tail, list) or any(
                not isinstance(row, dict) or type(row.get('time')) is not int
                or row['time'] < 0 for row in tail):
            raise ValueError('Malformed retention anchor')
        anchor = min((row['time'] for row in tail), default=None)
        bundle['retention_anchor_ms'] = anchor
        if anchor is None or start_ms < anchor:
            finding('retention_unverified', 'Requested history precedes or lacks a retained fills anchor')
        finding('funding_retention_unverified', 'Funding pagination does not independently certify historical retention')
        dexes = [None]
        discovery_complete = False
        if callable(getattr(client, 'post_info', None)):
            discovered = client.post_info({'type': 'perpDexs'})
            observe('hl_perp_dexs', discovered)
            if not isinstance(discovered, list):
                raise ValueError('Malformed perpetual DEX discovery')
            for dex in discovered:
                if dex is None:
                    continue
                if not isinstance(dex, dict) or not isinstance(dex.get('name'), str) or not dex['name'].strip():
                    raise ValueError('Malformed perpetual DEX discovery')
                if dex['name'] not in dexes:
                    dexes.append(dex['name'])
            discovery_complete = True
        else:
            finding('dex_scope_unverified', 'Client cannot discover all perpetual DEXes')
        positions = {}
        for dex in dexes:
            body = client.clearinghouse_state(user=account, dex=dex)
            observe('hl_positions:' + (dex or ''), body)
            if not isinstance(body, dict) or not isinstance(body.get('assetPositions'), list):
                raise ValueError('Malformed perpetual inventory')
            for row in body['assetPositions']:
                if not isinstance(row, dict) or not isinstance(row.get('position'), dict):
                    raise ValueError('Malformed perpetual position')
                position = row['position']
                coin = position.get('coin')
                if not isinstance(coin, str) or not coin or (dex and not coin.startswith(dex + ':')):
                    raise ValueError('Invalid perpetual inventory instrument')
                instrument = 'hl:' + coin
                quantity = number(position['szi'])
                if instrument in positions:
                    raise ValueError('Duplicate perpetual inventory instrument')
                positions[instrument] = quantity
        bundle['positions'] = [{'instrument': key, 'quantity': value} for key, value in sorted(positions.items())]
        bundle['inventory_scope'] = {'market': 'perpetuals', 'dexes': [dex or '' for dex in dexes]}
        if callable(getattr(client, 'spot_clearinghouse_state', None)):
            observe('hl_spot_positions', client.spot_clearinghouse_state(user=account))
        bundle['inventory_complete'] = discovery_complete
    else:
        zone = ZoneInfo('Asia/Seoul')
        first = (_EPOCH + timedelta(milliseconds=start_ms)).astimezone(zone).date()
        last = (_EPOCH + timedelta(milliseconds=end_ms - 1)).astimezone(zone).date()
        midnight = lambda day: datetime.combine(day, datetime.min.time(), tzinfo=zone)
        bundle['start_ms'] = max(0, _millis(midnight(first)))
        bundle['end_ms'] = _millis(midnight(last + timedelta(days=1)))
        bundle['requested_start_ms'], bundle['requested_end_ms'] = start_ms, end_ms

        def page(response):
            observe('kis_account_page', response.body, response.raw_body)

        def query(kind, **kwargs):
            result = client.account_pages(kind, page_observer=page, max_pages=100, **kwargs)
            if not isinstance(result, dict) or result.get('complete') is not True:
                raise RuntimeError('Incomplete KIS account collection')
            for field in ('output1', 'output2'):
                if not isinstance(result.get(field), list) or any(not isinstance(r, dict) for r in result[field]):
                    raise ValueError('Malformed KIS account collection')
            observe('kis_' + kind, result, parameters=kwargs)
            return result

        windows = []
        cursor = first
        while cursor <= last:
            # Ten calendar years inclusive, including a leap-day starting point.
            try:
                anniversary = cursor.replace(year=cursor.year + 10)
            except ValueError:
                anniversary = cursor.replace(year=cursor.year + 10, day=28)
            stop = min(last, anniversary - timedelta(days=1))
            windows.append((cursor.strftime('%Y%m%d'), stop.strftime('%Y%m%d')))
            cursor = stop + timedelta(days=1)
        days, orders, costs = {}, {}, {}
        overseas = {}
        for date_from, date_to in windows:
            dates = {'date_from': date_from, 'date_to': date_to}
            for row in query('domestic_trade_profit', **dates)['output1']:
                key = row['trad_dt'] + ':' + row['pdno']
                if key in days and days[key] != row:
                    raise ValueError('Conflicting domestic daily snapshots')
                days[key] = row
            for older in (False, True):
                for row in query('domestic_history', older_history=older, **dates)['output1']:
                    key = encode([row['ord_dt'], row['pdno'], row['odno'], row['ord_gno_brno']])
                    if key in orders and orders[key] != row:
                        raise ValueError('Conflicting overlapping domestic order snapshots')
                    orders[key] = row
            for exchange in ('NASD', 'NYSE', 'AMEX'):
                for row in query('overseas_transactions', exchange=exchange, **dates)['output1']:
                    key = encode([row['trad_dt'], row['pdno'], row['sll_buy_dvsn_cd'],
                                  row['crcy_cd'], row.get('loan_dvsn_cd', '')])
                    if key in overseas and overseas[key] != row:
                        raise ValueError('Conflicting overseas daily snapshots')
                    overseas[key] = row
        for key, day in sorted(days.items()):
            result = query('domestic_trade_profit', symbol=day['pdno'],
                           date_from=day['trad_dt'], date_to=day['trad_dt'])
            if len(result['output2']) != 1:
                raise ValueError('Ambiguous daily cost summary')
            costs[key] = result['output2'][0]
        domestic = {'days': list(days.values()), 'orders': list(orders.values()), 'costs_by_day_symbol': costs}
        validate_domestic_orders(domestic)
        bundle['sources'] = [{'parser': 'kis_domestic_bundle', 'data': domestic},
                             {'parser': 'kis_overseas_trans', 'data': list(overseas.values())}]
        positions = {}
        for kind, exchange in [('domestic_balance', None), ('overseas_balance', 'NASD'),
                               ('overseas_balance', 'NYSE'), ('overseas_balance', 'AMEX')]:
            args = {'exchange': exchange} if exchange else {}
            for row in query(kind, **args)['output1']:
                symbol = row.get('pdno' if kind == 'domestic_balance' else 'ovrs_pdno')
                if not isinstance(symbol, str) or not symbol.strip():
                    raise ValueError('Invalid KIS inventory instrument')
                quantity = number(row['hldg_qty' if kind == 'domestic_balance' else 'ovrs_cblc_qty'])
                if Decimal(quantity) < 0:
                    raise ValueError('Negative KIS cash inventory')
                instrument = 'kis:' + symbol
                if instrument in positions and positions[instrument] != quantity:
                    raise ValueError('Conflicting KIS inventory snapshots')
                positions[instrument] = quantity
        bundle['positions'] = [{'instrument': key, 'quantity': value} for key, value in sorted(positions.items())]
        bundle['inventory_scope'] = {'markets': ['domestic', 'NASD', 'NYSE', 'AMEX'], 'currency_overseas': 'USD'}
        finding('limited_market_scope', 'KIS capture covers domestic and US equities; other overseas markets are unverified')
        finding('retention_unverified', 'KIS dated pages do not certify historical retention or opening inventory')

    bundle['collected_ms'] = now_ms()
    bundle['inventory_observed_ms'] = bundle['collected_ms']
    if not 0 <= bundle['collected_ms'] - requested_end <= 60000:
        bundle['inventory_complete'] = False
        finding('historical_inventory', 'Current inventory cannot certify the requested historical ending inventory')
    bundle['collection_complete'] = True
    return bundle
