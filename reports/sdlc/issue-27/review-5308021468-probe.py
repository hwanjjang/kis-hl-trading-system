import json, socket
from unittest.mock import patch
from tests.test_conditional_add import ConditionalAddTests, NOW, sizing
from kis_hl.managed_execution import ExecutionStore, Supervisor
from kis_hl.strategy_signals import Signals
from kis_hl.strategy_tools import size_position

results=[]
def case():
    c=ConditionalAddTests();c.setUp();return c
with patch.object(socket, 'socket', side_effect=AssertionError('Network forbidden')):
    for status in ('canceled','rejected','expired','filled'):
        c=case()
        try:
            c.test_native_overlay_preserves_old_watermark_and_covers_combined_size()
            trails=[a for a in c.g.sent if a['kind']=='trailing']
            c.g.orders[trails[0]['id']]['status']=status
            if status=='filled': c.g.size='0.5';c.g.protective_filled='1'
            r=c.worker.step(c.row['id'],NOW+20)
            exits=[a['quantity'] for a in c.g.sent if a['kind']=='exit']
            results.append(dict(case='old-trail-'+status,overlay_status=c.g.orders[trails[1]['id']]['status'],overlay_size=c.g.orders[trails[1]['id']]['size'],remaining=c.g.size,exit_quantities=exits,state=r['state'],covered=r['trailing_covered_size']))
            assert exits == ['0.5' if status=='filled' else '1.5']
        finally: c.doCleanups()
    c=case()
    try:
        c.native_fixture()
        old=next(a for a in c.g.sent if a['kind']=='trailing')
        c.g.orders[old['id']]['status']='canceled'
        r=c.worker.step(c.row['id'],NOW+20)
        exits=[a['quantity'] for a in c.g.sent if a['kind']=='exit']
        assert exits==['1']
        results.append(dict(case='single-trail-canceled',exit_quantities=exits,state=r['state']))
    finally: c.doCleanups()
    for error in (OSError,RuntimeError):
        c=case()
        try:
            t=c.authorize();original=c.g.preflight
            def fail(*a,**kw):raise error('temporary read failure')
            c.g.preflight=fail
            c.worker.step(c.row['id'],NOW+10)
            c.g.preflight=original
            store=ExecutionStore(c.path)
            replay=Signals(store).execute('add-once','scope',c.plan,manual=True,live=True,now_ms=NOW+11)
            Supervisor(store,c.g,live=True).step(c.row['id'],NOW+12)
            t=store.tranches(c.row['id'])[0]
            adds=[a for a in c.g.sent if a['kind']=='add']
            assert t['status']=='REJECTED' and not adds
            results.append(dict(case=error.__name__,tranche_status=t['status'],add_submissions=len(adds),same_tranche=replay['id']==t['id']))
        finally:c.doCleanups()
    for field in ('evmEscrows','borrowed','supplied'):
        request=sizing()
        spot=request['capital_evidence']['spot']
        if field=='evmEscrows':spot[field]=[dict(coin='HYPE',token=150,total='10')]
        else:spot['balances'][0][field]='500'
        r=size_position(request,now_ms=NOW)
        assert r['equity']=='1000'
        results.append(dict(case=field,result='accepted',equity=r['equity'],operating_capital=r['operating_capital'],risk_budget=r['risk_budget']))
print(json.dumps(results,indent=2))
