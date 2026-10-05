"""Apply a plan to map instances and package a Cemu content overlay."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
import json
import tempfile
import zipfile

from .actors import build_check_actors
from .chests import patch_chest_byml
from .plan import validate_plan
from .resources import binary_modules, decode_byml, decompress, encode_byml, replace_members
from .ui import build_check_messages
from .hook import build_seed_hook
from .starting import build_starting_resources
from .resource_sizes import update_resource_sizes

RSTB_PATH = "content/System/Resource/ResourceSizeTable.product.srsizetable"


def apply_plan(plan: dict, dump, output: str) -> dict:
    validate_plan(plan)
    output_path = Path(output).resolve()
    for root in (dump.base, dump.update, dump.dlc):
        if root and output_path.is_relative_to(root):
            raise ValueError("Output must be outside the original game dump")
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite {output_path}")
    _, rstb = binary_modules()
    maps = {}
    for entry in plan["locations"]:
        maps.setdefault(entry["resource"], []).append(entry)
        for variant in entry.get("resource_variants", []):
            maps.setdefault(variant["resource"], []).append({
                **entry,
                "map_sha256": variant["map_sha256"],
            })
    replacements = {}
    for resource, entries in sorted(maps.items()):
        original = dump.read(resource)
        checksum = hashlib.sha256(original).hexdigest()
        if any(entry["map_sha256"] != checksum for entry in entries):
            raise ValueError(f"Game version/catalog mismatch: {resource}")
        data = decode_byml(original)
        patch_chest_byml(data, {entry["hash_id"]: entry["id"] for entry in entries})
        patched = encode_byml(data, original)
        outer, _, member = resource.partition("!")
        replacements.setdefault(outer, {})[member] = patched
    files = {}
    for outer, members in sorted(replacements.items()):
        files[outer] = replace_members(dump.read(outer), members)
    actor_files, _ = build_check_actors(dump, [entry["id"] for entry in plan["locations"]])
    files.update(actor_files)
    message_files, _ = build_check_messages(dump, [entry["id"] for entry in plan["locations"]])
    files.update(message_files)
    if plan.get("starting_state") is not None:
        starting_files, _ = build_starting_resources(dump, plan["starting_state"])
        if files.keys() & starting_files.keys():
            raise ValueError("Starting-state resources collide with another patch branch")
        files.update(starting_files)
    table_raw = dump.read(RSTB_PATH)
    table = rstb.ResourceSizeTable(decompress(table_raw), be=True)
    update_resource_sizes(table, dump, files)
    stream = io.BytesIO()
    table.write(stream, be=True)
    files[RSTB_PATH] = bytes(binary_modules()[0].yaz0.compress(stream.getvalue()))
    files["rules.txt"] = (
        '[Definition]\n'
        'titleIds = 00050000101C9300,00050000101C9400,00050000101C9500\n'
        f'name = Archipelago - Player {plan["player"]} Static Checks\n'
        'path = "The Legend of Zelda: Breath of the Wild/Mods/Archipelago Static Checks"\n'
        'description = Seed-bound chest markers and AP v2 acquisition/delivery hook. Enable only this AP pack.\n'
        'version = 7\n'
    ).encode()
    files["botw_patch.json"] = json.dumps(plan, indent=2, sort_keys=True).encode()
    files["patch_Archipelago.asm"] = build_seed_hook(plan)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Publish only a complete zip, so a failed build cannot leave a usable-looking pack.
    with tempfile.NamedTemporaryFile(dir=output_path.parent, suffix=".tmp", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(temporary_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                entry = zipfile.ZipInfo(f"BotW_AP_P{plan['player']}/{name}", (1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, data)
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return {"chests": len(plan["locations"]), "maps": len(maps), "files": len(files), "output": str(output_path)}
