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
from botw_static.version import WORLD_VERSION


def runtime_payload(value: str) -> tuple[str, Path]:
    rid, separator, filename = value.partition("=")
    platforms = {"win-x64", "win-arm64", "linux-x64", "linux-arm64"}
    if not separator or rid not in platforms or not filename:
        raise argparse.ArgumentTypeError("Expected RID=PATH for a Windows or Linux x64/ARM64 payload")
    path = Path(filename)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"Payload not found: {path}")
    return rid, path


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
    bundle = commands.add_parser("bundle-world", help="Package the versioned BotW APWorld")
    bundle.add_argument("--output", type=Path,
                        help="Output archive (defaults to out/botw-VERSION[-RID].apworld)")
    bundle.add_argument("--client", action="append", type=runtime_payload, default=[],
                        metavar="RID=PATH", help="Embed a published single-file client (repeat for each platform)")
    bundle.add_argument("--patcher", action="append", type=runtime_payload, default=[],
                        metavar="RID=ZIP", help="Embed a self-contained patcher ZIP (repeat for each platform)")
    args = parser.parse_args()
    if args.command == "bundle-world":
        if len(dict(args.client)) != len(args.client):
            parser.error("Supply at most one client executable per RID")
        if len(dict(args.patcher)) != len(args.patcher):
            parser.error("Supply at most one patcher ZIP per RID")
        for rid, path in args.patcher:
            with zipfile.ZipFile(path) as payload:
                expected = {"python.exe", "player.py"} if rid.startswith("win-") else {"BotWPatcher"}
                if not expected.issubset(payload.namelist()):
                    parser.error(f"Patcher ZIP for {rid} must contain {', '.join(sorted(expected))}")
        platforms = {rid for rid, _ in args.client + args.patcher}
        suffix = f"-{next(iter(platforms))}" if len(platforms) == 1 else ""
        output = args.output or Path(f"out/botw-{WORLD_VERSION}{suffix}.apworld")
        if output.exists():
            raise FileExistsError(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("archipelago.json", json.dumps({
                "game": "Breath of the Wild", "version": 7, "compatible_version": 7,
                "world_version": WORLD_VERSION, "minimum_ap_version": "0.6.0"
            }))
            archive.write(ROOT / "src/hook/patch_Archipelago.asm", "botw/static/hook_template.asm")
            for path in sorted((ROOT / "worlds/botw").rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts and "test" not in path.parts:
                    archive.write(path, f"botw/{path.relative_to(ROOT / 'worlds/botw').as_posix()}")
            for rid, path in args.client:
                name = "BotWClient.exe" if rid.startswith("win-") else "BotWClient"
                archive.write(path, f"botw/client_payloads/{rid}/{name}")
            for rid, path in args.patcher:
                archive.write(path, f"botw/patcher_payloads/{rid}.zip", compress_type=zipfile.ZIP_STORED)
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
