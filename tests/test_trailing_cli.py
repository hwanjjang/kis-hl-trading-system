from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from kis_hl.cli import build_parser, main


class TrailingCliTests(unittest.TestCase):
    def test_enroll_and_run_default_to_paper(self):
        p=build_parser()
        a=p.parse_args(['trailing','enroll','--symbol','BTC-PERP','--entry-order-id','5','--stop-order-id','7','--multiple','2','--max-gap-ms','15000','--slippage','0.01'])
        self.assertFalse(a.live)
        a=p.parse_args(['trailing','run','--position-id','abc'])
        self.assertFalse(a.live)

    def test_offline_replay_records_crossing_and_never_loads_exchange(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'ticks.jsonl'; db=Path(td)/'paper.sqlite'
            f.write_text('\n'.join(json.dumps(x) for x in [
                {'type':'position','symbol':'BTC-PERP','size':'1','entry':'100','atr':'2','multiple':'2','opened_ms':0,'max_gap_ms':540000},
                {'time_ms':1,'price':'100'},{'time_ms':540000,'price':'108'},{'time_ms':1080000,'price':'104'}]))
            out=io.StringIO()
            with patch('kis_hl.cli.load_hyperliquid_config', side_effect=AssertionError('network path used')), redirect_stdout(out):
                result=main(['--db',str(db),'trailing','replay','--input',str(f)])
            self.assertEqual(result,0)
            row=json.loads(out.getvalue())
            self.assertEqual(row['state'],'PAPER_EXIT')
            self.assertEqual(row['trail']['threshold'],'104')
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--db',str(db),'trailing','status']),0)
