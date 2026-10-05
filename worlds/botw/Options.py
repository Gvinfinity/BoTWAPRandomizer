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


@dataclass
class BotWOptions(PerGameCommonOptions):
    chest_shuffle: ChestShuffle
    enable_the_master_trials_dlc: MasterTrials
    enable_the_champions_ballad_dlc: ChampionsBallad


botw_options = BotWOptions
