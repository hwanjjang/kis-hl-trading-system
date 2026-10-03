"""Explicit manual NEW percentage policy; deterministic checks, no order transport."""
from decimal import Decimal, ROUND_DOWN
from kis_hl.journal_sync import decimal
from kis_hl.intraday_add import confirm_breakout


def check_authority(scope, mode, p, now):
    a = p.get('percentage_entry_authorization', {})
    if (a.get('manual') is not True or a.get('scope') != scope or a.get('mode') != mode
            or a.get('intent_id') != p.get('intent_id') or a.get('instrument') != p.get('instrument')
            or not p['instrument'].startswith('hl:') or not p.get('native_trailing_percent')
            or p.get('trailing_provider') != 'native' or p.get('local_trailing_backup') is not False
            or p.get('allow_local_sl') is not False or p.get('entry_route') != 'limit'
            or p.get('signal_id') or p.get('grant_id') or p.get('position_id') or p.get('action') == 'add'
            or type(a.get('authorized_ms')) is not int or not 0 <= a['authorized_ms'] <= now
            or type(a.get('expires_ms')) is not int or now >= a['expires_ms']
            or p['expires_ms'] > a['expires_ms']):
        raise ValueError('Explicit manual scoped NEW percentage entry authority required')
    for field in ('fixed_stop_price', 'native_trailing_percent', 'max_notional',
                  'max_portfolio_notional', 'max_correlated_notional', 'max_spread_bps',
                  'max_quote_age_ms', 'slippage', 'protection_grace_ms', 'max_exit_attempts',
                  'exit_deadline_ms', 'exit_reprice_ms'):
        if p.get(field) != a.get(field):
            raise ValueError('NEW percentage entry authorized policy changed')
    decimal(a.get('units'), positive=True)


def prepare_entry(scope, mode, p, snap, bars, now):
    from kis_hl.conditional_add import size_add
    from kis_hl.account_capital import reconcile_capital
    from kis_hl.managed_execution import validate_plan
    check_authority(scope, mode, p, now)
    a = p['percentage_entry_authorization']
    bar = confirm_breakout(bars, a['authorized_ms'], now, p['max_quote_age_ms'])
    if p.get('condition_bar_end_ms') not in (None, bar['end_ms']):
        raise ValueError('NEW entry trigger changed; fresh review required')
    cap = decimal(bar['close']) * Decimal('1.003')
    tick = max(decimal(snap['price_step'], positive=True), min(Decimal(1), Decimal(10)**(cap.adjusted()-4)))
    price = (cap/tick).to_integral_value(rounding=ROUND_DOWN)*tick
    if decimal(snap['ask'], positive=True) > price:
        raise ValueError('NEW entry ask exceeds inward hard price cap')
    candidate = dict(p, limit_price=str(price), units=a['units'], hard_price_cap=str(cap),
                     condition_bars=bars, condition_bar_end_ms=bar['end_ms'],
                     expires_ms=min(p['expires_ms'], bar['end_ms']+p['max_quote_age_ms']))
    evidence = snap.get('capital_evidence')
    capital = reconcile_capital(evidence, scope=scope, now_ms=now, max_age_ms=p['max_quote_age_ms'])
    sized = size_add(candidate, scope, evidence, now, quantity_step=snap['quantity_step'])
    if sized['below_minimum']:
        raise ValueError('NEW percentage entry below exchange minimum')
    candidate.update(quantity=sized['quantity'], max_loss=str(decimal(capital['total_balance'])*Decimal('.02')),
                     capital_evidence=evidence, sizing=sized,
                     execution_quote={'time_ms':int(snap['time_ms']), 'ask':str(snap['ask'])})
    return validate_plan(candidate, now)


def check_send(row, attempt, now):
    """Last transport boundary: never turn the cap into an SDK market price."""
    p = row['plan']
    from kis_hl.managed_execution import validate_plan
    from kis_hl.account_capital import reconcile_capital
    validate_plan(p, now)
    reconcile_capital(p.get('capital_evidence'), scope=row['scope'], now_ms=now,
                      max_age_ms=p['max_quote_age_ms'])
    check_authority(row['scope'], row['mode'], p, now)
    a = p['percentage_entry_authorization']
    bar = confirm_breakout(p['condition_bars'], a['authorized_ms'], now, p['max_quote_age_ms'])
    cap = decimal(bar['close']) * Decimal('1.003')
    if (not 0 <= now-p['execution_quote']['time_ms'] <= p['max_quote_age_ms']
            or attempt.get('order_type') != 'limit' or decimal(attempt['price']) > cap
            or decimal(attempt['price']) != decimal(p['limit_price'])
            or decimal(attempt['quantity']) != decimal(p['quantity'])
            or now >= p['expires_ms']):
        raise ValueError('NEW percentage entry hard send boundary violated')
