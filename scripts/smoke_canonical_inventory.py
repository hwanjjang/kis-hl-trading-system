"""Exercise canonical inventory eligibility through real offline CLI processes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def main():
    with TemporaryDirectory(prefix='inventory-smoke-') as directory:
        folder = Path(directory)
        database = folder / 'state.sqlite'
        env = {'PATH': os.environ.get('PATH', ''), 'PYTHONPATH': str(ROOT)}
        calls = 0

        def cli(*args):
            nonlocal calls
            run = subprocess.run([sys.executable, '-m', 'kis_hl.cli', '--db',
                                  str(database), *args], cwd=folder, env=env,
                                 capture_output=True, text=True, timeout=30)
            if run.returncode:
                raise RuntimeError(f'CLI failed: {args}: {run.stderr}')
            calls += 1
            return json.loads(run.stdout)

        rows = []
        for symbol, sequence, anchored in [
                ('OVERSELL', [('buy', 3), ('sell', 10), ('buy', 7)], True),
                ('UNANCHORED', [('buy', 3), ('sell', 3)], False),
                ('VALID', [('buy', 3), ('sell', 3)], True)]:
            for index, (side, quantity) in enumerate(sequence):
                row = dict(source_id=f'{symbol}-{index}', instrument=f'kis:{symbol}',
                           currency='USD', event_start_ms=100 + index * 10,
                           event_end_ms=101 + index * 10, time_precision='MILLISECOND',
                           grain='EXECUTION', side=side, quantity=str(quantity),
                           price='100', notional=str(quantity * 100), total_cost='1',
                           costs={'broker': '1'})
                if index == 0 and anchored:
                    row['position_before'] = '0'
                rows.append(row)
        source = folder / 'source.json'
        source.write_text(json.dumps(rows))
        manifest = folder / 'manifest.json'
        manifest.write_text(json.dumps(dict(schema_version=1,
            accounts=[dict(alias='test', venue='kis', environment='sim', native_id='synthetic')],
            files=[dict(path=source.name, sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                        account='test', role='raw', parser='statement')],
            coverage=[dict(account='test', dataset='trade', start_ms=0, end_ms=10**15,
                           status='complete', details={'source': 'synthetic fixture'})])))
        assert not cli('data', 'import', '--manifest', str(manifest))['applied']
        assert not database.exists(), 'Preview created a database'
        first = cli('data', 'import', '--manifest', str(manifest), '--apply')
        replay = cli('data', 'import', '--manifest', str(manifest), '--apply')
        assert first['fact_ids'] == replay['fact_ids']
        account = cli('data', 'status')['accounts'][0]['id']
        report = cli('data', 'journal', '--accounts', account)
        cycles = {c['instrument']: c for c in report['cycles']}
        assert cycles['kis:VALID']['status'] == 'FINALIZED'
        assert cycles['kis:UNANCHORED']['status'] == 'PENDING'
        assert 'inventory_unanchored' in cycles['kis:UNANCHORED']['reasons']
        assert 'opening_inventory_gap' in cycles['kis:OVERSELL']['reasons']
        assert all(c['side'] == 'long' for c in report['cycles'])
        assert all(c['net_return_pct'] is None for k, c in cycles.items() if k != 'kis:VALID')
        summary = report['summary_by_account_currency'][0]
        assert summary['statistics_by_strategy']['unassigned']['trade_count'] == 1
        assert summary['trading_fee'] == '7'
        assert summary['net_booked_pnl'] is None
        target = folder / 'report.json'
        cli('data', 'export', '--report-id', str(report['report_id']), '--output', str(target))
        before = target.read_bytes()
        assert json.loads(before)['inventory_policy_version'] == 'kis-inventory-v1'
        cli('data', 'journal', '--accounts', account)
        assert target.read_bytes() == before
    assert not folder.exists(), 'Temporary fixtures were not cleaned up'
    print(json.dumps(dict(status='passed', cli_processes=calls, raw_facts=7,
                          finalized_cycles=1, invalid_returns_excluded=True,
                          fees_preserved=True, immutable_export=True, cleanup=True)))


if __name__ == '__main__':
    main()
