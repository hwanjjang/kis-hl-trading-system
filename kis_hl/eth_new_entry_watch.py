"""Once-only manually approved ETH NEW watch; paper/read-only unless --live."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
import json
from pathlib import Path
import time

from kis_hl.intraday_add import confirm_breakout, AddConditionPending
from kis_hl.journal_sync import Scope, decimal
from kis_hl.percentage_entry import prepare_entry

ACCOUNT = '0x1dac321cd9a14a9a6da3ae155601c6cc38a748b4'
EXPIRES_MS = int(datetime(2026,10,2,19,55,tzinfo=timezone.utc).timestamp()*1000)
DECISION = 'AK-ETH-NEW-20261002'
INSTRUMENT = 'hl:ETH'
ROOT = Path(__file__).resolve().parents[1]


def utc_ms(value):
    stamp = datetime.fromisoformat(value.replace('Z','+00:00'))
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError('Authorization timestamp must be explicit UTC')
    return int(stamp.timestamp()*1000)


def draft(scope, authorized_ms, close, *, live=False):
    # ATR fields are schema placeholders, never collected or used for exits.
    price = (decimal(close)*Decimal('1.003')).quantize(Decimal('.1'), rounding=ROUND_DOWN)
    p = dict(intent_id=DECISION, instrument=INSTRUMENT, signal_instrument=INSTRUMENT,
        strategy='manual-eth-adjacent-utc9m-new', strategy_version='1', quantity='.01',
        limit_price=str(price), atr='1', atr_multiple='1', fixed_stop_price='2610',
        trailing_provider='native', native_trailing_percent='8.35', local_trailing_backup=False,
        entry_route='limit', allow_local_sl=False, max_notional='2000', max_loss='1',
        max_portfolio_notional='3000', max_correlated_notional='2000', max_spread_bps='30',
        max_entry_deviation_bps='30', max_quote_age_ms=30000, slippage='.003',
        protection_grace_ms=120000, max_exit_attempts=3, exit_deadline_ms=120000,
        exit_reprice_ms=5000, expires_ms=EXPIRES_MS)
    fields = ('fixed_stop_price','native_trailing_percent','max_notional','max_portfolio_notional',
              'max_correlated_notional','max_spread_bps','max_quote_age_ms','slippage',
              'protection_grace_ms','max_exit_attempts','exit_deadline_ms','exit_reprice_ms')
    a = {k:p[k] for k in fields}
    a.update(manual=True,scope=scope,mode='live' if live else 'paper',instrument=INSTRUMENT,
             intent_id=DECISION,authorized_ms=authorized_ms,expires_ms=EXPIRES_MS,units='0.2')
    return dict(p,percentage_entry_authorization=a)


def review(gateway, *, authorized_ms, now_ms, live=False):
    if now_ms >= EXPIRES_MS:
        return {'status':'expired','expires_ms':EXPIRES_MS}
    if not 0 <= authorized_ms <= now_ms < EXPIRES_MS:
        raise ValueError('Invalid approved watch window')
    try:
        bars = gateway.completed_nine_minute_bars(INSTRUMENT, now_ms)
        bar = confirm_breakout(bars, authorized_ms, now_ms, 30000)
    except AddConditionPending as exc:
        return {'status':'waiting','reason':str(exc),'asof_ms':now_ms}
    p = draft(gateway.scope, authorized_ms, bar['close'], live=live)
    pre = gateway.preflight(p, now_ms)
    now = int(pre.get('observed_now_ms',now_ms))
    p = prepare_entry(gateway.scope, 'live' if live else 'paper', p, pre, bars, now)
    bid, ask = decimal(pre['price']),decimal(pre['ask'])
    notional = decimal(p['quantity'])*decimal(p['limit_price'])
    if (not pre['eligible'] or not pre['session_open'] or decimal(pre['position']) != 0
            or pre['open_orders'] or not 0 <= now-int(pre['time_ms']) <= 30000
            or ask < bid or (ask-bid)/bid*10000 > 30
            or notional > decimal(pre['available_notional'])
            or notional+decimal(pre['portfolio_notional']) > 3000
            or notional+decimal(pre['correlated_notional']) > 2000):
        raise ValueError('ETH NEW fresh flat-account/quote/funds/portfolio preflight not ready')
    return {'status':'ready','mode':'live' if live else 'paper','asof_ms':now,'plan':p}


def handoff(store, result, scope, now):
    """No signed writes: supervisor alone can dispatch; stable intent claims once."""
    if result['status'] != 'ready':
        raise ValueError('No fresh ready NEW entry')
    with store.connect() as db:
        supervisor = db.execute('SELECT heartbeat_ms,mode,entries_enabled FROM managed_supervisors WHERE scope=?',(scope,)).fetchone()
        peers = db.execute("SELECT 1 FROM managed_positions WHERE scope=? AND mode='live' AND state NOT IN ('CLOSED','REJECTED','PREVIEWED','QUEUED','PROTECTED')",(scope,)).fetchone()
    if (not supervisor or supervisor['mode'] != 'live' or supervisor['entries_enabled'] != 1
            or not 0 <= now-supervisor['heartbeat_ms'] <= 30000 or peers):
        raise ValueError('Healthy enabled live supervisor and reconciled account owners required')
    p = result['plan']; a = p['percentage_entry_authorization']
    confirm_breakout(p['condition_bars'],a['authorized_ms'],now,30000)
    return store.enqueue_percentage_new_entry(scope,p,manual=True,live=True,now_ms=now,
        authorized_ms=a['authorized_ms'],decision_expires_ms=EXPIRES_MS,units='0.2')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorized-utc',required=True,help='Original approval timestamp, never a renewal')
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--watch',action='store_true',help='Poll public reads every five seconds until ready or original expiry')
    parser.add_argument('--manual-authorization',choices=[DECISION])
    parser.add_argument('--execution-db',default=str(ROOT/'data/kis_hl.sqlite'))
    args=parser.parse_args(argv)
    if args.live and args.manual_authorization != DECISION:
        parser.error('--live requires explicit --manual-authorization '+DECISION)
    authorized=utc_ms(args.authorized_utc); now=int(time.time()*1000)
    if now >= EXPIRES_MS:
        print(json.dumps({'status':'expired','expires_ms':EXPIRES_MS})); return 0
    if Path(args.execution_db).resolve() != (ROOT/'data/kis_hl.sqlite').resolve():
        parser.error('Use the existing shared operational DB, not a shadow execution database')
    from kis_hl.config import load_env_file
    from kis_hl.operations_cli import scope_client
    from kis_hl.hyperliquid.client import HyperliquidTradingClient
    from kis_hl.managed_gateways import ManagedHyperliquidGateway
    load_env_file(ROOT/'.env')
    scope,info=scope_client('hyperliquid')
    expected=Scope('hyperliquid','mainnet',ACCOUNT).key
    if scope.key != expected or info.config.base_url.rstrip('/') != 'https://api.hyperliquid.xyz':
        raise ValueError('Exact approved ETH execution account and official mainnet required')
    gateway=ManagedHyperliquidGateway(info,HyperliquidTradingClient(info.config,verification_db_path=args.execution_db))
    while True:
        now=int(time.time()*1000)
        try:
            result=review(gateway,authorized_ms=authorized,now_ms=now,live=args.live)
            if args.live and result['status']=='ready':
                from kis_hl.managed_execution import ExecutionStore
                row=handoff(ExecutionStore(args.execution_db),result,scope.key,int(time.time()*1000))
                result['owner']={'id':row['id'],'state':row['state']}
        except (ValueError, OSError) as exc:
            result={'status':'blocked','reason':str(exc) if isinstance(exc,ValueError) else type(exc).__name__}
        except RuntimeError as exc:
            # Duplicate/uncertain handoff is terminal: never renew or blindly retry.
            import traceback
            traceback.print_exc()
            print(json.dumps({'status':'intervention','reason':'Read or once-intent handoff failed; inspect owner state',
                              'error_type':type(exc).__name__}),flush=True)
            return 2
        print(json.dumps(result,default=str),flush=True)
        if not args.watch or result['status'] in {'ready','expired'}:
            return 0
        time.sleep(min(5,max(0,(EXPIRES_MS-int(time.time()*1000))/1000)))


if __name__=='__main__': raise SystemExit(main())
