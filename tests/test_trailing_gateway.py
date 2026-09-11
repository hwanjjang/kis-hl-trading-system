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

    def enroll(self,store,info,trading,now):
        from kis_hl.trailing_runner import enroll_position
        return enroll_position(store,info,trading,symbol='BTC-PERP',entry_oid=5,stop_oid=7,
            multiple=D('2'),max_gap_ms=15000,slippage=D('0.01'),now_ms=now)

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
