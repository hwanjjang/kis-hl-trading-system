from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock

from kis_hl.binance.ws import BinanceUserStreamClient, parse_market_ticks, stream_route
from kis_hl.config import load_binance_config
from tests.test_binance_ws import make_config


class StreamReviewTests(unittest.TestCase):
    def test_quiet_stream_renews_without_reconnecting(self):
        clock = [0]
        rest = Mock()
        rest.create_listen_key.return_value = 'private-sentinel'
        received = []

        class QuietSocket:
            def recv_text(self, **kwargs):
                clock[0] += 60_000
                if clock[0] >= 31 * 60_000:
                    return '{"e":"ACCOUNT_UPDATE"}'
                raise TimeoutError()
            def close(self):
                pass

        factory = Mock(return_value=QuietSocket())
        client = BinanceUserStreamClient(make_config(), rest, on_message=received.append,
            transport_factory=factory, now_ms=lambda: clock[0], sleep=lambda _: None)
        status = client.run(max_messages=1, max_reconnects=0)
        self.assertEqual(len(received), 1)
        rest.keepalive_listen_key.assert_called_once()
        self.assertEqual(status.connection_count, 1)
        self.assertNotIn('private-sentinel', repr(status))

    def test_message_is_delivered_before_failed_renewal_and_retry_is_throttled(self):
        clock = [0]
        rest = Mock()
        rest.create_listen_key.return_value = 'key'
        rest.keepalive_listen_key.side_effect = RuntimeError('HTTP 503')
        received = []
        client = BinanceUserStreamClient(make_config(), rest, on_message=received.append,
            transport_factory=Mock(), now_ms=lambda: clock[0])
        client._connect_with_fresh_listen_key('', 1)
        clock[0] = 30 * 60_000
        client._handle_raw_message('{"e":"ACCOUNT_UPDATE"}', None)
        client._keepalive_if_due()
        self.assertEqual(len(received), 1)
        rest.keepalive_listen_key.assert_called_once()

    def test_missing_credentials_fails_before_retry_loop(self):
        from kis_hl.binance.client import BinanceFuturesClient
        config = replace(make_config(), api_key='')
        factory = Mock()
        client = BinanceUserStreamClient(config, BinanceFuturesClient(config), on_message=lambda _: None,
            transport_factory=factory, sleep=lambda _: None)
        with self.assertRaisesRegex(RuntimeError, 'credentials'):
            client.run(max_reconnects=0)
        factory.assert_not_called()

    def test_permanent_auth_error_stops_and_hides_vendor_message(self):
        from kis_hl.streaming import PermanentWebSocketError
        rest = Mock()
        rest.create_listen_key.side_effect = RuntimeError('HTTP 401 -2015 private-sentinel')
        client = BinanceUserStreamClient(make_config(), rest, on_message=lambda _: None,
            transport_factory=Mock(), sleep=lambda _: self.fail('must not retry'))
        with self.assertRaises(PermanentWebSocketError) as caught:
            client.run()
        self.assertNotIn('private-sentinel', str(caught.exception))
        rest.create_listen_key.assert_called_once()

    def test_permanent_websocket_handshake_denial_stops(self):
        from kis_hl.streaming import PermanentWebSocketError
        error = RuntimeError('private-sentinel')
        error.status_code = 403
        rest = Mock()
        rest.create_listen_key.return_value = 'private-sentinel'
        client = BinanceUserStreamClient(make_config(), rest, on_message=lambda _: None,
            transport_factory=Mock(side_effect=error), sleep=lambda _: self.fail('must not retry'))
        with self.assertRaises(PermanentWebSocketError):
            client.run(max_reconnects=0)

    def test_market_parser_rejects_nonfinite_and_preserves_frame(self):
        for price in ('NaN', 'Infinity', '-1', '0'):
            self.assertEqual(parse_market_ticks({'e':'markPriceUpdate','s':'BTCUSDT','p':price}, received_at_ms=1), [])
        frame = {'e':'markPriceUpdate','s':'BTCUSDT','p':'100','extra_vendor_field':7}
        self.assertEqual(parse_market_ticks(frame, received_at_ms=1)[0].raw['frame'], frame)

    def test_public_tier_variants(self):
        for stream in ('!bookTicker', 'btcusdt@rpiDepth@500ms'):
            self.assertEqual(stream_route(stream), 'public')


class ConfigReviewTests(unittest.TestCase):
    def test_credentials_are_not_in_repr(self):
        config = replace(make_config(), api_key='sentinel-api-key', api_secret='sentinel-api-secret')
        self.assertNotIn('sentinel-api-key', repr(config))
        self.assertNotIn('sentinel-api-secret', repr(config))

    def test_ambiguous_or_insecure_environment_rejected(self):
        for env in ({'BINANCE_TESTNET':'yes'}, {'BINANCE_BASE_URL':'http://fapi.binance.com'},
                    {'BINANCE_WS_USER_URL':'ws://fstream.binance.com/private'},
                    {'BINANCE_TESTNET':'true','BINANCE_BASE_URL':'https://fapi.binance.com'}):
            with self.subTest(env=env), self.assertRaisesRegex(RuntimeError, 'BINANCE'):
                load_binance_config(env)
