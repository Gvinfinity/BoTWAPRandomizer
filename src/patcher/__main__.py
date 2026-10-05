from __future__ import annotations

import argparse
import json
from pathlib import Path
import zipfile

from .core import ROOT
from botw_static.apply import apply_plan
from botw_static.bindings import bind_reference
from botw_static.discovery import discover_chests
from botw_static.plan import read_plan
from botw_static.resources import GameDump


def main() -> None:
    parser = argparse.ArgumentParser(description="BotW AP static chest patcher (Wii U v208)")
    commands = parser.add_subparsers(dest="command", required=True)
    discover = commands.add_parser("discover", help="Create the versioned chest/logic catalog")
    apply = commands.add_parser("apply", help="Apply an .apbotw seed to the player's extracted game")
    for command in (discover, apply):
        command.add_argument("--base", required=True, help="Base game content directory")
        command.add_argument("--update", required=True, help="v208 update content directory")
        command.add_argument("--dlc", help="DLC content directory containing 0010")
        command.add_argument("--output", required=True)
    discover.add_argument("--bind-reference", action="store_true")
    apply.add_argument("patch", help="Generated .apbotw or JSON patch plan")
    bundle = commands.add_parser("bundle-world", help="Package the world into botw.apworld")
    bundle.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "bundle-world":
        output = Path(args.output)
        if output.exists():
            raise FileExistsError(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("archipelago.json", json.dumps({
                "game": "Breath of the Wild", "version": 7, "compatible_version": 7,
                "world_version": "0.3.0", "minimum_ap_version": "0.6.0"
            }))
            archive.write(ROOT / "src/hook/patch_Archipelago.asm", "botw/static/hook_template.asm")
            for path in sorted((ROOT / "worlds/botw").rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts and "test" not in path.parts:
                    archive.write(path, f"botw/{path.relative_to(ROOT / 'worlds/botw').as_posix()}")
        print(output)
        return
    dump = GameDump(args.base, args.update, args.dlc)
    if args.command == "discover":
        output = Path(args.output)
        if output.exists():
            raise FileExistsError(output)
        data = discover_chests(dump)
        if args.bind_reference:
            data = bind_reference(data, dump, ROOT / "worlds/botw/data/manual", ROOT / "external/BotwRandomizer")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        print(f"Discovered {len(data['locations'])} chests; {sum(bool(entry['region']) for entry in data['locations'])} bound; {len(data['ignored'])} excluded")
    else:
        print(json.dumps(apply_plan(read_plan(args.patch), dump, args.output), indent=2))


if __name__ == "__main__":
    main()
