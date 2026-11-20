from dataclasses import dataclass

from Options import Choice, DefaultOnToggle, PerGameCommonOptions, Toggle


class Goal(Choice):
    """Choose the checks required for Victory, always including Dark Beast Ganon.

    All Divine Beasts requires the four Blight defeat checks even with Boss
    Defeat Checks disabled. All Divine Beasts and Trials also requires Trial of
    the Sword completion when both it and The Master Trials DLC are enabled. All Checks
    requires every enabled check. Requirements delay the AP goal report;
    they do not physically prevent an early Ganon fight.
    """
    display_name = "Goal"
    option_dark_beast_ganon = 0
    option_all_divine_beasts = 1
    option_all_divine_beasts_and_trials = 2
    option_all_checks = 3
    default = 2


class ChestSanity(DefaultOnToggle):
    """Include all mapped chests as Archipelago checks."""
    display_name = "ChestSanity"


class ShrineSanity(DefaultOnToggle):
    """Include mapped shrine chests and base-game monk rewards as Archipelago checks."""
    display_name = "ShrineSanity"


class TowerSanity(DefaultOnToggle):
    """Physical tower terminal checks, reachable without receiving a tower item.

    The Plateau tower check is omitted when Skip Great Plateau Tutorial is on.
    Receiving a tower item never completes its physical check.
    """
    display_name = "TowerSanity"


class MinibossSanity(DefaultOnToggle):
    """Include individual Hinox/Stalnox, Talus and Molduga defeats."""
    display_name = "MinibossSanity"


class BossSanity(DefaultOnToggle):
    """Include optional boss defeats. Bosses required by the selected goal
    remain enabled even when this option is disabled.
    """
    display_name = "BossSanity"


class MasterTrials(Toggle):
    """Include mapped Master Trials DLC checks/items. Requires a DLC catalog."""
    display_name = "The Master Trials DLC"


class TrialOfTheSword(DefaultOnToggle):
    """Include Trial of the Sword chests and its completion check.

    Requires The Master Trials DLC. Trial chests also require ChestSanity.
    Disable to remove the trial checks and Victory requirement while retaining
    the DLC's other content.
    This changes the randomizer's checks and logic, not physical access to the trial.
    """
    display_name = "Trial of the Sword"


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
    goal: Goal
    skip_great_plateau: SkipGreatPlateau
    chest_sanity: ChestSanity
    shrine_sanity: ShrineSanity
    tower_sanity: TowerSanity
    miniboss_sanity: MinibossSanity
    boss_sanity: BossSanity
    enable_the_master_trials_dlc: MasterTrials
    trial_of_the_sword: TrialOfTheSword
    enable_the_champions_ballad_dlc: ChampionsBallad


botw_options = BotWOptions
