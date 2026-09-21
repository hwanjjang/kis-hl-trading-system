import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kis_hl.config import load_kis_config
from kis_hl.kis.client import KisClient, KisHttpResponse


class KisTradingTests(unittest.TestCase):
    def test_broker_instrument_metadata_uses_exact_product_route(self):
        c=self.client(True)
        with patch.object(c,'_request_with_auth') as send:
            c.overseas_instrument_info(symbol='DRAM',exchange='AMEX')
        self.assertEqual(send.call_args.args,('GET','/uapi/overseas-price/v1/quotations/search-info'))
        self.assertEqual(send.call_args.kwargs['tr_id'],'CTPF1702R')
        self.assertEqual(send.call_args.kwargs['query'],{'PRDT_TYPE_CD':'529','PDNO':'DRAM'})
    def client(self, live=False):
        env={'SANDBOX':'false' if live else 'true','KIS_API_KEY':'fake','KIS_API_SECRET':'fake',
             'KIS_STOCK_ACCOUNT':'1234567801','KIS_API_ST_KEY':'fake','KIS_API_ST_SECRET':'fake',
             'KIS_ST_STOCK_ACCOUNT':'1234567801','KIS_MIN_REQUEST_INTERVAL_MS':'0'}
        return KisClient(load_kis_config(env))

    def test_overseas_balance_collects_pages_and_sets_continuation(self):
        c=self.client(True)
        pages=[KisHttpResponse(200,{'rt_cd':'0','output1':[{'pdno':'SPY'}], 'output2':[],
                                  'ctx_area_fk200':'f','ctx_area_nk200':'n'},{'tr_cont':'M'}),
               KisHttpResponse(200,{'rt_cd':'0','output1':[{'pdno':'QQQ'}],'output2':[]},{'tr_cont':'D'})]
        with patch.object(c,'_request_with_auth',side_effect=pages) as request:
            data=c.account_pages('overseas_balance', exchange='NASD')
        self.assertEqual(len(data['output1']),2)
        self.assertEqual(request.call_args.kwargs['tr_cont'],'N')
        self.assertEqual(request.call_args.kwargs['tr_id'],'TTTS3012R')
        self.assertEqual(request.call_args.kwargs['query']['CTX_AREA_NK200'],'n')

    def test_repeated_page_cursor_fails(self):
        c=self.client(True)
        page=KisHttpResponse(200,{'rt_cd':'0','output1':[], 'ctx_area_fk100':'a','ctx_area_nk100':'b'},{'tr_cont':'M'})
        with patch.object(c,'_request_with_auth',return_value=page):
            with self.assertRaisesRegex(RuntimeError,'pagination'):c.account_pages('domestic_balance')

    def test_body_error_is_sanitized(self):
        c=self.client()
        with patch.object(c,'_request_with_auth',return_value=KisHttpResponse(200,{'rt_cd':'1','msg1':'secret'},{})):
            with self.assertRaisesRegex(RuntimeError,'KIS account inquiry failed') as error:
                c.account_pages('domestic_balance')
        self.assertNotIn('secret',str(error.exception))

    def test_order_preview_has_distinct_domestic_overseas_types_and_no_network(self):
        c=self.client(True)
        with patch.object(c,'_request_with_auth') as request:
            local=c.cash_order(market='domestic',symbol='069500',side='buy',quantity='1',price='30000')
            foreign=c.cash_order(market='overseas',symbol='SPY',exchange='AMEX',side='sell',quantity='1',price='500')
        request.assert_not_called()
        self.assertTrue(local['dry_run'])
        self.assertEqual(local['tr_id'],'TTTC0012U')
        self.assertEqual(foreign['tr_id'],'TTTT1006U')
        self.assertNotIn('CANO',local['request'])

    def test_unknown_order_type_and_unverified_paper_us_sell_fail(self):
        c=self.client()
        with self.assertRaises(ValueError):
            c.cash_order(market='domestic',symbol='069500',side='buy',quantity='1',price='30000',order_type='stop-limit')
        with self.assertRaisesRegex(ValueError,'paper'):
            c.cash_order(market='overseas',symbol='SPY',exchange='AMEX',side='sell',quantity='1',price='500',dry_run=False)

    def test_write_response_is_never_automatically_retried(self):
        c=self.client(True)
        with patch.object(c,'get_access_token',return_value='fake'), patch.object(c,'_request_json',return_value=KisHttpResponse(500,{'msg_cd':'EGW00201'},{})) as request:
            c._request_with_auth('POST','/test',tr_id='TTTC0012U',body={})
        self.assertEqual(request.call_count,1)

    def test_timestamped_quote_routes_are_explicit(self):
        c=self.client()
        with patch.object(c,'_request_with_auth') as request:
            c.order_book(market='overseas',symbol='SPY',exchange='AMS')
        self.assertEqual(request.call_args.kwargs['tr_id'],'HHDFS76200100')
        with patch.object(c,'_request_with_auth') as request:
            c.domestic_intraday_chart(symbol='069500',hour='120000')
        self.assertEqual(request.call_args.kwargs['tr_id'],'FHKST03010200')

    def test_kospi_chart_route(self):
        c=self.client()
        with patch.object(c,'_request_with_auth') as request:
            c.domestic_chart(symbol='0001',date_from='20260101',date_to='20260131',index=True)
        self.assertEqual(request.call_args.kwargs['tr_id'],'FHKUP03500100')
        self.assertEqual(request.call_args.kwargs['query']['FID_COND_MRKT_DIV_CODE'],'U')


if __name__=='__main__':unittest.main()
