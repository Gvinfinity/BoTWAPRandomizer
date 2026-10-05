"""Fresh-save starting state, applied to Bootup GameData before launch.

Tower/movie defaults follow external/BotwRandomizer's UpdateGameData. Plateau
containment and the paraglider possession flags stay unset so the Paraglider
remains an AP item even when the tutorial and map are skipped.
"""
from .resources import binary_modules, decode_byml, decompress, encode_byml, replace_members

BOOTUP = "content/Pack/Bootup.pack"
GAMEDATA_MEMBER = "GameData/gamedata.ssarc"
BASE_INVENTORY = {"Heart Container": 3, "Weapon Slot": 8, "Bow Slot": 5, "Shield Slot": 4}
BASE_FLAGS = {"MaxHartValue": 12, "WeaponPorchStockNum": 8, "BowPorchStockNum": 5, "ShieldPorchStockNum": 4}
PLATEAU_FLAGS = (
    "MapTower_07", "MapTower_07_Demo", "MapTower_DemoFirst", "Open_StartPoint",
    "IsPlayed_Demo103_0", "IsPlayed_Demo104_0", "IsPlayed_Demo109_1",
    "IsPlayed_Demo164_0", "IsPlayed_Demo166_0",
    "FirstTower_Activated", "FirstTower_Finish", "FindDungeon_Activated",
    "FindDungeon_1stClear", "FindDungeon_AllClear", "FindDungeon_Finish",
    "IsGet_Obj_DRStone_Get",
)


def starting_state(skip_plateau: bool) -> dict:
    inventory = dict(BASE_INVENTORY)
    if skip_plateau:
        inventory.update({"Great Plateau Tower": 1})
    return {
        "version": 1, "skip_great_plateau": bool(skip_plateau),
        "bool_flags": {name: True for name in PLATEAU_FLAGS} if skip_plateau else {},
        "s32_flags": dict(BASE_FLAGS, **({"Location_MapTower07": 1} if skip_plateau else {})),
        "pouch_items": {"Obj_DRStone_Get": 1} if skip_plateau else {},
        "logical_inventory": inventory,
    }


def validate_starting_state(state: dict) -> dict:
    if (not isinstance(state, dict) or type(state.get("skip_great_plateau")) is not bool
            or state != starting_state(state["skip_great_plateau"])):
        raise ValueError("Unsupported fresh-save starting state; regenerate this seed")
    return state


def patch_starting_gamedata(documents: dict, state: dict) -> set[str]:
    """Patch decoded .bgdata documents; require each named flag exactly once."""
    validate_starting_state(state)
    oead, _ = binary_modules()
    wanted = {**{name: ("bool_data", int(value)) for name, value in state["bool_flags"].items()},
              **{name: ("s32_data", value) for name, value in state["s32_flags"].items()}}
    if state["pouch_items"]:
        wanted.update({"PorchItem": ("string64_array_data", None),
                       "PorchItem_Value1": ("s32_array_data", None),
                       "PorchItem_EquipFlag": ("bool_array_data", None)})
    matches, changed = {}, set()
    for member, document in documents.items():
        for kind, rows in document.items():
            for row in rows:
                name = row.get("DataName")
                if name not in wanted:
                    continue
                expected_kind, value = wanted[name]
                if kind != expected_kind or name in matches:
                    raise ValueError(f"Invalid or duplicate starting flag: {name}")
                matches[name] = row
                if value is not None:
                    row["InitValue"] = oead.S32(value)
                    changed.add(member)
    missing = set(wanted) - set(matches)
    if missing:
        raise ValueError(f"Missing starting-state GameData flags: {sorted(missing)}")
    if state["pouch_items"]:
        arrays = {}
        for name in ("PorchItem", "PorchItem_Value1", "PorchItem_EquipFlag"):
            initial = matches[name]["InitValue"]
            if len(initial) != 1 or "Values" not in initial[0]:
                raise ValueError(f"Unexpected pouch initialization shape: {name}")
            arrays[name] = initial[0]["Values"]
        names, values, equipped = (arrays[name] for name in ("PorchItem", "PorchItem_Value1", "PorchItem_EquipFlag"))
        if len(names) != 420 or len(values) != 420 or len(equipped) != 420:
            raise ValueError("Unexpected v208 pouch array capacity")
        for actor, quantity in state["pouch_items"].items():
            existing = [index for index, name in enumerate(names) if str(name) == actor]
            if len(existing) > 1:
                raise ValueError(f"Duplicate starting pouch actor: {actor}")
            index = existing[0] if existing else next((index for index, name in enumerate(names)
                    if str(name) == "" and int(values[index]) == 0 and int(equipped[index]) == 0), None)
            if index is None:
                raise ValueError("No free slot in the initial pouch")
            names[index] = actor
            values[index] = oead.S32(quantity)
            equipped[index] = oead.S32(0)
        for member, document in documents.items():
            if any(row.get("DataName") in arrays for rows in document.values() for row in rows):
                changed.add(member)
    return changed


def build_starting_resources(dump, state: dict) -> tuple[dict[str, bytes], dict[str, int]]:
    validate_starting_state(state)
    oead, _ = binary_modules()
    bootup = dump.read(BOOTUP)
    gamedata = dump.read(f"{BOOTUP}!{GAMEDATA_MEMBER}")
    archive = oead.Sarc(decompress(gamedata))
    documents, originals = {}, {}
    for entry in archive.get_files():
        if entry.name and entry.name.endswith(".bgdata"):
            originals[entry.name] = bytes(entry.data)
            documents[entry.name] = decode_byml(originals[entry.name])
    changed = patch_starting_gamedata(documents, state)
    replacements = {member: encode_byml(documents[member], originals[member]) for member in sorted(changed)}
    patched = replace_members(gamedata, replacements)
    output = replace_members(bootup, {GAMEDATA_MEMBER: patched})
    # The existing RSTB uses the decompressed .sarc name. Sizes of each changed
    # .bgdata member also feed the same conservative allocation policy.
    sizes = {GAMEDATA_MEMBER.replace(".ssarc", ".sarc"): len(decompress(patched)),
             "Pack/Bootup.pack": len(decompress(output))}
    sizes.update({member.lstrip("/"): len(decompress(data)) for member, data in replacements.items()})
    return {BOOTUP: output}, sizes
