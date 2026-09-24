from __future__ import annotations
import json
import unittest
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch
from kis_hl.binance.trading import BinanceTradingClient
from kis_hl.cli import build_parser
from tests.test_binance_trading import RecordingTradingClient, make_config, FILTERS, EXCHANGE_INFO, ONE_WAY, ACK, MARK

class OrderReviewTests(unittest.TestCase):
    def setUp(self):
        self.lock = patch('kis_hl.binance.trading.account_lock')
        self.lock_mock = self.lock.start()
        self.addCleanup(self.lock.stop)

    def client(self, response=ACK, **kwargs):
        return RecordingTradingClient(make_config(**kwargs), {
            '/fapi/v1/exchangeInfo': (200, EXCHANGE_INFO),
            '/fapi/v1/positionSide/dual': (200, ONE_WAY),
            '/fapi/v1/order': (200, response),
        })

    def order(self, c, **kwargs):
        return c.place_order(symbol='BTCUSDT', side='BUY', order_type='MARKET', quantity=Decimal('.01'),
            filters=FILTERS, mark_price=MARK, dry_run=False, **kwargs)

    def test_env_cannot_expand_supported_live_universe(self):
        c=self.client(live_symbols=('ETHUSDT',))
        with self.assertRaisesRegex(RuntimeError, 'supported'):
            c.place_order(symbol='ETHUSDT',side='BUY',order_type='MARKET',quantity=Decimal('.01'),filters=FILTERS,mark_price=MARK,dry_run=False)
        self.assertEqual(c.calls, [])

    def test_metadata_must_confirm_trading_crypto_perpetual(self):
        for field,bad in [('status','PENDING_TRADING'),('underlyingType','INDEX'),('contractType','CURRENT_QUARTER')]:
            info=json.loads(EXCHANGE_INFO);info['symbols'][0][field]=bad
            c=self.client(); c.responses['/fapi/v1/exchangeInfo']=(200,json.dumps(info))
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError, 'metadata'):
                self.order(c)
            self.assertFalse(any(call['method']=='POST' for call in c.calls))

    def test_terminal_ack_without_fill_is_rejected_but_partial_fill_is_submitted(self):
        for qty,expected in [('0','rejected'),('.001','submitted')]:
            response=json.dumps({'orderId':1,'status':'EXPIRED','executedQty':qty})
            self.assertEqual(self.order(self.client(response)).status,expected)

    def test_signed_submit_occurs_under_account_lock(self):
        c=self.client(); inside=[False]; original=c.send
        @contextmanager
        def locked(*args):
            inside[0]=True
            try: yield
            finally: inside[0]=False
        def send(method,*args):
            if method=='POST': self.assertTrue(inside[0])
            return original(method,*args)
        c.send=send
        self.lock_mock.side_effect=locked
        self.order(c)
        self.lock_mock.assert_called_once_with(c.config.base_url,c.config.api_key)

    def test_algo_allowlist_runs_before_lookup(self):
        c=self.client(live_symbols=())
        with self.assertRaises(RuntimeError): c.cancel_algo_order(symbol='BTCUSDT',algo_id=1,dry_run=False)
        self.assertEqual(c.calls,[])

    def test_cancel_identifiers_are_exclusive(self):
        c=self.client()
        with self.assertRaises(ValueError): c.cancel_order(symbol='BTCUSDT',order_id=1,client_order_id='c')
        with self.assertRaises(ValueError): c.cancel_algo_order(symbol='BTCUSDT',algo_id=1,client_algo_id='c')

    def test_live_cli_default_and_explicit_dry_run(self):
        argv=['binance-trade','--symbol','BTCUSDT','--side','buy','--order-type','market','--quantity','.001']
        self.assertFalse(build_parser().parse_args(argv).dry_run)
        self.assertTrue(build_parser().parse_args(argv+['--dry-run']).dry_run)

    def test_market_rejects_nondefault_tif(self):
        with self.assertRaisesRegex(ValueError,'MARKET'):
            self.client().place_order(symbol='BTCUSDT',side='BUY',order_type='MARKET',quantity=Decimal('.01'),tif='IOC',filters=FILTERS,mark_price=MARK)

    def test_protective_stop_checks_position_direction_and_coverage(self):
        for amount,quantity in [('0',None),('-.01',None),('.02',Decimal('.01'))]:
            c=self.client()
            c.responses['/fapi/v2/positionRisk']=(200,json.dumps([{'symbol':'BTCUSDT','positionSide':'BOTH','positionAmt':amount}]))
            with self.subTest(amount=amount), self.assertRaisesRegex(RuntimeError,'position|coverage'):
                c.place_stop_market(symbol='BTCUSDT',side='SELL',stop_price=Decimal('74000'),quantity=quantity,
                    close_position=quantity is None,filters=FILTERS,mark_price=MARK,dry_run=False)
            self.assertFalse(any(call['method']=='POST' for call in c.calls))

class OrderCliReviewTests(unittest.TestCase):
    def test_failed_protection_is_inactive_and_exit_code_is_nonzero(self):
        import contextlib, io, sqlite3, tempfile
        from pathlib import Path
        from kis_hl.cli import main
        from kis_hl.binance.trading import BinanceOrderSubmission
        for state,code in [('unknown',3),('rejected',2)]:
            with self.subTest(state=state), tempfile.TemporaryDirectory() as tmp:
                db=Path(tmp)/'t.sqlite'
                submission=BinanceOrderSubmission(state,False,'BTCUSDT',{
                    'path':'/fapi/v1/algoOrder','method':'POST','params':{'side':'SELL','type':'STOP_MARKET','triggerPrice':'74000','closePosition':'true'},
                },{'error':'fixture'})
                with patch('kis_hl.cli.load_env_file'),patch('kis_hl.cli.BinanceTradingClient') as cls,contextlib.redirect_stdout(io.StringIO()):
                    cls.return_value.place_stop_market.return_value=submission
                    status=main(['--db',str(db),'binance-stop','--side','sell','--kind','stop-market','--stop-price','74000'])
                with sqlite3.connect(db) as con:
                    self.assertEqual(con.execute('SELECT active,status FROM protective_orders').fetchone(),(0,state))
                self.assertEqual(status,code)

    def test_default_live_dispatch_and_explicit_dry_run(self):
        import contextlib, io
        from kis_hl.cli import main
        from kis_hl.binance.trading import BinanceOrderSubmission
        for extra,expected in [([],False),(['--dry-run'],True)]:
            with patch('kis_hl.cli.load_env_file'),patch('kis_hl.cli.BinanceTradingClient') as cls,contextlib.redirect_stdout(io.StringIO()):
                cls.return_value.place_order.return_value=BinanceOrderSubmission('dry_run',True,'BTCUSDT',{}, {})
                main(['binance-trade','--side','buy','--order-type','market','--quantity','.001','--no-store',*extra])
                self.assertEqual(cls.return_value.place_order.call_args.kwargs['dry_run'],expected)

    def test_dry_run_and_exchange_test_cannot_be_combined(self):
        import contextlib, io
        argv=['binance-trade','--side','buy','--order-type','market','--quantity','.001','--dry-run','--exchange-test']
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(argv)
