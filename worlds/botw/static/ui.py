"""Add visible Archipelago item names to each installed language message pack."""
from __future__ import annotations

import re

from .checks import check_actor_name
from .messages import add_messages
from .resources import binary_modules, decompress, replace_members


def reward_messages(location_ids, placements=None, local_player=None, player_name=None):
    def text(value):
        # MSBT reserves control characters for binary commands. Player and item
        # names are plain text, including names from other games.
        return ' '.join(''.join(c for c in str(value) if ord(c) >= 32).split())
    additions = {}
    for code in sorted(location_ids):
        actor = check_actor_name(code)
        placed = (placements or {}).get(code)
        if placed and placed.get('name'):
            name = text(placed['name'])
            owner = placed.get('player')
            recipient = text(placed.get('player_name') or (
                player_name if owner == local_player and player_name else f'Player {owner}'))
            additions[f'{actor}_Name'] = name if owner == local_player else f'{name} ({recipient})'
            additions[f'{actor}_Desc'] = f'{name}\nSent to {recipient} through Archipelago.'
        else:
            # Legacy fixture plans have no placements. Production AP patches do.
            additions[f'{actor}_Name'] = f'Archipelago Item [{code:08X}]'
            additions[f'{actor}_Desc'] = 'A multiworld location check.\nIts reward is delivered by Archipelago.'
    return additions


def build_check_messages(dump, location_ids, placements=None, local_player=None, player_name=None):
    oead, _ = binary_modules()
    files, sizes = {}, {}
    languages = {path.name for root in (dump.base, dump.update)
                 for path in (root / "Pack").glob("Bootup_*.pack")
                 if re.fullmatch(r"Bootup_[A-Z]{2}[a-z]{2}\.pack", path.name)}
    if not languages:
        raise ValueError("No language message packs found")
    additions = reward_messages(location_ids, placements, local_player, player_name)
    for filename in sorted(languages):
        outer = f"content/Pack/{filename}"
        original = dump.read(outer)
        archive = oead.Sarc(decompress(original))
        messages = next(entry for entry in archive.get_files() if entry.name.endswith(".ssarc"))
        message_archive = oead.Sarc(decompress(bytes(messages.data)))
        item = message_archive.get_file("ActorType/Item.msbt")
        if item is None:
            raise ValueError(f"No Item messages in {filename}")
        modified = add_messages(bytes(item.data), additions)
        modified_messages = replace_members(bytes(messages.data), {"ActorType/Item.msbt": modified})
        files[outer] = replace_members(original, {messages.name: modified_messages})
        sizes[messages.name.replace(".ssarc", ".sarc")] = len(decompress(modified_messages))
        sizes["ActorType/Item.msbt"] = max(sizes.get("ActorType/Item.msbt", 0), len(modified))
        sizes[outer.removeprefix("content/")] = len(decompress(files[outer]))
    return files, sizes
