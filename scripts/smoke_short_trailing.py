"""Offline short replay through separate CLI processes and persistent SQLite."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='short-trailing-') as temp:
        db = Path(temp) / 'paper.sqlite'
        base = [sys.executable, '-m', 'kis_hl.cli', '--db', str(db), 'trailing']
        commands = [base + ['replay', '--input', 'examples/trailing-stop-short-replay.jsonl'],
                    base + ['status']]
        results = []
        for command in commands:
            result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=True)
            results.append(json.loads(result.stdout))
        row, status = results[0], results[1]['positions'][0]
        assert row['state'] == status['state'] == 'PAPER_EXIT'
        assert row['side'] == status['trail']['side'] == 'short'
        assert status['trail']['low'] == '92' and status['trail']['threshold'] == '96'
        assert status['exit_intent']['reason'] == 'trailing'
        assert status['exit_intent']['created_ms'] == 1080000
        assert status['attempts'] == []
        with sqlite3.connect(db) as connection:
            assert connection.execute('SELECT COUNT(*) FROM trailing_exit_intents').fetchone()[0] == 1
            assert connection.execute('SELECT COUNT(*) FROM trailing_exit_attempts').fetchone()[0] == 0
        print('$ python -m kis_hl.cli --db PAPER_DB trailing replay')
        print('  --input examples/trailing-stop-short-replay.jsonl')
        print(json.dumps({k: row[k] for k in ['state', 'side']}, indent=2))
        print('$ python -m kis_hl.cli --db PAPER_DB trailing status')
        print(json.dumps({'low': status['trail']['low'], 'threshold': status['trail']['threshold'],
                          'exit_intent': status['exit_intent']['reason'], 'attempts': status['attempts']}, indent=2))
        print('PASS: threshold 104 -> 96; durable intent; zero order attempts.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
