"""Install only the tested advisory module and thin profile wrapper.

No exchange requests, cron edits, operational database changes or repository sync.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def legacy_config(script):
    values = {}
    for node in ast.parse(script.read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in {'ACCOUNT', 'OWNER_IDS'}:
                values[name] = ast.literal_eval(node.value)
            elif name == 'ROOT' and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'Path':
                values[name] = ast.literal_eval(node.value.args[0])
    return dict(root=values['ROOT'], expected_account=values['ACCOUNT'], owner_ids=values['OWNER_IDS'])


def atomic_write(path, content):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.'+path.name, delete=False) as f:
        temporary = Path(f.name)
        f.write(content)
        f.flush(); os.fsync(f.fileno())
    try:
        os.chmod(temporary, 0o600 if path.suffix == '.json' else 0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def install(profile_script, *, apply=False):
    script = Path(profile_script).resolve()
    config_path = script.with_suffix('.json')
    config = json.loads(config_path.read_text()) if config_path.exists() else legacy_config(script)
    root = Path(config['root']).resolve()
    module = root / 'kis_hl/advisory_ts.py'
    wrapper_source = SOURCE_ROOT / 'scripts/hl_9m_ts_alert.py'
    module_source = SOURCE_ROOT / 'kis_hl/advisory_ts.py'
    if not script.is_file() or not module.parent.is_dir():
        raise ValueError('Existing deployment script and package are required')
    sources = {module: module_source.read_bytes(), config_path: (json.dumps(config, indent=2)+'\n').encode(),
               script: wrapper_source.read_bytes()}
    hashes = {str(target): hashlib.sha256(data).hexdigest() for target, data in sources.items()}
    if not apply:
        return dict(applied=False, files=hashes)
    backup = script.parent / ('hl-9m-ts-backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(mode=0o700)
    existing = {target: target.exists() for target in sources}
    for index, target in enumerate(sources):
        if existing[target]:
            shutil.copy2(target, backup / str(index))
    manifest = dict(files=[dict(path=str(t), existed=existing[t], backup=str(i)) for i,t in enumerate(sources)], hashes=hashes)
    (backup/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    try:
        # Import target first, configuration second, wrapper last: old wrapper remains
        # usable throughout installation; the monitor state is never touched.
        for target, content in sources.items():
            atomic_write(target, content)
        for target, content in sources.items():
            if target.read_bytes() != content:
                raise ValueError('Installed bytes do not match the tested source')
    except Exception:
        for index, target in enumerate(sources):
            if existing[target]:
                atomic_write(target, (backup/str(index)).read_bytes())
            else:
                target.unlink(missing_ok=True)
        raise
    return dict(applied=True, backup=str(backup), files=hashes)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile-script', type=Path, required=True)
    parser.add_argument('--apply', action='store_true', help='Apply the scoped installation; default only reports hashes')
    args=parser.parse_args()
    print(json.dumps(install(args.profile_script, apply=args.apply), sort_keys=True))


if __name__ == '__main__':
    main()
