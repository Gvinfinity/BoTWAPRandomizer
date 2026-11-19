"""Archipelago entry points for patching a local dump and starting the client."""
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import zipfile

from Launcher import launch
from Utils import env_cleared_lib_path, messagebox, open_directory, open_filename, user_path
from worlds.LauncherComponents import Component, SuffixIdentifier, Type

from .static.plan import read_plan
from .static.resources import GameDump


def install_patch(*args):
    try:
        patch = args[0] if args else open_filename("Select the BotW player patch", [("BotW patch", (".apbotw",))])
        if not patch:
            return
        plan = read_plan(patch)
        settings_path = Path(user_path("BotWAP", "folders.json"))
        folders = json.loads(settings_path.read_text()) if settings_path.exists() else {}
        for key, title in (
            ("base", "Select the base game's content folder"),
            ("update", "Select the v208 update's content folder"),
            ("dlc", "Select the DLC folder containing 0010, or cancel if playing without DLC"),
            ("packs", "Select Cemu's Graphic Packs folder"),
        ):
            selected = open_directory(title, folders.get(key) or "")
            if not selected and key != "dlc":
                return
            folders[key] = selected
        dump = GameDump(folders["base"], folders["update"], folders["dlc"])
        packs = Path(folders["packs"]).resolve()
        target = packs / f"BotW_AP_P{plan['player']}"
        if target.exists():
            raise FileExistsError(f"Move the existing pack out of Cemu's Graphic Packs folder first: {target}")
        if any(packs.is_relative_to(root) for root in (dump.base, dump.update, dump.dlc) if root):
            raise ValueError("Select Cemu's Graphic Packs folder outside the original game content.")

        with tempfile.TemporaryDirectory(prefix=".botw-setup-", dir=packs) as directory:
            staging = Path(directory)
            archive_path = staging / "pack.zip"
            patcher = bundled_patcher()
            if patcher:
                command, options = patcher
                arguments = [str(Path(patch).resolve()), "--base", str(dump.base),
                             "--update", str(dump.update), "--output", str(archive_path)]
                if dump.dlc:
                    arguments.extend(("--dlc", str(dump.dlc)))
                result = subprocess.run(command + arguments, capture_output=True, encoding="utf-8",
                                        errors="replace", **options)
                if result.returncode:
                    raise RuntimeError(result.stderr.strip() or f"BotW patcher exited with code {result.returncode}.")
            else:
                from .static.apply import apply_plan

                apply_plan(plan, dump, archive_path)
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(staging)
            (staging / target.name).rename(target)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(folders, indent=2), encoding="utf-8")
        messagebox("BotW pack installed", f"{target}\nRefresh Graphic Packs in Cemu and enable this pack.")
    except Exception as exc:
        messagebox("BotW setup failed", str(exc), error=True)


def client_platform():
    system = {"Windows": "win", "Linux": "linux"}.get(platform.system())
    architecture = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
        platform.machine().lower()
    )
    if system and architecture:
        return f"{system}-{architecture}", "BotWClient.exe" if system == "win" else "BotWClient"
    raise RuntimeError("BotWClient requires Windows or Linux on x64 or ARM64.")


def bundled_patcher():
    try:
        rid, _ = client_platform()
    except RuntimeError:
        return None
    payload = files(__package__).joinpath("patcher_payloads", f"{rid}.zip")
    if not payload.is_file():
        return None
    with payload.open("rb") as source:
        digest = hashlib.sha256()
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
        cache = Path(user_path("BotWAP", "patchers", rid, digest.hexdigest()))
        if not cache.is_dir():
            cache.parent.mkdir(parents=True, exist_ok=True)
            source.seek(0)
            with tempfile.TemporaryDirectory(dir=cache.parent) as directory:
                staging = Path(directory) / "runtime"
                with zipfile.ZipFile(source) as archive:
                    archive.extractall(staging)
                if not rid.startswith("win-"):
                    (staging / "BotWPatcher").chmod(0o755)
                try:
                    staging.rename(cache)
                except OSError:
                    if not cache.is_dir():
                        raise
    if rid.startswith("win-"):
        return [str(cache / "python.exe"), "-X", "utf8", str(cache / "player.py")], {
            "creationflags": subprocess.CREATE_NO_WINDOW,
        }
    environment = dict(env_cleared_lib_path())
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return [str(cache / "BotWPatcher")], {"env": environment}


def launch_client(*args):
    try:
        rid, name = client_platform()
        bundled = files(__package__).joinpath("client_payloads", rid, name)
        if bundled.is_file():
            with bundled.open("rb") as source:
                digest = hashlib.sha256()
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
                source.seek(0)
                cache = Path(user_path("BotWAP", "clients", rid, digest.hexdigest()))
                cache.mkdir(parents=True, exist_ok=True)
                executable = cache / name
                if not executable.is_file():
                    with tempfile.TemporaryDirectory(dir=cache) as directory:
                        staged = Path(directory) / name
                        with staged.open("wb") as destination:
                            shutil.copyfileobj(source, destination)
                        staged.chmod(0o755)
                        try:
                            staged.replace(executable)
                        except PermissionError:
                            if not executable.is_file():
                                raise
        else:
            raise RuntimeError(f"This APWorld has no bundled client for {rid}. Use a client-enabled build or run the standalone BotWClient.")
        command = [str(executable), *(args or ("--interactive",))]
        if rid.startswith("win-"):
            subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            launch(command, in_terminal=True)
    except Exception as exc:
        messagebox("BotW client launch failed", str(exc), error=True)


def register(components):
    components.extend((
        Component("Install BotW Seed Pack", func=install_patch, component_type=Type.CLIENT,
                  file_identifier=SuffixIdentifier(".apbotw")),
        Component("BotW Client", func=launch_client, component_type=Type.CLIENT),
    ))
