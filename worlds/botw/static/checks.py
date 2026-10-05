"""Versioned identity contract for APWorld, static patcher and acquisition hook."""
from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath

PROTOCOL_VERSION = 1
ACTOR_PREFIX = "AP_Check_"
_ACTOR = re.compile(r"AP_Check_([0-9A-F]{8})\Z")


def check_actor_name(location_id: int) -> str:
    if type(location_id) is not int or not 0 < location_id <= 0xFFFFFFFF:
        raise ValueError("Check IDs must be nonzero unsigned 32-bit integers")
    return f"{ACTOR_PREFIX}{location_id:08X}"


def location_id_from_actor(name: str) -> int | None:
    match = _ACTOR.fullmatch(name)
    return int(match[1], 16) if match and int(match[1], 16) else None


def validate_resource_path(path: str) -> str:
    """Paths may include nested SARC members, separated by '!'."""
    if not isinstance(path, str) or not path:
        raise ValueError("A resource path is required")
    for part in path.split("!"):
        parsed = PurePosixPath(part)
        if (not part or parsed.is_absolute() or ".." in parsed.parts
                or "\\" in part or ":" in part or str(parsed) != part):
            raise ValueError(f"Unsafe/noncanonical resource path: {path!r}")
    return path


def chest_key(resource: str, hash_id: int) -> str:
    validate_resource_path(resource)
    if type(hash_id) is not int or not 0 <= hash_id <= 0xFFFFFFFF:
        raise ValueError("Chest HashId must be an unsigned 32-bit integer")
    return f"{resource}#{hash_id:08X}"


def discovered_location_id(resource: str, hash_id: int) -> int:
    """Seed-independent IDs. Discovery rejects collisions instead of renumbering."""
    digest = hashlib.sha256(chest_key(resource, hash_id).encode()).digest()
    return 0xB0000000 | (int.from_bytes(digest[:4], "big") & 0x0FFFFFFF)
