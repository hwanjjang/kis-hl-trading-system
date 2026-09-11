import json
import unittest
from kis_hl.streaming import MaintainedWebSocketClient


class StreamHookTests(unittest.TestCase):
    def test_silence_and_disconnect_notify_state_owner(self):
        events=[]
        class Transport:
            def recv_text(self, **kw): raise TimeoutError()
            def close(self): pass
        times=iter([0,0,0,2000,2000,2000,2000])
        client=MaintainedWebSocketClient(url='test',subscriptions=[],on_message=lambda *a:None,
            transport_factory=lambda *a:Transport(),now_ms=lambda:next(times,3000),stale_after_ms=1000,
            on_idle=lambda:events.append('idle'),on_disconnect=lambda:events.append('disconnected'))
        client.run(max_reconnects=0)
        self.assertIn('idle',events)
        self.assertIn('disconnected',events)
