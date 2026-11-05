"""Community data, explicit native delivery metadata, and chest catalog."""
from __future__ import annotations

from importlib.resources import files
import json

from .static.checks import PROTOCOL_VERSION, chest_key, check_actor_name


def _read(name):
    return json.loads(files(__package__).joinpath(f"data/{name}.json").read_text())


manual_items = _read("manual/items")["data"]
manual_regions = {key: value for key, value in _read("manual/regions").items() if not key.startswith("$")}
manual_locations = _read("manual/locations")["data"]
categories = _read("manual/categories")
game_data = _read("manual/game")

# Actor, wallet, stat and native-profile grants have distinct delivery semantics.
native_items = {
    "Master Sword": ("Weapon_Sword_070", 1),
    "Hylian Shield": ("Weapon_Shield_030", 1),
    "Bow of Light": ("Weapon_Bow_071", 1),
    "Paraglider": ("PlayerStole2", 1),
    "Arrows (10)": ("NormalArrow", 10),
    "Arrows (20)": ("NormalArrow", 20),
    "Arrows (50)": ("NormalArrow", 50),
    "Fire Arrows (15)": ("FireArrow", 15),
    "Ice Arrows (15)": ("IceArrow", 15),
    "Shock Arrows (15)": ("ElectricArrow", 15),
    "Bomb Arrows (15)": ("BombArrow_A", 15),
    "Ancient Arrows (5)": ("AncientArrow", 5),
    "Royal Broadsword": ("Weapon_Sword_024", 1),
    "Royal Shield": ("Weapon_Shield_022", 1),
    "Royal Bow": ("Weapon_Bow_036", 1),
    "Savage Lynel Shield": ("Weapon_Shield_018", 1),
    "Savage Lynel Bow": ("Weapon_Bow_032", 1),
    "Diamond": ("Item_Ore_A", 1),
    "Wood Bundles (10)": ("Obj_FireWoodBundle", 10),
    "Farosh's Scale": ("Item_Enemy_53", 1),
    "Dinraal's Scale": ("Item_Enemy_38", 1),
    "Naydra's Scale": ("Item_Enemy_49", 1),
}

# Base armor IDs verified against EU English messages and ActorInfo rank metadata.
native_items.update(_read("native_armor"))

rupee_items = {"50 Rupees": 50, "100 Rupees": 100, "200 Rupees": 200, "Greg the Green Rupee": 1}

native_grants = _read("native_grants")

progression_items = {
    "Heart Container": "heart_container", "Stamina Vessel": "stamina_vessel",
    "Weapon Slot": "weapon_slot", "Bow Slot": "bow_slot", "Shield Slot": "shield_slot",
}

item_data = {}
for index, item in enumerate(manual_items):
    entry = dict(item, id=0xB0100000 + index, count=int(item.get("count", 1)))
    if item["name"] in native_items:
        actor, quantity = native_items[item["name"]]
        entry.update(delivery={"kind": "actor", "actor": actor, "quantity": quantity})
    elif item["name"] in rupee_items:
        entry.update(delivery={"kind": "rupees", "name": item["name"], "quantity": rupee_items[item["name"]]})
    elif item["name"] in progression_items:
        entry.update(delivery={"kind": "progression", "name": item["name"],
                               "command": progression_items[item["name"]], "quantity": 1})
    elif item["name"] in native_grants:
        entry.update(delivery={"kind": "native", "name": item["name"], "quantity": 1})
    else:
        entry.update(delivery={"kind": "unimplemented", "name": item["name"]})
    item_data[item["name"]] = entry
item_data["Paraglider"] = {"name": "Paraglider", "id": 0xB010FFFE, "count": 1, "progression": True,
                          "category": ["Key Items"], "delivery": {"kind": "actor", "actor": "PlayerStole2", "quantity": 1}}
item_data["Arrows (10)"] = {"name": "Arrows (10)", "id": 0xB010FFFF, "count": 0,
                           "delivery": {"kind": "actor", "actor": "NormalArrow", "quantity": 10}}
item_groups = {}
for item in item_data.values():
    for category in item.get("category", []):
        item_groups.setdefault(category, set()).add(item["name"])


def load_chests():
    data = _read("chests")
    if data.get("version") != PROTOCOL_VERSION:
        raise ValueError("Unsupported chest catalog version")
    names, codes, keys = set(), set(), set()
    bound = []
    for entry in data["locations"]:
        if not entry.get("region"):
            continue
        check_actor_name(entry["id"])
        key = chest_key(entry["resource"], entry["hash_id"])
        if entry["name"] in names or entry["id"] in codes or key in keys:
            raise ValueError(f"Duplicate chest binding: {entry['name']}")
        if entry["region"] not in manual_regions:
            raise ValueError(f"Unknown chest region: {entry['region']}")
        names.add(entry["name"])
        codes.add(entry["id"])
        keys.add(key)
        bound.append(entry)
    return bound


def load_completions():
    from .static.completions import catalog
    data = catalog()
    if data.get('version') != PROTOCOL_VERSION:
        raise ValueError('Unsupported completion catalog version')
    ids, names = set(), set()
    for entry in data['locations']:
        check_actor_name(entry['id'])
        if entry['kind'] not in {'shrine', 'tower'} or entry['region'] not in manual_regions:
            raise ValueError(f'Invalid completion binding: {entry["name"]}')
        if entry['id'] in ids or entry['name'] in names:
            raise ValueError('Duplicate completion binding')
        ids.add(entry['id']); names.add(entry['name'])
    return data['locations']
