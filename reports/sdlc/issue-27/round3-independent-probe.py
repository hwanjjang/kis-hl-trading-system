import json,socket
from types import SimpleNamespace
from unittest.mock import patch
from tests.test_conditional_add import ConditionalAddTests,NOW
from tests.test_managed_execution import plan
from kis_hl.operations_cli import cmd_supervisor

results=[]
def case():
    c=ConditionalAddTests();c.setUp();return c

def grant(c):
    c.signals.grant(dict(id='peer-grant',scope='scope',strategy='fixture',strategy_version='1',instruments=['hl:ETH'],max_notional='100',max_intents=1,live=True,actions=['add'],signal_ids=['add-once'],position_ids=[c.row['id']],expires_ms=NOW+50000),now_ms=NOW)
    c.signals.execute('add-once','scope',c.plan,grant_id='peer-grant',live=True,now_ms=NOW+5)

def dump(c):
    with c.store.connect() as db:return list(db.iterdump())

with patch.object(socket,'socket',side_effect=AssertionError('Network forbidden')):
    for state in ('DEGRADED','ADOPTING'):
        c=case()
        try:
            grant(c);c.other_position(state)
            with patch.object(c.g,'preflight',wraps=c.g.preflight) as reads:
                c.worker.step(c.row['id'],NOW+10)
                assert c.store.tranches(c.row['id'])[0]['status']=='QUEUED'
                c.signals.revoke('peer-grant');c.worker.step(c.row['id'],NOW+11)
                assert reads.call_count==0
            assert c.store.tranches(c.row['id'])[0]['status']=='REJECTED'
            assert not any(a['kind']=='add' for a in c.g.sent)
            results.append(dict(case='revoked-during-'+state,status='REJECTED',preflight_count=0,add_count=0))
        finally:c.doCleanups()
    for state in ('DEGRADED','ADOPTING'):
        c=case()
        try:
            c.authorize();peer=c.other_position(state);c.worker.step(c.row['id'],NOW+10)
            peer.update(state='PROTECTED',exit_requested_ms=NOW+11);c.store.save(peer,NOW+11)
            c.worker.step(c.row['id'],NOW+12)
            assert c.store.tranches(c.row['id'])[0]['status']=='REJECTED'
            assert not any(a['kind']=='add' for a in c.g.sent)
            results.append(dict(case='recovery-with-exit-from-'+state,status='REJECTED',add_count=0))
        finally:c.doCleanups()
    for state in ('CLOSED','REJECTED','PREVIEWED'):
        c=case()
        try:
            c.authorize();peer=c.other_position(state)
            peer.update(exit_requested_ms=NOW+6,cancel_entry=True,native_trailing_intervention=True);c.store.save(peer,NOW+6)
            c.worker.step(c.row['id'],NOW+10)
            assert len([a for a in c.g.sent if a['kind']=='add'])==1
            results.append(dict(case='finished-peer-'+state,add_count=1))
        finally:c.doCleanups()
    c=case()
    try:
        c.authorize();peer=c.store.enqueue('scope',{**plan(),'intent_id':'paper-peer','expires_ms':NOW+60000},live=False,now_ms=NOW)
        peer.update(state='INTERVENTION',exit_requested_ms=NOW+6);c.store.save(peer,NOW+6)
        c.worker.step(c.row['id'],NOW+10)
        assert len([a for a in c.g.sent if a['kind']=='add'])==1
        results.append(dict(case='other-mode-intervention',add_count=1))
    finally:c.doCleanups()
    c=case()
    try:
        tranche=c.authorize()
        for status in ('QUEUED','SUBMITTED','UNKNOWN','FILLED','CANCELED','REJECTED','EXPIRED'):
            tranche.update(status=status,filled='0.2',attempt_id='fixture-attempt',reason='Fixture pending detail')
            c.store.save_tranche(tranche);before=dump(c)
            with patch('kis_hl.operations_cli.scope_client',return_value=(SimpleNamespace(key='scope'),None)):
                result=cmd_supervisor(SimpleNamespace(venue='hyperliquid',db=c.path,action='status'))
            row=next(x for x in result['positions'] if x['id']==c.row['id'])
            pending=row['pending_adds']
            assert row['state']=='PROTECTED' and dump(c)==before
            if status in ('QUEUED','SUBMITTED','UNKNOWN'):
                assert pending==[dict(id=tranche['id'],signal_id='add-once',status=status,filled='0.2',attempt_id='fixture-attempt',reason='Fixture pending detail')]
            else:assert pending==[]
            assert c.store.tranches(c.row['id'])[0]['status']==status
            results.append(dict(case='status-'+status,pending_count=len(pending),database_unchanged=True))
    finally:c.doCleanups()
print(json.dumps(dict(result='passed',network='forbidden',cases=results),indent=2))
