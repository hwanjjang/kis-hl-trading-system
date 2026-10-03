import tempfile
import unittest
from pathlib import Path
from kis_hl.managed_execution import ExecutionStore, Supervisor
from tests.test_managed_execution import plan, Gateway
from tests.test_conditional_add import capital


class PercentageNewEntryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = ExecutionStore(Path(tmp.name)/'offline.sqlite')
        self.now = 1080001
        self.bars = [dict(start_ms=0, end_ms=540000, high='99', close='98'),
                     dict(start_ms=540000, end_ms=1080000, high='101', close='100')]
        self.p = plan(trailing_provider='native', native_trailing_percent='8.35',
                      local_trailing_backup=False, fixed_stop_price='95',
                      entry_route='limit') | dict(expires_ms=1110000, allow_local_sl=False, max_notional='500')
        self.p['intent_id'] = 'once-decision'
        self.g = Gateway(); self.g.native_trailing = True
        old = self.g.preflight
        self.g.preflight = lambda p, now: old(p, now) | {
            'entry_order_type':'limit', 'capital_evidence':capital('scope') | {'asof_ms':now}}
        self.g.completed_nine_minute_bars = lambda instrument, now: self.bars
        snapshot = self.g.snapshot
        self.g.snapshot = lambda row, attempts, now: snapshot(row, attempts, now) | {'fixed_stop_filled':'0'}
        self.worker = Supervisor(self.store, self.g, live=True)

    def queue(self, manual=True):
        return self.store.enqueue_percentage_new_entry('scope', self.p, live=True,
            manual=manual, authorized_ms=1079999, decision_expires_ms=1110000,
            units='0.2', now_ms=self.now)

    def test_explicit_manual_authority_required(self):
        with self.assertRaises(ValueError): self.queue(manual=False)
        with self.assertRaises(ValueError):
            self.store.enqueue('scope', self.p, live=True, now_ms=self.now)
        row = self.queue()
        self.assertEqual(row['state'], 'QUEUED')
        with self.assertRaises(RuntimeError): self.queue()

    def test_new_entry_sends_inward_cap_not_unbounded_ask(self):
        row = self.queue()
        self.worker.step(row['id'], self.now+1)
        entry = next(a for a in self.g.sent if a['kind']=='entry')
        self.assertEqual(entry['order_type'], 'limit')
        self.assertEqual(entry['price'], '100.30')
        self.assertEqual(entry['quantity'], '3.77')


    def test_transport_rejects_market_above_cap_and_expired_trigger(self):
        from kis_hl.percentage_entry import prepare_entry, check_send
        row = self.queue()
        row['plan'] = prepare_entry('scope', 'live', row['plan'], self.g.preflight(row['plan'], self.now), self.bars, self.now)
        a = dict(kind='entry', order_type='limit', price=row['plan']['limit_price'], quantity=row['plan']['quantity'])
        check_send(row, a, self.now)
        for changes, now in (({'order_type':'market'}, self.now), ({'price':'100.31'}, self.now),
                             ({}, 1081001)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                check_send(row, a | changes, now)

    def test_gateway_percent_new_transport_is_limit_and_uses_trigger_expiry(self):
        from unittest.mock import patch
        from tests.test_managed_gateways import ManagedGatewayTests
        from kis_hl.percentage_entry import prepare_entry
        from types import SimpleNamespace
        row=self.queue()
        row['plan']=prepare_entry('scope','live',row['plan'],self.g.preflight(row['plan'],self.now),self.bars,self.now)
        g,_,_,_,_=ManagedGatewayTests().hl()
        g.scope='scope'
        g.trading.place_order.return_value=SimpleNamespace(status='submitted',response={})
        a=dict(id='fixture-entry',kind='entry',order_type='limit',created_ms=self.now,
               price=row['plan']['limit_price'],quantity=row['plan']['quantity'],expires_ms=row['plan']['expires_ms'])
        with patch('kis_hl.managed_gateways.time.time',return_value=self.now/1000):
            g.submit(row,a)
        kw=g.trading.place_order.call_args.kwargs
        self.assertEqual((kw['order_type'],kw['tif']),('limit','Gtc'))
        self.assertEqual(str(kw['price']),'100.30')
        self.assertEqual(kw['expires_after_ms'],1081000)
        g.trading.place_order.reset_mock()
        with patch('kis_hl.managed_gateways.time.time',return_value=self.now/1000),self.assertRaises(ValueError):
            g.submit(row,a | {'price':'101'})
        g.trading.place_order.assert_not_called()

    def test_authority_scope_mode_policy_and_timestamp_tampering_rejected(self):
        from kis_hl.percentage_entry import check_authority
        row=self.queue()
        for field,value in (('scope','other'),('mode','paper'),('manual',False),('authorized_ms',self.now+1),
                            ('expires_ms',self.now),('fixed_stop_price','94')):
            p=dict(row['plan']); p['percentage_entry_authorization']=dict(p['percentage_entry_authorization'],**{field:value})
            with self.subTest(field=field),self.assertRaises(ValueError): check_authority('scope','live',p,self.now)

    def test_fixed_stop_before_percentage_trail_with_no_local_backup(self):
        row = self.queue(); self.worker.step(row['id'], self.now+1)
        entry = self.g.sent[-1]
        self.g.size = self.g.filled = entry['quantity']
        self.g.orders[entry['id']]['status'] = 'filled'
        self.worker.step(row['id'], self.now+2)
        self.assertEqual(self.g.sent[-1]['kind'], 'stop')
        self.assertFalse(any(a['kind']=='trailing' for a in self.g.sent))
        self.worker.step(row['id'], self.now+3)
        trail = self.g.sent[-1]
        self.assertEqual(trail['kind'], 'trailing')
        self.assertEqual((trail['retracement'], trail['retracement_unit'], trail['price']), ('8.35','percent','0'))
        self.assertEqual(trail['quantity'], entry['quantity'])
        self.assertEqual(self.store.get(row['id'])['local_trailing_covered_size'], '0')
        self.g.orders[trail['id']].update(retracement='8.35',retracement_unit='percent',active=True)
        result=self.worker.step(row['id'],self.now+4)
        self.assertEqual(result['state'],'PROTECTED')
        self.assertEqual(result['trailing_covered_size'],entry['quantity'])
        self.assertEqual(result['covered_size'],entry['quantity'])
        self.assertEqual(len([a for a in self.g.sent if a['kind']=='stop']),1)
        snapshot=self.g.snapshot
        self.g.snapshot=lambda row,attempts,now: snapshot(row,attempts,now) | {'price':'95.5'}
        result=self.worker.step(row['id'],self.now+5)
        self.assertIsNone(result['exit_requested_ms'])
        self.assertFalse(any(a['kind']=='exit' for a in self.g.sent))

    def test_unknown_new_percentage_trail_not_resent_after_restart(self):
        row=self.queue(); self.worker.step(row['id'],self.now+1)
        entry=self.g.sent[-1]; self.g.size=self.g.filled=entry['quantity']
        self.g.orders[entry['id']]['status']='filled'
        self.worker.step(row['id'],self.now+2)
        submit=self.g.submit
        def unknown(row,a):
            if a['kind']=='trailing':
                self.g.sent.append(dict(a)); raise OSError('fixture lost acknowledgement')
            return submit(row,a)
        self.g.submit=unknown
        self.worker.step(row['id'],self.now+3)
        self.worker=Supervisor(self.store,self.g,live=True)
        result=self.worker.step(row['id'],self.now+4)
        self.assertEqual(result['state'],'INTERVENTION')
        self.assertEqual(len([a for a in self.g.sent if a['kind']=='trailing']),1)

    def test_once_claim_survives_closed_owner_and_new_bar(self):
        row=self.queue(); row['state']='CLOSED'; self.store.save(row,self.now+1)
        self.store=ExecutionStore(self.store.path)
        with self.assertRaisesRegex(RuntimeError,'Duplicate intent'): self.queue()

    def test_stale_bar_quote_expiry_flat_and_peer_guards(self):
        for case in ('stale', 'quote', 'position', 'orders', 'wide', 'funds', 'peer', 'expired', 'above_cap'):
            with self.subTest(case=case):
                self.setUp(); row = self.queue(); now = self.now+1
                pre = self.g.preflight
                change = {}
                if case == 'stale': now = 1081001
                if case == 'expired': now = 1110000
                if case == 'quote': change['time_ms'] = now-1001
                if case == 'position': change['position'] = '1'
                if case == 'orders': change['open_orders'] = [{'oid':123}]
                if case == 'wide': change['price'] = '99'
                if case == 'funds': change['available_notional'] = '1'
                if case == 'above_cap': change['ask'] = '100.31'
                if case == 'peer':
                    peer = self.store.enqueue('scope', plan() | {'intent_id':'peer','instrument':'hl:ETH','expires_ms':1110000}, live=True, now_ms=self.now)
                    peer['state']='INTERVENTION'; self.store.save(peer, self.now)
                self.g.preflight = lambda p, n: pre(p, n) | change
                self.worker.step(row['id'], now)
                self.assertFalse(self.g.sent)


if __name__ == '__main__': unittest.main()
