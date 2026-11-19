"""Run physical Dark Beast Ganon completion and missing-prerequisite locking tests."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args, extra = parser.parse_known_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = {}
    for mode in ('locked', 'complete'):
        directory = output / mode
        process = subprocess.run([
            sys.executable, str(Path(__file__).with_name('run.py')), *extra,
            '--goal-test', mode, '--location-id', '3254779910',
            '--assisted-combat', '--output', str(directory)])
        evidence = directory / 'result.json'
        result = json.loads(evidence.read_text()) if evidence.exists() else {}
        results[mode] = dict(passed=process.returncode == 0 and result.get('passed') is True
                            and result.get('goal_test') == mode
                            and result.get('physical_check_passed') is True
                            and result.get('completion_flag') == 1,
                            evidence=str(evidence), exit_code=process.returncode)
        (output / 'result.json').write_text(json.dumps(dict(
            passed=len(results) == 2 and all(r['passed'] for r in results.values()),
            cases=results), indent=2))
    return 0 if all(r['passed'] for r in results.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
