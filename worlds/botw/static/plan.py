"""Copyright-free seed patch plan. The player applies it to their own dump."""
from __future__ import annotations

import json
import zipfile

from .checks import PROTOCOL_VERSION, check_actor_name, chest_key, validate_resource_path
from .protocol import MAILBOX_VERSION, PROTOCOL, seed_fingerprint
from .starting import validate_starting_state


def validate_plan(plan: dict) -> dict:
    if plan.get("version") != PROTOCOL_VERSION or plan.get("game") != "Breath of the Wild":
        raise ValueError("Unsupported BotW patch plan")
    if type(plan.get("player")) is not int or plan["player"] < 1:
        raise ValueError("Invalid player slot")
    if not isinstance(plan.get("seed"), str) or not plan["seed"]:
        raise ValueError("Invalid seed name")
    ids, keys = set(), set()
    if not plan.get("locations"):
        raise ValueError("A patch plan must contain at least one chest")
    for entry in plan["locations"]:
        name = check_actor_name(entry["id"])
        key = chest_key(entry["resource"], entry["hash_id"])
        if entry["id"] in ids or key in keys:
            raise ValueError(f"Duplicate check: {key}")
        ids.add(entry["id"])
        keys.add(key)
        if entry.get("check_actor", name) != name:
            raise ValueError("Check actor does not encode the location ID")
        checksum = entry.get("map_sha256", "")
        if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
            raise ValueError("Every mapped chest needs a source map SHA-256")
        if not entry["resource"].endswith(".smubin"):
            raise ValueError("Checks must reference map BYML")
        validate_resource_path(entry["resource"])
        for variant in entry.get("resource_variants", []):
            validate_resource_path(variant["resource"])
            if not variant["resource"].endswith(".smubin"):
                raise ValueError("Check variants must reference map BYML")
            variant_checksum = variant.get("map_sha256", "")
            if len(variant_checksum) != 64 or any(c not in "0123456789abcdef" for c in variant_checksum):
                raise ValueError("Every check variant needs a source map SHA-256")
    slot = plan.get("slot_data", {})
    start = plan.get("starting_state")
    if start is not None:
        validate_starting_state(start)
        if slot.get("starting_state") != start:
            raise ValueError("Patch and slot starting state disagree")
    elif "starting_state" in slot:
        raise ValueError("Patch is missing the slot's starting state")
    expected = {str(value): check_actor_name(value) for value in ids}
    if len(ids) > PROTOCOL["max_locations"]:
        raise ValueError("Too many checks for the native mailbox location table")
    if (slot.get("protocol_version") != MAILBOX_VERSION or slot.get("locations") != expected
            or slot.get("player") != plan["player"] or slot.get("seed") != plan.get("seed")
            or slot.get("check_actor_prefix") != "AP_Check_"
            or slot.get("seed_fingerprint") != seed_fingerprint(plan.get("seed"), plan["player"], ids, start)):
        raise ValueError("Patch and slot data disagree; regenerate this seed with the current APWorld")
    return plan


def read_plan(path: str) -> dict:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            plan = json.loads(archive.read("botw_patch.json"))
            if "archipelago.json" in archive.namelist():
                manifest = json.loads(archive.read("archipelago.json"))
                if manifest.get("game") != plan.get("game") or manifest.get("player") != plan.get("player"):
                    raise ValueError("Archipelago manifest disagrees with patch plan")
    else:
        with open(path, encoding="utf-8") as stream:
            plan = json.load(stream)
    return validate_plan(plan)
