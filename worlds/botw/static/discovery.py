"""Discover physical chest identities; names and logic are bound separately."""
from __future__ import annotations

import hashlib

from .checks import PROTOCOL_VERSION, chest_key, discovered_location_id
from .chests import iter_chests
from .resources import GameDump, decode_byml, map_resources


def discover_chests(dump: GameDump) -> dict:
    # DLC overlays base MainField maps. Packed maps take priority over loose
    # copies; patch the archive itself rather than corrupting AocMainField.pack.
    maps = {}
    for outer in dump.outer_resources():
        for resource, raw in map_resources(outer, dump.read(outer)):
            logical = resource.split("!")[-1]
            if logical.startswith("content/"):
                logical = logical.removeprefix("content/")
            elif logical.startswith("aoc/0010/"):
                logical = logical.removeprefix("aoc/0010/")
            priority = (resource.startswith("aoc/"), "!" in resource)
            if logical not in maps or priority > maps[logical][0]:
                maps[logical] = priority, resource, raw
    locations, ignored, ids = [], [], {}
    for logical, (_, resource, raw) in sorted(maps.items()):
        for actor in iter_chests(decode_byml(raw)):
            params = actor.get("!Parameters", {})
            original = str(params.get("DropActor", ""))
            hash_id = int(actor["HashId"])
            reason = None
            if "Gamble" in actor["UnitConfigName"]:
                reason = "Treasure Chest Shop minigame"
            elif original == "KeySmall":
                reason = "Dungeon-local small key; requires separate key logic/delivery"
            elif params.get("IsHardModeActor", False):
                reason = "Master Mode chest"
            elif not original:
                reason = "No direct DropActor (shared/scripted loot requires explicit binding)"
            entry = {
                "id": discovered_location_id(logical, hash_id),
                "name": f"{logical} - Chest {hash_id:08X}",
                "resource": resource,
                "logical_map": logical,
                "hash_id": hash_id,
                "map_sha256": hashlib.sha256(raw).hexdigest(),
                "original_actor": original,
                "position": [float(value) for value in actor.get("Translate", [])],
                "region": None,
                "requires": "",
            }
            if reason:
                entry["reason"] = reason
                ignored.append(entry)
                continue
            key = chest_key(logical, hash_id)
            if entry["id"] in ids:
                raise ValueError(f"Duplicate identity or ID collision: {key} / {ids[entry['id']]}")
            ids[entry["id"]] = key
            locations.append(entry)
    return {"version": PROTOCOL_VERSION, "locations": locations, "ignored": ignored}
