from BaseClasses import Location

from .reference import load_chests


class BotWLocation(Location):
    game = "Breath of the Wild"


chest_data = load_chests()
botw_locations = {entry["name"]: entry["id"] for entry in chest_data}
