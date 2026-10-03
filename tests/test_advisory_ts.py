"""Offline advisory monitor regressions; all data is synthetic."""
from decimal import Decimal
import unittest

from kis_hl.advisory_ts import aggregate, ObservationError


def candles(start=540000, count=9):
    return [dict(t=start+i*60000, T=start+(i+1)*60000-1,
                 h='23.264', c='22.607') for i in range(count)]


class AggregationTests(unittest.TestCase):
    def test_complete_bucket(self):
        self.assertEqual(aggregate(candles(), 540000, 1080000),
                         [(540000, Decimal('23.264'), Decimal('22.607'))])

    def test_gap_explains_bucket_and_missing_minute(self):
        raw = candles(); del raw[4]
        with self.assertRaises(ValueError) as raised:
            aggregate(raw, 540000, 1080000)
        self.assertEqual(raised.exception.reason, 'coverage_gap')
        self.assertEqual(raised.exception.bucket_start_ms, 540000)
        self.assertEqual(raised.exception.missing_minutes_ms, [780000])

    def test_boundary_invalid_minute_is_gap_and_later_finalization_succeeds(self):
        raw = candles(); raw[4]['T'] -= 1
        with self.assertRaises(ObservationError) as raised:
            aggregate(raw, 540000, 1080000)
        self.assertEqual(raised.exception.missing_minutes_ms, [780000])
        raw[4]['T'] += 1
        self.assertEqual(len(aggregate(raw, 540000, 1080000)), 1)

    def test_malformed_nan_duplicate_and_high_below_close_rejected(self):
        for change in ('NaN', 'Infinity', '0', '-1', 'secret-token'):
            raw = candles(); raw[0]['h'] = change
            with self.subTest(change=change), self.assertRaises(ObservationError) as raised:
                aggregate(raw, 540000, 1080000)
            self.assertEqual(raised.exception.reason, 'invalid_schema')
            self.assertNotIn(change, str(raised.exception))
        for raw in ([None], candles()+candles()[:1], [dict(candles()[0], h='1')]+candles()[1:]):
            with self.assertRaises(ObservationError):
                aggregate(raw, 540000, 1080000)


import copy
import json
import sqlite3
from unittest.mock import patch

from kis_hl.advisory_ts import Monitor, initialize
from kis_hl.config import HyperliquidConfig
from kis_hl.hyperliquid.client import HyperliquidInfoClient

COINS = {'xyz:KORU': 'owner-koru', 'xyz:SP500': 'owner-sp500'}


def owner(coin, owner_id):
    return ('PROTECTED', dict(id=owner_id, mode='live', observed_size='34.2',
        first_fill_ms=1000, created_ms=0, plan=dict(instrument='hl:'+coin,
        atr='1.0588', atr_multiple='3', local_atr_multiple='3')))


class ReadOnlyInfo(HyperliquidInfoClient):
    """Exercise the real info client's request builders; reject mutations."""
    def __init__(self):
        super().__init__(HyperliquidConfig('https://api.hyperliquid.xyz', 'fixture', '', 'default'))
        self.requests = []
        self.raw = {coin: candles() for coin in COINS}
        self.bids = {coin: '22.6' for coin in COINS}
        self.quantities = {coin: '34.2' for coin in COINS}
        self.orders = [dict(coin=coin, reduceOnly=True, side='A', sz='34.2', orderType=kind)
                       for coin in COINS for kind in ['Stop Market', 'Trailing Stop Market']]
        self.failure = None

    def post_info(self, payload):
        allowed = {'clearinghouseState', 'frontendOpenOrders', 'candleSnapshot', 'l2Book', 'userFillsByTime'}
        if payload.get('type') not in allowed or any(k in payload for k in ('signature', 'action', 'nonce')):
            raise AssertionError('Mutation path forbidden')
        self.requests.append(copy.deepcopy(payload))
        kind = payload['type']
        if self.failure == kind:
            raise RuntimeError('SECRET_TOKEN accountPayload={private_key: SECRET_KEY}')
        if kind == 'clearinghouseState':
            return {'assetPositions': [{'position': dict(coin=c, szi=q, entryPx='22.1')}
                                      for c, q in self.quantities.items()]}
        if kind == 'frontendOpenOrders':
            return copy.deepcopy(self.orders)
        if kind == 'candleSnapshot':
            return copy.deepcopy(self.raw[payload['req']['coin']])
        if kind == 'l2Book':
            return dict(levels=[[dict(px=self.bids[payload['coin']])], []])
        if kind == 'userFillsByTime':
            return []


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:'); self.addCleanup(self.conn.close)
        initialize(self.conn)
        self.conn.executemany('INSERT INTO bars VALUES(?,?,?,?,?)',
            [(c, 1000, 540000, '23.264', '20.0876') for c in COINS])
        self.info = ReadOnlyInfo()
        self.owners = {oid: owner(c, oid) for c, oid in COINS.items()}
        self.monitor = Monitor(self.conn, self.info, self.read_owner, lambda _: set())

    def read_owner(self, oid):
        if oid not in self.owners:
            raise ObservationError('owner_missing')
        return copy.deepcopy(self.owners[oid])

    def tick(self, now=1095001):
        return self.monitor.tick(COINS, now)

    def bar(self, coin='xyz:KORU'):
        return self.conn.execute('SELECT generation,last_end,high,threshold FROM bars WHERE coin=?', (coin,)).fetchone()

    def test_gap_retry_keeps_watermark_high_threshold_and_recovers_once(self):
        prior = self.bar(); del self.info.raw['xyz:KORU'][4]
        result = self.tick()
        self.assertEqual(self.bar(), prior)
        d = result['diagnostics']['xyz:KORU']
        self.assertEqual((d['reason'], d['operation'], d['prior_watermark_ms']), ('coverage_gap', 'aggregation', 540000))
        self.assertEqual(d['missing_minutes_ms'], [780000])
        self.assertEqual(self.bar('xyz:SP500')[1], 1080000)
        self.assertFalse(self.tick()['messages'])
        self.info.raw['xyz:KORU'] = candles()
        result = self.tick(1097000)
        recovery = [m for m in result['messages'] if 'recovered' in m]
        self.assertEqual(len(recovery), 1)
        self.assertIn('covered_through_ms=1080000', recovery[0])
        self.assertEqual(self.bar(), (1000, 1080000, '23.264', '20.0876'))
        self.assertEqual(result['diagnostics']['xyz:KORU']['last_success_ms'], 1097000)
        self.assertFalse(self.tick(1099000)['messages'])
        requests = [r for r in self.info.requests if r['type']=='candleSnapshot' and r['req']['coin']=='xyz:KORU']
        self.assertEqual([r['req']['startTime'] for r in requests], [540000]*3)

    def test_different_value_errors_notify_and_repeat_reason_deduplicates(self):
        self.info.raw['xyz:KORU'] = candles(count=8)
        first = self.tick(); self.info.raw['xyz:KORU'] = candles()
        self.info.bids['xyz:KORU'] = 'NaN'
        second = self.tick()
        self.assertEqual(first['diagnostics']['xyz:KORU']['reason'], 'coverage_gap')
        self.assertEqual(second['diagnostics']['xyz:KORU']['reason'], 'invalid_bid')
        self.assertEqual(second['diagnostics']['xyz:KORU']['operation'], 'bid')
        self.assertTrue(second['messages']); self.assertFalse(self.tick()['messages'])
        self.assertEqual(self.bar()[1], 540000)
        self.info.bids['xyz:KORU'] = '22.6'
        self.assertEqual(sum('recovered' in m for m in self.tick()['messages']), 1)

    def test_failed_bid_does_not_commit_candidate_high_or_breach(self):
        prior = self.bar(); self.info.raw['xyz:KORU'][0]['h']='50'
        self.info.bids['xyz:KORU']='SECRET_KEY'
        result = self.tick()
        self.assertEqual(self.bar(), prior)
        self.assertFalse(any('TS advisory:' in m for m in result['messages']))
        self.assertNotIn('SECRET_KEY', json.dumps(result))

    def test_owner_failure_isolated_and_no_orders_or_parameters_changed(self):
        baseline = copy.deepcopy((self.info.orders, self.info.quantities, self.owners))
        del self.owners['owner-koru']
        result = self.tick()
        self.assertEqual(result['diagnostics']['xyz:KORU']['reason'], 'owner_missing')
        self.assertEqual(result['diagnostics']['xyz:SP500']['reason'], 'verified')
        self.assertEqual((self.info.orders, self.info.quantities), baseline[:2])
        self.assertEqual(self.owners['owner-sp500'], baseline[2]['owner-sp500'])
        self.assertEqual(sum(r['type']=='clearinghouseState' for r in self.info.requests), 1)

    def test_reason_classification_and_transport_payload_sanitization(self):
        cases = [('mismatch','exposure_mismatch'), ('entry','entry_evidence_missing'),
                 ('identity','owner_identity_mismatch'), ('schema','invalid_schema'),
                 ('retention','retention_limit'), ('transport','read_unavailable')]
        for mode, expected in cases:
            with self.subTest(mode=mode):
                self.setUp()
                if mode=='mismatch': self.info.quantities['xyz:KORU']='1'
                if mode=='entry': self.owners['owner-koru'][1]['first_fill_ms']=None
                if mode=='identity': self.owners['owner-koru'][1]['mode']='dry'
                if mode=='schema': self.owners['owner-koru'][1]['plan']['atr']='secret-token'
                if mode=='transport': self.info.failure='clearinghouseState'
                result = self.tick(540000 + 5000*60000 + 15001 if mode=='retention' else 1095001)
                self.assertEqual(result['diagnostics']['xyz:KORU']['reason'], expected)
                output=json.dumps(result)+str(self.conn.execute('SELECT * FROM diagnostics').fetchall())
                for secret in ('SECRET_TOKEN', 'SECRET_KEY', 'private_key', 'accountPayload', 'secret-token'):
                    self.assertNotIn(secret, output)
                self.assertEqual(self.bar()[1],540000)

    def test_last_success_and_legacy_error_recovery(self):
        self.tick()
        self.conn.execute("UPDATE alerts SET value='ValueError' WHERE coin='xyz:KORU' AND kind='error'")
        result = self.tick(1097000)
        self.assertEqual(sum('recovered' in m for m in result['messages']), 1)
        self.info.bids['xyz:KORU']='0'
        d=self.tick(1099000)['diagnostics']['xyz:KORU']
        self.assertEqual(d['last_success_ms'],1097000)
        self.assertEqual(d['protection'], {'fixed_sl':'yes','native_ts':'yes'})
        self.assertEqual(d['covered_through_ms'],1080000)

    def test_configuration_failure_has_no_exchange_reads(self):
        result=self.monitor.tick(COINS,1095001,configuration_error=True)
        self.assertEqual({d['reason'] for d in result['diagnostics'].values()}, {'configuration_mismatch'})
        self.assertFalse(self.info.requests)

    def test_missing_protection_is_independent_of_monitor_health(self):
        self.info.orders=[]
        result=self.tick()
        self.assertEqual(result['diagnostics']['xyz:KORU']['reason'],'verified')
        self.assertEqual(result['diagnostics']['xyz:KORU']['protection']['native_ts'],'no')
        self.assertEqual(sum(m.startswith('Urgent') for m in result['messages']),4)
        self.assertFalse(self.tick()['messages'])

    def test_closed_exposure_does_not_certify_recovery(self):
        self.info.bids['xyz:KORU']='0'; self.tick()
        del self.info.quantities['xyz:KORU']
        result=self.tick()
        self.assertEqual(result['diagnostics']['xyz:KORU']['reason'],'closed')
        self.assertFalse(any('recovered' in m for m in result['messages']))
        self.assertEqual(self.bar()[1],540000)

    @patch('urllib.request.urlopen', side_effect=AssertionError('Real network forbidden'))
    @patch('kis_hl.hyperliquid.client.HyperliquidTradingClient', side_effect=AssertionError('Trading forbidden'))
    def test_only_recorded_info_reads_never_signed_or_network_mutations(self, *_):
        self.assertEqual(self.tick()['diagnostics']['xyz:KORU']['reason'],'verified')
        self.assertTrue(self.info.requests)
        source=__import__('inspect').getsource(__import__('kis_hl.advisory_ts',fromlist=['Monitor']))
        for forbidden in ('HyperliquidTradingClient', '/exchange', 'sign_l1_action', 'place_order(', 'cancel_order('):
            self.assertNotIn(forbidden,source)


class DeploymentTests(unittest.TestCase):
    def test_scoped_install_preserves_unrelated_files_and_backups_wrapper(self):
        from scripts.install_hl_9m_ts_alert import install, SOURCE_ROOT
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'kis_hl').mkdir(); (root/'scripts').mkdir()
            unrelated=root/'kis_hl/managed_execution.py'; unrelated.write_text('unrelated dirty source')
            script=root/'scripts/hl_9m_ts_alert.py'
            old=f"from pathlib import Path\nROOT = Path({str(root)!r})\nACCOUNT = 'fixture'\nOWNER_IDS = {{'xyz:KORU':'owner-koru'}}\n"
            script.write_text(old)
            self.assertFalse(install(script)['applied'])
            self.assertEqual(script.read_text(),old)
            result=install(script,apply=True)
            self.assertEqual(script.read_bytes(),(SOURCE_ROOT/'scripts/hl_9m_ts_alert.py').read_bytes())
            self.assertEqual((root/'kis_hl/advisory_ts.py').read_bytes(),(SOURCE_ROOT/'kis_hl/advisory_ts.py').read_bytes())
            self.assertEqual(unrelated.read_text(),'unrelated dirty source')
            manifest=json.loads((Path(result['backup'])/'manifest.json').read_text())
            saved=next(f for f in manifest['files'] if f['path']==str(script))
            self.assertEqual((Path(result['backup'])/saved['backup']).read_text(),old)
            self.assertEqual(json.loads(script.with_suffix('.json').read_text())['owner_ids'],{'xyz:KORU':'owner-koru'})

    def test_wrapper_scheduler_error_is_sanitized(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import subprocess
        with TemporaryDirectory() as temporary:
            config=Path(temporary)/'config.json';config.write_text('SECRET_TOKEN invalid json')
            run=subprocess.run([__import__('sys').executable,'scripts/hl_9m_ts_alert.py','--config',str(config),'--report'],capture_output=True,text=True)
            self.assertEqual(run.returncode,1)
            self.assertNotIn('SECRET_TOKEN',run.stdout+run.stderr)
            self.assertIn('scheduler failed',run.stderr)
