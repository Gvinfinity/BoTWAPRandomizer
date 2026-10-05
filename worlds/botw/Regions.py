from BaseClasses import Region

from .Locations import BotWLocation
from .reference import manual_regions


def create_regions(world):
    regions = {name: Region(name, world.player, world.multiworld) for name in ("Menu", *manual_regions)}
    world.multiworld.regions.extend(regions.values())
    # The reference uses tower unlocks as access gates from a common hub.
    # Destination requirements are attached to these entrances in Rules.py.
    for name in manual_regions:
        regions["Menu"].connect(regions[name], f"Menu -> {name}")
    for entry in world.active_chests:
        region = regions[entry["region"]]
        region.locations.append(BotWLocation(world.player, entry["name"], entry["id"], region))
    victory = BotWLocation(world.player, "Dark Beast Ganon Defeated", None, regions["Hyrule Castle"])
    victory.place_locked_item(world.create_event("Victory"))
    regions["Hyrule Castle"].locations.append(victory)
