from BaseClasses import Location

from .reference import load_chests, load_completions


class BotWLocation(Location):
    game = "Breath of the Wild"


chest_data = load_chests()
completion_data = load_completions()
from .static.combat import catalog as combat_catalog
combat_data = combat_catalog()["locations"]
botw_locations = {entry["name"]: entry["id"] for entry in [*chest_data, *completion_data, *combat_data]}
if len(botw_locations) != len(chest_data) + len(completion_data) + len(combat_data):
    raise ValueError("Chest and completion location names overlap")
if len(set(botw_locations.values())) != len(botw_locations):
    raise ValueError("Chest and completion location IDs overlap")
