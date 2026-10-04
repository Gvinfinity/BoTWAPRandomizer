from worlds.AutoWorld import World, WebWorld
from .Items import botw_items, BotWItem
from .Locations import botw_locations, BotWLocation
from .Regions import create_regions
from .Rules import set_rules
from .Options import botw_options

class BotWWebWorld(WebWorld):
    setup_en = "setup_en.md"

class BotWWorld(World):
    """
    The Legend of Zelda: Breath of the Wild Archipelago Multiworld integration.
    """
    game = "Breath of the Wild"
    options_dataclass = botw_options
    options_dict = botw_options
    web = BotWWebWorld()

    def generate_early(self):
        pass

    def create_items(self):
        # Create items from botw_items
        pass

    def create_regions(self):
        create_regions(self.multiworld, self.player)

    def set_rules(self):
        set_rules(self.multiworld, self.player)

    def generate_output(self, output_directory: str):
        # Package Cemu Graphic Pack
        pass
