"""Minimal executable entry point for the bundled player patcher."""
import argparse
import json
from pathlib import Path
import sys

from static.apply import apply_plan
from static.plan import read_plan
from static.resources import GameDump
from static.tracker_map import build, installed_map_directory


def main() -> int:
    if sys.argv[1:2] == ["--tracker-map"]:
        parser = argparse.ArgumentParser(description="Generate the BotW tracker map")
        parser.add_argument("--base", type=Path, required=True)
        parser.add_argument("--update", type=Path)
        args = parser.parse_args(sys.argv[2:])
        static = Path(__file__).resolve().parent / "static"
        try:
            locations = [entry for filename in ("tracker_chests.json", "completions.json")
                         for entry in json.loads((static / filename).read_text(encoding="utf-8"))["locations"]]
            build([root for root in (args.base, args.update) if root], installed_map_directory(), locations)
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    parser = argparse.ArgumentParser(description="Apply a BotW player patch")
    parser.add_argument("patch")
    parser.add_argument("--base", required=True)
    parser.add_argument("--update", required=True)
    parser.add_argument("--dlc")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        apply_plan(read_plan(args.patch), GameDump(args.base, args.update, args.dlc), args.output)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
