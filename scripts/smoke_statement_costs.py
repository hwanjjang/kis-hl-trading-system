"""Offline real-CLI acceptance for unresolved costs, correction and safe backup."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
RUNNER = """import sys
import kis_hl.config as config
config.load_dotenv=lambda *a,**k:None
from kis_hl.cli import main
raise SystemExit(main())
"""


def main():
    calls = 0
    with TemporaryDirectory(prefix='statement-cost-smoke-') as tmp:
        root = Path(tmp)
        db = root / 'state.sqlite'

        def cli(*args, error=None):
            nonlocal calls
            calls += 1
            result = subprocess.run(
                [sys.executable, '-c', RUNNER, '--db', str(db), *args],
                cwd=ROOT, text=True, capture_output=True, timeout=30,
                env={'PATH': os.environ.get('PATH', ''), 'PYTHONPATH': str(ROOT),
                     'PYTHONDONTWRITEBYTECODE': '1'})
            if error is not None:
                assert result.returncode != 0, result.stdout
                assert error in result.stderr, result.stderr
                return
            assert result.returncode == 0, result.stderr
            return json.loads(result.stdout)

        backup = root / 'backup' / 'copy.sqlite'
        cli('data', 'backup', '--target', str(backup), error='not initialized')
        assert not db.exists() and not backup.parent.exists()
        rows = [dict(source_id=str(i), instrument='kis:X', currency='USD',
                     event_start_ms=i * 10, event_end_ms=i * 10 + 1,
                     time_precision='MILLISECOND', grain='EXECUTION', side=side,
                     quantity='1', price=price, notional=price, total_cost='1',
                     costs={'broker': '1'})
                for i, side, price in [(1, 'buy', '100'), (2, 'sell', '110')]]
        rows[0] |= {'position_before': '0', 'costs': {'broker': '10', 'tax': None}}
        account = dict(alias='k', venue='kis', environment='sim', native_id='synthetic')
        raw = root / 'raw.json'
        manifest = root / 'manifest.json'

        def write_manifest(correction=False):
            raw.write_text(json.dumps(rows))
            manifest.write_text(json.dumps(dict(schema_version=1, accounts=[account],
                files=[dict(path=raw.name, sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
                            account='k', role='raw', parser='statement', allow_correction=correction)],
                coverage=[dict(account='k', dataset='trade', start_ms=0, end_ms=100,
                               status='complete', details={'source': 'Synthetic test coverage'})])))

        write_manifest()
        assert cli('data', 'import', '--manifest', str(manifest))['applied'] is False
        assert not db.exists()
        cli('data', 'import', '--manifest', str(manifest), '--apply')
        aid = cli('data', 'status')['accounts'][0]['id']
        before = cli('data', 'journal', '--accounts', aid)
        cycle = before['cycles'][0]
        assert cycle['status'] == 'PENDING'
        assert cycle['net_pnl'] is None and cycle['net_return_pct'] is None
        assert cycle['cost_components'] == {'broker': '11'}
        summary = before['summary_by_account_currency'][0]
        assert summary['net_booked_pnl'] is None
        assert summary['statistics_by_strategy']['unassigned']['trade_count'] == 0
        output = root / 'before.json'
        cli('data', 'export', '--report-id', str(before['report_id']), '--output', str(output))
        frozen = output.read_bytes()
        source = root / 'statement.json'

        def write_statement():
            source.write_text(json.dumps(dict(schema_version=1, source='Synthetic independent statement',
                complete=True, account={k: v for k, v in account.items() if k != 'alias'},
                dataset='trade', start_ms=0, end_ms=100, parser='statement', rows=rows,
                opening_inventory={'kis:X': '0'}, closing_inventory={'kis:X': '0'})))
            return hashlib.sha256(source.read_bytes()).hexdigest()

        digest = write_statement()
        cli('data', 'reconcile', '--statement', str(source), '--sha256', digest,
            '--apply', error='Unresolved costs')
        rows[0] |= {'costs': {'broker': '10', 'tax': '0'}, 'total_cost': '10'}
        write_manifest(correction=True)
        cli('data', 'import', '--manifest', str(manifest), '--apply')
        digest = write_statement()
        cli('data', 'reconcile', '--statement', str(source), '--sha256', digest, '--apply')
        after = cli('data', 'journal', '--accounts', aid)
        assert after['cycles'][0]['status'] == 'FINALIZED'
        assert after['cycles'][0]['trading_fee'] == '11'
        assert after['cycles'][0]['net_pnl'] == '-1'
        assert after['summary_by_account_currency'][0]['net_booked_pnl'] == '-1'
        assert before['report_id'] in cli('data', 'status')['stale_runs']
        old_export = root / 'old-again.json'
        cli('data', 'export', '--report-id', str(before['report_id']), '--output', str(old_export))
        assert old_export.read_bytes() == frozen == output.read_bytes()
        cli('data', 'backup', '--target', str(backup))
        restored = root / 'restored.sqlite'
        cli('data', 'restore', '--source', str(backup), '--target', str(restored))
        db = restored
        restored_report = cli('data', 'journal', '--accounts', aid)
        assert restored_report['cycles'][0]['net_pnl'] == '-1'
    assert not root.exists()
    print(json.dumps(dict(status='passed', cli_processes=calls, network=False, private_data=False,
                         unresolved_returns_pending=True, corrected_net_pnl='-1',
                         immutable_export=True, missing_backup_no_files=True,
                         backup_restore=True, cleanup=True)))


if __name__ == '__main__':
    main()
