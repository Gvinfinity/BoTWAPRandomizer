"""Build the offline tracker background from an installed Wii U game dump."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import ROOT
from botw_static.tracker_map import build, choose_tile, decode_tile, installed_map_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cemu-data', type=Path, default=Path.home() / '.local/share/Cemu')
    parser.add_argument('--base', type=Path)
    parser.add_argument('--update', type=Path)
    parser.add_argument('--output', type=Path, default=installed_map_directory(),
                        help='Output directory (defaults to the installed client map directory)')
    parser.add_argument('--lod', type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args()
    roots = [args.base] if args.base else sorted((args.cemu_data / 'mlc01/usr/title/00050000').glob('101c*/content'))
    if args.update:
        roots.append(args.update)
    elif not args.base:
        roots.extend(sorted((args.cemu_data / 'mlc01/usr/title/0005000e').glob('101c*/content')))
    roots = [root for root in roots if root and root.is_dir()]
    if not roots:
        parser.error('No installed BotW content found; pass --base and --update content directories.')
    locations = [entry for path in ('data/chests.json', 'static/completions.json')
                 for entry in json.loads((ROOT / 'worlds/botw' / path).read_text())['locations']]
    build(roots, args.output, locations, args.lod)


if __name__ == '__main__':
    main()
