from dataclasses import dataclass

from Options import DefaultOnToggle, PerGameCommonOptions, Toggle


class ChestShuffle(DefaultOnToggle):
    """Include the mapped overworld chests in addition to mapped shrine chests."""
    display_name = "Overworld Chest Shuffle"


class MasterTrials(Toggle):
    """Include mapped Master Trials DLC checks/items. Requires a DLC catalog."""
    display_name = "The Master Trials DLC"


class ChampionsBallad(Toggle):
    """Include mapped Champions' Ballad DLC checks/items. Requires a DLC catalog."""
    display_name = "The Champions' Ballad DLC"


class SkipGreatPlateau(DefaultOnToggle):
    """Start with the Plateau tutorial finished and map revealed.

    Applied to a new save through the generated graphic pack. Other regions,
    the Paraglider, rune upgrades, and shrine chest checks retain their normal
    AP requirements.
    """
    display_name = "Skip Great Plateau Tutorial"


@dataclass
class BotWOptions(PerGameCommonOptions):
    skip_great_plateau: SkipGreatPlateau
    chest_shuffle: ChestShuffle
    enable_the_master_trials_dlc: MasterTrials
    enable_the_champions_ballad_dlc: ChampionsBallad


botw_options = BotWOptions
