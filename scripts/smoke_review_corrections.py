"""Offline real-CLI smoke for bounded reconciliation and immutable reports."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
RUNNER="""import sys
import kis_hl.config as config
config.load_dotenv=lambda *a,**k:None
from kis_hl.cli import main
raise SystemExit(main())
"""


def main():
    calls=0
    with TemporaryDirectory(prefix='review-correction-smoke-') as tmp:
        root=Path(tmp);db=root/'state.sqlite'
        def cli(*args):
            nonlocal calls
            calls+=1
            result=subprocess.run([sys.executable,'-c',RUNNER,'--db',str(db),*args],cwd=ROOT,text=True,capture_output=True,timeout=30,env={'PATH':os.environ.get('PATH',''),'PYTHONPATH':str(ROOT),'PYTHONDONTWRITEBYTECODE':'1'})
            if result.returncode:raise AssertionError(result.stderr)
            return json.loads(result.stdout)
        assert cli('data','status')['exists'] is False
        assert not db.exists()
        rows=[dict(source_id=str(i),instrument='kis:X',currency='USD',event_start_ms=i*10,event_end_ms=i*10+1,time_precision='MILLISECOND',grain='EXECUTION',side=side,quantity='1',price=price,notional=price,total_cost='1',costs={'broker':'1'}) for i,side,price in [(1,'buy','100'),(2,'sell','110')]]
        raw=root/'raw.json';raw.write_text(json.dumps(rows))
        account=dict(alias='k',venue='kis',environment='live',native_id='synthetic')
        manifest=dict(schema_version=1,accounts=[account],files=[dict(path=raw.name,sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),account='k',role='raw',parser='statement')])
        mf=root/'manifest.json';mf.write_text(json.dumps(manifest))
        assert cli('data','import','--manifest',str(mf))['applied'] is False
        assert not db.exists()
        cli('data','import','--manifest',str(mf),'--apply')
        aid=cli('data','status')['accounts'][0]['id']
        before=cli('data','journal','--accounts',aid)
        assert before['cycles'][0]['status']=='PENDING'
        source=root/'independent-statement.json'
        source.write_text(json.dumps(dict(schema_version=1,source='Synthetic independent statement',complete=True,account={k:v for k,v in account.items() if k!='alias'},dataset='trade',start_ms=0,end_ms=100,parser='statement',rows=rows,opening_inventory={'kis:X':'0'},closing_inventory={'kis:X':'0'})))
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        assert cli('data','reconcile','--statement',str(source),'--sha256',digest)['applied'] is False
        assert cli('data','reconcile','--statement',str(source),'--sha256',digest,'--apply')['applied'] is True
        after=cli('data','journal','--accounts',aid)
        assert after['cycles'][0]['status']=='FINALIZED'
        assert after['cycles'][0]['net_pnl']=='8'
        output=root/'journal.json';cli('data','export','--report-id',str(after['report_id']),'--output',str(output))
        frozen=output.read_bytes()
        assert before['report_id'] in cli('data','status')['stale_runs']
        backup=root/'backup.sqlite';cli('data','backup','--target',str(backup))
        restored=root/'restored.sqlite';cli('data','restore','--source',str(backup),'--target',str(restored))
        assert restored.exists() and output.read_bytes()==frozen
    assert not root.exists()
    print(json.dumps(dict(status='passed',cli_processes=calls,network=False,private_data=False,
        preview_read_only=True,net_pnl='8',immutable_export=True,backup_restore=True,cleanup=True)))


if __name__=='__main__':main()
