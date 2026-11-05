"""Resumable physical location and item delivery validation in isolated Cemu saves.

Each location requires a real game check followed by independently verified AP
receipts. Fixture positioning assists travel; it does not certify puzzle logic.
Missing combat automation or inaccessible scenes remain explicit failures.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import sys
import time

from items import scenarios, world_reference

ROOT = Path(__file__).resolve().parents[2]


def manifest(mode, kinds=None):
    reference = world_reference()
    from importlib import import_module
    combat = import_module(reference.__package__ + '.static.combat').catalog()['locations']
    locations = [*reference.load_chests(), *reference.load_completions(), *combat]
    locations = [dict(entry, kind=entry.get('kind', 'chest')) for entry in locations]
    # Start with the known smoke chest, then stable IDs for reproducible resumes.
    locations.sort(key=lambda e: (e.get('hash_id') != 2009260213, e['id']))
    if kinds is not None:
        unknown = set(kinds) - {entry['kind'] for entry in locations}
        if unknown: raise ValueError('Unknown location kinds: ' + ', '.join(sorted(unknown)))
        locations = [entry for entry in locations if entry['kind'] in kinds]
    if mode == 'simplified': locations = locations[:1]
    elif mode == 'partial':
        selected = {}
        for entry in locations: selected.setdefault(entry['kind'], entry)
        if 'miniboss' in selected:
            selected['miniboss'] = next(e for e in locations if e.get('actor') == 'Enemy_Giant_Junior')
        locations = list(selected.values())
    elif mode != 'full': raise ValueError('Unknown coverage mode')
    # Choose unique types; each selected progressive reward tests all its tiers.
    rewards = list({case['name']: case for case in scenarios(mode)}.values())
    return [dict(location=entry, reward=rewards[i % len(rewards)]['name']) for i, entry in enumerate(locations)]


def atomic_json(path, value):
    path.with_suffix('.tmp').write_text(json.dumps(value, indent=2))
    path.with_suffix('.tmp').replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('simplified', 'partial', 'full'), default='full')
    parser.add_argument('--kinds', help='Comma-separated production location kinds to include: chest,shrine,tower,miniboss,boss')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--keep-runtime', action='store_true', help="Retain successful visits' emulator profiles; failures always retain theirs")
    parser.add_argument('--manifest-only', action='store_true')
    parser.add_argument('--location-timeout', type=int, default=120)
    parser.add_argument('--display', default=':0')
    args, extra = parser.parse_known_args()
    if not 30 <= args.location_timeout <= 1800: parser.error('Invalid location timeout')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=args.resume)
    kinds = None if args.kinds is None else {part.strip() for part in args.kinds.split(',') if part.strip()}
    if args.kinds is not None and not kinds: parser.error('--kinds must name at least one location kind')
    try: entries = manifest(args.mode, kinds)
    except ValueError as exc: parser.error(str(exc))
    sources = [*sorted((ROOT/'worlds/botw/static').glob('*.py')),
               *sorted((ROOT/'src/hook').glob('*.asm')),
               *sorted(path for path in (ROOT/'src/client').rglob('*.cs') if not {'bin','obj'} & set(path.parts))]
    contract = dict(cases=entries, items=world_reference().item_data, native_profiles=world_reference().native_grants,
                    sources={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources})
    identity = hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()
    manifest_path = output / 'manifest.json'
    if manifest_path.exists():
        if json.loads(manifest_path.read_text())['identity'] != identity:
            parser.error('Location, delivery or source contract changed; use a fresh output directory')
    else: atomic_json(manifest_path, dict(identity=identity, mode=args.mode,
                                         kinds=sorted(kinds) if kinds is not None else None, cases=entries))
    if args.manifest_only:
        print(f'{len(entries)} physical locations planned; no locations tested')
        return 0
    state_path = output / 'result.json'
    state = json.loads(state_path.read_text()) if args.resume and state_path.exists() else dict(cases={})
    state.update(identity=identity, planned=len(entries), passed=False, running=True)
    started = time.monotonic()
    def checkpoint():
        state.update(completed=sum(e.get('passed', False) for e in state['cases'].values()),
                     failed=sum(not e.get('passed', False) for e in state['cases'].values()),
                     elapsed_this_run=time.monotonic()-started)
        atomic_json(state_path, state)
    try:
        # All item types/tiers share one launch before the per-location visits.
        item_output = output / 'items'
        item_result = item_output / 'result.json'
        if not (args.resume and item_result.exists() and json.loads(item_result.read_text()).get('passed')):
            if item_output.exists(): item_output = output / f'items-{time.time_ns()}'
            subprocess.run([sys.executable, str(ROOT/'tests/cemu/run.py'), '--items', args.mode,
                            '--watch-combat', '--all-checks', '--output', str(item_output), '--display', args.display, *extra], check=True)
            state['item_evidence'] = str(item_output / 'result.json')
        for number, entry in enumerate(entries, 1):
            location = entry['location']; key = str(location['id'])
            if state['cases'].get(key, {}).get('passed'): continue
            case_output = output / f'{location["id"]:08X}-{time.time_ns()}'
            checkpoint()
            print(f'VISIT {number}/{len(entries)}: {location["name"]}', flush=True)
            command = [sys.executable, str(ROOT/'tests/cemu/run.py'), '--location-id', key,
                       '--reward', entry['reward'], '--output', str(case_output), '--display', args.display,
                       '--timeout', str(args.location_timeout), '--assisted-combat', '--fast-fixtures', *extra]
            completed = subprocess.run(command, check=False)
            result_path = case_output/'result.json'
            evidence = json.loads(result_path.read_text()) if result_path.exists() else dict(error='No runner result')
            verified = completed.returncode == 0 and evidence.get('passed') and evidence.get('physical_check_passed')
            state['cases'][key] = dict(name=location['name'], kind=location['kind'], reward=entry['reward'],
                                       passed=bool(verified), evidence=str(result_path), error=evidence.get('error'))
            if verified and not args.keep_runtime:
                for folder in ('mlc', 'cache', 'data', 'config'):
                    shutil.rmtree(case_output/folder, ignore_errors=True)
                state['cases'][key]['runtime_pruned'] = True
            checkpoint()
        state['passed'] = state['completed'] == len(entries)
        return 0 if state['passed'] else 1
    finally:
        state['running'] = False
        checkpoint()


if __name__ == '__main__': sys.exit(main())
