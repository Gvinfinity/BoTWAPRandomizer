"""Sequential Ganon-before-beasts acceptance route with real save-file handoffs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--resume', action='store_true', help='Continue from verified save handoffs in this output directory')
    args, extra = parser.parse_known_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=args.resume)
    previous = json.loads((root/'result.json').read_text())['cases'] if args.resume else []
    results = []
    source = None
    stages = [('early-ganon', 3254779910), ('wind', 3254779904),
              ('fire', 3254779905), ('water', 3254779906),
              ('thunder', 3254779907), ('final-ganon', 3254779910)]
    for index, (name, location) in enumerate(stages):
        prior = next((case for case in previous if case['stage'] == name and case['passed']), None)
        if prior:
            evidence = json.loads(Path(prior['evidence']).read_text())
            if not evidence.get('passed'):
                raise ValueError('Previous evidence is no longer passing')
            if 1 <= index <= 4:
                source = Path(evidence['saved_game'])
                if not source.is_file():
                    raise ValueError('Missing continuation save')
            results.append(prior)
            continue
        output = root / name
        if output.exists():
            output = root / f'{name}-retry-{time.time_ns()}'
        command = [sys.executable, str(Path(__file__).with_name('run.py')), *extra,
                   '--output', str(output), '--beast-goal', '--goal-test',
                   'complete' if index >= 4 else 'locked', '--location-id', str(location),
                   '--assisted-combat', '--journal-directory', str(root / 'journal')]
        # Ganon does not support a normal post-victory manual save. Its AP check
        # persists in the journal while the first Beast starts from the base save.
        if 1 <= index <= 4:
            command.append('--save-after-test')
        if source:
            command.extend(['--save-source', str(source), '--preserve-save-state'])
        process = subprocess.run(command)
        path = output / 'result.json'
        evidence = json.loads(path.read_text()) if path.exists() else {}
        passed = process.returncode == 0 and evidence.get('passed') is True
        if 1 <= index <= 4:
            passed = passed and bool(evidence.get('saved_game'))
            if passed:
                source = Path(evidence['saved_game'])
        results.append(dict(stage=name, passed=passed, evidence=str(path)))
        (root / 'result.json').write_text(json.dumps(dict(
            passed=len(results) == len(stages) and all(r['passed'] for r in results),
            cases=results), indent=2))
        if not passed:
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
