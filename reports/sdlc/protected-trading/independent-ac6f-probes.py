"""Independent bounded correction checks; temporary SQLite and fixture transports only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch, Mock
from kis_hl.journal_sync import JournalLedger, Scope, SyncSchedule
from kis_hl.managed_execution import ExecutionStore, Supervisor, validate_plan
from tests.test_managed_execution import Gateway, plan
from tests.test_managed_gateways import ManagedGatewayTests
from tests.test_operations_cli import OperationsCliTests


def outage_probe(folder):
    store = ExecutionStore(folder / 'execution.sqlite')
    gateway = Gateway()
    gateway.native_sl = False
    worker = Supervisor(store, gateway, live=True)
    row = store.enqueue('scope', plan(), live=True, now_ms=1)
    worker.step(row['id'], 10)
    gateway.size = gateway.filled = '1'
    gateway.orders[gateway.sent[0]['id']]['status'] = 'filled'
    worker.step(row['id'], 20)
    snapshot = gateway.snapshot
    gateway.snapshot = lambda *a: (_ for _ in ()).throw(OSError('offline'))
    worker.step(row['id'], 30)
    original_fill = store.get(row['id'])['first_fill_ms']
    Supervisor(store, gateway, live=True).step(row['id'], 5031)
    failed = store.get(row['id'])
    assert failed['read_failures'] == 2 and failed['read_failure_exit']
    assert failed['exit_requested_ms'] == 5031 and failed['first_fill_ms'] == original_fill
    gateway.snapshot = snapshot
    Supervisor(store, gateway, live=True).step(row['id'], 5040)
    assert gateway.sent[-1]['kind'] == 'exit'
    assert store.get(row['id'])['exit_requested_ms'] == 5031
    # An ambiguous submission stays reserved through outage/restart/recovery.
    store = ExecutionStore(folder / 'unknown.sqlite')
    gateway = Gateway()
    gateway.submit = lambda *a: (_ for _ in ()).throw(TimeoutError('offline'))
    row = store.enqueue('scope', plan(), live=True, now_ms=1)
    Supervisor(store, gateway, live=True).step(row['id'], 10)
    snapshot = gateway.snapshot
    gateway.snapshot = lambda *a: (_ for _ in ()).throw(OSError('offline'))
    for now in [20, 30, 40]:
        Supervisor(store, gateway, live=True).step(row['id'], now)
    gateway.snapshot = snapshot
    Supervisor(store, gateway, live=True).step(row['id'], 50)
    attempts = store.attempts(row['id'])
    assert len(attempts) == 1 and attempts[0]['status'] == 'UNKNOWN'
    return 'F1 grace-budget restart, original clocks and UNKNOWN preservation passed'


def migration_probe(folder):
    path = folder / 'legacy.sqlite'
    scope = Scope('hyperliquid', 'testnet', 'migration-fixture')
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE journal_sync_schedule(scope TEXT PRIMARY KEY, interval_seconds INTEGER NOT NULL DEFAULT 10800, last_success_ms INTEGER,next_due_ms INTEGER NOT NULL DEFAULT 0)')
        db.execute('INSERT INTO journal_sync_schedule VALUES(?,60,100,60100)', (scope.key,))
    schedule = SyncSchedule(JournalLedger(path), scope)
    assert schedule.settings()['next_due_ms'] == 60100
    assert schedule.settings()['last_success_ms'] == 100
    assert schedule.settings()['last_attempt_ms'] is None
    schedule.attempted(200, 'offline failed collection')
    assert schedule.settings()['next_due_ms'] == 60200
    assert schedule.settings()['last_success_ms'] == 100
    schedule = SyncSchedule(JournalLedger(path), scope)
    assert not schedule.due(201)
    schedule.configure(120, now_ms=300)
    assert schedule.settings()['next_due_ms'] == 120200
    return 'F3 legacy migration preserves coverage/settings and persists failure pacing'


def failed_handler_probe():
    case = OperationsCliTests()
    case.setUp()
    scope = Scope('hyperliquid', 'testnet', 'failed-fixture')
    sleeps = []
    def sleep(_):
        sleeps.append(1)
        if len(sleeps) == 2:
            raise KeyboardInterrupt
    sync = Mock(side_effect=OSError('offline'))
    try:
        with patch('kis_hl.operations_cli.scope_client', return_value=(scope, None)), patch('kis_hl.operations_cli.sync_hyperliquid', sync), patch('kis_hl.operations_cli.time.sleep', side_effect=sleep):
            try:
                case.run_cli('journal', 'run', '--venue', 'hyperliquid', '--start-ms', '0')
            except KeyboardInterrupt:
                pass
        assert sync.call_count == 1
        schedule = SyncSchedule(JournalLedger(case.db), scope).settings()
        assert schedule['last_success_ms'] is None
        assert schedule['next_due_ms'] == schedule['last_attempt_ms'] + 10800000
        assert 'failed' in schedule['last_reason'].lower()
    finally:
        case.doCleanups()
    return 'F3 failed real CLI handler collection paced once over two polls; actual lock retained'


def baseline_probe():
    gateway, client = ManagedGatewayTests().kis()
    reads = []
    def pages(kind, **kwargs):
        if kind.endswith('_history'):
            reads.append(kwargs)
            return {'output1': []}
        return {'output': [{'ord_psbl_cash': '1000'}] if kind.endswith('_buying_power') else []}
    client.account_pages.side_effect = pages
    gateway._rows = lambda *a: []
    gateway._quote = lambda *a: (Decimal('100'), Decimal('100'), 20)
    gateway._atr = lambda *a: ('2', {'basis': 'offline'})
    gateway._session = lambda *a: True
    now = int(datetime(2026,9,12,15,1,tzinfo=timezone.utc).timestamp()*1000)
    p = plan(); p.update(instrument='kis:069500', verified_price_step='5')
    preflight = gateway.preflight(p, now)
    row = dict(created_ms=now-120000, plan=p, baseline=preflight['baseline'], baseline_start_ms=preflight['baseline_start_ms'])
    gateway.snapshot(row, [], now+1000)
    assert [r['date_from'] for r in reads] == ['20260913', '20260913']
    assert preflight['baseline_start_ms'] == now
    for value in ['0', '-1', 'NaN', 'Infinity']:
        p['verified_price_step'] = value
        try:
            validate_plan(p, 1)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid tick accepted')
    return 'F8 actual KIS history route preserves preflight KST date; F7 invalid ticks rejected'


with tempfile.TemporaryDirectory(prefix='independent-ac6f-') as temporary:
    folder = Path(temporary)
    results = [outage_probe(folder), migration_probe(folder), failed_handler_probe(), baseline_probe()]
print(json.dumps(dict(status='passed', checks=results, network_calls=0, exchange_orders=0), indent=2))
