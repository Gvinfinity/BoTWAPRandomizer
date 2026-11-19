"""Minimal executable entry point for the bundled player patcher."""
import argparse
import sys

from static.apply import apply_plan
from static.plan import read_plan
from static.resources import GameDump


def main() -> int:
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
