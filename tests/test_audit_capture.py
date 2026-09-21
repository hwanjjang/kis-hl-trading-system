"""Offline account-capture boundary and provenance tests."""
import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from kis_hl.data_audit_capture import collect_bundle
from kis_hl.journal_sync import Scope


ADDRESS = '0x' + '1' * 40
HL_SCOPE = Scope('hyperliquid', 'mainnet', ADDRESS)
KIS_SCOPE = Scope('kis', 'live', '1234567801')


def ms(value):
    delta = datetime.fromisoformat(value) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return delta.days * 86400000 + delta.seconds * 1000 + delta.microseconds // 1000


class HL:
    def __init__(self):
        self.calls = []
        self.last_raw_body = None

    def response(self, kind, body, **kwargs):
        self.calls.append((kind, kwargs))
        self.last_raw_body = json.dumps(body).encode()
        return body

    def user_fills_by_time(self, **kwargs):
        return self.response('fills', [{'time': kwargs['start_time_ms'], 'coin': 'BTC'}], **kwargs)

    def user_funding(self, **kwargs):
        return self.response('funding', [], **kwargs)

    def user_fills(self, **kwargs):
        return self.response('tail', [{'time': 0}], **kwargs)

    def post_info(self, payload):
        assert payload == {'type': 'perpDexs'}
        return self.response('dexs', [None, {'name': 'xyz'}, {'name': 'other'}])

    def clearinghouse_state(self, **kwargs):
        dex = kwargs['dex']
        rows = [] if dex != 'other' else [{'position': {'coin': 'other:ABC', 'szi': '-2'}}]
        return self.response('state', {'assetPositions': rows}, **kwargs)

    def spot_clearinghouse_state(self, **kwargs):
        return self.response('spot', {'balances': []}, **kwargs)


class KIS:
    def __init__(self):
        self.calls = []
        self.config = SimpleNamespace(account_id=KIS_SCOPE.account, mode='live')

    def account_pages(self, kind, **kwargs):
        self.calls.append((kind, kwargs))
        body = {'rt_cd': '0', 'output1': [], 'output2': []}
        if kind == 'domestic_trade_profit' and kwargs.get('symbol'):
            body['output2'] = [{'buy_fee_smtl': '1'}]
        kwargs['page_observer'](SimpleNamespace(body=body, raw_body=json.dumps(body).encode(),
                                               headers={'authorization': 'secret'}))
        return {**body, 'complete': True, 'pages': 1}


class CaptureTests(unittest.TestCase):
    def hl(self, client=None, **kwargs):
        return collect_bundle('hyperliquid', ADDRESS, start_ms=0, end_ms=100,
                              client=client or HL(), scope=HL_SCOPE, **kwargs)

    def test_explicit_identity_and_nonempty_range_before_client_creation(self):
        for venue, account, start, end in [('bad', ADDRESS, 0, 1), ('hyperliquid', '', 0, 1),
                                         ('hyperliquid', ADDRESS, 1, 1), ('hyperliquid', ADDRESS, 2, 1),
                                         ('hyperliquid', ADDRESS, False, 1)]:
            with self.subTest(venue=venue, account=account, start=start, end=end):
                with self.assertRaises(ValueError):
                    collect_bundle(venue, account, start_ms=start, end_ms=end)

    def test_scope_mismatch_rejected_without_calls(self):
        client = HL()
        with self.assertRaises(ValueError):
            collect_bundle('hyperliquid', ADDRESS, start_ms=0, end_ms=1, client=client,
                           scope=Scope('hyperliquid', 'mainnet', 'different'))
        self.assertEqual(client.calls, [])

    def test_hl_end_exclusive_explicit_user_and_native_evidence(self):
        client = HL()
        result = self.hl(client)
        self.assertEqual(result['account'], {'venue': 'hyperliquid', 'environment': 'mainnet', 'native_id': ADDRESS})
        self.assertEqual(result['sources'][0], {'parser': 'hl_fills', 'data': [{'time': 0, 'coin': 'BTC'}]})
        for kind, args in client.calls:
            if kind in {'fills', 'funding'}:
                self.assertEqual(args, {'start_time_ms': 0, 'end_time_ms': 99, 'user': ADDRESS})
            elif kind != 'dexs':
                self.assertEqual(args['user'], ADDRESS)
        self.assertTrue(result['collection_complete'])
        self.assertEqual(result['evidence'][0]['raw'], json.dumps([{'time': 0, 'coin': 'BTC'}]))
        self.assertFalse(result['inventory_complete'])
        self.assertTrue(any(f['code'] == 'historical_inventory' for f in result['findings']))

    @patch('kis_hl.data_audit_capture.now_ms', return_value=100)
    def test_all_discovered_dexes_zero_states_and_current_inventory(self, _):
        client = HL()
        result = self.hl(client)
        self.assertEqual([args['dex'] for kind, args in client.calls if kind == 'state'], [None, 'xyz', 'other'])
        self.assertEqual(result['positions'], [{'instrument': 'hl:other:ABC', 'quantity': '-2'}])
        self.assertTrue(result['inventory_complete'])
        self.assertEqual(result['inventory_scope']['dexes'], ['', 'xyz', 'other'])

    def test_saturated_history_fails_instead_of_partial_success(self):
        client = HL()
        client.user_fills_by_time = lambda **kw: [{'time': kw['start_time_ms']}] * 2000
        with self.assertRaisesRegex(RuntimeError, 'Saturated'):
            self.hl(client)

    def test_malformed_position_is_not_absent_position(self):
        client = HL()
        client.clearinghouse_state = lambda **kw: {}
        with self.assertRaises((ValueError, RuntimeError)):
            self.hl(client)

    def test_empty_tail_is_retention_uncertainty(self):
        client = HL()
        client.user_fills = lambda **kw: []
        result = self.hl(client)
        self.assertTrue(any(f['code'] == 'retention_unverified' for f in result['findings']))
        self.assertTrue(result['collection_complete'])

    def test_kis_dates_expand_to_seoul_midnight_and_headers_excluded(self):
        client = KIS()
        result = collect_bundle('kis', KIS_SCOPE.account, start_ms=ms('2026-09-20T16:00:00+00:00'),
                                end_ms=ms('2026-09-21T15:00:00+00:00'), client=client, scope=KIS_SCOPE)
        self.assertEqual(result['start_ms'], ms('2026-09-20T15:00:00+00:00'))
        self.assertEqual(result['end_ms'], ms('2026-09-21T15:00:00+00:00'))
        for kind, args in client.calls:
            if 'date_from' in args:
                self.assertEqual((args['date_from'], args['date_to']), ('20260921', '20260921'))
        self.assertEqual({args['older_history'] for kind, args in client.calls if kind == 'domestic_history'}, {False, True})
        self.assertNotIn('authorization', json.dumps(result))
        self.assertNotIn('secret', json.dumps(result))
        self.assertFalse(result['inventory_complete'])
        self.assertTrue(any(f['code'] == 'limited_market_scope' for f in result['findings']))

    def test_profit_windows_span_at_most_ten_calendar_years(self):
        client = KIS()
        collect_bundle('kis', KIS_SCOPE.account, start_ms=ms('2000-01-01T00:00:00+00:00'),
                       end_ms=ms('2026-09-21T00:00:00+00:00'), client=client, scope=KIS_SCOPE)
        windows = [(kw['date_from'], kw['date_to']) for kind, kw in client.calls if kind == 'domestic_trade_profit']
        self.assertEqual(windows, [('20000101', '20091231'), ('20100101', '20191231'), ('20200101', '20260921')])

    def test_kis_epoch_expansion_never_produces_negative_start(self):
        result = collect_bundle('kis', KIS_SCOPE.account, start_ms=0, end_ms=1,
                                client=KIS(), scope=KIS_SCOPE)
        self.assertEqual(result['start_ms'], 0)
        self.assertEqual(result['end_ms'], 54000000)

    def test_kis_incomplete_pages_fail(self):
        client = KIS()
        client.account_pages = lambda *args, **kw: {'complete': False, 'output1': [], 'output2': []}
        with self.assertRaisesRegex(RuntimeError, '[Ii]ncomplete'):
            collect_bundle('kis', KIS_SCOPE.account, start_ms=1, end_ms=1000, client=client, scope=KIS_SCOPE)

    def test_configured_kis_identity_mismatch_fails_before_request(self):
        client = KIS()
        client.config.account_id = '9999999901'
        with self.assertRaises(ValueError):
            collect_bundle('kis', KIS_SCOPE.account, start_ms=0, end_ms=1, client=client, scope=KIS_SCOPE)
        self.assertEqual(client.calls, [])

    def test_domestic_costs_and_duplicate_order_routes_preserve_native_rows(self):
        client = KIS()
        original = client.account_pages
        day = {'trad_dt': '20260921', 'pdno': '005930'}
        order = {'ord_dt': '20260921', 'pdno': '005930', 'odno': '17', 'ord_gno_brno': '001', 'tot_ccld_qty': '1'}
        def pages(kind, **kwargs):
            response = original(kind, **kwargs)
            if kind == 'domestic_trade_profit' and not kwargs.get('symbol'):
                response['output1'] = [day]
            if kind == 'domestic_history':
                response['output1'] = [dict(order)]
            return response
        client.account_pages = pages
        result = collect_bundle('kis', KIS_SCOPE.account, start_ms=ms('2026-09-21T00:00:00+00:00'),
                                end_ms=ms('2026-09-21T01:00:00+00:00'), client=client, scope=KIS_SCOPE)
        domestic = result['sources'][0]['data']
        self.assertEqual(domestic, {'days': [day], 'orders': [order],
                                   'costs_by_day_symbol': {'20260921:005930': {'buy_fee_smtl': '1'}}})
        costs = [kw for kind, kw in client.calls if kind == 'domestic_trade_profit' and kw.get('symbol')]
        self.assertEqual(len(costs), 1)
        self.assertEqual((costs[0]['date_from'], costs[0]['date_to'], costs[0]['symbol']),
                         ('20260921', '20260921', '005930'))

    def test_aggregate_evidence_retains_only_native_query_parameters(self):
        client = KIS()
        result = collect_bundle('kis', KIS_SCOPE.account, start_ms=ms('2026-09-21T00:00:00+00:00'),
                                end_ms=ms('2026-09-21T01:00:00+00:00'), client=client, scope=KIS_SCOPE)
        for kind, kwargs in client.calls:
            parameters = {key: value for key, value in kwargs.items() if key not in {'page_observer', 'max_pages'}}
            matching = [entry for entry in result['evidence']
                        if entry['dataset'] == 'kis_' + kind and entry.get('parameters') == parameters]
            self.assertTrue(matching, (kind, parameters))
        self.assertNotIn('page_observer', json.dumps(result))

    def test_executed_orders_require_day_profit_and_cost_corroboration(self):
        for quantity, rejects in [('1', True), ('0', False)]:
            with self.subTest(quantity=quantity):
                client = KIS()
                original = client.account_pages
                def pages(kind, **kwargs):
                    result = original(kind, **kwargs)
                    if kind == 'domestic_history':
                        result['output1'] = [{'ord_dt': '20260921', 'pdno': '005930', 'odno': '17',
                                              'ord_gno_brno': '001', 'tot_ccld_qty': quantity}]
                    return result
                client.account_pages = pages
                def capture():
                    return collect_bundle('kis', KIS_SCOPE.account, start_ms=ms('2026-09-21T00:00:00+00:00'),
                                          end_ms=ms('2026-09-21T01:00:00+00:00'), client=client, scope=KIS_SCOPE)
                if rejects:
                    with self.assertRaisesRegex(ValueError, 'corroboration'):
                        capture()
                else:
                    self.assertTrue(capture()['collection_complete'])

    def test_injected_hl_environment_must_match_scope(self):
        client = HL()
        client.config = SimpleNamespace(base_url='https://api.hyperliquid-testnet.xyz')
        with self.assertRaisesRegex(ValueError, 'environment'):
            self.hl(client)
        self.assertEqual(client.calls, [])

    def test_unverified_client_without_scope_cannot_capture(self):
        client = HL()
        with self.assertRaisesRegex(ValueError, 'scope'):
            collect_bundle('hyperliquid', ADDRESS, start_ms=0, end_ms=100, client=client)
        self.assertEqual(client.calls, [])

    @patch('kis_hl.data_audit_capture.now_ms', return_value=100)
    def test_missing_dex_discovery_does_not_certify_absent_positions(self, _):
        client = HL()
        client.post_info = None
        result = self.hl(client)
        self.assertFalse(result['inventory_complete'])
        self.assertTrue(any(f['code'] == 'dex_scope_unverified' for f in result['findings']))

    def test_explicit_raw_evidence_must_match_decoded_body(self):
        client = KIS()
        def pages(kind, **kwargs):
            kwargs['page_observer'](SimpleNamespace(body={'output1': []}, raw_body=b'{"output1":[{}]}'))
        client.account_pages = pages
        with self.assertRaisesRegex(ValueError, 'Raw response'):
            collect_bundle('kis', KIS_SCOPE.account, start_ms=0, end_ms=100, client=client, scope=KIS_SCOPE)

    def test_kis_sim_rejected_before_queries(self):
        client = KIS()
        client.config.mode = 'sim'
        with self.assertRaisesRegex(ValueError, 'live'):
            collect_bundle('kis', KIS_SCOPE.account, start_ms=0, end_ms=100, client=client,
                           scope=Scope('kis', 'sim', KIS_SCOPE.account))
        self.assertEqual(client.calls, [])

    def test_identical_overseas_rows_across_exchange_routes_are_deduplicated(self):
        client = KIS()
        original = client.account_pages
        row = {'trad_dt': '20260921', 'pdno': 'AAPL', 'sll_buy_dvsn_cd': '02',
               'crcy_cd': 'USD', 'loan_dvsn_cd': '', 'ccld_qty': '1'}
        def pages(kind, **kwargs):
            response = original(kind, **kwargs)
            if kind == 'overseas_transactions':
                response['output1'] = [dict(row)]
            return response
        client.account_pages = pages
        result = collect_bundle('kis', KIS_SCOPE.account, start_ms=ms('2026-09-21T00:00:00+00:00'),
                                end_ms=ms('2026-09-21T01:00:00+00:00'), client=client, scope=KIS_SCOPE)
        self.assertEqual(result['sources'][1]['data'], [row])
        evidence = [e for e in result['evidence'] if e['dataset'] == 'kis_overseas_transactions']
        self.assertEqual(len(evidence), 3)

    def test_conflicting_overseas_rows_across_exchange_routes_fail(self):
        client = KIS()
        original = client.account_pages
        def pages(kind, **kwargs):
            response = original(kind, **kwargs)
            if kind == 'overseas_transactions':
                response['output1'] = [{'trad_dt': '20260921', 'pdno': 'AAPL', 'sll_buy_dvsn_cd': '02',
                    'crcy_cd': 'USD', 'loan_dvsn_cd': '', 'ccld_qty': '1' if kwargs['exchange'] == 'NASD' else '2'}]
            return response
        client.account_pages = pages
        with self.assertRaisesRegex(ValueError, 'Conflicting overseas'):
            collect_bundle('kis', KIS_SCOPE.account, start_ms=ms('2026-09-21T00:00:00+00:00'),
                           end_ms=ms('2026-09-21T01:00:00+00:00'), client=client, scope=KIS_SCOPE)

    @patch('kis_hl.hyperliquid.client.HyperliquidInfoClient', return_value=HL())
    @patch.dict('os.environ', {'HYPERLIQUID_PRIVATEKEY': 'must-not-read', 'HYPERLIQUID_BASE_URL': 'https://api.hyperliquid.xyz'})
    def test_default_hl_client_does_not_load_private_key(self, ctor):
        def construct(config):
            client = HL()
            client.config = config
            return client
        ctor.side_effect = construct
        collect_bundle('hyperliquid', ADDRESS, start_ms=0, end_ms=100)
        self.assertEqual(ctor.call_args.args[0].private_key, '')
        self.assertEqual(ctor.call_args.args[0].account_address, ADDRESS)


if __name__ == '__main__':
    unittest.main()
