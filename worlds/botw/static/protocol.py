"""Shared wire contract; the C# client embeds this same JSON resource."""
from importlib.resources import files
import hashlib
import json

PROTOCOL = json.loads(files(__package__).joinpath("protocol.json").read_text())
MAILBOX_VERSION = PROTOCOL["version"]


def seed_fingerprint(seed: str, player: int, location_ids) -> str:
    identity = {"seed": str(seed), "player": player, "locations": sorted(location_ids)}
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:32]
