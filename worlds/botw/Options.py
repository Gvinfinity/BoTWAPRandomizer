from dataclasses import dataclass
from Options import Choice, Range, Toggle, PerGameCommonOptions

class ChestShuffle(Toggle):
    """Shuffle overworld chests."""
    display_name = "Chest Shuffle"
    default = 1

@dataclass
class BotWOptions(PerGameCommonOptions):
    chest_shuffle: ChestShuffle

botw_options = BotWOptions
