"""Thin scheduling/stdout delivery wrapper for the read-only TS advisory."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_suffix('.json'))
    parser.add_argument('--state-path', type=Path, help='Use a scratch alert database for diagnostic reads')
    parser.add_argument('--report', action='store_true', help='Print sanitized health evidence even without notifications')
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text())
        root = Path(config['root'])
        sys.path.insert(0, str(root))
        from kis_hl.advisory_ts import run_monitor
        result = run_monitor(root, config['expected_account'], config['owner_ids'], state_path=args.state_path)
    except Exception:
        # Scheduler/config/storage failure is distinct from a completed degraded tick.
        print('Nine-minute advisory scheduler failed: configuration/storage/module unavailable; details omitted.', file=sys.stderr)
        return 1
    if args.report:
        print(json.dumps(result, sort_keys=True))
    elif result['messages']:
        print('\n'.join(result['messages']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
