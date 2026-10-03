import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from kis_hl.journal_sync import Scope
from tests.test_conditional_add import capital

class EthWatchTests(unittest.TestCase):
    def runner(self):
        from kis_hl import eth_new_entry_watch
        return eth_new_entry_watch

    def test_paper_ready_and_once_live_handoff(self):
        m = self.runner()
        now = m.EXPIRES_MS-60000
        end = now//540000*540000; now = end+1
        scope = Scope('hyperliquid','mainnet',m.ACCOUNT).key
        g = Mock(scope=scope)
        g.completed_nine_minute_bars.return_value = [
            dict(start_ms=end-1080000,end_ms=end-540000,high='2700',close='2690'),
            dict(start_ms=end-540000,end_ms=end,high='2710',close='2701')]
        g.preflight.return_value = dict(observed_now_ms=now, time_ms=now, price='2700',ask='2701',
            price_step='.01',quantity_step='.0001',capital_evidence=capital(scope)|{'asof_ms':now},
            position='0',open_orders=[],eligible=True,session_open=True,available_notional='2000',
            portfolio_notional='0',correlated_notional='0',entry_order_type='limit')
        result = m.review(g, authorized_ms=end-1, now_ms=now)
        self.assertEqual(result['status'],'ready')
        self.assertEqual(result['plan']['fixed_stop_price'],'2610')
        g.submit.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp:
            from kis_hl.managed_execution import ExecutionStore
            store=ExecutionStore(Path(tmp)/'offline.sqlite')
            store.heartbeat(scope,now,live=True)
            row=m.handoff(store,result,scope,now)
            self.assertEqual(row['state'],'QUEUED')
            with self.assertRaises(RuntimeError): m.handoff(store,result,scope,now)
        g.submit.assert_not_called()

    def test_watch_cli_is_available_offline(self):
        import subprocess
        result=subprocess.run([__import__('sys').executable,'-m','kis_hl.eth_new_entry_watch','--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        self.assertIn('--watch',result.stdout)
        self.assertIn('--manual-authorization',result.stdout)

    def test_expired_default_does_not_read(self):
        m=self.runner(); g=Mock()
        self.assertEqual(m.review(g,authorized_ms=m.EXPIRES_MS-1,now_ms=m.EXPIRES_MS)['status'],'expired')
        g.preflight.assert_not_called()


if __name__=='__main__': unittest.main()
