import copy,json,socket
from unittest.mock import patch
from tests.test_conditional_add import ConditionalAddTests, NOW, capital
from tests.test_managed_execution import plan
from kis_hl.strategy_signals import Signals

results=[]
with patch.object(socket,'socket',side_effect=AssertionError('Network forbidden')):
 for source,delay in [('setup',9000),('setup',10500),('capital',10500)]:
  c=ConditionalAddTests();c.setUp()
  try:
   if source=='setup':
    signal=copy.deepcopy(c.signal);signal['id']='short-source';signal['setup_input']['snapshot']['max_age_ms']=10000
    c.signals.ingest(signal,now_ms=NOW)
    c.signals.execute('short-source','scope',c.plan,manual=True,live=True,now_ms=NOW+5)
   else:
    c.plan['capital_evidence']['max_age_ms']=10000
    c.authorize()
   c.g.balance=capital(now=NOW+delay)
   with patch.object(c.g,'preflight',wraps=c.g.preflight) as read:
    c.worker.step(c.row['id'],NOW+delay)
    t=c.store.tranches(c.row['id'])[0]
    results.append(dict(case=source,delay_ms=delay,approval_ms_remaining=c.plan['expires_ms']-(NOW+delay),status=t['status'],reason=t.get('reason'),preflight_calls=read.call_count,add_submissions=len([a for a in c.g.sent if a['kind']=='add'])))
   assert t['status']==('SUBMITTED' if delay==9000 else 'REJECTED')
  finally:c.doCleanups()
 for state in ('QUEUED','ENTERING','PROTECTING'):
  c=ConditionalAddTests();c.setUp()
  try:
   c.authorize()
   other=c.store.enqueue('scope',{**plan(), 'intent_id':'other', 'expires_ms':NOW+50000},live=True,now_ms=NOW)
   other['state']=state;c.store.save(other,NOW+6)
   c.worker.step(c.row['id'],NOW+10)
   before=c.store.tranches(c.row['id'])[0]
   other['state']='CLOSED';c.store.save(other,NOW+11)
   c.worker.step(c.row['id'],NOW+12)
   after=c.store.tranches(c.row['id'])[0]
   assert before['status']==after['status']=='REJECTED'
   assert not any(a['kind']=='add' for a in c.g.sent)
   results.append(dict(case='other-position-'+state,initial_status=before['status'],reason=before.get('reason'),after_other_closed=after['status'],add_submissions=0))
  finally:c.doCleanups()
print(json.dumps(results,indent=2))
