"""Per-instance loot patching. BotW .bdrop files are shared AAMP tables."""
from __future__ import annotations

from .checks import check_actor_name


def iter_chests(data):
    if not hasattr(data, "get"):
        return
    for actor in data.get("Objs", []):
        if str(actor.get("UnitConfigName", "")).startswith("TBox_"):
            yield actor


def patch_chest_byml(data, location_map: dict[int, int]) -> bool:
    """Patch explicitly mapped HashIds in ONE map. Empty mappings patch nothing."""
    modified, seen = False, set()
    for actor in iter_chests(data):
        hash_id = int(actor["HashId"])
        if hash_id not in location_map:
            continue
        if hash_id in seen:
            raise ValueError(f"Duplicate chest HashId in map: {hash_id:08X}")
        seen.add(hash_id)
        if "!Parameters" not in actor:
            if isinstance(actor, dict):
                actor["!Parameters"] = {}
            else:
                from .resources import binary_modules
                actor["!Parameters"] = binary_modules()[0].byml.Hash()
        params = actor["!Parameters"]
        name = check_actor_name(location_map[hash_id])
        if params.get("DropActor") != name or "DropTable" in params:
            params["DropActor"] = name
            if "DropTable" in params:
                del params["DropTable"]
            if "DropActorNum" in params:
                params["DropActorNum"] = type(params["DropActorNum"])(1)
            # Custom AP_LocationID parameters are not understood by the game.
            if "AP_LocationID" in params:
                del params["AP_LocationID"]
            modified = True
    missing = set(location_map) - seen
    if missing:
        raise ValueError(f"Mapped chests absent from map: {sorted(missing)}")
    return modified
