from copy import deepcopy
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest

from kis_hl.trailing import Trail
from kis_hl.trailing_storage import TrailStore
from kis_hl.trailing_runner import TrailingRunner


class FakeGateway:
    def __init__(self):
        self.data={'size':'1','entry':'100','generation_ok':True,'protection':True,
                   'stop_open':True,'order_states':{}}
        self.sent=[]
        self.canceled=[]
        self.timeout=False
    def snapshot(self, row, attempts, now_ms): return deepcopy(self.data)
    def submit(self, row, attempt):
        self.sent.append(attempt)
        if self.timeout: raise TimeoutError('response lost')
        return {'status':'ok','response':{'data':{'statuses':[{'filled':{'oid':88,'totalSz':'1'}}]}}}
    def cancel_stop(self, row): self.canceled.append(row['stop_oid'])


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store=TrailStore(Path(self.tmp.name)/'state.sqlite')
        self.row=self.store.enroll({'account':'acct','network':'test','coin':'BTC','symbol':'BTC-PERP',
            'mode':'live','state':'RECOVERING','size':'1','entry':'100','stop_oid':7,'sz_decimals':3,
            'max_gap_ms':15000,'slippage':'0.01','max_attempts':3,'exit_timeout_ms':120000,
            'trail':Trail.create(entry=D('100'),atr=D('2'),multiple=D('2'),opened_ms=0).to_dict()})
        self.g=FakeGateway(); self.runner=TrailingRunner(self.store,self.row['id'],self.g)

    def test_timeout_and_restart_never_resends_unknown(self):
        self.g.timeout=True
        self.runner.on_tick(100,D('95'))
        self.assertEqual(len(self.g.sent),1)
        again=TrailingRunner(self.store,self.row['id'],self.g)
        again.on_tick(200,D('94'))
        self.assertEqual(len(self.g.sent),1)
        self.assertEqual(self.store.attempts(self.row['id'])[0]['status'],'UNKNOWN')

    def test_partial_fill_retries_only_after_terminal_confirmation(self):
        self.runner.on_tick(100,D('95'))
        attempt=self.g.sent[0]
        self.g.data['size']='0.4'
        self.g.data['order_states'][attempt['cloid']]='filled'
        self.runner.on_tick(10100,D('94'))
        self.assertEqual(len(self.g.sent),2)
        self.assertEqual(self.g.sent[1]['size'],'0.400')
        self.assertNotEqual(self.g.sent[1]['cloid'],attempt['cloid'])

    def test_native_stop_race_flat_requires_cleanup_confirmation(self):
        self.runner.on_tick(100,D('95'))
        self.g.data['size']='0'
        self.g.data['order_states'][self.g.sent[0]['cloid']]='reduceOnlyCanceled'
        self.runner.on_tick(10100,D('94'))
        self.assertEqual(len(self.g.sent),1)
        self.assertEqual(self.g.canceled,[7])
        self.assertEqual(self.runner.row['state'],'FLAT_CLEANUP')
        self.g.data['stop_open']=False
        self.runner.on_tick(20100,D('94'))
        self.assertEqual(self.runner.row['state'],'CLOSED')

    def test_stale_price_cannot_submit(self):
        self.runner.on_tick(100,D('95'),age_ms=20000)
        self.assertFalse(self.g.sent)
        self.assertEqual(self.runner.row['state'],'DEGRADED')

    def test_unexpected_increase_or_reversal_requires_intervention(self):
        for size in ['2','-1']:
            self.g.data['size']=size
            self.runner.on_tick(100,D('95'))
            self.assertEqual(self.runner.row['state'],'MANUAL_INTERVENTION')
            self.assertFalse(self.g.sent)

    def test_missing_protection_does_not_claim_protected(self):
        self.g.data['protection']=False
        self.runner.on_tick(100,D('99'))
        self.assertEqual(self.runner.row['state'],'MANUAL_INTERVENTION')
        self.assertFalse(self.g.sent)

    def test_paper_tick_records_intent_without_external_mutations(self):
        self.runner.row['mode']='paper'
        self.store.save(self.runner.row,'test paper')
        self.runner.on_tick(100,D('95'))
        self.assertEqual(self.runner.row['state'],'PAPER_EXIT')
        self.assertTrue(self.store.intent(self.row['id']))
        self.assertFalse(self.g.sent)

    def test_external_generation_change_blocks_cleanup_of_other_position(self):
        self.g.data.update(size='0',generation_ok=False)
        self.runner.on_tick(100,D('95'))
        self.assertEqual(self.runner.row['state'],'MANUAL_INTERVENTION')
        self.assertFalse(self.g.canceled)

    def test_manual_intervention_remains_latched_after_restart(self):
        self.g.data['protection']=False
        self.runner.on_tick(100,D('95'))
        self.g.data['protection']=True
        restarted=TrailingRunner(self.store,self.row['id'],self.g)
        self.assertFalse(restarted.reconcile(10000))
        self.assertEqual(restarted.row['state'],'MANUAL_INTERVENTION')

    def test_retry_cap_and_deadline_do_not_reset_after_restart(self):
        self.runner.row['max_attempts']=1
        self.store.save(self.runner.row,'test cap')
        self.runner.on_tick(100,D('95'))
        self.g.data['order_states'][self.g.sent[0]['cloid']]='filled'
        self.g.data['size']='0.4'
        restarted=TrailingRunner(self.store,self.row['id'],self.g)
        restarted.on_tick(10100,D('94'))
        self.assertEqual(len(self.g.sent),1)
        self.assertEqual(restarted.row['state'],'MANUAL_INTERVENTION')

    def test_deadline_stops_even_an_unknown_attempt(self):
        self.runner.on_tick(100,D('95'))
        self.runner.on_tick(120101,D('94'))
        self.assertEqual(len(self.g.sent),1)
        self.assertEqual(self.runner.row['state'],'MANUAL_INTERVENTION')

    def test_persist_verified_coverage_and_partial_manual_close(self):
        self.runner.reconcile(100)
        self.g.data['size']='0.5'
        self.runner.reconcile(10100)
        row=self.store.get(self.row['id'])
        self.assertEqual(row['size'],'0.5')
        self.assertEqual(row['protection_verified_ms'],10100)

    def test_snapshot_failure_and_unknown_cleanup_cannot_close(self):
        self.g.data['size']='0'
        self.runner.on_tick(100,D('95'))
        self.assertEqual(self.runner.row['state'],'FLAT_CLEANUP')
        def fail(*a): raise TimeoutError('offline')
        self.g.snapshot=fail
        self.runner.on_tick(10100,D('94'))
        self.assertEqual(self.runner.row['state'],'RECONCILING')
        self.assertFalse(self.g.sent)

    def test_price_age_includes_initial_and_presubmit_reconciliation(self):
        from unittest.mock import patch
        clock = [0.0]
        original = self.g.snapshot
        def slow_snapshot(*args):
            clock[0] += 10.0
            return original(*args)
        self.g.snapshot = slow_snapshot
        with patch('kis_hl.trailing_runner.time.monotonic', side_effect=lambda: clock[0]):
            self.runner.on_tick(100,D('95'))
        self.assertFalse(self.g.sent)
        self.assertEqual(self.runner.row['state'],'DEGRADED')
