"""Build a player patcher ZIP for bundle-world from a release build environment."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rid", choices=("linux-x64", "win-x64"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--windows-python", type=Path, help="Official CPython 3.12 x64 embeddable ZIP")
    args = parser.parse_args()
    if args.rid == "win-x64" and not args.windows_python:
        parser.error("--windows-python is required for win-x64")
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}")

    with tempfile.TemporaryDirectory(prefix="botw-player-build-") as directory:
        staging = Path(directory)
        runtime = staging / "runtime"
        source = staging / "source"
        source.mkdir()
        runtime.mkdir()
        shutil.copyfile(ROOT / "src/patcher/player.py", source / "player.py")
        shutil.copytree(ROOT / "worlds/botw/static", source / "static", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(ROOT / "worlds/botw/data/chests.json", source / "static/tracker_chests.json")
        shutil.copyfile(ROOT / "src/hook/patch_Archipelago.asm", source / "static/hook_template.asm")
        if args.rid == "win-x64":
            with zipfile.ZipFile(args.windows_python) as archive:
                archive.extractall(runtime)
            (runtime / "python312._pth").write_text("python312.zip\n.\npackages\n", encoding="utf-8")
            shutil.copytree(source, runtime, dirs_exist_ok=True)
            subprocess.run([
                sys.executable, "-m", "pip", "install", "--target", str(runtime / "packages"),
                "--only-binary=:all:", "--platform", "win_amd64", "--python-version", "3.12",
                "--implementation", "cp", "--abi", "cp312",
                "-r", str(ROOT / "src/patcher/requirements-tracker.txt"),
            ], check=True)
        else:
            subprocess.run([
                sys.executable, "-m", "PyInstaller", "--onefile", "--name", "BotWPatcher",
                "--distpath", str(runtime), "--workpath", str(staging / "build"),
                "--specpath", str(staging), "--add-data", f"{source / 'static'}:static",
                "--collect-data", "rstb", str(source / "player.py"),
            ], check=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.output, "x", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(runtime.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    archive.write(path, path.relative_to(runtime))


if __name__ == "__main__":
    main()
