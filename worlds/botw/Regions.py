from BaseClasses import Region, Entrance
from .Locations import BotWLocation, botw_locations

def create_regions(multiworld, player):
    menu = Region("Menu", player, multiworld)
    plateau = Region("Great Plateau", player, multiworld)
    
    multiworld.regions += [menu, plateau]
    menu.connect(plateau)
