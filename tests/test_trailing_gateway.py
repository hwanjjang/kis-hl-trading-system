from copy import deepcopy
from decimal import Decimal as D
import unittest
from unittest.mock import MagicMock

from kis_hl.trailing_runner import HyperliquidGateway, protection_matches, fetch_trailing_atr


class GatewayTests(unittest.TestCase):
    def stop(self):
        return {'oid':7,'coin':'BTC','side':'A','isTrigger':True,'reduceOnly':True,'orderType':'Stop Market','triggerPx':'96','sz':'1'}

    def test_only_matching_reduce_only_stop_counts_as_protection(self):
        row={'coin':'BTC','stop_oid':7,'native_trigger':'96'}
        for key,value in [('reduceOnly',False),('side','B'),('orderType','Take Profit Market'),('sz','0.4'),('triggerPx','90'),('coin','ETH')]:
            stop=self.stop(); stop[key]=value
            self.assertFalse(protection_matches(row,stop,D('1')))
        self.assertTrue(protection_matches(row,self.stop(),D('1')))

    def test_status_queries_precede_position_snapshot_and_missing_fill_proof_rejected(self):
        info=MagicMock(); g=HyperliquidGateway(info,MagicMock())
        info.order_status.return_value={'status':'unknownOid'}
        info.user_fills_by_time.return_value=[]
        info.frontend_open_orders.return_value=[self.stop()]
        info.clearinghouse_state.return_value={'assetPositions':[{'position':{'coin':'BTC','szi':'1','entryPx':'100'}}]}
        row={'coin':'BTC','dex':None,'stop_oid':7,'native_trigger':'96','opened_ms':0,'entry_oid':5,'entry_size':'1','entry_fill_ids':['1']}
        out=g.snapshot(row,[{'cloid':'0x'+'a'*32,'status':'UNKNOWN'}],100)
        self.assertFalse(out['generation_ok'])
        names=[c[0] for c in info.method_calls]
        self.assertLess(names.index('order_status'),names.index('clearinghouse_state'))

    def test_atr_requires_complete_contiguous_same_instrument_daily_bars(self):
        info=MagicMock(); day=86400000
        info.candle_snapshot.return_value=[{'s':'BTC','t':i*day,'T':(i+1)*day-1,'h':'102','l':'98','c':'100'} for i in range(11)]
        atr, bars=fetch_trailing_atr(info,'BTC-PERP',now_ms=11*day+1)
        self.assertEqual(atr,D('4'))
        info.candle_snapshot.return_value[5]['s']='ETH'
        with self.assertRaises(ValueError): fetch_trailing_atr(info,'BTC-PERP',now_ms=11*day+1)

    def enrollment_fixture(self):
        from kis_hl.config import HyperliquidConfig
        from kis_hl.trailing_storage import TrailStore
        from pathlib import Path
        import tempfile
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        store=TrailStore(Path(tmp.name)/'state.sqlite')
        info=MagicMock(); info.config=HyperliquidConfig('test-network','test-account','','default')
        day=86400000
        info.order_status.return_value={'status':'order','order':{'status':'filled','order':
            {'coin':'BTC','side':'B','reduceOnly':False,'timestamp':10*day,'origSz':'1'}}}
        info.user_fills_by_time.return_value=[{'coin':'BTC','oid':5,'tid':1,'side':'B','sz':'1','px':'100'}]
        stop=self.stop(); stop['triggerPx']='92'
        info.frontend_open_orders.return_value=[stop]
        info.clearinghouse_state.return_value={'assetPositions':[{'position':{'coin':'BTC','szi':'1','entryPx':'100'}}]}
        info.meta_and_asset_ctxs.return_value=[{'universe':[{'name':'BTC','szDecimals':3}]},[]]
        info.candle_snapshot.return_value=[{'s':'BTC','t':i*day,'T':(i+1)*day-1,'h':'102','l':'98','c':'100'} for i in range(11)]
        return store,info,MagicMock(),11*day+1

    def enroll(self,store,info,trading,now,**changes):
        from kis_hl.trailing_runner import enroll_position
        return enroll_position(store,info,trading,symbol='BTC-PERP',entry_oid=5,stop_oid=7,
            multiple=D('2'),max_gap_ms=15000,slippage=D('0.01'),now_ms=now,**changes)

    def short_fixture(self):
        store, info, trading, now = self.enrollment_fixture()
        info.order_status.return_value['order']['order']['side'] = 'A'
        info.user_fills_by_time.return_value[0]['side'] = 'A'
        info.frontend_open_orders.return_value[0].update(side='B', triggerPx='108')
        info.clearinghouse_state.return_value['assetPositions'][0]['position']['szi'] = '-1'
        return store, info, trading, now

    def test_short_enrollment_requires_matching_entry_position_and_buy_stop(self):
        store, info, trading, now = self.short_fixture()
        row = self.enroll(store, info, trading, now, side='short')
        self.assertEqual((row['side'], row['size'], row['trail']['threshold']), ('short', '1', '108'))
        self.assertEqual(row['trail']['low'], '100')
        trading.place_order.assert_not_called()

    def test_short_enrollment_rejects_wrong_side_loose_stop_and_reversal(self):
        for target, key, value in [('entry', 'side', 'B'), ('fill', 'side', 'B'),
                                   ('stop', 'side', 'A'), ('stop', 'triggerPx', '110'),
                                   ('position', 'szi', '1'), ('position', 'entryPx', '101')]:
            with self.subTest(target=target, key=key):
                store, info, trading, now = self.short_fixture()
                objects = {'entry': info.order_status.return_value['order']['order'],
                           'fill': info.user_fills_by_time.return_value[0],
                           'stop': info.frontend_open_orders.return_value[0],
                           'position': info.clearinghouse_state.return_value['assetPositions'][0]['position']}
                objects[target][key] = value
                with self.assertRaises((ValueError, RuntimeError)):
                    self.enroll(store, info, trading, now, side='short')
                self.assertEqual(store.list(), [])
                trading.place_order.assert_not_called()

    def test_short_gateway_submits_only_buy_reduce_only_ioc(self):
        store, info, trading, now = self.short_fixture()
        row = self.enroll(store, info, trading, now, side='short')
        attempt = {'size': '1', 'limit_price': '110', 'cloid': '0x'+'a'*32, 'created_ms': now}
        HyperliquidGateway(info, trading).submit(row, attempt)
        call = trading.place_order.call_args.kwargs
        self.assertEqual((call['side'], call['reduce_only'], call['tif']), ('buy', True, 'Ioc'))

    def test_short_fill_ledger_tracks_partial_close_and_foreign_entry(self):
        store, info, trading, now = self.short_fixture()
        row = self.enroll(store, info, trading, now, side='short')
        info.user_fills_by_time.return_value.append({'coin':'BTC','oid':8,'tid':2,'side':'B','sz':'0.4','px':'110'})
        info.clearinghouse_state.return_value['assetPositions'][0]['position']['szi'] = '-0.6'
        result = HyperliquidGateway(info, trading).snapshot(row, [], now)
        self.assertTrue(result['generation_ok'])
        self.assertEqual(D(result['size']), D('0.6'))
        info.user_fills_by_time.return_value.append({'coin':'BTC','oid':9,'tid':3,'side':'A','sz':'0.2','px':'100'})
        info.clearinghouse_state.return_value['assetPositions'][0]['position']['szi'] = '-0.8'
        self.assertFalse(HyperliquidGateway(info, trading).snapshot(row, [], now)['generation_ok'])

    def test_short_reversed_exposure_and_wrong_side_exit_status_require_intervention(self):
        store, info, trading, now = self.short_fixture()
        row = self.enroll(store, info, trading, now, side='short')
        info.clearinghouse_state.return_value['assetPositions'][0]['position']['szi'] = '1'
        result = HyperliquidGateway(info, trading).snapshot(row, [], now)
        self.assertFalse(result['generation_ok'])
        self.assertEqual(result['size'], '-1')
        info.clearinghouse_state.return_value['assetPositions'][0]['position']['szi'] = '-1'
        cloid = '0x'+'a'*32
        info.order_status.return_value = {'order': {'status': 'filled', 'order':
            {'coin':'BTC', 'reduceOnly':True, 'side':'A', 'cloid':cloid}}}
        result = HyperliquidGateway(info, trading).snapshot(row, [{'cloid':cloid,'status':'UNKNOWN'}], now)
        self.assertFalse(result['generation_ok'])
        trading.place_order.assert_not_called()

    def test_short_enrollment_rejects_missing_insufficient_or_unowned_protection(self):
        for problem in ['missing', 'coverage', 'foreign-order', 'quantity', 'unfilled']:
            with self.subTest(problem=problem):
                store, info, trading, now = self.short_fixture()
                if problem == 'missing':
                    info.frontend_open_orders.return_value = []
                elif problem == 'coverage':
                    info.frontend_open_orders.return_value[0]['sz'] = '0.4'
                elif problem == 'foreign-order':
                    info.frontend_open_orders.return_value.append({'oid': 99, 'coin': 'BTC'})
                elif problem == 'quantity':
                    info.clearinghouse_state.return_value['assetPositions'][0]['position']['szi'] = '-2'
                else:
                    info.order_status.return_value['order']['status'] = 'open'
                with self.assertRaises((ValueError, RuntimeError)):
                    self.enroll(store, info, trading, now, side='short')
                self.assertEqual(store.list(), [])
                trading.place_order.assert_not_called()
                trading.cancel_order.assert_not_called()

    def test_short_wrong_side_stop_or_opposite_position_never_mutates_even_when_flat(self):
        from kis_hl.trailing_runner import TrailingRunner
        for problem in ['wrong-stop', 'opposite-position', 'flat-wrong-stop', 'flat-foreign-entry']:
            with self.subTest(problem=problem):
                store, info, trading, now = self.short_fixture()
                row = self.enroll(store, info, trading, now, side='short')
                row['mode'] = 'live'
                store.save(row, 'offline live-shaped fixture')
                if problem in {'wrong-stop', 'flat-wrong-stop'}:
                    info.frontend_open_orders.return_value[0]['side'] = 'A'
                if problem == 'opposite-position':
                    info.clearinghouse_state.return_value['assetPositions'][0]['position']['szi'] = '1'
                if problem.startswith('flat-'):
                    info.clearinghouse_state.return_value = {'assetPositions': []}
                    info.user_fills_by_time.return_value.append(
                        {'coin':'BTC','oid':8,'tid':2,'side':'B','sz':'1','px':'105'})
                    if problem == 'flat-foreign-entry':
                        info.user_fills_by_time.return_value.extend([
                            {'coin':'BTC','oid':9,'tid':3,'side':'A','sz':'1','px':'100'},
                            {'coin':'BTC','oid':10,'tid':4,'side':'B','sz':'1','px':'105'}])
                runner = TrailingRunner(store, row['id'], HyperliquidGateway(info, trading))
                runner.on_tick(now, D('109'))
                self.assertEqual(runner.row['state'], 'MANUAL_INTERVENTION')
                trading.place_order.assert_not_called()
                trading.cancel_order.assert_not_called()

    def test_enrollment_reconciles_existing_entry_and_stop_without_mutation(self):
        store,info,trading,now=self.enrollment_fixture()
        row=self.enroll(store,info,trading,now)
        self.assertEqual(row['mode'],'paper')
        self.assertEqual(row['trail']['distance'],'8')
        self.assertEqual(row['entry_fill_ids'],['1'])
        trading.place_order.assert_not_called()

    def test_enrollment_rejects_missing_or_loose_stop(self):
        store,info,trading,now=self.enrollment_fixture()
        info.frontend_open_orders.return_value[0]['triggerPx']='90'
        with self.assertRaisesRegex(ValueError,'risk floor'):
            self.enroll(store,info,trading,now)
        self.assertEqual(store.list(),[])

    def test_live_row_cannot_be_run_in_default_paper_mode(self):
        from kis_hl.trailing_runner import run_trailing_stream
        store,info,trading,now=self.enrollment_fixture()
        row=self.enroll(store,info,trading,now)
        row['mode']='live'; store.save(row,'test mode mismatch')
        with self.assertRaisesRegex(ValueError,'Run mode'):
            run_trailing_stream(store,row['id'],info,trading)
        trading.place_order.assert_not_called()

    def test_stream_quarantines_first_sample_then_paper_exits_without_orders(self):
        import json
        from kis_hl.trailing_runner import run_trailing_stream
        store,info,trading,now=self.enrollment_fixture()
        row=self.enroll(store,info,trading,now)
        samples=iter(['80','90'])
        class Transport:
            def send_text(self,s): pass
            def recv_text(self,**kw): return json.dumps({'channel':'allMids','data':{'mids':{'BTC':next(samples)}}})
            def close(self): pass
        out=run_trailing_stream(store,row['id'],info,trading,max_messages=2,max_reconnects=0,
                                transport_factory=lambda *a:Transport())
        self.assertEqual(out['state'],'PAPER_EXIT')
        trading.place_order.assert_not_called()
        trading.cancel_order.assert_not_called()
