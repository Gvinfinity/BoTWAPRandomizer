from worlds.generic.Rules import set_rule

from .logic import compile_requirement
from .reference import item_data, item_groups, manual_locations, manual_regions


def set_rules(world):
    def rule(expression):
        return compile_requirement(expression, world.player, item_data, item_groups)

    for name, data in manual_regions.items():
        # The starting area is reachable before its tower is activated.
        requirement = rule("" if name == "Great Plateau" else data.get("requires", ""))
        if name != "Great Plateau":
            original = requirement
            requirement = lambda state, original=original: state.has("Paraglider", world.player) and original(state)
        set_rule(world.get_entrance(f"Menu -> {name}"), requirement)
    for entry in world.active_chests:
        set_rule(world.get_location(entry["name"]), rule(entry.get("requires", "")))
    victory = next(entry for entry in manual_locations if entry.get("victory"))
    set_rule(world.get_location("Dark Beast Ganon Defeated"), rule(victory["requires"]))
    world.multiworld.completion_condition[world.player] = lambda state: state.has("Victory", world.player)
