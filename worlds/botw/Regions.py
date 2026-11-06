from BaseClasses import Region

from .Locations import BotWLocation
from .reference import manual_regions
from .access import BOARDING, story_events


def create_regions(world):
    regions = {name: Region(name, world.player, world.multiworld)
               for name in ("Menu", *manual_regions, 'Gerudo Town', *(f'{beast} Boarding' for beast in BOARDING))}
    world.multiworld.regions.extend(regions.values())
    # Open-world destinations share a hub; physical access is set in Rules.py.
    for name in manual_regions:
        if name.startswith('Divine Beast Vah '):
            continue
        regions["Menu"].connect(regions[name], f"Menu -> {name}")
    regions['Gerudo Desert'].connect(regions['Gerudo Town'], 'Gerudo Desert -> Gerudo Town')
    for beast, (parent, _) in BOARDING.items():
        regions[parent].connect(regions[f'{beast} Boarding'], f'{parent} -> {beast} Boarding')
        regions[f'{beast} Boarding'].connect(regions[f'Divine Beast {beast}'], f'{beast} Boarding -> Divine Beast {beast}')
    for entry in world.active_locations:
        region = regions[entry["region"]]
        region.locations.append(BotWLocation(world.player, entry["name"], entry["id"], region))
    world.story_events = story_events(world)
    for entry in world.story_events:
        region = regions[entry['region']]
        event = BotWLocation(world.player, entry['name'], None, region)
        event.place_locked_item(world.create_event(entry['name']))
        region.locations.append(event)
    victory = BotWLocation(world.player, "Dark Beast Ganon Defeated", None, regions["Hyrule Castle"])
    victory.place_locked_item(world.create_event("Victory"))
    regions["Hyrule Castle"].locations.append(victory)
